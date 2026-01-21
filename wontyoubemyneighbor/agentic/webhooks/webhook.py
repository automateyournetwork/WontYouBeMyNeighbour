"""
Webhook Module - Webhook registration and event management

Provides:
- Webhook registration with URL endpoints
- Event type subscriptions
- Secret-based signature verification
- Webhook lifecycle management
"""

import logging
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger("WebhookManager")


class WebhookEventType(str, Enum):
    """Types of events that can trigger webhooks"""
    # Agent events
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_ERROR = "agent.error"

    # Network events
    NETWORK_CREATED = "network.created"
    NETWORK_DELETED = "network.deleted"
    NETWORK_DEPLOYED = "network.deployed"
    NETWORK_STOPPED = "network.stopped"

    # Protocol events
    OSPF_NEIGHBOR_UP = "ospf.neighbor_up"
    OSPF_NEIGHBOR_DOWN = "ospf.neighbor_down"
    BGP_PEER_UP = "bgp.peer_up"
    BGP_PEER_DOWN = "bgp.peer_down"
    ISIS_ADJACENCY_UP = "isis.adjacency_up"
    ISIS_ADJACENCY_DOWN = "isis.adjacency_down"

    # Routing events
    ROUTE_ADDED = "route.added"
    ROUTE_REMOVED = "route.removed"
    ROUTE_CHANGED = "route.changed"
    CONVERGENCE_COMPLETE = "convergence.complete"

    # Health events
    HEALTH_CHECK_PASSED = "health.check_passed"
    HEALTH_CHECK_FAILED = "health.check_failed"
    ANOMALY_DETECTED = "anomaly.detected"
    REMEDIATION_EXECUTED = "remediation.executed"

    # Test events
    TEST_STARTED = "test.started"
    TEST_COMPLETED = "test.completed"
    TEST_FAILED = "test.failed"

    # Chaos events
    FAILURE_INJECTED = "chaos.failure_injected"
    FAILURE_CLEARED = "chaos.failure_cleared"
    SCENARIO_STARTED = "chaos.scenario_started"
    SCENARIO_COMPLETED = "chaos.scenario_completed"

    # User events
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_ACTION = "user.action"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    CONFIG_CHANGED = "config.changed"

    # Catch-all
    ALL = "*"


class WebhookStatus(str, Enum):
    """Webhook status"""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    FAILED = "failed"  # Too many failures


@dataclass
class WebhookEvent:
    """
    An event to be delivered to webhooks

    Attributes:
        id: Event identifier
        event_type: Type of event
        payload: Event payload data
        source: Source of event (agent_id, network_id, etc.)
        timestamp: When event occurred
        metadata: Additional metadata
    """
    id: str
    event_type: WebhookEventType
    payload: Dict[str, Any]
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class Webhook:
    """
    A webhook registration

    Attributes:
        id: Webhook identifier
        url: Target URL for deliveries
        name: Human-readable name
        description: Webhook description
        events: Subscribed event types
        secret: Shared secret for signatures
        status: Current status
        headers: Custom headers to send
        created_at: Creation timestamp
        updated_at: Last update timestamp
        last_triggered: Last trigger timestamp
        failure_count: Consecutive failure count
        total_deliveries: Total delivery attempts
        successful_deliveries: Successful deliveries
    """
    id: str
    url: str
    name: str
    description: str = ""
    events: Set[WebhookEventType] = field(default_factory=set)
    secret: str = field(default_factory=lambda: secrets.token_hex(32))
    status: WebhookStatus = WebhookStatus.ACTIVE
    headers: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_triggered: Optional[datetime] = None
    failure_count: int = 0
    total_deliveries: int = 0
    successful_deliveries: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_deliveries == 0:
            return 100.0
        return (self.successful_deliveries / self.total_deliveries) * 100

    def is_subscribed(self, event_type: WebhookEventType) -> bool:
        """Check if webhook is subscribed to event type"""
        if WebhookEventType.ALL in self.events:
            return True
        return event_type in self.events

    def generate_signature(self, payload: str) -> str:
        """Generate HMAC signature for payload"""
        return hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify HMAC signature"""
        expected = self.generate_signature(payload)
        return hmac.compare_digest(expected, signature)

    def record_delivery(self, success: bool):
        """Record delivery attempt"""
        self.total_deliveries += 1
        self.last_triggered = datetime.now()
        self.updated_at = datetime.now()

        if success:
            self.successful_deliveries += 1
            self.failure_count = 0
        else:
            self.failure_count += 1
            # Disable after 10 consecutive failures
            if self.failure_count >= 10:
                self.status = WebhookStatus.FAILED
                logger.warning(f"Webhook {self.id} disabled due to failures")

    def to_dict(self, include_secret: bool = False) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "url": self.url,
            "name": self.name,
            "description": self.description,
            "events": [e.value for e in self.events],
            "status": self.status.value,
            "headers": self.headers,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "failure_count": self.failure_count,
            "total_deliveries": self.total_deliveries,
            "successful_deliveries": self.successful_deliveries,
            "success_rate": round(self.success_rate, 2)
        }
        if include_secret:
            result["secret"] = self.secret
        return result


class WebhookManager:
    """
    Manages webhook registrations
    """

    def __init__(self):
        """Initialize webhook manager"""
        self._webhooks: Dict[str, Webhook] = {}
        self._event_subscriptions: Dict[WebhookEventType, Set[str]] = {}
        self._webhook_counter = 0

    def register_webhook(
        self,
        url: str,
        name: str,
        events: List[str],
        description: str = "",
        headers: Optional[Dict[str, str]] = None,
        secret: Optional[str] = None
    ) -> Webhook:
        """
        Register a new webhook

        Args:
            url: Target URL
            name: Webhook name
            events: List of event types to subscribe to
            description: Description
            headers: Custom headers
            secret: Shared secret (generated if not provided)

        Returns:
            Created webhook
        """
        self._webhook_counter += 1
        webhook_id = f"webhook-{self._webhook_counter:04d}"

        # Parse event types
        event_set = set()
        for event in events:
            try:
                event_set.add(WebhookEventType(event))
            except ValueError:
                logger.warning(f"Unknown event type: {event}")

        webhook = Webhook(
            id=webhook_id,
            url=url,
            name=name,
            description=description,
            events=event_set,
            headers=headers or {},
            secret=secret or secrets.token_hex(32)
        )

        self._webhooks[webhook_id] = webhook

        # Update subscription index
        for event_type in event_set:
            if event_type not in self._event_subscriptions:
                self._event_subscriptions[event_type] = set()
            self._event_subscriptions[event_type].add(webhook_id)

        logger.info(f"Registered webhook {webhook_id}: {name} -> {url}")
        return webhook

    def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """Get webhook by ID"""
        return self._webhooks.get(webhook_id)

    def list_webhooks(
        self,
        status: Optional[WebhookStatus] = None
    ) -> List[Webhook]:
        """List all webhooks"""
        webhooks = list(self._webhooks.values())
        if status:
            webhooks = [w for w in webhooks if w.status == status]
        return webhooks

    def update_webhook(
        self,
        webhook_id: str,
        url: Optional[str] = None,
        name: Optional[str] = None,
        events: Optional[List[str]] = None,
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        status: Optional[str] = None
    ) -> Optional[Webhook]:
        """Update a webhook"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return None

        if url:
            webhook.url = url
        if name:
            webhook.name = name
        if description is not None:
            webhook.description = description
        if headers is not None:
            webhook.headers = headers
        if status:
            try:
                webhook.status = WebhookStatus(status)
                if webhook.status == WebhookStatus.ACTIVE:
                    webhook.failure_count = 0  # Reset on reactivation
            except ValueError:
                pass

        if events is not None:
            # Update subscriptions
            old_events = webhook.events
            new_events = set()
            for event in events:
                try:
                    new_events.add(WebhookEventType(event))
                except ValueError:
                    pass

            # Remove old subscriptions
            for event_type in old_events:
                if event_type in self._event_subscriptions:
                    self._event_subscriptions[event_type].discard(webhook_id)

            # Add new subscriptions
            for event_type in new_events:
                if event_type not in self._event_subscriptions:
                    self._event_subscriptions[event_type] = set()
                self._event_subscriptions[event_type].add(webhook_id)

            webhook.events = new_events

        webhook.updated_at = datetime.now()
        return webhook

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return False

        # Remove from subscriptions
        for event_type in webhook.events:
            if event_type in self._event_subscriptions:
                self._event_subscriptions[event_type].discard(webhook_id)

        del self._webhooks[webhook_id]
        logger.info(f"Deleted webhook {webhook_id}")
        return True

    def pause_webhook(self, webhook_id: str) -> bool:
        """Pause a webhook"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return False
        webhook.status = WebhookStatus.PAUSED
        webhook.updated_at = datetime.now()
        return True

    def resume_webhook(self, webhook_id: str) -> bool:
        """Resume a paused webhook"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return False
        webhook.status = WebhookStatus.ACTIVE
        webhook.failure_count = 0
        webhook.updated_at = datetime.now()
        return True

    def regenerate_secret(self, webhook_id: str) -> Optional[str]:
        """Regenerate webhook secret"""
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return None
        webhook.secret = secrets.token_hex(32)
        webhook.updated_at = datetime.now()
        return webhook.secret

    def get_webhooks_for_event(
        self,
        event_type: WebhookEventType
    ) -> List[Webhook]:
        """Get all webhooks subscribed to an event type"""
        webhook_ids = set()

        # Get direct subscriptions
        if event_type in self._event_subscriptions:
            webhook_ids.update(self._event_subscriptions[event_type])

        # Get wildcard subscriptions
        if WebhookEventType.ALL in self._event_subscriptions:
            webhook_ids.update(self._event_subscriptions[WebhookEventType.ALL])

        webhooks = []
        for webhook_id in webhook_ids:
            webhook = self.get_webhook(webhook_id)
            if webhook and webhook.status == WebhookStatus.ACTIVE:
                webhooks.append(webhook)

        return webhooks

    def get_event_types(self) -> List[Dict[str, str]]:
        """Get all available event types"""
        return [
            {"value": e.value, "name": e.name}
            for e in WebhookEventType
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get webhook statistics"""
        total = len(self._webhooks)
        by_status = {}
        total_deliveries = 0
        total_successful = 0

        for webhook in self._webhooks.values():
            status = webhook.status.value
            by_status[status] = by_status.get(status, 0) + 1
            total_deliveries += webhook.total_deliveries
            total_successful += webhook.successful_deliveries

        return {
            "total_webhooks": total,
            "by_status": by_status,
            "total_deliveries": total_deliveries,
            "successful_deliveries": total_successful,
            "overall_success_rate": round(
                (total_successful / total_deliveries * 100) if total_deliveries > 0 else 100, 2
            ),
            "event_types_available": len(WebhookEventType)
        }


# Global webhook manager instance
_global_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """Get or create the global webhook manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = WebhookManager()
    return _global_manager
