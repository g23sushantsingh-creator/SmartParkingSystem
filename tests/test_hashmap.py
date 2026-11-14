"""
Unit tests for Custom ParkingHashMap.
Covers normal operations, collision resolution, duplicate key updates,
deletion from bucket chains, dynamic resizing/rehashing, and edge cases.
"""

import unittest
from data_structures.parking_hashmap import ParkingHashMap, HashNode
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot


class TestParkingHashMap(unittest.TestCase):
    def setUp(self):
        # Fresh map with small capacity for predictable testing
        self.map = ParkingHashMap(initial_capacity=5, load_factor_threshold=0.75)

    def test_initial_state(self):
        self.assertEqual(self.map.size, 0)
        self.assertEqual(self.map.capacity, 5)
        self.assertTrue(self.map.is_empty())
        self.assertEqual(len(self.map), 0)

    def test_insert_and_search_basic(self):
        self.map.insert("DL01AB1234", "Slot-F1-01")
        self.assertEqual(self.map.size, 1)
        self.assertFalse(self.map.is_empty())

        # Search via search() and __getitem__
        self.assertEqual(self.map.search("DL01AB1234"), "Slot-F1-01")
        self.assertEqual(self.map["DL01AB1234"], "Slot-F1-01")

        # Search via get()
        self.assertEqual(self.map.get("DL01AB1234"), "Slot-F1-01")
        self.assertEqual(self.map.get("NONEXISTENT", default="DefaultVal"), "DefaultVal")

        # Contains
        self.assertTrue(self.map.contains("DL01AB1234"))
        self.assertTrue("DL01AB1234" in self.map)
        self.assertFalse(self.map.contains("UNKNOWN"))
        self.assertFalse("UNKNOWN" in self.map)

    def test_duplicate_key_update(self):
        """Inserting an existing key should update the value, not increment size."""
        self.map.insert("DL01AB1234", "Slot-01")
        self.assertEqual(self.map.size, 1)
        self.assertEqual(self.map.search("DL01AB1234"), "Slot-01")

        # Update with new slot
        self.map.insert("DL01AB1234", "Slot-99")
        self.assertEqual(self.map.size, 1, "Size should not increase on duplicate key update")
        self.assertEqual(self.map.search("DL01AB1234"), "Slot-99")

        # Update via subscript operator
        self.map["DL01AB1234"] = "Slot-100"
        self.assertEqual(self.map.size, 1)
        self.assertEqual(self.map["DL01AB1234"], "Slot-100")

    def test_update_existing_key_does_not_trigger_resize(self):
        """
        Regression Test:
        Updating an existing key when map is right at the threshold boundary
        must NOT trigger resizing.
        """
        # Capacity 4, threshold 0.75 -> load threshold is 4 * 0.75 = 3
        test_map = ParkingHashMap(initial_capacity=4, load_factor_threshold=0.75)
        test_map.insert("K1", "V1")
        test_map.insert("K2", "V2")
        test_map.insert("K3", "V3")

        self.assertEqual(test_map.size, 3)
        self.assertEqual(test_map.capacity, 4)

        # Update existing key "K2" - if size + 1 was checked first, it would trigger resize to capacity 9
        test_map.insert("K2", "V2_UPDATED")

        self.assertEqual(test_map.size, 3, "Size must remain 3 after updating existing key")
        self.assertEqual(test_map.capacity, 4, "Capacity must NOT increase when updating an existing key")
        self.assertEqual(test_map.search("K2"), "V2_UPDATED")

        # Now insert a NEW 4th key; this MUST trigger resize
        test_map.insert("K4", "V4")
        self.assertEqual(test_map.size, 4)
        self.assertEqual(test_map.capacity, 9, "Capacity should resize to 9 upon inserting genuinely new key")
        self.assertEqual(test_map.search("K2"), "V2_UPDATED")
        self.assertEqual(test_map.search("K4"), "V4")

    def test_collision_resolution_separate_chaining(self):
        """
        Force collisions by mocking _hash to return the exact same bucket index
        or using keys that naturally collide.
        """
        # Create a single-bucket map so every key collides into bucket 0
        collision_map = ParkingHashMap(initial_capacity=1, load_factor_threshold=100.0)

        collision_map.insert("KEY_A", "VAL_A")
        collision_map.insert("KEY_B", "VAL_B")
        collision_map.insert("KEY_C", "VAL_C")

        self.assertEqual(collision_map.size, 3)
        self.assertEqual(collision_map.capacity, 1)

        # All 3 must be retrievable despite all living in bucket 0 chain
        self.assertEqual(collision_map.search("KEY_A"), "VAL_A")
        self.assertEqual(collision_map.search("KEY_B"), "VAL_B")
        self.assertEqual(collision_map.search("KEY_C"), "VAL_C")

        # Check internal state structure: 1 bucket with 3 chained nodes
        internal = collision_map.get_internal_state()
        self.assertEqual(len(internal), 1)
        self.assertEqual(len(internal[0]), 3)

    def test_deletion_from_bucket_chains(self):
        """Test deleting head, middle, and tail nodes in a collision chain."""
        collision_map = ParkingHashMap(initial_capacity=1, load_factor_threshold=100.0)
        collision_map.insert("KEY_1", "V1")  # Head after all inserted
        collision_map.insert("KEY_2", "V2")  # Middle
        collision_map.insert("KEY_3", "V3")  # Tail

        # Delete middle node
        removed_val = collision_map.delete("KEY_2")
        self.assertEqual(removed_val, "V2")
        self.assertEqual(collision_map.size, 2)
        self.assertFalse("KEY_2" in collision_map)
        self.assertTrue("KEY_1" in collision_map)
        self.assertTrue("KEY_3" in collision_map)

        # Delete head node
        removed_head = collision_map.delete("KEY_3")
        self.assertEqual(removed_head, "V3")
        self.assertEqual(collision_map.size, 1)
        self.assertFalse("KEY_3" in collision_map)
        self.assertTrue("KEY_1" in collision_map)

        # Delete remaining tail node
        removed_tail = collision_map.delete("KEY_1")
        self.assertEqual(removed_tail, "V1")
        self.assertEqual(collision_map.size, 0)
        self.assertTrue(collision_map.is_empty())

    def test_dynamic_resizing_and_rehashing(self):
        """
        Verify that exceeding load factor threshold doubles capacity
        and rehashes all elements correctly without losing data.
        """
        # Capacity 4, threshold 0.75 -> max 3 elements before resizing on 4th
        resizing_map = ParkingHashMap(initial_capacity=4, load_factor_threshold=0.75)
        self.assertEqual(resizing_map.capacity, 4)

        resizing_map.insert("K1", "V1")
        resizing_map.insert("K2", "V2")
        resizing_map.insert("K3", "V3")
        self.assertEqual(resizing_map.capacity, 4)
        self.assertEqual(resizing_map.size, 3)

        # 4th element exceeds (3 + 1)/4 = 1.0 > 0.75 -> triggers resize
        resizing_map.insert("K4", "V4")
        self.assertGreater(resizing_map.capacity, 4)
        self.assertEqual(resizing_map.size, 4)

        # Verify all elements remain intact after rehashing
        self.assertEqual(resizing_map.search("K1"), "V1")
        self.assertEqual(resizing_map.search("K2"), "V2")
        self.assertEqual(resizing_map.search("K3"), "V3")
        self.assertEqual(resizing_map.search("K4"), "V4")

    def test_edge_cases_and_error_handling(self):
        # None key rejected
        with self.assertRaises(ValueError):
            self.map.insert(None, "Val")
        with self.assertRaises(ValueError):
            self.map.search(None)
        with self.assertRaises(ValueError):
            self.map.delete(None)

        # Key not found raises KeyError
        with self.assertRaises(KeyError):
            self.map.search("MISSING_KEY")
        with self.assertRaises(KeyError):
            self.map.delete("MISSING_KEY")
        with self.assertRaises(KeyError):
            _ = self.map["MISSING_KEY"]

        # Invalid capacity or load factor
        with self.assertRaises(ValueError):
            ParkingHashMap(initial_capacity=0)
        with self.assertRaises(ValueError):
            ParkingHashMap(initial_capacity=-5)
        with self.assertRaises(ValueError):
            ParkingHashMap(load_factor_threshold=0)

    def test_iteration_helpers_keys_values_items(self):
        self.map.insert("P1", "Slot1")
        self.map.insert("P2", "Slot2")
        self.map.insert("P3", "Slot3")

        keys = self.map.keys()
        values = self.map.values()
        items = self.map.items()

        self.assertEqual(len(keys), 3)
        self.assertEqual(len(values), 3)
        self.assertEqual(len(items), 3)

        self.assertIn("P1", keys)
        self.assertIn("Slot1", values)
        self.assertIn(("P1", "Slot1"), items)

    def test_display_and_clear(self):
        self.map.insert("DL01", "F1")
        display_str = self.map.display()
        self.assertIn("ParkingHashMap", display_str)
        self.assertIn("DL01", display_str)

        self.map.clear()
        self.assertEqual(self.map.size, 0)
        self.assertTrue(self.map.is_empty())

    def test_with_domain_models(self):
        """Verify ParkingHashMap works seamlessly with Vehicle and ParkingSlot objects."""
        vehicle = Vehicle("DL01AB9999", "Car", owner_name="Dave")
        slot = ParkingSlot("F1-S01", floor=1, slot_type="Car")
        slot.assign_vehicle(vehicle)

        # Map vehicle license plate to ParkingSlot instance
        self.map.insert(vehicle.license_plate, slot)

        retrieved_slot = self.map.search("DL01AB9999")
        self.assertEqual(retrieved_slot, slot)
        self.assertTrue(retrieved_slot.is_occupied)
        self.assertEqual(retrieved_slot.vehicle.owner_name, "Dave")


if __name__ == "__main__":
    unittest.main()
