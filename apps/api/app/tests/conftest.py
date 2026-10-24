"""Shared database fixtures: each test runs inside a rolled-back transaction."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


@pytest.fixture(scope="module")
def engine():
    from app.core.config import settings

    return create_engine(settings.DATABASE_URL, echo=False)


@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def db(engine, tables):
    conn = engine.connect()
    txn = conn.begin()
    session = sessionmaker(bind=conn, expire_on_commit=False)()
    yield session
    session.close()
    txn.rollback()
    conn.close()
