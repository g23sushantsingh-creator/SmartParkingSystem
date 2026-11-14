"""
Parking Slot Model for Smart Parking Management System.

Represents an individual physical parking space in the facility.
Handles slot allocation, vehicle departure, and MongoDB serialization.
"""

from typing import Optional, Dict, Any
from models.vehicle import Vehicle


class ParkingSlot:
    """
    Represents an individual parking slot in the facility.

    Attributes:
        slot_id (str): Unique slot identifier (e.g., 'F1-S01').
        floor (int): The floor number where this slot is located (positive integer).
        slot_type (str): Type of vehicle accepted ('Car', 'Bike', 'Truck', 'EV').
        is_occupied (bool): Status indicating if a vehicle is currently parked.
        vehicle (Optional[Vehicle]): The parked Vehicle instance, or None if vacant.
    """

    ALLOWED_SLOT_TYPES = {"Car", "Bike", "Truck", "EV"}
    _TYPE_NORMALIZATION = {
        "CAR": "Car",
        "BIKE": "Bike",
        "TRUCK": "Truck",
        "EV": "EV"
    }

    def __init__(
        self,
        slot_id: str,
        floor: int = 1,
        slot_type: str = "Car",
        is_occupied: Optional[bool] = None,
        vehicle: Optional[Vehicle] = None
    ) -> None:
        # Validate slot_id before and after normalization
        if not isinstance(slot_id, str):
            raise TypeError(f"slot_id must be a string, got {type(slot_id).__name__}.")
        normalized_slot_id = slot_id.strip().upper()
        if not normalized_slot_id:
            raise ValueError("slot_id cannot be blank after normalization.")
        self.slot_id = normalized_slot_id

        # Validate that floor is a positive integer
        if isinstance(floor, bool) or not isinstance(floor, int) or floor <= 0:
            raise ValueError(f"floor must be a positive integer (> 0), got {floor}.")
        self.floor = floor

        # Validate slot type
        if not isinstance(slot_type, str):
            raise TypeError(f"slot_type must be a string, got {type(slot_type).__name__}.")
        upper_type = slot_type.strip().upper()
        if upper_type not in self._TYPE_NORMALIZATION:
            raise ValueError(f"Invalid slot type '{slot_type}'. Allowed types: {sorted(list(self.ALLOWED_SLOT_TYPES))}")
        self.slot_type = self._TYPE_NORMALIZATION[upper_type]

        # Validate vehicle type if provided
        if vehicle is not None and not isinstance(vehicle, Vehicle):
            raise TypeError(f"vehicle must be an instance of Vehicle or None, got {type(vehicle).__name__}.")

        # Enforce consistent occupancy state
        if vehicle is None:
            if is_occupied is True:
                raise ValueError("Inconsistent occupancy state: A slot without a vehicle cannot be marked as occupied.")
            self.vehicle = None
            self.is_occupied = False
        else:
            if is_occupied is False:
                raise ValueError("Inconsistent occupancy state: A slot containing a vehicle must always be marked as occupied.")
            self.vehicle = vehicle
            self.is_occupied = True

    def assign_vehicle(self, vehicle: Vehicle) -> None:
        """
        Assigns a vehicle to this slot.

        Args:
            vehicle (Vehicle): The vehicle to be parked.

        Raises:
            ValueError: If the slot is already occupied or vehicle type is incompatible.
            TypeError: If vehicle is not a Vehicle instance.
        """
        if self.is_occupied:
            raise ValueError(f"Slot {self.slot_id} is already occupied by {self.vehicle.license_plate}.")

        if not isinstance(vehicle, Vehicle):
            raise TypeError(f"vehicle must be an instance of Vehicle, got {type(vehicle).__name__}.")

        # Type compatibility check:
        # Direct match allowed, or EV can park in Car slots
        if vehicle.vehicle_type != self.slot_type and not (vehicle.vehicle_type == "EV" and self.slot_type == "Car"):
            raise ValueError(
                f"Incompatible vehicle type: Cannot park a '{vehicle.vehicle_type}' in a '{self.slot_type}' slot."
            )

        self.vehicle = vehicle
        self.is_occupied = True

    def release_vehicle(self) -> Optional[Vehicle]:
        """
        Vacates the parking slot and returns the departing vehicle.

        Returns:
            Optional[Vehicle]: The vehicle that was parked, or None if already vacant.
        """
        departing_vehicle = self.vehicle
        self.vehicle = None
        self.is_occupied = False
        return departing_vehicle

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the ParkingSlot object into a dictionary for MongoDB storage.

        Returns:
            Dict[str, Any]: Dictionary representation of the slot.
        """
        return {
            "slot_id": self.slot_id,
            "floor": self.floor,
            "slot_type": self.slot_type,
            "is_occupied": self.is_occupied,
            "vehicle": self.vehicle.to_dict() if self.vehicle else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParkingSlot":
        """
        Reconstructs a ParkingSlot instance from a dictionary.

        Args:
            data (Dict[str, Any]): Dictionary containing slot details.

        Returns:
            ParkingSlot: Instantiated ParkingSlot object.

        Raises:
            ValueError: If data is empty or required fields are missing/inconsistent.
        """
        if not data or not isinstance(data, dict):
            raise ValueError("Data dictionary must be a non-empty dictionary.")

        if "slot_id" not in data:
            raise ValueError("Missing required field 'slot_id' in slot data.")

        vehicle_data = data.get("vehicle")
        vehicle_obj = Vehicle.from_dict(vehicle_data) if vehicle_data else None

        return cls(
            slot_id=data["slot_id"],
            floor=data.get("floor", 1),
            slot_type=data.get("slot_type", "Car"),
            is_occupied=data.get("is_occupied"),
            vehicle=vehicle_obj
        )

    def __eq__(self, other: Any) -> bool:
        """Equality based on unique slot_id."""
        if isinstance(other, ParkingSlot):
            return self.slot_id == other.slot_id
        return False

    def __hash__(self) -> int:
        return hash(self.slot_id)

    def __repr__(self) -> str:
        status = f"Occupied by {self.vehicle.license_plate}" if self.is_occupied and self.vehicle else "Available"
        return f"ParkingSlot(id='{self.slot_id}', floor={self.floor}, type='{self.slot_type}', status='{status}')"
