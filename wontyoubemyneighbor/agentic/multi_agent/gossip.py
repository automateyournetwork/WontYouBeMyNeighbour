"""
Gossip Protocol for Ralph-to-Ralph Communication

Implements epidemic-style information dissemination between Ralph instances
for state sharing, anomaly detection, and coordination.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import asyncio
import json
import hashlib


class MessageType(str, Enum):
    """Types of gossip messages"""
    STATE_UPDATE = "state_update"
    ANOMALY_ALERT = "anomaly_alert"
    CONSENSUS_REQUEST = "consensus_request"
    CONSENSUS_VOTE = "consensus_vote"
    HEALTH_CHECK = "health_check"
    TOPOLOGY_SYNC = "topology_sync"


@dataclass
class GossipMessage:
    """Message exchanged between Ralph instances"""
    message_id: str
    message_type: MessageType
    sender_id: str
    timestamp: datetime
    payload: Dict[str, Any]
    ttl: int = 3  # Time-to-live (hops)
    seen_by: Set[str] = None

    def __post_init__(self):
        if self.seen_by is None:
            self.seen_by = {self.sender_id}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "ttl": self.ttl,
            "seen_by": list(self.seen_by)
        }

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GossipMessage':
        """Deserialize from dictionary"""
        return cls(
            message_id=data["message_id"],
            message_type=MessageType(data["message_type"]),
            sender_id=data["sender_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data["payload"],
            ttl=data.get("ttl", 3),
            seen_by=set(data.get("seen_by", []))
        )


class GossipProtocol:
    """
    Gossip protocol for distributed Ralph coordination.

    Features:
    - Epidemic-style message propagation
    - Duplicate detection
    - TTL-based message expiration
    - Configurable fanout
    """

    def __init__(
        self,
        ralph_id: str,
        fanout: int = 3,
        gossip_interval: float = 5.0
    ):
        self.ralph_id = ralph_id
        self.fanout = fanout  # Number of peers to gossip to
        self.gossip_interval = gossip_interval

        # Known Ralph peers
        self.peers: Dict[str, Dict[str, Any]] = {}

        # Message history (for duplicate detection)
        self.seen_messages: Set[str] = set()
        self.message_buffer: List[GossipMessage] = []

        # Handlers for different message types
        self.handlers: Dict[MessageType, callable] = {}

        # Gossip task
        self._gossip_task: Optional[asyncio.Task] = None
        self._running = False

    def register_peer(
        self,
        peer_id: str,
        peer_address: str,
        peer_port: int = 8080
    ):
        """Register a Ralph peer for gossip"""
        self.peers[peer_id] = {
            "address": peer_address,
            "port": peer_port,
            "last_seen": datetime.utcnow(),
            "health": "unknown"
        }

    def register_handler(self, message_type: MessageType, handler: callable):
        """Register handler for message type"""
        self.handlers[message_type] = handler

    def create_message(
        self,
        message_type: MessageType,
        payload: Dict[str, Any],
        ttl: int = 3
    ) -> GossipMessage:
        """Create new gossip message"""
        # Generate unique message ID
        message_data = f"{self.ralph_id}{datetime.utcnow().isoformat()}{json.dumps(payload)}"
        message_id = hashlib.sha256(message_data.encode()).hexdigest()[:16]

        return GossipMessage(
            message_id=message_id,
            message_type=message_type,
            sender_id=self.ralph_id,
            timestamp=datetime.utcnow(),
            payload=payload,
            ttl=ttl
        )

    async def broadcast(self, message: GossipMessage):
        """
        Broadcast message to gossip network.

        Message will be propagated via epidemic protocol.
        """
        # Mark as seen
        self.seen_messages.add(message.message_id)
        message.seen_by.add(self.ralph_id)

        # Add to buffer
        self.message_buffer.append(message)

        # Immediately forward to peers
        await self._forward_message(message)

    async def receive_message(self, message: GossipMessage) -> bool:
        """
        Receive message from peer.

        Returns True if message is new, False if duplicate.
        """
        # Check if already seen
        if message.message_id in self.seen_messages:
            return False

        # Check TTL
        if message.ttl <= 0:
            return False

        # Mark as seen
        self.seen_messages.add(message.message_id)
        message.seen_by.add(self.ralph_id)

        # Handle message
        if message.message_type in self.handlers:
            await self.handlers[message.message_type](message)

        # Decrement TTL and forward
        message.ttl -= 1
        if message.ttl > 0:
            await self._forward_message(message)

        return True

    async def _forward_message(self, message: GossipMessage):
        """Forward message to random subset of peers"""
        import random

        # Select random peers (excluding those who've seen it)
        available_peers = [
            peer_id for peer_id in self.peers.keys()
            if peer_id not in message.seen_by
        ]

        if not available_peers:
            return

        # Select fanout peers
        selected_peers = random.sample(
            available_peers,
            min(self.fanout, len(available_peers))
        )

        # Forward to selected peers
        for peer_id in selected_peers:
            await self._send_to_peer(peer_id, message)

    async def _send_to_peer(self, peer_id: str, message: GossipMessage):
        """
        Send message to specific peer.

        In real implementation, this would use HTTP/WebSocket.
        For now, it's a stub.
        """
        if peer_id not in self.peers:
            return

        peer = self.peers[peer_id]

        # TODO: Actual network send
        # Would use aiohttp to POST to peer's gossip endpoint
        # await aiohttp.post(f"http://{peer['address']}:{peer['port']}/gossip", json=message.to_dict())

        print(f"[Gossip] Would send {message.message_type.value} to {peer_id} at {peer['address']}")

    async def start(self):
        """Start gossip protocol"""
        if self._running:
            return

        self._running = True
        self._gossip_task = asyncio.create_task(self._gossip_loop())
        print(f"[Gossip] Started for Ralph {self.ralph_id}")

    async def stop(self):
        """Stop gossip protocol"""
        self._running = False
        if self._gossip_task:
            self._gossip_task.cancel()
            try:
                await self._gossip_task
            except asyncio.CancelledError:
                pass

    async def _gossip_loop(self):
        """Main gossip loop - periodic health checks and state sync"""
        while self._running:
            try:
                # Send health check to peers
                health_msg = self.create_message(
                    MessageType.HEALTH_CHECK,
                    payload={"status": "alive", "timestamp": datetime.utcnow().isoformat()}
                )
                await self.broadcast(health_msg)

                # Clean old messages from buffer
                self._clean_message_buffer()

                await asyncio.sleep(self.gossip_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Gossip] Error in gossip loop: {e}")
                await asyncio.sleep(1)

    def _clean_message_buffer(self, max_age_seconds: int = 300):
        """Remove old messages from buffer"""
        cutoff_time = datetime.utcnow().timestamp() - max_age_seconds
        self.message_buffer = [
            msg for msg in self.message_buffer
            if msg.timestamp.timestamp() > cutoff_time
        ]

        # Keep seen_messages set bounded
        if len(self.seen_messages) > 10000:
            # Keep only recent half
            self.seen_messages = set(list(self.seen_messages)[-5000:])

    def get_peer_status(self) -> Dict[str, Any]:
        """Get status of all known peers"""
        return {
            peer_id: {
                "address": peer["address"],
                "last_seen": peer["last_seen"].isoformat(),
                "health": peer["health"]
            }
            for peer_id, peer in self.peers.items()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get gossip protocol statistics"""
        return {
            "ralph_id": self.ralph_id,
            "peers": len(self.peers),
            "messages_seen": len(self.seen_messages),
            "messages_buffered": len(self.message_buffer),
            "running": self._running
        }
