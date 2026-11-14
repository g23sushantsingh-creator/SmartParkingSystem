"""
Unit tests for Domain Models: Vehicle and ParkingSlot.
Includes tests for normal operations, edge cases, type safety, and state invariants.
"""

import unittest
from datetime import datetime
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot


class TestVehicleModel(unittest.TestCase):
    def test_vehicle_creation_and_normalization(self):
        v = Vehicle(license_plate=" dl 01-ab 1234 ", vehicle_type="car", owner_name="Alice", owner_phone="9876543210")
        self.assertEqual(v.license_plate, "DL01AB1234")
        self.assertEqual(v.vehicle_type, "Car")
        self.assertEqual(v.owner_name, "Alice")
        self.assertEqual(v.owner_phone, "9876543210")
        self.assertIsInstance(v.entry_time, datetime)

    def test_vehicle_invalid_inputs(self):
        # Empty / whitespace plates
        with self.assertRaises(ValueError):
            Vehicle(license_plate="")
        with self.assertRaises(ValueError):
            Vehicle(license_plate="   ")
        with self.assertRaises(ValueError):
            Vehicle(license_plate="---")
        # Non-string plates
        with self.assertRaises(TypeError):
            Vehicle(license_plate=12345)
        # Invalid vehicle type
        with self.assertRaises(ValueError):
            Vehicle(license_plate="DL01AB1234", vehicle_type="Airplane")

    def test_vehicle_type_string_validation(self):
        """Validate vehicle_type must be a string before calling strip()."""
        with self.assertRaises(TypeError):
            Vehicle(license_plate="DL01AB1234", vehicle_type=123)
        with self.assertRaises(TypeError):
            Vehicle(license_plate="DL01AB1234", vehicle_type=None)
        with self.assertRaises(TypeError):
            Vehicle(license_plate="DL01AB1234", vehicle_type=["Car"])

    def test_vehicle_serialization_roundtrip(self):
        fixed_time = datetime(2026, 11, 10, 10, 30, 0)
        v1 = Vehicle("MH12DE4567", "Bike", entry_time=fixed_time, owner_name="Bob", owner_phone="1234567890")
        data = v1.to_dict()

        self.assertEqual(data["license_plate"], "MH12DE4567")
        self.assertEqual(data["vehicle_type"], "Bike")
        self.assertEqual(data["entry_time"], "2026-11-10T10:30:00")

        v2 = Vehicle.from_dict(data)
        self.assertEqual(v1, v2)
        self.assertEqual(v2.license_plate, "MH12DE4567")
        self.assertEqual(v2.vehicle_type, "Bike")
        self.assertEqual(v2.entry_time, fixed_time)

    def test_vehicle_from_dict_invalid_entry_time(self):
        """In from_dict(), raise a clear ValueError for invalid entry_time."""
        invalid_data = {
            "license_plate": "DL01AB1234",
            "vehicle_type": "Car",
            "entry_time": "invalid-timestamp-string"
        }
        with self.assertRaises(ValueError) as ctx:
            Vehicle.from_dict(invalid_data)
        self.assertIn("Invalid entry_time string format", str(ctx.exception))

        invalid_type_data = {
            "license_plate": "DL01AB1234",
            "vehicle_type": "Car",
            "entry_time": 123456789
        }
        with self.assertRaises(ValueError) as ctx2:
            Vehicle.from_dict(invalid_type_data)
        self.assertIn("Invalid entry_time type", str(ctx2.exception))

    def test_vehicle_equality_and_hash(self):
        v1 = Vehicle("KA01XY9999", "Car")
        v2 = Vehicle("ka-01 xy-9999", "Car")
        self.assertEqual(v1, v2)
        self.assertEqual(hash(v1), hash(v2))


class TestParkingSlotModel(unittest.TestCase):
    def test_slot_creation(self):
        slot = ParkingSlot(slot_id="F1-S01", floor=1, slot_type="Car")
        self.assertEqual(slot.slot_id, "F1-S01")
        self.assertEqual(slot.floor, 1)
        self.assertEqual(slot.slot_type, "Car")
        self.assertFalse(slot.is_occupied)
        self.assertIsNone(slot.vehicle)

    def test_slot_id_validation_after_normalization(self):
        """Validate slot_id type and non-blank check after normalization."""
        with self.assertRaises(TypeError):
            ParkingSlot(slot_id=101, floor=1)
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="", floor=1)
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="   ", floor=1)

    def test_floor_positive_integer_validation(self):
        """Validate that floor must be a positive integer (> 0)."""
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="F0-S01", floor=0)
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="F-1-S01", floor=-1)
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="F1-S01", floor="1")  # Must be int, not string
        with self.assertRaises(ValueError):
            ParkingSlot(slot_id="F1-S01", floor=True)  # Booleans are not valid floor integers

    def test_occupancy_state_consistency(self):
        """
        Enforce consistent occupancy state:
        - A slot without a vehicle must not be marked occupied.
        - A slot containing a vehicle must always be marked occupied.
        """
        # Slot without vehicle marked occupied -> must raise ValueError
        with self.assertRaises(ValueError) as ctx1:
            ParkingSlot(slot_id="F1-S01", floor=1, is_occupied=True, vehicle=None)
        self.assertIn("A slot without a vehicle cannot be marked as occupied", str(ctx1.exception))

        # Slot with vehicle marked unoccupied -> must raise ValueError
        v = Vehicle("DL01AB1234", "Car")
        with self.assertRaises(ValueError) as ctx2:
            ParkingSlot(slot_id="F1-S01", floor=1, is_occupied=False, vehicle=v)
        self.assertIn("A slot containing a vehicle must always be marked as occupied", str(ctx2.exception))

        # Initializing with vehicle defaults is_occupied to True
        slot_with_veh = ParkingSlot(slot_id="F1-S02", floor=1, vehicle=v)
        self.assertTrue(slot_with_veh.is_occupied)
        self.assertEqual(slot_with_veh.vehicle, v)

    def test_slot_vehicle_assignment_and_release(self):
        slot = ParkingSlot(slot_id="F1-S01", floor=1, slot_type="Car")
        v = Vehicle("DL01AB1234", "Car")

        # Assign
        slot.assign_vehicle(v)
        self.assertTrue(slot.is_occupied)
        self.assertEqual(slot.vehicle, v)

        # Cannot assign another vehicle while occupied
        v2 = Vehicle("DL02CD5678", "Car")
        with self.assertRaises(ValueError):
            slot.assign_vehicle(v2)

        # Release
        released = slot.release_vehicle()
        self.assertEqual(released, v)
        self.assertFalse(slot.is_occupied)
        self.assertIsNone(slot.vehicle)

    def test_type_compatibility(self):
        bike_slot = ParkingSlot("F1-B01", floor=1, slot_type="Bike")
        car_vehicle = Vehicle("DL01AB1234", "Car")

        # Incompatible vehicle type
        with self.assertRaises(ValueError):
            bike_slot.assign_vehicle(car_vehicle)

        # Compatible EV in Car slot
        car_slot = ParkingSlot("F1-C01", floor=1, slot_type="Car")
        ev_vehicle = Vehicle("DL09EV0001", "EV")
        car_slot.assign_vehicle(ev_vehicle)
        self.assertTrue(car_slot.is_occupied)

    def test_slot_serialization_roundtrip(self):
        slot = ParkingSlot("F2-S10", floor=2, slot_type="Car")
        v = Vehicle("UP16ZZ1111", "Car", owner_name="Charlie")
        slot.assign_vehicle(v)

        serialized = slot.to_dict()
        self.assertEqual(serialized["slot_id"], "F2-S10")
        self.assertTrue(serialized["is_occupied"])
        self.assertIsNotNone(serialized["vehicle"])
        self.assertEqual(serialized["vehicle"]["license_plate"], "UP16ZZ1111")

        reconstructed = ParkingSlot.from_dict(serialized)
        self.assertEqual(reconstructed.slot_id, "F2-S10")
        self.assertEqual(reconstructed.floor, 2)
        self.assertTrue(reconstructed.is_occupied)
        self.assertEqual(reconstructed.vehicle.license_plate, "UP16ZZ1111")
        self.assertEqual(reconstructed.vehicle.owner_name, "Charlie")

    def test_slot_from_dict_inconsistent_occupancy(self):
        """Inconsistent occupancy flags in persisted data must be rejected on reconstruction."""
        # Occupied flag true, but no vehicle
        bad_doc_1 = {
            "slot_id": "F1-S01",
            "floor": 1,
            "slot_type": "Car",
            "is_occupied": True,
            "vehicle": None
        }
        with self.assertRaises(ValueError):
            ParkingSlot.from_dict(bad_doc_1)

        # Occupied flag false, but vehicle present
        bad_doc_2 = {
            "slot_id": "F1-S01",
            "floor": 1,
            "slot_type": "Car",
            "is_occupied": False,
            "vehicle": {
                "license_plate": "DL01AB1234",
                "vehicle_type": "Car",
                "entry_time": "2026-11-10T10:00:00"
            }
        }
        with self.assertRaises(ValueError):
            ParkingSlot.from_dict(bad_doc_2)


if __name__ == "__main__":
    unittest.main()
