"""
Pipeline Orchestration

Provides:
- Pipeline definition
- Pipeline execution
- End-to-end ETL
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import asyncio

from .sources import DataSource, SourceManager, get_source_manager, ExtractResult
from .transforms import Transform, TransformManager, get_transform_manager, TransformResult
from .sinks import DataSink, SinkManager, get_sink_manager, LoadResult


class PipelineStatus(Enum):
    """Pipeline execution status"""
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class PipelineStage:
    """A stage in the pipeline"""

    id: str
    name: str
    stage_type: str  # "extract", "transform", "load"
    component_id: str  # Source, Transform, or Sink ID
    order: int = 0
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "stage_type": self.stage_type,
            "component_id": self.component_id,
            "order": self.order,
            "enabled": self.enabled
        }


@dataclass
class PipelineResult:
    """Result of pipeline execution"""

    pipeline_id: str
    status: PipelineStatus
    extract_results: List[ExtractResult] = field(default_factory=list)
    transform_results: List[TransformResult] = field(default_factory=list)
    load_results: List[LoadResult] = field(default_factory=list)
    total_records_extracted: int = 0
    total_records_transformed: int = 0
    total_records_loaded: int = 0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status.value,
            "extract_results": [r.to_dict() for r in self.extract_results],
            "transform_results": [r.to_dict() for r in self.transform_results],
            "load_results": [r.to_dict() for r in self.load_results],
            "total_records_extracted": self.total_records_extracted,
            "total_records_transformed": self.total_records_transformed,
            "total_records_loaded": self.total_records_loaded,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms
        }


@dataclass
class Pipeline:
    """Data pipeline definition"""

    id: str
    name: str
    description: str = ""
    source_ids: List[str] = field(default_factory=list)
    transform_ids: List[str] = field(default_factory=list)
    sink_ids: List[str] = field(default_factory=list)
    stages: List[PipelineStage] = field(default_factory=list)
    schedule: Optional[str] = None  # Cron expression
    enabled: bool = True
    continue_on_error: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    tags: List[str] = field(default_factory=list)

    # Runtime state
    status: PipelineStatus = PipelineStatus.DRAFT
    current_stage: Optional[str] = None
    last_result: Optional[PipelineResult] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_ids": self.source_ids,
            "transform_ids": self.transform_ids,
            "sink_ids": self.sink_ids,
            "stages": [s.to_dict() for s in self.stages],
            "schedule": self.schedule,
            "enabled": self.enabled,
            "continue_on_error": self.continue_on_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "tags": self.tags,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "last_result": self.last_result.to_dict() if self.last_result else None
        }


class PipelineManager:
    """Manages data pipelines"""

    def __init__(self):
        self.pipelines: Dict[str, Pipeline] = {}
        self._source_manager = get_source_manager()
        self._transform_manager = get_transform_manager()
        self._sink_manager = get_sink_manager()
        self._running_pipelines: Dict[str, asyncio.Task] = {}
        self._init_example_pipelines()

    def _init_example_pipelines(self) -> None:
        """Initialize example pipelines"""
        # These are just pipeline definitions; sources/transforms/sinks
        # would need to be created separately

        # Network Metrics Pipeline
        network_pipeline = Pipeline(
            id="pl_network_metrics",
            name="Network Metrics Pipeline",
            description="Collect and process network metrics from SNMP",
            source_ids=["snmp_collector"],
            transform_ids=["metric_normalizer", "metric_aggregator"],
            sink_ids=["prometheus_sink", "database_sink"],
            tags=["metrics", "network", "monitoring"]
        )
        self.pipelines[network_pipeline.id] = network_pipeline

        # Log Processing Pipeline
        log_pipeline = Pipeline(
            id="pl_log_processing",
            name="Log Processing Pipeline",
            description="Process and analyze syslog messages",
            source_ids=["syslog_source"],
            transform_ids=["log_parser", "severity_filter", "log_enricher"],
            sink_ids=["elasticsearch_sink", "alert_sink"],
            tags=["logs", "syslog", "analysis"]
        )
        self.pipelines[log_pipeline.id] = log_pipeline

        # Config Backup Pipeline
        backup_pipeline = Pipeline(
            id="pl_config_backup",
            name="Config Backup Pipeline",
            description="Backup device configurations via NETCONF",
            source_ids=["netconf_source"],
            transform_ids=["config_formatter"],
            sink_ids=["file_sink", "git_sink"],
            tags=["backup", "config", "compliance"]
        )
        self.pipelines[backup_pipeline.id] = backup_pipeline

    def create_pipeline(
        self,
        name: str,
        description: str = "",
        source_ids: Optional[List[str]] = None,
        transform_ids: Optional[List[str]] = None,
        sink_ids: Optional[List[str]] = None,
        schedule: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Pipeline:
        """Create a new pipeline"""
        pipeline_id = f"pl_{uuid.uuid4().hex[:8]}"

        pipeline = Pipeline(
            id=pipeline_id,
            name=name,
            description=description,
            source_ids=source_ids or [],
            transform_ids=transform_ids or [],
            sink_ids=sink_ids or [],
            schedule=schedule,
            tags=tags or []
        )

        self.pipelines[pipeline_id] = pipeline
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Optional[Pipeline]:
        """Get pipeline by ID"""
        return self.pipelines.get(pipeline_id)

    def update_pipeline(
        self,
        pipeline_id: str,
        **kwargs
    ) -> Optional[Pipeline]:
        """Update pipeline properties"""
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            return None

        for key, value in kwargs.items():
            if hasattr(pipeline, key):
                setattr(pipeline, key, value)

        pipeline.updated_at = datetime.now()
        return pipeline

    def delete_pipeline(self, pipeline_id: str) -> bool:
        """Delete a pipeline"""
        if pipeline_id in self._running_pipelines:
            self._running_pipelines[pipeline_id].cancel()
            del self._running_pipelines[pipeline_id]

        if pipeline_id in self.pipelines:
            del self.pipelines[pipeline_id]
            return True
        return False

    def enable_pipeline(self, pipeline_id: str) -> bool:
        """Enable a pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline:
            pipeline.enabled = True
            pipeline.status = PipelineStatus.READY
            pipeline.updated_at = datetime.now()
            return True
        return False

    def disable_pipeline(self, pipeline_id: str) -> bool:
        """Disable a pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline:
            pipeline.enabled = False
            pipeline.updated_at = datetime.now()
            return True
        return False

    def add_source(self, pipeline_id: str, source_id: str) -> bool:
        """Add a source to pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and source_id not in pipeline.source_ids:
            pipeline.source_ids.append(source_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    def remove_source(self, pipeline_id: str, source_id: str) -> bool:
        """Remove a source from pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and source_id in pipeline.source_ids:
            pipeline.source_ids.remove(source_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    def add_transform(self, pipeline_id: str, transform_id: str) -> bool:
        """Add a transform to pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and transform_id not in pipeline.transform_ids:
            pipeline.transform_ids.append(transform_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    def remove_transform(self, pipeline_id: str, transform_id: str) -> bool:
        """Remove a transform from pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and transform_id in pipeline.transform_ids:
            pipeline.transform_ids.remove(transform_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    def add_sink(self, pipeline_id: str, sink_id: str) -> bool:
        """Add a sink to pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and sink_id not in pipeline.sink_ids:
            pipeline.sink_ids.append(sink_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    def remove_sink(self, pipeline_id: str, sink_id: str) -> bool:
        """Remove a sink from pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and sink_id in pipeline.sink_ids:
            pipeline.sink_ids.remove(sink_id)
            pipeline.updated_at = datetime.now()
            return True
        return False

    async def run(self, pipeline_id: str) -> PipelineResult:
        """Run a pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            return PipelineResult(
                pipeline_id=pipeline_id,
                status=PipelineStatus.FAILED,
                errors=["Pipeline not found"]
            )

        if not pipeline.enabled:
            return PipelineResult(
                pipeline_id=pipeline_id,
                status=PipelineStatus.FAILED,
                errors=["Pipeline is disabled"]
            )

        started_at = datetime.now()
        pipeline.status = PipelineStatus.RUNNING
        pipeline.run_count += 1

        extract_results = []
        transform_results = []
        load_results = []
        errors = []
        all_data = []

        # Extract phase
        pipeline.current_stage = "extract"
        for source_id in pipeline.source_ids:
            source = self._source_manager.get_source(source_id)
            if not source:
                errors.append(f"Source not found: {source_id}")
                if not pipeline.continue_on_error:
                    break
                continue

            result = await self._source_manager.extract(source_id)
            extract_results.append(result)

            if result.success:
                all_data.extend(result.data)
            else:
                if result.error:
                    errors.append(f"Extract error ({source_id}): {result.error}")
                if not pipeline.continue_on_error:
                    break

        total_extracted = sum(r.record_count for r in extract_results if r.success)

        # Transform phase
        if all_data and (pipeline.continue_on_error or not errors):
            pipeline.current_stage = "transform"
            current_data = all_data

            for transform_id in pipeline.transform_ids:
                transform = self._transform_manager.get_transform(transform_id)
                if not transform:
                    errors.append(f"Transform not found: {transform_id}")
                    if not pipeline.continue_on_error:
                        break
                    continue

                result = self._transform_manager.apply(transform_id, current_data)
                transform_results.append(result)

                if result.success:
                    current_data = result.data
                else:
                    if result.error:
                        errors.append(f"Transform error ({transform_id}): {result.error}")
                    if not pipeline.continue_on_error:
                        break

            all_data = current_data

        total_transformed = len(all_data)

        # Load phase
        if all_data and (pipeline.continue_on_error or not errors):
            pipeline.current_stage = "load"
            for sink_id in pipeline.sink_ids:
                sink = self._sink_manager.get_sink(sink_id)
                if not sink:
                    errors.append(f"Sink not found: {sink_id}")
                    if not pipeline.continue_on_error:
                        break
                    continue

                result = await self._sink_manager.load(sink_id, all_data)
                load_results.append(result)

                if not result.success:
                    if result.error:
                        errors.append(f"Load error ({sink_id}): {result.error}")
                    if not pipeline.continue_on_error:
                        break

        total_loaded = sum(r.records_loaded for r in load_results if r.success)

        # Complete
        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        final_status = PipelineStatus.COMPLETED if not errors else PipelineStatus.FAILED
        pipeline.status = final_status
        pipeline.current_stage = None
        pipeline.last_run_at = completed_at

        if final_status == PipelineStatus.COMPLETED:
            pipeline.success_count += 1
        else:
            pipeline.failure_count += 1

        result = PipelineResult(
            pipeline_id=pipeline_id,
            status=final_status,
            extract_results=extract_results,
            transform_results=transform_results,
            load_results=load_results,
            total_records_extracted=total_extracted,
            total_records_transformed=total_transformed,
            total_records_loaded=total_loaded,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms
        )

        pipeline.last_result = result
        return result

    def start_async(self, pipeline_id: str) -> bool:
        """Start pipeline asynchronously"""
        if pipeline_id in self._running_pipelines:
            return False

        async def run_task():
            return await self.run(pipeline_id)

        task = asyncio.create_task(run_task())
        self._running_pipelines[pipeline_id] = task
        return True

    def pause(self, pipeline_id: str) -> bool:
        """Pause a running pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and pipeline.status == PipelineStatus.RUNNING:
            pipeline.status = PipelineStatus.PAUSED
            return True
        return False

    def resume(self, pipeline_id: str) -> bool:
        """Resume a paused pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if pipeline and pipeline.status == PipelineStatus.PAUSED:
            pipeline.status = PipelineStatus.RUNNING
            return True
        return False

    def cancel(self, pipeline_id: str) -> bool:
        """Cancel a pipeline"""
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            return False

        if pipeline_id in self._running_pipelines:
            self._running_pipelines[pipeline_id].cancel()
            del self._running_pipelines[pipeline_id]

        pipeline.status = PipelineStatus.CANCELLED
        return True

    def clone(self, pipeline_id: str, new_name: str) -> Optional[Pipeline]:
        """Clone a pipeline"""
        original = self.pipelines.get(pipeline_id)
        if not original:
            return None

        cloned = self.create_pipeline(
            name=new_name,
            description=original.description,
            source_ids=list(original.source_ids),
            transform_ids=list(original.transform_ids),
            sink_ids=list(original.sink_ids),
            schedule=original.schedule,
            tags=list(original.tags)
        )

        cloned.continue_on_error = original.continue_on_error
        return cloned

    def validate(self, pipeline_id: str) -> Dict[str, Any]:
        """Validate a pipeline configuration"""
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            return {"valid": False, "errors": ["Pipeline not found"]}

        errors = []
        warnings = []

        # Check sources
        for source_id in pipeline.source_ids:
            source = self._source_manager.get_source(source_id)
            if not source:
                errors.append(f"Source not found: {source_id}")
            elif not source.enabled:
                warnings.append(f"Source is disabled: {source_id}")

        # Check transforms
        for transform_id in pipeline.transform_ids:
            transform = self._transform_manager.get_transform(transform_id)
            if not transform:
                errors.append(f"Transform not found: {transform_id}")
            elif not transform.enabled:
                warnings.append(f"Transform is disabled: {transform_id}")

        # Check sinks
        for sink_id in pipeline.sink_ids:
            sink = self._sink_manager.get_sink(sink_id)
            if not sink:
                errors.append(f"Sink not found: {sink_id}")
            elif not sink.enabled:
                warnings.append(f"Sink is disabled: {sink_id}")

        # Check for empty pipeline
        if not pipeline.source_ids:
            errors.append("Pipeline has no sources")
        if not pipeline.sink_ids:
            warnings.append("Pipeline has no sinks")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def get_pipelines(
        self,
        status: Optional[PipelineStatus] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Pipeline]:
        """Get pipelines with filtering"""
        pipelines = list(self.pipelines.values())

        if status:
            pipelines = [p for p in pipelines if p.status == status]
        if enabled_only:
            pipelines = [p for p in pipelines if p.enabled]
        if tag:
            pipelines = [p for p in pipelines if tag in p.tags]

        return pipelines

    def get_running(self) -> List[Pipeline]:
        """Get running pipelines"""
        return [
            p for p in self.pipelines.values()
            if p.status == PipelineStatus.RUNNING
        ]

    def get_statistics(self) -> dict:
        """Get pipeline statistics"""
        by_status = {}
        total_runs = 0
        total_success = 0
        total_failure = 0

        for pipeline in self.pipelines.values():
            by_status[pipeline.status.value] = by_status.get(pipeline.status.value, 0) + 1
            total_runs += pipeline.run_count
            total_success += pipeline.success_count
            total_failure += pipeline.failure_count

        return {
            "total_pipelines": len(self.pipelines),
            "enabled_pipelines": len([p for p in self.pipelines.values() if p.enabled]),
            "running_pipelines": len(self._running_pipelines),
            "by_status": by_status,
            "total_runs": total_runs,
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": total_success / total_runs if total_runs > 0 else 0,
            "sources": self._source_manager.get_statistics(),
            "transforms": self._transform_manager.get_statistics(),
            "sinks": self._sink_manager.get_statistics()
        }


# Global pipeline manager instance
_pipeline_manager: Optional[PipelineManager] = None


def get_pipeline_manager() -> PipelineManager:
    """Get or create the global pipeline manager"""
    global _pipeline_manager
    if _pipeline_manager is None:
        _pipeline_manager = PipelineManager()
    return _pipeline_manager
