"""
Test Scheduler - Automated test execution scheduling

Provides scheduling capabilities for pyATS tests:
- Interval-based scheduling (every N minutes/hours)
- Cron-style scheduling (specific times)
- Event-triggered tests (on config change)
- Results storage and notification
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import logging
import json
from pathlib import Path

logger = logging.getLogger("pyATS_Tests.scheduler")


class ScheduleType(Enum):
    """Types of test schedules"""
    INTERVAL = "interval"     # Every N minutes/hours
    CRON = "cron"            # Cron-style schedule
    EVENT = "event"          # Triggered by event
    ONCE = "once"            # One-time execution


@dataclass
class TestSchedule:
    """Configuration for a scheduled test run"""
    schedule_id: str
    agent_id: str
    suite_ids: List[str]  # List of test suite IDs to run, empty = all
    schedule_type: ScheduleType
    enabled: bool = True

    # Interval settings (for INTERVAL type)
    interval_minutes: int = 60

    # Cron settings (for CRON type)
    cron_hour: Optional[int] = None
    cron_minute: int = 0
    cron_day_of_week: Optional[str] = None  # "mon,wed,fri" or "*"

    # Event settings (for EVENT type)
    event_trigger: Optional[str] = None  # "config_change", "adjacency_down", etc.

    # Scheduling metadata
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "agent_id": self.agent_id,
            "suite_ids": self.suite_ids,
            "schedule_type": self.schedule_type.value,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "cron_hour": self.cron_hour,
            "cron_minute": self.cron_minute,
            "cron_day_of_week": self.cron_day_of_week,
            "event_trigger": self.event_trigger,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestSchedule":
        return cls(
            schedule_id=data["schedule_id"],
            agent_id=data["agent_id"],
            suite_ids=data.get("suite_ids", []),
            schedule_type=ScheduleType(data.get("schedule_type", "interval")),
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 60),
            cron_hour=data.get("cron_hour"),
            cron_minute=data.get("cron_minute", 0),
            cron_day_of_week=data.get("cron_day_of_week"),
            event_trigger=data.get("event_trigger"),
            last_run=data.get("last_run"),
            next_run=data.get("next_run"),
            run_count=data.get("run_count", 0)
        )


@dataclass
class TestRunResult:
    """Result of a scheduled test run"""
    run_id: str
    schedule_id: str
    agent_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "running"  # running, passed, failed, error
    summary: Dict[str, int] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "summary": self.summary,
            "results": self.results
        }


class TestScheduler:
    """
    Test scheduler for automated test execution

    Features:
    - Background scheduling with asyncio
    - Multiple schedule types (interval, cron, event)
    - Persistent schedule storage
    - Result history tracking
    - Failure notifications
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the test scheduler

        Args:
            storage_path: Path to store schedules and results
        """
        self.storage_path = storage_path or Path.home() / ".asi" / "test_schedules"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._schedules: Dict[str, TestSchedule] = {}
        self._results: Dict[str, List[TestRunResult]] = {}  # agent_id -> results
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._notification_callbacks: List[Callable] = []

        # Load saved schedules
        self._load_schedules()

    def _load_schedules(self) -> None:
        """Load saved schedules from disk"""
        schedule_file = self.storage_path / "schedules.json"
        if schedule_file.exists():
            try:
                with open(schedule_file, 'r') as f:
                    data = json.load(f)
                    for schedule_data in data.get("schedules", []):
                        schedule = TestSchedule.from_dict(schedule_data)
                        self._schedules[schedule.schedule_id] = schedule
                logger.info(f"Loaded {len(self._schedules)} schedules")
            except Exception as e:
                logger.error(f"Failed to load schedules: {e}")

    def _save_schedules(self) -> None:
        """Save schedules to disk"""
        schedule_file = self.storage_path / "schedules.json"
        try:
            with open(schedule_file, 'w') as f:
                json.dump({
                    "schedules": [s.to_dict() for s in self._schedules.values()]
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save schedules: {e}")

    def add_schedule(self, schedule: TestSchedule) -> bool:
        """
        Add a new test schedule

        Args:
            schedule: TestSchedule to add

        Returns:
            True if added successfully
        """
        if schedule.schedule_id in self._schedules:
            logger.warning(f"Schedule {schedule.schedule_id} already exists")
            return False

        self._schedules[schedule.schedule_id] = schedule
        self._save_schedules()

        # Start schedule if scheduler is running
        if self._running and schedule.enabled:
            self._start_schedule_task(schedule)

        logger.info(f"Added schedule {schedule.schedule_id} for agent {schedule.agent_id}")
        return True

    def remove_schedule(self, schedule_id: str) -> bool:
        """
        Remove a test schedule

        Args:
            schedule_id: ID of schedule to remove

        Returns:
            True if removed successfully
        """
        if schedule_id not in self._schedules:
            return False

        # Stop task if running
        if schedule_id in self._tasks:
            self._tasks[schedule_id].cancel()
            del self._tasks[schedule_id]

        del self._schedules[schedule_id]
        self._save_schedules()

        logger.info(f"Removed schedule {schedule_id}")
        return True

    def update_schedule(self, schedule: TestSchedule) -> bool:
        """
        Update an existing schedule

        Args:
            schedule: Updated TestSchedule

        Returns:
            True if updated successfully
        """
        if schedule.schedule_id not in self._schedules:
            return False

        # Stop existing task
        if schedule.schedule_id in self._tasks:
            self._tasks[schedule.schedule_id].cancel()
            del self._tasks[schedule.schedule_id]

        self._schedules[schedule.schedule_id] = schedule
        self._save_schedules()

        # Restart if enabled and scheduler is running
        if self._running and schedule.enabled:
            self._start_schedule_task(schedule)

        logger.info(f"Updated schedule {schedule.schedule_id}")
        return True

    def get_schedule(self, schedule_id: str) -> Optional[TestSchedule]:
        """Get a schedule by ID"""
        return self._schedules.get(schedule_id)

    def list_schedules(self, agent_id: Optional[str] = None) -> List[TestSchedule]:
        """
        List all schedules

        Args:
            agent_id: Optional filter by agent ID

        Returns:
            List of TestSchedule objects
        """
        schedules = list(self._schedules.values())
        if agent_id:
            schedules = [s for s in schedules if s.agent_id == agent_id]
        return schedules

    def get_results(
        self,
        agent_id: str,
        limit: int = 10
    ) -> List[TestRunResult]:
        """
        Get recent test results for an agent

        Args:
            agent_id: Agent ID
            limit: Maximum results to return

        Returns:
            List of TestRunResult objects
        """
        results = self._results.get(agent_id, [])
        return results[-limit:]

    def register_notification_callback(self, callback: Callable) -> None:
        """
        Register a callback for test failure notifications

        Args:
            callback: Async function(agent_id, result) to call on failure
        """
        self._notification_callbacks.append(callback)

    async def start(self) -> None:
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        logger.info("Starting test scheduler")

        # Start all enabled schedules
        for schedule in self._schedules.values():
            if schedule.enabled:
                self._start_schedule_task(schedule)

    async def stop(self) -> None:
        """Stop the scheduler"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping test scheduler")

        # Cancel all tasks
        for task in self._tasks.values():
            task.cancel()

        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()

    def _start_schedule_task(self, schedule: TestSchedule) -> None:
        """Start a background task for a schedule"""
        if schedule.schedule_type == ScheduleType.INTERVAL:
            task = asyncio.create_task(
                self._run_interval_schedule(schedule)
            )
            self._tasks[schedule.schedule_id] = task
        elif schedule.schedule_type == ScheduleType.CRON:
            task = asyncio.create_task(
                self._run_cron_schedule(schedule)
            )
            self._tasks[schedule.schedule_id] = task
        # EVENT type schedules are triggered externally

    async def _run_interval_schedule(self, schedule: TestSchedule) -> None:
        """Run an interval-based schedule"""
        interval_seconds = schedule.interval_minutes * 60

        while self._running and schedule.enabled:
            try:
                # Update next run time
                schedule.next_run = datetime.now().isoformat()
                self._save_schedules()

                # Wait for interval
                await asyncio.sleep(interval_seconds)

                # Run tests
                await self._execute_scheduled_tests(schedule)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in interval schedule {schedule.schedule_id}: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def _run_cron_schedule(self, schedule: TestSchedule) -> None:
        """Run a cron-style schedule"""
        while self._running and schedule.enabled:
            try:
                # Calculate time until next run
                now = datetime.now()
                target_hour = schedule.cron_hour if schedule.cron_hour is not None else now.hour
                target_minute = schedule.cron_minute

                # Create target time for today
                target = now.replace(
                    hour=target_hour,
                    minute=target_minute,
                    second=0,
                    microsecond=0
                )

                # If target time has passed, schedule for tomorrow
                if target <= now:
                    target = target.replace(day=target.day + 1)

                # Check day of week filter
                if schedule.cron_day_of_week and schedule.cron_day_of_week != "*":
                    days = schedule.cron_day_of_week.lower().split(",")
                    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

                    while target.weekday() not in [day_map.get(d.strip(), -1) for d in days]:
                        target = target.replace(day=target.day + 1)

                # Update next run time
                schedule.next_run = target.isoformat()
                self._save_schedules()

                # Wait until target time
                wait_seconds = (target - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                # Run tests
                await self._execute_scheduled_tests(schedule)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cron schedule {schedule.schedule_id}: {e}")
                await asyncio.sleep(60)

    async def trigger_event(self, event_type: str, agent_id: str) -> None:
        """
        Trigger event-based test schedules

        Args:
            event_type: Type of event (e.g., "config_change", "adjacency_down")
            agent_id: Agent that triggered the event
        """
        for schedule in self._schedules.values():
            if (schedule.schedule_type == ScheduleType.EVENT and
                schedule.event_trigger == event_type and
                schedule.agent_id == agent_id and
                schedule.enabled):

                logger.info(f"Event {event_type} triggered schedule {schedule.schedule_id}")
                asyncio.create_task(self._execute_scheduled_tests(schedule))

    async def _execute_scheduled_tests(self, schedule: TestSchedule) -> None:
        """Execute tests for a schedule"""
        from pyATS_Tests import run_all_tests

        run_id = f"{schedule.schedule_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        result = TestRunResult(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            agent_id=schedule.agent_id,
            started_at=datetime.now().isoformat()
        )

        try:
            logger.info(f"Starting scheduled test run {run_id}")

            # Get agent configuration
            # Note: In production, this would load from agent state
            agent_config = await self._get_agent_config(schedule.agent_id)

            if not agent_config:
                result.status = "error"
                result.results = {"error": "Agent not found"}
                return

            # Run tests
            test_results = await run_all_tests(
                agent_config,
                suite_filter=schedule.suite_ids if schedule.suite_ids else None
            )

            # Update result
            result.completed_at = datetime.now().isoformat()
            result.summary = test_results.get("summary", {})
            result.results = test_results

            # Determine overall status
            if result.summary.get("failed", 0) > 0:
                result.status = "failed"
            else:
                result.status = "passed"

            # Update schedule
            schedule.last_run = result.started_at
            schedule.run_count += 1
            self._save_schedules()

            # Store result
            if schedule.agent_id not in self._results:
                self._results[schedule.agent_id] = []
            self._results[schedule.agent_id].append(result)

            # Trim old results (keep last 100)
            if len(self._results[schedule.agent_id]) > 100:
                self._results[schedule.agent_id] = self._results[schedule.agent_id][-100:]

            # Save results to disk
            self._save_results(schedule.agent_id)

            # Notify on failure
            if result.status == "failed":
                await self._notify_failure(schedule.agent_id, result)

            logger.info(f"Completed test run {run_id}: {result.status}")

        except Exception as e:
            result.status = "error"
            result.completed_at = datetime.now().isoformat()
            result.results = {"error": str(e)}
            logger.error(f"Test run {run_id} failed: {e}")

    async def _get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get agent configuration for testing

        In production, this would load from the agent's TOON data
        or query the running agent's state.
        """
        # TODO: Integrate with actual agent state management
        # For now, return a placeholder
        return {
            "id": agent_id,
            "n": f"Agent {agent_id}",
            "r": "1.1.1.1",
            "ifs": [],
            "protos": []
        }

    def _save_results(self, agent_id: str) -> None:
        """Save test results to disk"""
        results_file = self.storage_path / f"results_{agent_id}.json"
        try:
            results = self._results.get(agent_id, [])
            with open(results_file, 'w') as f:
                json.dump({
                    "results": [r.to_dict() for r in results]
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save results for {agent_id}: {e}")

    async def _notify_failure(self, agent_id: str, result: TestRunResult) -> None:
        """Notify registered callbacks of test failure"""
        for callback in self._notification_callbacks:
            try:
                await callback(agent_id, result)
            except Exception as e:
                logger.error(f"Notification callback failed: {e}")


# Global scheduler instance
_scheduler: Optional[TestScheduler] = None


def get_scheduler() -> TestScheduler:
    """Get or create the global test scheduler"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TestScheduler()
    return _scheduler


async def start_scheduler() -> None:
    """Start the global test scheduler"""
    await get_scheduler().start()


async def stop_scheduler() -> None:
    """Stop the global test scheduler"""
    scheduler = get_scheduler()
    await scheduler.stop()
