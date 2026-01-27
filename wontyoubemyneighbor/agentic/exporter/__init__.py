"""
Network Topology Exporter Module

This module provides network topology export capabilities including:
- Multiple export formats (DOT, JSON, YAML, GNS3, Containerlab)
- Selective node/link export
- Configuration export
- Topology import

Classes:
    ExportFormat: Enum of supported export formats
    ExportOptions: Export configuration options
    ExportResult: Result of an export operation
    TopologyExporter: Main topology export engine

Functions:
    get_topology_exporter: Get the singleton TopologyExporter instance
    export_topology: Export network topology to a format
    import_topology: Import topology from a file
    get_supported_formats: Get list of supported formats
"""

from .topology_exporter import (
    ExportFormat,
    ExportOptions,
    ExportResult,
    TopologyExporter,
)


# Singleton instance
_exporter_instance = None


def get_topology_exporter() -> TopologyExporter:
    """Get the singleton TopologyExporter instance."""
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = TopologyExporter()
    return _exporter_instance


def export_topology(
    format: ExportFormat,
    options: ExportOptions = None
) -> ExportResult:
    """Export network topology to a format."""
    exporter = get_topology_exporter()
    return exporter.export(format, options)


def import_topology(
    content: str,
    format: ExportFormat
) -> dict:
    """Import topology from a string."""
    exporter = get_topology_exporter()
    return exporter.import_topology(content, format)


def get_supported_formats() -> list:
    """Get list of supported export formats."""
    return [f.value for f in ExportFormat]


__all__ = [
    'ExportFormat',
    'ExportOptions',
    'ExportResult',
    'TopologyExporter',
    'get_topology_exporter',
    'export_topology',
    'import_topology',
    'get_supported_formats',
]
