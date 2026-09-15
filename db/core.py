"""
db/core.py — accès Postgres.

`with get_conn() as conn:` emprunte une connexion au pool, valide (ou annule)
la transaction en sortie, puis rend la connexion au pool.
"""
import threading
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS, DB_POOL_MAX

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """Pool créé à la première requête : importer ce module ne doit pas
    exiger une base joignable (tests, outillage)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=DB_POOL_MAX,
                    host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                    user=DB_USER, password=DB_PASS,
                    cursor_factory=RealDictCursor,
                )
    return _pool


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_pool() -> None:
    """Fermeture propre à l'arrêt de l'application."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
