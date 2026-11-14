"""
Unit tests for Custom BookingQueue.
Covers FIFO behavior, empty queue handling, single-element edge case,
front/rear pointer integrity, O(1) operations, and internal state retrieval.
"""

import unittest
from data_structures.booking_queue import BookingQueue, QueueNode
from models.vehicle import Vehicle


class TestBookingQueue(unittest.TestCase):
    def setUp(self):
        self.queue = BookingQueue()

    def test_initial_state(self):
        """Newly created queue must be empty with None pointers."""
        self.assertTrue(self.queue.is_empty())
        self.assertEqual(len(self.queue), 0)
        self.assertEqual(self.queue.size, 0)
        self.assertIsNone(self.queue.front)
        self.assertIsNone(self.queue.rear)

    def test_empty_queue_errors(self):
        """dequeue() and peek() must raise IndexError on an empty queue."""
        with self.assertRaises(IndexError):
            self.queue.dequeue()
        with self.assertRaises(IndexError):
            self.queue.peek()

    def test_enqueue_none_raises_value_error(self):
        """Cannot enqueue None."""
        with self.assertRaises(ValueError):
            self.queue.enqueue(None)

    def test_single_element_case(self):
        """
        When 1 element is added, front and rear point to the same node.
        When that element is dequeued, both front and rear must become None.
        """
        self.queue.enqueue("VEHICLE_1")
        self.assertFalse(self.queue.is_empty())
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(self.queue.size, 1)

        # Front and rear must reference the exact same node
        self.assertIsNotNone(self.queue.front)
        self.assertIsNotNone(self.queue.rear)
        self.assertIs(self.queue.front, self.queue.rear)
        self.assertEqual(self.queue.peek(), "VEHICLE_1")

        # Dequeue the only element
        removed = self.queue.dequeue()
        self.assertEqual(removed, "VEHICLE_1")
        self.assertTrue(self.queue.is_empty())
        self.assertEqual(len(self.queue), 0)
        self.assertEqual(self.queue.size, 0)

        # Crucial check: both front and rear must be None
        self.assertIsNone(self.queue.front)
        self.assertIsNone(self.queue.rear)

    def test_fifo_ordering(self):
        """Elements must dequeue in exact arrival order (First-In, First-Out)."""
        items = ["FIRST", "SECOND", "THIRD", "FOURTH"]
        for item in items:
            self.queue.enqueue(item)

        self.assertEqual(len(self.queue), 4)
        self.assertEqual(self.queue.peek(), "FIRST")

        dequeued_items = []
        while not self.queue.is_empty():
            dequeued_items.append(self.queue.dequeue())

        self.assertEqual(dequeued_items, items)
        self.assertTrue(self.queue.is_empty())
        self.assertIsNone(self.queue.front)
        self.assertIsNone(self.queue.rear)

    def test_multiple_enqueue_dequeue_cycles(self):
        """Simulate realistic traffic: interleaving enqueues and dequeues."""
        self.queue.enqueue("V1")
        self.queue.enqueue("V2")
        self.assertEqual(self.queue.dequeue(), "V1")

        self.queue.enqueue("V3")
        self.assertEqual(self.queue.dequeue(), "V2")

        self.queue.enqueue("V4")
        self.assertEqual(self.queue.dequeue(), "V3")
        self.assertEqual(self.queue.dequeue(), "V4")

        self.assertTrue(self.queue.is_empty())
        self.assertIsNone(self.queue.front)
        self.assertIsNone(self.queue.rear)

    def test_get_internal_state(self):
        """get_internal_state() returns an ordered snapshot without modifying queue."""
        self.assertEqual(self.queue.get_internal_state(), [])

        self.queue.enqueue("A")
        self.queue.enqueue("B")
        self.queue.enqueue("C")

        state = self.queue.get_internal_state()
        self.assertEqual(state, ["A", "B", "C"])
        # Ensure state extraction is non-destructive
        self.assertEqual(len(self.queue), 3)
        self.assertEqual(self.queue.peek(), "A")

    def test_display(self):
        """display() returns informative string for debugging and UI."""
        self.assertIn("EMPTY", self.queue.display())

        self.queue.enqueue("CAR_1")
        self.queue.enqueue("CAR_2")
        disp = self.queue.display()
        self.assertIn("BookingQueue", disp)
        self.assertIn("CAR_1", disp)
        self.assertIn("CAR_2", disp)

    def test_with_vehicle_model(self):
        """Verify BookingQueue works cleanly with Vehicle domain objects."""
        v1 = Vehicle("DL01AA1111", "Car", owner_name="Alice")
        v2 = Vehicle("MH12BB2222", "Bike", owner_name="Bob")

        self.queue.enqueue(v1)
        self.queue.enqueue(v2)

        self.assertEqual(self.queue.peek(), v1)
        self.assertEqual(self.queue.dequeue(), v1)
        self.assertEqual(self.queue.dequeue(), v2)
        self.assertTrue(self.queue.is_empty())

    def test_iteration(self):
        """Queue supports iteration from front to rear."""
        values = [10, 20, 30]
        for v in values:
            self.queue.enqueue(v)

        iterated = list(self.queue)
        self.assertEqual(iterated, values)
        self.assertEqual(len(self.queue), 3)


if __name__ == "__main__":
    unittest.main()
