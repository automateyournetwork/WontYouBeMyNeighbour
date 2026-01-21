"""
Data Sinks

Provides:
- Data sink definitions
- Sink connectors
- Data loading/output
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import asyncio
import json


class SinkType(Enum):
    """Types of data sinks"""
    API = "api"
    DATABASE = "database"
    FILE = "file"
    STREAM = "stream"
    QUEUE = "queue"
    WEBHOOK = "webhook"
    EMAIL = "email"
    LOG = "log"
    METRICS = "metrics"
    ALERT = "alert"


@dataclass
class SinkConfig:
    """Data sink configuration"""

    connection_string: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    path: Optional[str] = None
    table: Optional[str] = None
    batch_size: int = 100
    timeout_seconds: int = 30
    retry_count: int = 3
    mode: str = "append"  # append, overwrite, upsert
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "connection_string": self.connection_string,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "has_password": bool(self.password),
            "has_api_key": bool(self.api_key),
            "headers": self.headers,
            "path": self.path,
            "table": self.table,
            "batch_size": self.batch_size,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "mode": self.mode,
            "extra": self.extra
        }


@dataclass
class LoadResult:
    """Result of data loading"""

    sink_id: str
    success: bool
    records_loaded: int = 0
    records_failed: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sink_id": self.sink_id,
            "success": self.success,
            "records_loaded": self.records_loaded,
            "records_failed": self.records_failed,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


@dataclass
class DataSink:
    """Data sink definition"""

    id: str
    name: str
    sink_type: SinkType
    description: str = ""
    config: SinkConfig = field(default_factory=SinkConfig)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_load_at: Optional[datetime] = None
    load_count: int = 0
    records_total: int = 0
    error_count: int = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "sink_type": self.sink_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_load_at": self.last_load_at.isoformat() if self.last_load_at else None,
            "load_count": self.load_count,
            "records_total": self.records_total,
            "error_count": self.error_count,
            "tags": self.tags
        }


class SinkManager:
    """Manages data sinks"""

    def __init__(self):
        self.sinks: Dict[str, DataSink] = {}
        self._loaders: Dict[SinkType, callable] = {}
        self._register_builtin_loaders()

    def _register_builtin_loaders(self) -> None:
        """Register built-in data loaders"""

        async def api_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Load data to API (simulated)"""
            # Simulated API POST
            return len(data)

        async def database_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Load data to database (simulated)"""
            table = sink.config.table or "data_table"
            # Simulated INSERT
            return len(data)

        async def file_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Load data to file (simulated)"""
            path = sink.config.path or "/data/output.json"
            # Simulated file write
            return len(data)

        async def stream_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Load data to stream (simulated)"""
            # Simulated stream publish
            return len(data)

        async def queue_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Load data to queue (simulated)"""
            # Simulated queue publish
            return len(data)

        async def webhook_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Send data to webhook (simulated)"""
            # Simulated webhook POST
            return len(data)

        async def email_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Send data via email (simulated)"""
            recipients = sink.config.extra.get("recipients", [])
            # Simulated email send
            return len(data)

        async def log_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Write data to log (simulated)"""
            # Simulated log write
            return len(data)

        async def metrics_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Export data as metrics (simulated)"""
            # Simulated metrics export
            return len(data)

        async def alert_loader(
            sink: DataSink,
            data: List[Dict[str, Any]]
        ) -> int:
            """Send data as alerts (simulated)"""
            # Simulated alert generation
            return len(data)

        self._loaders = {
            SinkType.API: api_loader,
            SinkType.DATABASE: database_loader,
            SinkType.FILE: file_loader,
            SinkType.STREAM: stream_loader,
            SinkType.QUEUE: queue_loader,
            SinkType.WEBHOOK: webhook_loader,
            SinkType.EMAIL: email_loader,
            SinkType.LOG: log_loader,
            SinkType.METRICS: metrics_loader,
            SinkType.ALERT: alert_loader
        }

    def register_loader(
        self,
        sink_type: SinkType,
        loader: callable
    ) -> None:
        """Register a custom data loader"""
        self._loaders[sink_type] = loader

    def create_sink(
        self,
        name: str,
        sink_type: SinkType,
        description: str = "",
        config: Optional[SinkConfig] = None,
        tags: Optional[List[str]] = None
    ) -> DataSink:
        """Create a new data sink"""
        sink_id = f"sink_{uuid.uuid4().hex[:8]}"

        sink = DataSink(
            id=sink_id,
            name=name,
            sink_type=sink_type,
            description=description,
            config=config or SinkConfig(),
            tags=tags or []
        )

        self.sinks[sink_id] = sink
        return sink

    def get_sink(self, sink_id: str) -> Optional[DataSink]:
        """Get sink by ID"""
        return self.sinks.get(sink_id)

    def update_sink(
        self,
        sink_id: str,
        **kwargs
    ) -> Optional[DataSink]:
        """Update sink properties"""
        sink = self.sinks.get(sink_id)
        if not sink:
            return None

        for key, value in kwargs.items():
            if hasattr(sink, key):
                setattr(sink, key, value)

        sink.updated_at = datetime.now()
        return sink

    def delete_sink(self, sink_id: str) -> bool:
        """Delete a sink"""
        if sink_id in self.sinks:
            del self.sinks[sink_id]
            return True
        return False

    def enable_sink(self, sink_id: str) -> bool:
        """Enable a sink"""
        sink = self.sinks.get(sink_id)
        if sink:
            sink.enabled = True
            sink.updated_at = datetime.now()
            return True
        return False

    def disable_sink(self, sink_id: str) -> bool:
        """Disable a sink"""
        sink = self.sinks.get(sink_id)
        if sink:
            sink.enabled = False
            sink.updated_at = datetime.now()
            return True
        return False

    async def load(
        self,
        sink_id: str,
        data: List[Dict[str, Any]]
    ) -> LoadResult:
        """Load data to a sink"""
        sink = self.sinks.get(sink_id)
        if not sink:
            return LoadResult(
                sink_id=sink_id,
                success=False,
                error="Sink not found"
            )

        if not sink.enabled:
            return LoadResult(
                sink_id=sink_id,
                success=False,
                error="Sink is disabled"
            )

        if not data:
            return LoadResult(
                sink_id=sink_id,
                success=True,
                records_loaded=0,
                metadata={"message": "No data to load"}
            )

        loader = self._loaders.get(sink.sink_type)
        if not loader:
            return LoadResult(
                sink_id=sink_id,
                success=False,
                error=f"No loader for type: {sink.sink_type.value}"
            )

        started_at = datetime.now()
        try:
            # Load in batches
            batch_size = sink.config.batch_size
            total_loaded = 0

            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                loaded = await asyncio.wait_for(
                    loader(sink, batch),
                    timeout=sink.config.timeout_seconds
                )
                total_loaded += loaded

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            sink.last_load_at = completed_at
            sink.load_count += 1
            sink.records_total += total_loaded

            return LoadResult(
                sink_id=sink_id,
                success=True,
                records_loaded=total_loaded,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                metadata={"sink_type": sink.sink_type.value}
            )

        except asyncio.TimeoutError:
            sink.error_count += 1
            return LoadResult(
                sink_id=sink_id,
                success=False,
                error=f"Load timed out after {sink.config.timeout_seconds}s",
                started_at=started_at,
                completed_at=datetime.now()
            )
        except Exception as e:
            sink.error_count += 1
            return LoadResult(
                sink_id=sink_id,
                success=False,
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now()
            )

    async def load_to_multiple(
        self,
        sink_ids: List[str],
        data: List[Dict[str, Any]]
    ) -> Dict[str, LoadResult]:
        """Load data to multiple sinks"""
        results = {}
        for sink_id in sink_ids:
            results[sink_id] = await self.load(sink_id, data)
        return results

    def get_sinks(
        self,
        sink_type: Optional[SinkType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[DataSink]:
        """Get sinks with filtering"""
        sinks = list(self.sinks.values())

        if sink_type:
            sinks = [s for s in sinks if s.sink_type == sink_type]
        if enabled_only:
            sinks = [s for s in sinks if s.enabled]
        if tag:
            sinks = [s for s in sinks if tag in s.tags]

        return sinks

    def test_connection(self, sink_id: str) -> Dict[str, Any]:
        """Test sink connection (simulated)"""
        sink = self.sinks.get(sink_id)
        if not sink:
            return {"success": False, "error": "Sink not found"}

        # Simulated connection test
        return {
            "success": True,
            "sink_id": sink_id,
            "sink_type": sink.sink_type.value,
            "latency_ms": 12.3,
            "message": "Connection successful"
        }

    def get_statistics(self) -> dict:
        """Get sink statistics"""
        by_type = {}
        total_loads = 0
        total_records = 0
        total_errors = 0

        for sink in self.sinks.values():
            by_type[sink.sink_type.value] = by_type.get(sink.sink_type.value, 0) + 1
            total_loads += sink.load_count
            total_records += sink.records_total
            total_errors += sink.error_count

        return {
            "total_sinks": len(self.sinks),
            "enabled_sinks": len([s for s in self.sinks.values() if s.enabled]),
            "by_type": by_type,
            "total_loads": total_loads,
            "total_records": total_records,
            "total_errors": total_errors,
            "available_loaders": len(self._loaders)
        }


# Global sink manager instance
_sink_manager: Optional[SinkManager] = None


def get_sink_manager() -> SinkManager:
    """Get or create the global sink manager"""
    global _sink_manager
    if _sink_manager is None:
        _sink_manager = SinkManager()
    return _sink_manager
