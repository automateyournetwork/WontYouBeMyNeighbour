"""
Backup Module - Network backup management

Provides:
- Full and incremental backups
- Backup metadata tracking
- Compression support
- Backup verification
"""

import logging
import hashlib
import json
import gzip
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("BackupManager")


class BackupType(str, Enum):
    """Types of backups"""
    FULL = "full"               # Complete snapshot
    INCREMENTAL = "incremental" # Changes since last backup
    DIFFERENTIAL = "differential" # Changes since last full backup
    AGENT = "agent"             # Single agent backup
    NETWORK = "network"         # Full network backup
    CONFIG = "config"           # Configuration only


class BackupStatus(str, Enum):
    """Backup status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"


@dataclass
class BackupMetadata:
    """
    Metadata for a backup

    Attributes:
        version: Backup format version
        created_by: User/system that created backup
        network_id: Network identifier
        agent_count: Number of agents backed up
        protocol_count: Number of protocols configured
        total_routes: Total routes in backup
        compressed: Whether backup is compressed
        encrypted: Whether backup is encrypted
        checksum: SHA256 checksum of content
    """
    version: str = "1.0"
    created_by: str = "system"
    network_id: str = ""
    agent_count: int = 0
    protocol_count: int = 0
    total_routes: int = 0
    compressed: bool = True
    encrypted: bool = False
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_by": self.created_by,
            "network_id": self.network_id,
            "agent_count": self.agent_count,
            "protocol_count": self.protocol_count,
            "total_routes": self.total_routes,
            "compressed": self.compressed,
            "encrypted": self.encrypted,
            "checksum": self.checksum
        }


@dataclass
class Backup:
    """
    A backup record

    Attributes:
        id: Backup identifier
        name: Human-readable name
        backup_type: Type of backup
        status: Backup status
        metadata: Backup metadata
        file_path: Path to backup file
        size_bytes: Backup file size
        created_at: Creation timestamp
        completed_at: Completion timestamp
        error_message: Error if failed
        parent_backup_id: Parent for incremental
        tags: Searchable tags
    """
    id: str
    name: str
    backup_type: BackupType
    status: BackupStatus = BackupStatus.PENDING
    metadata: BackupMetadata = field(default_factory=BackupMetadata)
    file_path: str = ""
    size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: str = ""
    parent_backup_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status in [BackupStatus.COMPLETED, BackupStatus.VERIFIED]

    @property
    def duration_seconds(self) -> int:
        if self.completed_at:
            return int((self.completed_at - self.created_at).total_seconds())
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "backup_type": self.backup_type.value,
            "status": self.status.value,
            "metadata": self.metadata.to_dict(),
            "file_path": self.file_path,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1024 * 1024), 2),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "parent_backup_id": self.parent_backup_id,
            "tags": self.tags
        }


class BackupManager:
    """
    Manages backup operations
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize backup manager

        Args:
            storage_path: Path to backup storage directory
        """
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            self._storage_path = Path.home() / ".asi" / "backups"

        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._backups: Dict[str, Backup] = {}
        self._backup_counter = 0
        self._load_existing_backups()

    def _load_existing_backups(self):
        """Load backup metadata from storage"""
        index_path = self._storage_path / "backup_index.json"
        if index_path.exists():
            try:
                with open(index_path, "r") as f:
                    data = json.load(f)
                    self._backup_counter = data.get("counter", 0)
                    for backup_data in data.get("backups", []):
                        backup = self._deserialize_backup(backup_data)
                        if backup:
                            self._backups[backup.id] = backup
                logger.info(f"Loaded {len(self._backups)} existing backups")
            except Exception as e:
                logger.error(f"Failed to load backup index: {e}")

    def _save_index(self):
        """Save backup index to storage"""
        index_path = self._storage_path / "backup_index.json"
        try:
            data = {
                "counter": self._backup_counter,
                "backups": [self._serialize_backup(b) for b in self._backups.values()]
            }
            with open(index_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save backup index: {e}")

    def _serialize_backup(self, backup: Backup) -> Dict[str, Any]:
        """Serialize backup for storage"""
        return backup.to_dict()

    def _deserialize_backup(self, data: Dict[str, Any]) -> Optional[Backup]:
        """Deserialize backup from storage"""
        try:
            metadata = BackupMetadata(**data.get("metadata", {}))
            backup = Backup(
                id=data["id"],
                name=data["name"],
                backup_type=BackupType(data["backup_type"]),
                status=BackupStatus(data["status"]),
                metadata=metadata,
                file_path=data.get("file_path", ""),
                size_bytes=data.get("size_bytes", 0),
                error_message=data.get("error_message", ""),
                parent_backup_id=data.get("parent_backup_id"),
                tags=data.get("tags", [])
            )
            backup.created_at = datetime.fromisoformat(data["created_at"])
            if data.get("completed_at"):
                backup.completed_at = datetime.fromisoformat(data["completed_at"])
            return backup
        except Exception as e:
            logger.error(f"Failed to deserialize backup: {e}")
            return None

    def create_backup(
        self,
        name: str,
        backup_type: BackupType = BackupType.FULL,
        content: Dict[str, Any] = None,
        created_by: str = "system",
        tags: Optional[List[str]] = None,
        parent_backup_id: Optional[str] = None
    ) -> Backup:
        """
        Create a new backup

        Args:
            name: Backup name
            backup_type: Type of backup
            content: Content to backup (agents, networks, etc.)
            created_by: Creator identifier
            tags: Searchable tags
            parent_backup_id: Parent backup for incremental

        Returns:
            Created backup object
        """
        self._backup_counter += 1
        backup_id = f"backup-{self._backup_counter:05d}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{backup_id}_{timestamp}.toon.gz"
        file_path = str(self._storage_path / filename)

        # Create metadata
        metadata = BackupMetadata(
            created_by=created_by,
            compressed=True
        )

        if content:
            # Extract metadata from content
            if "network" in content:
                metadata.network_id = content["network"].get("id", "")
            if "agents" in content:
                metadata.agent_count = len(content["agents"])
            if "protocols" in content:
                metadata.protocol_count = len(content["protocols"])
            if "routes" in content:
                metadata.total_routes = len(content["routes"])

        backup = Backup(
            id=backup_id,
            name=name,
            backup_type=backup_type,
            status=BackupStatus.IN_PROGRESS,
            metadata=metadata,
            file_path=file_path,
            parent_backup_id=parent_backup_id,
            tags=tags or []
        )

        self._backups[backup_id] = backup

        # Write backup content
        if content:
            try:
                self._write_backup(backup, content)
                backup.status = BackupStatus.COMPLETED
                backup.completed_at = datetime.now()
            except Exception as e:
                backup.status = BackupStatus.FAILED
                backup.error_message = str(e)
                logger.error(f"Backup failed: {e}")

        self._save_index()
        logger.info(f"Created backup {backup_id}: {name}")
        return backup

    def _write_backup(self, backup: Backup, content: Dict[str, Any]):
        """Write backup content to file"""
        # Serialize to JSON
        json_content = json.dumps(content, indent=2, default=str)

        # Calculate checksum
        checksum = hashlib.sha256(json_content.encode()).hexdigest()
        backup.metadata.checksum = checksum

        # Compress and write
        if backup.metadata.compressed:
            with gzip.open(backup.file_path, "wt", encoding="utf-8") as f:
                f.write(json_content)
        else:
            with open(backup.file_path, "w") as f:
                f.write(json_content)

        # Update size
        backup.size_bytes = os.path.getsize(backup.file_path)

    def read_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """
        Read backup content

        Args:
            backup_id: Backup identifier

        Returns:
            Backup content or None
        """
        backup = self.get_backup(backup_id)
        if not backup or not backup.is_complete:
            return None

        if not os.path.exists(backup.file_path):
            logger.error(f"Backup file not found: {backup.file_path}")
            return None

        try:
            if backup.metadata.compressed:
                with gzip.open(backup.file_path, "rt", encoding="utf-8") as f:
                    content = json.load(f)
            else:
                with open(backup.file_path, "r") as f:
                    content = json.load(f)
            return content
        except Exception as e:
            logger.error(f"Failed to read backup {backup_id}: {e}")
            return None

    def verify_backup(self, backup_id: str) -> bool:
        """
        Verify backup integrity

        Args:
            backup_id: Backup identifier

        Returns:
            True if backup is valid
        """
        backup = self.get_backup(backup_id)
        if not backup or not backup.is_complete:
            return False

        content = self.read_backup(backup_id)
        if not content:
            backup.status = BackupStatus.CORRUPTED
            self._save_index()
            return False

        # Verify checksum
        json_content = json.dumps(content, indent=2, default=str)
        checksum = hashlib.sha256(json_content.encode()).hexdigest()

        if checksum == backup.metadata.checksum:
            backup.status = BackupStatus.VERIFIED
            self._save_index()
            logger.info(f"Backup {backup_id} verified successfully")
            return True
        else:
            backup.status = BackupStatus.CORRUPTED
            self._save_index()
            logger.warning(f"Backup {backup_id} checksum mismatch")
            return False

    def get_backup(self, backup_id: str) -> Optional[Backup]:
        """Get backup by ID"""
        return self._backups.get(backup_id)

    def list_backups(
        self,
        backup_type: Optional[BackupType] = None,
        status: Optional[BackupStatus] = None,
        network_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Backup]:
        """List backups with optional filters"""
        backups = list(self._backups.values())

        if backup_type:
            backups = [b for b in backups if b.backup_type == backup_type]

        if status:
            backups = [b for b in backups if b.status == status]

        if network_id:
            backups = [b for b in backups if b.metadata.network_id == network_id]

        if tags:
            backups = [b for b in backups if any(t in b.tags for t in tags)]

        # Sort by created_at descending
        backups.sort(key=lambda b: b.created_at, reverse=True)

        return backups[:limit]

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup"""
        backup = self.get_backup(backup_id)
        if not backup:
            return False

        # Delete file if exists
        if os.path.exists(backup.file_path):
            try:
                os.remove(backup.file_path)
            except Exception as e:
                logger.error(f"Failed to delete backup file: {e}")

        del self._backups[backup_id]
        self._save_index()
        logger.info(f"Deleted backup {backup_id}")
        return True

    def get_latest_backup(
        self,
        backup_type: Optional[BackupType] = None,
        network_id: Optional[str] = None
    ) -> Optional[Backup]:
        """Get the most recent backup"""
        backups = self.list_backups(
            backup_type=backup_type,
            network_id=network_id,
            status=BackupStatus.COMPLETED,
            limit=1
        )
        return backups[0] if backups else None

    def get_backup_chain(self, backup_id: str) -> List[Backup]:
        """Get backup chain (for incremental backups)"""
        chain = []
        current_id = backup_id

        while current_id:
            backup = self.get_backup(current_id)
            if not backup:
                break
            chain.append(backup)
            current_id = backup.parent_backup_id

        chain.reverse()  # Oldest first
        return chain

    def cleanup_old_backups(
        self,
        keep_count: int = 10,
        keep_days: int = 30
    ) -> int:
        """
        Clean up old backups

        Args:
            keep_count: Keep at least this many backups
            keep_days: Keep backups newer than this many days

        Returns:
            Number of backups deleted
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=keep_days)
        backups = list(self._backups.values())
        backups.sort(key=lambda b: b.created_at, reverse=True)

        # Keep at least keep_count backups
        protected = set(b.id for b in backups[:keep_count])

        deleted_count = 0
        for backup in backups:
            if backup.id in protected:
                continue
            if backup.created_at < cutoff_date:
                if self.delete_backup(backup.id):
                    deleted_count += 1

        return deleted_count

    def get_statistics(self) -> Dict[str, Any]:
        """Get backup statistics"""
        total = len(self._backups)
        by_type = {}
        by_status = {}
        total_size = 0

        for backup in self._backups.values():
            btype = backup.backup_type.value
            bstatus = backup.status.value

            by_type[btype] = by_type.get(btype, 0) + 1
            by_status[bstatus] = by_status.get(bstatus, 0) + 1
            total_size += backup.size_bytes

        return {
            "total_backups": total,
            "by_type": by_type,
            "by_status": by_status,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "storage_path": str(self._storage_path)
        }


# Global backup manager instance
_global_manager: Optional[BackupManager] = None


def get_backup_manager() -> BackupManager:
    """Get or create the global backup manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = BackupManager()
    return _global_manager
