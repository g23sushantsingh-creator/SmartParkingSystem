"""
Database package for Smart Parking Management System.
"""

from database.repository import ParkingRepository


def __getattr__(name: str):
    """
    Lazy loader for live MongoDB connection objects to allow offline unit tests
    and test runners to operate without requiring active DNS/network access.
    """
    if name in ("client", "db", "test_connection"):
        from database import mongodb
        return getattr(mongodb, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["client", "db", "test_connection", "ParkingRepository"]
