"""
Configuration Manager

Provides:
- Configuration storage
- Namespace management
- Environment support
- Configuration access
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum

from .version import get_version_manager, ConfigVersion
from .schema import get_schema_validator, ValidationResult


class Environment(Enum):
    """Configuration environments"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class ConfigEntry:
    """Configuration entry"""

    key: str
    value: Any
    namespace: str
    environment: Environment = Environment.PRODUCTION
    description: str = ""
    encrypted: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value if not self.encrypted else "***ENCRYPTED***",
            "namespace": self.namespace,
            "environment": self.environment.value,
            "description": self.description,
            "encrypted": self.encrypted,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "metadata": self.metadata
        }


@dataclass
class ConfigNamespace:
    """Configuration namespace"""

    name: str
    description: str = ""
    entries: Dict[str, ConfigEntry] = field(default_factory=dict)
    schema_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        entry = self.entries.get(key)
        return entry.value if entry else default

    def set(
        self,
        key: str,
        value: Any,
        description: str = "",
        encrypted: bool = False,
        updated_by: Optional[str] = None
    ) -> ConfigEntry:
        """Set configuration value"""
        if key in self.entries:
            entry = self.entries[key]
            entry.value = value
            entry.updated_at = datetime.now()
            entry.updated_by = updated_by
            if description:
                entry.description = description
        else:
            entry = ConfigEntry(
                key=key,
                value=value,
                namespace=self.name,
                description=description,
                encrypted=encrypted,
                created_by=updated_by,
                updated_by=updated_by
            )
            self.entries[key] = entry
        return entry

    def delete(self, key: str) -> bool:
        """Delete configuration entry"""
        if key in self.entries:
            del self.entries[key]
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "entries": {k: e.to_dict() for k, e in self.entries.items()},
            "schema_name": self.schema_name,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "entry_count": len(self.entries)
        }

    def to_config_dict(self) -> dict:
        """Get configuration as simple dictionary"""
        return {k: e.value for k, e in self.entries.items()}


class ConfigManager:
    """Manages application configuration"""

    def __init__(self):
        self.namespaces: Dict[str, ConfigNamespace] = {}
        self.version_manager = get_version_manager()
        self.schema_validator = get_schema_validator()
        self.current_environment = Environment.PRODUCTION
        self._change_listeners: List[Callable[[str, str, Any, Any], None]] = []

        # Create default namespaces
        self._create_default_namespaces()

    def create_namespace(
        self,
        name: str,
        description: str = "",
        schema_name: Optional[str] = None
    ) -> ConfigNamespace:
        """Create a new namespace"""
        namespace = ConfigNamespace(
            name=name,
            description=description,
            schema_name=schema_name
        )
        self.namespaces[name] = namespace
        return namespace

    def get_namespace(self, name: str) -> Optional[ConfigNamespace]:
        """Get namespace by name"""
        return self.namespaces.get(name)

    def delete_namespace(self, name: str) -> bool:
        """Delete a namespace"""
        if name in self.namespaces:
            del self.namespaces[name]
            return True
        return False

    def get(
        self,
        namespace: str,
        key: str,
        default: Any = None
    ) -> Any:
        """Get configuration value"""
        ns = self.namespaces.get(namespace)
        if not ns:
            return default
        return ns.get(key, default)

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        description: str = "",
        encrypted: bool = False,
        user: Optional[str] = None,
        validate: bool = True
    ) -> ConfigEntry:
        """Set configuration value"""
        # Get or create namespace
        if namespace not in self.namespaces:
            self.create_namespace(namespace)

        ns = self.namespaces[namespace]
        old_value = ns.get(key)

        # Validate if schema exists
        if validate and ns.schema_name:
            config = ns.to_config_dict()
            config[key] = value
            result = self.schema_validator.validate(config, ns.schema_name)
            if not result.valid:
                raise ValueError(f"Validation failed: {result.errors}")

        entry = ns.set(key, value, description, encrypted, user)

        # Notify listeners
        for listener in self._change_listeners:
            try:
                listener(namespace, key, old_value, value)
            except Exception:
                pass

        return entry

    def delete(self, namespace: str, key: str) -> bool:
        """Delete configuration entry"""
        ns = self.namespaces.get(namespace)
        if not ns:
            return False
        return ns.delete(key)

    def get_all(self, namespace: str) -> Dict[str, Any]:
        """Get all configuration for namespace"""
        ns = self.namespaces.get(namespace)
        if not ns:
            return {}
        return ns.to_config_dict()

    def set_bulk(
        self,
        namespace: str,
        config: Dict[str, Any],
        user: Optional[str] = None,
        validate: bool = True,
        create_version: bool = True
    ) -> ValidationResult:
        """Set multiple configuration values"""
        # Get or create namespace
        if namespace not in self.namespaces:
            self.create_namespace(namespace)

        ns = self.namespaces[namespace]

        # Validate entire config
        if validate and ns.schema_name:
            result = self.schema_validator.validate(config, ns.schema_name)
            if not result.valid:
                return result

        # Apply changes
        for key, value in config.items():
            ns.set(key, value, updated_by=user)

        # Create version
        if create_version:
            self.version_manager.create_version(
                namespace=namespace,
                config_data=config,
                created_by=user,
                message="Bulk configuration update"
            )

        return ValidationResult(valid=True)

    def validate(self, namespace: str, config: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validate configuration"""
        ns = self.namespaces.get(namespace)
        if not ns:
            result = ValidationResult(valid=False)
            result.add_error("_namespace", f"Namespace '{namespace}' not found")
            return result

        if not ns.schema_name:
            return ValidationResult(valid=True)

        config_data = config if config else ns.to_config_dict()
        return self.schema_validator.validate(config_data, ns.schema_name)

    def commit(
        self,
        namespace: str,
        message: str = "",
        user: Optional[str] = None
    ) -> Optional[ConfigVersion]:
        """Commit current configuration as new version"""
        ns = self.namespaces.get(namespace)
        if not ns:
            return None

        return self.version_manager.create_version(
            namespace=namespace,
            config_data=ns.to_config_dict(),
            created_by=user,
            message=message
        )

    def rollback(
        self,
        namespace: str,
        version_id: str,
        user: Optional[str] = None
    ) -> Optional[ConfigVersion]:
        """Rollback to a previous version"""
        version = self.version_manager.rollback(namespace, version_id, user)
        if not version:
            return None

        # Apply rollback configuration
        ns = self.namespaces.get(namespace)
        if ns:
            # Clear and reapply
            ns.entries.clear()
            for key, value in version.config_data.items():
                ns.set(key, value, updated_by=user)

        return version

    def get_history(self, namespace: str, limit: int = 50) -> List[ConfigVersion]:
        """Get configuration history"""
        return self.version_manager.get_history(namespace, limit)

    def diff(
        self,
        namespace: str,
        config: Dict[str, Any]
    ) -> List[dict]:
        """Compare configuration with current"""
        changes = self.version_manager.compare_with_current(namespace, config)
        return [c.to_dict() for c in changes]

    def export(self, namespace: str) -> Dict[str, Any]:
        """Export namespace configuration"""
        ns = self.namespaces.get(namespace)
        if not ns:
            return {}

        return {
            "namespace": namespace,
            "environment": self.current_environment.value,
            "exported_at": datetime.now().isoformat(),
            "config": ns.to_config_dict(),
            "metadata": ns.metadata
        }

    def import_config(
        self,
        namespace: str,
        data: Dict[str, Any],
        user: Optional[str] = None,
        validate: bool = True
    ) -> ValidationResult:
        """Import configuration"""
        config = data.get("config", data)
        return self.set_bulk(namespace, config, user, validate)

    def add_change_listener(
        self,
        listener: Callable[[str, str, Any, Any], None]
    ) -> None:
        """Add configuration change listener"""
        self._change_listeners.append(listener)

    def remove_change_listener(
        self,
        listener: Callable[[str, str, Any, Any], None]
    ) -> None:
        """Remove configuration change listener"""
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def set_environment(self, environment: Environment) -> None:
        """Set current environment"""
        self.current_environment = environment

    def get_namespaces(self) -> List[str]:
        """Get all namespace names"""
        return list(self.namespaces.keys())

    def search(
        self,
        query: str,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search configuration entries"""
        results = []
        query_lower = query.lower()

        namespaces = [self.namespaces[namespace]] if namespace else self.namespaces.values()

        for ns in namespaces:
            for key, entry in ns.entries.items():
                if (query_lower in key.lower() or
                    query_lower in entry.description.lower() or
                    query_lower in str(entry.value).lower()):
                    results.append({
                        "namespace": ns.name,
                        "key": key,
                        "value": entry.value if not entry.encrypted else "***",
                        "description": entry.description
                    })

        return results

    def get_statistics(self) -> dict:
        """Get configuration statistics"""
        total_entries = sum(len(ns.entries) for ns in self.namespaces.values())
        encrypted_entries = sum(
            len([e for e in ns.entries.values() if e.encrypted])
            for ns in self.namespaces.values()
        )

        return {
            "namespace_count": len(self.namespaces),
            "total_entries": total_entries,
            "encrypted_entries": encrypted_entries,
            "current_environment": self.current_environment.value,
            "change_listeners": len(self._change_listeners),
            "version_stats": self.version_manager.get_statistics(),
            "schema_stats": self.schema_validator.get_statistics()
        }

    def _create_default_namespaces(self) -> None:
        """Create default namespaces"""
        # System namespace
        system = self.create_namespace(
            "system",
            "System-wide configuration"
        )
        system.set("log_level", "INFO", "Logging level")
        system.set("debug_mode", False, "Enable debug mode")
        system.set("max_agents", 100, "Maximum number of agents")

        # Network defaults
        network = self.create_namespace(
            "network.defaults",
            "Default network configuration",
            schema_name="network"
        )
        network.set("mtu", 1500, "Default MTU")
        network.set("hello_interval", 10, "Default hello interval")
        network.set("dead_interval", 40, "Default dead interval")

        # Protocol defaults
        protocols = self.create_namespace(
            "protocols",
            "Protocol configuration"
        )
        protocols.set("ospf.enabled", True, "Enable OSPF")
        protocols.set("bgp.enabled", True, "Enable BGP")
        protocols.set("isis.enabled", False, "Enable IS-IS")


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get or create the global config manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
