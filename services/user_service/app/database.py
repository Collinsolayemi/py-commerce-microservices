"""Database layer for User Service with async SQLAlchemy and SQLite fallback."""

import logging
from typing import Optional, List
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from services.user_service.app.core.config import DATABASE_URL
from services.user_service.app.models.user import Base, UserModel

logger = logging.getLogger("user_service.database")

_engine = None
_session_factory = None
_is_fallback = False


async def init_db() -> None:
    """Initialize database connection pool and create tables. Fallbacks to SQLite if Postgres is unavailable."""
    global _engine, _session_factory, _is_fallback

    try:
        logger.info("Connecting to primary user database...")
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
        logger.info("Connected to PostgreSQL users database successfully.")
    except Exception as exc:
        logger.warning(
            f"PostgreSQL connection failed ({exc}). Falling back to local async SQLite for rapid development."
        )
        _is_fallback = True
        _engine = create_async_engine(
            "sqlite+aiosqlite:///./users_local.db",
            echo=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        logger.info("Initialized local SQLite users database fallback.")


async def close_db() -> None:
    """Dispose database engine connections."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("User database engine closed.")


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


class UserRepository:
    """Data access repository for users and authentication."""

    @staticmethod
    async def create_user(
        email: str,
        hashed_password: str,
        full_name: str,
    ) -> UserModel:
        """Create and persist a new user record."""
        async with get_db_session() as session:
            user = UserModel(
                email=email.lower().strip(),
                hashed_password=hashed_password,
                full_name=full_name.strip(),
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[UserModel]:
        """Fetch user by primary key ID."""
        async with get_db_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(email: str) -> Optional[UserModel]:
        """Fetch user by unique email address."""
        async with get_db_session() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.email == email.lower().strip())
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_users(
        skip: int = 0,
        limit: int = 50,
    ) -> List[UserModel]:
        """List registered users with pagination."""
        async with get_db_session() as session:
            result = await session.execute(
                select(UserModel).offset(skip).limit(limit)
            )
            return list(result.scalars().all())

