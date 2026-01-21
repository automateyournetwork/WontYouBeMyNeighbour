"""
Configuration Schema Validation

Provides:
- Schema definitions
- Type validation
- Range validation
- Pattern matching
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime
from enum import Enum


class SchemaType(Enum):
    """Configuration value types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ENUM = "enum"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    PORT = "port"
    URL = "url"
    EMAIL = "email"
    DURATION = "duration"
    ANY = "any"


@dataclass
class SchemaField:
    """Schema field definition"""

    name: str
    type: SchemaType
    required: bool = False
    default: Any = None
    description: str = ""
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    enum_values: Optional[List[Any]] = None
    array_type: Optional[SchemaType] = None
    object_schema: Optional["ConfigSchema"] = None

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "type": self.type.value,
            "required": self.required,
            "description": self.description
        }
        if self.default is not None:
            result["default"] = self.default
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        if self.min_length is not None:
            result["min_length"] = self.min_length
        if self.max_length is not None:
            result["max_length"] = self.max_length
        if self.pattern:
            result["pattern"] = self.pattern
        if self.enum_values:
            result["enum_values"] = self.enum_values
        if self.array_type:
            result["array_type"] = self.array_type.value
        return result


@dataclass
class ConfigSchema:
    """Configuration schema definition"""

    name: str
    version: str = "1.0"
    description: str = ""
    fields: Dict[str, SchemaField] = field(default_factory=dict)
    allow_extra_fields: bool = False

    def add_field(self, field: SchemaField) -> None:
        """Add a field to schema"""
        self.fields[field.name] = field

    def get_field(self, name: str) -> Optional[SchemaField]:
        """Get field by name"""
        return self.fields.get(name)

    def get_required_fields(self) -> List[SchemaField]:
        """Get required fields"""
        return [f for f in self.fields.values() if f.required]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "fields": {n: f.to_dict() for n, f in self.fields.items()},
            "allow_extra_fields": self.allow_extra_fields
        }


@dataclass
class ValidationError:
    """Validation error"""

    field: str
    message: str
    value: Any = None

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "message": self.message,
            "value": str(self.value) if self.value is not None else None
        }


@dataclass
class ValidationResult:
    """Result of schema validation"""

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, field: str, message: str, value: Any = None) -> None:
        """Add validation error"""
        self.errors.append(ValidationError(field=field, message=message, value=value))
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add validation warning"""
        self.warnings.append(message)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "error_count": len(self.errors)
        }


class SchemaValidator:
    """Validates configuration against schemas"""

    # IP address pattern
    IP_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )

    # CIDR pattern
    CIDR_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)/'
        r'(?:[0-9]|[1-2][0-9]|3[0-2])$'
    )

    # URL pattern
    URL_PATTERN = re.compile(
        r'^https?://[^\s/$.?#].[^\s]*$',
        re.IGNORECASE
    )

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )

    def __init__(self):
        self.schemas: Dict[str, ConfigSchema] = {}
        self._register_default_schemas()

    def register_schema(self, schema: ConfigSchema) -> None:
        """Register a schema"""
        self.schemas[schema.name] = schema

    def get_schema(self, name: str) -> Optional[ConfigSchema]:
        """Get schema by name"""
        return self.schemas.get(name)

    def validate(
        self,
        config: Dict[str, Any],
        schema_name: str
    ) -> ValidationResult:
        """Validate config against schema"""
        schema = self.schemas.get(schema_name)
        if not schema:
            result = ValidationResult(valid=False)
            result.add_error("_schema", f"Schema '{schema_name}' not found")
            return result

        return self.validate_with_schema(config, schema)

    def validate_with_schema(
        self,
        config: Dict[str, Any],
        schema: ConfigSchema
    ) -> ValidationResult:
        """Validate config against schema object"""
        result = ValidationResult(valid=True)

        # Check required fields
        for field in schema.get_required_fields():
            if field.name not in config:
                result.add_error(
                    field.name,
                    f"Required field '{field.name}' is missing"
                )

        # Check extra fields
        if not schema.allow_extra_fields:
            for key in config:
                if key not in schema.fields:
                    result.add_warning(f"Unknown field '{key}' will be ignored")

        # Validate each field
        for field_name, field_def in schema.fields.items():
            if field_name in config:
                value = config[field_name]
                self._validate_field(field_name, value, field_def, result)

        return result

    def validate_field_value(
        self,
        value: Any,
        field_type: SchemaType,
        constraints: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Validate a single field value"""
        result = ValidationResult(valid=True)

        # Create temporary field
        field = SchemaField(
            name="_value",
            type=field_type,
            min_value=constraints.get("min_value") if constraints else None,
            max_value=constraints.get("max_value") if constraints else None,
            min_length=constraints.get("min_length") if constraints else None,
            max_length=constraints.get("max_length") if constraints else None,
            pattern=constraints.get("pattern") if constraints else None,
            enum_values=constraints.get("enum_values") if constraints else None
        )

        self._validate_field("_value", value, field, result)
        return result

    def get_statistics(self) -> dict:
        """Get validator statistics"""
        return {
            "registered_schemas": len(self.schemas),
            "schemas": list(self.schemas.keys()),
            "supported_types": [t.value for t in SchemaType]
        }

    def _validate_field(
        self,
        name: str,
        value: Any,
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate a single field"""
        # Type validation
        if not self._validate_type(value, field.type, field):
            result.add_error(
                name,
                f"Expected type '{field.type.value}', got '{type(value).__name__}'",
                value
            )
            return

        # Type-specific validation
        if field.type == SchemaType.STRING:
            self._validate_string(name, value, field, result)
        elif field.type == SchemaType.INTEGER:
            self._validate_number(name, value, field, result)
        elif field.type == SchemaType.FLOAT:
            self._validate_number(name, value, field, result)
        elif field.type == SchemaType.ARRAY:
            self._validate_array(name, value, field, result)
        elif field.type == SchemaType.OBJECT:
            self._validate_object(name, value, field, result)
        elif field.type == SchemaType.ENUM:
            self._validate_enum(name, value, field, result)
        elif field.type == SchemaType.IP_ADDRESS:
            self._validate_ip(name, value, result)
        elif field.type == SchemaType.CIDR:
            self._validate_cidr(name, value, result)
        elif field.type == SchemaType.PORT:
            self._validate_port(name, value, result)
        elif field.type == SchemaType.URL:
            self._validate_url(name, value, result)
        elif field.type == SchemaType.EMAIL:
            self._validate_email(name, value, result)

    def _validate_type(self, value: Any, expected: SchemaType, field: SchemaField) -> bool:
        """Validate value type"""
        type_map = {
            SchemaType.STRING: str,
            SchemaType.INTEGER: int,
            SchemaType.FLOAT: (int, float),
            SchemaType.BOOLEAN: bool,
            SchemaType.ARRAY: list,
            SchemaType.OBJECT: dict,
            SchemaType.ENUM: type(None),  # Will check separately
            SchemaType.IP_ADDRESS: str,
            SchemaType.CIDR: str,
            SchemaType.PORT: int,
            SchemaType.URL: str,
            SchemaType.EMAIL: str,
            SchemaType.DURATION: (int, str),
            SchemaType.ANY: object
        }

        expected_type = type_map.get(expected, object)
        if expected == SchemaType.ENUM:
            return True  # Enum validation is done separately
        if expected == SchemaType.ANY:
            return True

        return isinstance(value, expected_type)

    def _validate_string(
        self,
        name: str,
        value: str,
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate string field"""
        if field.min_length is not None and len(value) < field.min_length:
            result.add_error(
                name,
                f"String length {len(value)} is less than minimum {field.min_length}",
                value
            )
        if field.max_length is not None and len(value) > field.max_length:
            result.add_error(
                name,
                f"String length {len(value)} exceeds maximum {field.max_length}",
                value
            )
        if field.pattern:
            if not re.match(field.pattern, value):
                result.add_error(
                    name,
                    f"Value does not match pattern '{field.pattern}'",
                    value
                )

    def _validate_number(
        self,
        name: str,
        value: Union[int, float],
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate numeric field"""
        if field.min_value is not None and value < field.min_value:
            result.add_error(
                name,
                f"Value {value} is less than minimum {field.min_value}",
                value
            )
        if field.max_value is not None and value > field.max_value:
            result.add_error(
                name,
                f"Value {value} exceeds maximum {field.max_value}",
                value
            )

    def _validate_array(
        self,
        name: str,
        value: list,
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate array field"""
        if field.min_length is not None and len(value) < field.min_length:
            result.add_error(
                name,
                f"Array length {len(value)} is less than minimum {field.min_length}",
                value
            )
        if field.max_length is not None and len(value) > field.max_length:
            result.add_error(
                name,
                f"Array length {len(value)} exceeds maximum {field.max_length}",
                value
            )

        # Validate array items
        if field.array_type:
            for i, item in enumerate(value):
                if not self._validate_type(item, field.array_type, field):
                    result.add_error(
                        f"{name}[{i}]",
                        f"Expected type '{field.array_type.value}'",
                        item
                    )

    def _validate_object(
        self,
        name: str,
        value: dict,
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate object field"""
        if field.object_schema:
            nested_result = self.validate_with_schema(value, field.object_schema)
            for error in nested_result.errors:
                result.add_error(
                    f"{name}.{error.field}",
                    error.message,
                    error.value
                )

    def _validate_enum(
        self,
        name: str,
        value: Any,
        field: SchemaField,
        result: ValidationResult
    ) -> None:
        """Validate enum field"""
        if field.enum_values and value not in field.enum_values:
            result.add_error(
                name,
                f"Value must be one of: {field.enum_values}",
                value
            )

    def _validate_ip(self, name: str, value: str, result: ValidationResult) -> None:
        """Validate IP address"""
        if not self.IP_PATTERN.match(value):
            result.add_error(name, "Invalid IP address format", value)

    def _validate_cidr(self, name: str, value: str, result: ValidationResult) -> None:
        """Validate CIDR notation"""
        if not self.CIDR_PATTERN.match(value):
            result.add_error(name, "Invalid CIDR notation", value)

    def _validate_port(self, name: str, value: int, result: ValidationResult) -> None:
        """Validate port number"""
        if not 0 <= value <= 65535:
            result.add_error(name, "Port must be between 0 and 65535", value)

    def _validate_url(self, name: str, value: str, result: ValidationResult) -> None:
        """Validate URL"""
        if not self.URL_PATTERN.match(value):
            result.add_error(name, "Invalid URL format", value)

    def _validate_email(self, name: str, value: str, result: ValidationResult) -> None:
        """Validate email"""
        if not self.EMAIL_PATTERN.match(value):
            result.add_error(name, "Invalid email format", value)

    def _register_default_schemas(self) -> None:
        """Register default configuration schemas"""
        # Network configuration schema
        network_schema = ConfigSchema(
            name="network",
            description="Network configuration schema"
        )
        network_schema.add_field(SchemaField(
            name="router_id", type=SchemaType.IP_ADDRESS, required=True,
            description="Router identifier"
        ))
        network_schema.add_field(SchemaField(
            name="interfaces", type=SchemaType.ARRAY, required=True,
            description="Network interfaces", array_type=SchemaType.OBJECT
        ))
        self.register_schema(network_schema)

        # OSPF configuration schema
        ospf_schema = ConfigSchema(
            name="ospf",
            description="OSPF configuration schema"
        )
        ospf_schema.add_field(SchemaField(
            name="router_id", type=SchemaType.IP_ADDRESS, required=True,
            description="OSPF router ID"
        ))
        ospf_schema.add_field(SchemaField(
            name="area", type=SchemaType.STRING, required=True,
            description="OSPF area ID"
        ))
        ospf_schema.add_field(SchemaField(
            name="hello_interval", type=SchemaType.INTEGER,
            default=10, min_value=1, max_value=65535,
            description="Hello interval in seconds"
        ))
        ospf_schema.add_field(SchemaField(
            name="dead_interval", type=SchemaType.INTEGER,
            default=40, min_value=1, max_value=65535,
            description="Dead interval in seconds"
        ))
        self.register_schema(ospf_schema)

        # BGP configuration schema
        bgp_schema = ConfigSchema(
            name="bgp",
            description="BGP configuration schema"
        )
        bgp_schema.add_field(SchemaField(
            name="local_as", type=SchemaType.INTEGER, required=True,
            min_value=1, max_value=4294967295,
            description="Local AS number"
        ))
        bgp_schema.add_field(SchemaField(
            name="router_id", type=SchemaType.IP_ADDRESS, required=True,
            description="BGP router ID"
        ))
        bgp_schema.add_field(SchemaField(
            name="neighbors", type=SchemaType.ARRAY,
            description="BGP neighbors", array_type=SchemaType.OBJECT
        ))
        self.register_schema(bgp_schema)


# Global schema validator instance
_schema_validator: Optional[SchemaValidator] = None


def get_schema_validator() -> SchemaValidator:
    """Get or create the global schema validator"""
    global _schema_validator
    if _schema_validator is None:
        _schema_validator = SchemaValidator()
    return _schema_validator
