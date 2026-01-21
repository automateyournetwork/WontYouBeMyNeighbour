"""
Trigger Management

Provides:
- Trigger definitions
- Cron expressions
- Time-based scheduling
- Event-based triggers
"""

import uuid
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import calendar


class TriggerType(Enum):
    """Types of triggers"""
    CRON = "cron"  # Cron expression
    INTERVAL = "interval"  # Fixed interval
    DATE = "date"  # Specific date/time
    EVENT = "event"  # Event-based
    DEPENDENT = "dependent"  # After another job
    MANUAL = "manual"  # Manual trigger only
    STARTUP = "startup"  # Run on startup
    SHUTDOWN = "shutdown"  # Run on shutdown


class TriggerStatus(Enum):
    """Trigger status"""
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    DISABLED = "disabled"


@dataclass
class CronExpression:
    """Cron expression parser and evaluator"""
    
    expression: str  # Standard cron format: minute hour day_of_month month day_of_week
    
    # Parsed fields
    minute: List[int] = field(default_factory=list)
    hour: List[int] = field(default_factory=list)
    day_of_month: List[int] = field(default_factory=list)
    month: List[int] = field(default_factory=list)
    day_of_week: List[int] = field(default_factory=list)
    
    def __post_init__(self):
        self._parse()
    
    def _parse(self) -> None:
        """Parse cron expression"""
        parts = self.expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {self.expression}")
        
        self.minute = self._parse_field(parts[0], 0, 59)
        self.hour = self._parse_field(parts[1], 0, 23)
        self.day_of_month = self._parse_field(parts[2], 1, 31)
        self.month = self._parse_field(parts[3], 1, 12)
        self.day_of_week = self._parse_field(parts[4], 0, 6)
    
    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single cron field"""
        values = []
        
        for part in field.split(','):
            if part == '*':
                values.extend(range(min_val, max_val + 1))
            elif '/' in part:
                base, step = part.split('/')
                step = int(step)
                if base == '*':
                    start = min_val
                else:
                    start = int(base)
                values.extend(range(start, max_val + 1, step))
            elif '-' in part:
                start, end = part.split('-')
                values.extend(range(int(start), int(end) + 1))
            else:
                values.append(int(part))
        
        return sorted(set(v for v in values if min_val <= v <= max_val))
    
    def matches(self, dt: datetime) -> bool:
        """Check if datetime matches cron expression"""
        return (
            dt.minute in self.minute and
            dt.hour in self.hour and
            dt.day in self.day_of_month and
            dt.month in self.month and
            dt.weekday() in self.day_of_week
        )
    
    def get_next(self, from_time: Optional[datetime] = None) -> datetime:
        """Get next matching datetime"""
        current = from_time or datetime.now()
        current = current.replace(second=0, microsecond=0)
        
        # Check up to 2 years ahead
        max_iterations = 365 * 24 * 60 * 2
        
        for _ in range(max_iterations):
            current += timedelta(minutes=1)
            if self.matches(current):
                return current
        
        raise ValueError("Could not find next matching time within 2 years")
    
    def get_previous(self, from_time: Optional[datetime] = None) -> datetime:
        """Get previous matching datetime"""
        current = from_time or datetime.now()
        current = current.replace(second=0, microsecond=0)
        
        # Check up to 2 years back
        max_iterations = 365 * 24 * 60 * 2
        
        for _ in range(max_iterations):
            current -= timedelta(minutes=1)
            if self.matches(current):
                return current
        
        raise ValueError("Could not find previous matching time within 2 years")
    
    def get_schedule(
        self,
        from_time: Optional[datetime] = None,
        count: int = 10
    ) -> List[datetime]:
        """Get next N matching datetimes"""
        schedule = []
        current = from_time or datetime.now()
        
        for _ in range(count):
            next_time = self.get_next(current)
            schedule.append(next_time)
            current = next_time
        
        return schedule
    
    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "minute": self.minute,
            "hour": self.hour,
            "day_of_month": self.day_of_month,
            "month": self.month,
            "day_of_week": self.day_of_week
        }
    
    @staticmethod
    def describe(expression: str) -> str:
        """Get human-readable description of cron expression"""
        common_expressions = {
            "* * * * *": "Every minute",
            "*/5 * * * *": "Every 5 minutes",
            "*/15 * * * *": "Every 15 minutes",
            "*/30 * * * *": "Every 30 minutes",
            "0 * * * *": "Every hour",
            "0 */2 * * *": "Every 2 hours",
            "0 */4 * * *": "Every 4 hours",
            "0 */6 * * *": "Every 6 hours",
            "0 */12 * * *": "Every 12 hours",
            "0 0 * * *": "Every day at midnight",
            "0 6 * * *": "Every day at 6 AM",
            "0 12 * * *": "Every day at noon",
            "0 18 * * *": "Every day at 6 PM",
            "0 0 * * 0": "Every Sunday at midnight",
            "0 0 * * 1": "Every Monday at midnight",
            "0 0 1 * *": "First day of every month at midnight",
            "0 0 1 1 *": "Every January 1st at midnight"
        }
        return common_expressions.get(expression, f"Custom: {expression}")


@dataclass
class Trigger:
    """Job trigger definition"""
    
    id: str
    name: str
    trigger_type: TriggerType
    description: str = ""
    status: TriggerStatus = TriggerStatus.ACTIVE
    
    # Cron configuration
    cron_expression: Optional[str] = None
    
    # Interval configuration
    interval_seconds: Optional[int] = None
    
    # Date configuration
    run_date: Optional[datetime] = None
    
    # Event configuration
    event_type: Optional[str] = None
    event_filter: Optional[Dict[str, Any]] = None
    
    # Dependent configuration
    depends_on_job_id: Optional[str] = None
    depend_on_success: bool = True
    
    # Time constraints
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timezone: str = "UTC"
    
    # Execution limits
    max_executions: Optional[int] = None
    execution_count: int = 0
    
    # Jitter for load distribution
    jitter_seconds: int = 0
    
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_fired_at: Optional[datetime] = None
    next_fire_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self._calculate_next_fire()
    
    def _calculate_next_fire(self) -> None:
        """Calculate next fire time"""
        now = datetime.now()
        
        # Check constraints
        if self.end_date and now >= self.end_date:
            self.status = TriggerStatus.EXPIRED
            return
        
        if self.max_executions and self.execution_count >= self.max_executions:
            self.status = TriggerStatus.EXPIRED
            return
        
        if self.status != TriggerStatus.ACTIVE:
            return
        
        # Calculate based on type
        if self.trigger_type == TriggerType.CRON and self.cron_expression:
            try:
                cron = CronExpression(self.cron_expression)
                self.next_fire_at = cron.get_next(now)
            except Exception:
                pass
        
        elif self.trigger_type == TriggerType.INTERVAL and self.interval_seconds:
            if self.last_fired_at:
                self.next_fire_at = self.last_fired_at + timedelta(seconds=self.interval_seconds)
            else:
                self.next_fire_at = now + timedelta(seconds=self.interval_seconds)
        
        elif self.trigger_type == TriggerType.DATE and self.run_date:
            if self.run_date > now:
                self.next_fire_at = self.run_date
        
        # Apply start_date constraint
        if self.start_date and self.next_fire_at and self.next_fire_at < self.start_date:
            self.next_fire_at = self.start_date
        
        # Apply end_date constraint
        if self.end_date and self.next_fire_at and self.next_fire_at > self.end_date:
            self.next_fire_at = None
            self.status = TriggerStatus.EXPIRED
    
    def fire(self) -> bool:
        """Mark trigger as fired"""
        if self.status != TriggerStatus.ACTIVE:
            return False
        
        self.last_fired_at = datetime.now()
        self.execution_count += 1
        self.updated_at = datetime.now()
        
        # Check if expired
        if self.max_executions and self.execution_count >= self.max_executions:
            self.status = TriggerStatus.EXPIRED
        else:
            self._calculate_next_fire()
        
        return True
    
    def should_fire(self, at_time: Optional[datetime] = None) -> bool:
        """Check if trigger should fire"""
        if self.status != TriggerStatus.ACTIVE:
            return False
        
        check_time = at_time or datetime.now()
        
        if self.next_fire_at and self.next_fire_at <= check_time:
            return True
        
        return False
    
    def pause(self) -> None:
        """Pause trigger"""
        if self.status == TriggerStatus.ACTIVE:
            self.status = TriggerStatus.PAUSED
            self.updated_at = datetime.now()
    
    def resume(self) -> None:
        """Resume trigger"""
        if self.status == TriggerStatus.PAUSED:
            self.status = TriggerStatus.ACTIVE
            self._calculate_next_fire()
            self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "trigger_type": self.trigger_type.value,
            "description": self.description,
            "status": self.status.value,
            "cron_expression": self.cron_expression,
            "cron_description": CronExpression.describe(self.cron_expression) if self.cron_expression else None,
            "interval_seconds": self.interval_seconds,
            "run_date": self.run_date.isoformat() if self.run_date else None,
            "event_type": self.event_type,
            "event_filter": self.event_filter,
            "depends_on_job_id": self.depends_on_job_id,
            "depend_on_success": self.depend_on_success,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "timezone": self.timezone,
            "max_executions": self.max_executions,
            "execution_count": self.execution_count,
            "jitter_seconds": self.jitter_seconds,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_fired_at": self.last_fired_at.isoformat() if self.last_fired_at else None,
            "next_fire_at": self.next_fire_at.isoformat() if self.next_fire_at else None,
            "tags": self.tags,
            "metadata": self.metadata
        }


class TriggerManager:
    """Manages job triggers"""
    
    def __init__(self):
        self.triggers: Dict[str, Trigger] = {}
        self._init_builtin_triggers()
    
    def _init_builtin_triggers(self) -> None:
        """Initialize built-in triggers"""
        
        # Every minute trigger
        self.create_trigger(
            name="Every Minute",
            trigger_type=TriggerType.CRON,
            cron_expression="* * * * *",
            description="Fires every minute",
            tags=["interval", "minute"]
        )
        
        # Every 5 minutes trigger
        self.create_trigger(
            name="Every 5 Minutes",
            trigger_type=TriggerType.CRON,
            cron_expression="*/5 * * * *",
            description="Fires every 5 minutes",
            tags=["interval", "minute"]
        )
        
        # Every hour trigger
        self.create_trigger(
            name="Hourly",
            trigger_type=TriggerType.CRON,
            cron_expression="0 * * * *",
            description="Fires at the top of every hour",
            tags=["interval", "hour"]
        )
        
        # Daily at midnight trigger
        self.create_trigger(
            name="Daily Midnight",
            trigger_type=TriggerType.CRON,
            cron_expression="0 0 * * *",
            description="Fires daily at midnight",
            tags=["daily", "midnight"]
        )
        
        # Daily at 6 AM trigger
        self.create_trigger(
            name="Daily 6 AM",
            trigger_type=TriggerType.CRON,
            cron_expression="0 6 * * *",
            description="Fires daily at 6 AM",
            tags=["daily", "morning"]
        )
        
        # Weekly on Sunday trigger
        self.create_trigger(
            name="Weekly Sunday",
            trigger_type=TriggerType.CRON,
            cron_expression="0 0 * * 0",
            description="Fires every Sunday at midnight",
            tags=["weekly", "sunday"]
        )
        
        # Monthly first day trigger
        self.create_trigger(
            name="Monthly First",
            trigger_type=TriggerType.CRON,
            cron_expression="0 0 1 * *",
            description="Fires on the first of every month",
            tags=["monthly", "first"]
        )
        
        # 30 second interval trigger
        self.create_trigger(
            name="30 Second Interval",
            trigger_type=TriggerType.INTERVAL,
            interval_seconds=30,
            description="Fires every 30 seconds",
            tags=["interval", "seconds"]
        )
    
    def create_trigger(
        self,
        name: str,
        trigger_type: TriggerType,
        description: str = "",
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        run_date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        event_filter: Optional[Dict[str, Any]] = None,
        depends_on_job_id: Optional[str] = None,
        depend_on_success: bool = True,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_executions: Optional[int] = None,
        jitter_seconds: int = 0,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Trigger:
        """Create a new trigger"""
        trigger_id = f"trg_{uuid.uuid4().hex[:8]}"
        
        trigger = Trigger(
            id=trigger_id,
            name=name,
            trigger_type=trigger_type,
            description=description,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_date=run_date,
            event_type=event_type,
            event_filter=event_filter,
            depends_on_job_id=depends_on_job_id,
            depend_on_success=depend_on_success,
            start_date=start_date,
            end_date=end_date,
            max_executions=max_executions,
            jitter_seconds=jitter_seconds,
            tags=tags or [],
            metadata=metadata or {}
        )
        
        self.triggers[trigger_id] = trigger
        return trigger
    
    def get_trigger(self, trigger_id: str) -> Optional[Trigger]:
        """Get trigger by ID"""
        return self.triggers.get(trigger_id)
    
    def get_trigger_by_name(self, name: str) -> Optional[Trigger]:
        """Get trigger by name"""
        for trigger in self.triggers.values():
            if trigger.name == name:
                return trigger
        return None
    
    def update_trigger(
        self,
        trigger_id: str,
        **kwargs
    ) -> Optional[Trigger]:
        """Update trigger properties"""
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return None
        
        for key, value in kwargs.items():
            if hasattr(trigger, key):
                setattr(trigger, key, value)
        
        trigger.updated_at = datetime.now()
        trigger._calculate_next_fire()
        return trigger
    
    def delete_trigger(self, trigger_id: str) -> bool:
        """Delete a trigger"""
        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            return True
        return False
    
    def pause_trigger(self, trigger_id: str) -> bool:
        """Pause a trigger"""
        trigger = self.triggers.get(trigger_id)
        if trigger:
            trigger.pause()
            return True
        return False
    
    def resume_trigger(self, trigger_id: str) -> bool:
        """Resume a trigger"""
        trigger = self.triggers.get(trigger_id)
        if trigger:
            trigger.resume()
            return True
        return False
    
    def fire_trigger(self, trigger_id: str) -> bool:
        """Fire a trigger"""
        trigger = self.triggers.get(trigger_id)
        if trigger:
            return trigger.fire()
        return False
    
    def get_due_triggers(self, at_time: Optional[datetime] = None) -> List[Trigger]:
        """Get triggers that are due to fire"""
        due = []
        for trigger in self.triggers.values():
            if trigger.should_fire(at_time):
                due.append(trigger)
        return due
    
    def get_triggers(
        self,
        trigger_type: Optional[TriggerType] = None,
        status: Optional[TriggerStatus] = None,
        tag: Optional[str] = None
    ) -> List[Trigger]:
        """Get triggers with filtering"""
        triggers = list(self.triggers.values())
        
        if trigger_type:
            triggers = [t for t in triggers if t.trigger_type == trigger_type]
        if status:
            triggers = [t for t in triggers if t.status == status]
        if tag:
            triggers = [t for t in triggers if tag in t.tags]
        
        return triggers
    
    def get_schedule(
        self,
        from_time: Optional[datetime] = None,
        hours: int = 24
    ) -> List[Tuple[datetime, Trigger]]:
        """Get scheduled fires for the next N hours"""
        schedule = []
        end_time = (from_time or datetime.now()) + timedelta(hours=hours)
        
        for trigger in self.triggers.values():
            if trigger.status != TriggerStatus.ACTIVE:
                continue
            
            if trigger.trigger_type == TriggerType.CRON and trigger.cron_expression:
                try:
                    cron = CronExpression(trigger.cron_expression)
                    current = from_time or datetime.now()
                    while True:
                        next_time = cron.get_next(current)
                        if next_time > end_time:
                            break
                        schedule.append((next_time, trigger))
                        current = next_time
                except Exception:
                    pass
            
            elif trigger.next_fire_at and trigger.next_fire_at <= end_time:
                schedule.append((trigger.next_fire_at, trigger))
        
        # Sort by time
        schedule.sort(key=lambda x: x[0])
        return schedule
    
    def get_statistics(self) -> dict:
        """Get trigger statistics"""
        by_type = {}
        by_status = {}
        total_fires = 0
        
        for trigger in self.triggers.values():
            by_type[trigger.trigger_type.value] = by_type.get(trigger.trigger_type.value, 0) + 1
            by_status[trigger.status.value] = by_status.get(trigger.status.value, 0) + 1
            total_fires += trigger.execution_count
        
        return {
            "total_triggers": len(self.triggers),
            "active_triggers": len([t for t in self.triggers.values() if t.status == TriggerStatus.ACTIVE]),
            "total_fires": total_fires,
            "by_type": by_type,
            "by_status": by_status
        }


# Global trigger manager instance
_trigger_manager: Optional[TriggerManager] = None


def get_trigger_manager() -> TriggerManager:
    """Get or create the global trigger manager"""
    global _trigger_manager
    if _trigger_manager is None:
        _trigger_manager = TriggerManager()
    return _trigger_manager
