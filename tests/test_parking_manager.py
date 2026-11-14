"""
Unit tests for ParkingManager service.
Uses an injected in-memory repository to test all core operations,
state synchronization, waitlist processing, failure injection recovery,
and DSA state exports without needing a live MongoDB connection.
"""

import unittest
from datetime import datetime, timedelta

from pymongo.errors import PyMongoError
from database.repository import ParkingRepository
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot
from services.parking_manager import ParkingManager
from tests.test_repository import MockDatabase


class TestParkingManager(unittest.TestCase):
    def setUp(self):
        self.mock_db = MockDatabase()
        self.repo = ParkingRepository(database=self.mock_db)
        self.manager = ParkingManager(repository=self.repo)

    # -------------------------------------------------------------------------
    # 1. Initialization and State Hydration Tests
    # -------------------------------------------------------------------------
    def test_hydration_from_preexisting_db_records(self):
        """Manager should hydrate existing slots, vehicles, and WAITING bookings upon init."""
        # Pre-seed mock database directly
        v1 = Vehicle("DL01AA1111", "Car", owner_name="Alice")
        s1 = ParkingSlot("F1-S01", floor=1, slot_type="Car")
        s1.assign_vehicle(v1)

        s2 = ParkingSlot("F1-S02", floor=1, slot_type="Bike")

        self.repo.insert_slot(s1)
        self.repo.insert_slot(s2)
        self.repo.create_booking({"license_plate": "DL02BB2222", "vehicle_type": "Car", "status": "WAITING"})
        self.repo.create_booking({"license_plate": "DL03CC3333", "vehicle_type": "Bike", "status": "ALLOCATED"})

        # Initialize fresh manager pointing to pre-seeded repository
        hydrated_manager = ParkingManager(repository=self.repo)

        # Verify slots loaded into custom Hash Map
        self.assertEqual(len(hydrated_manager.get_all_slots()), 2)
        slot1 = hydrated_manager.get_slot_by_id("F1-S01")
        self.assertIsNotNone(slot1)
        self.assertTrue(slot1.is_occupied)
        self.assertEqual(slot1.vehicle.license_plate, "DL01AA1111")

        # Verify vehicle-to-slot lookup
        self.assertEqual(hydrated_manager.get_slot_by_vehicle("DL01AA1111").slot_id, "F1-S01")

        # Verify only WAITING booking loaded into BookingQueue
        self.assertEqual(len(hydrated_manager.waiting_queue), 1)
        self.assertEqual(hydrated_manager.waiting_queue.peek()["license_plate"], "DL02BB2222")

    # -------------------------------------------------------------------------
    # 2. Slot & Vehicle Management Tests
    # -------------------------------------------------------------------------
    def test_add_parking_slot_and_duplicate_handling(self):
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        slot_id = self.manager.add_parking_slot(slot)
        self.assertEqual(slot_id, "F1-C01")

        # Hash Map fast lookup
        self.assertEqual(self.manager.get_slot_by_id("F1-C01"), slot)

        # Duplicate addition rejection
        with self.assertRaises(ValueError):
            self.manager.add_parking_slot(slot)

        # Verify action pushed to stack
        recent = self.manager.get_recent_actions(1)
        self.assertEqual(recent[0]["action"], "ADD_SLOT")
        self.assertEqual(recent[0]["slot_id"], "F1-C01")

    def test_register_vehicle_and_differing_duplicate_details(self):
        """Duplicate registration must not silently overwrite the canonical existing record."""
        v_orig = Vehicle("UP16AB1234", "Car", owner_name="Original Owner", owner_phone="111111")
        plate = self.manager.register_vehicle(v_orig)
        self.assertEqual(plate, "UP16AB1234")

        # Second registration attempt with conflicting details
        v_imposter = Vehicle("UP16AB1234", "Car", owner_name="Imposter Owner", owner_phone="999999")
        plate2 = self.manager.register_vehicle(v_imposter)
        self.assertEqual(plate2, "UP16AB1234")

        # Canonical record must be preserved in memory and DB
        fetched = self.manager.get_vehicle_by_plate("UP16AB1234")
        self.assertEqual(fetched.owner_name, "Original Owner")
        self.assertEqual(fetched.owner_phone, "111111")

        db_record = self.repo.get_vehicle_by_plate("UP16AB1234")
        self.assertEqual(db_record.owner_name, "Original Owner")

    # -------------------------------------------------------------------------
    # 3. Park Vehicle & Canonical Vehicle Tests
    # -------------------------------------------------------------------------
    def test_park_vehicle_auto_allocation(self):
        self.manager.add_parking_slot(ParkingSlot("F1-B01", floor=1, slot_type="Bike"))
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))

        # Park Car -> should auto-allocate F1-C01
        assigned_slot = self.manager.park_vehicle("DL04DD4444", vehicle_type="Car", owner_name="David")
        self.assertEqual(assigned_slot.slot_id, "F1-C01")
        self.assertTrue(assigned_slot.is_occupied)
        self.assertEqual(assigned_slot.vehicle.license_plate, "DL04DD4444")

        # Lookup by vehicle plate
        self.assertEqual(self.manager.get_slot_by_vehicle("DL04DD4444").slot_id, "F1-C01")

        # Cannot park again while already parked
        with self.assertRaises(ValueError) as ctx:
            self.manager.park_vehicle("DL04DD4444", vehicle_type="Car")
        self.assertIn("already parked", str(ctx.exception))

    def test_park_vehicle_explicit_slot_and_compatibility(self):
        self.manager.add_parking_slot(ParkingSlot("F1-B01", floor=1, slot_type="Bike"))
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))

        # Incompatible slot: Car in Bike slot
        with self.assertRaises(ValueError) as ctx:
            self.manager.park_vehicle("DL05EE5555", vehicle_type="Car", slot_id="F1-B01")
        self.assertIn("Incompatible vehicle type", str(ctx.exception))

        # Compatible EV in Car slot
        ev_slot = self.manager.park_vehicle("DL06EV0001", vehicle_type="EV", slot_id="F1-C01")
        self.assertEqual(ev_slot.slot_id, "F1-C01")
        self.assertTrue(ev_slot.is_occupied)

    def test_park_vehicle_when_full_raises_value_error(self):
        # No slots available
        with self.assertRaises(ValueError) as ctx:
            self.manager.park_vehicle("DL07FF7777", vehicle_type="Car")
        self.assertIn("No available compatible parking slot", str(ctx.exception))

    def test_park_canonical_vehicle_preserved(self):
        """Pre-existing canonical vehicle details must be preserved when parked with different input values."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Pre-seed canonical vehicle in database
        v_canon = Vehicle("CANON_01", "Car", owner_name="Canonical Alice", owner_phone="111-222")
        self.repo.insert_vehicle(v_canon)

        # Attempt to park vehicle specifying conflicting details
        parked_slot = self.manager.park_vehicle("CANON_01", "Car", owner_name="Bob Imposter", owner_phone="999-000")

        # Both slot vehicle and in-memory vehicles_map must preserve Canonical Alice
        self.assertEqual(parked_slot.vehicle.owner_name, "Canonical Alice")
        self.assertEqual(parked_slot.vehicle.owner_phone, "111-222")
        mem_veh = self.manager.get_vehicle_by_plate("CANON_01")
        self.assertEqual(mem_veh.owner_name, "Canonical Alice")

        # DB must still contain Canonical Alice
        db_veh = self.repo.get_vehicle_by_plate("CANON_01")
        self.assertEqual(db_veh.owner_name, "Canonical Alice")

    # -------------------------------------------------------------------------
    # 4. Check-Out and Billing Tests
    # -------------------------------------------------------------------------
    def test_checkout_vehicle_and_billing(self):
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Park vehicle with past entry time (2 hours ago)
        past_time = datetime.now() - timedelta(hours=2, minutes=15)
        v = Vehicle("DL08GG8888", "Car", entry_time=past_time)
        slot.assign_vehicle(v)
        self.repo.insert_vehicle(v)
        self.manager.slots_map.insert(slot.slot_id, slot)
        self.manager.vehicle_to_slot_map.insert(v.license_plate, slot.slot_id)
        self.manager.vehicles_map.insert(v.license_plate, v)
        self.repo.update_slot(slot)

        receipt = self.manager.checkout_vehicle("DL08GG8888", hourly_rate=30.0)

        self.assertEqual(receipt["license_plate"], "DL08GG8888")
        self.assertEqual(receipt["slot_id"], "F1-C01")
        self.assertGreaterEqual(receipt["duration_hours"], 2.2)
        self.assertGreater(receipt["fee"], 60.0)

        # Verify slot is vacated
        updated_slot = self.manager.get_slot_by_id("F1-C01")
        self.assertFalse(updated_slot.is_occupied)
        self.assertIsNone(updated_slot.vehicle)

        # Verify lookup removed from vehicle_to_slot_map, but preserved in vehicles_map
        self.assertIsNone(self.manager.get_slot_by_vehicle("DL08GG8888"))
        self.assertIsNotNone(self.manager.get_vehicle_by_plate("DL08GG8888"))

        # Checkout non-parked vehicle raises ValueError
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("NONEXISTENT_CAR")

    def test_checkout_preserves_registered_vehicle_in_vehicles_map(self):
        """
        Regression test:
        1. A registered vehicle remains in vehicles_map after checkout.
        2. Its entry is removed from vehicle_to_slot_map.
        3. Its parking slot becomes available.
        """
        slot = ParkingSlot("F1-S01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("SYNC_CAR_01", vehicle_type="Car", owner_name="Alice")

        # Verify before checkout
        self.assertIsNotNone(self.manager.get_vehicle_by_plate("SYNC_CAR_01"))
        self.assertIsNotNone(self.manager.get_slot_by_vehicle("SYNC_CAR_01"))
        self.assertTrue(self.manager.get_slot_by_id("F1-S01").is_occupied)

        # Checkout
        receipt = self.manager.checkout_vehicle("SYNC_CAR_01")
        self.assertEqual(receipt["license_plate"], "SYNC_CAR_01")

        # 1. Registered vehicle remains in vehicles_map
        preserved_veh = self.manager.get_vehicle_by_plate("SYNC_CAR_01")
        self.assertIsNotNone(preserved_veh)
        self.assertEqual(preserved_veh.owner_name, "Alice")
        self.assertTrue(self.manager.vehicles_map.contains("SYNC_CAR_01"))

        # 2. Its entry is removed from vehicle_to_slot_map
        self.assertIsNone(self.manager.get_slot_by_vehicle("SYNC_CAR_01"))
        self.assertFalse(self.manager.vehicle_to_slot_map.contains("SYNC_CAR_01"))

        # 3. Its parking slot becomes available
        vacated_slot = self.manager.get_slot_by_id("F1-S01")
        self.assertFalse(vacated_slot.is_occupied)
        self.assertIsNone(vacated_slot.vehicle)

    # -------------------------------------------------------------------------
    # 5. Waitlist Queue & Automated Slot Allocation
    # -------------------------------------------------------------------------
    def test_waitlist_queue_and_auto_allocation_on_checkout(self):
        # Create 1 Car slot
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))

        # Park first car -> parking is now FULL
        self.manager.park_vehicle("CAR_1", vehicle_type="Car", owner_name="First")

        # Second car attempts to park -> fails, added to waitlist
        b1 = self.manager.add_booking_to_waitlist("CAR_2", vehicle_type="Car", owner_name="Second")
        self.assertEqual(b1["status"], "WAITING")
        self.assertEqual(len(self.manager.waiting_queue), 1)

        # Third car added to waitlist
        b2 = self.manager.add_booking_to_waitlist("CAR_3", vehicle_type="Car", owner_name="Third")
        self.assertEqual(len(self.manager.waiting_queue), 2)

        # Checkout CAR_1: frees F1-C01, which should automatically allocate to CAR_2 (FIFO front)
        receipt = self.manager.checkout_vehicle("CAR_1")
        next_alloc = receipt["next_allocated_booking"]

        self.assertIsNotNone(next_alloc)
        self.assertEqual(next_alloc["license_plate"], "CAR_2")
        self.assertEqual(next_alloc["slot_id"], "F1-C01")

        # Waiting queue now has only CAR_3
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "CAR_3")

        # F1-C01 is occupied again by CAR_2
        slot = self.manager.get_slot_by_id("F1-C01")
        self.assertTrue(slot.is_occupied)
        self.assertEqual(slot.vehicle.license_plate, "CAR_2")

        # Stack verification: LIFO newest on top: PARK -> AUTOMATIC_ALLOCATION -> CHECK_OUT
        stack_list = self.manager.get_stack_state()
        self.assertEqual(stack_list[0]["action"], "PARK")
        self.assertEqual(stack_list[0]["license_plate"], "CAR_2")
        self.assertEqual(stack_list[0]["slot_id"], "F1-C01")

        self.assertEqual(stack_list[1]["action"], "AUTOMATIC_ALLOCATION")
        self.assertEqual(stack_list[1]["license_plate"], "CAR_2")
        self.assertEqual(stack_list[1]["slot_id"], "F1-C01")

        self.assertEqual(stack_list[2]["action"], "CHECK_OUT")
        self.assertEqual(stack_list[2]["license_plate"], "CAR_1")
        self.assertEqual(stack_list[2]["slot_id"], "F1-C01")

    def test_process_next_waiting_booking_pushes_automatic_allocation_to_stack(self):
        """Successful waitlist allocation records AUTOMATIC_ALLOCATION before the PARK session."""
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        booking = self.manager.add_booking_to_waitlist("WAIT_01", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Process next
        alloc = self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc["license_plate"], "WAIT_01")

        stack_list = self.manager.get_stack_state()
        self.assertEqual(stack_list[0]["action"], "PARK")
        self.assertEqual(stack_list[0]["license_plate"], "WAIT_01")
        self.assertEqual(stack_list[1]["action"], "AUTOMATIC_ALLOCATION")
        self.assertEqual(stack_list[1]["license_plate"], "WAIT_01")
        self.assertEqual(stack_list[1]["booking_id"], booking["booking_id"])
        self.assertEqual(stack_list[1]["slot_id"], "F1-C01")

    def test_checkout_when_waiting_queue_is_empty_leaves_checkout_on_top(self):
        """When waiting queue is empty, normal checkout leaves CHECK_OUT on top of stack."""
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("SOLO_CAR", vehicle_type="Car")
        receipt = self.manager.checkout_vehicle("SOLO_CAR")

        self.assertIsNone(receipt["next_allocated_booking"])
        slot = self.manager.get_slot_by_id("F1-C01")
        self.assertFalse(slot.is_occupied)
        self.assertIsNone(slot.vehicle)

        top_action = self.manager.action_stack.peek()
        self.assertEqual(top_action["action"], "CHECK_OUT")
        self.assertEqual(top_action["license_plate"], "SOLO_CAR")

    def test_waitlist_duplicate_rejection_and_policy(self):
        """Cannot add an already parked, already waitlisted, or vehicle when slots are available."""
        # 1. Enforce waitlist policy: cannot add when compatible slot is vacant
        self.manager.add_parking_slot(ParkingSlot("F1-S01", floor=1, slot_type="Car"))
        with self.assertRaises(ValueError) as ctx:
            self.manager.add_booking_to_waitlist("CAR_WAIT", vehicle_type="Car")
        self.assertIn("Compatible slot", str(ctx.exception))
        self.assertIn("is currently available", str(ctx.exception))

        # Park car to fill the slot
        self.manager.park_vehicle("PARKED_CAR", vehicle_type="Car")

        # 2. Cannot waitlist an already parked car
        with self.assertRaises(ValueError) as ctx1:
            self.manager.add_booking_to_waitlist("PARKED_CAR")
        self.assertIn("already parked", str(ctx1.exception))

        # 3. Add to waitlist now that slot is full
        self.manager.add_booking_to_waitlist("WAIT_CAR")

        # 4. Duplicate waitlist entry rejected
        with self.assertRaises(ValueError) as ctx2:
            self.manager.add_booking_to_waitlist("WAIT_CAR")
        self.assertIn("already in the waitlist", str(ctx2.exception))

    # -------------------------------------------------------------------------
    # 6. Verifiable Persistence Failure & Compensation Tests (Parking)
    # -------------------------------------------------------------------------
    def test_park_recovery_on_vehicle_insert_failure_after_slot_update(self):
        """If vehicle insertion fails after slot update, slot must be reverted to vacant in DB and memory."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Simulate vehicle insertion failure
        orig_insert = self.repo.vehicles_col.insert_one
        self.repo.vehicles_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated vehicle insert error"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.park_vehicle("VEH_FAIL", vehicle_type="Car")
        self.assertIn("Failed to persist vehicle parking", str(ctx.exception))

        # Restore
        self.repo.vehicles_col.insert_one = orig_insert

        # In-memory slot must be vacant
        in_mem_slot = self.manager.get_slot_by_id("F1-C01")
        self.assertFalse(in_mem_slot.is_occupied)
        self.assertIsNone(in_mem_slot.vehicle)
        self.assertIsNone(self.manager.get_slot_by_vehicle("VEH_FAIL"))

        # Database slot must also be compensated and reverted to vacant
        db_slot = self.repo.get_slot_by_id("F1-C01")
        self.assertFalse(db_slot.is_occupied)
        self.assertIsNone(db_slot.vehicle)

    def test_park_recovery_on_history_log_failure_during_parking(self):
        """If history logging fails during parking, slot is reverted and inserted vehicle is cleaned up."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Simulate history logging failure
        orig_log = self.repo.history_col.insert_one
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated history insert error"))

        with self.assertRaises(RuntimeError):
            self.manager.park_vehicle("HIST_FAIL", vehicle_type="Car")

        # Restore
        self.repo.history_col.insert_one = orig_log

        # In-memory slot must be vacant
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)
        self.assertIsNone(self.manager.get_slot_by_vehicle("HIST_FAIL"))

        # Database slot must be vacant
        self.assertFalse(self.repo.get_slot_by_id("F1-C01").is_occupied)
        # Compensating delete should have cleaned up the vehicle record from DB
        self.assertIsNone(self.repo.get_vehicle_by_plate("HIST_FAIL"))

    def test_parking_rollback_fails_to_update_slot(self):
        """If compensating slot update fails during rollback, raise diagnostic error with partial failure."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Primary failure: history logging fails
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Primary history failure"))

        # Secondary failure: compensating update_slot returns False
        orig_update = self.repo.slots_col.update_one
        call_count = {"val": 0}

        def failing_compensation(query, update):
            call_count["val"] += 1
            if call_count["val"] == 1:
                # Step 1: primary update_slot succeeds
                return orig_update(query, update)
            # Step 2: compensating update_slot fails
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()

        self.repo.slots_col.update_one = failing_compensation

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.park_vehicle("FAIL_COMP_SLOT", vehicle_type="Car")

        self.assertIn("CRITICAL: Compensating rollback also failed", str(ctx.exception))
        self.assertIn("Compensating slot update failed for 'F1-C01'", str(ctx.exception))

        # In-memory slot is released to avoid phantom occupancy
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)

    def test_parking_rollback_fails_to_delete_inserted_vehicle(self):
        """If compensating vehicle deletion fails during rollback, raise diagnostic error identifying it."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Primary failure: history logging fails
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Primary history failure"))

        # Secondary failure: compensating delete_vehicle returns False
        self.repo.vehicles_col.delete_one = lambda query: type("Result", (), {"deleted_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.park_vehicle("FAIL_COMP_DEL", vehicle_type="Car")

        self.assertIn("CRITICAL: Compensating rollback also failed", str(ctx.exception))
        self.assertIn("Compensating vehicle deletion failed for 'FAIL_COMP_DEL'", str(ctx.exception))

        # Vehicle is still in DB (since deletion failed) but in-memory slot is released
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("FAIL_COMP_DEL"))
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)

    # -------------------------------------------------------------------------
    # 7. Verifiable Persistence Failure & Compensation Tests (Checkout)
    # -------------------------------------------------------------------------
    def test_checkout_recovery_on_vehicle_deletion_failure(self):
        """If vehicle deletion fails during checkout, slot must be restored to occupied in DB and memory."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("CAR_DEL_FAIL", vehicle_type="Car")

        # Simulate vehicle deletion failure (matched 0)
        orig_delete = self.repo.vehicles_col.delete_one
        self.repo.vehicles_col.delete_one = lambda query: type("Result", (), {"deleted_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.checkout_vehicle("CAR_DEL_FAIL")
        self.assertIn("Failed to persist vehicle checkout", str(ctx.exception))

        # Restore
        self.repo.vehicles_col.delete_one = orig_delete

        # In-memory slot must remain occupied
        slot_mem = self.manager.get_slot_by_id("F1-C01")
        self.assertTrue(slot_mem.is_occupied)
        self.assertEqual(slot_mem.vehicle.license_plate, "CAR_DEL_FAIL")
        self.assertIsNotNone(self.manager.get_slot_by_vehicle("CAR_DEL_FAIL"))

        # Database slot must remain compensated as occupied
        db_slot = self.repo.get_slot_by_id("F1-C01")
        self.assertTrue(db_slot.is_occupied)
        self.assertEqual(db_slot.vehicle.license_plate, "CAR_DEL_FAIL")

    def test_checkout_recovery_on_history_log_failure(self):
        """If history logging fails during checkout, slot and deleted vehicle must be compensated."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("CAR_HIST_FAIL", vehicle_type="Car")

        # Simulate history logging failure during checkout
        orig_log = self.repo.history_col.insert_one
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated history checkout failure"))

        with self.assertRaises(RuntimeError):
            self.manager.checkout_vehicle("CAR_HIST_FAIL")

        # Restore
        self.repo.history_col.insert_one = orig_log

        # In-memory slot must remain occupied
        slot_mem = self.manager.get_slot_by_id("F1-C01")
        self.assertTrue(slot_mem.is_occupied)
        self.assertEqual(slot_mem.vehicle.license_plate, "CAR_HIST_FAIL")

        # Database slot must remain occupied
        db_slot = self.repo.get_slot_by_id("F1-C01")
        self.assertTrue(db_slot.is_occupied)

        # Vehicle must be restored into database
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("CAR_HIST_FAIL"))

    def test_checkout_rollback_fails_to_restore_slot(self):
        """If compensating slot update fails during checkout rollback, raise diagnostic error identifying it."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("CHECK_COMP_SLOT", vehicle_type="Car")

        # Primary failure: history logging fails
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("History fail"))

        # Secondary failure: compensating update_slot returns False
        orig_update = self.repo.slots_col.update_one
        calls = {"n": 0}

        def failing_comp_update(q, u):
            calls["n"] += 1
            if calls["n"] == 1:
                return orig_update(q, u)  # Primary checkout update succeeds
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()  # Compensation fails

        self.repo.slots_col.update_one = failing_comp_update

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.checkout_vehicle("CHECK_COMP_SLOT")

        self.assertIn("CRITICAL: Compensating rollback also failed", str(ctx.exception))
        self.assertIn("Compensating slot update failed for 'F1-C01'", str(ctx.exception))

        # In-memory slot remains occupied
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)

    def test_checkout_rollback_fails_to_reinsert_deleted_vehicle(self):
        """If compensating vehicle re-insertion fails during checkout rollback, raise diagnostic error."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("CHECK_COMP_VEH", vehicle_type="Car")

        # Primary failure: history logging fails
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("History fail"))

        # Secondary failure: compensating insert_vehicle throws
        orig_insert = self.repo.vehicles_col.insert_one
        self.repo.vehicles_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Cannot reinsert vehicle"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.checkout_vehicle("CHECK_COMP_VEH")

        self.assertIn("CRITICAL: Compensating rollback also failed", str(ctx.exception))
        self.assertIn("Compensating vehicle re-insertion failed for 'CHECK_COMP_VEH'", str(ctx.exception))

        # In-memory slot remains occupied
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)

    # -------------------------------------------------------------------------
    # 8. Detailed Waitlist Allocation Consistency & FIFO Order Tests
    # -------------------------------------------------------------------------
    def test_failed_allocation_of_middle_queue_booking_restores_fifo_position(self):
        """
        If a middle-queue booking is selected and allocation fails,
        it must be restored to its exact original position in the queue.
        Example: [TRUCK_1, CAR_2, BIKE_3] -> CAR_2 fails -> [TRUCK_1, CAR_2, BIKE_3].
        """
        # Fill parking slots so waitlist can be populated
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.add_parking_slot(ParkingSlot("F1-B01", floor=1, slot_type="Bike"))
        self.manager.park_vehicle("OCC_CAR", vehicle_type="Car")
        self.manager.park_vehicle("OCC_BIKE", vehicle_type="Bike")

        # Enqueue 3 bookings: Truck (incompatible with Car slot), Car, Bike
        self.manager.add_booking_to_waitlist("TRUCK_1", vehicle_type="Truck")
        self.manager.add_booking_to_waitlist("CAR_2", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("BIKE_3", vehicle_type="Bike")

        # Queue is currently: TRUCK_1 (front), CAR_2 (middle), BIKE_3 (rear)
        plates_before = [b["license_plate"] for b in self.manager.waiting_queue]
        self.assertEqual(plates_before, ["TRUCK_1", "CAR_2", "BIKE_3"])

        # Now free the Car slot
        car_slot = self.manager.get_slot_by_id("F1-C01")
        car_slot.release_vehicle()
        self.repo.update_slot(car_slot)
        self.manager.vehicle_to_slot_map.delete("OCC_CAR")
        self.repo.delete_vehicle("OCC_CAR")

        # Simulate park_vehicle failure for CAR_2 (e.g. database error during update_slot)
        orig_update = self.repo.slots_col.update_one
        self.repo.slots_col.update_one = lambda q, u: type("Result", (), {"matched_count": 0, "modified_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")
        self.assertIn("Waitlist allocation failed for booking", str(ctx.exception))

        # Restore update_one
        self.repo.slots_col.update_one = orig_update

        # CRITICAL FIFO ORDER CHECK:
        # CAR_2 must be in the exact middle index, NOT appended to the rear!
        plates_after = [b["license_plate"] for b in self.manager.waiting_queue]
        self.assertEqual(plates_after, ["TRUCK_1", "CAR_2", "BIKE_3"])

    def test_waitlist_rollback_vacant_slot_update_failure_prevents_vehicle_deletion(self):
        """
        When updating booking to ALLOCATED fails, if compensating update_slot (to vacant) fails:
        1. Vehicle must NOT be deleted from DB.
        2. In-memory slot must remain occupied.
        3. Booking must NOT be re-enqueued as WAITING.
        4. Diagnostic RuntimeError must be raised.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")

        # Free slot so waitlist can process it
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Primary failure: update booking to ALLOCATED fails
        orig_update_booking = self.repo.bookings_col.update_one

        def failing_alloc_update(q, u):
            if u.get("$set", {}).get("status") == "ALLOCATED":
                return type("Result", (), {"matched_count": 0, "modified_count": 0})()
            return orig_update_booking(q, u)

        self.repo.bookings_col.update_one = failing_alloc_update

        # Secondary failure: compensating update_slot to vacant returns False
        orig_update_slot = self.repo.slots_col.update_one
        calls = {"n": 0}

        def failing_unpark_slot(q, u):
            calls["n"] += 1
            if calls["n"] == 1:
                return orig_update_slot(q, u)  # park_vehicle update_slot succeeds
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()  # unpark update_slot fails

        self.repo.slots_col.update_one = failing_unpark_slot

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        err_msg = str(ctx.exception)
        self.assertIn("CRITICAL: Compensating unpark could not be verified", err_msg)
        self.assertIn("Compensating slot update to vacant returned False", err_msg)
        self.assertIn("Booking was NOT re-enqueued as WAITING", err_msg)

        # 1. Vehicle was NOT deleted from DB
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("WAITING_CAR"))

        # 2. In-memory slot remains occupied
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)

        # 3. Booking must NOT be in queue (prevents duplicate state)
        self.assertEqual(len(self.manager.waiting_queue), 0)

    def test_waitlist_rollback_vehicle_deletion_failure_restores_occupied_slot(self):
        """
        When updating booking to ALLOCATED fails, if compensating vehicle deletion fails:
        1. Attempt to restore slot to occupied in both MongoDB and memory.
        2. Booking must NOT be re-enqueued as WAITING.
        3. Diagnostic RuntimeError must be raised.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Primary failure: update booking to ALLOCATED fails
        orig_update_booking = self.repo.bookings_col.update_one

        def failing_alloc_update(q, u):
            if u.get("$set", {}).get("status") == "ALLOCATED":
                return type("Result", (), {"matched_count": 0, "modified_count": 0})()
            return orig_update_booking(q, u)

        self.repo.bookings_col.update_one = failing_alloc_update

        # Secondary failure: compensating delete_vehicle returns False
        self.repo.vehicles_col.delete_one = lambda q: type("Result", (), {"deleted_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        err_msg = str(ctx.exception)
        self.assertIn("CRITICAL: Compensating unpark could not be verified", err_msg)
        self.assertIn("Compensating vehicle deletion returned False", err_msg)
        self.assertIn("Booking was NOT re-enqueued as WAITING", err_msg)

        # 1. Slot is restored to occupied in memory
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)

        # 2. Slot is restored to occupied in MongoDB
        self.assertTrue(self.repo.get_slot_by_id("F1-C01").is_occupied)

        # 3. Vehicle still exists in DB
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("WAITING_CAR"))

        # 4. Booking was NOT re-enqueued as WAITING
        self.assertEqual(len(self.manager.waiting_queue), 0)

    def test_waitlist_park_failure_with_status_restoration_false(self):
        """
        When park_vehicle fails during waitlist processing and restoring booking status
        back to WAITING in database returns False:
        1. Booking IS restored to in-memory queue at original position.
        2. Clear diagnostic error is raised mentioning the warning about database status restoration.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # 1. Park fails via insert_vehicle throwing PyMongoError
        self.repo.vehicles_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated vehicle insert error"))

        # 2. update_booking_status to WAITING returns False
        self.repo.bookings_col.update_one = lambda q, u: type("Result", (), {"matched_count": 0, "modified_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        err_msg = str(ctx.exception)
        self.assertIn("Waitlist allocation failed for booking", err_msg)
        self.assertIn("Booking restored to in-memory queue at original position", err_msg)
        self.assertIn("database status restoration to WAITING failed (update_booking_status returned False)", err_msg)
        self.assertIn("Manual database reconciliation required", err_msg)

        # Verify in-memory queue restored at original index
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "WAITING_CAR")

    def test_waitlist_park_failure_with_status_restoration_exception(self):
        """
        When park_vehicle fails during waitlist processing and restoring booking status
        back to WAITING in database raises an exception:
        1. Booking IS restored to in-memory queue at original position.
        2. Clear diagnostic error is raised with exception details and warning.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # 1. Park fails via insert_vehicle throwing PyMongoError
        self.repo.vehicles_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated vehicle insert error"))

        # 2. update_booking_status raises PyMongoError
        self.repo.bookings_col.update_one = lambda q, u: (_ for _ in ()).throw(PyMongoError("Simulated status update error"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        err_msg = str(ctx.exception)
        self.assertIn("Waitlist allocation failed for booking", err_msg)
        self.assertIn("Booking restored to in-memory queue at original position", err_msg)
        self.assertIn("database status restoration to WAITING failed", err_msg)
        self.assertIn("Simulated status update error", err_msg)
        self.assertIn("Manual database reconciliation required", err_msg)

        # Verify in-memory queue restored at original index
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "WAITING_CAR")

    def test_waitlist_rollback_records_history_and_action_stack(self):
        """
        When waitlist allocation fails on marking booking ALLOCATED and compensating unpark succeeds:
        1. Original CHECK_IN history record is preserved in MongoDB.
        2. WAITLIST_ALLOCATION_ROLLBACK event is logged in MongoDB parking history.
        3. WAITLIST_ALLOCATION_ROLLBACK action is pushed to action stack.
        4. Booking is restored to waiting queue at original position.
        5. Booking status in MongoDB is restored to WAITING.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        booking_data = self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")
        booking_id = booking_data["booking_id"]

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Simulate update booking to ALLOCATED failing, while update to WAITING succeeds
        orig_update_booking = self.repo.bookings_col.update_one

        def failing_alloc_update(q, u):
            if u.get("$set", {}).get("status") == "ALLOCATED":
                return type("Result", (), {"matched_count": 0, "modified_count": 0})()
            return orig_update_booking(q, u)

        self.repo.bookings_col.update_one = failing_alloc_update

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        self.assertIn("Compensating unpark succeeded and booking restored to waiting queue at original position", str(ctx.exception))

        # 1. Original CHECK_IN history record is preserved
        all_history = self.repo.get_all_history()
        checkin_records = [h for h in all_history if h.get("action") == "CHECK_IN" and h.get("license_plate") == "WAITING_CAR"]
        self.assertEqual(len(checkin_records), 1)

        # 2. WAITLIST_ALLOCATION_ROLLBACK history event is logged in MongoDB
        rollback_history = [h for h in all_history if h.get("action") == "WAITLIST_ALLOCATION_ROLLBACK" and h.get("license_plate") == "WAITING_CAR"]
        self.assertEqual(len(rollback_history), 1)
        self.assertEqual(rollback_history[0]["booking_id"], booking_id)
        self.assertEqual(rollback_history[0]["slot_id"], "F1-C01")

        # 3. WAITLIST_ALLOCATION_ROLLBACK action is pushed to custom action stack
        top_action = self.manager.action_stack.peek()
        self.assertEqual(top_action["action"], "WAITLIST_ALLOCATION_ROLLBACK")
        self.assertEqual(top_action["booking_id"], booking_id)
        self.assertEqual(top_action["license_plate"], "WAITING_CAR")
        self.assertEqual(top_action["slot_id"], "F1-C01")

        # 4. Booking is restored to in-memory queue at original position
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "WAITING_CAR")

        # 5. Booking status in database is WAITING
        db_booking = self.repo.get_booking_by_id(booking_id)
        self.assertEqual(db_booking["status"], "WAITING")

        # 6. Slot in DB and memory is vacant, and vehicle is deleted
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)
        self.assertFalse(self.repo.get_slot_by_id("F1-C01").is_occupied)
        self.assertIsNone(self.repo.get_vehicle_by_plate("WAITING_CAR"))
        self.assertFalse(self.manager.vehicles_map.contains("WAITING_CAR"))

    def test_restoring_booking_status_to_waiting_returns_false(self):
        """If unpark succeeds but restoring status to WAITING returns False, raise diagnostic error with warning."""
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("WAITING_CAR", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Update booking: ALLOCATED fails, and WAITING restore also fails (returns False)
        self.repo.bookings_col.update_one = lambda q, u: type("Result", (), {"matched_count": 0, "modified_count": 0})()

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        self.assertIn("Compensating unpark succeeded, but restoring booking status to WAITING in database failed", str(ctx.exception))
        self.assertIn("Manual booking status reconciliation in database required", str(ctx.exception))

        # Unpark succeeded: slot is vacant in DB and memory
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)
        self.assertFalse(self.repo.get_slot_by_id("F1-C01").is_occupied)

        # Booking IS restored to in-memory queue at original position
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "WAITING_CAR")

    def test_waitlist_rollback_preserves_preexisting_vehicle_registration(self):
        """
        When a booking vehicle was pre-registered in the system, and waitlist allocation
        rollback occurs (due to failure updating booking to ALLOCATED):
        1. Compensating unpark must NOT delete the vehicle from MongoDB.
        2. Compensating unpark must NOT remove the vehicle from in-memory vehicles_map.
        3. Pre-existing vehicle attributes (owner_name, phone) must remain intact.
        4. Slot is vacated and booking restored to waiting queue.
        """
        # Pre-register vehicle with canonical owner details
        v_pre = Vehicle("PRE_EXIST_CAR", vehicle_type="Car", owner_name="Canonical Owner", owner_phone="9988776655")
        self.manager.register_vehicle(v_pre)

        # Slot setup
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")

        # Add pre-existing vehicle to waitlist
        booking_data = self.manager.add_booking_to_waitlist("PRE_EXIST_CAR", vehicle_type="Car")
        booking_id = booking_data["booking_id"]

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # Simulate update booking to ALLOCATED failing
        orig_update_booking = self.repo.bookings_col.update_one

        def failing_alloc_update(q, u):
            if u.get("$set", {}).get("status") == "ALLOCATED":
                return type("Result", (), {"matched_count": 0, "modified_count": 0})()
            return orig_update_booking(q, u)

        self.repo.bookings_col.update_one = failing_alloc_update

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        self.assertIn("Compensating unpark succeeded and booking restored to waiting queue at original position", str(ctx.exception))

        # 1. Pre-existing vehicle is NOT deleted from MongoDB
        db_veh = self.repo.get_vehicle_by_plate("PRE_EXIST_CAR")
        self.assertIsNotNone(db_veh)
        self.assertEqual(db_veh.owner_name, "Canonical Owner")
        self.assertEqual(db_veh.owner_phone, "9988776655")

        # 2. Pre-existing vehicle is NOT deleted from in-memory vehicles_map
        self.assertTrue(self.manager.vehicles_map.contains("PRE_EXIST_CAR"))
        mem_veh = self.manager.get_vehicle_by_plate("PRE_EXIST_CAR")
        self.assertEqual(mem_veh.owner_name, "Canonical Owner")

        # 3. Vehicle is no longer in vehicle_to_slot_map (slot is vacant)
        self.assertFalse(self.manager.vehicle_to_slot_map.contains("PRE_EXIST_CAR"))
        self.assertFalse(self.manager.get_slot_by_id("F1-C01").is_occupied)
        self.assertFalse(self.repo.get_slot_by_id("F1-C01").is_occupied)

        # 4. Booking is restored to queue
        self.assertEqual(len(self.manager.waiting_queue), 1)
        self.assertEqual(self.manager.waiting_queue.peek()["license_plate"], "PRE_EXIST_CAR")

    def test_waitlist_park_failure_with_incomplete_compensation_prevents_requeue(self):
        """
        When park_vehicle() fails during waitlist processing AND its compensating
        rollback is incomplete (e.g. compensating update_slot returns False):
        1. Booking must NOT be restored to the in-memory waiting queue.
        2. Diagnostic error is raised explaining that manual reconciliation is required.
        """
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("OCCUPANT", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("FAIL_COMP_CAR", vehicle_type="Car")

        # Free slot
        slot = self.manager.get_slot_by_id("F1-C01")
        slot.release_vehicle()
        self.repo.update_slot(slot)
        self.manager.vehicle_to_slot_map.delete("OCCUPANT")
        self.repo.delete_vehicle("OCCUPANT")

        # In park_vehicle:
        # Step 1: primary update_slot succeeds (slot updated to occupied)
        # Step 2: insert_vehicle succeeds
        # Step 3: log_history fails -> triggers compensating rollback
        # Compensating Step 1: compensating update_slot returns False -> rollback fails!
        orig_update_slot = self.repo.slots_col.update_one
        slot_calls = {"n": 0}

        def failing_comp_slot(q, u):
            slot_calls["n"] += 1
            if slot_calls["n"] == 1:
                return orig_update_slot(q, u)  # Primary park update_slot succeeds
            # Compensating update_slot fails
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()

        self.repo.slots_col.update_one = failing_comp_slot
        self.repo.history_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated history insert failure"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.process_next_waiting_booking(compatible_slot_id="F1-C01")

        err_msg = str(ctx.exception)
        self.assertIn("Parking persistence failed and compensating rollback was incomplete", err_msg)
        self.assertIn("Booking was NOT re-enqueued as WAITING", err_msg)
        self.assertIn("Manual database reconciliation required", err_msg)

        # CRITICAL ASSERTION: Booking was NOT restored to waiting_queue
        self.assertEqual(len(self.manager.waiting_queue), 0)

    # -------------------------------------------------------------------------
    # 9. Complete DSA State Exporters Tests
    # -------------------------------------------------------------------------
    def test_dsa_state_exporters_and_metrics(self):
        """Verify all three HashMaps, Queue, and Stack are accurately exported."""
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("DL09AA0001", vehicle_type="Car")
        self.manager.add_booking_to_waitlist("DL09BB0002", vehicle_type="Car")

        # 1. HashMap State: all three maps must be present
        hm_state = self.manager.get_hashmap_state()
        self.assertIn("slots_hashmap", hm_state)
        self.assertIn("vehicle_to_slot_hashmap", hm_state)
        self.assertIn("vehicles_hashmap", hm_state)
        self.assertIsInstance(hm_state["slots_hashmap"]["buckets"], list)
        self.assertEqual(hm_state["slots_hashmap"]["size"], 1)
        self.assertEqual(hm_state["vehicles_hashmap"]["size"], 1)

        # 2. Queue State
        q_state = self.manager.get_queue_state()
        self.assertEqual(len(q_state), 1)
        self.assertEqual(q_state[0]["license_plate"], "DL09BB0002")

        # 3. Stack State
        stack_state = self.manager.get_stack_state()
        self.assertGreaterEqual(len(stack_state), 3)  # ADD_SLOT, PARK, WAITLIST_ENQUEUE
        self.assertEqual(stack_state[0]["action"], "WAITLIST_ENQUEUE")

        # 4. Metrics: includes sizes, capacities, load factors for all three maps
        metrics = self.manager.get_dsa_metrics()
        self.assertEqual(metrics["slots_map_size"], 1)
        self.assertEqual(metrics["vehicle_to_slot_map_size"], 1)
        self.assertEqual(metrics["vehicles_map_size"], 1)
        self.assertIn("slots_map_load_factor", metrics)
        self.assertIn("vehicle_to_slot_map_load_factor", metrics)
        self.assertIn("vehicles_map_load_factor", metrics)
        self.assertEqual(metrics["waitlist_queue_size"], 1)
        self.assertGreaterEqual(metrics["action_stack_size"], 3)

    # -------------------------------------------------------------------------
    # 10. Input Validations
    # -------------------------------------------------------------------------
    def test_input_validations(self):
        self.manager.add_parking_slot(ParkingSlot("F1-C01", floor=1, slot_type="Car"))
        self.manager.park_vehicle("VAL_CAR", vehicle_type="Car")

        # hourly_rate validations
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=0)
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=-10)
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=True)  # Booleans rejected
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=float("inf"))
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=float("nan"))
        with self.assertRaises(ValueError):
            # Extremely large integers safely rejected
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=10**100)
        with self.assertRaises(ValueError):
            self.manager.checkout_vehicle("VAL_CAR", hourly_rate=200_000.0)

        # get_recent_actions count validations
        with self.assertRaises(ValueError):
            self.manager.get_recent_actions(count=-1)
        with self.assertRaises(ValueError):
            self.manager.get_recent_actions(count=True)  # Booleans rejected
        with self.assertRaises(ValueError):
            self.manager.get_recent_actions(count="5")


if __name__ == "__main__":
    unittest.main()
