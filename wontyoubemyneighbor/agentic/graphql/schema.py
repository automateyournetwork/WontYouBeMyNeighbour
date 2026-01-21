"""
GraphQL Schema - Type definitions for the ADN Platform

Provides:
- Type definitions for all entities
- Query type definitions
- Mutation type definitions
- Input type definitions
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Callable

logger = logging.getLogger("GraphQLSchema")


class GraphQLType(Enum):
    """GraphQL scalar and object types"""
    STRING = "String"
    INT = "Int"
    FLOAT = "Float"
    BOOLEAN = "Boolean"
    ID = "ID"
    OBJECT = "Object"
    LIST = "List"
    NON_NULL = "NonNull"
    ENUM = "Enum"
    INPUT = "Input"


@dataclass
class FieldDefinition:
    """
    Definition of a GraphQL field

    Attributes:
        name: Field name
        field_type: GraphQL type
        description: Field description
        args: Field arguments
        resolver: Optional custom resolver
        is_list: Whether this is a list type
        is_required: Whether this field is required
    """
    name: str
    field_type: str
    description: str = ""
    args: Dict[str, str] = field(default_factory=dict)
    resolver: Optional[Callable] = None
    is_list: bool = False
    is_required: bool = False

    def to_sdl(self) -> str:
        """Convert to SDL (Schema Definition Language)"""
        type_str = self.field_type
        if self.is_list:
            type_str = f"[{type_str}]"
        if self.is_required:
            type_str = f"{type_str}!"

        args_str = ""
        if self.args:
            args_parts = [f"{k}: {v}" for k, v in self.args.items()]
            args_str = f"({', '.join(args_parts)})"

        desc = f'  "{self.description}"\n' if self.description else ""
        return f'{desc}  {self.name}{args_str}: {type_str}'


@dataclass
class TypeDefinition:
    """
    Definition of a GraphQL type

    Attributes:
        name: Type name
        description: Type description
        fields: Type fields
        is_input: Whether this is an input type
    """
    name: str
    description: str = ""
    fields: List[FieldDefinition] = field(default_factory=list)
    is_input: bool = False
    implements: List[str] = field(default_factory=list)

    def add_field(
        self,
        name: str,
        field_type: str,
        description: str = "",
        is_list: bool = False,
        is_required: bool = False,
        args: Optional[Dict[str, str]] = None
    ):
        """Add a field to this type"""
        self.fields.append(FieldDefinition(
            name=name,
            field_type=field_type,
            description=description,
            is_list=is_list,
            is_required=is_required,
            args=args or {}
        ))

    def to_sdl(self) -> str:
        """Convert to SDL"""
        keyword = "input" if self.is_input else "type"
        implements = f" implements {' & '.join(self.implements)}" if self.implements else ""
        desc = f'"""{self.description}"""\n' if self.description else ""
        fields_sdl = "\n".join(f.to_sdl() for f in self.fields)
        return f'{desc}{keyword} {self.name}{implements} {{\n{fields_sdl}\n}}'


@dataclass
class EnumDefinition:
    """
    Definition of a GraphQL enum

    Attributes:
        name: Enum name
        values: Enum values
        description: Enum description
    """
    name: str
    values: List[str]
    description: str = ""

    def to_sdl(self) -> str:
        """Convert to SDL"""
        desc = f'"""{self.description}"""\n' if self.description else ""
        values_sdl = "\n  ".join(self.values)
        return f'{desc}enum {self.name} {{\n  {values_sdl}\n}}'


class GraphQLSchema:
    """
    GraphQL schema definition for ADN Platform
    """

    def __init__(self):
        """Initialize schema"""
        self._types: Dict[str, TypeDefinition] = {}
        self._enums: Dict[str, EnumDefinition] = {}
        self._query_type: Optional[TypeDefinition] = None
        self._mutation_type: Optional[TypeDefinition] = None

        # Build schema
        self._define_enums()
        self._define_types()
        self._define_queries()
        self._define_mutations()

    def _define_enums(self):
        """Define GraphQL enums"""
        # Protocol Status
        self._enums["ProtocolStatus"] = EnumDefinition(
            name="ProtocolStatus",
            values=["ACTIVE", "INACTIVE", "ERROR", "CONVERGING"],
            description="Status of a protocol instance"
        )

        # Agent Status
        self._enums["AgentStatus"] = EnumDefinition(
            name="AgentStatus",
            values=["RUNNING", "STOPPED", "ERROR", "STARTING", "STOPPING"],
            description="Status of a network agent"
        )

        # Tenant Tier
        self._enums["TenantTier"] = EnumDefinition(
            name="TenantTier",
            values=["FREE", "BASIC", "STANDARD", "PREMIUM", "ENTERPRISE"],
            description="Service tier for tenants"
        )

        # User Status
        self._enums["UserStatus"] = EnumDefinition(
            name="UserStatus",
            values=["PENDING", "ACTIVE", "SUSPENDED", "LOCKED", "DISABLED"],
            description="User account status"
        )

        # Flow Status
        self._enums["FlowStatus"] = EnumDefinition(
            name="FlowStatus",
            values=["PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"],
            description="Traffic flow status"
        )

    def _define_types(self):
        """Define GraphQL object types"""
        # Agent type
        agent = TypeDefinition(
            name="Agent",
            description="A network agent running routing protocols"
        )
        agent.add_field("id", "ID", "Unique identifier", is_required=True)
        agent.add_field("name", "String", "Agent name", is_required=True)
        agent.add_field("routerId", "String", "Router ID")
        agent.add_field("status", "AgentStatus", "Current status")
        agent.add_field("hostname", "String", "Hostname")
        agent.add_field("interfaces", "Interface", "Network interfaces", is_list=True)
        agent.add_field("protocols", "Protocol", "Running protocols", is_list=True)
        agent.add_field("tenantId", "ID", "Owning tenant ID")
        agent.add_field("createdAt", "String", "Creation timestamp")
        self._types["Agent"] = agent

        # Interface type
        iface = TypeDefinition(
            name="Interface",
            description="A network interface"
        )
        iface.add_field("name", "String", "Interface name", is_required=True)
        iface.add_field("ipAddress", "String", "IP address")
        iface.add_field("netmask", "String", "Network mask")
        iface.add_field("status", "String", "Interface status")
        iface.add_field("mtu", "Int", "Maximum transmission unit")
        self._types["Interface"] = iface

        # Protocol type
        protocol = TypeDefinition(
            name="Protocol",
            description="A routing protocol instance"
        )
        protocol.add_field("name", "String", "Protocol name", is_required=True)
        protocol.add_field("status", "ProtocolStatus", "Protocol status")
        protocol.add_field("neighbors", "Neighbor", "Protocol neighbors", is_list=True)
        protocol.add_field("routes", "Route", "Learned routes", is_list=True)
        protocol.add_field("config", "String", "Protocol configuration")
        self._types["Protocol"] = protocol

        # Neighbor type
        neighbor = TypeDefinition(
            name="Neighbor",
            description="A protocol neighbor/peer"
        )
        neighbor.add_field("id", "ID", "Neighbor ID", is_required=True)
        neighbor.add_field("address", "String", "Neighbor address")
        neighbor.add_field("state", "String", "Neighbor state")
        neighbor.add_field("uptime", "Int", "Uptime in seconds")
        neighbor.add_field("protocol", "String", "Protocol type")
        self._types["Neighbor"] = neighbor

        # Route type
        route = TypeDefinition(
            name="Route",
            description="A routing table entry"
        )
        route.add_field("prefix", "String", "Network prefix", is_required=True)
        route.add_field("nextHop", "String", "Next hop address")
        route.add_field("metric", "Int", "Route metric")
        route.add_field("protocol", "String", "Source protocol")
        route.add_field("age", "Int", "Route age in seconds")
        self._types["Route"] = route

        # Network type
        network = TypeDefinition(
            name="Network",
            description="A network deployment"
        )
        network.add_field("id", "ID", "Network ID", is_required=True)
        network.add_field("name", "String", "Network name", is_required=True)
        network.add_field("agents", "Agent", "Network agents", is_list=True)
        network.add_field("links", "Link", "Network links", is_list=True)
        network.add_field("tenantId", "ID", "Owning tenant ID")
        network.add_field("status", "String", "Network status")
        self._types["Network"] = network

        # Link type
        link = TypeDefinition(
            name="Link",
            description="A network link between agents"
        )
        link.add_field("id", "ID", "Link ID", is_required=True)
        link.add_field("sourceAgent", "String", "Source agent")
        link.add_field("destAgent", "String", "Destination agent")
        link.add_field("sourceInterface", "String", "Source interface")
        link.add_field("destInterface", "String", "Destination interface")
        link.add_field("utilization", "Float", "Current utilization %")
        link.add_field("capacity", "Int", "Capacity in bps")
        self._types["Link"] = link

        # Tenant type
        tenant = TypeDefinition(
            name="Tenant",
            description="A tenant in the multi-tenant system"
        )
        tenant.add_field("id", "ID", "Tenant ID", is_required=True)
        tenant.add_field("name", "String", "Tenant name", is_required=True)
        tenant.add_field("tier", "TenantTier", "Service tier")
        tenant.add_field("status", "String", "Tenant status")
        tenant.add_field("agentCount", "Int", "Number of agents")
        tenant.add_field("networkCount", "Int", "Number of networks")
        tenant.add_field("users", "User", "Tenant users", is_list=True)
        self._types["Tenant"] = tenant

        # User type
        user = TypeDefinition(
            name="User",
            description="A user account"
        )
        user.add_field("id", "ID", "User ID", is_required=True)
        user.add_field("username", "String", "Username", is_required=True)
        user.add_field("email", "String", "Email address")
        user.add_field("displayName", "String", "Display name")
        user.add_field("status", "UserStatus", "Account status")
        user.add_field("roles", "Role", "Assigned roles", is_list=True)
        user.add_field("tenantId", "ID", "Associated tenant")
        self._types["User"] = user

        # Role type
        role = TypeDefinition(
            name="Role",
            description="An RBAC role"
        )
        role.add_field("id", "ID", "Role ID", is_required=True)
        role.add_field("name", "String", "Role name", is_required=True)
        role.add_field("description", "String", "Role description")
        role.add_field("permissions", "Permission", "Role permissions", is_list=True)
        role.add_field("isSystem", "Boolean", "Is system role")
        self._types["Role"] = role

        # Permission type
        permission = TypeDefinition(
            name="Permission",
            description="An RBAC permission"
        )
        permission.add_field("id", "ID", "Permission ID", is_required=True)
        permission.add_field("name", "String", "Permission name")
        permission.add_field("resource", "String", "Resource type")
        permission.add_field("action", "String", "Allowed action")
        self._types["Permission"] = permission

        # TrafficFlow type
        flow = TypeDefinition(
            name="TrafficFlow",
            description="A traffic flow"
        )
        flow.add_field("id", "ID", "Flow ID", is_required=True)
        flow.add_field("sourceAgent", "String", "Source agent")
        flow.add_field("destAgent", "String", "Destination agent")
        flow.add_field("status", "FlowStatus", "Flow status")
        flow.add_field("bytesSent", "Int", "Bytes sent")
        flow.add_field("avgRateMbps", "Float", "Average rate in Mbps")
        self._types["TrafficFlow"] = flow

        # Heatmap type
        heatmap = TypeDefinition(
            name="Heatmap",
            description="A traffic heatmap"
        )
        heatmap.add_field("id", "ID", "Heatmap ID", is_required=True)
        heatmap.add_field("type", "String", "Heatmap type")
        heatmap.add_field("title", "String", "Heatmap title")
        heatmap.add_field("width", "Int", "Grid width")
        heatmap.add_field("height", "Int", "Grid height")
        heatmap.add_field("cells", "HeatmapCell", "Heatmap cells", is_list=True)
        self._types["Heatmap"] = heatmap

        # HeatmapCell type
        cell = TypeDefinition(
            name="HeatmapCell",
            description="A heatmap cell"
        )
        cell.add_field("x", "Int", "X coordinate")
        cell.add_field("y", "Int", "Y coordinate")
        cell.add_field("value", "Float", "Cell value")
        cell.add_field("color", "String", "Cell color")
        cell.add_field("label", "String", "Cell label")
        self._types["HeatmapCell"] = cell

        # Statistics type
        stats = TypeDefinition(
            name="Statistics",
            description="System statistics"
        )
        stats.add_field("totalAgents", "Int", "Total agents")
        stats.add_field("totalNetworks", "Int", "Total networks")
        stats.add_field("totalTenants", "Int", "Total tenants")
        stats.add_field("totalUsers", "Int", "Total users")
        stats.add_field("activeFlows", "Int", "Active traffic flows")
        self._types["Statistics"] = stats

        # Input types for mutations
        agent_input = TypeDefinition(
            name="AgentInput",
            description="Input for creating an agent",
            is_input=True
        )
        agent_input.add_field("name", "String", is_required=True)
        agent_input.add_field("routerId", "String", is_required=True)
        agent_input.add_field("hostname", "String")
        agent_input.add_field("tenantId", "ID")
        self._types["AgentInput"] = agent_input

        network_input = TypeDefinition(
            name="NetworkInput",
            description="Input for creating a network",
            is_input=True
        )
        network_input.add_field("name", "String", is_required=True)
        network_input.add_field("tenantId", "ID")
        self._types["NetworkInput"] = network_input

    def _define_queries(self):
        """Define Query type"""
        query = TypeDefinition(
            name="Query",
            description="Root query type"
        )

        # Agent queries
        query.add_field("agents", "Agent", "Get all agents", is_list=True,
                       args={"tenantId": "ID", "status": "AgentStatus"})
        query.add_field("agent", "Agent", "Get agent by ID",
                       args={"id": "ID!"})

        # Network queries
        query.add_field("networks", "Network", "Get all networks", is_list=True,
                       args={"tenantId": "ID"})
        query.add_field("network", "Network", "Get network by ID",
                       args={"id": "ID!"})

        # Tenant queries
        query.add_field("tenants", "Tenant", "Get all tenants", is_list=True,
                       args={"tier": "TenantTier"})
        query.add_field("tenant", "Tenant", "Get tenant by ID",
                       args={"id": "ID!"})

        # User queries
        query.add_field("users", "User", "Get all users", is_list=True,
                       args={"tenantId": "ID", "status": "UserStatus"})
        query.add_field("user", "User", "Get user by ID",
                       args={"id": "ID!"})

        # Role queries
        query.add_field("roles", "Role", "Get all roles", is_list=True)
        query.add_field("role", "Role", "Get role by ID",
                       args={"id": "ID!"})

        # Traffic queries
        query.add_field("trafficFlows", "TrafficFlow", "Get traffic flows", is_list=True,
                       args={"status": "FlowStatus"})
        query.add_field("heatmap", "Heatmap", "Get traffic heatmap",
                       args={"type": "String"})

        # Statistics
        query.add_field("statistics", "Statistics", "Get system statistics")

        self._query_type = query

    def _define_mutations(self):
        """Define Mutation type"""
        mutation = TypeDefinition(
            name="Mutation",
            description="Root mutation type"
        )

        # Agent mutations
        mutation.add_field("createAgent", "Agent", "Create a new agent",
                          args={"input": "AgentInput!"})
        mutation.add_field("deleteAgent", "Boolean", "Delete an agent",
                          args={"id": "ID!"})

        # Network mutations
        mutation.add_field("createNetwork", "Network", "Create a new network",
                          args={"input": "NetworkInput!"})
        mutation.add_field("deleteNetwork", "Boolean", "Delete a network",
                          args={"id": "ID!"})

        # Traffic mutations
        mutation.add_field("startFlow", "TrafficFlow", "Start a traffic flow",
                          args={"flowId": "ID!"})
        mutation.add_field("stopFlow", "TrafficFlow", "Stop a traffic flow",
                          args={"flowId": "ID!"})

        # User mutations
        mutation.add_field("createUser", "User", "Create a user",
                          args={"username": "String!", "email": "String!", "password": "String!"})
        mutation.add_field("activateUser", "User", "Activate a user",
                          args={"id": "ID!"})
        mutation.add_field("suspendUser", "User", "Suspend a user",
                          args={"id": "ID!"})

        self._mutation_type = mutation

    def get_type(self, name: str) -> Optional[TypeDefinition]:
        """Get a type by name"""
        return self._types.get(name)

    def get_all_types(self) -> List[TypeDefinition]:
        """Get all type definitions"""
        return list(self._types.values())

    def get_all_enums(self) -> List[EnumDefinition]:
        """Get all enum definitions"""
        return list(self._enums.values())

    def get_query_type(self) -> Optional[TypeDefinition]:
        """Get the Query type"""
        return self._query_type

    def get_mutation_type(self) -> Optional[TypeDefinition]:
        """Get the Mutation type"""
        return self._mutation_type

    def to_sdl(self) -> str:
        """Generate full schema as SDL"""
        parts = []

        # Enums
        for enum in self._enums.values():
            parts.append(enum.to_sdl())

        # Types
        for type_def in self._types.values():
            parts.append(type_def.to_sdl())

        # Query type
        if self._query_type:
            parts.append(self._query_type.to_sdl())

        # Mutation type
        if self._mutation_type:
            parts.append(self._mutation_type.to_sdl())

        return "\n\n".join(parts)

    def get_statistics(self) -> Dict[str, Any]:
        """Get schema statistics"""
        return {
            "type_count": len(self._types),
            "enum_count": len(self._enums),
            "query_fields": len(self._query_type.fields) if self._query_type else 0,
            "mutation_fields": len(self._mutation_type.fields) if self._mutation_type else 0
        }


# Global schema instance
_global_schema: Optional[GraphQLSchema] = None


def get_schema() -> GraphQLSchema:
    """Get or create the global schema"""
    global _global_schema
    if _global_schema is None:
        _global_schema = GraphQLSchema()
    return _global_schema


def create_schema() -> GraphQLSchema:
    """Create a new schema instance"""
    return GraphQLSchema()
