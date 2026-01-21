"""
TOON Schemas - Validation schemas for Token Oriented Object Notation

Provides schema definitions and validation logic for:
- Agent configurations
- Network definitions
- Interface specs
- Protocol configurations
- MCP configurations
- Runtime state
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
import re


@dataclass
class SchemaField:
    """Definition of a schema field"""
    name: str
    type: str  # 'str', 'int', 'float', 'bool', 'list', 'dict', 'any'
    required: bool = False
    default: Any = None
    pattern: Optional[str] = None  # Regex pattern for strings
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_values: Optional[List[Any]] = None
    item_schema: Optional[str] = None  # Schema name for list items


class Schema:
    """Base schema class for TOON validation"""

    def __init__(self, name: str, fields: List[SchemaField]):
        self.name = name
        self.fields = {f.name: f for f in fields}

    def validate(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate data against schema

        Args:
            data: Dict to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check required fields
        for field_name, field_def in self.fields.items():
            if field_def.required and field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        # Validate each present field
        for key, value in data.items():
            if key in self.fields:
                field_errors = self._validate_field(key, value, self.fields[key])
                errors.extend(field_errors)

        return errors

    def _validate_field(self, name: str, value: Any, field: SchemaField) -> List[str]:
        """Validate a single field"""
        errors = []

        # Type check
        type_valid, type_error = self._check_type(value, field.type)
        if not type_valid:
            errors.append(f"Field '{name}': {type_error}")
            return errors  # Skip other checks if type is wrong

        # Pattern check (for strings)
        if field.pattern and isinstance(value, str):
            if not re.match(field.pattern, value):
                errors.append(f"Field '{name}': does not match pattern {field.pattern}")

        # Range checks (for numbers)
        if isinstance(value, (int, float)):
            if field.min_value is not None and value < field.min_value:
                errors.append(f"Field '{name}': value {value} below minimum {field.min_value}")
            if field.max_value is not None and value > field.max_value:
                errors.append(f"Field '{name}': value {value} above maximum {field.max_value}")

        # Length checks (for strings/lists)
        if isinstance(value, (str, list)):
            if field.min_length is not None and len(value) < field.min_length:
                errors.append(f"Field '{name}': length {len(value)} below minimum {field.min_length}")
            if field.max_length is not None and len(value) > field.max_length:
                errors.append(f"Field '{name}': length {len(value)} above maximum {field.max_length}")

        # Allowed values check
        if field.allowed_values is not None and value not in field.allowed_values:
            errors.append(f"Field '{name}': value '{value}' not in allowed values {field.allowed_values}")

        # Nested list item validation
        if field.item_schema and isinstance(value, list):
            item_schema = get_schema(field.item_schema)
            if item_schema:
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        item_errors = item_schema.validate(item)
                        for error in item_errors:
                            errors.append(f"Field '{name}[{i}]': {error}")

        return errors

    def _check_type(self, value: Any, expected_type: str) -> tuple:
        """Check if value matches expected type"""
        type_map = {
            'str': str,
            'int': int,
            'float': (int, float),
            'bool': bool,
            'list': list,
            'dict': dict,
            'any': object
        }

        if expected_type == 'any':
            return True, None

        expected = type_map.get(expected_type)
        if expected is None:
            return True, None  # Unknown type, accept anything

        if not isinstance(value, expected):
            return False, f"expected {expected_type}, got {type(value).__name__}"

        return True, None


# Schema Definitions

InterfaceSchema = Schema("interface", [
    SchemaField("id", "str", required=True, min_length=1),
    SchemaField("n", "str", required=True, min_length=1),  # name
    SchemaField("t", "str", allowed_values=["eth", "lo", "vlan", "tun"]),
    SchemaField("a", "list"),  # addresses
    SchemaField("m", "str", pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"),  # MAC
    SchemaField("s", "str", allowed_values=["up", "down"]),
    SchemaField("mtu", "int", min_value=68, max_value=65535)
])

ProtocolConfigSchema = Schema("protocol_config", [
    SchemaField("p", "str", required=True, allowed_values=["ospf", "ospfv3", "ibgp", "ebgp"]),
    SchemaField("r", "str", required=True),  # router-id
    SchemaField("a", "str"),  # area
    SchemaField("asn", "int", min_value=1, max_value=4294967295),
    SchemaField("peers", "list"),
    SchemaField("nets", "list"),
    SchemaField("opts", "dict")
])

MCPConfigSchema = Schema("mcp_config", [
    SchemaField("id", "str", required=True),
    SchemaField("t", "str", required=True, allowed_values=[
        "gait", "markmap", "pyats", "servicenow", "netbox", "rfc", "slack", "github", "custom"
    ]),
    SchemaField("url", "str", required=True),
    SchemaField("c", "dict"),  # config
    SchemaField("e", "bool")  # enabled
])

RuntimeStateSchema = Schema("runtime_state", [
    SchemaField("ts", "str", required=True),  # timestamp
    SchemaField("rib", "list"),
    SchemaField("lsdb", "list"),
    SchemaField("nbrs", "list"),
    SchemaField("peers", "list"),
    SchemaField("metrics", "dict")
])

AgentSchema = Schema("agent", [
    SchemaField("id", "str", required=True, min_length=1, max_length=64),
    SchemaField("n", "str", required=True, min_length=1, max_length=128),  # name
    SchemaField("r", "str", required=True),  # router-id
    SchemaField("v", "str"),  # version
    SchemaField("ifs", "list", item_schema="interface"),
    SchemaField("protos", "list", item_schema="protocol_config"),
    SchemaField("mcps", "list", item_schema="mcp_config"),
    SchemaField("state", "dict"),
    SchemaField("meta", "dict")
])

DockerConfigSchema = Schema("docker_config", [
    SchemaField("n", "str", required=True, min_length=1),  # name
    SchemaField("driver", "str", allowed_values=["bridge", "host", "overlay", "macvlan"]),
    SchemaField("subnet", "str", pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$"),
    SchemaField("gw", "str"),  # gateway
    SchemaField("opts", "dict")
])

TopologySchema = Schema("topology", [
    SchemaField("links", "list"),
    SchemaField("layout", "dict")
])

NetworkSchema = Schema("network", [
    SchemaField("id", "str", required=True, min_length=1, max_length=64),
    SchemaField("n", "str", required=True, min_length=1, max_length=128),  # name
    SchemaField("v", "str"),  # version
    SchemaField("created", "str"),
    SchemaField("modified", "str"),
    SchemaField("docker", "dict"),
    SchemaField("agents", "list", item_schema="agent"),
    SchemaField("topo", "dict"),
    SchemaField("mcps", "list", item_schema="mcp_config"),
    SchemaField("meta", "dict")
])


# Schema registry
_SCHEMAS: Dict[str, Schema] = {
    "interface": InterfaceSchema,
    "protocol_config": ProtocolConfigSchema,
    "mcp_config": MCPConfigSchema,
    "runtime_state": RuntimeStateSchema,
    "agent": AgentSchema,
    "docker_config": DockerConfigSchema,
    "topology": TopologySchema,
    "network": NetworkSchema
}


def get_schema(name: str) -> Optional[Schema]:
    """
    Get schema by name

    Args:
        name: Schema name

    Returns:
        Schema instance or None if not found
    """
    return _SCHEMAS.get(name)


def list_schemas() -> List[str]:
    """
    List available schema names

    Returns:
        List of schema names
    """
    return list(_SCHEMAS.keys())


def register_schema(schema: Schema):
    """
    Register a custom schema

    Args:
        schema: Schema to register
    """
    _SCHEMAS[schema.name] = schema


def validate_agent(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate agent data

    Args:
        data: Agent dict to validate

    Returns:
        Validation result with 'valid' and 'errors'
    """
    errors = AgentSchema.validate(data)
    return {"valid": len(errors) == 0, "errors": errors if errors else None}


def validate_network(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate network data

    Args:
        data: Network dict to validate

    Returns:
        Validation result with 'valid' and 'errors'
    """
    errors = NetworkSchema.validate(data)
    return {"valid": len(errors) == 0, "errors": errors if errors else None}
