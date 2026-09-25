"""Cross-dialect column types.

docs/03-DATA-MODEL.md section 5.1 requires that the SQLite/Postgres difference
live only in this dialect layer, never as branches in engine or API code. Each
type here picks a native Postgres representation (JSONB, ARRAY) and falls back
to a JSON-encoded TEXT column on SQLite, transparently to callers.
"""
from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import String, TypeDecorator


def big_serial() -> BigInteger:
    """BIGSERIAL-equivalent primary key type (docs/03 section 5.1): BigInteger
    on Postgres, plain INTEGER on SQLite — SQLite only auto-assigns rowid
    (and therefore autoincrement) for a column typed exactly INTEGER, not
    BIGINT, so a literal BigInteger primary key silently fails to
    autoincrement there."""
    return BigInteger().with_variant(Integer(), "sqlite")


class JSONBType(TypeDecorator):
    """JSONB on Postgres, JSON-over-TEXT on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class StringArrayType(TypeDecorator):
    """TEXT[] on Postgres, a JSON array of strings on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(String()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        return list(value)


class SmallIntArrayType(TypeDecorator):
    """SMALLINT[] on Postgres, a JSON array of ints on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        from sqlalchemy import SmallInteger

        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(SmallInteger()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        return list(value)
