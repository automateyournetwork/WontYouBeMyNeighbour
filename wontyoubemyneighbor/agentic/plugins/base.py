"""
Plugin Base Classes

Provides:
- Plugin base class
- Plugin metadata
- Plugin configuration
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class PluginStatus(Enum):
    """Plugin lifecycle status"""
    DISCOVERED = "discovered"
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    UNINSTALLED = "uninstalled"


class PluginType(Enum):
    """Types of plugins"""
    PROTOCOL = "protocol"
    MONITORING = "monitoring"
    VISUALIZATION = "visualization"
    INTEGRATION = "integration"
    AUTHENTICATION = "authentication"
    NOTIFICATION = "notification"
    ANALYTICS = "analytics"
    UTILITY = "utility"


@dataclass
class PluginDependency:
    """Plugin dependency specification"""

    plugin_id: str
    version_min: Optional[str] = None
    version_max: Optional[str] = None
    optional: bool = False

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "version_min": self.version_min,
            "version_max": self.version_max,
            "optional": self.optional
        }


@dataclass
class PluginMetadata:
    """Plugin metadata"""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    email: str = ""
    website: str = ""
    license: str = "MIT"
    plugin_type: PluginType = PluginType.UTILITY
    tags: List[str] = field(default_factory=list)
    dependencies: List[PluginDependency] = field(default_factory=list)
    python_requires: str = ">=3.9"
    requires_restart: bool = False
    min_platform_version: str = "1.0.0"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "email": self.email,
            "website": self.website,
            "license": self.license,
            "plugin_type": self.plugin_type.value,
            "tags": self.tags,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "python_requires": self.python_requires,
            "requires_restart": self.requires_restart,
            "min_platform_version": self.min_platform_version
        }


@dataclass
class PluginConfig:
    """Plugin configuration"""

    settings: Dict[str, Any] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)
    enabled_features: List[str] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value"""
        self.settings[key] = value

    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value"""
        return self.secrets.get(key)

    def set_secret(self, key: str, value: str) -> None:
        """Set a secret value"""
        self.secrets[key] = value

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled"""
        return feature in self.enabled_features

    def enable_feature(self, feature: str) -> None:
        """Enable a feature"""
        if feature not in self.enabled_features:
            self.enabled_features.append(feature)

    def disable_feature(self, feature: str) -> None:
        """Disable a feature"""
        if feature in self.enabled_features:
            self.enabled_features.remove(feature)

    def to_dict(self) -> dict:
        # Don't expose secrets
        return {
            "settings": self.settings,
            "enabled_features": self.enabled_features
        }


class Plugin(ABC):
    """Base class for plugins"""

    def __init__(self, metadata: PluginMetadata, config: Optional[PluginConfig] = None):
        self.metadata = metadata
        self.config = config or PluginConfig()
        self.status = PluginStatus.DISCOVERED
        self.installed_at: Optional[datetime] = None
        self.enabled_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self._hooks: Dict[str, List[Callable]] = {}

    @property
    def id(self) -> str:
        return self.metadata.id

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def is_enabled(self) -> bool:
        return self.status == PluginStatus.ENABLED

    @abstractmethod
    def on_install(self) -> bool:
        """Called when plugin is installed"""
        pass

    @abstractmethod
    def on_uninstall(self) -> bool:
        """Called when plugin is uninstalled"""
        pass

    @abstractmethod
    def on_enable(self) -> bool:
        """Called when plugin is enabled"""
        pass

    @abstractmethod
    def on_disable(self) -> bool:
        """Called when plugin is disabled"""
        pass

    def on_config_change(self, old_config: PluginConfig, new_config: PluginConfig) -> None:
        """Called when configuration changes"""
        pass

    def get_api_routes(self) -> List[Dict[str, Any]]:
        """Get API routes provided by this plugin"""
        return []

    def get_menu_items(self) -> List[Dict[str, Any]]:
        """Get menu items for UI"""
        return []

    def get_widgets(self) -> List[Dict[str, Any]]:
        """Get dashboard widgets"""
        return []

    def get_settings_schema(self) -> Dict[str, Any]:
        """Get JSON schema for plugin settings"""
        return {}

    def health_check(self) -> Dict[str, Any]:
        """Check plugin health"""
        return {
            "healthy": True,
            "status": self.status.value,
            "error": self.error_message
        }

    def register_hook(self, hook_name: str, callback: Callable) -> None:
        """Register a hook callback"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def unregister_hook(self, hook_name: str, callback: Callable) -> bool:
        """Unregister a hook callback"""
        if hook_name in self._hooks and callback in self._hooks[hook_name]:
            self._hooks[hook_name].remove(callback)
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "config": self.config.to_dict(),
            "status": self.status.value,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "enabled_at": self.enabled_at.isoformat() if self.enabled_at else None,
            "is_enabled": self.is_enabled,
            "error_message": self.error_message,
            "health": self.health_check()
        }


class SimplePlugin(Plugin):
    """Simple plugin implementation for basic use cases"""

    def __init__(
        self,
        plugin_id: str,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        plugin_type: PluginType = PluginType.UTILITY
    ):
        metadata = PluginMetadata(
            id=plugin_id,
            name=name,
            version=version,
            description=description,
            plugin_type=plugin_type
        )
        super().__init__(metadata)

    def on_install(self) -> bool:
        self.status = PluginStatus.INSTALLED
        self.installed_at = datetime.now()
        return True

    def on_uninstall(self) -> bool:
        self.status = PluginStatus.UNINSTALLED
        return True

    def on_enable(self) -> bool:
        self.status = PluginStatus.ENABLED
        self.enabled_at = datetime.now()
        return True

    def on_disable(self) -> bool:
        self.status = PluginStatus.DISABLED
        return True
