"""
Unit tests for Database Repository Layer (ParkingRepository).
Uses isolated mock collections to ensure tests run fast in-memory
without touching or mutating real MongoDB Atlas production data.
"""

import unittest
from datetime import datetime
from copy import deepcopy

from pymongo.errors import PyMongoError
from database.repository import ParkingRepository
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot


class MockCursor:
    """Mock MongoDB cursor supporting .sort() and .limit() chaining."""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        for doc in self._docs:
            yield deepcopy(doc)


class MockCollection:
    """In-memory collection mock for isolated repository unit testing."""

    def __init__(self, name="mock_collection"):
        self.name = name
        self.docs = []
        self.indexes = {}
        self.simulate_find_error = False
        self.simulate_index_error = False

    def create_index(self, field, unique=False):
        if self.simulate_index_error:
            raise PyMongoError("Simulated index build error: duplicate keys exist in collection")
        self.indexes[field] = unique
        return f"{field}_1"

    def insert_one(self, doc):
        stored = deepcopy(doc)
        if "_id" not in stored:
            stored["_id"] = len(self.docs) + 1
        self.docs.append(stored)

        class Result:
            inserted_id = stored["_id"]

        return Result()

    def find_one(self, query):
        if self.simulate_find_error:
            raise PyMongoError("Simulated MongoDB network query failure")
        for doc in self.docs:
            if self._matches(doc, query):
                return deepcopy(doc)
        return None

    def find(self, query=None):
        if self.simulate_find_error:
            raise PyMongoError("Simulated MongoDB network query failure")
        if not query:
            return MockCursor(self.docs)
        matching = [d for d in self.docs if self._matches(d, query)]
        return MockCursor(matching)

    def update_one(self, query, update):
        target = None
        for doc in self.docs:
            if self._matches(doc, query):
                target = doc
                break

        matched_count = 1 if target else 0
        modified_count = 0

        if target and "$set" in update:
            for k, v in update["$set"].items():
                target[k] = deepcopy(v)
            modified_count = 1

        class Result:
            pass

        r = Result()
        r.matched_count = matched_count
        r.modified_count = modified_count
        return r

    def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)

                class Result:
                    deleted_count = 1

                return Result()

        class Result:
            deleted_count = 0

        return Result()

    def _matches(self, doc, query):
        for k, v in query.items():
            if doc.get(k) != v:
                return False
        return True


class MockDatabase:
    """Mock MongoDB database returning isolated MockCollections."""

    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name=name)
        return self.collections[name]


class TestParkingRepository(unittest.TestCase):
    def setUp(self):
        self.mock_db = MockDatabase()
        self.repo = ParkingRepository(database=self.mock_db)

    # -------------------------------------------------------------------------
    # Index Creation Tests
    # -------------------------------------------------------------------------
    def test_database_indexes_created(self):
        """Unique indexes must be registered on primary identifier fields."""
        self.assertTrue(self.repo.slots_col.indexes.get("slot_id"))
        self.assertTrue(self.repo.vehicles_col.indexes.get("license_plate"))
        self.assertTrue(self.repo.bookings_col.indexes.get("booking_id"))
        self.assertTrue(self.repo.history_col.indexes.get("history_id"))

    def test_mock_collection_without_create_index_supported(self):
        """A mock collection without create_index must remain supported gracefully."""
        class MockBareCollection:
            def __init__(self):
                self.docs = []

        class MockBareDatabase:
            def __getitem__(self, name):
                return MockBareCollection()

        # Should initialize without raising an AttributeError or exception
        bare_repo = ParkingRepository(database=MockBareDatabase())
        self.assertIsNotNone(bare_repo)

    def test_index_creation_pymongo_error_not_silently_swallowed(self):
        """A PyMongoError during index creation must raise a clear RuntimeError identifying collection and field."""
        error_db = MockDatabase()
        error_db["parking_slots"].simulate_index_error = True

        with self.assertRaises(RuntimeError) as ctx:
            ParkingRepository(database=error_db)

        self.assertIn("Failed to create unique index on 'parking_slots.slot_id'", str(ctx.exception))
        self.assertIn("duplicate keys exist in collection", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 1. Parking Slots Tests
    # -------------------------------------------------------------------------
    def test_slot_crud_operations(self):
        slot = ParkingSlot("F1-S01", floor=1, slot_type="Car")

        # Insert
        slot_id = self.repo.insert_slot(slot)
        self.assertEqual(slot_id, "F1-S01")

        # Duplicate rejection
        with self.assertRaises(ValueError):
            self.repo.insert_slot(slot)

        # Retrieve by ID
        fetched = self.repo.get_slot_by_id("F1-S01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.slot_id, "F1-S01")
        self.assertFalse(fetched.is_occupied)

        # Update slot with parked vehicle
        veh = Vehicle("DL01AB1234", "Car", owner_name="Alice")
        fetched.assign_vehicle(veh)
        updated = self.repo.update_slot(fetched)
        self.assertTrue(updated)

        # Verify updated state persisted
        re_fetched = self.repo.get_slot_by_id("F1-S01")
        self.assertTrue(re_fetched.is_occupied)
        self.assertEqual(re_fetched.vehicle.license_plate, "DL01AB1234")

        # Get all slots
        all_slots = self.repo.get_all_slots()
        self.assertEqual(len(all_slots), 1)

        # Delete slot
        deleted = self.repo.delete_slot("F1-S01")
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_slot_by_id("F1-S01"))

    def test_slot_precheck_error_handling(self):
        """Database errors during pre-check queries must be handled as RuntimeError."""
        self.repo.slots_col.simulate_find_error = True
        slot = ParkingSlot("F2-S05", floor=2, slot_type="Car")
        with self.assertRaises(RuntimeError) as ctx:
            self.repo.insert_slot(slot)
        self.assertIn("Database error inserting slot", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. Vehicles Tests
    # -------------------------------------------------------------------------
    def test_vehicle_crud_operations(self):
        v = Vehicle("MH12CD5678", "Bike", owner_name="Bob", owner_phone="9876543210")

        # Insert
        plate = self.repo.insert_vehicle(v)
        self.assertEqual(plate, "MH12CD5678")

        # Duplicate plate rejection
        with self.assertRaises(ValueError):
            self.repo.insert_vehicle(v)

        # Get by plate (case & format insensitive)
        fetched = self.repo.get_vehicle_by_plate("mh-12 cd-5678")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.license_plate, "MH12CD5678")
        self.assertEqual(fetched.vehicle_type, "Bike")
        self.assertEqual(fetched.owner_name, "Bob")
        self.assertIsInstance(fetched.entry_time, datetime)

        # Get all vehicles
        vehicles = self.repo.get_all_vehicles()
        self.assertEqual(len(vehicles), 1)

        # Update vehicle
        fetched.owner_name = "Robert"
        self.assertTrue(self.repo.update_vehicle(fetched))
        self.assertEqual(self.repo.get_vehicle_by_plate("MH12CD5678").owner_name, "Robert")

        # Delete vehicle
        self.assertTrue(self.repo.delete_vehicle("MH12CD5678"))
        self.assertIsNone(self.repo.get_vehicle_by_plate("MH12CD5678"))

    def test_vehicle_precheck_error_handling(self):
        """Database errors during vehicle duplicate pre-check must raise RuntimeError."""
        self.repo.vehicles_col.simulate_find_error = True
        v = Vehicle("UP14AA1111", "Car")
        with self.assertRaises(RuntimeError) as ctx:
            self.repo.insert_vehicle(v)
        self.assertIn("Database error inserting vehicle", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Bookings Tests
    # -------------------------------------------------------------------------
    def test_booking_crud_operations(self):
        booking_data = {
            "license_plate": "KA01ZZ9999",
            "vehicle_type": "Car",
            "owner_name": "Charlie"
        }

        # Create
        booking_id = self.repo.create_booking(booking_data)
        self.assertIsNotNone(booking_id)

        # Get by ID
        fetched = self.repo.get_booking_by_id(booking_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["license_plate"], "KA01ZZ9999")
        self.assertEqual(fetched["status"], "WAITING")
        self.assertIsInstance(fetched["created_at"], datetime)

        # Update status
        self.assertTrue(self.repo.update_booking_status(booking_id, "ALLOCATED"))
        self.assertEqual(self.repo.get_booking_by_id(booking_id)["status"], "ALLOCATED")

        # Filter by status
        waiting_bookings = self.repo.get_all_bookings(status="WAITING")
        self.assertEqual(len(waiting_bookings), 0)
        allocated_bookings = self.repo.get_all_bookings(status="ALLOCATED")
        self.assertEqual(len(allocated_bookings), 1)

        # Delete booking
        self.assertTrue(self.repo.delete_booking(booking_id))
        self.assertIsNone(self.repo.get_booking_by_id(booking_id))

    def test_booking_validation_and_id_normalization(self):
        """Validate license_plate string check and uppercase normalization of booking_id."""
        # Missing license plate
        with self.assertRaises(ValueError):
            self.repo.create_booking({})

        # Empty / non-string license plate
        with self.assertRaises(ValueError):
            self.repo.create_booking({"license_plate": ""})
        with self.assertRaises(ValueError):
            self.repo.create_booking({"license_plate": "   "})
        with self.assertRaises(ValueError):
            self.repo.create_booking({"license_plate": 12345})

        # Explicit lowercase booking_id must be stored uppercase
        b_id = self.repo.create_booking({
            "booking_id": "custom-book-01",
            "license_plate": "DL02XY1234"
        })
        self.assertEqual(b_id, "CUSTOM-BOOK-01")

        # Retrieve using either case
        retrieved = self.repo.get_booking_by_id("custom-book-01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["booking_id"], "CUSTOM-BOOK-01")

    # -------------------------------------------------------------------------
    # 4. Parking History Tests
    # -------------------------------------------------------------------------
    def test_parking_history_crud_operations(self):
        log_entry = {
            "license_plate": "DL09EV0001",
            "slot_id": "F1-E01",
            "action": "CHECK_IN",
            "fee": 0.0
        }

        # Log
        history_id = self.repo.log_history(log_entry)
        self.assertIsNotNone(history_id)

        # Retrieve by ID
        record = self.repo.get_history_by_id(history_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["license_plate"], "DL09EV0001")
        self.assertEqual(record["action"], "CHECK_IN")
        self.assertIsInstance(record["timestamp"], datetime)

        # Retrieve by plate
        plate_records = self.repo.get_history_by_plate("dl 09-ev 0001")
        self.assertEqual(len(plate_records), 1)

        # Retrieve all
        all_records = self.repo.get_all_history(limit=10)
        self.assertEqual(len(all_records), 1)

        # Delete record
        self.assertTrue(self.repo.delete_history_by_id(history_id))
        self.assertIsNone(self.repo.get_history_by_id(history_id))

    def test_history_id_normalization_and_limit_validation(self):
        """Explicit history_id must be normalized uppercase, and limit must be a positive int."""
        h_id = self.repo.log_history({
            "history_id": "hist-log-abc",
            "license_plate": "DL03ZZ7777",
            "slot_id": "F1-S02",
            "action": "CHECK_OUT"
        })
        self.assertEqual(h_id, "HIST-LOG-ABC")

        retrieved = self.repo.get_history_by_id("hist-log-abc")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["history_id"], "HIST-LOG-ABC")

        # Limit validation
        with self.assertRaises(ValueError):
            self.repo.get_all_history(limit=0)
        with self.assertRaises(ValueError):
            self.repo.get_all_history(limit=-5)
        with self.assertRaises(ValueError):
            self.repo.get_all_history(limit="10")
        with self.assertRaises(ValueError):
            self.repo.get_all_history(limit=True)  # Booleans rejected
        with self.assertRaises(ValueError):
            self.repo.get_all_history(limit=False)


if __name__ == "__main__":
    unittest.main()
