"""
Web UI Server for Won't You Be My Neighbor

FastAPI-based web dashboard providing:
- Chat interface for RubberBand agentic assistant
- Real-time protocol status (OSPF/BGP neighbors, routes)
- Log streaming via WebSocket
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Import wizard router
try:
    from .wizard_api import router as wizard_router
    WIZARD_AVAILABLE = True
except ImportError:
    WIZARD_AVAILABLE = False
    wizard_router = None


# Log buffer for streaming to web clients
class LogBuffer:
    """Thread-safe circular buffer for log messages"""

    def __init__(self, maxlen: int = 500):
        self._buffer = deque(maxlen=maxlen)
        self._websockets: List[WebSocket] = []

    def add(self, record: logging.LogRecord):
        """Add a log record to buffer and broadcast to websockets"""
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        self._buffer.append(entry)
        # Schedule broadcast to websockets (copy list to avoid modification during iteration)
        for ws in list(self._websockets):
            try:
                # Check if websocket is still open before sending
                if ws.client_state.name == "CONNECTED":
                    asyncio.create_task(self._safe_send(ws, entry))
            except Exception:
                pass

    async def _safe_send(self, ws: WebSocket, entry: dict):
        """Safely send to websocket, removing on failure"""
        try:
            await ws.send_json({"type": "log", "data": entry})
        except Exception:
            # Remove failed websocket
            if ws in self._websockets:
                self._websockets.remove(ws)

    def get_recent(self, count: int = 100) -> List[Dict]:
        """Get recent log entries"""
        return list(self._buffer)[-count:]

    def register_websocket(self, ws: WebSocket):
        """Register a websocket for log streaming"""
        self._websockets.append(ws)

    def unregister_websocket(self, ws: WebSocket):
        """Unregister a websocket"""
        if ws in self._websockets:
            self._websockets.remove(ws)


class WebUILogHandler(logging.Handler):
    """Logging handler that sends logs to the web UI"""

    def __init__(self, buffer: LogBuffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord):
        try:
            self.buffer.add(record)
        except Exception:
            pass


# Pydantic models
class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    timestamp: str


def create_webui_server(rubberband_app, agentic_bridge) -> FastAPI:
    """
    Create the Web UI FastAPI application

    Args:
        rubberband_app: WontYouBeMyNeighbor instance with protocol references
        agentic_bridge: AgenticBridge instance for chat

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="RubberBand Dashboard",
        description="Web UI for Won't You Be My Neighbor routing agent"
    )

    # Include wizard router if available
    if WIZARD_AVAILABLE and wizard_router:
        app.include_router(wizard_router)

    # Log buffer for streaming
    log_buffer = LogBuffer()

    # Install log handler
    log_handler = WebUILogHandler(log_buffer)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
    logging.getLogger().addHandler(log_handler)

    # Static files directory
    static_dir = Path(__file__).parent / "static"

    # Mount static files if directory exists
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Serve the network builder wizard as landing page"""
        wizard_file = static_dir / "wizard.html"
        if wizard_file.exists():
            return FileResponse(str(wizard_file))
        return HTMLResponse(content=get_fallback_html(), status_code=200)

    @app.get("/wizard", response_class=HTMLResponse)
    async def wizard():
        """Serve the network builder wizard page (alias for root)"""
        return await root()

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Serve the single-agent dashboard page"""
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse(content="Dashboard not found.", status_code=404)

    @app.get("/monitor", response_class=HTMLResponse)
    async def monitor():
        """Serve the network monitor page"""
        monitor_file = static_dir / "monitor.html"
        if monitor_file.exists():
            return FileResponse(str(monitor_file))
        return HTMLResponse(content="Monitor page not found. Ensure webui/static/monitor.html exists.", status_code=404)

    @app.get("/realtime", response_class=HTMLResponse)
    async def realtime_monitor():
        """Serve the real-time network monitor page"""
        realtime_file = static_dir / "realtime-monitor.html"
        if realtime_file.exists():
            return FileResponse(str(realtime_file))
        return HTMLResponse(content="Real-time monitor not found.", status_code=404)

    @app.get("/agent", response_class=HTMLResponse)
    async def agent_dashboard():
        """Serve the per-agent dashboard with protocol-specific metrics"""
        agent_file = static_dir / "agent-dashboard.html"
        if agent_file.exists():
            return FileResponse(str(agent_file))
        return HTMLResponse(content="Agent dashboard not found.", status_code=404)

    @app.get("/overview", response_class=HTMLResponse)
    async def network_overview():
        """Serve the network overview dashboard"""
        overview_file = static_dir / "overview.html"
        if overview_file.exists():
            return FileResponse(str(overview_file))
        return HTMLResponse(content="Overview dashboard not found.", status_code=404)

    @app.get("/api/status")
    async def get_status() -> Dict[str, Any]:
        """Get current router status"""
        import socket
        import os

        # Get agent name from environment (set by orchestrator), then other sources
        agent_name = os.environ.get('RUBBERBAND_AGENT_NAME', None)
        if not agent_name:
            agent_name = getattr(rubberband_app, 'agent_name', None)
        if not agent_name and agentic_bridge:
            agent_name = getattr(agentic_bridge, 'rubberband_id', None)
        if not agent_name:
            agent_name = f"Router {rubberband_app.router_id}"

        # Get container name from environment or hostname
        container_name = os.environ.get('CONTAINER_NAME', None)
        if not container_name:
            # Try to get hostname (Docker sets this to container name by default)
            try:
                container_name = socket.gethostname()
            except:
                container_name = None

        status = {
            "agent_name": agent_name,
            "container_name": container_name,
            "router_id": rubberband_app.router_id,
            "running": rubberband_app.running,
            "timestamp": datetime.now().isoformat(),
            "interfaces": [],
            "ospf": None,
            "ospfv3": None,
            "bgp": None,
            "agentic": None
        }

        # Collect interface information
        if hasattr(rubberband_app, 'interfaces') and rubberband_app.interfaces:
            for iface in rubberband_app.interfaces:
                status["interfaces"].append({
                    "id": iface.get('id') or iface.get('n'),
                    "name": iface.get('n') or iface.get('name'),
                    "type": iface.get('t') or iface.get('type', 'eth'),
                    "addresses": iface.get('a') or iface.get('addresses', []),
                    "status": iface.get('s') or iface.get('status', 'up'),
                    "mtu": iface.get('mtu', 1500),
                    "description": iface.get('description', '')
                })
        elif hasattr(rubberband_app, 'config') and rubberband_app.config:
            # Try getting from config
            config_ifs = rubberband_app.config.get('ifs') or rubberband_app.config.get('interfaces', [])
            for iface in config_ifs:
                status["interfaces"].append({
                    "id": iface.get('id') or iface.get('n'),
                    "name": iface.get('n') or iface.get('name'),
                    "type": iface.get('t') or iface.get('type', 'eth'),
                    "addresses": iface.get('a') or iface.get('addresses', []),
                    "status": iface.get('s') or iface.get('status', 'up'),
                    "mtu": iface.get('mtu', 1500),
                    "description": iface.get('description', '')
                })

        # OSPF status
        if rubberband_app.ospf_interface:
            ospf = rubberband_app.ospf_interface
            status["ospf"] = {
                "area": ospf.area_id,
                "interface": ospf.interface,
                "ip": ospf.source_ip,
                "neighbors": len(ospf.neighbors),
                "full_neighbors": sum(1 for n in ospf.neighbors.values() if n.is_full()),
                "lsdb_size": ospf.lsdb.get_size(),
                "routes": len(ospf.spf_calc.routing_table),
                "neighbor_details": [
                    {
                        "router_id": n.router_id,
                        "ip": n.ip_address,
                        "state": n.get_state_name(),
                        "is_full": n.is_full()
                    }
                    for n in ospf.neighbors.values()
                ]
            }

        # OSPFv3 status
        if rubberband_app.ospfv3_speaker:
            ospfv3 = rubberband_app.ospfv3_speaker
            status["ospfv3"] = {
                "router_id": ospfv3.config.router_id,
                "areas": ospfv3.config.areas,
                "interfaces": len(ospfv3.interfaces)
            }

        # BGP status
        if rubberband_app.bgp_speaker:
            bgp = rubberband_app.bgp_speaker
            try:
                stats = bgp.get_statistics()
                status["bgp"] = {
                    "local_as": bgp.agent.local_as,
                    "router_id": bgp.agent.router_id,
                    "total_peers": stats.get("total_peers", 0),
                    "established_peers": stats.get("established_peers", 0),
                    "loc_rib_routes": stats.get("loc_rib_routes", 0),
                    "peer_details": []
                }

                # Get peer details from sessions
                for peer_ip, session in bgp.agent.sessions.items():
                    peer_as = session.config.peer_as if hasattr(session, 'config') else 0
                    state_name = "Unknown"
                    if hasattr(session, 'fsm') and hasattr(session.fsm, 'get_state_name'):
                        state_name = session.fsm.get_state_name()
                    elif hasattr(session, 'fsm') and hasattr(session.fsm, 'state'):
                        state_name = str(session.fsm.state)

                    status["bgp"]["peer_details"].append({
                        "ip": peer_ip,
                        "remote_as": peer_as,
                        "state": state_name,
                        "peer_type": "iBGP" if peer_as == bgp.agent.local_as else "eBGP"
                    })
            except Exception as e:
                status["bgp"] = {"error": str(e)}

        # Agentic status
        if agentic_bridge:
            # Get provider name safely
            provider_name = "Unknown"
            try:
                if hasattr(agentic_bridge, 'llm') and hasattr(agentic_bridge.llm, 'get_active_provider_name'):
                    provider_name = agentic_bridge.llm.get_active_provider_name()
                elif hasattr(agentic_bridge, 'get_active_provider_name'):
                    provider_name = agentic_bridge.get_active_provider_name()
            except Exception:
                pass

            # Get autonomous mode safely
            autonomous = False
            try:
                if hasattr(agentic_bridge, 'safety') and hasattr(agentic_bridge.safety, 'config'):
                    autonomous = agentic_bridge.safety.config.get("autonomous_mode", False)
            except Exception:
                pass

            status["agentic"] = {
                "rubberband_id": agentic_bridge.rubberband_id,
                "provider": provider_name,
                "autonomous_mode": autonomous
            }

        # MCP status - get from environment or config
        mcps = []
        mcp_types = ['gait', 'markmap', 'pyats', 'servicenow', 'netbox', 'rfc', 'slack', 'github']
        for mcp_type in mcp_types:
            env_key = f"MCP_{mcp_type.upper()}_ENABLED"
            if os.environ.get(env_key) == "true":
                mcps.append({
                    "type": mcp_type,
                    "name": mcp_type.upper(),
                    "enabled": True,
                    "description": {
                        'gait': 'AI session tracking',
                        'markmap': 'Topology visualization',
                        'pyats': 'Network testing',
                        'servicenow': 'ITSM integration',
                        'netbox': 'DCIM/IPAM',
                        'rfc': 'RFC standards lookup',
                        'slack': 'Team notifications',
                        'github': 'Version control'
                    }.get(mcp_type, mcp_type)
                })

        if mcps:
            status["mcps"] = mcps

        return status

    @app.get("/api/routes")
    async def get_routes() -> Dict[str, Any]:
        """Get routing tables"""
        routes = {
            "ospf": [],
            "bgp": []
        }

        # OSPF routes
        if rubberband_app.ospf_interface:
            for prefix, route_info in rubberband_app.ospf_interface.spf_calc.routing_table.items():
                # Try to determine outgoing interface from route info or next hop
                outgoing_if = getattr(route_info, 'outgoing_interface', None)
                if not outgoing_if and hasattr(route_info, 'interface'):
                    outgoing_if = route_info.interface
                if not outgoing_if:
                    # If next_hop is on a directly connected network, find interface
                    outgoing_if = rubberband_app.ospf_interface.interface if route_info.next_hop else 'local'

                routes["ospf"].append({
                    "prefix": prefix,
                    "next_hop": route_info.next_hop,
                    "interface": outgoing_if,
                    "cost": route_info.cost,
                    "type": getattr(route_info, 'route_type', 'Intra-Area')
                })

        # BGP routes
        if rubberband_app.bgp_speaker:
            try:
                bgp_routes = rubberband_app.bgp_speaker.agent.loc_rib.get_all_routes()
                for route in bgp_routes[:100]:  # Limit to 100 routes
                    next_hop = "N/A"
                    as_path = ""

                    if 3 in route.path_attributes:
                        nh_attr = route.path_attributes[3]
                        if hasattr(nh_attr, 'next_hop'):
                            next_hop = nh_attr.next_hop

                    if 2 in route.path_attributes:
                        path_attr = route.path_attributes[2]
                        if hasattr(path_attr, 'segments'):
                            try:
                                as_list = []
                                for seg in path_attr.segments:
                                    if hasattr(seg, 'asns'):
                                        as_list.extend(str(asn) for asn in seg.asns)
                                    elif isinstance(seg, tuple):
                                        as_list.extend(str(asn) for asn in seg[1])
                                as_path = " ".join(as_list)
                            except Exception:
                                as_path = "?"

                    # Try to determine outgoing interface for BGP route
                    bgp_outgoing_if = None
                    # If we have OSPF running, check if next_hop is reachable via OSPF
                    if rubberband_app.ospf_interface and next_hop != "N/A":
                        bgp_outgoing_if = rubberband_app.ospf_interface.interface
                    # Default to first interface if not found
                    if not bgp_outgoing_if and hasattr(rubberband_app, 'interfaces') and rubberband_app.interfaces:
                        for iface in rubberband_app.interfaces:
                            if iface.get('t') == 'eth' or iface.get('type') == 'eth':
                                bgp_outgoing_if = iface.get('n') or iface.get('name')
                                break

                    routes["bgp"].append({
                        "prefix": route.prefix,
                        "next_hop": next_hop,
                        "interface": bgp_outgoing_if or '-',
                        "as_path": as_path,
                        "source": route.source
                    })
            except Exception as e:
                routes["bgp_error"] = str(e)

        return routes

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(msg: ChatMessage) -> ChatResponse:
        """Send a chat message to Ralph"""
        if not agentic_bridge:
            return ChatResponse(
                response="Agentic interface not available",
                timestamp=datetime.now().isoformat()
            )

        try:
            response = await agentic_bridge.process_message(msg.message)
            return ChatResponse(
                response=response,
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            return ChatResponse(
                response=f"Error processing message: {e}",
                timestamp=datetime.now().isoformat()
            )

    @app.get("/api/logs")
    async def get_logs(count: int = 100) -> List[Dict]:
        """Get recent log entries"""
        return log_buffer.get_recent(count)

    @app.websocket("/ws/monitor")
    async def websocket_monitor(websocket: WebSocket):
        """WebSocket for real-time network-wide monitoring"""
        await websocket.accept()
        connected = True

        async def safe_send(data: dict) -> bool:
            nonlocal connected
            if not connected:
                return False
            try:
                await websocket.send_json(data)
                return True
            except Exception:
                connected = False
                return False

        try:
            # Send initial metrics
            metrics = await get_network_metrics()
            if not await safe_send({"type": "metrics", "data": metrics}):
                return

            # Send initial topology
            topology = await get_network_topology()
            if not await safe_send({"type": "topology", "data": topology}):
                return

            while connected:
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)

                    if data.get("type") == "subscribe":
                        # Acknowledge subscription
                        await safe_send({"type": "subscribed", "topics": data.get("topics", [])})
                    elif data.get("type") == "get_metrics":
                        metrics = await get_network_metrics()
                        await safe_send({"type": "metrics", "data": metrics})
                    elif data.get("type") == "get_topology":
                        topology = await get_network_topology()
                        await safe_send({"type": "topology", "data": topology})
                    elif data.get("type") == "get_agent_details":
                        agent_id = data.get("agent_id")
                        details = await get_agent_details(agent_id)
                        await safe_send({"type": "agent_details", "data": details})

                except asyncio.TimeoutError:
                    # Send periodic metrics update
                    metrics = await get_network_metrics()
                    if not await safe_send({"type": "metrics", "data": metrics}):
                        break

        except WebSocketDisconnect:
            connected = False
        except Exception as e:
            connected = False
            logging.getLogger("WebUI").debug(f"Monitor WebSocket closed: {e}")

    async def get_network_metrics() -> Dict[str, Any]:
        """Gather network-wide metrics"""
        metrics = {
            "runningNetworks": 0,
            "totalAgents": 0,
            "totalNeighbors": 0,
            "totalRoutes": 0,
            "protocols": {}
        }

        # OSPF metrics
        if rubberband_app.ospf_interface:
            ospf = rubberband_app.ospf_interface
            metrics["totalNeighbors"] += len(ospf.neighbors)
            metrics["totalRoutes"] += len(ospf.spf_calc.routing_table)
            metrics["protocols"]["ospf"] = {
                "active": True,
                "metrics": {
                    "neighbors": len(ospf.neighbors),
                    "full_neighbors": sum(1 for n in ospf.neighbors.values() if n.is_full()),
                    "lsdb_size": ospf.lsdb.get_size(),
                    "routes": len(ospf.spf_calc.routing_table)
                }
            }

        # BGP metrics
        if rubberband_app.bgp_speaker:
            bgp = rubberband_app.bgp_speaker
            try:
                stats = bgp.get_statistics()
                established = stats.get("established_peers", 0)
                routes = stats.get("loc_rib_routes", 0)
                metrics["totalNeighbors"] += established
                metrics["totalRoutes"] += routes
                metrics["protocols"]["bgp"] = {
                    "active": True,
                    "metrics": {
                        "total_peers": stats.get("total_peers", 0),
                        "established": established,
                        "routes": routes
                    }
                }
            except Exception:
                metrics["protocols"]["bgp"] = {"active": False, "metrics": {}}

        # IS-IS metrics (if available)
        isis_speaker = getattr(rubberband_app, 'isis_speaker', None)
        if isis_speaker:
            try:
                metrics["protocols"]["isis"] = {
                    "active": True,
                    "metrics": {
                        "neighbors": getattr(isis_speaker, 'neighbor_count', 0),
                        "lsp_count": getattr(isis_speaker, 'lsp_count', 0)
                    }
                }
            except Exception:
                pass

        # MPLS metrics (if available)
        mpls_forwarder = getattr(rubberband_app, 'mpls_forwarder', None)
        if mpls_forwarder:
            try:
                stats = mpls_forwarder.get_statistics()
                metrics["protocols"]["mpls"] = {
                    "active": True,
                    "metrics": {
                        "lfib_entries": stats.get("lfib_entries", 0),
                        "packets_forwarded": stats.get("packets_forwarded", 0)
                    }
                }
            except Exception:
                pass

        # VXLAN/EVPN metrics (if available)
        evpn_manager = getattr(rubberband_app, 'evpn_manager', None)
        if evpn_manager:
            try:
                metrics["protocols"]["vxlan"] = {
                    "active": True,
                    "metrics": {
                        "vnis": getattr(evpn_manager, 'vni_count', 0),
                        "vteps": getattr(evpn_manager, 'vtep_count', 0)
                    }
                }
            except Exception:
                pass

        return metrics

    async def get_network_topology() -> Dict[str, Any]:
        """Build network topology data"""
        topology = {
            "nodes": [],
            "links": []
        }

        # Add this agent as a node
        agent_name = getattr(rubberband_app, 'agent_name', None) or f"Router {rubberband_app.router_id}"
        topology["nodes"].append({
            "id": rubberband_app.router_id,
            "name": agent_name,
            "status": "running" if rubberband_app.running else "stopped"
        })

        # Add OSPF neighbors as nodes and links
        if rubberband_app.ospf_interface:
            for neighbor in rubberband_app.ospf_interface.neighbors.values():
                node_id = neighbor.router_id
                if not any(n["id"] == node_id for n in topology["nodes"]):
                    topology["nodes"].append({
                        "id": node_id,
                        "name": node_id,
                        "status": "running" if neighbor.is_full() else "initializing"
                    })
                topology["links"].append({
                    "source": rubberband_app.router_id,
                    "target": node_id,
                    "protocol": "OSPF",
                    "status": "up" if neighbor.is_full() else "down"
                })

        # Add BGP peers as nodes and links
        if rubberband_app.bgp_speaker:
            try:
                for peer_ip, session in rubberband_app.bgp_speaker.agent.sessions.items():
                    node_id = peer_ip
                    state = "Unknown"
                    if hasattr(session, 'fsm') and hasattr(session.fsm, 'get_state_name'):
                        state = session.fsm.get_state_name()

                    if not any(n["id"] == node_id for n in topology["nodes"]):
                        topology["nodes"].append({
                            "id": node_id,
                            "name": f"AS {session.config.peer_as if hasattr(session, 'config') else '?'}",
                            "status": "running" if state == "Established" else "initializing"
                        })
                    topology["links"].append({
                        "source": rubberband_app.router_id,
                        "target": node_id,
                        "protocol": "BGP",
                        "status": "up" if state == "Established" else "down"
                    })
            except Exception:
                pass

        return topology

    async def get_agent_details(agent_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific agent"""
        details = {
            "id": agent_id,
            "protocols": [],
            "statistics": {}
        }

        if agent_id == rubberband_app.router_id:
            if rubberband_app.ospf_interface:
                details["protocols"].append({
                    "name": "OSPF",
                    "active": True,
                    "area": rubberband_app.ospf_interface.area_id
                })
            if rubberband_app.bgp_speaker:
                details["protocols"].append({
                    "name": "BGP",
                    "active": True,
                    "local_as": rubberband_app.bgp_speaker.agent.local_as
                })

        return details

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates"""
        await websocket.accept()
        log_buffer.register_websocket(websocket)
        connected = True

        async def safe_send(data: dict) -> bool:
            """Safely send JSON, return False if connection lost"""
            nonlocal connected
            if not connected:
                return False
            try:
                await websocket.send_json(data)
                return True
            except Exception:
                connected = False
                return False

        try:
            # Send initial status
            status = await get_status()
            if not await safe_send({"type": "status", "data": status}):
                return

            # Send recent logs
            logs = log_buffer.get_recent(50)
            for log in logs:
                if not await safe_send({"type": "log", "data": log}):
                    return

            # Keep connection alive and send periodic status updates
            while connected:
                try:
                    # Wait for messages from client
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)

                    if data.get("type") == "chat":
                        # Handle chat message
                        response = await chat(ChatMessage(message=data.get("message", "")))
                        await safe_send({
                            "type": "chat_response",
                            "data": {"response": response.response, "timestamp": response.timestamp}
                        })
                    elif data.get("type") == "get_status":
                        status = await get_status()
                        await safe_send({"type": "status", "data": status})
                    elif data.get("type") == "get_routes":
                        routes = await get_routes()
                        await safe_send({"type": "routes", "data": routes})

                except asyncio.TimeoutError:
                    # Send periodic status update
                    status = await get_status()
                    if not await safe_send({"type": "status", "data": status}):
                        break

        except WebSocketDisconnect:
            connected = False
        except Exception as e:
            connected = False
            logging.getLogger("WebUI").debug(f"WebSocket closed: {e}")
        finally:
            log_buffer.unregister_websocket(websocket)

    return app


def get_fallback_html() -> str:
    """Return fallback HTML if static files not found"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RubberBand Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #00d9ff; }
        .status { background: #16213e; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .error { color: #ff6b6b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>RubberBand Dashboard</h1>
        <div class="status">
            <p class="error">Static files not found. Please ensure the webui/static directory exists.</p>
            <p>API endpoints are still available:</p>
            <ul>
                <li><a href="/api/status">/api/status</a> - Router status</li>
                <li><a href="/api/routes">/api/routes</a> - Routing tables</li>
                <li><a href="/api/logs">/api/logs</a> - Recent logs</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""
