"""Storage layer. SQLite today; the SignalRepository interface is what the pipeline
depends on, so a Postgres implementation can be dropped in later."""

from .db import SignalRepository, init_db

__all__ = ["SignalRepository", "init_db"]
