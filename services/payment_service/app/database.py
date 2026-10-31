"""Database layer for Payment Service with async SQLAlchemy and SQLite fallback."""

import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from services.payment_service.app.core.config import DATABASE_URL
from services.payment_service.app.models.payment import (
    Base,
    PaymentTransactionModel,
    IdempotencyKeyModel,
    PaymentStatus,
    IdempotencyStatus,
)

logger = logging.getLogger("payment_service.database")

_engine = None
_session_factory = None
_is_fallback = False


async def init_db() -> None:
    """Initialize database connection pool and create tables. Fallbacks to SQLite if Postgres is unavailable."""
    global _engine, _session_factory, _is_fallback

    try:
        logger.info("Connecting to primary payment database...")
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
        logger.info("Connected to PostgreSQL payments database successfully.")
    except Exception as exc:
        logger.warning(
            f"PostgreSQL connection failed ({exc}). Falling back to local async SQLite for rapid development."
        )
        _is_fallback = True
        _engine = create_async_engine(
            "sqlite+aiosqlite:///./payments_local.db",
            echo=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        logger.info("Initialized local SQLite payments database fallback.")


async def close_db() -> None:
    """Dispose database engine connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Payment database engine closed.")


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


class PaymentRepository:
    """Data access repository for payments and idempotency enforcement."""

    @staticmethod
    async def get_idempotency_record(key: str) -> Optional[IdempotencyKeyModel]:
        """Check if an idempotency key already exists."""
        async with get_db_session() as session:
            result = await session.execute(
                select(IdempotencyKeyModel).where(IdempotencyKeyModel.key == key)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def save_idempotency_key(key: str, status: IdempotencyStatus = IdempotencyStatus.PROCESSING) -> IdempotencyKeyModel:
        """Register an idempotency key in processing status."""
        async with get_db_session() as session:
            record = IdempotencyKeyModel(
                key=key,
                status=status.value if isinstance(status, IdempotencyStatus) else status,
                created_at=datetime.utcnow(),
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    @staticmethod
    async def update_idempotency_result(
        key: str,
        status: IdempotencyStatus,
        response_payload: Optional[str] = None,
    ) -> Optional[IdempotencyKeyModel]:
        """Update idempotency key with completed result or failure."""
        async with get_db_session() as session:
            result = await session.execute(
                select(IdempotencyKeyModel).where(IdempotencyKeyModel.key == key)
            )
            record = result.scalar_one_or_none()
            if not record:
                return None

            record.status = status.value if isinstance(status, IdempotencyStatus) else status
            record.response_payload = response_payload
            record.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(record)
            return record

    @staticmethod
    async def create_transaction(
        order_id: str,
        user_id: str,
        amount: float,
        status: PaymentStatus,
        reason: Optional[str] = None,
    ) -> PaymentTransactionModel:
        """Record a completed or failed payment transaction."""
        async with get_db_session() as session:
            transaction = PaymentTransactionModel(
                order_id=order_id,
                user_id=user_id,
                amount=round(amount, 2),
                status=status.value if isinstance(status, PaymentStatus) else status,
                reason=reason,
                created_at=datetime.utcnow(),
            )
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            return transaction

    @staticmethod
    async def get_by_id(payment_id: str) -> Optional[PaymentTransactionModel]:
        """Fetch transaction by ID."""
        async with get_db_session() as session:
            result = await session.execute(
                select(PaymentTransactionModel).where(PaymentTransactionModel.id == payment_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_order_id(order_id: str) -> Optional[PaymentTransactionModel]:
        """Fetch transaction by order ID."""
        async with get_db_session() as session:
            result = await session.execute(
                select(PaymentTransactionModel).where(PaymentTransactionModel.order_id == order_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_transactions(
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[PaymentTransactionModel]:
        """List transactions with optional user filter."""
        async with get_db_session() as session:
            query = select(PaymentTransactionModel).offset(skip).limit(limit)
            if user_id:
                query = query.where(PaymentTransactionModel.user_id == user_id)
            result = await session.execute(query)
            return list(result.scalars().all())
