"""SQLAlchemy 引擎与 session 工厂。从 .env 读 MySQL 连接配置。"""
from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

logger = logging.getLogger(__name__)


def _build_url(user: str, password: str, host: str, port: str, db: str) -> str:
    pwd = quote_plus(password) if password else ""
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"


def _read_config(prefix: str = "") -> dict:
    """读 DB 配置;prefix 为空时取主账号,prefix='RO_' 时取只读账号。"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "3306"),
        "user": os.getenv(f"DB_{prefix}USER") or os.getenv("DB_USER", "root"),
        "password": os.getenv(f"DB_{prefix}PASSWORD") or os.getenv("DB_PASSWORD", ""),
        "db": os.getenv("DB_NAME", "ai_scraper_db"),
    }


_engine: Engine | None = None
_engine_ro: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        cfg = _read_config()
        url = _build_url(**cfg)
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        logger.info(f"MySQL engine ready: {cfg['host']}:{cfg['port']}/{cfg['db']}")
    return _engine


def get_readonly_engine() -> Engine:
    """SQL 查询页用的只读连接。如果未配置只读账号,降级到主账号。"""
    global _engine_ro
    if _engine_ro is None:
        cfg = _read_config(prefix="RO_")
        # 没配置只读账号时,直接复用主连接
        if not cfg["user"] or cfg["user"] == os.getenv("DB_USER"):
            return get_engine()
        url = _build_url(**cfg)
        _engine_ro = create_engine(
            url, pool_pre_ping=True, pool_recycle=3600, pool_size=2, future=True
        )
        logger.info(f"MySQL read-only engine ready as user '{cfg['user']}'")
    return _engine_ro


@contextmanager
def get_session() -> Session:
    """事务性 session;退出时自动 commit / rollback。"""
    if _SessionLocal is None:
        get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def healthcheck() -> bool:
    """快速检查数据库连接是否可用。"""
    try:
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB healthcheck failed: {e}")
        return False
