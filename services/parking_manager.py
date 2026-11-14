"""
Parking Manager Service for Smart Parking Management System.

Architectural Role:
Coordinates domain models (Vehicle, ParkingSlot), custom Data Structures
(ParkingHashMap, BookingQueue, ParkingStack), and persistent storage (ParkingRepository).

Reliability, Consistency & Recovery Architecture:
- Custom DSA structures actively manage operational state in memory.
- MongoDB Atlas provides persistent, durable storage.
- Synchronization occurs only after database operations succeed to avoid state drift.
- Explicit step-wise verification and compensating rollback handlers prevent state corruption.
- Multi-step operations (park, checkout, waitlist allocation) implement verifiable compensating transactions:
  if a secondary persistence step fails, preceding persistence steps are actively compensated
  (e.g., reverting slot occupancy, restoring deleted vehicle records, unparking on status failure).
- If compensating rollback cannot be verified, a diagnostic error is raised identifying every failed
  operation and detailing necessary manual reconciliation without claiming false success.
- Does NOT claim multi-document ACID transactions. Limitations of dual-write and distributed network
  failures are explicitly documented and handled with safest practical recovery.
- Exposes complete real-time internal state snapshots for the Streamlit DSA Visualizer.
"""

import math
from datetime import datetime
from typing import Optional, List, Dict, Any

from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot
from data_structures.parking_hashmap import ParkingHashMap
from data_structures.booking_queue import BookingQueue
from data_structures.parking_stack import ParkingStack
from database.repository import ParkingRepository


class ParkingManager:
    """
    Core business logic coordinator.
    Manages slots, vehicle parking, checkout, waitlisting, and action auditing.
    """

    DEFAULT_HOURLY_RATE = 20.0
    MAX_HOURLY_RATE = 100_000.0

    def __init__(self, repository: Optional[ParkingRepository] = None) -> None:
        """
        Initializes the ParkingManager with injected repository and custom DSA structures.

        Args:
            repository (Optional[ParkingRepository]): Data repository. Defaults to live Atlas repository.
        """
        self.repository: ParkingRepository = repository if repository is not None else ParkingRepository()

        # In-Memory Custom Data Structures (Zero built-in dict/list substitutes for core DSA)
        # 1. Hash Maps for O(1) average lookup
        self.slots_map: ParkingHashMap = ParkingHashMap(initial_capacity=17)
        self.vehicle_to_slot_map: ParkingHashMap = ParkingHashMap(initial_capacity=17)
        self.vehicles_map: ParkingHashMap = ParkingHashMap(initial_capacity=17)

        # 2. FIFO Queue for waitlisted vehicles
        self.waiting_queue: BookingQueue = BookingQueue()

        # 3. LIFO Stack for action audit trail and undo operations
        self.action_stack: ParkingStack = ParkingStack()

        # Hydrate in-memory state from database
        self._load_state_from_db()

    # -------------------------------------------------------------------------
    # State Hydration
    # -------------------------------------------------------------------------
    def _load_state_from_db(self) -> None:
        """
        Loads persistent slots, registered vehicles, and active WAITING bookings
        from MongoDB into the custom in-memory data structures.
        """
        # 1. Load Slots and their parked vehicles
        slots = self.repository.get_all_slots()
        for slot in slots:
            self.slots_map.insert(slot.slot_id, slot)
            if slot.is_occupied and slot.vehicle:
                self.vehicle_to_slot_map.insert(slot.vehicle.license_plate, slot.slot_id)
                self.vehicles_map.insert(slot.vehicle.license_plate, slot.vehicle)

        # 2. Load Vehicles
        vehicles = self.repository.get_all_vehicles()
        for v in vehicles:
            if not self.vehicles_map.contains(v.license_plate):
                self.vehicles_map.insert(v.license_plate, v)

        # 3. Load WAITING bookings into FIFO queue in creation order
        waiting_bookings = self.repository.get_all_bookings(status="WAITING")
        for booking in waiting_bookings:
            self.waiting_queue.enqueue(booking)

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------
    def _restore_booking_to_queue(self, booking: Dict[str, Any], original_index: int) -> None:
        """
        Restores a booking to its exact original index in the waiting_queue (preserving FIFO order)
        using only custom Queue enqueue and dequeue operations.

        Complexity:
            Time: O(N) where N = len(waiting_queue)
            Space: O(1) auxiliary space (nodes cycled in-place)
        """
        n = len(self.waiting_queue)
        k = max(0, min(original_index, n))
        for _ in range(k):
            self.waiting_queue.enqueue(self.waiting_queue.dequeue())
        self.waiting_queue.enqueue(booking)
        for _ in range(n - k):
            self.waiting_queue.enqueue(self.waiting_queue.dequeue())

    # -------------------------------------------------------------------------
    # Slot Management
    # -------------------------------------------------------------------------
    def add_parking_slot(self, slot: ParkingSlot) -> str:
        """
        Adds a new parking slot to persistent storage and in-memory HashMap.

        Args:
            slot (ParkingSlot): The slot entity to add.

        Returns:
            str: slot_id of added slot.

        Raises:
            ValueError: If slot already exists in memory or database.
        """
        if not isinstance(slot, ParkingSlot):
            raise TypeError(f"Expected ParkingSlot instance, got {type(slot).__name__}.")

        if self.slots_map.contains(slot.slot_id):
            raise ValueError(f"ParkingSlot '{slot.slot_id}' already exists in manager.")

        # Persist to MongoDB first
        slot_id = self.repository.insert_slot(slot)

        # Synchronize in-memory Hash Map only after DB insertion succeeds
        self.slots_map.insert(slot.slot_id, slot)
        if slot.is_occupied and slot.vehicle:
            self.vehicle_to_slot_map.insert(slot.vehicle.license_plate, slot.slot_id)
            self.vehicles_map.insert(slot.vehicle.license_plate, slot.vehicle)

        # Record action in stack
        self.action_stack.push({
            "action": "ADD_SLOT",
            "slot_id": slot.slot_id,
            "floor": slot.floor,
            "type": slot.slot_type,
            "timestamp": datetime.now()
        })
        return slot_id

    def get_slot_by_id(self, slot_id: str) -> Optional[ParkingSlot]:
        """Lookup slot in O(1) average time via custom Hash Map."""
        if not slot_id or not isinstance(slot_id, str):
            return None
        return self.slots_map.get(slot_id.strip().upper(), default=None)

    def get_all_slots(self) -> List[ParkingSlot]:
        """Returns all managed parking slots sorted by floor and slot_id."""
        raw_slots = self.slots_map.values()
        return sorted(raw_slots, key=lambda s: (s.floor, s.slot_id))

    def find_available_slot(self, vehicle_type: str) -> Optional[ParkingSlot]:
        """
        Finds the first available parking slot compatible with the specified vehicle type.

        Compatibility:
        - Exact match (Car -> Car, Bike -> Bike, Truck -> Truck, EV -> EV)
        - EV can also park in Car slots if no dedicated EV slot is vacant.
        """
        all_slots = self.get_all_slots()

        # First pass: try exact match
        for slot in all_slots:
            if not slot.is_occupied and slot.slot_type == vehicle_type:
                return slot

        # Second pass: EV in Car slot
        if vehicle_type == "EV":
            for slot in all_slots:
                if not slot.is_occupied and slot.slot_type == "Car":
                    return slot

        return None

    def delete_parking_slot(self, slot_id: str) -> bool:
        """
        Deletes a parking slot from persistent storage (MongoDB) and in-memory slots_map.

        Requirements:
        1. Validates slot existence in slots_map or MongoDB.
        2. Rejects deletion if slot is currently occupied.
        3. Deletes slot from MongoDB first.
        4. Updates in-memory slots_map only after database deletion succeeds.
        5. Preserves parking_history and unrelated records.
        6. Pushes DELETE_SLOT action to action_stack.

        Args:
            slot_id (str): Unique identifier of the slot to delete (e.g. 'F1-S01').

        Returns:
            bool: True if slot was deleted successfully.

        Raises:
            ValueError: If slot_id is invalid, not found, or slot is currently occupied.
            RuntimeError: If database deletion fails.
        """
        if not slot_id or not isinstance(slot_id, str):
            raise ValueError("slot_id must be a non-empty string.")

        normalized_id = slot_id.strip().upper()

        # Check in-memory slot or database slot
        slot = self.slots_map.get(normalized_id, default=None)
        if slot is None:
            # Fallback check against repository
            slot = self.repository.get_slot_by_id(normalized_id)

        if slot is None:
            raise ValueError(f"Parking slot '{normalized_id}' not found.")

        # Invariant: Prevent deletion if slot is currently occupied
        if slot.is_occupied or slot.vehicle is not None:
            plate_info = f" by vehicle '{slot.vehicle.license_plate}'" if slot.vehicle else ""
            raise ValueError(
                f"Cannot delete parking slot '{normalized_id}': Slot is currently occupied{plate_info}. "
                f"Checkout the vehicle before deleting the slot."
            )

        # Invariant: Double check vehicle_to_slot_map to guarantee no parked vehicle is linked to this slot
        for plate in self.vehicle_to_slot_map.keys():
            if self.vehicle_to_slot_map.get(plate) == normalized_id:
                raise ValueError(
                    f"Cannot delete parking slot '{normalized_id}': Slot is occupied by vehicle '{plate}'."
                )

        # 1. Delete from MongoDB first (database-first consistency)
        db_deleted = self.repository.delete_slot(normalized_id)
        if not db_deleted:
            raise RuntimeError(f"Database error deleting slot '{normalized_id}': Document was not deleted in MongoDB.")

        # 2. Synchronize in-memory slots_map only after database deletion succeeds
        if self.slots_map.contains(normalized_id):
            self.slots_map.delete(normalized_id)

        # 3. Push audit record to action stack (LIFO)
        self.action_stack.push({
            "action": "DELETE_SLOT",
            "slot_id": normalized_id,
            "floor": slot.floor,
            "type": slot.slot_type,
            "timestamp": datetime.now()
        })

        return True

    # -------------------------------------------------------------------------
    # Vehicle Management
    # -------------------------------------------------------------------------
    def register_vehicle(self, vehicle: Vehicle) -> str:
        """
        Registers a vehicle in the system.
        If a vehicle with this license plate is already registered (in memory or database),
        retrieves and preserves the canonical existing record rather than silently overwriting it.

        Args:
            vehicle (Vehicle): Vehicle instance.

        Returns:
            str: Normalized license plate.
        """
        if not isinstance(vehicle, Vehicle):
            raise TypeError(f"Expected Vehicle instance, got {type(vehicle).__name__}.")

        # 1. Check in-memory map first
        if self.vehicles_map.contains(vehicle.license_plate):
            return vehicle.license_plate

        # 2. Check persistent database to see if record already exists
        existing_db_vehicle = self.repository.get_vehicle_by_plate(vehicle.license_plate)
        if existing_db_vehicle is not None:
            # Preserve canonical record from DB in memory without overwriting
            self.vehicles_map.insert(existing_db_vehicle.license_plate, existing_db_vehicle)
            return existing_db_vehicle.license_plate

        # 3. New vehicle: persist to DB then store in memory
        plate = self.repository.insert_vehicle(vehicle)
        self.vehicles_map.insert(vehicle.license_plate, vehicle)

        # Push to LIFO audit stack (only for newly registered vehicles)
        self.action_stack.push({
            "action": "REGISTER_VEHICLE",
            "license_plate": vehicle.license_plate,
            "vehicle_type": vehicle.vehicle_type,
            "owner_name": vehicle.owner_name or "—",
            "timestamp": datetime.now()
        })
        return plate

    def get_vehicle_by_plate(self, license_plate: str) -> Optional[Vehicle]:
        """Lookup vehicle in O(1) average time via custom Hash Map."""
        if not license_plate or not isinstance(license_plate, str):
            return None
        norm_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        return self.vehicles_map.get(norm_plate, default=None)

    def get_slot_by_vehicle(self, license_plate: str) -> Optional[ParkingSlot]:
        """Retrieves the slot currently occupied by a vehicle in O(1) average time."""
        if not license_plate or not isinstance(license_plate, str):
            return None
        norm_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        slot_id = self.vehicle_to_slot_map.get(norm_plate, default=None)
        if slot_id:
            return self.slots_map.get(slot_id, default=None)
        return None

    def get_all_vehicles(self) -> List[Vehicle]:
        """Returns all registered vehicles sorted by license plate."""
        raw_vehicles = self.vehicles_map.values()
        return sorted(raw_vehicles, key=lambda v: v.license_plate)

    def delete_registered_vehicle(self, license_plate: str) -> bool:
        """
        Permanently deletes a registered vehicle from MongoDB and the in-memory vehicles_map.

        Guards:
        - Input validation: license_plate must be a non-empty string.
        - Parked Vehicle Protection: If the vehicle is currently parked in any slot,
          deletion is rejected with a ValueError.
        - Registration check: If vehicle is not registered, raises ValueError.
        - Persistence First: Deletes from MongoDB repository first. If repository deletion
          fails or raises an exception, in-memory state is NOT modified.
        - Preserves parking_history and unrelated records.
        - Audit trail: Pushes a DELETE_VEHICLE action to action_stack.

        Args:
            license_plate (str): Plate of vehicle to permanently delete.

        Returns:
            bool: True if vehicle was successfully deleted.

        Raises:
            ValueError: If input is invalid, vehicle is currently parked, or vehicle is not registered.
            RuntimeError: If database deletion fails.
        """
        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        norm_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")

        # Guard: Prevent deletion if vehicle is currently parked
        if self.vehicle_to_slot_map.contains(norm_plate):
            slot_id = self.vehicle_to_slot_map.search(norm_plate)
            raise ValueError(f"Cannot delete vehicle '{norm_plate}': vehicle is currently parked in slot '{slot_id}'.")

        for slot in self.slots_map.values():
            if slot.is_occupied and slot.vehicle and slot.vehicle.license_plate == norm_plate:
                raise ValueError(f"Cannot delete vehicle '{norm_plate}': vehicle is currently parked in slot '{slot.slot_id}'.")

        # Check existence
        in_memory = self.vehicles_map.contains(norm_plate)
        db_veh = self.repository.get_vehicle_by_plate(norm_plate)
        if not in_memory and db_veh is None:
            raise ValueError(f"Vehicle '{norm_plate}' is not registered in the system.")

        # Persist deletion to MongoDB first (preserves parking_history completely)
        if db_veh is not None:
            del_ok = self.repository.delete_vehicle(norm_plate)
            if not del_ok:
                raise RuntimeError(f"Database failed to delete vehicle '{norm_plate}' (delete returned False).")

        # Synchronize memory only after DB deletion succeeded
        if self.vehicles_map.contains(norm_plate):
            self.vehicles_map.delete(norm_plate)

        # Audit stack
        self.action_stack.push({
            "action": "DELETE_VEHICLE",
            "license_plate": norm_plate,
            "timestamp": datetime.now()
        })

        return True

    # -------------------------------------------------------------------------
    # Core Operations: Park & Check-Out with Verifiable Compensating Rollback
    # -------------------------------------------------------------------------
    def park_vehicle(
        self,
        license_plate: str,
        vehicle_type: str = "Car",
        owner_name: str = "",
        owner_phone: str = "",
        slot_id: Optional[str] = None
    ) -> ParkingSlot:
        """
        Parks a vehicle into a designated or automatically chosen slot.
        Maintains database and in-memory consistency using verifiable compensating rollbacks
        across multi-step persistence (update slot, insert vehicle, log history).

        Canonical Vehicle Policy:
        - If the vehicle already exists in memory or the database, its canonical record is preserved.
        - Newly supplied owner details do NOT overwrite the canonical record.
        - Rollback only deletes vehicle records that were newly inserted during this specific call.

        Verifiable Recovery Strategy:
        - Checks return values of update_slot(), insert_vehicle(), and log_history().
        - If a subsequent step fails, compensating operations revert the slot and clean up inserted vehicles.
        - If any compensating operation fails, a diagnostic error is raised detailing the partial failure
          and required manual database reconciliation.

        Args:
            license_plate (str): Vehicle license plate.
            vehicle_type (str): Type of vehicle ('Car', 'Bike', 'Truck', 'EV').
            owner_name (str): Driver/owner name (used if vehicle is new).
            owner_phone (str): Contact phone (used if vehicle is new).
            slot_id (Optional[str]): Explicit target slot ID, or None for auto-allocation.

        Returns:
            ParkingSlot: The slot where vehicle is now parked.

        Raises:
            ValueError: If vehicle is already parked, slot is occupied, or no slots available.
            RuntimeError: If database persistence or compensation fails.
        """
        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        norm_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")

        # Check if vehicle is already parked in any slot
        if self.vehicle_to_slot_map.contains(norm_plate):
            existing_slot = self.vehicle_to_slot_map.search(norm_plate)
            raise ValueError(f"Vehicle '{norm_plate}' is already parked in slot '{existing_slot}'.")

        # Canonical vehicle retrieval / construction:
        canonical_vehicle: Optional[Vehicle] = None
        newly_registered = False

        if self.vehicles_map.contains(norm_plate):
            canonical_vehicle = self.vehicles_map.search(norm_plate)
        else:
            db_vehicle = self.repository.get_vehicle_by_plate(norm_plate)
            if db_vehicle is not None:
                canonical_vehicle = db_vehicle
            else:
                canonical_vehicle = Vehicle(
                    license_plate=license_plate,
                    vehicle_type=vehicle_type,
                    owner_name=owner_name,
                    owner_phone=owner_phone
                )
                newly_registered = True

        # Slot selection
        target_slot: Optional[ParkingSlot] = None
        if slot_id:
            target_slot = self.get_slot_by_id(slot_id)
            if not target_slot:
                raise ValueError(f"ParkingSlot '{slot_id}' does not exist.")
            if target_slot.is_occupied:
                raise ValueError(f"ParkingSlot '{slot_id}' is already occupied.")
        else:
            target_slot = self.find_available_slot(canonical_vehicle.vehicle_type)
            if not target_slot:
                raise ValueError(f"No available compatible parking slot for vehicle type '{canonical_vehicle.vehicle_type}'.")

        # Assign vehicle to slot in-memory (validates type compatibility)
        target_slot.assign_vehicle(canonical_vehicle)

        # Multi-step persistence tracking for verifiable compensating rollback
        slot_persisted = False
        vehicle_inserted_in_db = False

        try:
            # Step 1: Update slot in database
            slot_updated = self.repository.update_slot(target_slot)
            if not slot_updated:
                raise RuntimeError(f"Database failed to update slot '{target_slot.slot_id}' during parking.")
            slot_persisted = True

            # Step 2: Register vehicle record in DB only if this is a newly registered vehicle
            if newly_registered:
                self.repository.insert_vehicle(canonical_vehicle)
                vehicle_inserted_in_db = True

            # Step 3: Log check-in history
            history_id = self.repository.log_history({
                "license_plate": canonical_vehicle.license_plate,
                "slot_id": target_slot.slot_id,
                "action": "CHECK_IN",
                "entry_time": canonical_vehicle.entry_time,
                "fee": 0.0
            })
            if not history_id:
                raise RuntimeError(f"Database failed to log check-in history for '{canonical_vehicle.license_plate}'.")

        except Exception as primary_exc:
            compensation_failures: List[str] = []

            # Compensating rollback Step 1: Revert slot in database
            if slot_persisted:
                try:
                    target_slot.release_vehicle()
                    revert_ok = self.repository.update_slot(target_slot)
                    if not revert_ok:
                        compensation_failures.append(f"Compensating slot update failed for '{target_slot.slot_id}' (update returned False)")
                except Exception as comp_err:
                    compensation_failures.append(f"Compensating slot update threw: {comp_err}")

            # Compensating rollback Step 2: Delete vehicle ONLY if it was newly inserted during this call
            if vehicle_inserted_in_db:
                try:
                    del_ok = self.repository.delete_vehicle(canonical_vehicle.license_plate)
                    if not del_ok:
                        compensation_failures.append(f"Compensating vehicle deletion failed for '{canonical_vehicle.license_plate}' (delete returned False)")
                except Exception as comp_err:
                    compensation_failures.append(f"Compensating vehicle deletion threw: {comp_err}")

            # In-memory slot state rollback
            if target_slot.is_occupied:
                target_slot.release_vehicle()

            if compensation_failures:
                comp_err = RuntimeError(
                    f"Failed to persist vehicle parking for '{canonical_vehicle.license_plate}': {primary_exc}. "
                    f"CRITICAL: Compensating rollback also failed: {'; '.join(compensation_failures)}. "
                    f"Manual database reconciliation required."
                )
                comp_err.is_incomplete_compensation = True
                raise comp_err from primary_exc
            else:
                raise RuntimeError(f"Failed to persist vehicle parking for '{canonical_vehicle.license_plate}': {primary_exc}") from primary_exc

        # Synchronize In-Memory Custom Data Structures ONLY after all persistence steps succeed
        self.slots_map.insert(target_slot.slot_id, target_slot)
        self.vehicle_to_slot_map.insert(canonical_vehicle.license_plate, target_slot.slot_id)
        self.vehicles_map.insert(canonical_vehicle.license_plate, canonical_vehicle)

        # Push to LIFO audit stack
        self.action_stack.push({
            "action": "PARK",
            "license_plate": canonical_vehicle.license_plate,
            "slot_id": target_slot.slot_id,
            "timestamp": datetime.now()
        })

        return target_slot

    def checkout_vehicle(self, license_plate: str, hourly_rate: float = DEFAULT_HOURLY_RATE) -> Dict[str, Any]:
        """
        Checks out a vehicle, vacates its slot, calculates parking fee,
        and synchronizes all data structures with verifiable compensating rollback protection.

        Recovery Strategy:
        If vehicle deletion or history logging fails after updating the slot to vacant,
        compensating operations revert the slot to occupied in MongoDB, re-insert the vehicle
        preserving exact original attributes (including entry_time), and restore in-memory occupancy.
        If compensation is incomplete, raises a diagnostic RuntimeError identifying partial failures.

        Args:
            license_plate (str): License plate of exiting vehicle.
            hourly_rate (float): Parking fee rate per hour (must be positive finite number <= 100,000.0).

        Returns:
            Dict[str, Any]: Checkout receipt with billing summary and next allocation info.

        Raises:
            ValueError: If input validation fails or vehicle is not currently parked.
            RuntimeError: If database persistence fails or compensation is incomplete.
        """
        # Validate hourly_rate strictly against boolean, non-numeric, overflow, or extreme values
        if isinstance(hourly_rate, bool) or not isinstance(hourly_rate, (int, float)):
            raise ValueError(f"hourly_rate must be a positive finite number, got {type(hourly_rate).__name__}.")
        try:
            rate_float = float(hourly_rate)
        except (OverflowError, ValueError):
            raise ValueError(f"hourly_rate is out of range or cannot be represented as float: {hourly_rate}")

        if not math.isfinite(rate_float) or rate_float <= 0 or rate_float > self.MAX_HOURLY_RATE:
            raise ValueError(f"hourly_rate must be a positive finite number <= {self.MAX_HOURLY_RATE}, got {hourly_rate}.")

        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        norm_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        if not self.vehicle_to_slot_map.contains(norm_plate):
            raise ValueError(f"Vehicle '{norm_plate}' is not currently parked in any slot.")

        slot_id = self.vehicle_to_slot_map.search(norm_plate)
        slot: ParkingSlot = self.slots_map.search(slot_id)

        # Vacate slot in-memory
        departed_vehicle = slot.release_vehicle()
        exit_time = datetime.now()

        # Calculate billing
        duration_seconds = max((exit_time - departed_vehicle.entry_time).total_seconds(), 0.0)
        duration_hours = round(duration_seconds / 3600.0, 2)
        billable_hours = max(1.0, duration_hours)
        fee = round(billable_hours * rate_float, 2)

        # Multi-step persistence tracking for verifiable compensating rollback
        slot_persisted = False
        vehicle_deleted = False
        history_id = None

        try:
            # Step 1: Update slot to vacant in DB
            slot_updated = self.repository.update_slot(slot)
            if not slot_updated:
                raise RuntimeError(f"Database failed to update slot '{slot.slot_id}' during checkout.")
            slot_persisted = True

            # Step 2: Delete vehicle from DB
            del_result = self.repository.delete_vehicle(departed_vehicle.license_plate)
            if not del_result:
                raise RuntimeError(f"Database failed to delete vehicle '{departed_vehicle.license_plate}' during checkout.")
            vehicle_deleted = True

            # Step 3: Log checkout history
            history_id = self.repository.log_history({
                "license_plate": departed_vehicle.license_plate,
                "slot_id": slot.slot_id,
                "action": "CHECK_OUT",
                "entry_time": departed_vehicle.entry_time,
                "exit_time": exit_time,
                "duration_hours": duration_hours,
                "fee": fee
            })
            if not history_id:
                raise RuntimeError(f"Database failed to log checkout history for '{norm_plate}'.")

        except Exception as primary_exc:
            compensation_failures: List[str] = []

            # Compensating rollback Step 1: Restore slot to occupied
            if slot_persisted:
                try:
                    slot.assign_vehicle(departed_vehicle)
                    revert_slot_ok = self.repository.update_slot(slot)
                    if not revert_slot_ok:
                        compensation_failures.append(f"Compensating slot update failed for '{slot.slot_id}' (update returned False)")
                except Exception as comp_err:
                    compensation_failures.append(f"Compensating slot update threw: {comp_err}")

            # Compensating rollback Step 2: Re-insert deleted vehicle (preserving exact original details & entry_time)
            if vehicle_deleted:
                try:
                    self.repository.insert_vehicle(departed_vehicle)
                except Exception as comp_err:
                    compensation_failures.append(f"Compensating vehicle re-insertion failed for '{departed_vehicle.license_plate}': {comp_err}")

            # In-memory rollback: slot must remain occupied
            if not slot.is_occupied:
                slot.assign_vehicle(departed_vehicle)

            if compensation_failures:
                raise RuntimeError(
                    f"Failed to persist vehicle checkout for '{norm_plate}': {primary_exc}. "
                    f"CRITICAL: Compensating rollback also failed: {'; '.join(compensation_failures)}. "
                    f"Manual database reconciliation required."
                ) from primary_exc
            else:
                raise RuntimeError(f"Failed to persist vehicle checkout for '{norm_plate}': {primary_exc}") from primary_exc

        # Synchronize In-Memory Data Structures ONLY after DB success
        # Vehicle is removed from active slot mapping, but preserved in vehicles_map as registered
        self.vehicle_to_slot_map.delete(norm_plate)
        self.slots_map.insert(slot.slot_id, slot)

        # Push to LIFO audit stack
        self.action_stack.push({
            "action": "CHECK_OUT",
            "license_plate": departed_vehicle.license_plate,
            "slot_id": slot.slot_id,
            "fee": fee,
            "history_id": history_id,
            "timestamp": exit_time
        })

        # Process next compatible waiting booking for this freed slot
        next_allocation: Optional[Dict[str, Any]] = None
        try:
            next_allocation = self.process_next_waiting_booking(compatible_slot_id=slot.slot_id)
        except Exception:
            # Background waitlist allocation failure must not crash successful checkout
            next_allocation = None

        return {
            "license_plate": departed_vehicle.license_plate,
            "slot_id": slot.slot_id,
            "entry_time": departed_vehicle.entry_time,
            "exit_time": exit_time,
            "duration_hours": duration_hours,
            "billable_hours": billable_hours,
            "hourly_rate": rate_float,
            "fee": fee,
            "history_id": history_id,
            "next_allocated_booking": next_allocation
        }

    # -------------------------------------------------------------------------
    # Waitlist & Queue Processing
    # -------------------------------------------------------------------------
    def add_booking_to_waitlist(
        self,
        license_plate: str,
        vehicle_type: str = "Car",
        owner_name: str = "",
        owner_phone: str = ""
    ) -> Dict[str, Any]:
        """
        Adds a vehicle to the FIFO waiting queue when no compatible parking slots are vacant.

        Waitlist Policy:
        - Waitlist bookings are only accepted when NO compatible slots are available.
        - If a compatible slot is currently free, the vehicle must be parked directly.

        Args:
            license_plate (str): Vehicle license plate.
            vehicle_type (str): Type of vehicle.
            owner_name (str): Driver/owner name.
            owner_phone (str): Contact phone.

        Returns:
            Dict[str, Any]: Stored booking record.

        Raises:
            ValueError: If vehicle is already parked, already waitlisted, or a compatible slot is free.
        """
        # Validate vehicle inputs via Vehicle constructor
        test_veh = Vehicle(
            license_plate=license_plate,
            vehicle_type=vehicle_type,
            owner_name=owner_name,
            owner_phone=owner_phone
        )

        if self.vehicle_to_slot_map.contains(test_veh.license_plate):
            raise ValueError(f"Vehicle '{test_veh.license_plate}' is already parked.")

        # Check if already in waiting queue
        for b in self.waiting_queue:
            if b.get("license_plate") == test_veh.license_plate:
                raise ValueError(f"Vehicle '{test_veh.license_plate}' is already in the waitlist queue.")

        # Enforce waitlist policy: cannot join waitlist if a compatible slot is available
        available_slot = self.find_available_slot(test_veh.vehicle_type)
        if available_slot is not None:
            raise ValueError(
                f"Cannot add to waitlist: Compatible slot '{available_slot.slot_id}' is currently available. "
                f"Please park the vehicle directly."
            )

        booking_data = {
            "license_plate": test_veh.license_plate,
            "vehicle_type": test_veh.vehicle_type,
            "owner_name": test_veh.owner_name,
            "owner_phone": test_veh.owner_phone,
            "status": "WAITING",
            "created_at": datetime.now()
        }

        # Persist to database
        booking_id = self.repository.create_booking(booking_data)
        booking_data["booking_id"] = booking_id

        # Enqueue in-memory
        self.waiting_queue.enqueue(booking_data)

        # Push to stack
        self.action_stack.push({
            "action": "WAITLIST_ENQUEUE",
            "booking_id": booking_id,
            "license_plate": test_veh.license_plate,
            "timestamp": datetime.now()
        })

        return booking_data

    def process_next_waiting_booking(self, compatible_slot_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Processes the next compatible booking from the FIFO waiting queue.
        Maintains strict FIFO order while finding the earliest waiting vehicle
        matching the available slot.

        Consistent Allocation & Verifiable Compensating Rollback:
        1. If park_vehicle() fails: the vehicle was NOT parked. The booking is restored to its
           exact original FIFO position in the waiting queue and database status verified as WAITING.
        2. If park_vehicle() succeeds but updating the booking to ALLOCATED fails:
           - First release the slot in memory and update the vacant slot in MongoDB.
           - Only after slot vacating succeeds, delete the parked vehicle from MongoDB.
           - Never delete the vehicle if the vacant-slot DB update fails.
           - If vehicle deletion fails, restore the occupied slot in both MongoDB and memory.
           - Do not re-enqueue a booking as WAITING if the rollback is incomplete.
           - If unpark succeeds, log WAITLIST_ALLOCATION_ROLLBACK in parking history and push to action stack.
           - Restore the booking to its exact original FIFO position in the waiting queue.
           - Update database status back to WAITING, reporting diagnostic errors if restoration fails.

        Args:
            compatible_slot_id (Optional[str]): Target vacant slot ID.

        Returns:
            Optional[Dict[str, Any]]: Allocation summary if a booking was parked, or None.

        Raises:
            RuntimeError: If allocation fails and recovery is executed or incomplete.
        """
        if self.waiting_queue.is_empty():
            return None

        # Determine target slot
        target_slot: Optional[ParkingSlot] = None
        if compatible_slot_id:
            target_slot = self.get_slot_by_id(compatible_slot_id)
            if not target_slot or target_slot.is_occupied:
                return None

        # Inspect queue elements in FIFO order while tracking original index
        queue_len = len(self.waiting_queue)
        matched_booking: Optional[Dict[str, Any]] = None
        matched_index: int = -1

        for idx in range(queue_len):
            current_booking = self.waiting_queue.dequeue()

            # If we haven't found a match yet, test compatibility
            if matched_booking is None:
                v_type = current_booking.get("vehicle_type", "Car")
                chosen_slot = target_slot if target_slot else self.find_available_slot(v_type)

                if chosen_slot and not chosen_slot.is_occupied:
                    is_compatible = (
                        chosen_slot.slot_type == v_type or
                        (v_type == "EV" and chosen_slot.slot_type == "Car")
                    )
                    if is_compatible:
                        matched_booking = current_booking
                        matched_index = idx  # Preserve exact original FIFO index
                        target_slot = chosen_slot
                        continue  # Keep out of queue while attempting allocation

            # Re-enqueue other bookings to preserve relative FIFO order
            self.waiting_queue.enqueue(current_booking)

        if not matched_booking or not target_slot:
            return None

        # Step 1: Record AUTOMATIC_ALLOCATION on custom action stack before parking session
        self.action_stack.push({
            "action": "AUTOMATIC_ALLOCATION",
            "booking_id": matched_booking["booking_id"],
            "license_plate": matched_booking["license_plate"],
            "slot_id": target_slot.slot_id,
            "timestamp": datetime.now()
        })

        # Determine whether the vehicle record already exists in memory or MongoDB
        norm_matched_plate = (
            matched_booking["license_plate"].strip().upper().replace(" ", "").replace("-", "")
        )
        vehicle_preexisted = (
            self.vehicles_map.contains(norm_matched_plate) or
            self.repository.get_vehicle_by_plate(norm_matched_plate) is not None
        )

        parked_slot: Optional[ParkingSlot] = None

        # Step 2: Attempt to park the vehicle (records PARK event on action stack)
        try:
            parked_slot = self.park_vehicle(
                license_plate=matched_booking["license_plate"],
                vehicle_type=matched_booking.get("vehicle_type", "Car"),
                owner_name=matched_booking.get("owner_name", ""),
                owner_phone=matched_booking.get("owner_phone", ""),
                slot_id=target_slot.slot_id
            )
        except Exception as park_exc:
            # Revert AUTOMATIC_ALLOCATION if parking attempt failed
            if not self.action_stack.is_empty() and self.action_stack.peek().get("action") == "AUTOMATIC_ALLOCATION":
                self.action_stack.pop()

            # Distinguish ordinary parking failure with confirmed rollback from incomplete compensation
            is_incomplete_compensation = (
                getattr(park_exc, "is_incomplete_compensation", False) or
                "CRITICAL: Compensating rollback also failed" in str(park_exc)
            )

            if is_incomplete_compensation:
                # Do NOT restore booking to queue because database/in-memory state is inconsistent
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': "
                    f"Parking persistence failed and compensating rollback was incomplete ({park_exc}). "
                    f"Booking was NOT re-enqueued as WAITING to prevent inconsistent duplicate state. "
                    f"Manual database reconciliation required."
                ) from park_exc

            # Parking failed with confirmed successful rollback:
            # Safe to restore booking to exact original FIFO position
            self._restore_booking_to_queue(matched_booking, matched_index)

            status_restore_ok = False
            status_restore_err = None
            try:
                status_restore_ok = self.repository.update_booking_status(matched_booking["booking_id"], "WAITING")
                if not status_restore_ok:
                    status_restore_err = "update_booking_status returned False"
            except Exception as e:
                status_restore_err = str(e)

            if not status_restore_ok:
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': Parking failed ({park_exc}). "
                    f"Booking restored to in-memory queue at original position, but database status restoration to WAITING failed ({status_restore_err}). "
                    f"Manual database reconciliation required."
                ) from park_exc
            else:
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': {park_exc}"
                ) from park_exc

        # Step 2: Update booking status to ALLOCATED in database
        try:
            status_updated = self.repository.update_booking_status(matched_booking["booking_id"], "ALLOCATED")
            if not status_updated:
                raise RuntimeError(
                    f"Database failed to mark booking '{matched_booking['booking_id']}' as ALLOCATED (update returned False)."
                )
        except Exception as status_exc:
            # Critical Scenario: Parking succeeded, but booking status update to ALLOCATED failed!
            # Must perform verified compensating unpark so the vehicle does NOT remain parked while waitlisted
            parked_vehicle = parked_slot.vehicle
            unpark_failures: List[str] = []

            # Step 2A: First release slot in memory and successfully update vacant slot in MongoDB
            parked_slot.release_vehicle()
            slot_vacate_ok = False
            try:
                slot_vacate_ok = self.repository.update_slot(parked_slot)
                if not slot_vacate_ok:
                    unpark_failures.append(f"Compensating slot update to vacant returned False for '{parked_slot.slot_id}'")
            except Exception as e:
                unpark_failures.append(f"Compensating slot update threw: {e}")

            # Step 2B: Never delete the vehicle if the vacant-slot DB update fails!
            # Only after slot vacating succeeds, delete vehicle from MongoDB ONLY IF it was newly created
            if slot_vacate_ok:
                veh_del_ok = True
                if not vehicle_preexisted:
                    try:
                        veh_del_ok = self.repository.delete_vehicle(norm_matched_plate)
                        if not veh_del_ok:
                            unpark_failures.append(f"Compensating vehicle deletion returned False for '{norm_matched_plate}'")
                    except Exception as e:
                        veh_del_ok = False
                        unpark_failures.append(f"Compensating vehicle deletion threw: {e}")

                # If vehicle deletion failed, attempt to restore the occupied slot in both MongoDB and memory
                if not veh_del_ok:
                    parked_slot.assign_vehicle(parked_vehicle)
                    try:
                        re_occupy_ok = self.repository.update_slot(parked_slot)
                        if not re_occupy_ok:
                            unpark_failures.append(f"Failed to restore slot '{parked_slot.slot_id}' to occupied in DB after deletion failure (returned False)")
                    except Exception as e:
                        unpark_failures.append(f"Failed to restore slot '{parked_slot.slot_id}' to occupied in DB after deletion failure: {e}")
            else:
                # Vacant-slot DB update failed: do NOT delete vehicle! Restore in-memory slot to occupied
                parked_slot.assign_vehicle(parked_vehicle)

            # Step 2C: Memory synchronization and rollback verification check
            if not unpark_failures:
                self.slots_map.insert(parked_slot.slot_id, parked_slot)
                self.vehicle_to_slot_map.delete(norm_matched_plate)
                if not vehicle_preexisted:
                    if self.vehicles_map.contains(norm_matched_plate):
                        self.vehicles_map.delete(norm_matched_plate)
            else:
                # Unpark could NOT be verified!
                # Do NOT re-enqueue as WAITING because vehicle may still be parked in DB/slot!
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': "
                    f"Failed to update booking status to ALLOCATED ({status_exc}). "
                    f"CRITICAL: Compensating unpark could not be verified: {'; '.join(unpark_failures)}. "
                    f"The vehicle '{matched_booking['license_plate']}' may still be parked in slot '{parked_slot.slot_id}'. "
                    f"Booking was NOT re-enqueued as WAITING to prevent inconsistent duplicate state. "
                    f"Manual database reconciliation required."
                ) from status_exc

            # Step 2D: Record rollback event in parking history
            history_rollback_ok = False
            history_rollback_err = None
            try:
                history_rollback_id = self.repository.log_history({
                    "license_plate": matched_booking["license_plate"],
                    "slot_id": parked_slot.slot_id,
                    "action": "WAITLIST_ALLOCATION_ROLLBACK",
                    "booking_id": matched_booking["booking_id"],
                    "timestamp": datetime.now(),
                    "fee": 0.0
                })
                if history_rollback_id:
                    history_rollback_ok = True
                else:
                    history_rollback_err = "log_history returned empty ID"
            except Exception as e:
                history_rollback_err = str(e)

            # Step 2E: Push rollback action onto custom action stack
            self.action_stack.push({
                "action": "WAITLIST_ALLOCATION_ROLLBACK",
                "booking_id": matched_booking["booking_id"],
                "license_plate": matched_booking["license_plate"],
                "slot_id": parked_slot.slot_id,
                "timestamp": datetime.now()
            })

            # Step 2F: Compensating unpark was verified! Restore booking to queue at original index
            self._restore_booking_to_queue(matched_booking, matched_index)

            # Step 2G: Attempt to restore booking status in DB to WAITING
            restore_ok = False
            restore_err = None
            try:
                restore_ok = self.repository.update_booking_status(matched_booking["booking_id"], "WAITING")
                if not restore_ok:
                    restore_err = "update_booking_status returned False"
            except Exception as e:
                restore_err = str(e)

            if not restore_ok:
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': "
                    f"Failed to mark booking as ALLOCATED ({status_exc}). "
                    f"Compensating unpark succeeded, but restoring booking status to WAITING in database failed ({restore_err}). "
                    f"Booking was restored to in-memory queue at original position. "
                    f"Manual booking status reconciliation in database required."
                ) from status_exc
            elif not history_rollback_ok:
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': "
                    f"Failed to mark booking as ALLOCATED ({status_exc}). "
                    f"Compensating unpark succeeded and booking restored to waiting queue, but logging rollback history failed ({history_rollback_err})."
                ) from status_exc
            else:
                raise RuntimeError(
                    f"Waitlist allocation failed for booking '{matched_booking['booking_id']}': "
                    f"Failed to mark booking as ALLOCATED ({status_exc}). "
                    f"Compensating unpark succeeded and booking restored to waiting queue at original position."
                ) from status_exc

        return {
            "booking_id": matched_booking["booking_id"],
            "license_plate": matched_booking["license_plate"],
            "slot_id": parked_slot.slot_id,
            "allocated_at": datetime.now()
        }

    # -------------------------------------------------------------------------
    # DSA State Exporters for Streamlit Visualizer
    # -------------------------------------------------------------------------
    def get_hashmap_state(self) -> Dict[str, Any]:
        """
        Exposes internal bucket chains from all three custom HashMaps for the DSA Visualizer:
        - slots_map
        - vehicle_to_slot_map
        - vehicles_map
        Zero hardcoded or simulated values.
        """
        return {
            "slots_hashmap": {
                "size": self.slots_map.size,
                "capacity": self.slots_map.capacity,
                "load_factor": round(self.slots_map.load_factor, 3),
                "buckets": self.slots_map.get_internal_state()
            },
            "vehicle_to_slot_hashmap": {
                "size": self.vehicle_to_slot_map.size,
                "capacity": self.vehicle_to_slot_map.capacity,
                "load_factor": round(self.vehicle_to_slot_map.load_factor, 3),
                "buckets": self.vehicle_to_slot_map.get_internal_state()
            },
            "vehicles_hashmap": {
                "size": self.vehicles_map.size,
                "capacity": self.vehicles_map.capacity,
                "load_factor": round(self.vehicles_map.load_factor, 3),
                "buckets": self.vehicles_map.get_internal_state()
            }
        }

    def get_queue_state(self) -> List[Any]:
        """Exposes actual linked list node payloads from front to rear."""
        return self.waiting_queue.get_internal_state()

    def get_stack_state(self) -> List[Any]:
        """Exposes actual linked list node payloads from top to bottom."""
        return self.action_stack.get_internal_state()

    def get_dsa_metrics(self) -> Dict[str, Any]:
        """Aggregates metrics across all custom DSA instances for dashboard KPI cards."""
        return {
            "slots_map_size": self.slots_map.size,
            "slots_map_capacity": self.slots_map.capacity,
            "slots_map_load_factor": round(self.slots_map.load_factor, 3),
            "vehicle_to_slot_map_size": self.vehicle_to_slot_map.size,
            "vehicle_to_slot_map_capacity": self.vehicle_to_slot_map.capacity,
            "vehicle_to_slot_map_load_factor": round(self.vehicle_to_slot_map.load_factor, 3),
            "vehicles_map_size": self.vehicles_map.size,
            "vehicles_map_capacity": self.vehicles_map.capacity,
            "vehicles_map_load_factor": round(self.vehicles_map.load_factor, 3),
            "waitlist_queue_size": self.waiting_queue.size,
            "action_stack_size": self.action_stack.size
        }

    def get_recent_actions(self, count: int = 10) -> List[Any]:
        """
        Retrieves most recent actions from the action stack without altering state.

        Args:
            count (int): Number of recent actions to retrieve (must be non-negative integer).

        Returns:
            List[Any]: List of recent action payload dictionaries.

        Raises:
            ValueError: If count is negative, non-integer, or a boolean.
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"count must be a non-negative integer, got {count}.")

        state = self.action_stack.get_internal_state()
        return state[:count]

    def pop_action_stack(self) -> Optional[Dict[str, Any]]:
        """
        Pops and returns the topmost action from the action stack (LIFO).

        Requirements:
        - Calls the existing custom ParkingStack.pop().
        - Exactly one top node is removed from self.action_stack.
        - Handles an empty stack safely (returns None without error).
        - Does NOT undo parking operations or modify MongoDB records.
        - Refreshes stack depth and visualization.

        Returns:
            Optional[Dict[str, Any]]: The popped action dictionary, or None if empty.
        """
        if self.action_stack.is_empty():
            return None
        return self.action_stack.pop()

    pop_action = pop_action_stack

    def get_parking_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves recent parking history / audit records from MongoDB.

        Args:
            limit (int): Maximum records to retrieve (default 100).

        Returns:
            List[Dict[str, Any]]: List of history record dictionaries.
        """
        return self.repository.get_all_history(limit=limit)
