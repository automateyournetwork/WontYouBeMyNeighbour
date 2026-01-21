"""Tests for data pipeline module"""

import pytest
from agentic.pipelines import (
    DataSource, SourceType, SourceConfig, SourceManager, get_source_manager,
    Transform, TransformType, TransformConfig, TransformManager, get_transform_manager,
    DataSink, SinkType, SinkConfig, SinkManager, get_sink_manager,
    Pipeline, PipelineStatus, PipelineResult, PipelineManager, get_pipeline_manager
)


class TestSourceManager:
    """Tests for SourceManager"""

    def test_create_source(self):
        """Test source creation"""
        manager = SourceManager()
        source = manager.create_source(
            name="test-source",
            source_type=SourceType.API,
            description="Test source"
        )
        assert source.name == "test-source"
        assert source.source_type == SourceType.API

    def test_get_source(self):
        """Test getting source by ID"""
        manager = SourceManager()
        source = manager.create_source("test", SourceType.DATABASE)

        retrieved = manager.get_source(source.id)
        assert retrieved is not None
        assert retrieved.id == source.id


class TestTransformManager:
    """Tests for TransformManager"""

    def test_create_transform(self):
        """Test transform creation"""
        manager = TransformManager()
        transform = manager.create_transform(
            name="test-transform",
            transform_type=TransformType.FILTER,
            description="Test transform"
        )
        assert transform.name == "test-transform"
        assert transform.transform_type == TransformType.FILTER

    def test_get_transform(self):
        """Test getting transform by ID"""
        manager = TransformManager()
        transform = manager.create_transform("test", TransformType.MAP)

        retrieved = manager.get_transform(transform.id)
        assert retrieved is not None
        assert retrieved.id == transform.id


class TestSinkManager:
    """Tests for SinkManager"""

    def test_create_sink(self):
        """Test sink creation"""
        manager = SinkManager()
        sink = manager.create_sink(
            name="test-sink",
            sink_type=SinkType.DATABASE,
            description="Test sink"
        )
        assert sink.name == "test-sink"
        assert sink.sink_type == SinkType.DATABASE

    def test_get_sink(self):
        """Test getting sink by ID"""
        manager = SinkManager()
        sink = manager.create_sink("test", SinkType.FILE)

        retrieved = manager.get_sink(sink.id)
        assert retrieved is not None
        assert retrieved.id == sink.id


class TestPipelineManager:
    """Tests for PipelineManager"""

    def test_create_pipeline(self):
        """Test pipeline creation"""
        manager = PipelineManager()
        pipeline = manager.create_pipeline(
            name="test-pipeline",
            description="Test pipeline"
        )
        assert pipeline.name == "test-pipeline"
        assert pipeline.status == PipelineStatus.DRAFT

    def test_get_pipeline(self):
        """Test getting pipeline by ID"""
        manager = PipelineManager()
        pipeline = manager.create_pipeline("test")

        retrieved = manager.get_pipeline(pipeline.id)
        assert retrieved is not None
        assert retrieved.id == pipeline.id


class TestSourceType:
    """Tests for SourceType enum"""

    def test_source_types_exist(self):
        """Test source types are defined"""
        assert hasattr(SourceType, "API")
        assert hasattr(SourceType, "DATABASE")
        assert hasattr(SourceType, "FILE")
        assert hasattr(SourceType, "STREAM")


class TestTransformType:
    """Tests for TransformType enum"""

    def test_transform_types_exist(self):
        """Test transform types are defined"""
        assert hasattr(TransformType, "FILTER")
        assert hasattr(TransformType, "MAP")
        assert hasattr(TransformType, "REDUCE")
        assert hasattr(TransformType, "AGGREGATE")


class TestSinkType:
    """Tests for SinkType enum"""

    def test_sink_types_exist(self):
        """Test sink types are defined"""
        assert hasattr(SinkType, "API")
        assert hasattr(SinkType, "DATABASE")
        assert hasattr(SinkType, "FILE")
        assert hasattr(SinkType, "WEBHOOK")


class TestPipelineStatus:
    """Tests for PipelineStatus enum"""

    def test_statuses_exist(self):
        """Test pipeline statuses are defined"""
        assert hasattr(PipelineStatus, "DRAFT")
        assert hasattr(PipelineStatus, "READY")
        assert hasattr(PipelineStatus, "RUNNING")
        assert hasattr(PipelineStatus, "COMPLETED")
        assert hasattr(PipelineStatus, "FAILED")
