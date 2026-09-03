"""Async SQLAlchemy engine/session."""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..config import get_settings


def make_engine():
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


def make_sessionmaker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)
