from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from api.settings import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_engine_kwargs: dict = {"future": True}
if _is_sqlite:
    # FastAPI's sync endpoints run in a worker-thread pool, so multiple
    # threads open connections to the same file concurrently. A single
    # shared connection (StaticPool) was tried to avoid that, but a raw
    # sqlite3 connection is not safe for concurrent *use* from multiple
    # threads even with check_same_thread=False — one thread mid-statement
    # while another commits on the same connection intermittently raised
    # "disk I/O error". The standard fix is the opposite: let each thread
    # have its own pooled connection (SQLAlchemy's default pool), and put
    # SQLite itself in WAL mode with a busy timeout so concurrent
    # readers/writers wait instead of erroring.
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine: Engine = create_engine(settings.database_url, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
