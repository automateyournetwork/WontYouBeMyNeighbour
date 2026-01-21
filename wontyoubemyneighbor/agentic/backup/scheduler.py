"""
Backup Scheduler Module - Automated backup scheduling

Provides:
- Scheduled backup jobs
- Retention policies
- Backup notifications
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger("BackupScheduler")


class ScheduleFrequency(str, Enum):
    """Backup schedule frequencies"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


@dataclass
class BackupSchedule:
    """
    A backup schedule definition

    Attributes:
        id: Schedule identifier
        name: Schedule name
        frequency: How often to run
        enabled: Whether schedule is active
        backup_type: Type of backup to create
        network_id: Network to backup (optional)
        retention_count: Number of backups to keep
        retention_days: Keep backups for this many days
        last_run: Last execution time
        next_run: Next scheduled run
        run_count: Total runs
        success_count: Successful runs
        tags: Tags to apply to backups
    """
    id: str
    name: str
    frequency: ScheduleFrequency
    enabled: bool = True
    backup_type: str = "full"
    network_id: Optional[str] = None
    retention_count: int = 10
    retention_days: int = 30
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    tags: List[str] = field(default_factory=list)
    custom_interval_hours: int = 24

    @property
    def success_rate(self) -> float:
        if self.run_count == 0:
            return 100.0
        return (self.success_count / self.run_count) * 100

    def calculate_next_run(self) -> datetime:
        """Calculate next run time based on frequency"""
        now = datetime.now()

        if self.frequency == ScheduleFrequency.HOURLY:
            return now + timedelta(hours=1)
        elif self.frequency == ScheduleFrequency.DAILY:
            return now + timedelta(days=1)
        elif self.frequency == ScheduleFrequency.WEEKLY:
            return now + timedelta(weeks=1)
        elif self.frequency == ScheduleFrequency.MONTHLY:
            return now + timedelta(days=30)
        elif self.frequency == ScheduleFrequency.CUSTOM:
            return now + timedelta(hours=self.custom_interval_hours)
        else:
            return now + timedelta(days=1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "frequency": self.frequency.value,
            "enabled": self.enabled,
            "backup_type": self.backup_type,
            "network_id": self.network_id,
            "retention_count": self.retention_count,
            "retention_days": self.retention_days,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 2),
            "tags": self.tags,
            "custom_interval_hours": self.custom_interval_hours
        }


@dataclass
class ScheduledRun:
    """Record of a scheduled backup run"""
    schedule_id: str
    backup_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "backup_id": self.backup_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "error_message": self.error_message
        }


class BackupScheduler:
    """
    Manages scheduled backup operations
    """

    def __init__(self):
        """Initialize scheduler"""
        self._schedules: Dict[str, BackupSchedule] = {}
        self._schedule_counter = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._run_history: List[ScheduledRun] = []
        self._callbacks: List[Callable] = []

    async def start(self):
        """Start the scheduler"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Backup scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Backup scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                now = datetime.now()

                # Check each enabled schedule
                for schedule in self._schedules.values():
                    if not schedule.enabled:
                        continue

                    if schedule.next_run and now >= schedule.next_run:
                        await self._execute_schedule(schedule)

                # Check every minute
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)

    async def _execute_schedule(self, schedule: BackupSchedule):
        """Execute a scheduled backup"""
        from .backup import get_backup_manager, BackupType

        logger.info(f"Executing scheduled backup: {schedule.name}")
        run = ScheduledRun(
            schedule_id=schedule.id,
            backup_id=None,
            started_at=datetime.now()
        )

        try:
            backup_manager = get_backup_manager()

            # Get content to backup
            content = self._get_backup_content(schedule.network_id)

            # Determine backup type
            try:
                backup_type = BackupType(schedule.backup_type)
            except ValueError:
                backup_type = BackupType.FULL

            # Create backup
            backup = backup_manager.create_backup(
                name=f"Scheduled: {schedule.name} ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
                backup_type=backup_type,
                content=content,
                created_by="scheduler",
                tags=schedule.tags + ["scheduled", schedule.frequency.value]
            )

            run.backup_id = backup.id
            run.success = backup.is_complete
            if not backup.is_complete:
                run.error_message = backup.error_message

            # Apply retention policy
            self._apply_retention_policy(schedule)

            # Update schedule
            schedule.last_run = datetime.now()
            schedule.next_run = schedule.calculate_next_run()
            schedule.run_count += 1
            if run.success:
                schedule.success_count += 1

            logger.info(f"Scheduled backup completed: {backup.id}")

        except Exception as e:
            run.success = False
            run.error_message = str(e)
            logger.error(f"Scheduled backup failed: {e}")

            schedule.last_run = datetime.now()
            schedule.next_run = schedule.calculate_next_run()
            schedule.run_count += 1

        run.completed_at = datetime.now()
        self._run_history.append(run)

        # Trim history
        if len(self._run_history) > 1000:
            self._run_history = self._run_history[-500:]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(schedule, run)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _get_backup_content(self, network_id: Optional[str]) -> Dict[str, Any]:
        """Get content to backup"""
        # Placeholder - in production would gather actual state
        return {
            "agents": [],
            "network": {"id": network_id} if network_id else {},
            "protocols": [],
            "routes": [],
            "config": {},
            "timestamp": datetime.now().isoformat()
        }

    def _apply_retention_policy(self, schedule: BackupSchedule):
        """Apply retention policy to scheduled backups"""
        from .backup import get_backup_manager

        backup_manager = get_backup_manager()

        # Get backups for this schedule
        backups = backup_manager.list_backups(
            tags=["scheduled", schedule.id]
        )

        if not backups:
            return

        # Sort by date (newest first)
        backups.sort(key=lambda b: b.created_at, reverse=True)

        # Keep by count
        protected = set(b.id for b in backups[:schedule.retention_count])

        # Delete old backups
        cutoff_date = datetime.now() - timedelta(days=schedule.retention_days)
        for backup in backups:
            if backup.id in protected:
                continue
            if backup.created_at < cutoff_date:
                backup_manager.delete_backup(backup.id)
                logger.info(f"Retention policy: deleted backup {backup.id}")

    def create_schedule(
        self,
        name: str,
        frequency: ScheduleFrequency,
        backup_type: str = "full",
        network_id: Optional[str] = None,
        retention_count: int = 10,
        retention_days: int = 30,
        tags: Optional[List[str]] = None,
        custom_interval_hours: int = 24,
        start_immediately: bool = False
    ) -> BackupSchedule:
        """
        Create a new backup schedule

        Args:
            name: Schedule name
            frequency: How often to run
            backup_type: Type of backup
            network_id: Network to backup
            retention_count: Backups to keep
            retention_days: Days to keep backups
            tags: Tags for backups
            custom_interval_hours: Hours for custom frequency
            start_immediately: Run first backup immediately

        Returns:
            Created schedule
        """
        self._schedule_counter += 1
        schedule_id = f"schedule-{self._schedule_counter:04d}"

        schedule = BackupSchedule(
            id=schedule_id,
            name=name,
            frequency=frequency,
            backup_type=backup_type,
            network_id=network_id,
            retention_count=retention_count,
            retention_days=retention_days,
            tags=(tags or []) + [schedule_id],
            custom_interval_hours=custom_interval_hours
        )

        if start_immediately:
            schedule.next_run = datetime.now()
        else:
            schedule.next_run = schedule.calculate_next_run()

        self._schedules[schedule_id] = schedule
        logger.info(f"Created backup schedule: {schedule_id} ({name})")
        return schedule

    def get_schedule(self, schedule_id: str) -> Optional[BackupSchedule]:
        """Get schedule by ID"""
        return self._schedules.get(schedule_id)

    def list_schedules(self, enabled_only: bool = False) -> List[BackupSchedule]:
        """List all schedules"""
        schedules = list(self._schedules.values())
        if enabled_only:
            schedules = [s for s in schedules if s.enabled]
        return schedules

    def update_schedule(
        self,
        schedule_id: str,
        name: Optional[str] = None,
        frequency: Optional[ScheduleFrequency] = None,
        enabled: Optional[bool] = None,
        retention_count: Optional[int] = None,
        retention_days: Optional[int] = None
    ) -> Optional[BackupSchedule]:
        """Update a schedule"""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            return None

        if name is not None:
            schedule.name = name
        if frequency is not None:
            schedule.frequency = frequency
            schedule.next_run = schedule.calculate_next_run()
        if enabled is not None:
            schedule.enabled = enabled
        if retention_count is not None:
            schedule.retention_count = retention_count
        if retention_days is not None:
            schedule.retention_days = retention_days

        return schedule

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule"""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            logger.info(f"Deleted backup schedule: {schedule_id}")
            return True
        return False

    def enable_schedule(self, schedule_id: str) -> bool:
        """Enable a schedule"""
        schedule = self.get_schedule(schedule_id)
        if schedule:
            schedule.enabled = True
            schedule.next_run = schedule.calculate_next_run()
            return True
        return False

    def disable_schedule(self, schedule_id: str) -> bool:
        """Disable a schedule"""
        schedule = self.get_schedule(schedule_id)
        if schedule:
            schedule.enabled = False
            return True
        return False

    async def run_now(self, schedule_id: str) -> Optional[ScheduledRun]:
        """Run a schedule immediately"""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            return None

        await self._execute_schedule(schedule)

        if self._run_history:
            return self._run_history[-1]
        return None

    def add_callback(self, callback: Callable):
        """Add a callback for backup completions"""
        self._callbacks.append(callback)

    def get_run_history(
        self,
        schedule_id: Optional[str] = None,
        limit: int = 50
    ) -> List[ScheduledRun]:
        """Get run history"""
        history = self._run_history
        if schedule_id:
            history = [r for r in history if r.schedule_id == schedule_id]
        return history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        total_schedules = len(self._schedules)
        enabled = sum(1 for s in self._schedules.values() if s.enabled)
        total_runs = len(self._run_history)
        successful_runs = sum(1 for r in self._run_history if r.success)

        return {
            "running": self._running,
            "total_schedules": total_schedules,
            "enabled_schedules": enabled,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "success_rate": round(
                (successful_runs / total_runs * 100) if total_runs > 0 else 100, 2
            )
        }


# Global scheduler instance
_global_scheduler: Optional[BackupScheduler] = None


def get_backup_scheduler() -> BackupScheduler:
    """Get or create the global backup scheduler"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = BackupScheduler()
    return _global_scheduler
