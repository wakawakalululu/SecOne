from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .domain import AnalysisResult, TaskRecord, TaskStatus, now_iso


class TaskStore:
    def __init__(self, database: Path):
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    workspace TEXT NOT NULL DEFAULT '',
                    input_count INTEGER NOT NULL DEFAULT 0,
                    flag_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)"
            )

    def create(
        self,
        task_id: str,
        title: str,
        mode: str,
        workspace: str,
        input_count: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                    (id, title, mode, status, created_at, workspace, input_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    mode,
                    TaskStatus.RUNNING,
                    now_iso(),
                    workspace,
                    input_count,
                ),
            )

    def update_meta(self, task_id: str, title: str, input_count: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET title = ?, input_count = ? WHERE id = ?",
                (title, input_count, task_id),
            )

    def complete(self, result: AnalysisResult) -> None:
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks SET
                    status = ?, completed_at = ?, flag_count = ?, summary = ?,
                    result_json = ?, error = ''
                WHERE id = ?
                """,
                (
                    result.status,
                    result.completed_at or now_iso(),
                    len(result.flags),
                    result.summary,
                    payload,
                    result.task_id,
                ),
            )

    def fail(self, task_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                (TaskStatus.FAILED, now_iso(), error, task_id),
            )

    def cancel(self, task_id: str, reason: str = "用户取消分析") -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                (TaskStatus.CANCELLED, now_iso(), reason, task_id),
            )

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_result(self, task_id: str) -> AnalysisResult | None:
        record = self.get(task_id)
        if not record or not record.result_json:
            return None
        return AnalysisResult.from_dict(json.loads(record.result_json))

    def list(self, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0)
                        AS completed,
                    COALESCE(SUM(flag_count), 0) AS flags
                FROM tasks
                """
            ).fetchone()
        return {
            "total": int(row["total"]),
            "completed": int(row["completed"]),
            "flags": int(row["flags"]),
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            title=row["title"],
            mode=row["mode"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            workspace=row["workspace"],
            input_count=int(row["input_count"]),
            flag_count=int(row["flag_count"]),
            summary=row["summary"],
            error=row["error"],
            result_json=row["result_json"],
        )
