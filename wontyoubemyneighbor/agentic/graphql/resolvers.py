"""
GraphQL Resolvers - Data fetching for GraphQL queries

Provides:
- Query resolvers for all types
- Mutation resolvers for modifications
- Field-level resolvers
- Data transformation
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger("GraphQLResolvers")


@dataclass
class ResolverContext:
    """
    Context passed to resolvers

    Attributes:
        user_id: Authenticated user ID
        tenant_id: Current tenant context
        session_id: Session identifier
        request_time: Request timestamp
    """
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    request_time: datetime = None

    def __post_init__(self):
        if self.request_time is None:
            self.request_time = datetime.now()


class QueryResolvers:
    """
    Resolvers for GraphQL queries
    """

    def __init__(self):
        """Initialize query resolvers"""
        self._resolvers: Dict[str, Callable] = {}
        self._register_resolvers()

    def _register_resolvers(self):
        """Register all query resolvers"""
        self._resolvers["agents"] = self._resolve_agents
        self._resolvers["agent"] = self._resolve_agent
        self._resolvers["networks"] = self._resolve_networks
        self._resolvers["network"] = self._resolve_network
        self._resolvers["tenants"] = self._resolve_tenants
        self._resolvers["tenant"] = self._resolve_tenant
        self._resolvers["users"] = self._resolve_users
        self._resolvers["user"] = self._resolve_user
        self._resolvers["roles"] = self._resolve_roles
        self._resolvers["role"] = self._resolve_role
        self._resolvers["trafficFlows"] = self._resolve_traffic_flows
        self._resolvers["heatmap"] = self._resolve_heatmap
        self._resolvers["statistics"] = self._resolve_statistics

    def resolve(
        self,
        field_name: str,
        args: Dict[str, Any],
        context: ResolverContext
    ) -> Any:
        """
        Resolve a query field

        Args:
            field_name: Name of the field to resolve
            args: Query arguments
            context: Resolver context

        Returns:
            Resolved data
        """
        resolver = self._resolvers.get(field_name)
        if not resolver:
            logger.warning(f"No resolver for field: {field_name}")
            return None

        try:
            return resolver(args, context)
        except Exception as e:
            logger.error(f"Resolver error for {field_name}: {e}")
            return None

    def _resolve_agents(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve agents query"""
        # In production, this would query actual agent data
        # For now, return mock data structure
        tenant_filter = args.get("tenantId")
        status_filter = args.get("status")

        agents = [
            {
                "id": "agent-001",
                "name": "Core Router",
                "routerId": "1.1.1.1",
                "status": "RUNNING",
                "hostname": "core-rtr-01",
                "tenantId": "tenant-default",
                "createdAt": datetime.now().isoformat(),
                "interfaces": [],
                "protocols": []
            },
            {
                "id": "agent-002",
                "name": "Edge Router",
                "routerId": "2.2.2.2",
                "status": "RUNNING",
                "hostname": "edge-rtr-01",
                "tenantId": "tenant-default",
                "createdAt": datetime.now().isoformat(),
                "interfaces": [],
                "protocols": []
            }
        ]

        # Apply filters
        if tenant_filter:
            agents = [a for a in agents if a.get("tenantId") == tenant_filter]
        if status_filter:
            agents = [a for a in agents if a.get("status") == status_filter]

        return agents

    def _resolve_agent(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve single agent query"""
        agent_id = args.get("id")
        agents = self._resolve_agents({}, context)
        for agent in agents:
            if agent.get("id") == agent_id:
                return agent
        return None

    def _resolve_networks(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve networks query"""
        tenant_filter = args.get("tenantId")

        networks = [
            {
                "id": "network-001",
                "name": "Production Network",
                "tenantId": "tenant-default",
                "status": "active",
                "agents": [],
                "links": []
            }
        ]

        if tenant_filter:
            networks = [n for n in networks if n.get("tenantId") == tenant_filter]

        return networks

    def _resolve_network(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve single network query"""
        network_id = args.get("id")
        networks = self._resolve_networks({}, context)
        for network in networks:
            if network.get("id") == network_id:
                return network
        return None

    def _resolve_tenants(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve tenants query"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()

            tier_filter = args.get("tier")
            tenants = manager.get_all_tenants()

            result = []
            for t in tenants:
                if tier_filter and t.tier.value.upper() != tier_filter:
                    continue
                result.append({
                    "id": t.tenant_id,
                    "name": t.name,
                    "tier": t.tier.value.upper(),
                    "status": t.status.value,
                    "agentCount": t.agent_count,
                    "networkCount": t.network_count,
                    "users": []
                })

            return result
        except ImportError:
            return []

    def _resolve_tenant(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve single tenant query"""
        tenant_id = args.get("id")
        tenants = self._resolve_tenants({}, context)
        for tenant in tenants:
            if tenant.get("id") == tenant_id:
                return tenant
        return None

    def _resolve_users(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve users query"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()

            tenant_filter = args.get("tenantId")
            status_filter = args.get("status")

            users = manager.get_all_users()

            result = []
            for u in users:
                if tenant_filter and u.tenant_id != tenant_filter:
                    continue
                if status_filter and u.status.value.upper() != status_filter:
                    continue
                result.append({
                    "id": u.user_id,
                    "username": u.username,
                    "email": u.email,
                    "displayName": u.display_name,
                    "status": u.status.value.upper(),
                    "roles": list(u.role_ids),
                    "tenantId": u.tenant_id
                })

            return result
        except ImportError:
            return []

    def _resolve_user(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve single user query"""
        user_id = args.get("id")
        users = self._resolve_users({}, context)
        for user in users:
            if user.get("id") == user_id:
                return user
        return None

    def _resolve_roles(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve roles query"""
        try:
            from agentic.rbac import get_role_manager
            manager = get_role_manager()

            roles = manager.get_all_roles()

            result = []
            for r in roles:
                result.append({
                    "id": r.role_id,
                    "name": r.name,
                    "description": r.description,
                    "permissions": list(r.permission_ids),
                    "isSystem": r.is_system
                })

            return result
        except ImportError:
            return []

    def _resolve_role(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve single role query"""
        role_id = args.get("id")
        roles = self._resolve_roles({}, context)
        for role in roles:
            if role.get("id") == role_id:
                return role
        return None

    def _resolve_traffic_flows(self, args: Dict[str, Any], context: ResolverContext) -> List[Dict]:
        """Resolve traffic flows query"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()

            status_filter = args.get("status")
            flows = generator.get_all_flows()

            result = []
            for f in flows:
                if status_filter and f.status.value.upper() != status_filter:
                    continue
                result.append({
                    "id": f.flow_id,
                    "sourceAgent": f.source_agent,
                    "destAgent": f.dest_agent,
                    "status": f.status.value.upper(),
                    "bytesSent": f.bytes_sent,
                    "avgRateMbps": f.avg_rate_mbps
                })

            return result
        except ImportError:
            return []

    def _resolve_heatmap(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Resolve heatmap query"""
        try:
            from agentic.heatmap import get_traffic_collector, HeatmapRenderer
            collector = get_traffic_collector()
            renderer = HeatmapRenderer()

            heatmap_type = args.get("type", "link_utilization")

            links = collector.get_all_links()
            link_data = [
                {
                    "link_id": l.link_id,
                    "source": l.source_node,
                    "dest": l.dest_node,
                    "utilization": l.current_utilization
                }
                for l in links
            ]

            heatmap = renderer.render_link_heatmap(link_data)

            return {
                "id": heatmap.heatmap_id,
                "type": heatmap.heatmap_type.value,
                "title": heatmap.title,
                "width": heatmap.width,
                "height": heatmap.height,
                "cells": [
                    {
                        "x": c.x,
                        "y": c.y,
                        "value": c.value,
                        "color": c.color,
                        "label": c.label
                    }
                    for c in heatmap.cells
                ]
            }
        except ImportError:
            return None

    def _resolve_statistics(self, args: Dict[str, Any], context: ResolverContext) -> Dict:
        """Resolve statistics query"""
        stats = {
            "totalAgents": 0,
            "totalNetworks": 0,
            "totalTenants": 0,
            "totalUsers": 0,
            "activeFlows": 0
        }

        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            stats["totalTenants"] = len(manager.get_all_tenants())
        except ImportError:
            pass

        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            stats["totalUsers"] = len(manager.get_all_users())
        except ImportError:
            pass

        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            stats["activeFlows"] = len(generator.get_active_flows())
        except ImportError:
            pass

        return stats


class MutationResolvers:
    """
    Resolvers for GraphQL mutations
    """

    def __init__(self):
        """Initialize mutation resolvers"""
        self._resolvers: Dict[str, Callable] = {}
        self._register_resolvers()

    def _register_resolvers(self):
        """Register all mutation resolvers"""
        self._resolvers["createAgent"] = self._resolve_create_agent
        self._resolvers["deleteAgent"] = self._resolve_delete_agent
        self._resolvers["createNetwork"] = self._resolve_create_network
        self._resolvers["deleteNetwork"] = self._resolve_delete_network
        self._resolvers["startFlow"] = self._resolve_start_flow
        self._resolvers["stopFlow"] = self._resolve_stop_flow
        self._resolvers["createUser"] = self._resolve_create_user
        self._resolvers["activateUser"] = self._resolve_activate_user
        self._resolvers["suspendUser"] = self._resolve_suspend_user

    def resolve(
        self,
        field_name: str,
        args: Dict[str, Any],
        context: ResolverContext
    ) -> Any:
        """
        Resolve a mutation field

        Args:
            field_name: Name of the mutation
            args: Mutation arguments
            context: Resolver context

        Returns:
            Mutation result
        """
        resolver = self._resolvers.get(field_name)
        if not resolver:
            logger.warning(f"No resolver for mutation: {field_name}")
            return None

        try:
            return resolver(args, context)
        except Exception as e:
            logger.error(f"Mutation error for {field_name}: {e}")
            return None

    def _resolve_create_agent(self, args: Dict[str, Any], context: ResolverContext) -> Dict:
        """Create agent mutation"""
        input_data = args.get("input", {})
        return {
            "id": f"agent-{datetime.now().timestamp()}",
            "name": input_data.get("name", "New Agent"),
            "routerId": input_data.get("routerId", "0.0.0.0"),
            "status": "STARTING",
            "hostname": input_data.get("hostname", ""),
            "tenantId": input_data.get("tenantId") or context.tenant_id,
            "createdAt": datetime.now().isoformat()
        }

    def _resolve_delete_agent(self, args: Dict[str, Any], context: ResolverContext) -> bool:
        """Delete agent mutation"""
        agent_id = args.get("id")
        logger.info(f"Deleting agent: {agent_id}")
        return True

    def _resolve_create_network(self, args: Dict[str, Any], context: ResolverContext) -> Dict:
        """Create network mutation"""
        input_data = args.get("input", {})
        return {
            "id": f"network-{datetime.now().timestamp()}",
            "name": input_data.get("name", "New Network"),
            "tenantId": input_data.get("tenantId") or context.tenant_id,
            "status": "creating",
            "agents": [],
            "links": []
        }

    def _resolve_delete_network(self, args: Dict[str, Any], context: ResolverContext) -> bool:
        """Delete network mutation"""
        network_id = args.get("id")
        logger.info(f"Deleting network: {network_id}")
        return True

    def _resolve_start_flow(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Start traffic flow mutation"""
        try:
            from agentic.traffic import get_traffic_generator
            import asyncio
            generator = get_traffic_generator()
            flow_id = args.get("flowId")

            # Note: In production, this would be async
            flow = generator.get_flow(flow_id)
            if flow:
                return {
                    "id": flow.flow_id,
                    "sourceAgent": flow.source_agent,
                    "destAgent": flow.dest_agent,
                    "status": "RUNNING",
                    "bytesSent": flow.bytes_sent,
                    "avgRateMbps": flow.avg_rate_mbps
                }
            return None
        except ImportError:
            return None

    def _resolve_stop_flow(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Stop traffic flow mutation"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            flow_id = args.get("flowId")

            flow = generator.get_flow(flow_id)
            if flow:
                return {
                    "id": flow.flow_id,
                    "sourceAgent": flow.source_agent,
                    "destAgent": flow.dest_agent,
                    "status": "STOPPED",
                    "bytesSent": flow.bytes_sent,
                    "avgRateMbps": flow.avg_rate_mbps
                }
            return None
        except ImportError:
            return None

    def _resolve_create_user(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Create user mutation"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()

            user = manager.create_user(
                username=args.get("username"),
                email=args.get("email"),
                password=args.get("password"),
                auto_activate=True
            )

            return {
                "id": user.user_id,
                "username": user.username,
                "email": user.email,
                "displayName": user.display_name,
                "status": user.status.value.upper(),
                "roles": list(user.role_ids),
                "tenantId": user.tenant_id
            }
        except ImportError:
            return None

    def _resolve_activate_user(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Activate user mutation"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()

            user_id = args.get("id")
            manager.activate_user(user_id)
            user = manager.get_user(user_id)

            if user:
                return {
                    "id": user.user_id,
                    "username": user.username,
                    "status": user.status.value.upper()
                }
            return None
        except ImportError:
            return None

    def _resolve_suspend_user(self, args: Dict[str, Any], context: ResolverContext) -> Optional[Dict]:
        """Suspend user mutation"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()

            user_id = args.get("id")
            manager.suspend_user(user_id)
            user = manager.get_user(user_id)

            if user:
                return {
                    "id": user.user_id,
                    "username": user.username,
                    "status": user.status.value.upper()
                }
            return None
        except ImportError:
            return None


# Global resolvers instance
_query_resolvers: Optional[QueryResolvers] = None
_mutation_resolvers: Optional[MutationResolvers] = None


def get_resolvers() -> tuple:
    """Get or create the global resolvers"""
    global _query_resolvers, _mutation_resolvers
    if _query_resolvers is None:
        _query_resolvers = QueryResolvers()
    if _mutation_resolvers is None:
        _mutation_resolvers = MutationResolvers()
    return _query_resolvers, _mutation_resolvers
