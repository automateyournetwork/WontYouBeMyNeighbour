"""
Data Pipeline Module

Provides:
- ETL (Extract, Transform, Load) pipelines
- Data source connectors
- Transformation operations
- Data sinks/destinations
"""

from .sources import (
    DataSource,
    SourceType,
    SourceConfig,
    SourceManager,
    get_source_manager
)
from .transforms import (
    Transform,
    TransformType,
    TransformConfig,
    TransformManager,
    get_transform_manager
)
from .sinks import (
    DataSink,
    SinkType,
    SinkConfig,
    SinkManager,
    get_sink_manager
)
from .pipeline import (
    Pipeline,
    PipelineStatus,
    PipelineResult,
    PipelineManager,
    get_pipeline_manager
)

__all__ = [
    # Sources
    "DataSource",
    "SourceType",
    "SourceConfig",
    "SourceManager",
    "get_source_manager",
    # Transforms
    "Transform",
    "TransformType",
    "TransformConfig",
    "TransformManager",
    "get_transform_manager",
    # Sinks
    "DataSink",
    "SinkType",
    "SinkConfig",
    "SinkManager",
    "get_sink_manager",
    # Pipeline
    "Pipeline",
    "PipelineStatus",
    "PipelineResult",
    "PipelineManager",
    "get_pipeline_manager"
]
