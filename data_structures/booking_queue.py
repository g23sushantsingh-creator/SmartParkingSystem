"""
Custom Booking Queue Implementation using Singly Linked List for Smart Parking Management System.

Academic Objective:
Demonstrates a custom FIFO (First-In, First-Out) Queue implemented from scratch
using singly-linked list nodes with explicit front and rear pointers.
Zero usage of Python collections.deque, queue.Queue, or built-in list operations.

Complexity Documentation:
- enqueue(data):       O(1) time | O(1) auxiliary space (tail pointer update)
- dequeue():           O(1) time | O(1) auxiliary space (head pointer update)
- peek():              O(1) time | O(1) auxiliary space
- is_empty():          O(1) time | O(1) auxiliary space
- __len__():           O(1) time | O(1) auxiliary space
- display():           O(n) time | O(n) space
- get_internal_state():O(n) time | O(n) space
- Total Space:         O(n) space for n active queue nodes
"""

from typing import Any, Optional, List


class QueueNode:
    """
    Singly linked list node for the custom BookingQueue.

    Attributes:
        data (Any): Payload stored in the node (e.g. Vehicle instance or booking request).
        next (Optional[QueueNode]): Pointer to the next node in the queue.
    """

    def __init__(self, data: Any, next_node: Optional["QueueNode"] = None) -> None:
        self.data = data
        self.next = next_node

    def __repr__(self) -> str:
        return f"QueueNode({repr(self.data)})"


class BookingQueue:
    """
    Custom FIFO Queue maintaining front and rear pointers for O(1) operations.
    Used to manage waitlisted vehicles when parking slots are fully occupied.

    Attributes:
        front (Optional[QueueNode]): Node at the front of the queue (next to be dequeued).
        rear (Optional[QueueNode]): Node at the rear of the queue (most recently enqueued).
        size (int): Total number of elements currently stored.
    """

    def __init__(self) -> None:
        self._front: Optional[QueueNode] = None
        self._rear: Optional[QueueNode] = None
        self._size: int = 0

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    @property
    def front(self) -> Optional[QueueNode]:
        """Returns the front node of the queue."""
        return self._front

    @property
    def rear(self) -> Optional[QueueNode]:
        """Returns the rear node of the queue."""
        return self._rear

    @property
    def size(self) -> int:
        """Returns the total number of items in the queue. Time: O(1)."""
        return self._size

    def is_empty(self) -> bool:
        """
        Checks whether the queue is empty.

        Time Complexity:  O(1)
        Space Complexity: O(1)
        """
        return self._size == 0

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------
    def enqueue(self, data: Any) -> None:
        """
        Appends a new element to the rear of the queue.

        Time Complexity:  O(1) - direct insertion using the rear pointer.
        Space Complexity: O(1) auxiliary space for allocating the new node.

        Args:
            data (Any): The payload to enqueue.

        Raises:
            ValueError: If data is None.
        """
        if data is None:
            raise ValueError("Cannot enqueue None into BookingQueue.")

        new_node = QueueNode(data)

        if self.is_empty():
            # When empty, both front and rear reference the new node
            self._front = new_node
            self._rear = new_node
        else:
            # Attach to rear and update rear pointer
            self._rear.next = new_node
            self._rear = new_node

        self._size += 1

    def dequeue(self) -> Any:
        """
        Removes and returns the element at the front of the queue (FIFO).
        Correctly resets both front and rear to None when the final element is removed.

        Time Complexity:  O(1) - direct removal using the front pointer.
        Space Complexity: O(1) auxiliary space.

        Returns:
            Any: The payload data of the dequeued node.

        Raises:
            IndexError: If attempted on an empty queue.
        """
        if self.is_empty():
            raise IndexError("Cannot dequeue from an empty BookingQueue.")

        removed_data = self._front.data
        self._front = self._front.next
        self._size -= 1

        # Single-element case: if queue becomes empty, reset rear to None
        if self._front is None:
            self._rear = None

        return removed_data

    def peek(self) -> Any:
        """
        Inspects the element at the front of the queue without removing it.

        Time Complexity:  O(1)
        Space Complexity: O(1)

        Returns:
            Any: The payload data at the front of the queue.

        Raises:
            IndexError: If attempted on an empty queue.
        """
        if self.is_empty():
            raise IndexError("Cannot peek into an empty BookingQueue.")

        return self._front.data

    # -------------------------------------------------------------------------
    # Inspection, Display, and Streamlit Visualizer Support
    # -------------------------------------------------------------------------
    def display(self) -> str:
        """
        Returns a formatted string visualization of the queue from front to rear.

        Time Complexity:  O(n)
        Space Complexity: O(n)
        """
        if self.is_empty():
            return "BookingQueue: EMPTY (Size: 0)"

        nodes: List[str] = []
        curr = self._front
        while curr is not None:
            nodes.append(f"[{curr.data}]")
            curr = curr.next

        return f"BookingQueue (Front -> Rear, Size: {self._size}): " + " -> ".join(nodes)

    def get_internal_state(self) -> List[Any]:
        """
        Returns an ordered list of all payload elements from front to rear.
        Directly consumed by the Streamlit DSA Visualizer UI to render the waitlist.

        Time Complexity:  O(n)
        Space Complexity: O(n)
        """
        state: List[Any] = []
        curr = self._front
        while curr is not None:
            state.append(curr.data)
            curr = curr.next
        return state

    def clear(self) -> None:
        """Resets the queue to an empty state. Time: O(1)."""
        self._front = None
        self._rear = None
        self._size = 0

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __len__(self) -> int:
        """Returns current queue length. Time: O(1)."""
        return self._size

    def __iter__(self):
        """Allows iteration from front to rear without modifying queue state."""
        curr = self._front
        while curr is not None:
            yield curr.data
            curr = curr.next

    def __repr__(self) -> str:
        front_val = repr(self._front.data) if self._front else "None"
        rear_val = repr(self._rear.data) if self._rear else "None"
        return f"<BookingQueue size={self._size} front={front_val} rear={rear_val}>"
