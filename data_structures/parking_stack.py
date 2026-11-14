"""
Custom Parking Stack Implementation using Singly Linked List for Smart Parking Management System.

Academic Objective:
Demonstrates a custom LIFO (Last-In, First-Out) Stack implemented from scratch
using singly-linked list nodes with an explicit top pointer.
Used for audit trails, recent vehicle operations logging, and undo operations.
Zero usage of Python list, collections.deque, or queue modules for the stack structure.

Complexity Documentation:
- push(data):          O(1) time | O(1) auxiliary space (head prepend)
- pop():               O(1) time | O(1) auxiliary space (head removal)
- peek():              O(1) time | O(1) auxiliary space
- is_empty():          O(1) time | O(1) auxiliary space
- clear():             O(1) time | O(1) auxiliary space
- __len__():           O(1) time | O(1) auxiliary space
- display():           O(n) time | O(n) space
- get_internal_state():O(n) time | O(n) space
- Total Space:         O(n) space for n active stack nodes
"""

from typing import Any, Optional, List


class StackNode:
    """
    Singly linked list node for the custom ParkingStack.

    Attributes:
        data (Any): Payload stored in the node (e.g. action record, vehicle audit log).
        next (Optional[StackNode]): Pointer to the node immediately below in the stack.
    """

    def __init__(self, data: Any, next_node: Optional["StackNode"] = None) -> None:
        self.data = data
        self.next = next_node

    def __repr__(self) -> str:
        return f"StackNode({repr(self.data)})"


class ParkingStack:
    """
    Custom LIFO Stack maintaining a top pointer for O(1) push and pop operations.
    Used to track recent parking/unparking transactions, audit history, and undo operations.

    Attributes:
        top (Optional[StackNode]): Pointer to the topmost node of the stack.
        size (int): Current number of items stored in the stack.
    """

    def __init__(self) -> None:
        self._top: Optional[StackNode] = None
        self._size: int = 0

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    @property
    def top(self) -> Optional[StackNode]:
        """Returns the topmost node of the stack."""
        return self._top

    @property
    def size(self) -> int:
        """Returns the total number of items stored. Time: O(1)."""
        return self._size

    def is_empty(self) -> bool:
        """
        Checks whether the stack is empty.

        Time Complexity:  O(1)
        Space Complexity: O(1)
        """
        return self._size == 0

    # -------------------------------------------------------------------------
    # Core Operations: Push, Pop, Peek
    # -------------------------------------------------------------------------
    def push(self, data: Any) -> None:
        """
        Pushes a new element onto the top of the stack.

        Time Complexity:  O(1) - prepends a node to the head of the linked list.
        Space Complexity: O(1) auxiliary space for allocating the new node.

        Args:
            data (Any): The payload to push.

        Raises:
            ValueError: If data is None.
        """
        if data is None:
            raise ValueError("Cannot push None onto ParkingStack.")

        new_node = StackNode(data, next_node=self._top)
        self._top = new_node
        self._size += 1

    def pop(self) -> Any:
        """
        Removes and returns the topmost element of the stack (LIFO).
        Popping the final remaining element resets top to None.

        Time Complexity:  O(1) - unlinks the head node.
        Space Complexity: O(1) auxiliary space.

        Returns:
            Any: The payload data of the removed top node.

        Raises:
            IndexError: If attempted on an empty stack.
        """
        if self.is_empty():
            raise IndexError("Cannot pop from an empty ParkingStack.")

        popped_data = self._top.data
        self._top = self._top.next
        self._size -= 1
        return popped_data

    def peek(self) -> Any:
        """
        Returns the data at the top of the stack without removing it.

        Time Complexity:  O(1)
        Space Complexity: O(1)

        Returns:
            Any: The payload data of the top node.

        Raises:
            IndexError: If attempted on an empty stack.
        """
        if self.is_empty():
            raise IndexError("Cannot peek into an empty ParkingStack.")

        return self._top.data

    def clear(self) -> None:
        """
        Resets the stack to an empty state.

        Time Complexity:  O(1)
        Space Complexity: O(1)
        """
        self._top = None
        self._size = 0

    # -------------------------------------------------------------------------
    # Display, Inspection, and Streamlit Visualizer Support
    # -------------------------------------------------------------------------
    def display(self) -> str:
        """
        Returns a formatted string visualization of the stack from top to bottom.

        Time Complexity:  O(n)
        Space Complexity: O(n)
        """
        if self.is_empty():
            return "ParkingStack: EMPTY (Size: 0)"

        nodes: List[str] = []
        curr = self._top
        while curr is not None:
            nodes.append(f"[{curr.data}]")
            curr = curr.next

        return f"ParkingStack (Top -> Bottom, Size: {self._size}): " + " -> ".join(nodes)

    def get_internal_state(self) -> List[Any]:
        """
        Traverses the actual linked-list nodes from top to bottom and returns
        their payload values as a list.
        Directly consumed by the Streamlit DSA Visualizer UI to render the transaction stack.

        Time Complexity:  O(n)
        Space Complexity: O(n)
        """
        state: List[Any] = []
        curr = self._top
        while curr is not None:
            state.append(curr.data)
            curr = curr.next
        return state

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __len__(self) -> int:
        """Returns current stack size. Time: O(1)."""
        return self._size

    def __iter__(self):
        """Allows iteration from top to bottom without modifying the stack."""
        curr = self._top
        while curr is not None:
            yield curr.data
            curr = curr.next

    def __repr__(self) -> str:
        top_val = repr(self._top.data) if self._top else "None"
        return f"<ParkingStack size={self._size} top={top_val}>"
