"""
Plugin Manager

Provides:
- Plugin lifecycle management
- Plugin installation/uninstallation
- Plugin enabling/disabling
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Type
from datetime import datetime

from .base import Plugin, PluginMetadata, PluginStatus, PluginType, PluginConfig, SimplePlugin
from .hooks import HookManager, get_hook_manager, HookType
from .registry import PluginRegistry, get_plugin_registry


class PluginManager:
    """Manages plugin lifecycle"""

    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self._plugin_classes: Dict[str, Type[Plugin]] = {}
        self._hook_manager = get_hook_manager()
        self._registry = get_plugin_registry()

    def register_plugin_class(
        self,
        plugin_id: str,
        plugin_class: Type[Plugin]
    ) -> None:
        """Register a plugin class for instantiation"""
        self._plugin_classes[plugin_id] = plugin_class

    def create_plugin(
        self,
        plugin_id: str,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        plugin_type: PluginType = PluginType.UTILITY,
        config: Optional[PluginConfig] = None
    ) -> Plugin:
        """Create a simple plugin"""
        # Check if there's a registered class
        if plugin_id in self._plugin_classes:
            plugin_class = self._plugin_classes[plugin_id]
            metadata = PluginMetadata(
                id=plugin_id,
                name=name,
                version=version,
                description=description,
                plugin_type=plugin_type
            )
            plugin = plugin_class(metadata, config)
        else:
            plugin = SimplePlugin(
                plugin_id=plugin_id,
                name=name,
                version=version,
                description=description,
                plugin_type=plugin_type
            )
            if config:
                plugin.config = config

        self.plugins[plugin_id] = plugin
        return plugin

    def install_plugin(
        self,
        plugin_id: str,
        config: Optional[PluginConfig] = None
    ) -> Optional[Plugin]:
        """Install a plugin from registry"""
        # Check registry
        entry = self._registry.get(plugin_id)
        if not entry:
            return None

        # Create plugin
        plugin = self.create_plugin(
            plugin_id=entry.metadata.id,
            name=entry.metadata.name,
            version=entry.metadata.version,
            description=entry.metadata.description,
            plugin_type=entry.metadata.plugin_type,
            config=config
        )

        # Execute install
        try:
            if plugin.on_install():
                self._registry.increment_downloads(plugin_id)
                return plugin
            else:
                del self.plugins[plugin_id]
                return None
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            plugin.error_message = str(e)
            return plugin

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """Uninstall a plugin"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        # Disable first if enabled
        if plugin.is_enabled:
            self.disable_plugin(plugin_id)

        try:
            if plugin.on_uninstall():
                # Remove hooks
                hooks = self._hook_manager.get_hooks_for_plugin(plugin_id)
                for hook in hooks:
                    self._hook_manager.unregister_hook(hook.id)

                del self.plugins[plugin_id]
                return True
            return False
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            plugin.error_message = str(e)
            return False

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        if plugin.status != PluginStatus.INSTALLED and plugin.status != PluginStatus.DISABLED:
            return False

        try:
            if plugin.on_enable():
                return True
            return False
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            plugin.error_message = str(e)
            return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return False

        if not plugin.is_enabled:
            return True  # Already disabled

        try:
            if plugin.on_disable():
                return True
            return False
        except Exception as e:
            plugin.status = PluginStatus.ERROR
            plugin.error_message = str(e)
            return False

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """Get plugin by ID"""
        return self.plugins.get(plugin_id)

    def get_plugins(
        self,
        status: Optional[PluginStatus] = None,
        plugin_type: Optional[PluginType] = None,
        enabled_only: bool = False
    ) -> List[Plugin]:
        """Get plugins with filtering"""
        plugins = list(self.plugins.values())

        if status:
            plugins = [p for p in plugins if p.status == status]
        if plugin_type:
            plugins = [p for p in plugins if p.metadata.plugin_type == plugin_type]
        if enabled_only:
            plugins = [p for p in plugins if p.is_enabled]

        return plugins

    def get_enabled_plugins(self) -> List[Plugin]:
        """Get enabled plugins"""
        return [p for p in self.plugins.values() if p.is_enabled]

    def update_plugin_config(
        self,
        plugin_id: str,
        config: PluginConfig
    ) -> Optional[Plugin]:
        """Update plugin configuration"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return None

        old_config = plugin.config
        plugin.config = config
        plugin.on_config_change(old_config, config)
        return plugin

    def check_dependencies(self, plugin_id: str) -> Dict[str, Any]:
        """Check plugin dependencies"""
        plugin = self.plugins.get(plugin_id)
        if not plugin:
            return {"satisfied": False, "missing": [], "error": "Plugin not found"}

        missing = []
        for dep in plugin.metadata.dependencies:
            dep_plugin = self.plugins.get(dep.plugin_id)
            if not dep_plugin:
                if not dep.optional:
                    missing.append(dep.plugin_id)
            elif dep.version_min and dep_plugin.version < dep.version_min:
                missing.append(f"{dep.plugin_id} (requires >= {dep.version_min})")
            elif dep.version_max and dep_plugin.version > dep.version_max:
                missing.append(f"{dep.plugin_id} (requires <= {dep.version_max})")

        return {
            "satisfied": len(missing) == 0,
            "missing": missing
        }

    def get_plugin_api_routes(self) -> List[Dict[str, Any]]:
        """Get all API routes from enabled plugins"""
        routes = []
        for plugin in self.get_enabled_plugins():
            plugin_routes = plugin.get_api_routes()
            for route in plugin_routes:
                route["plugin_id"] = plugin.id
            routes.extend(plugin_routes)
        return routes

    def get_plugin_menu_items(self) -> List[Dict[str, Any]]:
        """Get all menu items from enabled plugins"""
        items = []
        for plugin in self.get_enabled_plugins():
            plugin_items = plugin.get_menu_items()
            for item in plugin_items:
                item["plugin_id"] = plugin.id
            items.extend(plugin_items)
        return items

    def get_plugin_widgets(self) -> List[Dict[str, Any]]:
        """Get all widgets from enabled plugins"""
        widgets = []
        for plugin in self.get_enabled_plugins():
            plugin_widgets = plugin.get_widgets()
            for widget in plugin_widgets:
                widget["plugin_id"] = plugin.id
            widgets.extend(plugin_widgets)
        return widgets

    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """Health check all plugins"""
        results = {}
        for plugin_id, plugin in self.plugins.items():
            results[plugin_id] = plugin.health_check()
        return results

    def get_statistics(self) -> dict:
        """Get plugin manager statistics"""
        by_status = {}
        by_type = {}

        for plugin in self.plugins.values():
            by_status[plugin.status.value] = by_status.get(plugin.status.value, 0) + 1
            by_type[plugin.metadata.plugin_type.value] = by_type.get(plugin.metadata.plugin_type.value, 0) + 1

        return {
            "total_plugins": len(self.plugins),
            "enabled_plugins": len(self.get_enabled_plugins()),
            "by_status": by_status,
            "by_type": by_type,
            "registered_classes": len(self._plugin_classes),
            "hooks": self._hook_manager.get_statistics(),
            "registry": self._registry.get_statistics()
        }


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get or create the global plugin manager"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
