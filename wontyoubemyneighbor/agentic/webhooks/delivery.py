"""
Webhook Delivery Module - Handles webhook payload delivery

Provides:
- Async HTTP delivery
- Retry with exponential backoff
- Delivery tracking and history
- Batch processing
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid

logger = logging.getLogger("WebhookDispatcher")


class DeliveryStatus(str, Enum):
    """Delivery attempt status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class DeliveryResult:
    """
    Result of a delivery attempt

    Attributes:
        success: Whether delivery succeeded
        status_code: HTTP status code
        response_body: Response body (truncated)
        error_message: Error message if failed
        duration_ms: Request duration in milliseconds
        attempt_number: Attempt number (1-based)
    """
    success: bool
    status_code: Optional[int] = None
    response_body: str = ""
    error_message: str = ""
    duration_ms: float = 0.0
    attempt_number: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status_code": self.status_code,
            "response_body": self.response_body[:500] if self.response_body else "",
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 2),
            "attempt_number": self.attempt_number
        }


@dataclass
class WebhookDelivery:
    """
    A webhook delivery record

    Attributes:
        id: Delivery identifier
        webhook_id: Target webhook ID
        event_id: Source event ID
        event_type: Event type
        url: Target URL
        payload: Delivery payload
        status: Current status
        attempts: Delivery attempts
        max_attempts: Maximum attempts
        created_at: Creation timestamp
        scheduled_at: Next attempt timestamp
        completed_at: Completion timestamp
    """
    id: str
    webhook_id: str
    event_id: str
    event_type: str
    url: str
    payload: Dict[str, Any]
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: List[DeliveryResult] = field(default_factory=list)
    max_attempts: int = 5
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def is_complete(self) -> bool:
        return self.status in [DeliveryStatus.SUCCESS, DeliveryStatus.FAILED]

    @property
    def last_attempt(self) -> Optional[DeliveryResult]:
        return self.attempts[-1] if self.attempts else None

    def add_attempt(self, result: DeliveryResult):
        """Add a delivery attempt"""
        self.attempts.append(result)
        if result.success:
            self.status = DeliveryStatus.SUCCESS
            self.completed_at = datetime.now()
        elif self.attempt_count >= self.max_attempts:
            self.status = DeliveryStatus.FAILED
            self.completed_at = datetime.now()
        else:
            self.status = DeliveryStatus.RETRYING
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            delay = 2 ** (self.attempt_count - 1)
            self.scheduled_at = datetime.now() + timedelta(seconds=delay)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "webhook_id": self.webhook_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "url": self.url,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "attempts": [a.to_dict() for a in self.attempts],
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class WebhookDispatcher:
    """
    Handles webhook delivery with retry support
    """

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize dispatcher

        Args:
            max_concurrent: Maximum concurrent deliveries
        """
        self._deliveries: Dict[str, WebhookDelivery] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._max_concurrent = max_concurrent
        self._running = False
        self._workers: List[asyncio.Task] = []
        self._delivery_counter = 0
        self._history_limit = 1000

    async def start(self):
        """Start the dispatcher workers"""
        if self._running:
            return

        self._running = True
        self._queue = asyncio.Queue()

        # Start worker tasks
        for i in range(self._max_concurrent):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

        logger.info(f"Webhook dispatcher started with {self._max_concurrent} workers")

    async def stop(self):
        """Stop the dispatcher"""
        self._running = False

        # Cancel workers
        for task in self._workers:
            task.cancel()

        self._workers.clear()
        logger.info("Webhook dispatcher stopped")

    async def _worker(self, worker_id: int):
        """Worker that processes deliveries from queue"""
        while self._running:
            try:
                # Get delivery from queue with timeout
                try:
                    delivery_id = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                delivery = self._deliveries.get(delivery_id)
                if not delivery:
                    continue

                # Check if scheduled time has passed
                if delivery.scheduled_at > datetime.now():
                    # Re-queue for later
                    await asyncio.sleep(0.1)
                    await self._queue.put(delivery_id)
                    continue

                # Execute delivery
                await self._execute_delivery(delivery)

                # Re-queue if retrying
                if delivery.status == DeliveryStatus.RETRYING:
                    await self._queue.put(delivery_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

    async def _execute_delivery(self, delivery: WebhookDelivery):
        """Execute a single delivery attempt"""
        from .webhook import get_webhook_manager

        delivery.status = DeliveryStatus.IN_PROGRESS
        start_time = datetime.now()

        try:
            # Get webhook for signature
            manager = get_webhook_manager()
            webhook = manager.get_webhook(delivery.webhook_id)

            # Prepare payload
            payload_json = json.dumps(delivery.payload, default=str)

            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": delivery.event_type,
                "X-Webhook-Delivery": delivery.id,
                "X-Webhook-Timestamp": datetime.now().isoformat()
            }

            if webhook:
                # Add signature
                signature = webhook.generate_signature(payload_json)
                headers["X-Webhook-Signature"] = f"sha256={signature}"
                # Add custom headers
                headers.update(webhook.headers)

            # Simulate HTTP request (in production, use aiohttp or httpx)
            # For now, simulate success/failure based on URL
            await asyncio.sleep(0.1)  # Simulate network delay

            # Simulate response
            if "fail" in delivery.url.lower() or "error" in delivery.url.lower():
                status_code = 500
                response_body = "Simulated failure"
                success = False
            elif "timeout" in delivery.url.lower():
                await asyncio.sleep(30)  # Simulate timeout
                status_code = None
                response_body = ""
                success = False
            else:
                status_code = 200
                response_body = '{"status": "received"}'
                success = True

            duration = (datetime.now() - start_time).total_seconds() * 1000

            result = DeliveryResult(
                success=success,
                status_code=status_code,
                response_body=response_body,
                duration_ms=duration,
                attempt_number=delivery.attempt_count + 1
            )

            delivery.add_attempt(result)

            # Update webhook stats
            if webhook:
                webhook.record_delivery(success)

            logger.debug(
                f"Delivery {delivery.id}: attempt {result.attempt_number} "
                f"{'succeeded' if success else 'failed'}"
            )

        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            result = DeliveryResult(
                success=False,
                error_message="Request timeout",
                duration_ms=duration,
                attempt_number=delivery.attempt_count + 1
            )
            delivery.add_attempt(result)

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            result = DeliveryResult(
                success=False,
                error_message=str(e),
                duration_ms=duration,
                attempt_number=delivery.attempt_count + 1
            )
            delivery.add_attempt(result)
            logger.error(f"Delivery {delivery.id} error: {e}")

    async def dispatch(
        self,
        webhook_id: str,
        event_id: str,
        event_type: str,
        url: str,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        """
        Queue a webhook delivery

        Args:
            webhook_id: Target webhook ID
            event_id: Source event ID
            event_type: Event type
            url: Target URL
            payload: Delivery payload

        Returns:
            WebhookDelivery object
        """
        self._delivery_counter += 1
        delivery_id = f"delivery-{uuid.uuid4().hex[:8]}"

        delivery = WebhookDelivery(
            id=delivery_id,
            webhook_id=webhook_id,
            event_id=event_id,
            event_type=event_type,
            url=url,
            payload=payload
        )

        self._deliveries[delivery_id] = delivery

        # Trim history
        if len(self._deliveries) > self._history_limit:
            completed = [
                d for d in self._deliveries.values()
                if d.is_complete
            ]
            completed.sort(key=lambda d: d.completed_at or datetime.min)
            for d in completed[:100]:
                del self._deliveries[d.id]

        # Queue for delivery
        await self._queue.put(delivery_id)

        return delivery

    async def dispatch_to_webhooks(
        self,
        event_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> List[WebhookDelivery]:
        """
        Dispatch event to all subscribed webhooks

        Args:
            event_id: Event identifier
            event_type: Event type string
            payload: Event payload

        Returns:
            List of deliveries queued
        """
        from .webhook import get_webhook_manager, WebhookEventType

        manager = get_webhook_manager()

        try:
            event_type_enum = WebhookEventType(event_type)
        except ValueError:
            logger.warning(f"Unknown event type: {event_type}")
            return []

        webhooks = manager.get_webhooks_for_event(event_type_enum)
        deliveries = []

        for webhook in webhooks:
            delivery = await self.dispatch(
                webhook_id=webhook.id,
                event_id=event_id,
                event_type=event_type,
                url=webhook.url,
                payload=payload
            )
            deliveries.append(delivery)

        return deliveries

    def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Get delivery by ID"""
        return self._deliveries.get(delivery_id)

    def get_deliveries(
        self,
        webhook_id: Optional[str] = None,
        status: Optional[DeliveryStatus] = None,
        limit: int = 100
    ) -> List[WebhookDelivery]:
        """Get deliveries with optional filters"""
        deliveries = list(self._deliveries.values())

        if webhook_id:
            deliveries = [d for d in deliveries if d.webhook_id == webhook_id]

        if status:
            deliveries = [d for d in deliveries if d.status == status]

        # Sort by created_at descending
        deliveries.sort(key=lambda d: d.created_at, reverse=True)

        return deliveries[:limit]

    async def retry_delivery(self, delivery_id: str) -> bool:
        """Manually retry a failed delivery"""
        delivery = self.get_delivery(delivery_id)
        if not delivery:
            return False

        if delivery.status != DeliveryStatus.FAILED:
            return False

        # Reset for retry
        delivery.status = DeliveryStatus.PENDING
        delivery.scheduled_at = datetime.now()
        delivery.max_attempts += 3  # Allow 3 more attempts

        await self._queue.put(delivery_id)
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get dispatcher statistics"""
        total = len(self._deliveries)
        by_status = {}
        total_attempts = 0
        total_success = 0

        for delivery in self._deliveries.values():
            status = delivery.status.value
            by_status[status] = by_status.get(status, 0) + 1
            total_attempts += delivery.attempt_count
            if delivery.status == DeliveryStatus.SUCCESS:
                total_success += 1

        return {
            "total_deliveries": total,
            "by_status": by_status,
            "total_attempts": total_attempts,
            "success_count": total_success,
            "success_rate": round(
                (total_success / total * 100) if total > 0 else 100, 2
            ),
            "queue_size": self._queue.qsize() if self._queue else 0,
            "workers_active": len(self._workers),
            "running": self._running
        }


# Global dispatcher instance
_global_dispatcher: Optional[WebhookDispatcher] = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Get or create the global webhook dispatcher"""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = WebhookDispatcher()
    return _global_dispatcher
