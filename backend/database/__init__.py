"""
database package initialization.
Exports MongoDB repository and sets up connections.
"""
from backend.database.mongodb import MongoDBRepository

_db_repository = None

def get_db() -> MongoDBRepository:
    """
    Dependency generator for MongoDB.
    Returns the shared MongoDBRepository instance.
    """
    global _db_repository
    if _db_repository is None:
        _db_repository = MongoDBRepository()
    return _db_repository

__all__ = ["MongoDBRepository", "get_db"]
