"""
Job Management

Provides:
- Job definitions
- Job types and statuses
- Job execution tracking
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class JobType(Enum):
    """Types of jobs"""
    COMMAND = "command"  # Execute command
    SCRIPT = "script"  # Run script
    FUNCTION = "function"  # Call function
    WORKFLOW = "workflow"  # Run workflow
    PIPELINE = "pipeline"  # Run pipeline
    RULE = "rule"  # Evaluate rule
    TEMPLATE = "template"  # Render template
    API_CALL = "api_call"  # Make API call
    NOTIFICATION = "notification"  # Send notification
    BACKUP = "backup"  # Backup operation
    CLEANUP = "cleanup"  # Cleanup operation
    HEALTH_CHECK = "health_check"  # Health check
    METRICS = "metrics"  # Collect metrics
    REPORT = "report"  # Generate report
    CUSTOM = "custom"  # Custom job


class JobStatus(Enum):
    """Job execution status"""
    PENDING = "pending"  # Not started
    SCHEDULED = "scheduled"  # Scheduled for execution
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Cancelled by user
    SKIPPED = "skipped"  # Skipped (condition not met)
    TIMEOUT = "timeout"  # Execution timed out
    RETRYING = "retrying"  # Retrying after failure


class JobPriority(Enum):
    """Job priority levels"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    BACKGROUND = 5


@dataclass
class JobConfig:
    """Job configuration"""
    
    timeout_seconds: int = 300  # 5 minutes default
    retry_count: int = 3
    retry_delay_seconds: int = 60
    retry_backoff: float = 2.0  # Exponential backoff multiplier
    allow_concurrent: bool = False  # Allow concurrent executions
    max_instances: int = 1  # Max concurrent instances
    catch_up: bool = False  # Run missed executions
    coalesce: bool = True  # Combine missed runs into one
    store_result: bool = True  # Store execution results
    result_ttl_hours: int = 24  # How long to keep results
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "retry_backoff": self.retry_backoff,
            "allow_concurrent": self.allow_concurrent,
            "max_instances": self.max_instances,
            "catch_up": self.catch_up,
            "coalesce": self.coalesce,
            "store_result": self.store_result,
            "result_ttl_hours": self.result_ttl_hours,
            "extra": self.extra
        }


@dataclass
class JobResult:
    """Job execution result"""
    
    job_id: str
    execution_id: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    output: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "error": self.error,
            "retry_count": self.retry_count,
            "metadata": self.metadata
        }


@dataclass
class Job:
    """Scheduled job definition"""
    
    id: str
    name: str
    job_type: JobType
    handler: str  # Handler name or function reference
    description: str = ""
    priority: JobPriority = JobPriority.MEDIUM
    config: JobConfig = field(default_factory=JobConfig)
    parameters: Dict[str, Any] = field(default_factory=dict)  # Job parameters
    trigger_ids: List[str] = field(default_factory=list)  # Associated triggers
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Execution tracking
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    avg_duration_ms: float = 0.0
    
    def record_execution(self, result: JobResult) -> None:
        """Record execution result"""
        self.run_count += 1
        self.last_run_at = result.started_at
        
        if result.status == JobStatus.COMPLETED:
            self.success_count += 1
            self.last_success_at = result.completed_at
        elif result.status in (JobStatus.FAILED, JobStatus.TIMEOUT):
            self.failure_count += 1
            self.last_failure_at = result.completed_at
        
        # Update average duration
        if result.duration_ms > 0:
            if self.avg_duration_ms == 0:
                self.avg_duration_ms = result.duration_ms
            else:
                self.avg_duration_ms = (self.avg_duration_ms * 0.8) + (result.duration_ms * 0.2)
        
        self.updated_at = datetime.now()
    
    def get_success_rate(self) -> float:
        """Get success rate"""
        if self.run_count == 0:
            return 1.0
        return self.success_count / self.run_count
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "job_type": self.job_type.value,
            "handler": self.handler,
            "description": self.description,
            "priority": self.priority.value,
            "config": self.config.to_dict(),
            "parameters": self.parameters,
            "trigger_ids": self.trigger_ids,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "metadata": self.metadata,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "avg_duration_ms": self.avg_duration_ms,
            "success_rate": self.get_success_rate()
        }


class JobManager:
    """Manages scheduled jobs"""
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.results: Dict[str, List[JobResult]] = {}  # job_id -> results
        self._handlers: Dict[str, Callable] = {}
        self._init_builtin_handlers()
        self._init_builtin_jobs()
    
    def _init_builtin_handlers(self) -> None:
        """Initialize built-in job handlers"""
        
        def log_handler(params: Dict[str, Any]) -> Any:
            """Log message handler"""
            message = params.get("message", "Job executed")
            level = params.get("level", "info")
            return {"logged": True, "level": level, "message": message}
        
        def health_check_handler(params: Dict[str, Any]) -> Any:
            """Health check handler"""
            target = params.get("target", "localhost")
            return {"target": target, "healthy": True, "response_time_ms": 10}
        
        def metrics_handler(params: Dict[str, Any]) -> Any:
            """Metrics collection handler"""
            import random
            return {
                "cpu_percent": random.uniform(10, 90),
                "memory_percent": random.uniform(20, 80),
                "disk_percent": random.uniform(30, 70),
                "collected_at": datetime.now().isoformat()
            }
        
        def cleanup_handler(params: Dict[str, Any]) -> Any:
            """Cleanup handler"""
            target = params.get("target", "temp")
            max_age_hours = params.get("max_age_hours", 24)
            return {"target": target, "cleaned": True, "files_removed": 0}
        
        def backup_handler(params: Dict[str, Any]) -> Any:
            """Backup handler"""
            source = params.get("source", "/data")
            destination = params.get("destination", "/backup")
            return {"source": source, "destination": destination, "size_bytes": 0, "success": True}
        
        def notification_handler(params: Dict[str, Any]) -> Any:
            """Notification handler"""
            channel = params.get("channel", "email")
            recipient = params.get("recipient", "admin")
            message = params.get("message", "Notification")
            return {"channel": channel, "recipient": recipient, "sent": True}
        
        def api_call_handler(params: Dict[str, Any]) -> Any:
            """API call handler"""
            url = params.get("url", "http://localhost")
            method = params.get("method", "GET")
            return {"url": url, "method": method, "status_code": 200, "success": True}
        
        def report_handler(params: Dict[str, Any]) -> Any:
            """Report generation handler"""
            report_type = params.get("type", "summary")
            return {"type": report_type, "generated": True, "path": f"/reports/{report_type}.pdf"}
        
        self._handlers = {
            "log": log_handler,
            "health_check": health_check_handler,
            "metrics": metrics_handler,
            "cleanup": cleanup_handler,
            "backup": backup_handler,
            "notification": notification_handler,
            "api_call": api_call_handler,
            "report": report_handler
        }
    
    def _init_builtin_jobs(self) -> None:
        """Initialize built-in jobs"""
        
        # Health check job
        self.create_job(
            name="System Health Check",
            job_type=JobType.HEALTH_CHECK,
            handler="health_check",
            description="Check system health status",
            parameters={"target": "localhost"},
            tags=["health", "monitoring"]
        )
        
        # Metrics collection job
        self.create_job(
            name="Collect Metrics",
            job_type=JobType.METRICS,
            handler="metrics",
            description="Collect system metrics",
            parameters={},
            tags=["metrics", "monitoring"]
        )
        
        # Log cleanup job
        self.create_job(
            name="Log Cleanup",
            job_type=JobType.CLEANUP,
            handler="cleanup",
            description="Clean up old log files",
            parameters={"target": "logs", "max_age_hours": 168},
            priority=JobPriority.LOW,
            tags=["cleanup", "maintenance"]
        )
        
        # Config backup job
        self.create_job(
            name="Config Backup",
            job_type=JobType.BACKUP,
            handler="backup",
            description="Backup configuration files",
            parameters={"source": "/config", "destination": "/backup/config"},
            tags=["backup", "config"]
        )
        
        # Daily report job
        self.create_job(
            name="Daily Report",
            job_type=JobType.REPORT,
            handler="report",
            description="Generate daily summary report",
            parameters={"type": "daily_summary"},
            priority=JobPriority.LOW,
            tags=["report", "daily"]
        )
        
        # Alert notification job
        self.create_job(
            name="Alert Notification",
            job_type=JobType.NOTIFICATION,
            handler="notification",
            description="Send alert notifications",
            parameters={"channel": "email", "recipient": "admin@example.com"},
            priority=JobPriority.HIGH,
            tags=["notification", "alert"]
        )
    
    def register_handler(
        self,
        name: str,
        handler: Callable
    ) -> None:
        """Register a job handler"""
        self._handlers[name] = handler
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """Get handler by name"""
        return self._handlers.get(name)
    
    def get_handlers(self) -> List[str]:
        """Get all handler names"""
        return list(self._handlers.keys())
    
    def create_job(
        self,
        name: str,
        job_type: JobType,
        handler: str,
        description: str = "",
        priority: JobPriority = JobPriority.MEDIUM,
        config: Optional[JobConfig] = None,
        parameters: Optional[Dict[str, Any]] = None,
        trigger_ids: Optional[List[str]] = None,
        enabled: bool = True,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Job:
        """Create a new job"""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        
        job = Job(
            id=job_id,
            name=name,
            job_type=job_type,
            handler=handler,
            description=description,
            priority=priority,
            config=config or JobConfig(),
            parameters=parameters or {},
            trigger_ids=trigger_ids or [],
            enabled=enabled,
            tags=tags or [],
            metadata=metadata or {}
        )
        
        self.jobs[job_id] = job
        self.results[job_id] = []
        return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    def get_job_by_name(self, name: str) -> Optional[Job]:
        """Get job by name"""
        for job in self.jobs.values():
            if job.name == name:
                return job
        return None
    
    def update_job(
        self,
        job_id: str,
        **kwargs
    ) -> Optional[Job]:
        """Update job properties"""
        job = self.jobs.get(job_id)
        if not job:
            return None
        
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        job.updated_at = datetime.now()
        return job
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            if job_id in self.results:
                del self.results[job_id]
            return True
        return False
    
    def enable_job(self, job_id: str) -> bool:
        """Enable a job"""
        job = self.jobs.get(job_id)
        if job:
            job.enabled = True
            job.updated_at = datetime.now()
            return True
        return False
    
    def disable_job(self, job_id: str) -> bool:
        """Disable a job"""
        job = self.jobs.get(job_id)
        if job:
            job.enabled = False
            job.updated_at = datetime.now()
            return True
        return False
    
    def execute_job(
        self,
        job_id: str,
        override_params: Optional[Dict[str, Any]] = None
    ) -> Optional[JobResult]:
        """Execute a job immediately"""
        job = self.jobs.get(job_id)
        if not job:
            return None
        
        execution_id = f"exec_{uuid.uuid4().hex[:8]}"
        started_at = datetime.now()
        
        # Merge parameters
        params = {**job.parameters}
        if override_params:
            params.update(override_params)
        
        # Get handler
        handler = self._handlers.get(job.handler)
        
        try:
            if handler:
                output = handler(params)
                status = JobStatus.COMPLETED
                error = None
            else:
                output = None
                status = JobStatus.FAILED
                error = f"Handler '{job.handler}' not found"
        except Exception as e:
            output = None
            status = JobStatus.FAILED
            error = str(e)
        
        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000
        
        result = JobResult(
            job_id=job_id,
            execution_id=execution_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            output=output,
            error=error
        )
        
        # Record result
        job.record_execution(result)
        
        if job.config.store_result:
            self.results[job_id].append(result)
            # Trim old results
            max_results = 100
            if len(self.results[job_id]) > max_results:
                self.results[job_id] = self.results[job_id][-max_results:]
        
        return result
    
    def add_trigger(self, job_id: str, trigger_id: str) -> bool:
        """Add trigger to job"""
        job = self.jobs.get(job_id)
        if job and trigger_id not in job.trigger_ids:
            job.trigger_ids.append(trigger_id)
            job.updated_at = datetime.now()
            return True
        return False
    
    def remove_trigger(self, job_id: str, trigger_id: str) -> bool:
        """Remove trigger from job"""
        job = self.jobs.get(job_id)
        if job and trigger_id in job.trigger_ids:
            job.trigger_ids.remove(trigger_id)
            job.updated_at = datetime.now()
            return True
        return False
    
    def get_job_results(
        self,
        job_id: str,
        limit: int = 10
    ) -> List[JobResult]:
        """Get job execution results"""
        results = self.results.get(job_id, [])
        return results[-limit:]
    
    def get_jobs(
        self,
        job_type: Optional[JobType] = None,
        enabled_only: bool = False,
        priority: Optional[JobPriority] = None,
        tag: Optional[str] = None
    ) -> List[Job]:
        """Get jobs with filtering"""
        jobs = list(self.jobs.values())
        
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        if enabled_only:
            jobs = [j for j in jobs if j.enabled]
        if priority:
            jobs = [j for j in jobs if j.priority == priority]
        if tag:
            jobs = [j for j in jobs if tag in j.tags]
        
        return jobs
    
    def get_due_jobs(self, at_time: Optional[datetime] = None) -> List[Job]:
        """Get jobs that are due to run"""
        check_time = at_time or datetime.now()
        due_jobs = []
        
        for job in self.jobs.values():
            if job.enabled and job.next_run_at and job.next_run_at <= check_time:
                due_jobs.append(job)
        
        # Sort by priority
        due_jobs.sort(key=lambda j: j.priority.value)
        return due_jobs
    
    def get_statistics(self) -> dict:
        """Get job statistics"""
        total_runs = 0
        total_successes = 0
        total_failures = 0
        by_type = {}
        by_priority = {}
        
        for job in self.jobs.values():
            total_runs += job.run_count
            total_successes += job.success_count
            total_failures += job.failure_count
            by_type[job.job_type.value] = by_type.get(job.job_type.value, 0) + 1
            by_priority[job.priority.value] = by_priority.get(job.priority.value, 0) + 1
        
        return {
            "total_jobs": len(self.jobs),
            "enabled_jobs": len([j for j in self.jobs.values() if j.enabled]),
            "total_runs": total_runs,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": total_successes / total_runs if total_runs > 0 else 1.0,
            "by_type": by_type,
            "by_priority": by_priority,
            "registered_handlers": len(self._handlers)
        }


# Global job manager instance
_job_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    """Get or create the global job manager"""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
