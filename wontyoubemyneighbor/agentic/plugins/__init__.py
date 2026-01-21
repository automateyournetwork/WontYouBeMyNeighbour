"""
Plugin System

Provides:
- Plugin registration and discovery
- Plugin lifecycle management
- Hook system for extensibility
- Plugin marketplace
"""

from .base import (
    Plugin,
    PluginMetadata,
    PluginStatus,
    PluginType,
    PluginDependency,
    PluginConfig
)

from .manager import (
    PluginManager,
    get_plugin_manager
)

from .hooks import (
    Hook,
    HookType,
    HookManager,
    get_hook_manager
)

from .registry import (
    PluginRegistry,
    PluginRegistryEntry,
    get_plugin_registry
)

__all__ = [
    # Base
    "Plugin",
    "PluginMetadata",
    "PluginStatus",
    "PluginType",
    "PluginDependency",
    "PluginConfig",
    # Manager
    "PluginManager",
    "get_plugin_manager",
    # Hooks
    "Hook",
    "HookType",
    "HookManager",
    "get_hook_manager",
    # Registry
    "PluginRegistry",
    "PluginRegistryEntry",
    "get_plugin_registry"
]
