"""
NETCONF/RESTCONF Module for ASI Agents

Provides NETCONF (RFC 6241) and RESTCONF (RFC 8040) server capabilities
for agents, allowing external automation tools to configure and manage
network devices using standard protocols.

Features:
- NETCONF server with YANG model support
- RESTCONF API endpoint
- Configuration datastore (running, candidate, startup)
- Transaction support with commit/rollback
- Event notifications

Usage:
    from agentic.netconf import (
        NETCONFServer, RESTCONFServer, ConfigDatastore,
        start_netconf_server, start_restconf_server
    )

    # Start NETCONF server for an agent
    netconf = await start_netconf_server(agent_name="router-1", port=830)

    # Start RESTCONF server
    restconf = await start_restconf_server(agent_name="router-1", port=8443)
"""

from .netconf_server import (
    NETCONFServer,
    NETCONFConfig,
    NETCONFSession,
    ConfigDatastore,
    DatastoreType,
    OperationType,
    get_netconf_server,
    start_netconf_server,
    stop_netconf_server,
    get_netconf_statistics,
    list_netconf_sessions,
)

from .restconf_server import (
    RESTCONFServer,
    RESTCONFConfig,
    get_restconf_server,
    start_restconf_server,
    stop_restconf_server,
    get_restconf_statistics,
)

__all__ = [
    # NETCONF
    "NETCONFServer",
    "NETCONFConfig",
    "NETCONFSession",
    "ConfigDatastore",
    "DatastoreType",
    "OperationType",
    "get_netconf_server",
    "start_netconf_server",
    "stop_netconf_server",
    "get_netconf_statistics",
    "list_netconf_sessions",
    # RESTCONF
    "RESTCONFServer",
    "RESTCONFConfig",
    "get_restconf_server",
    "start_restconf_server",
    "stop_restconf_server",
    "get_restconf_statistics",
]
