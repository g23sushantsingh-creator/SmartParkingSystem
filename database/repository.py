"""
Database Repository Layer for Smart Parking Management System.

Provides CRUD helper functions for four MongoDB collections:
- parking_slots: Physical slot configurations and occupancy states.
- vehicles: Registered active vehicles.
- bookings: Waiting list reservations and queue tickets.
- parking_history: Audit trail logs of check-ins, check-outs, and fee collections.

Separation of Concerns:
Does NOT contain DSA logic (Hash Map, Queue, Stack).
DSA state management is decoupled and handled by the ParkingManager service.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from pymongo.database import Database
from pymongo.errors import PyMongoError, DuplicateKeyError
from models.vehicle import Vehicle
from models.parking_slot import ParkingSlot


class ParkingRepository:
    """
    Repository class providing CRUD operations for MongoDB collections.
    Accepts an optional Database instance for dependency injection and testing.
    """

    def __init__(self, database: Optional[Database] = None) -> None:
        if database is not None:
            self.db = database
        else:
            from database.mongodb import db as default_db
            self.db = default_db

        self.slots_col = self.db["parking_slots"]
        self.vehicles_col = self.db["vehicles"]
        self.bookings_col = self.db["bookings"]
        self.history_col = self.db["parking_history"]

        # Ensure database-level unique indexes
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """
        Creates unique database-level indexes on primary identifier fields.
        Skips collections that do not support indexing (e.g. basic mocks).
        Raises RuntimeError identifying the collection and field if a real
        PyMongoError occurs (e.g. duplicate keys in existing records or database error).
        """
        index_specs = [
            (self.slots_col, "slot_id"),
            (self.vehicles_col, "license_plate"),
            (self.bookings_col, "booking_id"),
            (self.history_col, "history_id")
        ]
        for col, field in index_specs:
            if not hasattr(col, "create_index") or not callable(getattr(col, "create_index", None)):
                continue

            try:
                col.create_index(field, unique=True)
            except PyMongoError as exc:
                col_name = getattr(col, "name", str(col))
                raise RuntimeError(
                    f"Failed to create unique index on '{col_name}.{field}': {exc}"
                ) from exc

    # =========================================================================
    # 1. PARKING SLOTS CRUD
    # =========================================================================
    def insert_slot(self, slot: ParkingSlot) -> str:
        """
        Inserts a new parking slot into the parking_slots collection.

        Args:
            slot (ParkingSlot): The slot entity to insert.

        Returns:
            str: The slot_id of the inserted slot.

        Raises:
            ValueError: If a slot with the same slot_id already exists.
            RuntimeError: If a database error occurs.
        """
        if not isinstance(slot, ParkingSlot):
            raise TypeError(f"Expected ParkingSlot instance, got {type(slot).__name__}.")

        doc = slot.to_dict()
        # Convert nested vehicle entry_time to native BSON datetime if present
        if doc.get("vehicle") and isinstance(slot.vehicle.entry_time, datetime):
            doc["vehicle"]["entry_time"] = slot.vehicle.entry_time
        doc["updated_at"] = datetime.now()

        try:
            existing = self.slots_col.find_one({"slot_id": slot.slot_id})
            if existing:
                raise ValueError(f"ParkingSlot with slot_id '{slot.slot_id}' already exists.")

            self.slots_col.insert_one(doc)
            return slot.slot_id
        except ValueError:
            raise
        except DuplicateKeyError as exc:
            raise ValueError(f"ParkingSlot '{slot.slot_id}' already exists.") from exc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error inserting slot '{slot.slot_id}': {exc}") from exc

    def get_slot_by_id(self, slot_id: str) -> Optional[ParkingSlot]:
        """
        Retrieves a parking slot by its unique slot_id.

        Args:
            slot_id (str): Identifier (e.g. 'F1-S01').

        Returns:
            Optional[ParkingSlot]: ParkingSlot instance or None if not found.
        """
        if not slot_id or not isinstance(slot_id, str):
            raise ValueError("slot_id must be a non-empty string.")

        normalized_id = slot_id.strip().upper()
        try:
            doc = self.slots_col.find_one({"slot_id": normalized_id})
            if not doc:
                return None
            doc.pop("_id", None)
            return ParkingSlot.from_dict(doc)
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving slot '{slot_id}': {exc}") from exc

    def get_all_slots(self) -> List[ParkingSlot]:
        """
        Retrieves all parking slots from the database.

        Returns:
            List[ParkingSlot]: List of all reconstructed ParkingSlot objects.
        """
        try:
            cursor = self.slots_col.find().sort([("floor", 1), ("slot_id", 1)])
            slots: List[ParkingSlot] = []
            for doc in cursor:
                doc.pop("_id", None)
                slots.append(ParkingSlot.from_dict(doc))
            return slots
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving all slots: {exc}") from exc

    def update_slot(self, slot: ParkingSlot) -> bool:
        """
        Updates an existing parking slot's occupancy and vehicle state.

        Args:
            slot (ParkingSlot): The updated slot entity.

        Returns:
            bool: True if a document was modified, False otherwise.
        """
        if not isinstance(slot, ParkingSlot):
            raise TypeError(f"Expected ParkingSlot instance, got {type(slot).__name__}.")

        doc = slot.to_dict()
        if doc.get("vehicle") and isinstance(slot.vehicle.entry_time, datetime):
            doc["vehicle"]["entry_time"] = slot.vehicle.entry_time
        doc["updated_at"] = datetime.now()

        try:
            res = self.slots_col.update_one(
                {"slot_id": slot.slot_id},
                {"$set": doc}
            )
            return res.matched_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error updating slot '{slot.slot_id}': {exc}") from exc

    def delete_slot(self, slot_id: str) -> bool:
        """
        Deletes a parking slot record by its slot_id.

        Args:
            slot_id (str): Identifier of slot to delete.

        Returns:
            bool: True if slot was deleted, False if not found.
        """
        if not slot_id or not isinstance(slot_id, str):
            raise ValueError("slot_id must be a non-empty string.")

        normalized_id = slot_id.strip().upper()
        try:
            res = self.slots_col.delete_one({"slot_id": normalized_id})
            return res.deleted_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error deleting slot '{slot_id}': {exc}") from exc

    # =========================================================================
    # 2. VEHICLES CRUD
    # =========================================================================
    def insert_vehicle(self, vehicle: Vehicle) -> str:
        """
        Inserts a vehicle into the vehicles collection.

        Args:
            vehicle (Vehicle): The vehicle instance to insert.

        Returns:
            str: Normalized license_plate of the inserted vehicle.

        Raises:
            ValueError: If vehicle with same license plate already exists.
        """
        if not isinstance(vehicle, Vehicle):
            raise TypeError(f"Expected Vehicle instance, got {type(vehicle).__name__}.")

        doc = vehicle.to_dict()
        doc["entry_time"] = vehicle.entry_time
        doc["created_at"] = datetime.now()

        try:
            existing = self.vehicles_col.find_one({"license_plate": vehicle.license_plate})
            if existing:
                raise ValueError(f"Vehicle with plate '{vehicle.license_plate}' already exists.")

            self.vehicles_col.insert_one(doc)
            return vehicle.license_plate
        except ValueError:
            raise
        except DuplicateKeyError as exc:
            raise ValueError(f"Vehicle with plate '{vehicle.license_plate}' already exists.") from exc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error inserting vehicle '{vehicle.license_plate}': {exc}") from exc

    def get_vehicle_by_plate(self, license_plate: str) -> Optional[Vehicle]:
        """
        Retrieves a vehicle by its license plate.

        Args:
            license_plate (str): Vehicle license plate.

        Returns:
            Optional[Vehicle]: Vehicle instance or None if not found.
        """
        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        normalized_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        try:
            doc = self.vehicles_col.find_one({"license_plate": normalized_plate})
            if not doc:
                return None
            doc.pop("_id", None)
            return Vehicle.from_dict(doc)
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving vehicle '{license_plate}': {exc}") from exc

    def get_all_vehicles(self) -> List[Vehicle]:
        """
        Retrieves all vehicles from the database.

        Returns:
            List[Vehicle]: List of reconstructed Vehicle objects.
        """
        try:
            cursor = self.vehicles_col.find().sort("entry_time", -1)
            vehicles: List[Vehicle] = []
            for doc in cursor:
                doc.pop("_id", None)
                vehicles.append(Vehicle.from_dict(doc))
            return vehicles
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving all vehicles: {exc}") from exc

    def update_vehicle(self, vehicle: Vehicle) -> bool:
        """
        Updates an existing vehicle record.

        Args:
            vehicle (Vehicle): Updated vehicle instance.

        Returns:
            bool: True if vehicle was found and updated, False otherwise.
        """
        if not isinstance(vehicle, Vehicle):
            raise TypeError(f"Expected Vehicle instance, got {type(vehicle).__name__}.")

        doc = vehicle.to_dict()
        doc["entry_time"] = vehicle.entry_time
        doc["updated_at"] = datetime.now()

        try:
            res = self.vehicles_col.update_one(
                {"license_plate": vehicle.license_plate},
                {"$set": doc}
            )
            return res.matched_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error updating vehicle '{vehicle.license_plate}': {exc}") from exc

    def delete_vehicle(self, license_plate: str) -> bool:
        """
        Deletes a vehicle record by license plate (e.g. upon departure).

        Args:
            license_plate (str): Plate of vehicle to remove.

        Returns:
            bool: True if removed, False if not found.
        """
        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        normalized_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        try:
            res = self.vehicles_col.delete_one({"license_plate": normalized_plate})
            return res.deleted_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error deleting vehicle '{license_plate}': {exc}") from exc

    # =========================================================================
    # 3. BOOKINGS / WAITLIST CRUD
    # =========================================================================
    def create_booking(self, booking_data: Dict[str, Any]) -> str:
        """
        Creates a new booking or waitlist reservation.

        Args:
            booking_data (Dict[str, Any]): Dictionary containing license_plate, vehicle_type, etc.

        Returns:
            str: Generated or normalized uppercase booking_id.

        Raises:
            ValueError: If booking_data or license_plate is missing or invalid.
        """
        if not booking_data or not isinstance(booking_data, dict):
            raise ValueError("booking_data must be a non-empty dictionary.")

        if "license_plate" not in booking_data:
            raise ValueError("Missing 'license_plate' in booking_data.")

        raw_plate = booking_data["license_plate"]
        if not isinstance(raw_plate, str) or not raw_plate.strip():
            raise ValueError("license_plate in booking_data must be a non-empty string.")

        doc = dict(booking_data)

        # Normalize explicitly supplied booking_id to uppercase
        raw_booking_id = doc.get("booking_id")
        if raw_booking_id is not None:
            if not isinstance(raw_booking_id, str) or not raw_booking_id.strip():
                raise ValueError("booking_id must be a non-empty string if provided.")
            booking_id = raw_booking_id.strip().upper()
        else:
            booking_id = uuid.uuid4().hex[:8].upper()

        doc["booking_id"] = booking_id
        doc["license_plate"] = raw_plate.strip().upper().replace(" ", "").replace("-", "")
        doc["status"] = doc.get("status", "WAITING")
        if "created_at" not in doc or not isinstance(doc["created_at"], datetime):
            doc["created_at"] = datetime.now()

        try:
            self.bookings_col.insert_one(doc)
            return booking_id
        except DuplicateKeyError as exc:
            raise ValueError(f"Booking with ID '{booking_id}' already exists.") from exc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error creating booking '{booking_id}': {exc}") from exc

    def get_booking_by_id(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a booking by booking_id.

        Args:
            booking_id (str): Booking ID.

        Returns:
            Optional[Dict[str, Any]]: Booking dictionary or None.
        """
        if not booking_id or not isinstance(booking_id, str):
            raise ValueError("booking_id must be a non-empty string.")

        try:
            doc = self.bookings_col.find_one({"booking_id": booking_id.strip().upper()})
            if doc:
                doc.pop("_id", None)
            return doc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving booking '{booking_id}': {exc}") from exc

    def get_all_bookings(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves all bookings, optionally filtered by status ('WAITING', 'ALLOCATED', etc.).

        Args:
            status (Optional[str]): Status filter.

        Returns:
            List[Dict[str, Any]]: List of booking records.
        """
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status.strip().upper()

        try:
            cursor = self.bookings_col.find(query).sort("created_at", 1)
            bookings: List[Dict[str, Any]] = []
            for doc in cursor:
                doc.pop("_id", None)
                bookings.append(doc)
            return bookings
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving bookings: {exc}") from exc

    def update_booking_status(self, booking_id: str, new_status: str) -> bool:
        """
        Updates the status of a booking.

        Args:
            booking_id (str): Booking ID.
            new_status (str): New status ('ALLOCATED', 'CANCELLED', etc.).

        Returns:
            bool: True if updated, False if booking_id was not matched.
        """
        if not booking_id or not isinstance(booking_id, str):
            raise ValueError("booking_id must be a non-empty string.")

        try:
            res = self.bookings_col.update_one(
                {"booking_id": booking_id.strip().upper()},
                {"$set": {"status": new_status.strip().upper(), "updated_at": datetime.now()}}
            )
            return res.matched_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error updating booking '{booking_id}': {exc}") from exc

    def delete_booking(self, booking_id: str) -> bool:
        """
        Deletes a booking record.

        Args:
            booking_id (str): Booking ID.

        Returns:
            bool: True if deleted, False otherwise.
        """
        if not booking_id or not isinstance(booking_id, str):
            raise ValueError("booking_id must be a non-empty string.")

        try:
            res = self.bookings_col.delete_one({"booking_id": booking_id.strip().upper()})
            return res.deleted_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error deleting booking '{booking_id}': {exc}") from exc

    # =========================================================================
    # 4. PARKING HISTORY / AUDIT LOG CRUD
    # =========================================================================
    def log_history(self, history_data: Dict[str, Any]) -> str:
        """
        Inserts an audit log record into parking_history.

        Args:
            history_data (Dict[str, Any]): Details of transaction (license_plate, slot_id, action, fee, etc.).

        Returns:
            str: Generated or normalized uppercase history_id.

        Raises:
            ValueError: If history_data is empty or history_id is blank string.
        """
        if not history_data or not isinstance(history_data, dict):
            raise ValueError("history_data must be a non-empty dictionary.")

        doc = dict(history_data)

        # Normalize explicitly supplied history_id to uppercase
        raw_history_id = doc.get("history_id")
        if raw_history_id is not None:
            if not isinstance(raw_history_id, str) or not raw_history_id.strip():
                raise ValueError("history_id must be a non-empty string if provided.")
            history_id = raw_history_id.strip().upper()
        else:
            history_id = uuid.uuid4().hex[:10].upper()

        doc["history_id"] = history_id
        doc["timestamp"] = doc.get("timestamp") if isinstance(doc.get("timestamp"), datetime) else datetime.now()

        # Normalize plate if present
        if "license_plate" in doc and isinstance(doc["license_plate"], str):
            doc["license_plate"] = doc["license_plate"].strip().upper().replace(" ", "").replace("-", "")

        try:
            self.history_col.insert_one(doc)
            return history_id
        except DuplicateKeyError as exc:
            raise ValueError(f"History record with ID '{history_id}' already exists.") from exc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error logging history '{history_id}': {exc}") from exc

    def get_history_by_id(self, history_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single history log by history_id.

        Args:
            history_id (str): Unique history record ID.

        Returns:
            Optional[Dict[str, Any]]: Record dictionary or None.
        """
        if not history_id or not isinstance(history_id, str):
            raise ValueError("history_id must be a non-empty string.")

        try:
            doc = self.history_col.find_one({"history_id": history_id.strip().upper()})
            if doc:
                doc.pop("_id", None)
            return doc
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving history '{history_id}': {exc}") from exc

    def get_all_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves recent parking history records sorted newest first.

        Args:
            limit (int): Maximum records to retrieve (positive integer, default 100).

        Returns:
            List[Dict[str, Any]]: List of history record dictionaries.

        Raises:
            ValueError: If limit is not a positive integer (rejects booleans).
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit}.")

        try:
            cursor = self.history_col.find().sort("timestamp", -1).limit(limit)
            records: List[Dict[str, Any]] = []
            for doc in cursor:
                doc.pop("_id", None)
                records.append(doc)
            return records
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving all history: {exc}") from exc

    def get_history_by_plate(self, license_plate: str) -> List[Dict[str, Any]]:
        """
        Retrieves all historical transactions for a specific license plate.

        Args:
            license_plate (str): Vehicle license plate.

        Returns:
            List[Dict[str, Any]]: List of matching records.
        """
        if not license_plate or not isinstance(license_plate, str):
            raise ValueError("license_plate must be a non-empty string.")

        normalized_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        try:
            cursor = self.history_col.find({"license_plate": normalized_plate}).sort("timestamp", -1)
            records: List[Dict[str, Any]] = []
            for doc in cursor:
                doc.pop("_id", None)
                records.append(doc)
            return records
        except PyMongoError as exc:
            raise RuntimeError(f"Database error retrieving history for '{license_plate}': {exc}") from exc

    def delete_history_by_id(self, history_id: str) -> bool:
        """
        Deletes a specific history record by ID.

        Args:
            history_id (str): Unique history record ID.

        Returns:
            bool: True if deleted, False if not found.
        """
        if not history_id or not isinstance(history_id, str):
            raise ValueError("history_id must be a non-empty string.")

        try:
            res = self.history_col.delete_one({"history_id": history_id.strip().upper()})
            return res.deleted_count > 0
        except PyMongoError as exc:
            raise RuntimeError(f"Database error deleting history '{history_id}': {exc}") from exc
