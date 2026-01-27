"""
Network Diff Module

Provides comparison between two network states,
highlighting changes in routes, neighbors, and configurations.
"""

from .network_differ import (
    NetworkDiffer,
    DiffResult,
    DiffItem,
    DiffType,
    DiffCategory,
    get_network_differ,
    compare_snapshots,
    compare_configs,
    get_diff_summary,
)

__all__ = [
    "NetworkDiffer",
    "DiffResult",
    "DiffItem",
    "DiffType",
    "DiffCategory",
    "get_network_differ",
    "compare_snapshots",
    "compare_configs",
    "get_diff_summary",
]
