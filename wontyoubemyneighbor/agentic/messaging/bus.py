"""
Message Bus - Inter-agent communication infrastructure

Provides:
- Async message passing between agents
- Topic-based publish/subscribe
- Direct agent-to-agent messaging
- Message history and audit trail
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable, Set
from collections import deque
import uuid

logger = logging.getLogger("MessageBus")


class MessageType(Enum):
    """Types of inter-agent messages"""
    # Information sharing
    ROUTE_UPDATE = "route_update"
    NEIGHBOR_STATE = "neighbor_state"
    METRIC_REPORT = "metric_report"
    HEALTH_STATUS = "health_status"

    # Collaboration
    TROUBLESHOOT_REQUEST = "troubleshoot_request"
    TROUBLESHOOT_RESPONSE = "troubleshoot_response"
    CONFIG_PROPOSAL = "config_proposal"
    CONFIG_VOTE = "config_vote"
    CONFIG_COMMIT = "config_commit"

    # Coordination
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
    HEARTBEAT = "heartbeat"

    # Alerts
    ALERT = "alert"
    ANOMALY_DETECTED = "anomaly_detected"
    FAILURE_NOTIFICATION = "failure_notification"

    # Custom
    CUSTOM = "custom"


class MessagePriority(Enum):
    """Message priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Message:
    """
    Inter-agent message

    Attributes:
        message_id: Unique message identifier
        message_type: Type of message
        sender_id: Sending agent ID
        recipient_id: Target agent ID (None for broadcast)
        topic: Message topic for pub/sub
        payload: Message content
        priority: Message priority
        timestamp: Message creation time
        correlation_id: ID for request/response correlation
        ttl_seconds: Time-to-live (0 = no expiry)
        requires_ack: Whether acknowledgment is required
    """
    message_id: str
    message_type: MessageType
    sender_id: str
    payload: Dict[str, Any]
    recipient_id: Optional[str] = None
    topic: Optional[str] = None
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    ttl_seconds: int = 300
    requires_ack: bool = False
    acknowledged: bool = False
    ack_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "topic": self.topic,
            "payload": self.payload,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "ttl_seconds": self.ttl_seconds,
            "requires_ack": self.requires_ack,
            "acknowledged": self.acknowledged,
            "ack_time": self.ack_time.isoformat() if self.ack_time else None
        }

    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.ttl_seconds == 0:
            return False
        elapsed = (datetime.now() - self.timestamp).total_seconds()
        return elapsed > self.ttl_seconds

    @staticmethod
    def create(
        message_type: MessageType,
        sender_id: str,
        payload: Dict[str, Any],
        **kwargs
    ) -> 'Message':
        """Factory method to create a message"""
        return Message(
            message_id=str(uuid.uuid4())[:12],
            message_type=message_type,
            sender_id=sender_id,
            payload=payload,
            **kwargs
        )


class MessageBus:
    """
    Central message bus for agent communication

    Provides pub/sub and direct messaging capabilities.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize message bus

        Args:
            max_history: Maximum message history to retain
        """
        self._agents: Dict[str, asyncio.Queue] = {}
        self._subscriptions: Dict[str, Set[str]] = {}  # topic -> {agent_ids}
        self._handlers: Dict[str, Callable[[Message], Awaitable[None]]] = {}
        self._history: deque = deque(maxlen=max_history)
        self._pending_acks: Dict[str, Message] = {}
        self._message_counter = 0
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the message bus"""
        self._running = True
        logger.info("Message bus started")

    async def stop(self) -> None:
        """Stop the message bus"""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Message bus stopped")

    def register_agent(self, agent_id: str) -> asyncio.Queue:
        """
        Register an agent with the message bus

        Args:
            agent_id: Agent identifier

        Returns:
            Message queue for the agent
        """
        if agent_id not in self._agents:
            self._agents[agent_id] = asyncio.Queue()
            logger.info(f"Agent registered: {agent_id}")
        return self._agents[agent_id]

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            # Remove from all subscriptions
            for topic in self._subscriptions:
                self._subscriptions[topic].discard(agent_id)
            logger.info(f"Agent unregistered: {agent_id}")

    def subscribe(self, agent_id: str, topic: str) -> None:
        """
        Subscribe an agent to a topic

        Args:
            agent_id: Agent identifier
            topic: Topic to subscribe to
        """
        if topic not in self._subscriptions:
            self._subscriptions[topic] = set()
        self._subscriptions[topic].add(agent_id)
        logger.debug(f"Agent {agent_id} subscribed to topic: {topic}")

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic"""
        if topic in self._subscriptions:
            self._subscriptions[topic].discard(agent_id)

    def register_handler(
        self,
        agent_id: str,
        handler: Callable[[Message], Awaitable[None]]
    ) -> None:
        """
        Register a message handler for an agent

        Args:
            agent_id: Agent identifier
            handler: Async function to handle messages
        """
        self._handlers[agent_id] = handler

    async def send(self, message: Message) -> bool:
        """
        Send a message

        Args:
            message: Message to send

        Returns:
            True if message was delivered
        """
        if message.is_expired():
            logger.warning(f"Message expired before delivery: {message.message_id}")
            return False

        self._history.append(message)
        self._message_counter += 1

        # Direct message
        if message.recipient_id:
            return await self._deliver_direct(message)

        # Topic-based broadcast
        if message.topic:
            return await self._deliver_topic(message)

        # Broadcast to all
        return await self._deliver_broadcast(message)

    async def _deliver_direct(self, message: Message) -> bool:
        """Deliver message to specific agent"""
        if message.recipient_id not in self._agents:
            logger.warning(f"Unknown recipient: {message.recipient_id}")
            return False

        queue = self._agents[message.recipient_id]
        await queue.put(message)

        # Invoke handler if registered
        if message.recipient_id in self._handlers:
            try:
                await self._handlers[message.recipient_id](message)
            except Exception as e:
                logger.error(f"Handler error for {message.recipient_id}: {e}")

        if message.requires_ack:
            self._pending_acks[message.message_id] = message

        logger.debug(f"Message delivered: {message.message_id} -> {message.recipient_id}")
        return True

    async def _deliver_topic(self, message: Message) -> bool:
        """Deliver message to topic subscribers"""
        if message.topic not in self._subscriptions:
            return False

        subscribers = self._subscriptions[message.topic]
        delivered = 0

        for agent_id in subscribers:
            if agent_id == message.sender_id:
                continue  # Don't send to self

            if agent_id in self._agents:
                await self._agents[agent_id].put(message)
                delivered += 1

                if agent_id in self._handlers:
                    try:
                        await self._handlers[agent_id](message)
                    except Exception as e:
                        logger.error(f"Handler error for {agent_id}: {e}")

        logger.debug(f"Topic message delivered: {message.message_id} -> {delivered} subscribers")
        return delivered > 0

    async def _deliver_broadcast(self, message: Message) -> bool:
        """Broadcast message to all agents"""
        delivered = 0

        for agent_id, queue in self._agents.items():
            if agent_id == message.sender_id:
                continue

            await queue.put(message)
            delivered += 1

            if agent_id in self._handlers:
                try:
                    await self._handlers[agent_id](message)
                except Exception as e:
                    logger.error(f"Handler error for {agent_id}: {e}")

        logger.debug(f"Broadcast message delivered: {message.message_id} -> {delivered} agents")
        return delivered > 0

    async def acknowledge(self, message_id: str, agent_id: str) -> bool:
        """
        Acknowledge receipt of a message

        Args:
            message_id: Message to acknowledge
            agent_id: Acknowledging agent

        Returns:
            True if acknowledgment recorded
        """
        if message_id in self._pending_acks:
            message = self._pending_acks[message_id]
            if message.recipient_id == agent_id:
                message.acknowledged = True
                message.ack_time = datetime.now()
                del self._pending_acks[message_id]
                return True
        return False

    async def receive(self, agent_id: str, timeout: float = 0) -> Optional[Message]:
        """
        Receive next message for an agent

        Args:
            agent_id: Agent identifier
            timeout: Timeout in seconds (0 = no wait)

        Returns:
            Message or None if no message available
        """
        if agent_id not in self._agents:
            return None

        queue = self._agents[agent_id]

        try:
            if timeout > 0:
                return await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                return queue.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    def get_pending_messages(self, agent_id: str) -> int:
        """Get count of pending messages for an agent"""
        if agent_id not in self._agents:
            return 0
        return self._agents[agent_id].qsize()

    def get_history(
        self,
        limit: int = 100,
        agent_id: Optional[str] = None,
        message_type: Optional[MessageType] = None
    ) -> List[Message]:
        """
        Get message history

        Args:
            limit: Maximum messages to return
            agent_id: Filter by sender or recipient
            message_type: Filter by type

        Returns:
            List of messages
        """
        history = list(self._history)[-limit:]

        if agent_id:
            history = [
                m for m in history
                if m.sender_id == agent_id or m.recipient_id == agent_id
            ]

        if message_type:
            history = [m for m in history if m.message_type == message_type]

        return history

    def get_statistics(self) -> Dict[str, Any]:
        """Get message bus statistics"""
        type_counts = {}
        for msg in self._history:
            type_name = msg.message_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return {
            "registered_agents": len(self._agents),
            "active_subscriptions": sum(len(s) for s in self._subscriptions.values()),
            "topics": list(self._subscriptions.keys()),
            "total_messages": self._message_counter,
            "history_size": len(self._history),
            "pending_acks": len(self._pending_acks),
            "messages_by_type": type_counts
        }

    # Convenience methods for common message types

    async def send_route_update(
        self,
        sender_id: str,
        routes: List[Dict[str, Any]],
        topic: str = "routes"
    ) -> bool:
        """Send route update to subscribers"""
        message = Message.create(
            message_type=MessageType.ROUTE_UPDATE,
            sender_id=sender_id,
            payload={"routes": routes},
            topic=topic
        )
        return await self.send(message)

    async def send_health_status(
        self,
        sender_id: str,
        status: Dict[str, Any],
        topic: str = "health"
    ) -> bool:
        """Send health status update"""
        message = Message.create(
            message_type=MessageType.HEALTH_STATUS,
            sender_id=sender_id,
            payload=status,
            topic=topic
        )
        return await self.send(message)

    async def send_alert(
        self,
        sender_id: str,
        alert_type: str,
        description: str,
        severity: str = "warning"
    ) -> bool:
        """Broadcast an alert"""
        message = Message.create(
            message_type=MessageType.ALERT,
            sender_id=sender_id,
            payload={
                "alert_type": alert_type,
                "description": description,
                "severity": severity
            },
            priority=MessagePriority.HIGH
        )
        return await self.send(message)

    async def request_troubleshoot(
        self,
        sender_id: str,
        recipient_id: str,
        issue: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Request troubleshooting help from another agent

        Returns:
            correlation_id for tracking the response
        """
        correlation_id = str(uuid.uuid4())[:8]
        message = Message.create(
            message_type=MessageType.TROUBLESHOOT_REQUEST,
            sender_id=sender_id,
            payload={"issue": issue, "context": context},
            recipient_id=recipient_id,
            correlation_id=correlation_id,
            requires_ack=True
        )
        await self.send(message)
        return correlation_id

    async def respond_troubleshoot(
        self,
        sender_id: str,
        recipient_id: str,
        correlation_id: str,
        findings: Dict[str, Any],
        recommendations: List[str]
    ) -> bool:
        """Respond to a troubleshooting request"""
        message = Message.create(
            message_type=MessageType.TROUBLESHOOT_RESPONSE,
            sender_id=sender_id,
            payload={
                "findings": findings,
                "recommendations": recommendations
            },
            recipient_id=recipient_id,
            correlation_id=correlation_id
        )
        return await self.send(message)


# Global message bus instance
_global_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get or create the global message bus"""
    global _global_bus
    if _global_bus is None:
        _global_bus = MessageBus()
    return _global_bus
