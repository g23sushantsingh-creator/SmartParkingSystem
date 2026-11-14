"""
Custom Hash Map Implementation with Separate Chaining for Smart Parking Management System.

Academic Objective:
Demonstrates a custom hash map built from scratch using a fixed-size array of buckets
and singly-linked list nodes for collision resolution via separate chaining.
Zero usage of Python dictionaries, sets, or collections.

Complexity Documentation:
- Hash Calculation (String):
    O(k) time where k is the string key length | O(1) auxiliary space.
- Search / Get:
    Average O(1) time, Worst O(n) time (assuming bounded key length k = O(1)) | O(1) auxiliary space.
    Average case holds because the load factor alpha = n / m <= threshold (e.g. 0.75), keeping
    expected bucket chain length <= 0.75. Worst case occurs if all n keys hash to the same bucket.
- Insert / Put:
    Amortized O(1) time, Worst O(n) time | O(1) auxiliary space.
    Under the load-factor threshold policy, the capacity doubles when alpha > threshold.
    Although a single insertion triggering resize costs O(n + m) time to rehash existing items,
    capacity doubling occurs geometrically infrequently (only after Omega(m) insertions).
    Distributing the O(n) rehashing work across the sequence of preceding insertions yields
    an amortized O(1) time per insert. Updating an existing key is average O(1) and never triggers resizing.
- Delete / Remove:
    Average O(1) time, Worst O(n) time | O(1) auxiliary space.
- Resize / Rehash:
    O(n + m) time where n = active elements, m = old capacity | O(m_new) auxiliary space.
- Total Space:
    O(n + m) space total (m buckets in array + n linked-list nodes).
"""

from typing import Any, Optional, List, Tuple


class HashNode:
    """
    Singly linked list node used for collision resolution in separate chaining.

    Attributes:
        key (Any): The search key (e.g. vehicle license plate, slot ID).
        value (Any): The payload value associated with the key.
        next (Optional[HashNode]): Reference to the next node in the same bucket chain.
    """

    def __init__(self, key: Any, value: Any, next_node: Optional["HashNode"] = None) -> None:
        self.key = key
        self.value = value
        self.next = next_node

    def __repr__(self) -> str:
        return f"HashNode({repr(self.key)}: {repr(self.value)})"


class ParkingHashMap:
    """
    Custom Hash Map utilizing an array of buckets and separate chaining.

    Attributes:
        capacity (int): Current total number of buckets in the array.
        size (int): Current number of active key-value pairs stored.
        load_factor_threshold (float): Threshold (size / capacity) triggering rehashing.
    """

    DEFAULT_INITIAL_CAPACITY = 11  # Prime number for uniform distribution
    DEFAULT_LOAD_FACTOR = 0.75

    def __init__(self, initial_capacity: int = DEFAULT_INITIAL_CAPACITY, load_factor_threshold: float = DEFAULT_LOAD_FACTOR) -> None:
        if not isinstance(initial_capacity, int) or isinstance(initial_capacity, bool) or initial_capacity <= 0:
            raise ValueError(f"initial_capacity must be a positive integer, got {initial_capacity}.")
        if not isinstance(load_factor_threshold, (int, float)) or load_factor_threshold <= 0:
            raise ValueError(f"load_factor_threshold must be a positive number, got {load_factor_threshold}.")

        self._capacity: int = initial_capacity
        self._load_factor_threshold: float = float(load_factor_threshold)
        self._size: int = 0
        # Initialize bucket array of fixed capacity holding head pointers to linked lists
        self._buckets: List[Optional[HashNode]] = [None] * self._capacity

    # -------------------------------------------------------------------------
    # Hash Function
    # -------------------------------------------------------------------------
    def _hash(self, key: Any) -> int:
        """
        Computes a bucket index for a given key.
        Uses a polynomial rolling hash for string keys (base 31) and falls back
        to Python's built-in hash() for other hashable types.

        Time Complexity:  O(k) where k is the string key length, or O(1) for numbers.
        Space Complexity: O(1) auxiliary space.

        Args:
            key (Any): Key to hash. Must be hashable.

        Returns:
            int: Bucket array index within [0, self._capacity - 1].
        """
        if key is None:
            raise ValueError("Key cannot be None.")

        if isinstance(key, str):
            hash_val = 0
            prime_base = 31
            for char in key:
                hash_val = (hash_val * prime_base + ord(char)) & 0xFFFFFFFF
            return hash_val % self._capacity

        try:
            return abs(hash(key)) % self._capacity
        except TypeError as exc:
            raise TypeError(f"Unhashable key type: {type(key).__name__}") from exc

    # -------------------------------------------------------------------------
    # Properties & Status
    # -------------------------------------------------------------------------
    @property
    def size(self) -> int:
        """Returns the number of key-value pairs stored. Time: O(1)."""
        return self._size

    @property
    def capacity(self) -> int:
        """Returns the total number of buckets available. Time: O(1)."""
        return self._capacity

    @property
    def load_factor(self) -> float:
        """Returns current load factor (size / capacity). Time: O(1)."""
        return self._size / self._capacity

    def is_empty(self) -> bool:
        """Returns True if the map holds zero elements, False otherwise. Time: O(1)."""
        return self._size == 0

    # -------------------------------------------------------------------------
    # Core Operations: Insert / Put
    # -------------------------------------------------------------------------
    def insert(self, key: Any, value: Any) -> None:
        """
        Inserts a key-value pair or updates the existing value if key already exists.
        Checks for an existing key before checking load factor: updating an existing key
        in-place never increments size and never triggers resizing.

        Time Complexity:
            - Key Update:  Average O(1), Worst O(n) assuming bounded key length O(k).
            - New Key:     Amortized O(1), Worst O(n) under load-factor threshold resizing.
        Space Complexity:
            - O(1) auxiliary space (reusing/allocating a single node).

        Args:
            key (Any): The search key.
            value (Any): The payload value.
        """
        if key is None:
            raise ValueError("Key cannot be None.")

        bucket_idx = self._hash(key)
        head = self._buckets[bucket_idx]

        # 1. First inspect bucket chain for existing key (update case)
        # Updating an existing key must never trigger resizing.
        current = head
        while current is not None:
            if current.key == key:
                current.value = value  # In-place update: size unchanged, no resize
                return
            current = current.next

        # 2. Key does not exist: this is a new insertion that increments size.
        # Check if resize is required prior to allocating new entry.
        if (self._size + 1) / self._capacity > self._load_factor_threshold:
            self.resize()
            # After resizing, recompute bucket_idx and head for the new capacity
            bucket_idx = self._hash(key)
            head = self._buckets[bucket_idx]

        # Prepend new node to the bucket chain
        new_node = HashNode(key, value, next_node=head)
        self._buckets[bucket_idx] = new_node
        self._size += 1

    def put(self, key: Any, value: Any) -> None:
        """Alias for insert(key, value)."""
        self.insert(key, value)

    # -------------------------------------------------------------------------
    # Core Operations: Search / Get
    # -------------------------------------------------------------------------
    def search(self, key: Any) -> Any:
        """
        Searches for a key in the hash map and returns its associated value.
        Raises KeyError if the key is not found.

        Time Complexity:
            - Average Case: O(1) time (assuming bounded key length k = O(1))
            - Worst Case:   O(n) time (if all keys hash to the same bucket chain)
        Space Complexity:
            - O(1) auxiliary space

        Args:
            key (Any): The key to locate.

        Returns:
            Any: The value mapped to the key.

        Raises:
            KeyError: If key is not present.
        """
        if key is None:
            raise ValueError("Key cannot be None.")

        bucket_idx = self._hash(key)
        current = self._buckets[bucket_idx]

        while current is not None:
            if current.key == key:
                return current.value
            current = current.next

        raise KeyError(f"Key '{key}' not found in ParkingHashMap.")

    def get(self, key: Any, default: Any = None) -> Any:
        """
        Safely retrieves a value by key. Returns default if not found.

        Time Complexity:  Average O(1), Worst O(n) assuming bounded key length.
        Space Complexity: O(1).
        """
        try:
            return self.search(key)
        except (KeyError, ValueError):
            return default

    def contains(self, key: Any) -> bool:
        """
        Checks whether a key exists in the hash map.

        Time Complexity:  Average O(1), Worst O(n) assuming bounded key length.
        Space Complexity: O(1).
        """
        if key is None:
            return False
        try:
            self.search(key)
            return True
        except KeyError:
            return False

    # -------------------------------------------------------------------------
    # Core Operations: Delete / Remove
    # -------------------------------------------------------------------------
    def delete(self, key: Any) -> Any:
        """
        Deletes the key-value pair from the hash map and returns its value.
        Raises KeyError if the key is not found.

        Time Complexity:
            - Average Case: O(1) time
            - Worst Case:   O(n) time
        Space Complexity:
            - O(1) auxiliary space

        Args:
            key (Any): The key to remove.

        Returns:
            Any: The value of the removed node.

        Raises:
            KeyError: If key is not present.
        """
        if key is None:
            raise ValueError("Key cannot be None.")

        bucket_idx = self._hash(key)
        current = self._buckets[bucket_idx]
        prev: Optional[HashNode] = None

        while current is not None:
            if current.key == key:
                # Key found: unlink current node
                if prev is None:
                    # Target is the head of the chain
                    self._buckets[bucket_idx] = current.next
                else:
                    # Target is inside or at tail of the chain
                    prev.next = current.next

                self._size -= 1
                return current.value

            prev = current
            current = current.next

        raise KeyError(f"Key '{key}' not found for deletion in ParkingHashMap.")

    def remove(self, key: Any) -> Any:
        """Alias for delete(key)."""
        return self.delete(key)

    # -------------------------------------------------------------------------
    # Dynamic Resizing / Rehashing
    # -------------------------------------------------------------------------
    def resize(self, new_capacity: Optional[int] = None) -> None:
        """
        Doubles the bucket array capacity (or resizes to new_capacity) and directly
        rehashes all existing nodes into the new bucket structure without calling
        normal insert() or triggering nested resizing.

        Time Complexity:
            - O(n + m) time, where n = active elements, m = old capacity.
        Space Complexity:
            - O(m_new) auxiliary space for the newly allocated bucket array.

        Args:
            new_capacity (Optional[int]): Target capacity. Defaults to approx. double (2 * old + 1).
        """
        if new_capacity is None:
            target_capacity = (self._capacity * 2) + 1
        else:
            if not isinstance(new_capacity, int) or new_capacity <= self._size:
                raise ValueError(f"new_capacity must be an integer greater than current size ({self._size}).")
            target_capacity = new_capacity

        old_buckets = self._buckets
        self._capacity = target_capacity
        self._buckets = [None] * self._capacity
        # Note: self._size remains strictly unchanged because all existing nodes are migrated directly.

        # Rehash every node from the old bucket chains directly into the new bucket array
        for head in old_buckets:
            current = head
            while current is not None:
                next_node = current.next
                # Compute new bucket index under new capacity
                new_idx = self._hash(current.key)
                # Re-link existing node directly at the head of the new bucket chain
                current.next = self._buckets[new_idx]
                self._buckets[new_idx] = current
                current = next_node

    # -------------------------------------------------------------------------
    # Traversal, Inspection, and Streamlit Visualizer Support
    # -------------------------------------------------------------------------
    def display(self) -> str:
        """
        Generates a human-readable visual display of all buckets and linked list chains.
        Crucial for DSA viva demonstrations and debugging.

        Time Complexity:  O(n + m)
        Space Complexity: O(n + m) string output
        """
        lines: List[str] = [
            f"--- ParkingHashMap (Size: {self._size}, Capacity: {self._capacity}, Load: {self.load_factor:.2f}) ---"
        ]
        for idx in range(self._capacity):
            chain_nodes: List[str] = []
            curr = self._buckets[idx]
            while curr is not None:
                chain_nodes.append(f"[{curr.key} -> {curr.value}]")
                curr = curr.next

            chain_str = " -> ".join(chain_nodes) if chain_nodes else "EMPTY"
            lines.append(f"Bucket {idx:02d}: {chain_str}")

        result = "\n".join(lines)
        return result

    def get_internal_state(self) -> List[List[Tuple[Any, Any]]]:
        """
        Returns a structured snapshot of the internal bucket chains without
        using Python dicts. Directly consumed by the Streamlit DSA Visualizer UI.

        Structure:
            [
               [(key1, val1), (key2, val2)],  # Bucket 0 chain
               [],                            # Bucket 1 empty
               [(key3, val3)]                 # Bucket 2 chain
            ]

        Time Complexity:  O(n + m)
        Space Complexity: O(n)
        """
        state: List[List[Tuple[Any, Any]]] = []
        for head in self._buckets:
            chain: List[Tuple[Any, Any]] = []
            curr = head
            while curr is not None:
                chain.append((curr.key, curr.value))
                curr = curr.next
            state.append(chain)
        return state

    def keys(self) -> List[Any]:
        """Returns a list of all stored keys. Time: O(n + m)."""
        key_list: List[Any] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                key_list.append(curr.key)
                curr = curr.next
        return key_list

    def values(self) -> List[Any]:
        """Returns a list of all stored values. Time: O(n + m)."""
        val_list: List[Any] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                val_list.append(curr.value)
                curr = curr.next
        return val_list

    def items(self) -> List[Tuple[Any, Any]]:
        """Returns a list of all (key, value) pairs. Time: O(n + m)."""
        item_list: List[Tuple[Any, Any]] = []
        for head in self._buckets:
            curr = head
            while curr is not None:
                item_list.append((curr.key, curr.value))
                curr = curr.next
        return item_list

    def clear(self) -> None:
        """Resets the hash map to empty state with default capacity. Time: O(m)."""
        self._capacity = self.DEFAULT_INITIAL_CAPACITY
        self._buckets = [None] * self._capacity
        self._size = 0

    # -------------------------------------------------------------------------
    # Python Special Methods (Operator Overloading for Map Semantics)
    # -------------------------------------------------------------------------
    def __len__(self) -> int:
        return self._size

    def __getitem__(self, key: Any) -> Any:
        return self.search(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        self.insert(key, value)

    def __delitem__(self, key: Any) -> None:
        self.delete(key)

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def __repr__(self) -> str:
        return f"<ParkingHashMap size={self._size} capacity={self._capacity} load={self.load_factor:.2f}>"
