"""
Time-Travel Network Replay Module

Provides recording and replay of network state over time,
enabling "time travel" debugging and training.
"""

from .network_recorder import (
    NetworkRecorder,
    NetworkSnapshot,
    ProtocolEvent,
    EventType,
    RecordingSession,
    get_network_recorder,
    record_snapshot,
    record_event,
    get_snapshots,
    get_events,
    replay_to_time,
)

__all__ = [
    "NetworkRecorder",
    "NetworkSnapshot",
    "ProtocolEvent",
    "EventType",
    "RecordingSession",
    "get_network_recorder",
    "record_snapshot",
    "record_event",
    "get_snapshots",
    "get_events",
    "replay_to_time",
]
