"""
Configuration Versioning

Provides:
- Version tracking
- Change history
- Diff generation
- Rollback support
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum


class ChangeType(Enum):
    """Type of configuration change"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ROLLBACK = "rollback"


@dataclass
class ConfigChange:
    """Represents a single configuration change"""

    path: str
    change_type: ChangeType
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "old_value": self.old_value,
            "new_value": self.new_value
        }


@dataclass
class ConfigVersion:
    """Represents a configuration version"""

    version_id: str
    namespace: str
    version_number: int
    config_data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    message: str = ""
    changes: List[ConfigChange] = field(default_factory=list)
    parent_version: Optional[str] = None
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of configuration data"""
        config_str = json.dumps(self.config_data, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "namespace": self.namespace,
            "version_number": self.version_number,
            "config_data": self.config_data,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "message": self.message,
            "changes": [c.to_dict() for c in self.changes],
            "parent_version": self.parent_version,
            "hash": self.hash
        }


@dataclass
class ConfigHistory:
    """Configuration history for a namespace"""

    namespace: str
    versions: List[ConfigVersion] = field(default_factory=list)
    current_version: Optional[str] = None

    @property
    def version_count(self) -> int:
        return len(self.versions)

    @property
    def latest_version(self) -> Optional[ConfigVersion]:
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)

    def get_version(self, version_id: str) -> Optional[ConfigVersion]:
        """Get specific version"""
        for version in self.versions:
            if version.version_id == version_id:
                return version
        return None

    def get_version_by_number(self, number: int) -> Optional[ConfigVersion]:
        """Get version by number"""
        for version in self.versions:
            if version.version_number == number:
                return version
        return None

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "version_count": self.version_count,
            "current_version": self.current_version,
            "versions": [v.to_dict() for v in sorted(
                self.versions, key=lambda v: v.version_number, reverse=True
            )]
        }


class VersionManager:
    """Manages configuration versions"""

    def __init__(self):
        self.histories: Dict[str, ConfigHistory] = {}
        self._max_versions = 100

    def create_version(
        self,
        namespace: str,
        config_data: Dict[str, Any],
        created_by: Optional[str] = None,
        message: str = "",
        changes: Optional[List[ConfigChange]] = None
    ) -> ConfigVersion:
        """Create a new configuration version"""
        # Get or create history
        if namespace not in self.histories:
            self.histories[namespace] = ConfigHistory(namespace=namespace)

        history = self.histories[namespace]

        # Determine version number
        version_number = 1
        parent_version = None
        if history.versions:
            latest = history.latest_version
            version_number = latest.version_number + 1
            parent_version = latest.version_id

            # Calculate changes if not provided
            if changes is None:
                changes = self._compute_changes(latest.config_data, config_data)

        # Generate version ID
        version_id = f"v{version_number}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        version = ConfigVersion(
            version_id=version_id,
            namespace=namespace,
            version_number=version_number,
            config_data=config_data,
            created_by=created_by,
            message=message,
            changes=changes or [],
            parent_version=parent_version
        )

        # Add to history
        history.versions.append(version)
        history.current_version = version_id

        # Trim old versions
        if len(history.versions) > self._max_versions:
            history.versions = history.versions[-self._max_versions:]

        return version

    def get_version(self, namespace: str, version_id: str) -> Optional[ConfigVersion]:
        """Get a specific version"""
        history = self.histories.get(namespace)
        if not history:
            return None
        return history.get_version(version_id)

    def get_current_version(self, namespace: str) -> Optional[ConfigVersion]:
        """Get current version for namespace"""
        history = self.histories.get(namespace)
        if not history or not history.current_version:
            return None
        return history.get_version(history.current_version)

    def get_history(self, namespace: str, limit: int = 50) -> List[ConfigVersion]:
        """Get version history for namespace"""
        history = self.histories.get(namespace)
        if not history:
            return []
        return sorted(history.versions, key=lambda v: v.version_number, reverse=True)[:limit]

    def rollback(
        self,
        namespace: str,
        target_version_id: str,
        created_by: Optional[str] = None
    ) -> Optional[ConfigVersion]:
        """Rollback to a previous version"""
        history = self.histories.get(namespace)
        if not history:
            return None

        target = history.get_version(target_version_id)
        if not target:
            return None

        # Create new version with rollback content
        current = self.get_current_version(namespace)
        changes = []
        if current:
            changes = self._compute_changes(current.config_data, target.config_data)
            for change in changes:
                change.change_type = ChangeType.ROLLBACK

        return self.create_version(
            namespace=namespace,
            config_data=target.config_data.copy(),
            created_by=created_by,
            message=f"Rollback to version {target.version_number}",
            changes=changes
        )

    def diff_versions(
        self,
        namespace: str,
        version_id_1: str,
        version_id_2: str
    ) -> List[ConfigChange]:
        """Compute diff between two versions"""
        history = self.histories.get(namespace)
        if not history:
            return []

        v1 = history.get_version(version_id_1)
        v2 = history.get_version(version_id_2)

        if not v1 or not v2:
            return []

        return self._compute_changes(v1.config_data, v2.config_data)

    def compare_with_current(
        self,
        namespace: str,
        new_config: Dict[str, Any]
    ) -> List[ConfigChange]:
        """Compare new config with current version"""
        current = self.get_current_version(namespace)
        if not current:
            # All new
            return [
                ConfigChange(path=k, change_type=ChangeType.CREATE, new_value=v)
                for k, v in self._flatten_dict(new_config).items()
            ]

        return self._compute_changes(current.config_data, new_config)

    def get_namespaces(self) -> List[str]:
        """Get all namespaces"""
        return list(self.histories.keys())

    def get_statistics(self) -> dict:
        """Get version manager statistics"""
        total_versions = sum(len(h.versions) for h in self.histories.values())
        return {
            "namespaces": len(self.histories),
            "total_versions": total_versions,
            "max_versions_per_namespace": self._max_versions,
            "namespace_stats": {
                ns: {
                    "version_count": len(h.versions),
                    "current_version": h.current_version
                }
                for ns, h in self.histories.items()
            }
        }

    def _compute_changes(
        self,
        old_config: Dict[str, Any],
        new_config: Dict[str, Any]
    ) -> List[ConfigChange]:
        """Compute changes between two configs"""
        changes = []

        old_flat = self._flatten_dict(old_config)
        new_flat = self._flatten_dict(new_config)

        all_keys = set(old_flat.keys()) | set(new_flat.keys())

        for key in all_keys:
            old_val = old_flat.get(key)
            new_val = new_flat.get(key)

            if key not in old_flat:
                changes.append(ConfigChange(
                    path=key,
                    change_type=ChangeType.CREATE,
                    new_value=new_val
                ))
            elif key not in new_flat:
                changes.append(ConfigChange(
                    path=key,
                    change_type=ChangeType.DELETE,
                    old_value=old_val
                ))
            elif old_val != new_val:
                changes.append(ConfigChange(
                    path=key,
                    change_type=ChangeType.UPDATE,
                    old_value=old_val,
                    new_value=new_val
                ))

        return changes

    def _flatten_dict(
        self,
        d: Dict[str, Any],
        parent_key: str = "",
        sep: str = "."
    ) -> Dict[str, Any]:
        """Flatten nested dictionary"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


# Global version manager instance
_version_manager: Optional[VersionManager] = None


def get_version_manager() -> VersionManager:
    """Get or create the global version manager"""
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
