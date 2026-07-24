"""
sapt.ai.usage
Local AI usage accounting and optional monthly budget enforcement.
"""

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sapt.utils.constants import USAGE_DB
from sapt.utils.system import ensure_directories


@dataclass
class BudgetDecision:
    """Result of checking whether another AI call is allowed."""

    allowed: bool
    message: str = ""
    projected_spend: float = 0.0
    budget: float = 0.0


class UsageTracker:
    """SQLite-backed monthly AI request accounting."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or USAGE_DB
        ensure_directories()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    month TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    command TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    estimated_cost REAL NOT NULL DEFAULT 0
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    @staticmethod
    def current_month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def record(
        self,
        provider: str,
        model: str,
        command: str,
        user_input: str,
        success: bool,
        estimated_cost: float = 0.0,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage (
                    created_at, month, provider, model, command,
                    user_input, success, estimated_cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    self.current_month(),
                    provider or "unknown",
                    model or "unknown",
                    command,
                    user_input[:200],
                    1 if success else 0,
                    max(0.0, float(estimated_cost or 0.0)),
                ),
            )

    def monthly_summary(self, month: str | None = None) -> dict:
        month = month or self.current_month()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(success), 0), COALESCE(SUM(estimated_cost), 0)
                FROM usage WHERE month = ?
                """,
                (month,),
            ).fetchone()
            by_provider = conn.execute(
                """
                SELECT provider, COUNT(*), COALESCE(SUM(estimated_cost), 0)
                FROM usage WHERE month = ?
                GROUP BY provider
                ORDER BY provider
                """,
                (month,),
            ).fetchall()

        calls, successes, spend = row
        return {
            "month": month,
            "calls": int(calls or 0),
            "successes": int(successes or 0),
            "failures": int(calls or 0) - int(successes or 0),
            "estimated_spend_usd": round(float(spend or 0.0), 6),
            "by_provider": {
                provider: {
                    "calls": int(count),
                    "estimated_spend_usd": round(float(cost), 6),
                }
                for provider, count, cost in by_provider
            },
        }

    def check_budget(self, budget_usd: float, next_cost: float = 0.0) -> BudgetDecision:
        budget = float(budget_usd or 0.0)
        next_cost = max(0.0, float(next_cost or 0.0))
        if budget <= 0:
            return BudgetDecision(allowed=True)

        current = self.monthly_summary()["estimated_spend_usd"]
        projected = current + next_cost
        if projected > budget:
            return BudgetDecision(
                allowed=False,
                message=(
                    f"Monthly AI budget would be exceeded "
                    f"(${projected:.4f} projected / ${budget:.4f} budget)."
                ),
                projected_spend=projected,
                budget=budget,
            )
        return BudgetDecision(
            allowed=True,
            projected_spend=projected,
            budget=budget,
        )
