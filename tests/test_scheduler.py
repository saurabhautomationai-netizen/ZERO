from __future__ import annotations

from datetime import datetime
from zero_core.scheduler import BriefingScheduler, ScheduledJob


def test_scheduled_job_timing_logic():
    job = ScheduledJob(
        name="test_job",
        target_hour=8,
        target_minute=0,
        action=lambda: "Executed Result",
    )

    # Before target hour
    now_early = datetime(2026, 8, 17, 7, 59)
    assert job.is_due(now=now_early) is False

    # At target hour and minute
    now_due = datetime(2026, 8, 17, 8, 0)
    assert job.is_due(now=now_due) is True

    # Execute
    res = job.execute(now=now_due)
    assert res == "Executed Result"
    assert job.last_executed_day == 17

    # Should not be due again on the same day
    assert job.is_due(now=now_due) is False

    # Next day at same hour -> Due again
    next_day = datetime(2026, 8, 18, 8, 5)
    assert job.is_due(now=next_day) is True


def test_briefing_scheduler_runs_due_jobs():
    scheduler = BriefingScheduler(morning_hour=8, morning_minute=0, evening_hour=20, evening_minute=0)
    
    # Check at 8:00 AM
    now_morning = datetime(2026, 8, 17, 8, 0)
    executed = scheduler.check_and_run_due_jobs(now=now_morning)
    assert len(executed) == 1
    assert executed[0][0] == "morning_briefing"
    assert "Daily Executive Briefing" in executed[0][1]


def test_scheduler_disabled_flag():
    scheduler = BriefingScheduler(auto_push_enabled=False)
    now = datetime(2026, 8, 17, 8, 0)
    executed = scheduler.check_and_run_due_jobs(now=now)
    assert len(executed) == 0
