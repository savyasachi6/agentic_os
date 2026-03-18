"""
Command Store: DB-backed CRUD for lanes and commands.
Uses the existing memory.db connection pool.
"""

import uuid
import json
from typing import Optional, List
from datetime import datetime, timezone

from agent_memory.db import get_db_connection
from .models import (
    Lane, Command, CommandStatus, CommandType, RiskLevel,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommandStore:
    """Postgres-backed lane and command operations."""

    # ------------------------------------------------------------------
    # Lanes
    # ------------------------------------------------------------------
    def create_lane(
        self,
        session_id: str,
        name: str = "default",
        risk_level: RiskLevel = RiskLevel.NORMAL,
    ) -> Lane:
        """Create a new lane for a session."""
        lane_id = f"lane-{uuid.uuid4().hex[:12]}"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lanes (id, session_id, name, risk_level)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, session_id, name, risk_level, is_active, created_at;
                    """,
                    (lane_id, session_id, name, risk_level.value),
                )
                row = cur.fetchone()
            conn.commit()
        return Lane(
            id=row[0], session_id=row[1], name=row[2],
            risk_level=RiskLevel(row[3]), is_active=row[4], created_at=row[5],
        )

    def get_lane(self, lane_id: str) -> Optional[Lane]:
        """Fetch a lane by ID."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, session_id, name, risk_level, is_active, created_at FROM lanes WHERE id = %s;",
                    (lane_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return Lane(
            id=row[0], session_id=row[1], name=row[2],
            risk_level=RiskLevel(row[3]), is_active=row[4], created_at=row[5],
        )

    def get_lanes_for_session(self, session_id: str) -> List[Lane]:
        """Return all lanes belonging to a session."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, session_id, name, risk_level, is_active, created_at "
                    "FROM lanes WHERE session_id = %s ORDER BY created_at;",
                    (session_id,),
                )
                rows = cur.fetchall()
        return [
            Lane(id=r[0], session_id=r[1], name=r[2],
                 risk_level=RiskLevel(r[3]), is_active=r[4], created_at=r[5])
            for r in rows
        ]

    def deactivate_lane(self, lane_id: str):
        """Mark a lane as inactive (soft-close)."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE lanes SET is_active = FALSE WHERE id = %s;", (lane_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def enqueue(
        self,
        lane_id: str,
        cmd_type: CommandType,
        payload: dict,
        tool_name: Optional[str] = None,
        sandbox_id: Optional[str] = None,
    ) -> Command:
        """Append a command to a lane. Auto-increments seq."""
        cmd_id = f"cmd-{uuid.uuid4().hex[:12]}"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Atomically get next seq number
                cur.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM commands WHERE lane_id = %s;",
                    (lane_id,),
                )
                next_seq = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO commands
                        (id, lane_id, seq, status, cmd_type, tool_name, payload, sandbox_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, lane_id, seq, status, cmd_type, tool_name,
                              payload, result, error, sandbox_id,
                              created_at, started_at, finished_at;
                    """,
                    (
                        cmd_id, lane_id, next_seq,
                        CommandStatus.PENDING.value, cmd_type.value,
                        tool_name, json.dumps(payload), sandbox_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return self._row_to_command(row)

    def claim_next(self, lane_id: str) -> Optional[Command]:
        """
        Atomically claim the next pending command in a lane.
        Uses FOR UPDATE SKIP LOCKED to support concurrent runners.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commands
                    SET status = %s, started_at = NOW()
                    WHERE id = (
                        SELECT id FROM commands
                        WHERE lane_id = %s AND status = %s
                        ORDER BY seq ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, lane_id, seq, status, cmd_type, tool_name,
                              payload, result, error, sandbox_id,
                              created_at, started_at, finished_at;
                    """,
                    (CommandStatus.RUNNING.value, lane_id, CommandStatus.PENDING.value),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            return None
        return self._row_to_command(row)

    def complete(self, command_id: str, result: dict):
        """Mark a command as done with its result."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commands
                    SET status = %s, result = %s, finished_at = NOW()
                    WHERE id = %s;
                    """,
                    (CommandStatus.DONE.value, json.dumps(result), command_id),
                )
            conn.commit()

    def fail(self, command_id: str, error: str):
        """Mark a command as failed with error detail."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commands
                    SET status = %s, error = %s, finished_at = NOW()
                    WHERE id = %s;
                    """,
                    (CommandStatus.FAILED.value, error, command_id),
                )
            conn.commit()

    def cancel_pending(self, lane_id: str) -> int:
        """Cancel all pending commands in a lane. Returns count cancelled."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commands
                    SET status = %s, finished_at = NOW()
                    WHERE lane_id = %s AND status = %s;
                    """,
                    (CommandStatus.CANCELLED.value, lane_id, CommandStatus.PENDING.value),
                )
                count = cur.rowcount
            conn.commit()
        return count

    def get_history(self, lane_id: str, limit: int = 50) -> List[Command]:
        """Return completed commands for a lane in execution order."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, lane_id, seq, status, cmd_type, tool_name,
                           payload, result, error, sandbox_id,
                           created_at, started_at, finished_at
                    FROM commands
                    WHERE lane_id = %s AND status IN (%s, %s)
                    ORDER BY seq ASC
                    LIMIT %s;
                    """,
                    (lane_id, CommandStatus.DONE.value, CommandStatus.FAILED.value, limit),
                )
                rows = cur.fetchall()
        return [self._row_to_command(r) for r in rows]

    def get_command(self, command_id: str) -> Optional[Command]:
        """Fetch a single command by ID."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, lane_id, seq, status, cmd_type, tool_name,
                           payload, result, error, sandbox_id,
                           created_at, started_at, finished_at
                    FROM commands WHERE id = %s;
                    """,
                    (command_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._row_to_command(row)

    def get_lane_status(self, lane_id: str) -> dict:
        """Return a summary of command counts by status for a lane."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*) FROM commands
                    WHERE lane_id = %s GROUP BY status;
                    """,
                    (lane_id,),
                )
                rows = cur.fetchall()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_command(row) -> Command:
        """Convert a DB row tuple to a Command model."""
        payload = row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {}
        result = row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else None
        return Command(
            id=row[0],
            lane_id=row[1],
            seq=row[2],
            status=CommandStatus(row[3]),
            cmd_type=CommandType(row[4]),
            tool_name=row[5],
            payload=payload,
            result=result,
            error=row[8],
            sandbox_id=row[9],
            created_at=row[10],
            started_at=row[11],
            finished_at=row[12],
        )
