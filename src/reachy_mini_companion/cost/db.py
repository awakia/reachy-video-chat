"""SQLite database for cost tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class CostDatabase:
    """Async SQLite wrapper for session and cost logging."""

    def __init__(self, db_path: str = "data/cost.db"):
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create database and tables if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_sec REAL,
                total_cost_usd REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                input_audio_tokens INTEGER DEFAULT 0,
                output_audio_tokens INTEGER DEFAULT 0,
                input_text_tokens INTEGER DEFAULT 0,
                output_text_tokens INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE VIEW IF NOT EXISTS daily_summary AS
            SELECT
                date(started_at) as day,
                COUNT(*) as session_count,
                ROUND(SUM(duration_sec), 1) as total_duration_sec,
                ROUND(SUM(total_cost_usd), 4) as total_cost_usd
            FROM sessions
            WHERE ended_at IS NOT NULL
            GROUP BY date(started_at);
        """)
        await self._db.commit()
        logger.info(f"Cost database initialized at {self.db_path}")

    async def log_session_start(self) -> int:
        """Log the start of a new session. Returns session ID."""
        if not self._db:
            raise RuntimeError("Database not initialized")

        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            "INSERT INTO sessions (started_at) VALUES (?)", (now,)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def log_session_end(
        self, session_id: int, duration_sec: float, total_cost_usd: float
    ) -> None:
        """Log the end of a session."""
        if not self._db:
            return

        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """UPDATE sessions
               SET ended_at = ?, duration_sec = ?, total_cost_usd = ?
               WHERE id = ?""",
            (now, duration_sec, total_cost_usd, session_id),
        )
        await self._db.commit()

    async def log_usage(
        self,
        session_id: int,
        input_audio_tokens: int = 0,
        output_audio_tokens: int = 0,
        input_text_tokens: int = 0,
        output_text_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Log token usage for a session."""
        if not self._db:
            return

        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO token_usage
               (session_id, timestamp, input_audio_tokens, output_audio_tokens,
                input_text_tokens, output_text_tokens, estimated_cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, now, input_audio_tokens, output_audio_tokens,
                input_text_tokens, output_text_tokens, estimated_cost_usd,
            ),
        )
        await self._db.commit()

    async def get_daily_total(self, date_str: str | None = None) -> float:
        """Get total cost for a given day (default: today).

        Args:
            date_str: Date string in YYYY-MM-DD format. Defaults to today.

        Returns:
            Total cost in USD for the day.
        """
        if not self._db:
            return 0.0

        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        cursor = await self._db.execute(
            """SELECT COALESCE(SUM(total_cost_usd), 0)
               FROM sessions
               WHERE date(started_at) = ? AND ended_at IS NOT NULL""",
            (date_str,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
