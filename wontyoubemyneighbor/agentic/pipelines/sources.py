"""
Data Sources

Provides:
- Data source definitions
- Source connectors
- Data extraction
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, AsyncIterator, Iterator
from datetime import datetime
from enum import Enum
import asyncio
import json


class SourceType(Enum):
    """Types of data sources"""
    API = "api"
    DATABASE = "database"
    FILE = "file"
    STREAM = "stream"
    QUEUE = "queue"
    WEBHOOK = "webhook"
    SNMP = "snmp"
    NETCONF = "netconf"
    CLI = "cli"
    SYSLOG = "syslog"


@dataclass
class SourceConfig:
    """Data source configuration"""

    connection_string: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    query: Optional[str] = None
    path: Optional[str] = None
    batch_size: int = 100
    timeout_seconds: int = 30
    retry_count: int = 3
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
            "query": self.query,
            "path": self.path,
            "batch_size": self.batch_size,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "extra": self.extra
        }


@dataclass
class ExtractResult:
    """Result of data extraction"""

    source_id: str
    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    record_count: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "success": self.success,
            "record_count": self.record_count,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


@dataclass
class DataSource:
    """Data source definition"""

    id: str
    name: str
    source_type: SourceType
    description: str = ""
    config: SourceConfig = field(default_factory=SourceConfig)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_extract_at: Optional[datetime] = None
    extract_count: int = 0
    error_count: int = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_extract_at": self.last_extract_at.isoformat() if self.last_extract_at else None,
            "extract_count": self.extract_count,
            "error_count": self.error_count,
            "tags": self.tags
        }


class SourceManager:
    """Manages data sources"""

    def __init__(self):
        self.sources: Dict[str, DataSource] = {}
        self._extractors: Dict[SourceType, callable] = {}
        self._register_builtin_extractors()

    def _register_builtin_extractors(self) -> None:
        """Register built-in data extractors"""

        async def api_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from API (simulated)"""
            # Simulated API response
            return [
                {"id": i, "timestamp": datetime.now().isoformat(), "value": f"data_{i}"}
                for i in range(source.config.batch_size)
            ]

        async def database_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from database (simulated)"""
            query = source.config.query or "SELECT * FROM data"
            # Simulated query result
            return [
                {"row_id": i, "query": query, "result": f"row_{i}"}
                for i in range(min(source.config.batch_size, 50))
            ]

        async def file_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from file (simulated)"""
            path = source.config.path or "/data/input.json"
            # Simulated file content
            return [
                {"file": path, "line": i, "content": f"line_{i}"}
                for i in range(min(source.config.batch_size, 100))
            ]

        async def stream_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from stream (simulated)"""
            # Simulated stream data
            return [
                {"stream": source.name, "sequence": i, "payload": f"event_{i}"}
                for i in range(min(source.config.batch_size, 20))
            ]

        async def snmp_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data via SNMP (simulated)"""
            host = source.config.host or "192.168.1.1"
            # Simulated SNMP data
            return [
                {"host": host, "oid": f"1.3.6.1.2.1.{i}", "value": f"snmp_value_{i}"}
                for i in range(min(source.config.batch_size, 30))
            ]

        async def netconf_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data via NETCONF (simulated)"""
            host = source.config.host or "192.168.1.1"
            # Simulated NETCONF data
            return [
                {
                    "host": host,
                    "xpath": "/interfaces/interface",
                    "data": {"name": f"eth{i}", "status": "up"}
                }
                for i in range(min(source.config.batch_size, 10))
            ]

        async def cli_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data via CLI (simulated)"""
            command = source.config.query or "show interfaces"
            # Simulated CLI output
            return [
                {"command": command, "output": f"Interface eth{i}: up"}
                for i in range(min(source.config.batch_size, 10))
            ]

        async def syslog_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from syslog (simulated)"""
            # Simulated syslog messages
            return [
                {
                    "timestamp": datetime.now().isoformat(),
                    "facility": "local0",
                    "severity": "info",
                    "message": f"Log message {i}"
                }
                for i in range(min(source.config.batch_size, 50))
            ]

        async def queue_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from queue (simulated)"""
            # Simulated queue messages
            return [
                {"queue": source.name, "message_id": i, "body": f"message_{i}"}
                for i in range(min(source.config.batch_size, 20))
            ]

        async def webhook_extractor(source: DataSource) -> List[Dict[str, Any]]:
            """Extract data from webhook buffer (simulated)"""
            # Simulated webhook events
            return [
                {"event_type": "network_event", "payload": {"index": i}}
                for i in range(min(source.config.batch_size, 10))
            ]

        self._extractors = {
            SourceType.API: api_extractor,
            SourceType.DATABASE: database_extractor,
            SourceType.FILE: file_extractor,
            SourceType.STREAM: stream_extractor,
            SourceType.SNMP: snmp_extractor,
            SourceType.NETCONF: netconf_extractor,
            SourceType.CLI: cli_extractor,
            SourceType.SYSLOG: syslog_extractor,
            SourceType.QUEUE: queue_extractor,
            SourceType.WEBHOOK: webhook_extractor
        }

    def register_extractor(
        self,
        source_type: SourceType,
        extractor: callable
    ) -> None:
        """Register a custom data extractor"""
        self._extractors[source_type] = extractor

    def create_source(
        self,
        name: str,
        source_type: SourceType,
        description: str = "",
        config: Optional[SourceConfig] = None,
        tags: Optional[List[str]] = None
    ) -> DataSource:
        """Create a new data source"""
        source_id = f"src_{uuid.uuid4().hex[:8]}"

        source = DataSource(
            id=source_id,
            name=name,
            source_type=source_type,
            description=description,
            config=config or SourceConfig(),
            tags=tags or []
        )

        self.sources[source_id] = source
        return source

    def get_source(self, source_id: str) -> Optional[DataSource]:
        """Get source by ID"""
        return self.sources.get(source_id)

    def update_source(
        self,
        source_id: str,
        **kwargs
    ) -> Optional[DataSource]:
        """Update source properties"""
        source = self.sources.get(source_id)
        if not source:
            return None

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        source.updated_at = datetime.now()
        return source

    def delete_source(self, source_id: str) -> bool:
        """Delete a source"""
        if source_id in self.sources:
            del self.sources[source_id]
            return True
        return False

    def enable_source(self, source_id: str) -> bool:
        """Enable a source"""
        source = self.sources.get(source_id)
        if source:
            source.enabled = True
            source.updated_at = datetime.now()
            return True
        return False

    def disable_source(self, source_id: str) -> bool:
        """Disable a source"""
        source = self.sources.get(source_id)
        if source:
            source.enabled = False
            source.updated_at = datetime.now()
            return True
        return False

    async def extract(self, source_id: str) -> ExtractResult:
        """Extract data from a source"""
        source = self.sources.get(source_id)
        if not source:
            return ExtractResult(
                source_id=source_id,
                success=False,
                error="Source not found"
            )

        if not source.enabled:
            return ExtractResult(
                source_id=source_id,
                success=False,
                error="Source is disabled"
            )

        extractor = self._extractors.get(source.source_type)
        if not extractor:
            return ExtractResult(
                source_id=source_id,
                success=False,
                error=f"No extractor for type: {source.source_type.value}"
            )

        started_at = datetime.now()
        try:
            # Execute with timeout
            data = await asyncio.wait_for(
                extractor(source),
                timeout=source.config.timeout_seconds
            )

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            source.last_extract_at = completed_at
            source.extract_count += 1

            return ExtractResult(
                source_id=source_id,
                success=True,
                data=data,
                record_count=len(data),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                metadata={"source_type": source.source_type.value}
            )

        except asyncio.TimeoutError:
            source.error_count += 1
            return ExtractResult(
                source_id=source_id,
                success=False,
                error=f"Extraction timed out after {source.config.timeout_seconds}s",
                started_at=started_at,
                completed_at=datetime.now()
            )
        except Exception as e:
            source.error_count += 1
            return ExtractResult(
                source_id=source_id,
                success=False,
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now()
            )

    def get_sources(
        self,
        source_type: Optional[SourceType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[DataSource]:
        """Get sources with filtering"""
        sources = list(self.sources.values())

        if source_type:
            sources = [s for s in sources if s.source_type == source_type]
        if enabled_only:
            sources = [s for s in sources if s.enabled]
        if tag:
            sources = [s for s in sources if tag in s.tags]

        return sources

    def test_connection(self, source_id: str) -> Dict[str, Any]:
        """Test source connection (simulated)"""
        source = self.sources.get(source_id)
        if not source:
            return {"success": False, "error": "Source not found"}

        # Simulated connection test
        return {
            "success": True,
            "source_id": source_id,
            "source_type": source.source_type.value,
            "latency_ms": 15.5,
            "message": "Connection successful"
        }

    def get_statistics(self) -> dict:
        """Get source statistics"""
        by_type = {}
        total_extracts = 0
        total_errors = 0

        for source in self.sources.values():
            by_type[source.source_type.value] = by_type.get(source.source_type.value, 0) + 1
            total_extracts += source.extract_count
            total_errors += source.error_count

        return {
            "total_sources": len(self.sources),
            "enabled_sources": len([s for s in self.sources.values() if s.enabled]),
            "by_type": by_type,
            "total_extracts": total_extracts,
            "total_errors": total_errors,
            "available_extractors": len(self._extractors)
        }


# Global source manager instance
_source_manager: Optional[SourceManager] = None


def get_source_manager() -> SourceManager:
    """Get or create the global source manager"""
    global _source_manager
    if _source_manager is None:
        _source_manager = SourceManager()
    return _source_manager
