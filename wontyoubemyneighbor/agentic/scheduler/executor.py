"""
Scheduler Executor

Provides:
- Main scheduler loop
- Job execution orchestration
- Missed job handling
- Concurrent execution management
"""

import uuid
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from enum import Enum
import time

from .jobs import Job, JobStatus, JobResult, JobManager, get_job_manager, JobPriority
from .triggers import Trigger, TriggerType, TriggerStatus, TriggerManager, get_trigger_manager


class SchedulerStatus(Enum):
    """Scheduler status"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class SchedulerConfig:
    """Scheduler configuration"""
    
    check_interval_seconds: float = 1.0  # How often to check for due jobs
    max_concurrent_jobs: int = 10  # Maximum concurrent job executions
    missed_job_grace_seconds: int = 60  # Grace period for missed jobs
    timezone: str = "UTC"
    catch_up_missed_jobs: bool = False  # Run missed jobs on startup
    coalesce_missed_jobs: bool = True  # Combine missed runs into one
    job_default_timeout_seconds: int = 300
    enable_job_queue: bool = True  # Queue jobs that exceed concurrency limit
    max_queue_size: int = 100
    thread_pool_size: int = 4
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "check_interval_seconds": self.check_interval_seconds,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "missed_job_grace_seconds": self.missed_job_grace_seconds,
            "timezone": self.timezone,
            "catch_up_missed_jobs": self.catch_up_missed_jobs,
            "coalesce_missed_jobs": self.coalesce_missed_jobs,
            "job_default_timeout_seconds": self.job_default_timeout_seconds,
            "enable_job_queue": self.enable_job_queue,
            "max_queue_size": self.max_queue_size,
            "thread_pool_size": self.thread_pool_size,
            "extra": self.extra
        }


@dataclass
class SchedulerEvent:
    """Scheduler event for history tracking"""
    
    id: str
    event_type: str  # started, stopped, job_executed, job_failed, etc.
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


class Scheduler:
    """Main scheduler for job execution"""
    
    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        job_manager: Optional[JobManager] = None,
        trigger_manager: Optional[TriggerManager] = None
    ):
        self.config = config or SchedulerConfig()
        self.job_manager = job_manager or get_job_manager()
        self.trigger_manager = trigger_manager or get_trigger_manager()
        
        self.status = SchedulerStatus.STOPPED
        self._running_jobs: Dict[str, JobResult] = {}  # job_id -> current result
        self._job_queue: List[str] = []  # Queue of job IDs waiting to run
        self._events: List[SchedulerEvent] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # Statistics
        self.started_at: Optional[datetime] = None
        self.stopped_at: Optional[datetime] = None
        self.total_executions: int = 0
        self.successful_executions: int = 0
        self.failed_executions: int = 0
        
        # Callbacks
        self._on_job_start: List[Callable] = []
        self._on_job_complete: List[Callable] = []
        self._on_job_fail: List[Callable] = []
        
        self._init_job_trigger_bindings()
    
    def _init_job_trigger_bindings(self) -> None:
        """Bind built-in jobs to triggers"""
        # This would typically bind jobs to their triggers
        # For now, we just ensure the structures are in place
        pass
    
    def _record_event(
        self,
        event_type: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a scheduler event"""
        event = SchedulerEvent(
            id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=event_type,
            timestamp=datetime.now(),
            details=details or {}
        )
        self._events.append(event)
        
        # Keep only last 1000 events
        if len(self._events) > 1000:
            self._events = self._events[-1000:]
    
    def on_job_start(self, callback: Callable) -> None:
        """Register job start callback"""
        self._on_job_start.append(callback)
    
    def on_job_complete(self, callback: Callable) -> None:
        """Register job complete callback"""
        self._on_job_complete.append(callback)
    
    def on_job_fail(self, callback: Callable) -> None:
        """Register job fail callback"""
        self._on_job_fail.append(callback)
    
    def _notify_job_start(self, job: Job, result: JobResult) -> None:
        """Notify callbacks of job start"""
        for callback in self._on_job_start:
            try:
                callback(job, result)
            except Exception:
                pass
    
    def _notify_job_complete(self, job: Job, result: JobResult) -> None:
        """Notify callbacks of job completion"""
        for callback in self._on_job_complete:
            try:
                callback(job, result)
            except Exception:
                pass
    
    def _notify_job_fail(self, job: Job, result: JobResult) -> None:
        """Notify callbacks of job failure"""
        for callback in self._on_job_fail:
            try:
                callback(job, result)
            except Exception:
                pass
    
    def start(self) -> bool:
        """Start the scheduler"""
        if self.status in (SchedulerStatus.RUNNING, SchedulerStatus.STARTING):
            return False
        
        self.status = SchedulerStatus.STARTING
        self._stop_event.clear()
        self.started_at = datetime.now()
        
        self._record_event("scheduler_starting")
        
        # Start scheduler thread
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        
        self.status = SchedulerStatus.RUNNING
        self._record_event("scheduler_started")
        
        return True
    
    def stop(self, wait: bool = True, timeout: float = 30.0) -> bool:
        """Stop the scheduler"""
        if self.status == SchedulerStatus.STOPPED:
            return False
        
        self.status = SchedulerStatus.STOPPING
        self._record_event("scheduler_stopping")
        
        self._stop_event.set()
        
        if wait and self._thread:
            self._thread.join(timeout=timeout)
        
        self.status = SchedulerStatus.STOPPED
        self.stopped_at = datetime.now()
        self._record_event("scheduler_stopped")
        
        return True
    
    def pause(self) -> bool:
        """Pause the scheduler"""
        if self.status != SchedulerStatus.RUNNING:
            return False
        
        self.status = SchedulerStatus.PAUSED
        self._record_event("scheduler_paused")
        return True
    
    def resume(self) -> bool:
        """Resume the scheduler"""
        if self.status != SchedulerStatus.PAUSED:
            return False
        
        self.status = SchedulerStatus.RUNNING
        self._record_event("scheduler_resumed")
        return True
    
    def _scheduler_loop(self) -> None:
        """Main scheduler loop"""
        while not self._stop_event.is_set():
            if self.status == SchedulerStatus.PAUSED:
                time.sleep(self.config.check_interval_seconds)
                continue
            
            try:
                self._check_and_execute()
            except Exception as e:
                self._record_event("scheduler_error", {"error": str(e)})
            
            time.sleep(self.config.check_interval_seconds)
    
    def _check_and_execute(self) -> None:
        """Check for due jobs and execute them"""
        now = datetime.now()
        
        # Get due triggers
        due_triggers = self.trigger_manager.get_due_triggers(now)
        
        for trigger in due_triggers:
            # Find jobs associated with this trigger
            for job in self.job_manager.jobs.values():
                if trigger.id in job.trigger_ids and job.enabled:
                    self._queue_job(job.id)
            
            # Fire the trigger
            trigger.fire()
        
        # Process queued jobs
        self._process_queue()
    
    def _queue_job(self, job_id: str) -> bool:
        """Add job to execution queue"""
        with self._lock:
            # Check if job is already running
            if job_id in self._running_jobs:
                job = self.job_manager.get_job(job_id)
                if job and not job.config.allow_concurrent:
                    return False
            
            # Check queue limits
            if len(self._job_queue) >= self.config.max_queue_size:
                return False
            
            if job_id not in self._job_queue:
                self._job_queue.append(job_id)
            
            return True
    
    def _process_queue(self) -> None:
        """Process jobs in the queue"""
        with self._lock:
            # Check how many slots available
            available_slots = self.config.max_concurrent_jobs - len(self._running_jobs)
            
            if available_slots <= 0 or not self._job_queue:
                return
            
            # Sort queue by job priority
            prioritized = []
            for job_id in self._job_queue:
                job = self.job_manager.get_job(job_id)
                if job:
                    prioritized.append((job.priority.value, job_id))
            
            prioritized.sort(key=lambda x: x[0])
            
            # Execute jobs up to available slots
            executed = []
            for _, job_id in prioritized[:available_slots]:
                result = self._execute_job(job_id)
                if result:
                    executed.append(job_id)
            
            # Remove executed jobs from queue
            for job_id in executed:
                if job_id in self._job_queue:
                    self._job_queue.remove(job_id)
    
    def _execute_job(self, job_id: str) -> Optional[JobResult]:
        """Execute a job"""
        job = self.job_manager.get_job(job_id)
        if not job:
            return None
        
        # Create execution result
        result = self.job_manager.execute_job(job_id)
        
        if result:
            self.total_executions += 1
            
            if result.status == JobStatus.COMPLETED:
                self.successful_executions += 1
                self._notify_job_complete(job, result)
                self._record_event("job_completed", {
                    "job_id": job_id,
                    "job_name": job.name,
                    "duration_ms": result.duration_ms
                })
            else:
                self.failed_executions += 1
                self._notify_job_fail(job, result)
                self._record_event("job_failed", {
                    "job_id": job_id,
                    "job_name": job.name,
                    "error": result.error
                })
        
        return result
    
    def run_job_now(
        self,
        job_id: str,
        override_params: Optional[Dict[str, Any]] = None
    ) -> Optional[JobResult]:
        """Run a job immediately (bypassing scheduler)"""
        job = self.job_manager.get_job(job_id)
        if not job:
            return None
        
        self._record_event("job_manual_run", {"job_id": job_id, "job_name": job.name})
        
        result = self.job_manager.execute_job(job_id, override_params)
        
        if result:
            self.total_executions += 1
            if result.status == JobStatus.COMPLETED:
                self.successful_executions += 1
                self._notify_job_complete(job, result)
            else:
                self.failed_executions += 1
                self._notify_job_fail(job, result)
        
        return result
    
    def schedule_job(
        self,
        job_id: str,
        trigger_id: str
    ) -> bool:
        """Associate a job with a trigger"""
        job = self.job_manager.get_job(job_id)
        trigger = self.trigger_manager.get_trigger(trigger_id)
        
        if not job or not trigger:
            return False
        
        if trigger_id not in job.trigger_ids:
            job.trigger_ids.append(trigger_id)
            job.updated_at = datetime.now()
            
            # Calculate next run time
            if trigger.next_fire_at:
                if not job.next_run_at or trigger.next_fire_at < job.next_run_at:
                    job.next_run_at = trigger.next_fire_at
            
            self._record_event("job_scheduled", {
                "job_id": job_id,
                "trigger_id": trigger_id
            })
        
        return True
    
    def unschedule_job(
        self,
        job_id: str,
        trigger_id: str
    ) -> bool:
        """Remove association between job and trigger"""
        job = self.job_manager.get_job(job_id)
        
        if not job:
            return False
        
        if trigger_id in job.trigger_ids:
            job.trigger_ids.remove(trigger_id)
            job.updated_at = datetime.now()
            
            self._record_event("job_unscheduled", {
                "job_id": job_id,
                "trigger_id": trigger_id
            })
        
        return True
    
    def get_running_jobs(self) -> List[Job]:
        """Get currently running jobs"""
        running = []
        for job_id in self._running_jobs.keys():
            job = self.job_manager.get_job(job_id)
            if job:
                running.append(job)
        return running
    
    def get_queued_jobs(self) -> List[Job]:
        """Get jobs in queue"""
        queued = []
        for job_id in self._job_queue:
            job = self.job_manager.get_job(job_id)
            if job:
                queued.append(job)
        return queued
    
    def get_upcoming_jobs(
        self,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get jobs scheduled to run in the next N hours"""
        upcoming = []
        schedule = self.trigger_manager.get_schedule(hours=hours)
        
        for fire_time, trigger in schedule:
            for job in self.job_manager.jobs.values():
                if trigger.id in job.trigger_ids and job.enabled:
                    upcoming.append({
                        "job_id": job.id,
                        "job_name": job.name,
                        "trigger_id": trigger.id,
                        "trigger_name": trigger.name,
                        "scheduled_at": fire_time.isoformat()
                    })
        
        return upcoming
    
    def get_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[SchedulerEvent]:
        """Get scheduler events"""
        events = self._events
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events[-limit:]
    
    def get_status(self) -> dict:
        """Get scheduler status"""
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "uptime_seconds": (datetime.now() - self.started_at).total_seconds() if self.started_at and self.status == SchedulerStatus.RUNNING else 0,
            "running_jobs_count": len(self._running_jobs),
            "queued_jobs_count": len(self._job_queue),
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.successful_executions / self.total_executions if self.total_executions > 0 else 1.0,
            "config": self.config.to_dict()
        }
    
    def get_statistics(self) -> dict:
        """Get comprehensive scheduler statistics"""
        job_stats = self.job_manager.get_statistics()
        trigger_stats = self.trigger_manager.get_statistics()
        
        return {
            "scheduler": self.get_status(),
            "jobs": job_stats,
            "triggers": trigger_stats,
            "events": {
                "total_events": len(self._events),
                "recent_events": len(self.get_events(limit=10))
            }
        }


# Global scheduler instance
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get or create the global scheduler"""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
