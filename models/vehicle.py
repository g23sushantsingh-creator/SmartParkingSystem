"""
Vehicle Model for Smart Parking Management System.

Represents a vehicle entering or parked in the parking facility.
Provides serialization and deserialization helpers for MongoDB Atlas storage.
"""

from datetime import datetime
from typing import Optional, Dict, Any


class Vehicle:
    """
    Represents a vehicle in the parking management system.

    Attributes:
        license_plate (str): Unique vehicle identifier (normalized to uppercase, no spaces/hyphens).
        vehicle_type (str): Category ('Car', 'Bike', 'Truck', 'EV').
        entry_time (datetime): Timestamp when the vehicle was checked in.
        owner_name (str): Optional name of the driver/owner.
        owner_phone (str): Optional contact number for alerts/billing.
    """

    VALID_TYPES = {"Car", "Bike", "Truck", "EV"}
    _TYPE_NORMALIZATION = {
        "CAR": "Car",
        "BIKE": "Bike",
        "TRUCK": "Truck",
        "EV": "EV"
    }

    def __init__(
        self,
        license_plate: str,
        vehicle_type: str = "Car",
        entry_time: Optional[datetime] = None,
        owner_name: str = "",
        owner_phone: str = ""
    ) -> None:
        if not isinstance(license_plate, str):
            raise TypeError(f"License plate must be a string, got {type(license_plate).__name__}.")

        # Normalize license plate: uppercase, trimmed, internal spaces and hyphens removed
        normalized_plate = license_plate.strip().upper().replace(" ", "").replace("-", "")
        if not normalized_plate:
            raise ValueError("License plate cannot be blank after normalization.")
        self.license_plate = normalized_plate

        # Validate vehicle type: must be a string before calling strip()
        if not isinstance(vehicle_type, str):
            raise TypeError(f"vehicle_type must be a string, got {type(vehicle_type).__name__}.")

        upper_type = vehicle_type.strip().upper()
        if upper_type not in self._TYPE_NORMALIZATION:
            raise ValueError(f"Invalid vehicle type '{vehicle_type}'. Allowed types: {sorted(list(self.VALID_TYPES))}")
        self.vehicle_type = self._TYPE_NORMALIZATION[upper_type]

        # Validate and set entry_time
        if entry_time is not None and not isinstance(entry_time, datetime):
            raise TypeError(f"entry_time must be a datetime instance or None, got {type(entry_time).__name__}.")
        self.entry_time = entry_time if entry_time is not None else datetime.now()

        self.owner_name = owner_name.strip() if isinstance(owner_name, str) else ""
        self.owner_phone = owner_phone.strip() if isinstance(owner_phone, str) else ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the Vehicle object into a dictionary for MongoDB persistence.

        Returns:
            Dict[str, Any]: Dictionary representation of the vehicle.
        """
        return {
            "license_plate": self.license_plate,
            "vehicle_type": self.vehicle_type,
            "entry_time": self.entry_time.isoformat() if isinstance(self.entry_time, datetime) else self.entry_time,
            "owner_name": self.owner_name,
            "owner_phone": self.owner_phone
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Vehicle":
        """
        Reconstructs a Vehicle instance from a dictionary (e.g. retrieved from MongoDB).

        Args:
            data (Dict[str, Any]): Dictionary containing vehicle attributes.

        Returns:
            Vehicle: Instantiated Vehicle object.

        Raises:
            ValueError: If data is empty, required fields are missing, or entry_time is invalid.
        """
        if not data or not isinstance(data, dict):
            raise ValueError("Data dictionary must be a non-empty dictionary.")

        if "license_plate" not in data:
            raise ValueError("Missing required field 'license_plate' in vehicle data.")

        entry_time_val = data.get("entry_time")
        if entry_time_val is not None:
            if isinstance(entry_time_val, str):
                try:
                    entry_time_val = datetime.fromisoformat(entry_time_val)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid entry_time string format: '{entry_time_val}'. Expected ISO format."
                    ) from exc
            elif isinstance(entry_time_val, datetime):
                pass
            else:
                raise ValueError(
                    f"Invalid entry_time type: {type(entry_time_val).__name__}. Expected ISO string or datetime."
                )

        return cls(
            license_plate=data["license_plate"],
            vehicle_type=data.get("vehicle_type", "Car"),
            entry_time=entry_time_val,
            owner_name=data.get("owner_name", ""),
            owner_phone=data.get("owner_phone", "")
        )

    def __eq__(self, other: Any) -> bool:
        """Equality based on unique normalized license plate."""
        if isinstance(other, Vehicle):
            return self.license_plate == other.license_plate
        return False

    def __hash__(self) -> int:
        """Hash based on normalized license plate for DSA compatibility."""
        return hash(self.license_plate)

    def __repr__(self) -> str:
        return (
            f"Vehicle(plate='{self.license_plate}', type='{self.vehicle_type}', "
            f"entry='{self.entry_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(self.entry_time, datetime) else self.entry_time}', "
            f"owner='{self.owner_name}')"
        )
