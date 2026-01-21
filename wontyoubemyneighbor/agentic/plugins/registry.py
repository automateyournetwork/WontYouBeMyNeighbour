"""
Plugin Registry

Provides:
- Plugin catalog
- Plugin discovery
- Version management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from .base import PluginMetadata, PluginType


class PluginSource(Enum):
    """Plugin source types"""
    BUILTIN = "builtin"
    LOCAL = "local"
    MARKETPLACE = "marketplace"
    GIT = "git"
    URL = "url"


@dataclass
class PluginRegistryEntry:
    """Entry in plugin registry"""

    id: str
    metadata: PluginMetadata
    source: PluginSource
    source_url: Optional[str] = None
    download_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    verified: bool = False
    featured: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    screenshots: List[str] = field(default_factory=list)
    changelog: str = ""
    readme: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "metadata": self.metadata.to_dict(),
            "source": self.source.value,
            "source_url": self.source_url,
            "download_count": self.download_count,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "verified": self.verified,
            "featured": self.featured,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "screenshots": self.screenshots,
            "changelog": self.changelog,
            "readme": self.readme
        }


class PluginRegistry:
    """Registry of available plugins"""

    def __init__(self):
        self.entries: Dict[str, PluginRegistryEntry] = {}
        self._init_builtin_plugins()

    def _init_builtin_plugins(self) -> None:
        """Initialize built-in plugin entries"""

        # OSPF Protocol Plugin
        self.register(
            PluginMetadata(
                id="plugin_ospf",
                name="OSPF Protocol",
                version="1.0.0",
                description="Open Shortest Path First routing protocol implementation",
                author="ADN Platform",
                plugin_type=PluginType.PROTOCOL,
                tags=["routing", "igp", "ospf"]
            ),
            PluginSource.BUILTIN,
            verified=True,
            featured=True
        )

        # BGP Protocol Plugin
        self.register(
            PluginMetadata(
                id="plugin_bgp",
                name="BGP Protocol",
                version="1.0.0",
                description="Border Gateway Protocol routing implementation",
                author="ADN Platform",
                plugin_type=PluginType.PROTOCOL,
                tags=["routing", "egp", "bgp"]
            ),
            PluginSource.BUILTIN,
            verified=True,
            featured=True
        )

        # IS-IS Protocol Plugin
        self.register(
            PluginMetadata(
                id="plugin_isis",
                name="IS-IS Protocol",
                version="1.0.0",
                description="Intermediate System to Intermediate System routing protocol",
                author="ADN Platform",
                plugin_type=PluginType.PROTOCOL,
                tags=["routing", "igp", "isis"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

        # Prometheus Monitoring Plugin
        self.register(
            PluginMetadata(
                id="plugin_prometheus",
                name="Prometheus Monitoring",
                version="1.0.0",
                description="Prometheus metrics integration for network monitoring",
                author="ADN Platform",
                plugin_type=PluginType.MONITORING,
                tags=["monitoring", "metrics", "prometheus"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

        # Grafana Visualization Plugin
        self.register(
            PluginMetadata(
                id="plugin_grafana",
                name="Grafana Dashboards",
                version="1.0.0",
                description="Pre-built Grafana dashboards for network visualization",
                author="ADN Platform",
                plugin_type=PluginType.VISUALIZATION,
                tags=["visualization", "dashboards", "grafana"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

        # Slack Integration Plugin
        self.register(
            PluginMetadata(
                id="plugin_slack",
                name="Slack Integration",
                version="1.0.0",
                description="Slack notifications and chatbot integration",
                author="ADN Platform",
                plugin_type=PluginType.INTEGRATION,
                tags=["integration", "notifications", "slack"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

        # LDAP Authentication Plugin
        self.register(
            PluginMetadata(
                id="plugin_ldap",
                name="LDAP Authentication",
                version="1.0.0",
                description="LDAP/Active Directory authentication integration",
                author="ADN Platform",
                plugin_type=PluginType.AUTHENTICATION,
                tags=["auth", "ldap", "active-directory"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

        # Traffic Analytics Plugin
        self.register(
            PluginMetadata(
                id="plugin_traffic_analytics",
                name="Traffic Analytics",
                version="1.0.0",
                description="Advanced traffic analysis and reporting",
                author="ADN Platform",
                plugin_type=PluginType.ANALYTICS,
                tags=["analytics", "traffic", "reporting"]
            ),
            PluginSource.BUILTIN,
            verified=True
        )

    def register(
        self,
        metadata: PluginMetadata,
        source: PluginSource,
        source_url: Optional[str] = None,
        verified: bool = False,
        featured: bool = False,
        screenshots: Optional[List[str]] = None,
        changelog: str = "",
        readme: str = ""
    ) -> PluginRegistryEntry:
        """Register a plugin in the registry"""
        entry = PluginRegistryEntry(
            id=metadata.id,
            metadata=metadata,
            source=source,
            source_url=source_url,
            verified=verified,
            featured=featured,
            screenshots=screenshots or [],
            changelog=changelog,
            readme=readme
        )

        self.entries[metadata.id] = entry
        return entry

    def get(self, plugin_id: str) -> Optional[PluginRegistryEntry]:
        """Get registry entry by ID"""
        return self.entries.get(plugin_id)

    def search(
        self,
        query: Optional[str] = None,
        plugin_type: Optional[PluginType] = None,
        tag: Optional[str] = None,
        source: Optional[PluginSource] = None,
        verified_only: bool = False,
        featured_only: bool = False
    ) -> List[PluginRegistryEntry]:
        """Search plugins in registry"""
        results = list(self.entries.values())

        if query:
            query = query.lower()
            results = [
                e for e in results
                if query in e.metadata.name.lower() or
                   query in e.metadata.description.lower() or
                   any(query in tag.lower() for tag in e.metadata.tags)
            ]

        if plugin_type:
            results = [e for e in results if e.metadata.plugin_type == plugin_type]

        if tag:
            results = [e for e in results if tag in e.metadata.tags]

        if source:
            results = [e for e in results if e.source == source]

        if verified_only:
            results = [e for e in results if e.verified]

        if featured_only:
            results = [e for e in results if e.featured]

        return results

    def get_by_type(self, plugin_type: PluginType) -> List[PluginRegistryEntry]:
        """Get plugins by type"""
        return [e for e in self.entries.values() if e.metadata.plugin_type == plugin_type]

    def get_by_tag(self, tag: str) -> List[PluginRegistryEntry]:
        """Get plugins by tag"""
        return [e for e in self.entries.values() if tag in e.metadata.tags]

    def get_featured(self) -> List[PluginRegistryEntry]:
        """Get featured plugins"""
        return [e for e in self.entries.values() if e.featured]

    def get_verified(self) -> List[PluginRegistryEntry]:
        """Get verified plugins"""
        return [e for e in self.entries.values() if e.verified]

    def get_popular(self, limit: int = 10) -> List[PluginRegistryEntry]:
        """Get popular plugins by download count"""
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: e.download_count,
            reverse=True
        )
        return sorted_entries[:limit]

    def get_top_rated(self, limit: int = 10) -> List[PluginRegistryEntry]:
        """Get top-rated plugins"""
        # Filter entries with at least some ratings
        rated = [e for e in self.entries.values() if e.rating_count > 0]
        sorted_entries = sorted(rated, key=lambda e: e.rating, reverse=True)
        return sorted_entries[:limit]

    def get_recent(self, limit: int = 10) -> List[PluginRegistryEntry]:
        """Get recently updated plugins"""
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: e.updated_at,
            reverse=True
        )
        return sorted_entries[:limit]

    def update_entry(
        self,
        plugin_id: str,
        **kwargs
    ) -> Optional[PluginRegistryEntry]:
        """Update a registry entry"""
        entry = self.entries.get(plugin_id)
        if not entry:
            return None

        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        entry.updated_at = datetime.now()
        return entry

    def increment_downloads(self, plugin_id: str) -> bool:
        """Increment download count"""
        entry = self.entries.get(plugin_id)
        if entry:
            entry.download_count += 1
            return True
        return False

    def add_rating(self, plugin_id: str, rating: float) -> bool:
        """Add a rating to a plugin"""
        entry = self.entries.get(plugin_id)
        if not entry or rating < 1 or rating > 5:
            return False

        # Calculate new average
        total = entry.rating * entry.rating_count + rating
        entry.rating_count += 1
        entry.rating = total / entry.rating_count
        return True

    def remove(self, plugin_id: str) -> bool:
        """Remove a plugin from registry"""
        if plugin_id in self.entries:
            del self.entries[plugin_id]
            return True
        return False

    def get_all_tags(self) -> List[str]:
        """Get all unique tags"""
        tags = set()
        for entry in self.entries.values():
            tags.update(entry.metadata.tags)
        return sorted(tags)

    def get_statistics(self) -> dict:
        """Get registry statistics"""
        by_type = {}
        by_source = {}
        total_downloads = 0

        for entry in self.entries.values():
            by_type[entry.metadata.plugin_type.value] = by_type.get(entry.metadata.plugin_type.value, 0) + 1
            by_source[entry.source.value] = by_source.get(entry.source.value, 0) + 1
            total_downloads += entry.download_count

        return {
            "total_plugins": len(self.entries),
            "verified_plugins": len([e for e in self.entries.values() if e.verified]),
            "featured_plugins": len([e for e in self.entries.values() if e.featured]),
            "by_type": by_type,
            "by_source": by_source,
            "total_downloads": total_downloads,
            "unique_tags": len(self.get_all_tags())
        }


# Global registry instance
_plugin_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry"""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry
