"""Database access layer supporting MongoDB with in-memory fallback for local testing."""

import logging
from typing import Optional, Dict, Any, List
import uuid
from datetime import datetime

from services.product_service.app.core.config import MONGODB_URL, MONGODB_DB_NAME

logger = logging.getLogger("product_service.database")

# In-memory store fallback if MongoDB is not running locally
_in_memory_products: Dict[str, Dict[str, Any]] = {}
_use_memory_fallback = False
_mongo_client = None
_db = None


async def init_db() -> None:
    """Attempt connection to MongoDB; fallback to in-memory store if unavailable."""
    global _mongo_client, _db, _use_memory_fallback
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=2000)
        # Verify connection
        await client.admin.command("ping")
        _mongo_client = client
        _db = _mongo_client[MONGODB_DB_NAME]
        _use_memory_fallback = False
        logger.info(f"Connected to MongoDB database '{MONGODB_DB_NAME}' successfully.")
    except Exception as exc:
        _use_memory_fallback = True
        logger.warning(
            f"MongoDB connection failed ({exc}). Falling back to local in-memory storage for rapid development."
        )


async def close_db() -> None:
    """Close MongoDB connection pool."""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        logger.info("MongoDB connection closed.")


class ProductRepository:
    """Data access repository for product catalog and inventory."""

    @staticmethod
    async def list_products(limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        if not _use_memory_fallback and _db is not None:
            cursor = _db.products.find({}).skip(skip).limit(limit)
            return [doc async for doc in cursor]
        return list(_in_memory_products.values())[skip : skip + limit]

    @staticmethod
    async def get_by_id(product_id: str) -> Optional[Dict[str, Any]]:
        if not _use_memory_fallback and _db is not None:
            return await _db.products.find_one({"id": product_id})
        return _in_memory_products.get(product_id)

    @staticmethod
    async def create(data: Dict[str, Any]) -> Dict[str, Any]:
        product_id = data.get("id") or str(uuid.uuid4())
        record = {
            "id": product_id,
            "name": data["name"],
            "description": data.get("description"),
            "price": float(data["price"]),
            "stock_quantity": int(data["stock_quantity"]),
            "reserved_quantity": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        if not _use_memory_fallback and _db is not None:
            await _db.products.insert_one(record)
        else:
            _in_memory_products[product_id] = record

        return record

    @staticmethod
    async def reserve_stock(product_id: str, quantity: int) -> bool:
        """Atomically reserve stock: decrement stock_quantity, increment reserved_quantity."""
        if not _use_memory_fallback and _db is not None:
            result = await _db.products.update_one(
                {"id": product_id, "stock_quantity": {"$gte": quantity}},
                {
                    "$inc": {
                        "stock_quantity": -quantity,
                        "reserved_quantity": quantity,
                    },
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
            return result.modified_count > 0
        else:
            product = _in_memory_products.get(product_id)
            if product and product["stock_quantity"] >= quantity:
                product["stock_quantity"] -= quantity
                product["reserved_quantity"] += quantity
                product["updated_at"] = datetime.utcnow()
                return True
            return False

    @staticmethod
    async def release_reserved_stock(product_id: str, quantity: int) -> None:
        """Rollback stock (compensating action): decrement reserved, increment stock."""
        if not _use_memory_fallback and _db is not None:
            await _db.products.update_one(
                {"id": product_id},
                {
                    "$inc": {
                        "stock_quantity": quantity,
                        "reserved_quantity": -quantity,
                    },
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
        else:
            product = _in_memory_products.get(product_id)
            if product:
                product["stock_quantity"] += quantity
                product["reserved_quantity"] = max(0, product["reserved_quantity"] - quantity)
                product["updated_at"] = datetime.utcnow()
