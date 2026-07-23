import os

from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


async def _configure_connection(conn) -> None:
    await register_vector_async(conn)


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.environ["SUPABASE_DB_URL"]
        _pool = AsyncConnectionPool(dsn, open=False, configure=_configure_connection, min_size=1, max_size=5)
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
