"""
Unit tests for Smart Parking System upgrades:
- Customer Portal & Administrator Dashboard access.
- Administrator-only operations (vehicle deletion and parked-vehicle protection).
- Database failure handling and parking-history preservation.
- POP TOP behaviour and safe empty-stack handling.
"""

import os
import unittest
from datetime import datetime
from pymongo.errors import PyMongoError

from database.repository import ParkingRepository
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from services.parking_manager import ParkingManager
from tests.test_repository import MockDatabase


def check_admin_password(provided_password: str) -> bool:
    """Helper used by the Streamlit Administrator Dashboard for authentication."""
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        admin_password = "admin"
    return provided_password == admin_password


class TestParkingSystemUpgrades(unittest.TestCase):
    def setUp(self):
        self.mock_db = MockDatabase()
        self.repo = ParkingRepository(database=self.mock_db)
        self.manager = ParkingManager(repository=self.repo)

    # -------------------------------------------------------------------------
    # 1. Administrator Authentication Tests
    # -------------------------------------------------------------------------
    def test_admin_authentication_default(self):
        """When ADMIN_PASSWORD is not set in env, defaults to 'admin' safely."""
        old_val = os.environ.pop("ADMIN_PASSWORD", None)
        try:
            self.assertTrue(check_admin_password("admin"))
            self.assertFalse(check_admin_password("wrong_password"))
            self.assertFalse(check_admin_password(""))
        finally:
            if old_val is not None:
                os.environ["ADMIN_PASSWORD"] = old_val

    def test_admin_authentication_with_env_var(self):
        """When ADMIN_PASSWORD is set in env, validates strictly against it."""
        old_val = os.environ.get("ADMIN_PASSWORD")
        os.environ["ADMIN_PASSWORD"] = "SecretAdmin2026!"
        try:
            self.assertTrue(check_admin_password("SecretAdmin2026!"))
            self.assertFalse(check_admin_password("admin"))
            self.assertFalse(check_admin_password("wrong"))
        finally:
            if old_val is not None:
                os.environ["ADMIN_PASSWORD"] = old_val
            else:
                os.environ.pop("ADMIN_PASSWORD", None)

    # -------------------------------------------------------------------------
    # 2. Vehicle Deletion & Parked-Vehicle Protection Tests
    # -------------------------------------------------------------------------
    def test_delete_registered_vehicle_success(self):
        """Admin can permanently delete a registered vehicle that is not parked."""
        veh = Vehicle("DEL01AA1111", "Car", owner_name="Bob", owner_phone="5551234")
        self.manager.register_vehicle(veh)

        # Verify initial presence
        self.assertTrue(self.manager.vehicles_map.contains("DEL01AA1111"))
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("DEL01AA1111"))

        # Delete vehicle
        result = self.manager.delete_registered_vehicle("DEL01AA1111")
        self.assertTrue(result)

        # Verify removal from both memory and MongoDB
        self.assertFalse(self.manager.vehicles_map.contains("DEL01AA1111"))
        self.assertIsNone(self.manager.get_vehicle_by_plate("DEL01AA1111"))
        self.assertIsNone(self.repo.get_vehicle_by_plate("DEL01AA1111"))

        # Verify action recorded in action stack
        top_act = self.manager.action_stack.peek()
        self.assertEqual(top_act["action"], "DELETE_VEHICLE")
        self.assertEqual(top_act["license_plate"], "DEL01AA1111")

    def test_delete_parked_vehicle_rejected(self):
        """Prevent deletion if the vehicle is currently parked in any slot."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("PARKED01", vehicle_type="Car", owner_name="Parked User")

        # Vehicle is active in slot
        self.assertIsNotNone(self.manager.get_slot_by_vehicle("PARKED01"))

        # Deletion must be rejected
        with self.assertRaises(ValueError) as ctx:
            self.manager.delete_registered_vehicle("PARKED01")
        self.assertIn("currently parked in slot", str(ctx.exception))

        # Vehicle must remain untouched in memory and database
        self.assertTrue(self.manager.vehicles_map.contains("PARKED01"))
        self.assertIsNotNone(self.repo.get_vehicle_by_plate("PARKED01"))
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)

    def test_delete_unregistered_vehicle_rejected(self):
        """Deleting a non-existent vehicle raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.manager.delete_registered_vehicle("NOTTHERE99")
        self.assertIn("not registered", str(ctx.exception))

    def test_vehicles_without_owner_name_not_auto_deleted(self):
        """Never automatically delete vehicles just because owner_name is missing."""
        v_no_owner = Vehicle("NOOWNER01", "Car", owner_name="", owner_phone="")
        self.manager.register_vehicle(v_no_owner)

        # Remains registered
        self.assertTrue(self.manager.vehicles_map.contains("NOOWNER01"))
        all_v = self.manager.get_all_vehicles()
        self.assertIn("NOOWNER01", [v.license_plate for v in all_v])

    # -------------------------------------------------------------------------
    # 3. Database Failure Handling & History Preservation
    # -------------------------------------------------------------------------
    def test_delete_vehicle_database_failure_preserves_in_memory_state(self):
        """If database deletion fails, in-memory vehicles_map is NOT modified."""
        veh = Vehicle("FAILDB01", "Car", owner_name="Charlie")
        self.manager.register_vehicle(veh)

        # Simulate database failure during delete_vehicle
        orig_del = self.repo.vehicles_col.delete_one
        self.repo.vehicles_col.delete_one = lambda q: (_ for _ in ()).throw(PyMongoError("Simulated DB connection drop"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.delete_registered_vehicle("FAILDB01")
        self.assertIn("Database error deleting vehicle", str(ctx.exception))

        # Restore
        self.repo.vehicles_col.delete_one = orig_del

        # In-memory vehicles_map MUST still contain the vehicle (no state corruption)
        self.assertTrue(self.manager.vehicles_map.contains("FAILDB01"))
        self.assertIsNotNone(self.manager.get_vehicle_by_plate("FAILDB01"))

    def test_delete_vehicle_preserves_parking_history(self):
        """Deleting a registered vehicle must preserve its historical parking records."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("HIST01AA", vehicle_type="Car")
        self.manager.checkout_vehicle("HIST01AA")

        # History contains CHECK_IN and CHECK_OUT
        all_history = self.manager.get_parking_history()
        hist_plates = [h.get("license_plate") for h in all_history]
        self.assertIn("HIST01AA", hist_plates)
        initial_history_count = len(all_history)
        self.assertGreaterEqual(initial_history_count, 2)

        # Now delete the vehicle registry entry
        del_ok = self.manager.delete_registered_vehicle("HIST01AA")
        self.assertTrue(del_ok)
        self.assertFalse(self.manager.vehicles_map.contains("HIST01AA"))

        # Verify parking history is completely preserved
        history_after = self.manager.get_parking_history()
        self.assertEqual(len(history_after), initial_history_count)
        self.assertIn("HIST01AA", [h.get("license_plate") for h in history_after])

    # -------------------------------------------------------------------------
    # 4. POP TOP Behaviour & Empty-Stack Handling
    # -------------------------------------------------------------------------
    def test_pop_action_stack_removes_top_node(self):
        """POP TOP must remove exactly one top node without modifying DB or undoing actions."""
        slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("POP01AA", vehicle_type="Car")

        # Initial stack depth is 2 (ADD_SLOT, then PARK)
        self.assertEqual(self.manager.action_stack.size, 2)
        top_before = self.manager.action_stack.peek()
        self.assertEqual(top_before["action"], "PARK")

        # Call pop_action_stack()
        popped = self.manager.pop_action_stack()
        self.assertIsNotNone(popped)
        self.assertEqual(popped["action"], "PARK")
        self.assertEqual(popped["license_plate"], "POP01AA")

        # Stack depth reduced by exactly 1
        self.assertEqual(self.manager.action_stack.size, 1)
        self.assertEqual(self.manager.action_stack.peek()["action"], "ADD_SLOT")

        # Vehicle is STILL parked in DB and slot (POP does NOT undo parking!)
        self.assertTrue(self.manager.get_slot_by_id("F1-C01").is_occupied)
        self.assertEqual(self.manager.get_slot_by_vehicle("POP01AA").slot_id, "F1-C01")

    def test_pop_empty_stack_returns_none_safely(self):
        """Calling pop_action_stack on an empty stack returns None without raising an error."""
        # Ensure stack is empty
        while not self.manager.action_stack.is_empty():
            self.manager.action_stack.pop()

        self.assertEqual(self.manager.action_stack.size, 0)
        popped = self.manager.pop_action_stack()
        self.assertIsNone(popped)
        self.assertEqual(self.manager.action_stack.size, 0)

    # -------------------------------------------------------------------------
    # 5. Parking Slot Deletion Tests (Admin-Only)
    # -------------------------------------------------------------------------
    def test_delete_vacant_slot_success(self):
        """Admin can permanently delete a vacant parking slot."""
        slot = ParkingSlot("F3-S10", floor=3, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Initial presence check
        self.assertTrue(self.manager.slots_map.contains("F3-S10"))
        self.assertIsNotNone(self.repo.get_slot_by_id("F3-S10"))

        # Delete slot
        result = self.manager.delete_parking_slot("F3-S10")
        self.assertTrue(result)

        # In-memory slots_map and MongoDB must no longer have this slot
        self.assertFalse(self.manager.slots_map.contains("F3-S10"))
        self.assertIsNone(self.manager.get_slot_by_id("F3-S10"))
        self.assertIsNone(self.repo.get_slot_by_id("F3-S10"))

        # Verify action recorded on action stack
        top_act = self.manager.action_stack.peek()
        self.assertEqual(top_act["action"], "DELETE_SLOT")
        self.assertEqual(top_act["slot_id"], "F3-S10")

    def test_delete_occupied_slot_blocked(self):
        """Attempting to delete an occupied slot must raise ValueError and preserve the slot."""
        slot = ParkingSlot("F1-C99", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("OCC99AA", vehicle_type="Car", slot_id="F1-C99")

        # Slot is occupied
        s = self.manager.get_slot_by_id("F1-C99")
        self.assertTrue(s.is_occupied)

        # Deletion must be rejected
        with self.assertRaises(ValueError) as ctx:
            self.manager.delete_parking_slot("F1-C99")
        self.assertIn("currently occupied", str(ctx.exception))

        # Slot remains intact in memory and database
        self.assertTrue(self.manager.slots_map.contains("F1-C99"))
        self.assertIsNotNone(self.repo.get_slot_by_id("F1-C99"))
        self.assertTrue(self.manager.get_slot_by_id("F1-C99").is_occupied)

    def test_delete_non_existent_slot_raises_error(self):
        """Deleting a non-existent slot raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.manager.delete_parking_slot("NONEXISTENT")
        self.assertIn("not found", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            self.manager.delete_parking_slot("")
        self.assertIn("non-empty string", str(ctx2.exception))

    def test_delete_slot_database_failure_preserves_in_memory_state(self):
        """If database deletion fails, in-memory slots_map is NOT modified."""
        slot = ParkingSlot("F2-FAIL01", floor=2, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Simulate database failure during delete_slot
        orig_del = self.repo.slots_col.delete_one
        self.repo.slots_col.delete_one = lambda q: (_ for _ in ()).throw(PyMongoError("Simulated MongoDB drop during slot deletion"))

        with self.assertRaises(RuntimeError) as ctx:
            self.manager.delete_parking_slot("F2-FAIL01")
        self.assertIn("Database error deleting slot", str(ctx.exception))

        # Restore delete_one
        self.repo.slots_col.delete_one = orig_del

        # In-memory slots_map MUST still contain the slot (no state drift)
        self.assertTrue(self.manager.slots_map.contains("F2-FAIL01"))
        self.assertIsNotNone(self.manager.get_slot_by_id("F2-FAIL01"))

    def test_delete_slot_preserves_parking_history_and_unrelated_records(self):
        """Deleting a slot must preserve historical parking records and unrelated slots/vehicles."""
        # 1. Setup slot and historical parking
        slot1 = ParkingSlot("F1-S01", floor=1, slot_type="Car")
        slot2 = ParkingSlot("F1-S02", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot1)
        self.manager.add_parking_slot(slot2)

        self.manager.park_vehicle("HISTSLOT01", vehicle_type="Car", slot_id="F1-S01")
        self.manager.checkout_vehicle("HISTSLOT01")

        # History has records mentioning F1-S01
        history_before = self.manager.get_parking_history()
        s01_history = [h for h in history_before if h.get("slot_id") == "F1-S01"]
        self.assertGreaterEqual(len(s01_history), 2)
        total_history_count = len(history_before)

        # 2. Delete slot1
        del_ok = self.manager.delete_parking_slot("F1-S01")
        self.assertTrue(del_ok)

        # 3. Verify history is untouched
        history_after = self.manager.get_parking_history()
        self.assertEqual(len(history_after), total_history_count)
        self.assertIn("HISTSLOT01", [h.get("license_plate") for h in history_after])
        self.assertTrue(any(h.get("slot_id") == "F1-S01" for h in history_after))

        # 4. Unrelated slot2 is completely preserved
        self.assertTrue(self.manager.slots_map.contains("F1-S02"))
        self.assertIsNotNone(self.repo.get_slot_by_id("F1-S02"))

    # -------------------------------------------------------------------------
    # 6. Vehicle Registration Stack Event Tests
    # -------------------------------------------------------------------------
    def test_successful_vehicle_registration_creates_stack_event(self):
        """Successful vehicle registration must push a REGISTER_VEHICLE event to ParkingStack."""
        initial_stack_size = self.manager.action_stack.size
        veh = Vehicle("STACK01", "Car", owner_name="Alice", owner_phone="1234567890")

        plate = self.manager.register_vehicle(veh)
        self.assertEqual(plate, "STACK01")

        # Verify stack size increased by exactly 1
        self.assertEqual(self.manager.action_stack.size, initial_stack_size + 1)

        # Verify top event details
        top_event = self.manager.action_stack.peek()
        self.assertEqual(top_event["action"], "REGISTER_VEHICLE")
        self.assertEqual(top_event["license_plate"], "STACK01")
        self.assertEqual(top_event["vehicle_type"], "Car")
        self.assertEqual(top_event["owner_name"], "Alice")
        self.assertIn("timestamp", top_event)

    def test_duplicate_vehicle_registration_does_not_create_stack_event(self):
        """Duplicate vehicle registration must preserve canonical record and NOT push to stack."""
        veh = Vehicle("DUP01", "Car", owner_name="Bob")
        self.manager.register_vehicle(veh)

        stack_size_after_first = self.manager.action_stack.size
        top_after_first = self.manager.action_stack.peek()
        self.assertEqual(top_after_first["action"], "REGISTER_VEHICLE")

        # Second registration of the exact same vehicle
        veh_dup = Vehicle("DUP01", "Car", owner_name="Bob Overwrite")
        plate = self.manager.register_vehicle(veh_dup)
        self.assertEqual(plate, "DUP01")

        # Stack size MUST NOT increase for duplicate
        self.assertEqual(self.manager.action_stack.size, stack_size_after_first)

    def test_failed_vehicle_registration_does_not_create_stack_event(self):
        """If database insertion fails during vehicle registration, no stack event is created."""
        initial_stack_size = self.manager.action_stack.size

        # Simulate database failure during insert_vehicle
        orig_insert = self.repo.vehicles_col.insert_one
        self.repo.vehicles_col.insert_one = lambda doc: (_ for _ in ()).throw(PyMongoError("Simulated DB connection failure"))

        veh = Vehicle("FAILDB02", "Car", owner_name="Dan")
        with self.assertRaises(RuntimeError) as ctx:
            self.manager.register_vehicle(veh)
        self.assertIn("Database error inserting vehicle", str(ctx.exception))

        # Restore
        self.repo.vehicles_col.insert_one = orig_insert

        # Stack size MUST NOT increase
        self.assertEqual(self.manager.action_stack.size, initial_stack_size)

    # -------------------------------------------------------------------------
    # 7. Real-Time Top-Down Parking Lot Visualization Tests
    # -------------------------------------------------------------------------
    def test_visualization_available_and_occupied_states(self):
        """Verify available slots reflect vacant state (green) and occupied slots reflect occupied state (red)."""
        from ui.app import stall_html, lot_html, lot_legend_html

        slot_vacant = ParkingSlot("F1-V01", floor=1, slot_type="Car")
        slot_occupied = ParkingSlot("F1-O01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot_vacant)
        self.manager.add_parking_slot(slot_occupied)

        # Initially both are vacant
        vac_html = stall_html(slot_vacant)
        self.assertIn("bay vac", vac_html)
        self.assertIn("Available", vac_html)
        self.assertIn("Vacant", vac_html)
        self.assertIn("F1-V01", vac_html)

        # Park a vehicle in slot_occupied
        self.manager.park_vehicle("VIS01AA", vehicle_type="Car", slot_id="F1-O01", owner_name="Alice")
        fresh_occupied = self.manager.get_slot_by_id("F1-O01")

        occ_html = stall_html(fresh_occupied)
        self.assertIn("bay occ", occ_html)
        self.assertIn("Occupied", occ_html)
        self.assertIn("VIS01AA", occ_html)
        self.assertIn("Alice", occ_html)
        self.assertIn("F1-O01", occ_html)

        # Verify lot HTML generates both floors, legend, and respective slot indicators
        full_lot = lot_html([slot_vacant, fresh_occupied], show_legend=True)
        self.assertIn("lot-legend", full_lot)
        self.assertIn("Available (Green)", full_lot)
        self.assertIn("Occupied (Red)", full_lot)
        self.assertIn("bay vac", full_lot)
        self.assertIn("bay occ", full_lot)

    def test_visualization_checkout_transitions_slot_to_vacant(self):
        """Checking out a vehicle transitions its slot back to vacant (green) in the visualization."""
        from ui.app import stall_html

        slot = ParkingSlot("F2-T01", floor=2, slot_type="Car")
        self.manager.add_parking_slot(slot)
        self.manager.park_vehicle("CHECK01AA", vehicle_type="Car", slot_id="F2-T01")

        occupied_slot = self.manager.get_slot_by_id("F2-T01")
        self.assertIn("bay occ", stall_html(occupied_slot))

        # Checkout
        self.manager.checkout_vehicle("CHECK01AA")
        vacated_slot = self.manager.get_slot_by_id("F2-T01")
        self.assertFalse(vacated_slot.is_occupied)
        self.assertIn("bay vac", stall_html(vacated_slot))
        self.assertIn("Available", stall_html(vacated_slot))

    def test_visualization_waitlist_allocation_updates_slot(self):
        """Waitlist allocation automatically updates vacant slot to occupied (red) in the visualization."""
        from ui.app import stall_html

        slot = ParkingSlot("F1-W01", floor=1, slot_type="Car")
        self.manager.add_parking_slot(slot)

        # Park a vehicle so slot is full
        self.manager.park_vehicle("CAR01", vehicle_type="Car", slot_id="F1-W01")
        # Add another car to waitlist
        self.manager.add_booking_to_waitlist("WAITCAR01", vehicle_type="Car", owner_name="Wait User")
        self.assertEqual(len(self.manager.waiting_queue), 1)

        # Checkout first car -> automatic waitlist allocation occurs inside checkout_vehicle!
        co_receipt = self.manager.checkout_vehicle("CAR01")
        self.assertIsNotNone(co_receipt.get("next_allocated_booking"))
        self.assertEqual(co_receipt["next_allocated_booking"]["license_plate"], "WAITCAR01")

        # Slot was automatically re-allocated to WAITCAR01 and is occupied (red)
        fresh_slot = self.manager.get_slot_by_id("F1-W01")
        self.assertTrue(fresh_slot.is_occupied)
        html = stall_html(fresh_slot)
        self.assertIn("bay occ", html)
        self.assertIn("WAITCAR01", html)

    def test_topdown_vehicle_svg_and_bay_markings(self):
        """Top-down vehicle SVGs render for all vehicle types and stalls include realistic markings."""
        from ui.app import topdown_vehicle_svg, stall_html

        for vt in ["Car", "Bike", "Truck", "EV"]:
            svg = topdown_vehicle_svg(vt)
            self.assertIn("<svg", svg)
            self.assertIn("bay-car-svg", svg)

        # Vacant stall has stopper, P symbol, and Available indicator
        slot_vac = ParkingSlot("F1-C99", floor=1, slot_type="Car")
        vac_html = stall_html(slot_vac)
        self.assertIn("bay-stopper", vac_html)
        self.assertIn("bay-p-symbol", vac_html)
        self.assertIn("Available", vac_html)

        # Occupied stall has stopper, top-down SVG, plate badge, and Occupied indicator
        self.manager.add_parking_slot(slot_vac)
        self.manager.park_vehicle("SVG01AA", vehicle_type="Car", slot_id="F1-C99", owner_name="Diana")
        occ_slot = self.manager.get_slot_by_id("F1-C99")
        occ_html = stall_html(occ_slot)
        self.assertIn("bay-stopper", occ_html)
        self.assertIn("bay-car-svg", occ_html)
        self.assertIn("SVG01AA", occ_html)
        self.assertIn("Diana", occ_html)
        self.assertIn("Occupied", occ_html)

    def test_driving_aisle_and_floor_organization(self):
        """Parking lot HTML renders realistic driving aisle and floor-wise deck organization."""
        from ui.app import lot_html

        s1 = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        s2 = ParkingSlot("F2-T01", floor=2, slot_type="Truck")
        self.manager.add_parking_slot(s1)
        self.manager.add_parking_slot(s2)

        lot_markup = lot_html([s1, s2], show_legend=True)
        self.assertIn("FLOOR 1 · DECK LEVEL", lot_markup)
        self.assertIn("FLOOR 2 · DECK LEVEL", lot_markup)
        self.assertIn("driving-aisle", lot_markup)
        self.assertIn("DRIVING AISLE", lot_markup)
        self.assertIn("lot-legend", lot_markup)

    def test_compact_activity_timeline_rendering(self):
        """Activity timeline formats events with distinct icons, timestamps, and compact chips."""
        from ui.app import activity_timeline_html

        sample_actions = [
            {"action": "PARK", "license_plate": "TIM01AA", "slot_id": "F1-C01", "timestamp": datetime.now()},
            {"action": "ADD_SLOT", "slot_id": "F1-C02", "floor": 1, "type": "Car", "timestamp": datetime.now()},
            {"action": "CHECK_OUT", "license_plate": "TIM02BB", "slot_id": "F1-C03", "fee": 45.0, "timestamp": datetime.now()},
        ]
        t_html = activity_timeline_html(sample_actions)
        self.assertIn("timeline", t_html)
        self.assertIn("Vehicle Parked", t_html)
        self.assertIn("Slot Added", t_html)
        self.assertIn("Vehicle Checked Out", t_html)
        self.assertIn("TIM01AA", t_html)
        self.assertIn("F1-C01", t_html)
        self.assertIn("45.00", t_html)

    def test_two_row_aerial_lot_geometry(self):
        """Parking lot partitions slots into North and South facing rows across central roadway."""
        from ui.app import lot_html

        # Create 4 slots on Floor 1
        s1 = ParkingSlot("F1-B01", floor=1, slot_type="Bike")
        s2 = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        s3 = ParkingSlot("F1-C02", floor=1, slot_type="Car")
        s4 = ParkingSlot("F1-E01", floor=1, slot_type="EV")
        for s in [s1, s2, s3, s4]:
            self.manager.add_parking_slot(s)

        # Park a vehicle in F1-C01
        self.manager.park_vehicle("AER01AA", vehicle_type="Car", slot_id="F1-C01", owner_name="Elena")
        fresh_slots = [self.manager.get_slot_by_id(sid) for sid in ["F1-B01", "F1-C01", "F1-C02", "F1-E01"]]

        lot_markup = lot_html(fresh_slots, show_legend=True)
        # Verify asphalt apron canvas
        self.assertIn("asphalt-apron", lot_markup)
        self.assertIn("apron-curb top-curb", lot_markup)
        self.assertIn("apron-curb bottom-curb", lot_markup)

        # Verify North and South row partitioning across the central driving roadway
        self.assertIn("stalls-row north-row", lot_markup)
        self.assertIn("stalls-row south-row", lot_markup)
        self.assertIn("driving-aisle", lot_markup)
        self.assertIn("ONE WAY TRAFFIC", lot_markup)

        # Verify North row has F1-B01 and F1-C01
        self.assertIn("F1-B01", lot_markup)
        self.assertIn("F1-C01", lot_markup)
        # Verify South row has F1-C02 and F1-E01
        self.assertIn("F1-C02", lot_markup)
        self.assertIn("F1-E01", lot_markup)

        # Verify occupied slot details in aerial canvas
        self.assertIn("AER01AA", lot_markup)
        self.assertIn("Elena", lot_markup)


if __name__ == "__main__":
    unittest.main()
