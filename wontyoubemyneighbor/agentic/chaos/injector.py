"""
Failure Injector - Controlled failure injection for chaos engineering

Provides:
- Link failure simulation
- Agent/node failure simulation
- Packet loss injection
- Latency injection
- Configuration error injection
- Scheduled and random failures
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
from collections import deque

logger = logging.getLogger("FailureInjector")


class FailureType(Enum):
    """Types of failures that can be injected"""
    LINK_DOWN = "link_down"
    AGENT_DOWN = "agent_down"
    PACKET_LOSS = "packet_loss"
    LATENCY = "latency"
    CONFIG_ERROR = "config_error"
    CPU_SPIKE = "cpu_spike"
    MEMORY_PRESSURE = "memory_pressure"
    FLAP = "flap"  # Rapid up/down cycling
    PARTITION = "partition"  # Network partition


@dataclass
class FailureConfig:
    """
    Configuration for a failure injection

    Attributes:
        failure_type: Type of failure to inject
        target_agent: Target agent ID
        target_link: Target link ID (for link failures)
        target_peer: Target peer/neighbor (for selective failures)
        duration_seconds: How long the failure lasts (0 = permanent until cleared)
        intensity: Failure intensity (0.0-1.0, e.g., packet loss percentage)
        parameters: Additional failure-specific parameters
    """
    failure_type: FailureType
    target_agent: str
    target_link: Optional[str] = None
    target_peer: Optional[str] = None
    duration_seconds: int = 60
    intensity: float = 1.0
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_type": self.failure_type.value,
            "target_agent": self.target_agent,
            "target_link": self.target_link,
            "target_peer": self.target_peer,
            "duration_seconds": self.duration_seconds,
            "intensity": self.intensity,
            "parameters": self.parameters
        }


@dataclass
class FailureResult:
    """
    Result of a failure injection

    Attributes:
        failure_id: Unique failure identifier
        config: Failure configuration
        start_time: When the failure was injected
        end_time: When the failure was cleared (or None if active)
        status: Current status (active, cleared, failed)
        impact: Observed impact metrics
        recovery_time_ms: Time to recover after clearing (if measured)
    """
    failure_id: str
    config: FailureConfig
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "active"
    impact: Dict[str, Any] = field(default_factory=dict)
    recovery_time_ms: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "config": self.config.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "impact": self.impact,
            "recovery_time_ms": self.recovery_time_ms,
            "error": self.error
        }


@dataclass
class ScheduledFailure:
    """
    A scheduled failure for future injection

    Attributes:
        schedule_id: Unique schedule identifier
        config: Failure configuration
        scheduled_time: When to inject
        repeat_interval_seconds: Repeat interval (0 = one-time)
        enabled: Whether the schedule is active
    """
    schedule_id: str
    config: FailureConfig
    scheduled_time: datetime
    repeat_interval_seconds: int = 0
    enabled: bool = True
    last_triggered: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "config": self.config.to_dict(),
            "scheduled_time": self.scheduled_time.isoformat(),
            "repeat_interval_seconds": self.repeat_interval_seconds,
            "enabled": self.enabled,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None
        }


class FailureInjector:
    """
    Failure injection engine for chaos engineering

    Injects controlled failures into the network to test resilience.
    """

    def __init__(self, dry_run: bool = False, max_history: int = 500):
        """
        Initialize failure injector

        Args:
            dry_run: If True, log failures but don't execute
            max_history: Maximum failure history to retain
        """
        self.dry_run = dry_run
        self._active_failures: Dict[str, FailureResult] = {}
        self._history: deque = deque(maxlen=max_history)
        self._schedules: Dict[str, ScheduledFailure] = {}
        self._handlers: Dict[FailureType, Callable[[FailureConfig], Awaitable[Dict[str, Any]]]] = {}
        self._clear_handlers: Dict[FailureType, Callable[[str, FailureConfig], Awaitable[None]]] = {}
        self._failure_counter = 0
        self._schedule_counter = 0
        self._scheduler_task: Optional[asyncio.Task] = None

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default failure handlers"""
        # These are simulation handlers - in production, these would
        # interface with actual network components

        async def handle_link_down(config: FailureConfig) -> Dict[str, Any]:
            """Simulate link down"""
            logger.info(f"[INJECT] Link down: {config.target_agent} -> {config.target_link or config.target_peer}")
            return {
                "simulated": True,
                "action": "link_down",
                "affected_routes": random.randint(5, 50)
            }

        async def handle_agent_down(config: FailureConfig) -> Dict[str, Any]:
            """Simulate agent down"""
            logger.info(f"[INJECT] Agent down: {config.target_agent}")
            return {
                "simulated": True,
                "action": "agent_down",
                "affected_neighbors": random.randint(1, 10)
            }

        async def handle_packet_loss(config: FailureConfig) -> Dict[str, Any]:
            """Simulate packet loss"""
            loss_pct = config.intensity * 100
            logger.info(f"[INJECT] Packet loss {loss_pct:.0f}% on {config.target_agent}")
            return {
                "simulated": True,
                "action": "packet_loss",
                "loss_percentage": loss_pct
            }

        async def handle_latency(config: FailureConfig) -> Dict[str, Any]:
            """Simulate latency injection"""
            latency_ms = config.parameters.get("latency_ms", 100)
            jitter_ms = config.parameters.get("jitter_ms", 10)
            logger.info(f"[INJECT] Latency {latency_ms}ms (+/-{jitter_ms}ms) on {config.target_agent}")
            return {
                "simulated": True,
                "action": "latency",
                "latency_ms": latency_ms,
                "jitter_ms": jitter_ms
            }

        async def handle_config_error(config: FailureConfig) -> Dict[str, Any]:
            """Simulate configuration error"""
            error_type = config.parameters.get("error_type", "invalid_metric")
            logger.info(f"[INJECT] Config error ({error_type}) on {config.target_agent}")
            return {
                "simulated": True,
                "action": "config_error",
                "error_type": error_type
            }

        async def handle_flap(config: FailureConfig) -> Dict[str, Any]:
            """Simulate interface/adjacency flapping"""
            flap_count = config.parameters.get("flap_count", 5)
            interval_ms = config.parameters.get("interval_ms", 1000)
            logger.info(f"[INJECT] Flap ({flap_count}x at {interval_ms}ms) on {config.target_agent}")
            return {
                "simulated": True,
                "action": "flap",
                "flap_count": flap_count,
                "interval_ms": interval_ms
            }

        async def handle_partition(config: FailureConfig) -> Dict[str, Any]:
            """Simulate network partition"""
            partition_group = config.parameters.get("partition_group", [])
            logger.info(f"[INJECT] Network partition: {config.target_agent} isolated from {partition_group}")
            return {
                "simulated": True,
                "action": "partition",
                "isolated_from": partition_group
            }

        # Register handlers
        self._handlers[FailureType.LINK_DOWN] = handle_link_down
        self._handlers[FailureType.AGENT_DOWN] = handle_agent_down
        self._handlers[FailureType.PACKET_LOSS] = handle_packet_loss
        self._handlers[FailureType.LATENCY] = handle_latency
        self._handlers[FailureType.CONFIG_ERROR] = handle_config_error
        self._handlers[FailureType.FLAP] = handle_flap
        self._handlers[FailureType.PARTITION] = handle_partition

    def register_handler(
        self,
        failure_type: FailureType,
        inject_handler: Callable[[FailureConfig], Awaitable[Dict[str, Any]]],
        clear_handler: Optional[Callable[[str, FailureConfig], Awaitable[None]]] = None
    ) -> None:
        """
        Register custom failure handlers

        Args:
            failure_type: Type of failure to handle
            inject_handler: Async function to inject the failure
            clear_handler: Async function to clear the failure
        """
        self._handlers[failure_type] = inject_handler
        if clear_handler:
            self._clear_handlers[failure_type] = clear_handler

    def _generate_failure_id(self) -> str:
        """Generate unique failure ID"""
        self._failure_counter += 1
        return f"failure-{self._failure_counter:04d}"

    def _generate_schedule_id(self) -> str:
        """Generate unique schedule ID"""
        self._schedule_counter += 1
        return f"schedule-{self._schedule_counter:04d}"

    async def inject_failure(self, config: FailureConfig) -> FailureResult:
        """
        Inject a failure

        Args:
            config: Failure configuration

        Returns:
            FailureResult with injection details
        """
        failure_id = self._generate_failure_id()

        result = FailureResult(
            failure_id=failure_id,
            config=config,
            start_time=datetime.now(),
            status="active"
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would inject: {config.failure_type.value} on {config.target_agent}")
            result.impact = {"dry_run": True}
            self._active_failures[failure_id] = result
            self._history.append(result)
            return result

        # Execute handler
        handler = self._handlers.get(config.failure_type)
        if handler:
            try:
                impact = await handler(config)
                result.impact = impact

                self._active_failures[failure_id] = result
                self._history.append(result)

                # Schedule auto-clear if duration specified
                if config.duration_seconds > 0:
                    asyncio.create_task(self._auto_clear(failure_id, config.duration_seconds))

                logger.info(f"Failure injected: {failure_id} ({config.failure_type.value})")
                return result

            except Exception as e:
                logger.error(f"Failed to inject failure: {e}")
                result.status = "failed"
                result.error = str(e)
                self._history.append(result)
                return result
        else:
            result.status = "failed"
            result.error = f"No handler for failure type: {config.failure_type.value}"
            self._history.append(result)
            return result

    async def _auto_clear(self, failure_id: str, delay_seconds: int) -> None:
        """Auto-clear a failure after delay"""
        await asyncio.sleep(delay_seconds)
        await self.clear_failure(failure_id)

    async def clear_failure(self, failure_id: str) -> Optional[FailureResult]:
        """
        Clear an active failure

        Args:
            failure_id: Failure to clear

        Returns:
            Updated FailureResult or None if not found
        """
        if failure_id not in self._active_failures:
            return None

        result = self._active_failures[failure_id]
        result.end_time = datetime.now()
        result.status = "cleared"

        # Execute clear handler if registered
        clear_handler = self._clear_handlers.get(result.config.failure_type)
        if clear_handler:
            try:
                await clear_handler(failure_id, result.config)
            except Exception as e:
                logger.error(f"Error in clear handler: {e}")

        # Calculate recovery time
        result.recovery_time_ms = (result.end_time - result.start_time).total_seconds() * 1000

        del self._active_failures[failure_id]

        logger.info(f"Failure cleared: {failure_id}")
        return result

    async def clear_all_failures(self) -> List[FailureResult]:
        """Clear all active failures"""
        results = []
        for failure_id in list(self._active_failures.keys()):
            result = await self.clear_failure(failure_id)
            if result:
                results.append(result)
        return results

    def get_active_failures(self) -> List[FailureResult]:
        """Get all active failures"""
        return list(self._active_failures.values())

    def get_failure(self, failure_id: str) -> Optional[FailureResult]:
        """Get a specific failure"""
        return self._active_failures.get(failure_id)

    def get_history(
        self,
        limit: int = 100,
        failure_type: Optional[FailureType] = None,
        target_agent: Optional[str] = None
    ) -> List[FailureResult]:
        """
        Get failure history

        Args:
            limit: Maximum results
            failure_type: Filter by type
            target_agent: Filter by target agent

        Returns:
            List of failure results
        """
        history = list(self._history)[-limit:]

        if failure_type:
            history = [f for f in history if f.config.failure_type == failure_type]

        if target_agent:
            history = [f for f in history if f.config.target_agent == target_agent]

        return history

    # Scheduled failures

    def schedule_failure(
        self,
        config: FailureConfig,
        delay_seconds: int = 0,
        repeat_interval_seconds: int = 0
    ) -> ScheduledFailure:
        """
        Schedule a failure for future injection

        Args:
            config: Failure configuration
            delay_seconds: Seconds until first injection
            repeat_interval_seconds: Repeat interval (0 = one-time)

        Returns:
            ScheduledFailure object
        """
        schedule_id = self._generate_schedule_id()
        scheduled_time = datetime.now() + timedelta(seconds=delay_seconds)

        schedule = ScheduledFailure(
            schedule_id=schedule_id,
            config=config,
            scheduled_time=scheduled_time,
            repeat_interval_seconds=repeat_interval_seconds
        )

        self._schedules[schedule_id] = schedule
        logger.info(f"Failure scheduled: {schedule_id} at {scheduled_time}")

        return schedule

    def cancel_schedule(self, schedule_id: str) -> bool:
        """Cancel a scheduled failure"""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            logger.info(f"Schedule cancelled: {schedule_id}")
            return True
        return False

    def get_schedules(self) -> List[ScheduledFailure]:
        """Get all scheduled failures"""
        return list(self._schedules.values())

    async def start_scheduler(self) -> None:
        """Start the failure scheduler background task"""
        if self._scheduler_task is None:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            logger.info("Failure scheduler started")

    async def stop_scheduler(self) -> None:
        """Stop the failure scheduler"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            logger.info("Failure scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Background scheduler loop"""
        while True:
            try:
                now = datetime.now()

                for schedule_id, schedule in list(self._schedules.items()):
                    if not schedule.enabled:
                        continue

                    if now >= schedule.scheduled_time:
                        # Inject the failure
                        await self.inject_failure(schedule.config)
                        schedule.last_triggered = now

                        if schedule.repeat_interval_seconds > 0:
                            # Reschedule
                            schedule.scheduled_time = now + timedelta(
                                seconds=schedule.repeat_interval_seconds
                            )
                        else:
                            # One-time, remove
                            del self._schedules[schedule_id]

                await asyncio.sleep(1)  # Check every second

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(5)

    # Random failure injection (chaos mode)

    async def inject_random_failure(
        self,
        agents: List[str],
        failure_types: Optional[List[FailureType]] = None,
        duration_range: tuple = (30, 120)
    ) -> FailureResult:
        """
        Inject a random failure on a random agent

        Args:
            agents: List of agent IDs to choose from
            failure_types: Allowed failure types (None = all)
            duration_range: (min, max) duration in seconds

        Returns:
            FailureResult
        """
        if not agents:
            raise ValueError("No agents provided")

        target = random.choice(agents)

        if failure_types:
            ftype = random.choice(failure_types)
        else:
            ftype = random.choice(list(FailureType))

        duration = random.randint(duration_range[0], duration_range[1])

        config = FailureConfig(
            failure_type=ftype,
            target_agent=target,
            duration_seconds=duration,
            intensity=random.uniform(0.3, 1.0)
        )

        return await self.inject_failure(config)

    def get_statistics(self) -> Dict[str, Any]:
        """Get failure injection statistics"""
        type_counts = {}
        for result in self._history:
            type_name = result.config.failure_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return {
            "total_failures_injected": len(self._history),
            "active_failures": len(self._active_failures),
            "scheduled_failures": len(self._schedules),
            "failures_by_type": type_counts,
            "dry_run_mode": self.dry_run
        }
