"""
Data Transforms

Provides:
- Data transformation definitions
- Transform operations
- Data processing
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
import re
import json


class TransformType(Enum):
    """Types of data transformations"""
    FILTER = "filter"
    MAP = "map"
    REDUCE = "reduce"
    AGGREGATE = "aggregate"
    JOIN = "join"
    SPLIT = "split"
    SORT = "sort"
    DEDUPE = "dedupe"
    ENRICH = "enrich"
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    CONVERT = "convert"


@dataclass
class TransformConfig:
    """Transform configuration"""

    target_field: Optional[str] = None  # Field to transform
    target_fields: List[str] = field(default_factory=list)  # Multiple fields
    condition: Optional[str] = None  # Filter/validation condition
    expression: Optional[str] = None  # Transform expression
    mapping: Dict[str, str] = field(default_factory=dict)  # Field mapping
    default_value: Optional[Any] = None  # Default for missing values
    aggregate_func: Optional[str] = None  # sum, avg, count, min, max
    group_by: Optional[str] = None  # Grouping field
    sort_order: str = "asc"  # asc or desc
    join_field: Optional[str] = None  # Field for joins
    output_field: Optional[str] = None  # Output field name
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_field": self.target_field,
            "target_fields": self.target_fields,
            "condition": self.condition,
            "expression": self.expression,
            "mapping": self.mapping,
            "default_value": self.default_value,
            "aggregate_func": self.aggregate_func,
            "group_by": self.group_by,
            "sort_order": self.sort_order,
            "join_field": self.join_field,
            "output_field": self.output_field,
            "extra": self.extra
        }


@dataclass
class TransformResult:
    """Result of transformation"""

    transform_id: str
    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    input_count: int = 0
    output_count: int = 0
    filtered_count: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "transform_id": self.transform_id,
            "success": self.success,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "filtered_count": self.filtered_count,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


@dataclass
class Transform:
    """Data transformation definition"""

    id: str
    name: str
    transform_type: TransformType
    description: str = ""
    config: TransformConfig = field(default_factory=TransformConfig)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    execution_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "transform_type": self.transform_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "execution_count": self.execution_count,
            "error_count": self.error_count
        }


class TransformManager:
    """Manages data transformations"""

    def __init__(self):
        self.transforms: Dict[str, Transform] = {}
        self._processors: Dict[TransformType, Callable] = {}
        self._register_builtin_processors()

    def _register_builtin_processors(self) -> None:
        """Register built-in transform processors"""

        def filter_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Filter records based on condition"""
            if not config.condition:
                return data

            result = []
            for record in data:
                # Simple condition evaluation
                condition = config.condition
                # Replace field references with values
                for key, value in record.items():
                    condition = condition.replace(f"${{{key}}}", str(value))

                try:
                    # Evaluate simple conditions
                    if "==" in condition:
                        parts = condition.split("==")
                        if parts[0].strip() == parts[1].strip():
                            result.append(record)
                    elif "!=" in condition:
                        parts = condition.split("!=")
                        if parts[0].strip() != parts[1].strip():
                            result.append(record)
                    elif ">" in condition:
                        parts = condition.split(">")
                        if float(parts[0].strip()) > float(parts[1].strip()):
                            result.append(record)
                    elif "<" in condition:
                        parts = condition.split("<")
                        if float(parts[0].strip()) < float(parts[1].strip()):
                            result.append(record)
                    elif condition.lower() == "true":
                        result.append(record)
                except (ValueError, TypeError):
                    pass

            return result

        def map_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Map/rename fields"""
            if not config.mapping:
                return data

            result = []
            for record in data:
                new_record = {}
                for old_key, new_key in config.mapping.items():
                    if old_key in record:
                        new_record[new_key] = record[old_key]
                # Include unmapped fields
                for key, value in record.items():
                    if key not in config.mapping and key not in new_record:
                        new_record[key] = value
                result.append(new_record)

            return result

        def aggregate_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Aggregate records"""
            if not config.aggregate_func or not config.target_field:
                return data

            values = [r.get(config.target_field, 0) for r in data]
            try:
                values = [float(v) for v in values if v is not None]
            except (ValueError, TypeError):
                values = []

            if config.aggregate_func == "sum":
                result = sum(values)
            elif config.aggregate_func == "avg":
                result = sum(values) / len(values) if values else 0
            elif config.aggregate_func == "count":
                result = len(data)
            elif config.aggregate_func == "min":
                result = min(values) if values else 0
            elif config.aggregate_func == "max":
                result = max(values) if values else 0
            else:
                result = len(data)

            output_field = config.output_field or f"{config.aggregate_func}_{config.target_field}"
            return [{output_field: result, "record_count": len(data)}]

        def sort_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Sort records"""
            if not config.target_field:
                return data

            reverse = config.sort_order == "desc"
            try:
                return sorted(
                    data,
                    key=lambda x: x.get(config.target_field, ""),
                    reverse=reverse
                )
            except TypeError:
                return data

        def dedupe_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Remove duplicate records"""
            if not config.target_field:
                # Dedupe by all fields
                seen = set()
                result = []
                for record in data:
                    key = json.dumps(record, sort_keys=True)
                    if key not in seen:
                        seen.add(key)
                        result.append(record)
                return result

            # Dedupe by specific field
            seen = set()
            result = []
            for record in data:
                key = record.get(config.target_field)
                if key not in seen:
                    seen.add(key)
                    result.append(record)
            return result

        def enrich_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Enrich records with additional data"""
            enrichments = config.extra.get("enrichments", {})
            result = []
            for record in data:
                new_record = dict(record)
                new_record.update(enrichments)
                # Add timestamp if not present
                if "enriched_at" not in new_record:
                    new_record["enriched_at"] = datetime.now().isoformat()
                result.append(new_record)
            return result

        def validate_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Validate records against schema"""
            required_fields = config.target_fields or []
            result = []
            for record in data:
                valid = True
                for field_name in required_fields:
                    if field_name not in record or record[field_name] is None:
                        valid = False
                        break
                if valid:
                    result.append(record)
            return result

        def normalize_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Normalize field values"""
            result = []
            for record in data:
                new_record = dict(record)
                for key, value in new_record.items():
                    # Convert strings to lowercase
                    if isinstance(value, str):
                        new_record[key] = value.lower().strip()
                    # Remove None values
                    if config.default_value is not None and value is None:
                        new_record[key] = config.default_value
                result.append(new_record)
            return result

        def convert_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Convert field types"""
            type_mapping = config.extra.get("type_mapping", {})
            result = []
            for record in data:
                new_record = dict(record)
                for field_name, target_type in type_mapping.items():
                    if field_name in new_record:
                        value = new_record[field_name]
                        try:
                            if target_type == "int":
                                new_record[field_name] = int(value)
                            elif target_type == "float":
                                new_record[field_name] = float(value)
                            elif target_type == "string":
                                new_record[field_name] = str(value)
                            elif target_type == "bool":
                                new_record[field_name] = bool(value)
                        except (ValueError, TypeError):
                            pass
                result.append(new_record)
            return result

        def split_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Split records based on field"""
            if not config.target_field:
                return data

            result = []
            delimiter = config.extra.get("delimiter", ",")
            for record in data:
                value = record.get(config.target_field, "")
                if isinstance(value, str):
                    parts = value.split(delimiter)
                    for part in parts:
                        new_record = dict(record)
                        new_record[config.target_field] = part.strip()
                        result.append(new_record)
                else:
                    result.append(record)
            return result

        def join_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Join with additional data (lookup)"""
            lookup_data = config.extra.get("lookup_data", [])
            if not lookup_data or not config.join_field:
                return data

            # Build lookup dictionary
            lookup = {}
            for item in lookup_data:
                key = item.get(config.join_field)
                if key:
                    lookup[key] = item

            # Join records
            result = []
            for record in data:
                key = record.get(config.join_field)
                if key and key in lookup:
                    new_record = {**record, **lookup[key]}
                else:
                    new_record = dict(record)
                result.append(new_record)

            return result

        def reduce_processor(
            data: List[Dict[str, Any]],
            config: TransformConfig
        ) -> List[Dict[str, Any]]:
            """Reduce records to subset of fields"""
            if not config.target_fields:
                return data

            result = []
            for record in data:
                new_record = {}
                for field_name in config.target_fields:
                    if field_name in record:
                        new_record[field_name] = record[field_name]
                result.append(new_record)
            return result

        self._processors = {
            TransformType.FILTER: filter_processor,
            TransformType.MAP: map_processor,
            TransformType.AGGREGATE: aggregate_processor,
            TransformType.SORT: sort_processor,
            TransformType.DEDUPE: dedupe_processor,
            TransformType.ENRICH: enrich_processor,
            TransformType.VALIDATE: validate_processor,
            TransformType.NORMALIZE: normalize_processor,
            TransformType.CONVERT: convert_processor,
            TransformType.SPLIT: split_processor,
            TransformType.JOIN: join_processor,
            TransformType.REDUCE: reduce_processor
        }

    def register_processor(
        self,
        transform_type: TransformType,
        processor: Callable
    ) -> None:
        """Register a custom transform processor"""
        self._processors[transform_type] = processor

    def create_transform(
        self,
        name: str,
        transform_type: TransformType,
        description: str = "",
        config: Optional[TransformConfig] = None
    ) -> Transform:
        """Create a new transform"""
        transform_id = f"xfm_{uuid.uuid4().hex[:8]}"

        transform = Transform(
            id=transform_id,
            name=name,
            transform_type=transform_type,
            description=description,
            config=config or TransformConfig()
        )

        self.transforms[transform_id] = transform
        return transform

    def get_transform(self, transform_id: str) -> Optional[Transform]:
        """Get transform by ID"""
        return self.transforms.get(transform_id)

    def update_transform(
        self,
        transform_id: str,
        **kwargs
    ) -> Optional[Transform]:
        """Update transform properties"""
        transform = self.transforms.get(transform_id)
        if not transform:
            return None

        for key, value in kwargs.items():
            if hasattr(transform, key):
                setattr(transform, key, value)

        return transform

    def delete_transform(self, transform_id: str) -> bool:
        """Delete a transform"""
        if transform_id in self.transforms:
            del self.transforms[transform_id]
            return True
        return False

    def apply(
        self,
        transform_id: str,
        data: List[Dict[str, Any]]
    ) -> TransformResult:
        """Apply a transform to data"""
        transform = self.transforms.get(transform_id)
        if not transform:
            return TransformResult(
                transform_id=transform_id,
                success=False,
                error="Transform not found"
            )

        if not transform.enabled:
            return TransformResult(
                transform_id=transform_id,
                success=False,
                error="Transform is disabled"
            )

        processor = self._processors.get(transform.transform_type)
        if not processor:
            return TransformResult(
                transform_id=transform_id,
                success=False,
                error=f"No processor for type: {transform.transform_type.value}"
            )

        started_at = datetime.now()
        try:
            result_data = processor(data, transform.config)
            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            transform.execution_count += 1

            return TransformResult(
                transform_id=transform_id,
                success=True,
                data=result_data,
                input_count=len(data),
                output_count=len(result_data),
                filtered_count=len(data) - len(result_data),
                duration_ms=duration_ms
            )

        except Exception as e:
            transform.error_count += 1
            return TransformResult(
                transform_id=transform_id,
                success=False,
                error=str(e),
                input_count=len(data)
            )

    def apply_chain(
        self,
        transform_ids: List[str],
        data: List[Dict[str, Any]]
    ) -> TransformResult:
        """Apply multiple transforms in sequence"""
        current_data = data
        total_filtered = 0

        for transform_id in transform_ids:
            result = self.apply(transform_id, current_data)
            if not result.success:
                return result
            current_data = result.data
            total_filtered += result.filtered_count

        return TransformResult(
            transform_id=",".join(transform_ids),
            success=True,
            data=current_data,
            input_count=len(data),
            output_count=len(current_data),
            filtered_count=total_filtered
        )

    def get_transforms(
        self,
        transform_type: Optional[TransformType] = None,
        enabled_only: bool = False
    ) -> List[Transform]:
        """Get transforms with filtering"""
        transforms = list(self.transforms.values())

        if transform_type:
            transforms = [t for t in transforms if t.transform_type == transform_type]
        if enabled_only:
            transforms = [t for t in transforms if t.enabled]

        return transforms

    def get_statistics(self) -> dict:
        """Get transform statistics"""
        by_type = {}
        total_executions = 0
        total_errors = 0

        for transform in self.transforms.values():
            by_type[transform.transform_type.value] = by_type.get(transform.transform_type.value, 0) + 1
            total_executions += transform.execution_count
            total_errors += transform.error_count

        return {
            "total_transforms": len(self.transforms),
            "enabled_transforms": len([t for t in self.transforms.values() if t.enabled]),
            "by_type": by_type,
            "total_executions": total_executions,
            "total_errors": total_errors,
            "available_processors": len(self._processors)
        }


# Global transform manager instance
_transform_manager: Optional[TransformManager] = None


def get_transform_manager() -> TransformManager:
    """Get or create the global transform manager"""
    global _transform_manager
    if _transform_manager is None:
        _transform_manager = TransformManager()
    return _transform_manager
