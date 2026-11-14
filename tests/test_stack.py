"""
Unit tests for Custom ParkingStack.
Covers LIFO behavior, empty stack handling, single-element lifecycle,
top pointer integrity, O(1) push/pop operations, clear, iteration, and internal state retrieval.
"""

import unittest
from data_structures.parking_stack import ParkingStack, StackNode


class TestParkingStack(unittest.TestCase):
    def setUp(self):
        self.stack = ParkingStack()

    def test_initial_state(self):
        """Newly created stack must be empty with top None."""
        self.assertTrue(self.stack.is_empty())
        self.assertEqual(len(self.stack), 0)
        self.assertEqual(self.stack.size, 0)
        self.assertIsNone(self.stack.top)

    def test_empty_stack_errors(self):
        """pop() and peek() must raise IndexError on an empty stack."""
        with self.assertRaises(IndexError):
            self.stack.pop()
        with self.assertRaises(IndexError):
            self.stack.peek()

    def test_push_none_raises_value_error(self):
        """Cannot push None onto the stack."""
        with self.assertRaises(ValueError):
            self.stack.push(None)

    def test_single_element_lifecycle(self):
        """
        When 1 element is pushed, top references the new node.
        When that element is popped, top must reset to None and stack is empty.
        """
        self.stack.push("ACTION_PARK_1")
        self.assertFalse(self.stack.is_empty())
        self.assertEqual(len(self.stack), 1)
        self.assertEqual(self.stack.size, 1)

        self.assertIsNotNone(self.stack.top)
        self.assertEqual(self.stack.top.data, "ACTION_PARK_1")
        self.assertEqual(self.stack.peek(), "ACTION_PARK_1")

        # Pop the only element
        popped = self.stack.pop()
        self.assertEqual(popped, "ACTION_PARK_1")
        self.assertTrue(self.stack.is_empty())
        self.assertEqual(len(self.stack), 0)
        self.assertEqual(self.stack.size, 0)
        self.assertIsNone(self.stack.top, "Top must be None after popping final element")

    def test_lifo_ordering(self):
        """Elements must pop in Last-In, First-Out order."""
        actions = ["CHECKIN_DL01", "ASSIGN_SLOT_01", "PAYMENT_DONE", "CHECKOUT_DL01"]
        for action in actions:
            self.stack.push(action)

        self.assertEqual(len(self.stack), 4)
        self.assertEqual(self.stack.peek(), "CHECKOUT_DL01")

        popped_order = []
        while not self.stack.is_empty():
            popped_order.append(self.stack.pop())

        expected_lifo = list(reversed(actions))
        self.assertEqual(popped_order, expected_lifo)
        self.assertTrue(self.stack.is_empty())
        self.assertIsNone(self.stack.top)

    def test_multiple_push_pop_interleaved(self):
        """Simulate realistic action logging and undo behavior."""
        self.stack.push("ACT_1")
        self.stack.push("ACT_2")
        self.assertEqual(self.stack.pop(), "ACT_2")

        self.stack.push("ACT_3")
        self.stack.push("ACT_4")
        self.assertEqual(self.stack.pop(), "ACT_4")
        self.assertEqual(self.stack.pop(), "ACT_3")
        self.assertEqual(self.stack.pop(), "ACT_1")

        self.assertTrue(self.stack.is_empty())
        self.assertIsNone(self.stack.top)

    def test_clear_operation(self):
        """clear() resets stack to empty state with top None."""
        self.stack.push("OP_1")
        self.stack.push("OP_2")
        self.stack.push("OP_3")
        self.assertEqual(len(self.stack), 3)

        self.stack.clear()
        self.assertTrue(self.stack.is_empty())
        self.assertEqual(len(self.stack), 0)
        self.assertEqual(self.stack.size, 0)
        self.assertIsNone(self.stack.top)

    def test_get_internal_state(self):
        """
        get_internal_state() must traverse actual linked list from top to bottom
        without modifying stack state.
        """
        self.assertEqual(self.stack.get_internal_state(), [])

        self.stack.push("BOTTOM")
        self.stack.push("MIDDLE")
        self.stack.push("TOP")

        state = self.stack.get_internal_state()
        self.assertEqual(state, ["TOP", "MIDDLE", "BOTTOM"])

        # Non-destructive check
        self.assertEqual(len(self.stack), 3)
        self.assertEqual(self.stack.peek(), "TOP")

    def test_display(self):
        """display() returns formatted string representation."""
        self.assertIn("EMPTY", self.stack.display())

        self.stack.push("ITEM_A")
        self.stack.push("ITEM_B")
        disp = self.stack.display()
        self.assertIn("ParkingStack", disp)
        self.assertIn("ITEM_A", disp)
        self.assertIn("ITEM_B", disp)

    def test_iteration(self):
        """__iter__() yields items from top to bottom."""
        items = ["A", "B", "C"]
        for it in items:
            self.stack.push(it)

        iterated = list(self.stack)
        self.assertEqual(iterated, ["C", "B", "A"])
        self.assertEqual(len(self.stack), 3)

    def test_transaction_payloads(self):
        """Verify stack handles structured transaction action payloads."""
        tx1 = {"action": "PARK", "slot_id": "F1-S01", "vehicle": "DL01AB1234"}
        tx2 = {"action": "UNPARK", "slot_id": "F1-S01", "fee": 50.0}

        self.stack.push(tx1)
        self.stack.push(tx2)

        self.assertEqual(self.stack.peek(), tx2)
        popped = self.stack.pop()
        self.assertEqual(popped["action"], "UNPARK")
        self.assertEqual(self.stack.pop()["action"], "PARK")
        self.assertTrue(self.stack.is_empty())


if __name__ == "__main__":
    unittest.main()
