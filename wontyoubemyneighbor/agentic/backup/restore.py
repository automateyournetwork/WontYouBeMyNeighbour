"""
Restore Module - Point-in-time restore functionality

Provides:
- Restore point management
- Full and partial restore
- Restore validation
- Rollback support
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("RestoreManager")


class RestoreType(str, Enum):
    """Types of restore operations"""
    FULL = "full"           # Complete restore
    PARTIAL = "partial"     # Selected components
    AGENTS_ONLY = "agents"  # Only agents
    CONFIG_ONLY = "config"  # Only configuration
    ROUTES_ONLY = "routes"  # Only routing tables


class RestoreStatus(str, Enum):
    """Restore operation status"""
    PENDING = "pending"
    VALIDATING = "validating"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class RestorePoint:
    """
    A restore point reference

    Attributes:
        id: Restore point identifier
        backup_id: Source backup ID
        name: Human-readable name
        description: Description
        created_at: Creation timestamp
        components: Available components
    """
    id: str
    backup_id: str
    name: str
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    components: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "backup_id": self.backup_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "components": self.components
        }


@dataclass
class RestoreResult:
    """
    Result of a restore operation

    Attributes:
        restore_point_id: Restore point used
        restore_type: Type of restore
        status: Operation status
        agents_restored: Number of agents restored
        routes_restored: Number of routes restored
        configs_restored: Number of configs restored
        started_at: Start timestamp
        completed_at: Completion timestamp
        error_message: Error if failed
        rollback_backup_id: Backup created before restore
    """
    restore_point_id: str
    restore_type: RestoreType
    status: RestoreStatus = RestoreStatus.PENDING
    agents_restored: int = 0
    routes_restored: int = 0
    configs_restored: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: str = ""
    rollback_backup_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> int:
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "restore_point_id": self.restore_point_id,
            "restore_type": self.restore_type.value,
            "status": self.status.value,
            "agents_restored": self.agents_restored,
            "routes_restored": self.routes_restored,
            "configs_restored": self.configs_restored,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "rollback_backup_id": self.rollback_backup_id,
            "warnings": self.warnings
        }


class RestoreManager:
    """
    Manages restore operations
    """

    def __init__(self):
        """Initialize restore manager"""
        self._restore_points: Dict[str, RestorePoint] = {}
        self._restore_history: List[RestoreResult] = []
        self._restore_counter = 0

    def create_restore_point(
        self,
        backup_id: str,
        name: str,
        description: str = ""
    ) -> Optional[RestorePoint]:
        """
        Create a restore point from a backup

        Args:
            backup_id: Source backup ID
            name: Restore point name
            description: Description

        Returns:
            Created restore point or None
        """
        from .backup import get_backup_manager

        manager = get_backup_manager()
        backup = manager.get_backup(backup_id)
        if not backup or not backup.is_complete:
            logger.warning(f"Cannot create restore point from backup {backup_id}")
            return None

        # Read backup to determine components
        content = manager.read_backup(backup_id)
        if not content:
            return None

        components = []
        if "agents" in content:
            components.append("agents")
        if "network" in content:
            components.append("network")
        if "protocols" in content:
            components.append("protocols")
        if "routes" in content:
            components.append("routes")
        if "config" in content:
            components.append("config")

        self._restore_counter += 1
        point_id = f"rp-{self._restore_counter:05d}"

        restore_point = RestorePoint(
            id=point_id,
            backup_id=backup_id,
            name=name,
            description=description,
            components=components
        )

        self._restore_points[point_id] = restore_point
        logger.info(f"Created restore point {point_id} from backup {backup_id}")
        return restore_point

    def get_restore_point(self, point_id: str) -> Optional[RestorePoint]:
        """Get restore point by ID"""
        return self._restore_points.get(point_id)

    def list_restore_points(self) -> List[RestorePoint]:
        """List all restore points"""
        points = list(self._restore_points.values())
        points.sort(key=lambda p: p.created_at, reverse=True)
        return points

    def delete_restore_point(self, point_id: str) -> bool:
        """Delete a restore point"""
        if point_id in self._restore_points:
            del self._restore_points[point_id]
            logger.info(f"Deleted restore point {point_id}")
            return True
        return False

    async def restore(
        self,
        restore_point_id: str,
        restore_type: RestoreType = RestoreType.FULL,
        components: Optional[List[str]] = None,
        create_rollback: bool = True
    ) -> RestoreResult:
        """
        Perform a restore operation

        Args:
            restore_point_id: Restore point to use
            restore_type: Type of restore
            components: Specific components to restore
            create_rollback: Whether to create rollback backup

        Returns:
            RestoreResult
        """
        from .backup import get_backup_manager, BackupType

        result = RestoreResult(
            restore_point_id=restore_point_id,
            restore_type=restore_type
        )

        # Get restore point
        restore_point = self.get_restore_point(restore_point_id)
        if not restore_point:
            result.status = RestoreStatus.FAILED
            result.error_message = "Restore point not found"
            result.completed_at = datetime.now()
            self._restore_history.append(result)
            return result

        # Get backup manager
        backup_manager = get_backup_manager()

        # Validate backup exists
        result.status = RestoreStatus.VALIDATING
        backup = backup_manager.get_backup(restore_point.backup_id)
        if not backup:
            result.status = RestoreStatus.FAILED
            result.error_message = "Source backup not found"
            result.completed_at = datetime.now()
            self._restore_history.append(result)
            return result

        # Read backup content
        content = backup_manager.read_backup(restore_point.backup_id)
        if not content:
            result.status = RestoreStatus.FAILED
            result.error_message = "Failed to read backup content"
            result.completed_at = datetime.now()
            self._restore_history.append(result)
            return result

        # Create rollback backup if requested
        if create_rollback:
            rollback_content = self._get_current_state()
            rollback_backup = backup_manager.create_backup(
                name=f"Pre-restore rollback ({restore_point_id})",
                backup_type=BackupType.FULL,
                content=rollback_content,
                created_by="restore_manager",
                tags=["rollback", "auto"]
            )
            result.rollback_backup_id = rollback_backup.id

        # Perform restore
        result.status = RestoreStatus.IN_PROGRESS
        try:
            # Determine what to restore
            if components:
                restore_components = [c for c in components if c in restore_point.components]
            elif restore_type == RestoreType.AGENTS_ONLY:
                restore_components = ["agents"]
            elif restore_type == RestoreType.CONFIG_ONLY:
                restore_components = ["config"]
            elif restore_type == RestoreType.ROUTES_ONLY:
                restore_components = ["routes"]
            else:
                restore_components = restore_point.components

            # Restore each component
            for component in restore_components:
                if component == "agents" and "agents" in content:
                    count = self._restore_agents(content["agents"])
                    result.agents_restored = count
                elif component == "routes" and "routes" in content:
                    count = self._restore_routes(content["routes"])
                    result.routes_restored = count
                elif component == "config" and "config" in content:
                    count = self._restore_config(content["config"])
                    result.configs_restored = count

            result.status = RestoreStatus.COMPLETED
            result.completed_at = datetime.now()
            logger.info(f"Restore completed: {result.agents_restored} agents, {result.routes_restored} routes")

        except Exception as e:
            result.status = RestoreStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now()
            logger.error(f"Restore failed: {e}")

        self._restore_history.append(result)
        return result

    def _get_current_state(self) -> Dict[str, Any]:
        """Get current system state for rollback"""
        # Placeholder - in production would gather current state
        return {
            "agents": [],
            "network": {},
            "protocols": [],
            "routes": [],
            "config": {},
            "timestamp": datetime.now().isoformat()
        }

    def _restore_agents(self, agents: List[Dict[str, Any]]) -> int:
        """Restore agents from backup"""
        # Placeholder - in production would restore to actual system
        count = len(agents)
        logger.info(f"Restored {count} agents")
        return count

    def _restore_routes(self, routes: List[Dict[str, Any]]) -> int:
        """Restore routes from backup"""
        # Placeholder - in production would restore to actual system
        count = len(routes)
        logger.info(f"Restored {count} routes")
        return count

    def _restore_config(self, config: Dict[str, Any]) -> int:
        """Restore configuration from backup"""
        # Placeholder - in production would restore to actual system
        count = len(config)
        logger.info(f"Restored {count} config items")
        return count

    async def rollback(self, restore_result_id: int) -> Optional[RestoreResult]:
        """
        Rollback a restore operation

        Args:
            restore_result_id: Index of restore result to rollback

        Returns:
            New RestoreResult for rollback
        """
        if restore_result_id >= len(self._restore_history):
            return None

        original = self._restore_history[restore_result_id]
        if not original.rollback_backup_id:
            return None

        # Create restore point from rollback backup
        rollback_point = self.create_restore_point(
            backup_id=original.rollback_backup_id,
            name="Rollback operation",
            description=f"Rollback of restore {original.restore_point_id}"
        )

        if not rollback_point:
            return None

        # Perform rollback restore
        result = await self.restore(
            restore_point_id=rollback_point.id,
            restore_type=RestoreType.FULL,
            create_rollback=False
        )

        if result.status == RestoreStatus.COMPLETED:
            result.status = RestoreStatus.ROLLED_BACK

        return result

    def get_restore_history(self, limit: int = 50) -> List[RestoreResult]:
        """Get restore operation history"""
        return self._restore_history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get restore statistics"""
        total_restores = len(self._restore_history)
        successful = sum(
            1 for r in self._restore_history
            if r.status == RestoreStatus.COMPLETED
        )
        failed = sum(
            1 for r in self._restore_history
            if r.status == RestoreStatus.FAILED
        )
        rolled_back = sum(
            1 for r in self._restore_history
            if r.status == RestoreStatus.ROLLED_BACK
        )

        return {
            "total_restore_points": len(self._restore_points),
            "total_restores": total_restores,
            "successful_restores": successful,
            "failed_restores": failed,
            "rolled_back": rolled_back,
            "success_rate": round(
                (successful / total_restores * 100) if total_restores > 0 else 100, 2
            )
        }


# Global restore manager instance
_global_manager: Optional[RestoreManager] = None


def get_restore_manager() -> RestoreManager:
    """Get or create the global restore manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = RestoreManager()
    return _global_manager
