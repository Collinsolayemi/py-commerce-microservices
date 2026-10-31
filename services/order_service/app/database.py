"""Database layer for Order Service with async SQLAlchemy and SQLite fallback."""

import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from services.order_service.app.core.config import DATABASE_URL
from services.order_service.app.models.order import (
    Base,
    OrderModel,
    OrderItemModel,
    OrderStatus,
)

logger = logging.getLogger("order_service.database")

_engine = None
_session_factory = None
_is_fallback = False


async def init_db() -> None:
    """Initialize database connection pool and create tables. Fallbacks to SQLite if Postgres is unavailable."""
    global _engine, _session_factory, _is_fallback

    try:
        # Test connecting to configured PostgreSQL
        logger.info(f"Connecting to primary database...")
        test_engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            connect_args={"timeout": 3},
        )
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        _engine = test_engine
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        _is_fallback = False
        logger.info("Connected to PostgreSQL orders database successfully.")
    except Exception as exc:
        logger.warning(
            f"PostgreSQL connection failed ({exc}). Falling back to local async SQLite for rapid development."
        )
        _is_fallback = True
        _engine = create_async_engine(
            "sqlite+aiosqlite:///./orders_local.db",
            echo=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        logger.info("Initialized local SQLite database fallback.")


async def close_db() -> None:
    """Dispose database engine connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Database engine closed.")


@asynccontextmanager
async def get_db_session():
    """Context manager for obtaining a database session."""
    if not _session_factory:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class OrderRepository:
    """Data access repository for Order operations."""

    @staticmethod
    async def create_order(user_id: str, items_data: List[Dict[str, Any]]) -> OrderModel:
        """Create a new order and line items with PENDING status."""
        total_price = sum(item["quantity"] * item["unit_price"] for item in items_data)

        async with get_db_session() as session:
            order = OrderModel(
                user_id=user_id,
                total_price=round(total_price, 2),
                status=OrderStatus.PENDING.value,
            )
            session.add(order)
            await session.flush()  # populate order.id

            for item in items_data:
                order_item = OrderItemModel(
                    order_id=order.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    price=item["unit_price"],
                )
                session.add(order_item)

            await session.commit()
            
            # Re-query with eager loaded items
            result = await session.execute(
                select(OrderModel)
                .options(selectinload(OrderModel.items))
                .where(OrderModel.id == order.id)
            )
            return result.scalar_one()

    @staticmethod
    async def get_order(order_id: str) -> Optional[OrderModel]:
        """Fetch order by ID with line items."""
        async with get_db_session() as session:
            result = await session.execute(
                select(OrderModel)
                .options(selectinload(OrderModel.items))
                .where(OrderModel.id == order_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_orders(user_id: Optional[str] = None, skip: int = 0, limit: int = 50) -> List[OrderModel]:
        """List orders with optional user filtering and pagination."""
        async with get_db_session() as session:
            query = select(OrderModel).options(selectinload(OrderModel.items)).offset(skip).limit(limit)
            if user_id:
                query = query.where(OrderModel.user_id == user_id)
            result = await session.execute(query)
            return list(result.scalars().all())

    @staticmethod
    async def update_status(order_id: str, new_status: OrderStatus) -> Optional[OrderModel]:
        """Update the status of an existing order."""
        async with get_db_session() as session:
            result = await session.execute(
                select(OrderModel)
                .options(selectinload(OrderModel.items))
                .where(OrderModel.id == order_id)
            )
            order = result.scalar_one_or_none()
            if not order:
                return None

            order.status = new_status.value if isinstance(new_status, OrderStatus) else new_status
            await session.commit()
            await session.refresh(order)
            return order
