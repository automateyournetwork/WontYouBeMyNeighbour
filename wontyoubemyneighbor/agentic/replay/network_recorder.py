"""
Network Recorder for Time-Travel Replay

Records network state over time and enables replaying
to any previous point for debugging and training.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import copy

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of protocol events."""
    # OSPF events
    OSPF_NEIGHBOR_UP = "ospf_neighbor_up"
    OSPF_NEIGHBOR_DOWN = "ospf_neighbor_down"
    OSPF_NEIGHBOR_STATE_CHANGE = "ospf_neighbor_state_change"
    OSPF_LSA_RECEIVED = "ospf_lsa_received"
    OSPF_SPF_RUN = "ospf_spf_run"
    OSPF_ROUTE_ADD = "ospf_route_add"
    OSPF_ROUTE_REMOVE = "ospf_route_remove"

    # BGP events
    BGP_PEER_UP = "bgp_peer_up"
    BGP_PEER_DOWN = "bgp_peer_down"
    BGP_PEER_STATE_CHANGE = "bgp_peer_state_change"
    BGP_ROUTE_RECEIVED = "bgp_route_received"
    BGP_ROUTE_WITHDRAWN = "bgp_route_withdrawn"
    BGP_ROUTE_BEST = "bgp_route_best"

    # ISIS events
    ISIS_ADJACENCY_UP = "isis_adjacency_up"
    ISIS_ADJACENCY_DOWN = "isis_adjacency_down"
    ISIS_LSP_RECEIVED = "isis_lsp_received"
    ISIS_SPF_RUN = "isis_spf_run"

    # LLDP events
    LLDP_NEIGHBOR_DISCOVERED = "lldp_neighbor_discovered"
    LLDP_NEIGHBOR_LOST = "lldp_neighbor_lost"

    # Interface events
    INTERFACE_UP = "interface_up"
    INTERFACE_DOWN = "interface_down"
    INTERFACE_FLAP = "interface_flap"

    # General events
    CONFIG_CHANGE = "config_change"
    TEST_STARTED = "test_started"
    TEST_COMPLETED = "test_completed"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"


@dataclass
class ProtocolEvent:
    """A single protocol event."""
    event_id: str
    timestamp: datetime
    event_type: EventType
    agent_id: str
    protocol: str
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info, warning, error
    source_ip: Optional[str] = None
    target_ip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "protocol": self.protocol,
            "description": self.description,
            "details": self.details,
            "severity": self.severity,
            "source_ip": self.source_ip,
            "target_ip": self.target_ip,
        }


@dataclass
class NetworkSnapshot:
    """A snapshot of network state at a point in time."""
    snapshot_id: str
    timestamp: datetime
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    topology: Dict[str, Any] = field(default_factory=dict)
    routes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    neighbors: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    protocols: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "agents": self.agents,
            "topology": self.topology,
            "routes": self.routes,
            "neighbors": self.neighbors,
            "protocols": self.protocols,
            "agent_count": len(self.agents),
            "route_count": sum(len(r) for r in self.routes.values()),
        }


@dataclass
class RecordingSession:
    """A recording session."""
    session_id: str
    name: str
    description: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    active: bool = True
    snapshot_interval_seconds: int = 30
    snapshot_count: int = 0
    event_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        duration = None
        if self.ended_at:
            duration = (self.ended_at - self.started_at).total_seconds()
        elif self.active:
            duration = (datetime.now() - self.started_at).total_seconds()

        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "active": self.active,
            "snapshot_interval_seconds": self.snapshot_interval_seconds,
            "snapshot_count": self.snapshot_count,
            "event_count": self.event_count,
            "duration_seconds": duration,
        }


class NetworkRecorder:
    """
    Network Recorder for Time-Travel functionality.

    Records network state snapshots and protocol events,
    allowing replay to any previous point in time.
    """

    # Singleton instance
    _instance: Optional["NetworkRecorder"] = None

    def __new__(cls) -> "NetworkRecorder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        # Storage
        self._sessions: Dict[str, RecordingSession] = {}
        self._snapshots: Dict[str, List[NetworkSnapshot]] = {}  # session_id -> snapshots
        self._events: Dict[str, List[ProtocolEvent]] = {}  # session_id -> events
        self._current_session: Optional[str] = None

        # Counters
        self._snapshot_counter = 0
        self._event_counter = 0
        self._session_counter = 0

        # Recording task
        self._recording_task: Optional[asyncio.Task] = None

        # Replay state
        self._replay_time: Optional[datetime] = None
        self._replay_snapshot: Optional[NetworkSnapshot] = None

        # Max storage limits
        self._max_snapshots_per_session = 1000
        self._max_events_per_session = 10000
        self._max_sessions = 10

        logger.info("NetworkRecorder initialized")

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        self._session_counter += 1
        return f"session-{self._session_counter:04d}"

    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID."""
        self._snapshot_counter += 1
        return f"snap-{self._snapshot_counter:06d}"

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        return f"event-{self._event_counter:08d}"

    # ==== Session Management ====

    def start_recording(
        self,
        name: str = "Recording",
        description: str = "",
        snapshot_interval: int = 30,
    ) -> RecordingSession:
        """Start a new recording session."""
        # Clean up old sessions if too many
        while len(self._sessions) >= self._max_sessions:
            oldest_id = min(
                self._sessions.keys(),
                key=lambda k: self._sessions[k].started_at
            )
            self._delete_session(oldest_id)

        session_id = self._generate_session_id()
        session = RecordingSession(
            session_id=session_id,
            name=name,
            description=description,
            snapshot_interval_seconds=snapshot_interval,
        )

        self._sessions[session_id] = session
        self._snapshots[session_id] = []
        self._events[session_id] = []
        self._current_session = session_id

        # Start recording task
        self._start_recording_task(session)

        logger.info(f"Started recording session: {name} ({session_id})")
        return session

    def stop_recording(self) -> Optional[RecordingSession]:
        """Stop the current recording session."""
        if not self._current_session:
            return None

        session = self._sessions.get(self._current_session)
        if session:
            session.active = False
            session.ended_at = datetime.now()

            # Cancel recording task
            if self._recording_task:
                self._recording_task.cancel()
                self._recording_task = None

            logger.info(f"Stopped recording session: {session.name}")

        self._current_session = None
        return session

    def _delete_session(self, session_id: str):
        """Delete a session and its data."""
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._snapshots:
            del self._snapshots[session_id]
        if session_id in self._events:
            del self._events[session_id]

    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        """Get a recording session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self, active_only: bool = False) -> List[RecordingSession]:
        """List all recording sessions."""
        sessions = list(self._sessions.values())
        if active_only:
            sessions = [s for s in sessions if s.active]
        return sorted(sessions, key=lambda s: s.started_at, reverse=True)

    def _start_recording_task(self, session: RecordingSession):
        """Start the periodic snapshot recording task."""
        async def recording_loop():
            while session.active:
                try:
                    # Take a snapshot
                    await self._take_snapshot(session.session_id)
                    await asyncio.sleep(session.snapshot_interval_seconds)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Recording error: {e}")
                    await asyncio.sleep(5)

        try:
            loop = asyncio.get_event_loop()
            self._recording_task = loop.create_task(recording_loop())
        except RuntimeError:
            # No event loop running
            pass

    # ==== Snapshot Management ====

    async def _take_snapshot(self, session_id: str):
        """Take a snapshot of current network state."""
        if session_id not in self._sessions:
            return

        session = self._sessions[session_id]
        snapshots = self._snapshots[session_id]

        # Enforce max snapshots
        while len(snapshots) >= self._max_snapshots_per_session:
            snapshots.pop(0)

        # Capture current state
        snapshot = await self._capture_network_state()
        snapshots.append(snapshot)
        session.snapshot_count = len(snapshots)

        logger.debug(f"Snapshot taken: {snapshot.snapshot_id}")

    async def _capture_network_state(self) -> NetworkSnapshot:
        """Capture the current network state."""
        snapshot_id = self._generate_snapshot_id()

        # Create snapshot with demo data (in production, would query actual agents)
        snapshot = NetworkSnapshot(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(),
            agents=self._capture_agents(),
            topology=self._capture_topology(),
            routes=self._capture_routes(),
            neighbors=self._capture_neighbors(),
            protocols=self._capture_protocols(),
        )

        return snapshot

    def _capture_agents(self) -> Dict[str, Dict[str, Any]]:
        """Capture agent states."""
        # Demo data - in production would query actual agents
        return {
            "router-1": {
                "name": "Core Router",
                "status": "running",
                "uptime": 3600,
                "cpu_percent": 15 + (hash(str(datetime.now())) % 10),
                "memory_percent": 40 + (hash(str(datetime.now())) % 15),
            },
            "router-2": {
                "name": "Edge Router",
                "status": "running",
                "uptime": 3500,
                "cpu_percent": 20 + (hash(str(datetime.now())) % 12),
                "memory_percent": 35 + (hash(str(datetime.now())) % 20),
            },
        }

    def _capture_topology(self) -> Dict[str, Any]:
        """Capture topology."""
        return {
            "nodes": [
                {"id": "router-1", "type": "router", "status": "up"},
                {"id": "router-2", "type": "router", "status": "up"},
                {"id": "switch-1", "type": "switch", "status": "up"},
            ],
            "links": [
                {"source": "router-1", "target": "router-2", "status": "up"},
                {"source": "router-1", "target": "switch-1", "status": "up"},
            ],
        }

    def _capture_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Capture routing tables."""
        return {
            "router-1": [
                {"prefix": "10.0.0.0/24", "next_hop": "10.0.1.2", "protocol": "ospf", "metric": 10},
                {"prefix": "10.0.2.0/24", "next_hop": "10.0.1.3", "protocol": "bgp", "metric": 20},
            ],
            "router-2": [
                {"prefix": "10.0.1.0/24", "next_hop": "10.0.0.1", "protocol": "ospf", "metric": 10},
            ],
        }

    def _capture_neighbors(self) -> Dict[str, List[Dict[str, Any]]]:
        """Capture neighbor relationships."""
        return {
            "router-1": [
                {"neighbor": "router-2", "protocol": "ospf", "state": "FULL", "interface": "eth0"},
            ],
            "router-2": [
                {"neighbor": "router-1", "protocol": "ospf", "state": "FULL", "interface": "eth0"},
            ],
        }

    def _capture_protocols(self) -> Dict[str, Dict[str, Any]]:
        """Capture protocol states."""
        return {
            "ospf": {
                "neighbors": 2,
                "full_neighbors": 2,
                "lsdb_size": 15,
                "spf_runs": 3,
            },
            "bgp": {
                "peers": 1,
                "established_peers": 1,
                "received_prefixes": 5,
                "advertised_prefixes": 3,
            },
        }

    def record_snapshot(self) -> Optional[NetworkSnapshot]:
        """Manually record a snapshot."""
        if not self._current_session:
            return None

        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._take_snapshot(self._current_session))
        except RuntimeError:
            # Synchronous fallback
            snapshot_id = self._generate_snapshot_id()
            snapshot = NetworkSnapshot(
                snapshot_id=snapshot_id,
                timestamp=datetime.now(),
                agents=self._capture_agents(),
                topology=self._capture_topology(),
                routes=self._capture_routes(),
                neighbors=self._capture_neighbors(),
                protocols=self._capture_protocols(),
            )
            if self._current_session in self._snapshots:
                self._snapshots[self._current_session].append(snapshot)
            return snapshot

    def get_snapshots(
        self,
        session_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[NetworkSnapshot]:
        """Get snapshots with optional filtering."""
        sid = session_id or self._current_session
        if not sid or sid not in self._snapshots:
            return []

        snapshots = self._snapshots[sid]

        if start_time:
            snapshots = [s for s in snapshots if s.timestamp >= start_time]
        if end_time:
            snapshots = [s for s in snapshots if s.timestamp <= end_time]

        return snapshots[-limit:]

    # ==== Event Recording ====

    def record_event(
        self,
        event_type: EventType,
        agent_id: str,
        protocol: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        source_ip: Optional[str] = None,
        target_ip: Optional[str] = None,
    ) -> Optional[ProtocolEvent]:
        """Record a protocol event."""
        if not self._current_session:
            return None

        events = self._events.get(self._current_session)
        if events is None:
            return None

        # Enforce max events
        while len(events) >= self._max_events_per_session:
            events.pop(0)

        event = ProtocolEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(),
            event_type=event_type,
            agent_id=agent_id,
            protocol=protocol,
            description=description,
            details=details or {},
            severity=severity,
            source_ip=source_ip,
            target_ip=target_ip,
        )

        events.append(event)
        session = self._sessions.get(self._current_session)
        if session:
            session.event_count = len(events)

        logger.debug(f"Event recorded: {event_type.value} - {description}")
        return event

    def get_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        agent_id: Optional[str] = None,
        protocol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ProtocolEvent]:
        """Get events with optional filtering."""
        sid = session_id or self._current_session
        if not sid or sid not in self._events:
            return []

        events = self._events[sid]

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        if protocol:
            events = [e for e in events if e.protocol == protocol]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events[-limit:]

    # ==== Replay Functionality ====

    def replay_to_time(
        self,
        target_time: datetime,
        session_id: Optional[str] = None,
    ) -> Optional[NetworkSnapshot]:
        """
        Replay to a specific point in time.

        Returns the network snapshot closest to (but not after) the target time.
        """
        sid = session_id or self._current_session
        if not sid or sid not in self._snapshots:
            return None

        snapshots = self._snapshots[sid]
        if not snapshots:
            return None

        # Find the closest snapshot before or at target_time
        best_snapshot = None
        for snapshot in snapshots:
            if snapshot.timestamp <= target_time:
                best_snapshot = snapshot
            else:
                break

        if best_snapshot:
            self._replay_time = target_time
            self._replay_snapshot = copy.deepcopy(best_snapshot)
            logger.info(f"Replayed to {target_time.isoformat()}, snapshot: {best_snapshot.snapshot_id}")

        return self._replay_snapshot

    def get_replay_state(self) -> Optional[Dict[str, Any]]:
        """Get the current replay state."""
        if not self._replay_snapshot:
            return None

        return {
            "replay_time": self._replay_time.isoformat() if self._replay_time else None,
            "snapshot": self._replay_snapshot.to_dict(),
        }

    def clear_replay(self):
        """Clear the replay state."""
        self._replay_time = None
        self._replay_snapshot = None

    def get_timeline(
        self,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get the recording timeline with snapshots and events.

        Returns a summary for timeline visualization.
        """
        sid = session_id or self._current_session
        if not sid:
            return {"error": "No session specified"}

        session = self._sessions.get(sid)
        snapshots = self._snapshots.get(sid, [])
        events = self._events.get(sid, [])

        if not session:
            return {"error": "Session not found"}

        # Build timeline entries
        timeline = []

        for snapshot in snapshots:
            timeline.append({
                "type": "snapshot",
                "timestamp": snapshot.timestamp.isoformat(),
                "id": snapshot.snapshot_id,
                "agent_count": len(snapshot.agents),
            })

        for event in events:
            timeline.append({
                "type": "event",
                "timestamp": event.timestamp.isoformat(),
                "id": event.event_id,
                "event_type": event.event_type.value,
                "description": event.description,
                "severity": event.severity,
                "agent_id": event.agent_id,
            })

        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])

        return {
            "session": session.to_dict(),
            "timeline": timeline,
            "total_snapshots": len(snapshots),
            "total_events": len(events),
            "start_time": session.started_at.isoformat(),
            "end_time": session.ended_at.isoformat() if session.ended_at else None,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get recorder statistics."""
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len([s for s in self._sessions.values() if s.active]),
            "current_session": self._current_session,
            "total_snapshots": sum(len(s) for s in self._snapshots.values()),
            "total_events": sum(len(e) for e in self._events.values()),
            "is_replaying": self._replay_snapshot is not None,
            "replay_time": self._replay_time.isoformat() if self._replay_time else None,
        }


# Singleton accessor
def get_network_recorder() -> NetworkRecorder:
    """Get the network recorder instance."""
    return NetworkRecorder()


# Convenience functions
def record_snapshot() -> Optional[NetworkSnapshot]:
    """Record a snapshot of current network state."""
    return get_network_recorder().record_snapshot()


def record_event(
    event_type: EventType,
    agent_id: str,
    protocol: str,
    description: str,
    **kwargs,
) -> Optional[ProtocolEvent]:
    """Record a protocol event."""
    return get_network_recorder().record_event(
        event_type=event_type,
        agent_id=agent_id,
        protocol=protocol,
        description=description,
        **kwargs,
    )


def get_snapshots(
    session_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get snapshots as dictionaries."""
    snapshots = get_network_recorder().get_snapshots(session_id=session_id, limit=limit)
    return [s.to_dict() for s in snapshots]


def get_events(
    session_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get events as dictionaries."""
    events = get_network_recorder().get_events(session_id=session_id, limit=limit)
    return [e.to_dict() for e in events]


def replay_to_time(target_time: datetime) -> Optional[Dict[str, Any]]:
    """Replay to a specific time and return the snapshot."""
    snapshot = get_network_recorder().replay_to_time(target_time)
    return snapshot.to_dict() if snapshot else None
