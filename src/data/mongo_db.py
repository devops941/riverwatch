"""
MongoDB Integration Module for RiverWatch.
Loads configuration from .env and provides seamless document storage,
synchronization, and connection health status for MongoDB.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import pymongo
from pymongo import MongoClient

# Load .env file
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "riverwatch")
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "mongodb").lower()

_mongo_client: Optional[MongoClient] = None
_mongo_db = None
_is_connected: Optional[bool] = None


def get_mongo_client() -> Optional[MongoClient]:
    global _mongo_client, _is_connected
    if _mongo_client is None:
        try:
            _mongo_client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500,
            )
            # Ping to verify
            _mongo_client.admin.command("ping")
            _is_connected = True
        except Exception:
            _mongo_client = None
            _is_connected = False
    return _mongo_client


def get_mongo_db():
    global _mongo_db
    client = get_mongo_client()
    if client and _is_connected:
        if _mongo_db is None:
            _mongo_db = client[MONGODB_DB_NAME]
        return _mongo_db
    return None


def get_db_status() -> Dict[str, Any]:
    """
    Check active database status (MongoDB vs SQLite fallback).
    """
    client = get_mongo_client()
    connected = _is_connected is True
    return {
        "configured_type": DATABASE_TYPE,
        "mongodb_connected": connected,
        "mongodb_uri": MONGODB_URI.split("@")[-1],  # mask password if any
        "mongodb_database": MONGODB_DB_NAME,
        "active_backend": "MongoDB" if (DATABASE_TYPE == "mongodb" and connected) else "SQLite (Primary/Fallback)",
    }


def sync_records_to_mongo(collection_name: str, documents: List[Dict[str, Any]], key_field: str = "_id"):
    """
    Upsert documents into a MongoDB collection.
    """
    db = get_mongo_db()
    if db is None or not documents:
        return 0

    coll = db[collection_name]
    count = 0
    for doc in documents:
        doc_copy = dict(doc)
        if key_field in doc_copy and doc_copy[key_field] is not None:
            key_val = doc_copy[key_field]
            coll.update_one({key_field: key_val}, {"$set": doc_copy}, upsert=True)
            count += 1
        else:
            coll.insert_one(doc_copy)
            count += 1
    return count
