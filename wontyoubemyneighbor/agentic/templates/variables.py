"""
Template Variables

Provides:
- Variable definitions
- Variable types
- Variable management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class VariableType(Enum):
    """Types of variables"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    MAC_ADDRESS = "mac_address"
    HOSTNAME = "hostname"
    PORT = "port"
    VLAN = "vlan"
    ASN = "asn"
    SECRET = "secret"
    PATH = "path"
    URL = "url"
    DATETIME = "datetime"
    ENUM = "enum"
    CUSTOM = "custom"


class VariableScope(Enum):
    """Variable scope"""
    GLOBAL = "global"  # Available everywhere
    TEMPLATE = "template"  # Available in template
    RENDER = "render"  # Available during render
    LOCAL = "local"  # Local to block
    ENVIRONMENT = "environment"  # From environment


@dataclass
class VariableValidation:
    """Variable validation rules"""

    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    pattern: Optional[str] = None  # Regex pattern
    allowed_values: List[Any] = field(default_factory=list)
    custom_validator: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "required": self.required,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "pattern": self.pattern,
            "allowed_values": self.allowed_values,
            "custom_validator": self.custom_validator
        }


@dataclass
class Variable:
    """Template variable"""

    id: str
    name: str
    variable_type: VariableType
    scope: VariableScope = VariableScope.TEMPLATE
    default_value: Any = None
    description: str = ""
    validation: VariableValidation = field(default_factory=VariableValidation)
    sensitive: bool = False  # Mask in logs
    computed: bool = False  # Calculated from others
    expression: Optional[str] = None  # For computed variables
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    def validate(self, value: Any) -> tuple:
        """Validate a value against rules"""
        errors = []

        # Required check
        if self.validation.required and value is None:
            errors.append(f"Variable '{self.name}' is required")
            return False, errors

        if value is None:
            return True, []

        # Type validation
        if not self._validate_type(value):
            errors.append(f"Variable '{self.name}' has invalid type")

        # Length validation for strings/lists
        if self.validation.min_length is not None:
            if hasattr(value, '__len__') and len(value) < self.validation.min_length:
                errors.append(f"Variable '{self.name}' is too short")

        if self.validation.max_length is not None:
            if hasattr(value, '__len__') and len(value) > self.validation.max_length:
                errors.append(f"Variable '{self.name}' is too long")

        # Range validation for numbers
        if self.validation.min_value is not None:
            if isinstance(value, (int, float)) and value < self.validation.min_value:
                errors.append(f"Variable '{self.name}' is below minimum")

        if self.validation.max_value is not None:
            if isinstance(value, (int, float)) and value > self.validation.max_value:
                errors.append(f"Variable '{self.name}' is above maximum")

        # Pattern validation
        if self.validation.pattern and isinstance(value, str):
            import re
            if not re.match(self.validation.pattern, value):
                errors.append(f"Variable '{self.name}' doesn't match pattern")

        # Allowed values
        if self.validation.allowed_values and value not in self.validation.allowed_values:
            errors.append(f"Variable '{self.name}' has invalid value")

        return len(errors) == 0, errors

    def _validate_type(self, value: Any) -> bool:
        """Validate value type"""
        if self.variable_type == VariableType.STRING:
            return isinstance(value, str)
        elif self.variable_type == VariableType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        elif self.variable_type == VariableType.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif self.variable_type == VariableType.BOOLEAN:
            return isinstance(value, bool)
        elif self.variable_type == VariableType.LIST:
            return isinstance(value, list)
        elif self.variable_type == VariableType.DICT:
            return isinstance(value, dict)
        elif self.variable_type in (VariableType.IP_ADDRESS, VariableType.CIDR,
                                    VariableType.MAC_ADDRESS, VariableType.HOSTNAME,
                                    VariableType.PATH, VariableType.URL):
            return isinstance(value, str)
        elif self.variable_type in (VariableType.PORT, VariableType.VLAN, VariableType.ASN):
            return isinstance(value, int)
        elif self.variable_type == VariableType.SECRET:
            return isinstance(value, str)
        elif self.variable_type == VariableType.DATETIME:
            return isinstance(value, (str, datetime))
        elif self.variable_type == VariableType.ENUM:
            return value in self.validation.allowed_values if self.validation.allowed_values else True

        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "variable_type": self.variable_type.value,
            "scope": self.scope.value,
            "default_value": self.default_value if not self.sensitive else "***",
            "description": self.description,
            "validation": self.validation.to_dict(),
            "sensitive": self.sensitive,
            "computed": self.computed,
            "expression": self.expression,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags
        }


class VariableManager:
    """Manages template variables"""

    def __init__(self):
        self.variables: Dict[str, Variable] = {}
        self._validators: Dict[str, Callable] = {}
        self._computed_handlers: Dict[str, Callable] = {}
        self._init_builtin_variables()
        self._init_builtin_validators()

    def _init_builtin_variables(self) -> None:
        """Initialize built-in variables"""

        # Network variables
        self.create_variable(
            name="hostname",
            variable_type=VariableType.HOSTNAME,
            scope=VariableScope.GLOBAL,
            description="Device hostname",
            validation=VariableValidation(required=True, max_length=64),
            tags=["network", "device"]
        )

        self.create_variable(
            name="router_id",
            variable_type=VariableType.IP_ADDRESS,
            scope=VariableScope.GLOBAL,
            description="Router ID (IP address format)",
            tags=["network", "routing"]
        )

        self.create_variable(
            name="management_ip",
            variable_type=VariableType.IP_ADDRESS,
            scope=VariableScope.GLOBAL,
            description="Management IP address",
            tags=["network", "management"]
        )

        self.create_variable(
            name="asn",
            variable_type=VariableType.ASN,
            scope=VariableScope.GLOBAL,
            description="Autonomous System Number",
            validation=VariableValidation(min_value=1, max_value=4294967295),
            tags=["bgp", "routing"]
        )

        # OSPF variables
        self.create_variable(
            name="ospf_area",
            variable_type=VariableType.STRING,
            scope=VariableScope.TEMPLATE,
            default_value="0.0.0.0",
            description="OSPF area ID",
            tags=["ospf", "routing"]
        )

        self.create_variable(
            name="ospf_cost",
            variable_type=VariableType.INTEGER,
            scope=VariableScope.TEMPLATE,
            default_value=10,
            description="OSPF interface cost",
            validation=VariableValidation(min_value=1, max_value=65535),
            tags=["ospf", "routing"]
        )

        # BGP variables
        self.create_variable(
            name="bgp_neighbor_ip",
            variable_type=VariableType.IP_ADDRESS,
            scope=VariableScope.TEMPLATE,
            description="BGP neighbor IP address",
            tags=["bgp", "routing"]
        )

        self.create_variable(
            name="bgp_peer_asn",
            variable_type=VariableType.ASN,
            scope=VariableScope.TEMPLATE,
            description="BGP peer AS number",
            tags=["bgp", "routing"]
        )

        # Interface variables
        self.create_variable(
            name="interface_name",
            variable_type=VariableType.STRING,
            scope=VariableScope.TEMPLATE,
            description="Interface name",
            tags=["interface", "network"]
        )

        self.create_variable(
            name="interface_ip",
            variable_type=VariableType.CIDR,
            scope=VariableScope.TEMPLATE,
            description="Interface IP with prefix",
            tags=["interface", "network"]
        )

        self.create_variable(
            name="vlan_id",
            variable_type=VariableType.VLAN,
            scope=VariableScope.TEMPLATE,
            description="VLAN ID",
            validation=VariableValidation(min_value=1, max_value=4094),
            tags=["vlan", "layer2"]
        )

    def _init_builtin_validators(self) -> None:
        """Initialize built-in validators"""

        def validate_ip(value: str) -> bool:
            """Validate IP address"""
            import re
            pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
            if not re.match(pattern, value):
                return False
            octets = value.split('.')
            return all(0 <= int(o) <= 255 for o in octets)

        def validate_cidr(value: str) -> bool:
            """Validate CIDR notation"""
            if '/' not in value:
                return False
            ip, prefix = value.rsplit('/', 1)
            if not validate_ip(ip):
                return False
            try:
                return 0 <= int(prefix) <= 32
            except ValueError:
                return False

        def validate_mac(value: str) -> bool:
            """Validate MAC address"""
            import re
            patterns = [
                r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$',
                r'^([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$',
                r'^([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$'
            ]
            return any(re.match(p, value) for p in patterns)

        def validate_hostname(value: str) -> bool:
            """Validate hostname"""
            import re
            if len(value) > 255:
                return False
            pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
            return bool(re.match(pattern, value))

        self._validators = {
            "ip_address": validate_ip,
            "cidr": validate_cidr,
            "mac_address": validate_mac,
            "hostname": validate_hostname
        }

    def register_validator(
        self,
        name: str,
        validator: Callable
    ) -> None:
        """Register a custom validator"""
        self._validators[name] = validator

    def get_validator(self, name: str) -> Optional[Callable]:
        """Get validator by name"""
        return self._validators.get(name)

    def register_computed_handler(
        self,
        name: str,
        handler: Callable
    ) -> None:
        """Register a computed variable handler"""
        self._computed_handlers[name] = handler

    def create_variable(
        self,
        name: str,
        variable_type: VariableType,
        scope: VariableScope = VariableScope.TEMPLATE,
        default_value: Any = None,
        description: str = "",
        validation: Optional[VariableValidation] = None,
        sensitive: bool = False,
        computed: bool = False,
        expression: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Variable:
        """Create a new variable"""
        variable_id = f"var_{uuid.uuid4().hex[:8]}"

        variable = Variable(
            id=variable_id,
            name=name,
            variable_type=variable_type,
            scope=scope,
            default_value=default_value,
            description=description,
            validation=validation or VariableValidation(),
            sensitive=sensitive,
            computed=computed,
            expression=expression,
            tags=tags or []
        )

        self.variables[variable_id] = variable
        return variable

    def get_variable(self, variable_id: str) -> Optional[Variable]:
        """Get variable by ID"""
        return self.variables.get(variable_id)

    def get_variable_by_name(self, name: str) -> Optional[Variable]:
        """Get variable by name"""
        for variable in self.variables.values():
            if variable.name == name:
                return variable
        return None

    def update_variable(
        self,
        variable_id: str,
        **kwargs
    ) -> Optional[Variable]:
        """Update variable properties"""
        variable = self.variables.get(variable_id)
        if not variable:
            return None

        for key, value in kwargs.items():
            if hasattr(variable, key):
                setattr(variable, key, value)

        return variable

    def delete_variable(self, variable_id: str) -> bool:
        """Delete a variable"""
        if variable_id in self.variables:
            del self.variables[variable_id]
            return True
        return False

    def validate_value(
        self,
        variable_id: str,
        value: Any
    ) -> tuple:
        """Validate a value against variable rules"""
        variable = self.variables.get(variable_id)
        if not variable:
            return False, ["Variable not found"]

        return variable.validate(value)

    def get_default_value(
        self,
        variable_id: str
    ) -> Any:
        """Get default value for variable"""
        variable = self.variables.get(variable_id)
        if variable:
            return variable.default_value
        return None

    def compute_value(
        self,
        variable_id: str,
        context: Dict[str, Any]
    ) -> Any:
        """Compute value for computed variable"""
        variable = self.variables.get(variable_id)
        if not variable or not variable.computed:
            return None

        if variable.expression:
            # Simple expression evaluation
            try:
                return eval(variable.expression, {"__builtins__": {}}, context)
            except Exception:
                return None

        return None

    def get_variables(
        self,
        variable_type: Optional[VariableType] = None,
        scope: Optional[VariableScope] = None,
        tag: Optional[str] = None
    ) -> List[Variable]:
        """Get variables with filtering"""
        variables = list(self.variables.values())

        if variable_type:
            variables = [v for v in variables if v.variable_type == variable_type]
        if scope:
            variables = [v for v in variables if v.scope == scope]
        if tag:
            variables = [v for v in variables if tag in v.tags]

        return variables

    def get_statistics(self) -> dict:
        """Get variable statistics"""
        by_type = {}
        by_scope = {}
        computed_count = 0
        sensitive_count = 0

        for variable in self.variables.values():
            by_type[variable.variable_type.value] = by_type.get(variable.variable_type.value, 0) + 1
            by_scope[variable.scope.value] = by_scope.get(variable.scope.value, 0) + 1
            if variable.computed:
                computed_count += 1
            if variable.sensitive:
                sensitive_count += 1

        return {
            "total_variables": len(self.variables),
            "computed_variables": computed_count,
            "sensitive_variables": sensitive_count,
            "by_type": by_type,
            "by_scope": by_scope,
            "registered_validators": len(self._validators),
            "computed_handlers": len(self._computed_handlers)
        }


# Global variable manager instance
_variable_manager: Optional[VariableManager] = None


def get_variable_manager() -> VariableManager:
    """Get or create the global variable manager"""
    global _variable_manager
    if _variable_manager is None:
        _variable_manager = VariableManager()
    return _variable_manager
