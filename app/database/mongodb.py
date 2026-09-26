from pymongo import MongoClient
from pymongo.collection import Collection
from core.config import settings

client: MongoClient | None = None


def get_database():
    """Return the configured database instance. Raises RuntimeError if not yet initialized."""
    if client is None:
        raise RuntimeError("MongoDB client is not initialized. Call init_mongodb() first.")
    return client[settings.DATABASE_NAME]


def get_collection() -> Collection:
    """Return the resume collection from the configured database."""
    db = get_database()
    return db[settings.RESUME_COLLECTION]


def init_mongodb():
    """Initialize the global MongoDB client from settings. Safe to call multiple times."""
    global client
    if client is None:
        client = MongoClient(settings.MONGODB_URI)


def close_mongodb():
    """Close the MongoDB connection and reset the global client."""
    global client
    if client is not None:
        client.close()
        client = None
