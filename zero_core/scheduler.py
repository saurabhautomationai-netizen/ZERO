"""Lightweight, zero-dependency cron and recurring job scheduler for ZERO.

Supports:
- Morning Daily Executive Briefing (Default 08:00 local time)
- Evening Daily Operations Summary (Default 20:00 local time)
- Custom interval / cron triggers without requiring external dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ScheduledJob:
    """Represents a recurring scheduled task."""
    name: str
    target_hour: int
    target_minute: int
    action: Callable[[], str]
    last_executed_day: Optional[int] = None
    enabled: bool = True

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """Checks if the job is due for execution at the current time."""
        if not self.enabled:
            return False

        current = now or datetime.now()
        # Same hour and at or past the target minute
        if current.hour == self.target_hour and current.minute >= self.target_minute:
            # Has not executed today yet
            if self.last_executed_day != current.day:
                return True
        return False

    def execute(self, now: Optional[datetime] = None) -> str:
        """Executes the action and marks the job as executed for the day."""
        current = now or datetime.now()
        self.last_executed_day = current.day
        return self.action()


class BriefingScheduler:
    """Manages scheduled morning & evening automated briefing broadcasts."""

    def __init__(
        self,
        morning_hour: int = 8,
        morning_minute: int = 0,
        evening_hour: int = 20,
        evening_minute: int = 0,
        auto_push_enabled: bool = True,
    ):
        # Allow environment overrides
        m_hour = int(os.environ.get("BRIEFING_MORNING_HOUR", str(morning_hour)))
        m_min = int(os.environ.get("BRIEFING_MORNING_MINUTE", str(morning_minute)))
        e_hour = int(os.environ.get("BRIEFING_EVENING_HOUR", str(evening_hour)))
        e_min = int(os.environ.get("BRIEFING_EVENING_MINUTE", str(evening_minute)))
        enabled_val = os.environ.get("BRIEFING_AUTO_PUSH_ENABLED", "true").lower() in ("1", "true", "yes")

        self.jobs: Dict[str, ScheduledJob] = {}
        self.auto_push_enabled = auto_push_enabled and enabled_val

        self._setup_default_jobs(m_hour, m_min, e_hour, e_min)

    def _setup_default_jobs(self, m_hour: int, m_min: int, e_hour: int, e_min: int):
        from zero_core.agents.briefing_agent import DEFAULT_BRIEFING_AGENT

        self.add_job(
            ScheduledJob(
                name="morning_briefing",
                target_hour=m_hour,
                target_minute=m_min,
                action=lambda: DEFAULT_BRIEFING_AGENT.generate_morning_briefing().to_markdown(),
                enabled=self.auto_push_enabled,
            )
        )
        self.add_job(
            ScheduledJob(
                name="evening_briefing",
                target_hour=e_hour,
                target_minute=e_min,
                action=lambda: DEFAULT_BRIEFING_AGENT.generate_morning_briefing().to_markdown(),
                enabled=self.auto_push_enabled,
            )
        )

    def add_job(self, job: ScheduledJob):
        self.jobs[job.name] = job

    def check_and_run_due_jobs(self, now: Optional[datetime] = None) -> List[tuple[str, str]]:
        """Checks all registered jobs and returns list of (job_name, output) for executed jobs."""
        executed = []
        for name, job in self.jobs.items():
            if job.is_due(now=now):
                result = job.execute(now=now)
                executed.append((name, result))
        return executed


# Global singleton instance
DEFAULT_BRIEFING_SCHEDULER = BriefingScheduler()
