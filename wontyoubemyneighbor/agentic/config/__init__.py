"""
Configuration Management Module

Provides:
- Configuration versioning
- Schema validation
- Configuration diff and rollback
- Environment management
"""

from .version import (
    ConfigVersion,
    ConfigHistory,
    VersionManager,
    get_version_manager
)

from .schema import (
    ConfigSchema,
    SchemaType,
    SchemaValidator,
    ValidationResult,
    get_schema_validator
)

from .manager import (
    ConfigEntry,
    ConfigNamespace,
    ConfigManager,
    get_config_manager
)

__all__ = [
    # Version
    "ConfigVersion",
    "ConfigHistory",
    "VersionManager",
    "get_version_manager",
    # Schema
    "ConfigSchema",
    "SchemaType",
    "SchemaValidator",
    "ValidationResult",
    "get_schema_validator",
    # Manager
    "ConfigEntry",
    "ConfigNamespace",
    "ConfigManager",
    "get_config_manager"
]
