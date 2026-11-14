import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get MongoDB connection string
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError(
        "MongoDB connection failed: MONGODB_URI environment variable is missing or empty. "
        "Please check your .env configuration file."
    )

# Connect to MongoDB Atlas with 5-second timeout
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)

# Select database
db = client["smart_parking_db"]


def test_connection() -> bool:
    """
    Pings MongoDB Atlas to verify server connectivity.

    Returns:
        bool: True if connection succeeds, False otherwise.
    """
    try:
        client.admin.command("ping")
        print("Successfully connected to MongoDB Atlas!")
        print("Database: smart_parking_db")
        return True
    except Exception as e:
        print("MongoDB connection failed!")
        print(e)
        return False


if __name__ == "__main__":
    test_connection()
    client.close()
