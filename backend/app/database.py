"""数据库连接与会话管理。

使用 SQLAlchemy 异步模式，生产环境用 asyncpg（PostgreSQL），测试用 aiosqlite。
测试环境通过 DATABASE_URL 环境变量覆盖为 SQLite 内存库。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# 异步引擎 —— PostgreSQL 自动管理连接池，SQLite 仅单连接
_engine_kwargs = {"echo": False}
if settings.DATABASE_URL.startswith("postgresql"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# 会话工厂
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：为每个请求提供独立的数据库会话。"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
