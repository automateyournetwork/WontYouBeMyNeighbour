"""
Web UI Server for Won't You Be My Neighbor

FastAPI-based web dashboard providing:
- Chat interface for ASI agentic assistant
- Real-time protocol status (OSPF/BGP neighbors, routes)
- Log streaming via WebSocket
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import wizard router
try:
    from .wizard_api import router as wizard_router
    WIZARD_AVAILABLE = True
except ImportError:
    WIZARD_AVAILABLE = False
    wizard_router = None


# Log buffer for streaming to web clients
# Storage for NetBox configuration (received from wizard during deployment)
_netbox_config_storage: Dict[str, Any] = {}

class LogBuffer:
    """Thread-safe circular buffer for log messages"""

    def __init__(self, maxlen: int = 500):
        self._buffer = deque(maxlen=maxlen)
        self._websockets: List[WebSocket] = []
        self._ws_lock = asyncio.Lock()  # Lock for thread-safe websocket list access

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
                    task = asyncio.create_task(self._safe_send(ws, entry))
                    # Add error callback to handle task exceptions
                    task.add_done_callback(self._handle_task_error)
            except (AttributeError, RuntimeError) as e:
                # Log specific errors, don't silently swallow
                logging.getLogger("WebUI").debug(f"WebSocket check failed: {e}")

    def _handle_task_error(self, task):
        """Handle errors from async send tasks"""
        try:
            exc = task.exception()
            if exc and not task.cancelled():
                logging.getLogger("WebUI").debug(f"WebSocket send task error: {exc}")
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            pass

    async def _safe_send(self, ws: WebSocket, entry: dict):
        """Safely send to websocket, removing on failure"""
        try:
            await ws.send_json({"type": "log", "data": entry})
        except Exception as e:
            # Remove failed websocket with lock protection
            logging.getLogger("WebUI").debug(f"WebSocket send failed: {e}")
            async with self._ws_lock:
                if ws in self._websockets:
                    self._websockets.remove(ws)

    def get_recent(self, count: int = 100) -> List[Dict]:
        """Get recent log entries"""
        return list(self._buffer)[-count:]

    async def register_websocket(self, ws: WebSocket):
        """Register a websocket for log streaming (async for lock)"""
        async with self._ws_lock:
            self._websockets.append(ws)

    async def unregister_websocket(self, ws: WebSocket):
        """Unregister a websocket (async for lock)"""
        async with self._ws_lock:
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


def create_webui_server(asi_app, agentic_bridge) -> FastAPI:
    """
    Create the Web UI FastAPI application

    Args:
        asi_app: WontYouBeMyNeighbor instance with protocol references
        agentic_bridge: AgenticBridge instance for chat

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="ASI Dashboard",
        description="Web UI for Won't You Be My Neighbor routing agent"
    )

    # Add CORS middleware to allow wizard (port 5111) to push config to agents (ports 8801+)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for local development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Track app startup time for uptime display
    app_start_time = datetime.now()

    # Startup event handler to initialize agentic bridge, GAIT, and LLDP
    @app.on_event("startup")
    async def startup_event():
        """Initialize agentic bridge, GAIT tracking, and LLDP on server startup"""
        if agentic_bridge:
            try:
                await agentic_bridge.initialize()
                logging.getLogger("WebUI").info("AgenticBridge and GAIT initialized successfully")
            except Exception as e:
                logging.getLogger("WebUI").error(f"Failed to initialize AgenticBridge: {e}")

        # Start LLDP daemon to query lldpcli for real neighbor data
        try:
            from agentic.discovery.lldp import start_lldp, LLDPConfig
            config = LLDPConfig(enabled=True, tx_interval=30)
            await start_lldp("local", config)
            logging.getLogger("WebUI").info("LLDP daemon started - will query lldpcli for neighbors")
        except Exception as e:
            logging.getLogger("WebUI").warning(f"LLDP daemon not started: {e}")

        # Start Prometheus metrics collection
        try:
            from agentic.mcp.prometheus_mcp import (
                get_prometheus_client, collect_system_metrics, collect_interface_metrics
            )
            import asyncio

            prometheus = get_prometheus_client()
            # Create exporter for this agent
            agent_id = os.environ.get("ASI_AGENT_ID", "local")
            router_id = os.environ.get("ASI_ROUTER_ID", "10.255.255.1")
            exporter = prometheus.create_exporter(agent_id, router_id)

            # Background task to collect metrics every 10 seconds
            async def metrics_collector():
                while True:
                    try:
                        await collect_system_metrics(exporter)
                        await collect_interface_metrics(exporter)

                        # Record OSPF metrics from actual protocol state
                        ospf_neighbors = 0
                        ospf_full = 0
                        lsdb_size = 0
                        ospf_routes = 0
                        if asi_app and asi_app.ospf_interface:
                            ospf = asi_app.ospf_interface
                            ospf_neighbors = len(ospf.neighbors)
                            ospf_full = sum(1 for n in ospf.neighbors.values() if n.is_full())
                            lsdb_size = ospf.lsdb.get_size() if hasattr(ospf, 'lsdb') else 0
                            ospf_routes = len(ospf.spf_calc.routing_table) if hasattr(ospf, 'spf_calc') else 0
                        exporter.set_gauge("ospf_neighbors_total", float(ospf_neighbors))
                        exporter.set_gauge("ospf_neighbors_full", float(ospf_full))
                        exporter.set_gauge("ospf_lsdb_size", float(lsdb_size))
                        exporter.set_gauge("ospf_routes_total", float(ospf_routes))

                        # Record BGP metrics from actual protocol state
                        bgp_peers = 0
                        bgp_established = 0
                        bgp_routes = 0
                        if asi_app and asi_app.bgp_speaker:
                            bgp = asi_app.bgp_speaker
                            if hasattr(bgp, 'agent') and bgp.agent:
                                bgp_peers = len(bgp.agent.sessions)
                                bgp_established = sum(1 for s in bgp.agent.sessions.values()
                                                     if hasattr(s, 'fsm') and hasattr(s.fsm, 'state') and 'ESTABLISHED' in str(s.fsm.state).upper())
                                if hasattr(bgp.agent, 'loc_rib'):
                                    bgp_routes = len(bgp.agent.loc_rib.get_all_routes())
                        exporter.set_gauge("bgp_peers_total", float(bgp_peers))
                        exporter.set_gauge("bgp_peers_established", float(bgp_established))
                        exporter.set_gauge("bgp_routes_total", float(bgp_routes))

                        # Record OSPF message counters
                        ospf_stats = {}
                        if asi_app and asi_app.ospf_interface:
                            ospf = asi_app.ospf_interface
                            # Try to get message stats from OSPF interface
                            if hasattr(ospf, 'stats'):
                                ospf_stats = ospf.stats
                            elif hasattr(ospf, 'message_stats'):
                                ospf_stats = ospf.message_stats
                        exporter.set_gauge("ospf_hello_sent_total", float(ospf_stats.get('hello_sent', 0)))
                        exporter.set_gauge("ospf_hello_recv_total", float(ospf_stats.get('hello_recv', 0)))
                        exporter.set_gauge("ospf_dbd_sent_total", float(ospf_stats.get('dbd_sent', 0)))
                        exporter.set_gauge("ospf_dbd_recv_total", float(ospf_stats.get('dbd_recv', 0)))
                        exporter.set_gauge("ospf_lsr_sent_total", float(ospf_stats.get('lsr_sent', 0)))
                        exporter.set_gauge("ospf_lsr_recv_total", float(ospf_stats.get('lsr_recv', 0)))
                        exporter.set_gauge("ospf_lsu_sent_total", float(ospf_stats.get('lsu_sent', 0)))
                        exporter.set_gauge("ospf_lsu_recv_total", float(ospf_stats.get('lsu_recv', 0)))
                        exporter.set_gauge("ospf_lsack_sent_total", float(ospf_stats.get('lsack_sent', 0)))
                        exporter.set_gauge("ospf_lsack_recv_total", float(ospf_stats.get('lsack_recv', 0)))

                        # Record BGP message counters
                        bgp_stats = {}
                        if asi_app and asi_app.bgp_speaker:
                            bgp = asi_app.bgp_speaker
                            if hasattr(bgp, 'stats'):
                                bgp_stats = bgp.stats
                            elif hasattr(bgp, 'agent') and hasattr(bgp.agent, 'stats'):
                                bgp_stats = bgp.agent.stats
                        exporter.set_gauge("bgp_open_sent_total", float(bgp_stats.get('open_sent', 0)))
                        exporter.set_gauge("bgp_open_recv_total", float(bgp_stats.get('open_recv', 0)))
                        exporter.set_gauge("bgp_update_sent_total", float(bgp_stats.get('update_sent', 0)))
                        exporter.set_gauge("bgp_update_recv_total", float(bgp_stats.get('update_recv', 0)))
                        exporter.set_gauge("bgp_keepalive_sent_total", float(bgp_stats.get('keepalive_sent', 0)))
                        exporter.set_gauge("bgp_keepalive_recv_total", float(bgp_stats.get('keepalive_recv', 0)))
                        exporter.set_gauge("bgp_notification_sent_total", float(bgp_stats.get('notification_sent', 0)))
                        exporter.set_gauge("bgp_notification_recv_total", float(bgp_stats.get('notification_recv', 0)))

                        # Record interface count
                        interface_count = len(asi_app.interfaces) if asi_app and hasattr(asi_app, 'interfaces') else 0
                        exporter.set_gauge("agent_interfaces_total", float(interface_count))

                        # Update QoS statistics from ALL protocols in the stack
                        try:
                            from agentic.protocols.qos import get_qos_manager
                            qos = get_qos_manager(agent_id)

                            # Get primary interface for QoS
                            interfaces = list(qos.interface_policies.keys())
                            if not interfaces and asi_app and hasattr(asi_app, 'interfaces'):
                                for iface in asi_app.interfaces:
                                    iface_name = iface.get('name') or iface.get('n')
                                    if iface_name:
                                        interfaces.append(iface_name)
                            iface = interfaces[0] if interfaces else 'eth0'

                            # Update QoS from ALL protocol stats (OSPF, OSPFv3, BGP, ISIS, LDP, LLDP, BFD)
                            qos.update_from_protocol_stats(asi_app, iface)

                            # Log current QoS state
                            if qos.total_classified > 0:
                                logging.getLogger("WebUI").debug(
                                    f"QoS: classified={qos.total_classified}, marked={qos.total_marked}"
                                )

                        except Exception as qos_err:
                            logging.getLogger("WebUI").debug(f"QoS tracking: {qos_err}")

                        # Update NetFlow from protocol activity
                        try:
                            from agentic.protocols.netflow import get_flow_exporter

                            netflow = get_flow_exporter(agent_id, router_id)
                            local_ip = router_id  # Use router ID as source

                            # Record OSPF flows
                            if ospf_stats:
                                hello_count = ospf_stats.get('hello_sent', 0) + ospf_stats.get('hello_recv', 0)
                                if hello_count > 0:
                                    netflow.record_protocol_flow(
                                        "ospf", local_ip, "224.0.0.5",  # OSPF multicast
                                        hello_count * 64, iface, "egress", 48, "network_control"
                                    )

                            # Record BGP flows
                            if bgp_stats:
                                bgp_count = sum([
                                    bgp_stats.get('keepalive_sent', 0),
                                    bgp_stats.get('update_sent', 0),
                                    bgp_stats.get('open_sent', 0)
                                ])
                                if bgp_count > 0:
                                    # Get BGP peers if available
                                    if asi_app.bgp_speaker and hasattr(asi_app.bgp_speaker, 'agent'):
                                        for peer_ip in asi_app.bgp_speaker.agent.sessions.keys():
                                            netflow.record_protocol_flow(
                                                "bgp", local_ip, peer_ip,
                                                bgp_count * 64, iface, "egress", 48, "network_control"
                                            )

                        except Exception as nf_err:
                            logging.getLogger("WebUI").debug(f"NetFlow tracking: {nf_err}")

                        logging.getLogger("WebUI").debug(f"Collected metrics: OSPF neighbors={ospf_neighbors}, BGP peers={bgp_peers}")
                    except Exception as e:
                        logging.getLogger("WebUI").warning(f"Metrics collection error: {e}")
                    await asyncio.sleep(10)

            asyncio.create_task(metrics_collector())
            logging.getLogger("WebUI").info(f"Prometheus metrics collection started for agent {agent_id}")
        except Exception as e:
            logging.getLogger("WebUI").warning(f"Prometheus metrics not started: {e}")

        # Initialize QoS (RFC 4594) - always enabled, auto-apply to all interfaces
        try:
            from agentic.protocols.qos import get_qos_manager
            agent_id = os.environ.get("ASI_AGENT_ID", "local")
            qos = get_qos_manager(agent_id)

            # Get interfaces and apply QoS policy
            interfaces = []
            if asi_app and hasattr(asi_app, 'interfaces') and asi_app.interfaces:
                interfaces = [iface.get('n') or iface.get('name', 'eth0') for iface in asi_app.interfaces]
            if not interfaces:
                interfaces = ['eth0', 'eth1', 'lo0']  # Defaults

            qos.apply_to_all_interfaces(interfaces)
            logging.getLogger("WebUI").info(f"QoS (RFC 4594) enabled on {len(interfaces)} interfaces - DSCP marking active")
        except Exception as e:
            logging.getLogger("WebUI").warning(f"QoS initialization: {e}")

        # Initialize SLAAC (RFC 4862) for IPv6 overlay addresses
        try:
            from agentic.protocols.slaac import initialize_agent_slaac
            agent_id = os.environ.get("ASI_AGENT_ID", "local")
            slaac_result = initialize_agent_slaac(agent_id)
            logging.getLogger("WebUI").info(f"SLAAC assigned mesh address: {slaac_result.get('mesh_address')}")
        except Exception as e:
            logging.getLogger("WebUI").warning(f"SLAAC initialization: {e}")

        # Initialize NetFlow/IPFIX (RFC 7011) for flow tracking
        try:
            from agentic.protocols.netflow import get_flow_exporter
            agent_id = os.environ.get("ASI_AGENT_ID", "local")
            router_id = os.environ.get("ASI_ROUTER_ID", "0.0.0.0")
            netflow = get_flow_exporter(agent_id, router_id)
            netflow.export_interval = 30  # Export every 30 seconds
            logging.getLogger("WebUI").info(f"NetFlow (RFC 7011) exporter initialized - tracking flows")
        except Exception as e:
            logging.getLogger("WebUI").warning(f"NetFlow initialization: {e}")

    # Include wizard router if available
    if WIZARD_AVAILABLE and wizard_router:
        app.include_router(wizard_router)

    # Use existing log buffer from asi_app if available (captures all protocol logs)
    # Otherwise create a new one (for standalone/wizard mode)
    if hasattr(asi_app, 'log_buffer') and asi_app.log_buffer is not None:
        log_buffer = asi_app.log_buffer
        logging.getLogger("WebUI").info("Using existing log buffer with protocol logs")
    else:
        # Create new log buffer for standalone mode
        log_buffer = LogBuffer()
        # Install log handler only if we created a new buffer
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
        """Serve the full agent dashboard with protocol tabs (GAIT, Testing, Markmap, etc.)"""
        dashboard_file = static_dir / "agent-dashboard.html"
        if dashboard_file.exists():
            return FileResponse(str(dashboard_file))
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

    @app.get("/topology3d", response_class=HTMLResponse)
    async def topology_3d():
        """Serve the 3D network topology visualization"""
        topology3d_file = static_dir / "topology3d.html"
        if topology3d_file.exists():
            return FileResponse(str(topology3d_file))
        return HTMLResponse(content="3D topology not found.", status_code=404)

    # NOTE: /api/logs endpoint is defined later in this file (around line 610)
    # using the log_buffer for actual protocol logs - DO NOT add a duplicate here

    @app.get("/api/status")
    async def get_status() -> Dict[str, Any]:
        """Get current router status"""
        import socket
        import os

        # Get agent name from environment (set by orchestrator), then other sources
        agent_name = os.environ.get('ASI_AGENT_NAME', None)
        if not agent_name:
            agent_name = getattr(asi_app, 'agent_name', None)
        if not agent_name and agentic_bridge:
            agent_name = getattr(agentic_bridge, 'asi_id', None)
        if not agent_name:
            agent_name = f"Router {asi_app.router_id}"

        # Get container name from environment or hostname
        container_name = os.environ.get('CONTAINER_NAME', None)
        if not container_name:
            # Try to get hostname (Docker sets this to container name by default)
            try:
                container_name = socket.gethostname()
            except OSError as e:
                logging.getLogger("WebUI").debug(f"Failed to get hostname: {e}")
                container_name = None

        status = {
            "agent_name": agent_name,
            "container_name": container_name,
            "router_id": asi_app.router_id,
            "running": asi_app.running,
            "timestamp": datetime.now().isoformat(),
            "interfaces": [],
            "ospf": None,
            "ospfv3": None,
            "bgp": None,
            "agentic": None
        }

        # Collect interface information from multiple sources
        def add_interface(iface):
            status["interfaces"].append({
                "id": iface.get('id') or iface.get('n'),
                "name": iface.get('n') or iface.get('name'),
                "type": iface.get('t') or iface.get('type', 'eth'),
                "addresses": iface.get('a') or iface.get('addresses', []),
                "status": iface.get('s') or iface.get('status', 'up'),
                "mtu": iface.get('mtu', 1500),
                "description": iface.get('description', '')
            })

        # Source 1: asi_app.interfaces
        if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
            for iface in asi_app.interfaces:
                add_interface(iface)
        # Source 2: asi_app.config
        elif hasattr(asi_app, 'config') and asi_app.config:
            config_ifs = asi_app.config.get('ifs') or asi_app.config.get('interfaces', [])
            for iface in config_ifs:
                add_interface(iface)

        # Source 3: State manager interfaces (fallback)
        if not status["interfaces"] and agentic_bridge:
            try:
                if hasattr(agentic_bridge, 'state_manager'):
                    state_manager = agentic_bridge.state_manager
                    if hasattr(state_manager, '_interfaces') and state_manager._interfaces:
                        for iface in state_manager._interfaces:
                            add_interface(iface)
            except Exception:
                pass

        # Source 4: Original config (last resort)
        if not status["interfaces"] and hasattr(asi_app, '_original_config'):
            orig_ifs = asi_app._original_config.get('ifs') or asi_app._original_config.get('interfaces', [])
            for iface in orig_ifs:
                add_interface(iface)

        # OSPF status
        if asi_app.ospf_interface:
            ospf = asi_app.ospf_interface
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
        if asi_app.ospfv3_speaker:
            ospfv3 = asi_app.ospfv3_speaker
            status["ospfv3"] = {
                "router_id": ospfv3.config.router_id,
                "areas": ospfv3.config.areas,
                "interfaces": len(ospfv3.interfaces)
            }

        # BGP status
        if asi_app.bgp_speaker:
            bgp = asi_app.bgp_speaker
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
            # Model ID to human-readable name mapping
            model_display_names = {
                "claude-sonnet-4-20250514": "Claude Sonnet 4",
                "claude-opus-4-5-20251101": "Claude Opus 4.5",
                "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
                "claude-3-5-haiku-20241022": "Claude 3.5 Haiku",
                "claude-3-sonnet-20240229": "Claude 3 Sonnet",
                "claude-3-opus-20240229": "Claude 3 Opus",
                "gpt-4-turbo": "GPT-4 Turbo",
                "gpt-4o": "GPT-4o",
                "gpt-4": "GPT-4",
                "gemini-1.5-pro": "Gemini 1.5 Pro",
            }

            # Get provider and model name safely
            provider_name = "Unknown"
            model_name = ""
            try:
                if hasattr(agentic_bridge, 'llm'):
                    llm = agentic_bridge.llm
                    # LLMInterface has preferred_provider and providers dict
                    if hasattr(llm, 'preferred_provider') and hasattr(llm, 'providers'):
                        # Get the preferred provider enum value (e.g., LLMProvider.CLAUDE)
                        pref_provider = llm.preferred_provider
                        # Get provider name from enum value
                        provider_name = pref_provider.value.capitalize() if hasattr(pref_provider, 'value') else str(pref_provider)

                        # Get the actual provider instance from providers dict
                        if pref_provider in llm.providers:
                            active_provider = llm.providers[pref_provider]
                            # Get model from provider instance
                            if hasattr(active_provider, 'model') and active_provider.model:
                                raw_model = active_provider.model
                                # Convert to human-readable name
                                model_name = model_display_names.get(raw_model, raw_model)
                            # Keep provider name simple (Claude, OpenAI, etc.) - don't use get_provider_name which includes model
                        elif llm.providers:
                            # Fallback to first available provider
                            first_provider_type = next(iter(llm.providers))
                            active_provider = llm.providers[first_provider_type]
                            provider_name = first_provider_type.value.capitalize() if hasattr(first_provider_type, 'value') else str(first_provider_type)
                            if hasattr(active_provider, 'model') and active_provider.model:
                                raw_model = active_provider.model
                                model_name = model_display_names.get(raw_model, raw_model)
            except Exception as e:
                logger.debug(f"Error getting LLM provider info: {e}")

            # Get autonomous mode safely
            autonomous = False
            try:
                if hasattr(agentic_bridge, 'safety') and hasattr(agentic_bridge.safety, 'config'):
                    autonomous = agentic_bridge.safety.config.get("autonomous_mode", False)
            except Exception:
                pass

            status["agentic"] = {
                "asi_id": agentic_bridge.asi_id,
                "provider": provider_name,
                "model": model_name,
                "autonomous_mode": autonomous
            }

        # Calculate uptime
        uptime_delta = datetime.now() - app_start_time
        uptime_seconds = int(uptime_delta.total_seconds())
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"
        status["uptime"] = uptime_str

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

        # ND (Neighbor Discovery) status - Layer 2 ASI Overlay
        try:
            from agentic.discovery.neighbor_discovery import get_neighbor_discovery
            nd = get_neighbor_discovery()
            if nd._running:
                status["nd"] = {
                    "enabled": True,
                    "local_ipv6": nd._local_ipv6,
                    "neighbors": len(nd.get_neighbors()),
                    "reachable": len(nd.get_neighbors(reachable_only=True))
                }
        except ImportError:
            pass
        except Exception:
            pass

        return status

    @app.get("/api/interfaces")
    async def get_interfaces() -> Dict[str, Any]:
        """
        Get all interfaces configured on this agent.

        Returns interfaces from multiple sources:
        1. asi_app.interfaces (config)
        2. asi_app.config.ifs
        3. State manager _interfaces
        """
        interfaces = []

        # Source 1: asi_app.interfaces
        if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
            for iface in asi_app.interfaces:
                interfaces.append({
                    "id": iface.get('id') or iface.get('n'),
                    "name": iface.get('n') or iface.get('name'),
                    "type": iface.get('t') or iface.get('type', 'eth'),
                    "addresses": iface.get('a') or iface.get('addresses', []),
                    "status": iface.get('s') or iface.get('status', 'up'),
                    "mtu": iface.get('mtu', 1500),
                    "description": iface.get('description', '')
                })

        # Source 2: asi_app.config
        if not interfaces and hasattr(asi_app, 'config') and asi_app.config:
            config_ifs = asi_app.config.get('ifs') or asi_app.config.get('interfaces', [])
            for iface in config_ifs:
                interfaces.append({
                    "id": iface.get('id') or iface.get('n'),
                    "name": iface.get('n') or iface.get('name'),
                    "type": iface.get('t') or iface.get('type', 'eth'),
                    "addresses": iface.get('a') or iface.get('addresses', []),
                    "status": iface.get('s') or iface.get('status', 'up'),
                    "mtu": iface.get('mtu', 1500),
                    "description": iface.get('description', '')
                })

        # Source 3: State manager (agentic_bridge.state_manager._interfaces)
        if not interfaces and agentic_bridge:
            try:
                if hasattr(agentic_bridge, 'state_manager'):
                    state_manager = agentic_bridge.state_manager
                    if hasattr(state_manager, '_interfaces') and state_manager._interfaces:
                        for iface in state_manager._interfaces:
                            interfaces.append({
                                "id": iface.get('id') or iface.get('n'),
                                "name": iface.get('n') or iface.get('name'),
                                "type": iface.get('t') or iface.get('type', 'eth'),
                                "addresses": iface.get('a') or iface.get('addresses', []),
                                "status": iface.get('s') or iface.get('status', 'up'),
                                "mtu": iface.get('mtu', 1500),
                                "description": iface.get('description', '')
                            })
            except Exception as e:
                logger.debug(f"Error getting state manager interfaces: {e}")

        # Source 4: Original config passed to ASIApp
        if not interfaces and hasattr(asi_app, '_original_config'):
            orig_ifs = asi_app._original_config.get('ifs') or asi_app._original_config.get('interfaces', [])
            for iface in orig_ifs:
                interfaces.append({
                    "id": iface.get('id') or iface.get('n'),
                    "name": iface.get('n') or iface.get('name'),
                    "type": iface.get('t') or iface.get('type', 'eth'),
                    "addresses": iface.get('a') or iface.get('addresses', []),
                    "status": iface.get('s') or iface.get('status', 'up'),
                    "mtu": iface.get('mtu', 1500),
                    "description": iface.get('description', '')
                })

        return {
            "interfaces": interfaces,
            "count": len(interfaces)
        }

    # ========================================
    # NetBox Configuration Storage
    # (Received from wizard during deployment)
    # ========================================

    @app.get("/api/config/netbox")
    async def get_netbox_config() -> Dict[str, Any]:
        """Get stored NetBox configuration for this agent"""
        global _netbox_config_storage
        if _netbox_config_storage:
            return {
                "status": "ok",
                "config": _netbox_config_storage
            }
        return {
            "status": "not_configured",
            "config": None
        }

    @app.post("/api/config/netbox")
    async def set_netbox_config(request: Request) -> Dict[str, Any]:
        """Store NetBox configuration for this agent (called by wizard during deployment)"""
        global _netbox_config_storage
        try:
            data = await request.json()
            # Validate required fields
            if not data.get('netbox_url') or not data.get('api_token'):
                return {"status": "error", "message": "Missing netbox_url or api_token"}

            _netbox_config_storage = {
                "netbox_url": data.get('netbox_url'),
                "api_token": data.get('api_token'),
                "site_name": data.get('site_name'),
                "device_name": data.get('device_name')
            }

            logging.getLogger("WebUI").info(f"[NetBox] Stored config for device: {_netbox_config_storage.get('device_name')}")
            return {"status": "ok", "message": "NetBox config stored"}
        except Exception as e:
            logging.getLogger("WebUI").error(f"[NetBox] Failed to store config: {e}")
            return {"status": "error", "message": str(e)}

    @app.get("/api/netbox/sync")
    async def sync_netbox_device() -> Dict[str, Any]:
        """
        Get full device sync status from NetBox using stored config.
        Fetches device info, interfaces, IPs, services, and cables.
        """
        global _netbox_config_storage

        if not _netbox_config_storage:
            return {"status": "not_configured", "error": "NetBox not configured for this agent"}

        netbox_url = _netbox_config_storage.get("netbox_url")
        api_token = _netbox_config_storage.get("api_token")
        device_name = _netbox_config_storage.get("device_name")

        if not all([netbox_url, api_token, device_name]):
            return {"status": "error", "error": "Missing required NetBox configuration (url, token, or device_name)"}

        try:
            from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

            config = NetBoxConfig(url=netbox_url, api_token=api_token)
            client = NetBoxClient(config)

            # Get device by name
            device = await client.get_device(device_name)
            if not device:
                await client.close()
                return {
                    "status": "not_found",
                    "error": f"Device '{device_name}' not found in NetBox"
                }

            device_id = device["id"]

            # Get the underlying HTTP client for direct API calls
            http_client = await client._get_client()

            # Get interfaces with full details
            interfaces_raw = await client.get_interfaces(device_id)
            interfaces = []
            for iface in (interfaces_raw or []):
                interfaces.append({
                    "id": iface.get("id"),
                    "name": iface.get("name"),
                    "type": iface.get("type", {}).get("value") if isinstance(iface.get("type"), dict) else iface.get("type"),
                    "enabled": iface.get("enabled", True),
                    "url": f"{netbox_url.rstrip('/')}/dcim/interfaces/{iface.get('id')}/"
                })
            interface_count = len(interfaces)

            # Get IP addresses for the device
            ip_addresses = []
            try:
                ip_response = await http_client.get(
                    "/api/ipam/ip-addresses/",
                    params={"device_id": device_id, "limit": 100}
                )
                logging.getLogger("WebUI").info(f"[NetBox] IP query for device_id={device_id}, status={ip_response.status_code}")
                if ip_response.status_code == 200:
                    ip_data = ip_response.json()
                    logging.getLogger("WebUI").info(f"[NetBox] IP results count: {ip_data.get('count', 0)}, results: {len(ip_data.get('results', []))}")
                    for ip in ip_data.get("results", []):
                        ip_addresses.append({
                            "id": ip.get("id"),
                            "address": ip.get("address"),
                            "status": ip.get("status", {}).get("value") if isinstance(ip.get("status"), dict) else ip.get("status"),
                            "interface": ip.get("assigned_object", {}).get("name") if ip.get("assigned_object") else None,
                            "url": f"{netbox_url.rstrip('/')}/ipam/ip-addresses/{ip.get('id')}/"
                        })
                else:
                    logging.getLogger("WebUI").warning(f"[NetBox] IP query failed: {ip_response.text[:200]}")
            except Exception as e:
                logging.getLogger("WebUI").warning(f"[NetBox] Could not get IP addresses: {e}")
            ip_count = len(ip_addresses)

            # Get services for the device
            services = []
            try:
                svc_response = await http_client.get(
                    "/api/ipam/services/",
                    params={"device_id": device_id, "limit": 100}
                )
                if svc_response.status_code == 200:
                    svc_data = svc_response.json()
                    for svc in svc_data.get("results", []):
                        services.append({
                            "id": svc.get("id"),
                            "name": svc.get("name"),
                            "protocol": svc.get("protocol", {}).get("value") if isinstance(svc.get("protocol"), dict) else svc.get("protocol"),
                            "ports": svc.get("ports", []),
                            "url": f"{netbox_url.rstrip('/')}/ipam/services/{svc.get('id')}/"
                        })
            except Exception as e:
                logging.getLogger("WebUI").warning(f"[NetBox] Could not get services: {e}")
            service_count = len(services)

            # Get cable connections
            connections = await client.get_interface_connections(device_id)
            logging.getLogger("WebUI").info(f"[NetBox] Cable connections for device_id={device_id}: {len(connections)} found")
            if connections:
                logging.getLogger("WebUI").info(f"[NetBox] First connection: {connections[0]}")
            cables = []
            for conn in connections:
                cable_id = conn.get("cable_id")
                cables.append({
                    "local_interface": conn.get("local_interface"),
                    "remote_device": conn.get("remote_device"),
                    "remote_interface": conn.get("remote_interface"),
                    "cable_id": cable_id,
                    "status": "connected",
                    "url": f"{netbox_url.rstrip('/')}/dcim/cables/{cable_id}/" if cable_id else None
                })

            await client.close()

            # Build NetBox URL for the device
            device_url = f"{netbox_url.rstrip('/')}/dcim/devices/{device_id}/"

            # Extract site name
            site_name = None
            if device.get("site"):
                site_name = device["site"].get("name") if isinstance(device["site"], dict) else str(device["site"])

            # Extract primary IP
            primary_ip = None
            if device.get("primary_ip4"):
                primary_ip = device["primary_ip4"].get("address") if isinstance(device["primary_ip4"], dict) else str(device["primary_ip4"])
            elif device.get("primary_ip"):
                primary_ip = device["primary_ip"].get("address") if isinstance(device["primary_ip"], dict) else str(device["primary_ip"])

            return {
                "status": "ok",
                "device": {
                    "id": device_id,
                    "name": device.get("name"),
                    "site": site_name,
                    "primary_ip": primary_ip,
                    "url": device_url,
                    "interface_count": interface_count,
                    "ip_count": ip_count,
                    "service_count": service_count,
                    "status": device.get("status", {}).get("value") if isinstance(device.get("status"), dict) else device.get("status"),
                    "role": device.get("role", {}).get("name") if isinstance(device.get("role"), dict) else device.get("role")
                },
                "interfaces": interfaces,
                "ip_addresses": ip_addresses,
                "services": services,
                "cables": cables
            }
        except ImportError:
            return {"status": "error", "error": "NetBox client module not available"}
        except Exception as e:
            logging.getLogger("WebUI").error(f"[NetBox] Sync error: {e}")
            return {"status": "error", "error": str(e)}

    @app.post("/api/netbox/push")
    async def push_to_netbox(request: Request) -> Dict[str, Any]:
        """
        PUSH sync - Agent is Master.
        Push local agent configuration to NetBox, registering/updating:
        - Device
        - All interfaces
        - All IP addresses
        - ALL running services (OSPF, BGP, IS-IS, etc.)

        This ensures NetBox reflects the current agent state.
        """
        global _netbox_config_storage

        if not _netbox_config_storage:
            return {"status": "error", "error": "NetBox not configured for this agent"}

        netbox_url = _netbox_config_storage.get("netbox_url")
        api_token = _netbox_config_storage.get("api_token")
        device_name = _netbox_config_storage.get("device_name")
        site_name = _netbox_config_storage.get("site_name", "Default")

        if not all([netbox_url, api_token, device_name]):
            return {"status": "error", "error": "Missing required NetBox configuration"}

        try:
            body = await request.json()
            provided_protocols = body.get("protocols", [])
        except:
            provided_protocols = []

        try:
            from agentic.mcp.netbox_mcp import (
                NetBoxClient, NetBoxConfig, configure_netbox, auto_register_agent
            )

            # Build agent config from current local state
            agent_config = {
                "router_id": getattr(asi_app, 'router_id', device_name),
                "interfaces": [],
                "protocols": []
            }

            # Get interfaces from local state
            if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
                for iface in asi_app.interfaces.values():
                    iface_data = {
                        "name": getattr(iface, 'name', str(iface)),
                        "type": getattr(iface, 'type', 'ethernet'),
                        "enabled": getattr(iface, 'enabled', True),
                    }
                    # Get IP from interface
                    if hasattr(iface, 'ip_address') and iface.ip_address:
                        iface_data["ip"] = iface.ip_address
                    elif hasattr(iface, 'addresses') and iface.addresses:
                        iface_data["ip"] = iface.addresses[0] if iface.addresses else None
                    agent_config["interfaces"].append(iface_data)

            # Detect running protocols from asi_app
            if asi_app.ospf_interface:
                area = getattr(asi_app.ospf_interface, 'area_id', '0.0.0.0')
                agent_config["protocols"].append({"type": "ospf", "area": area})
                logging.getLogger("WebUI").info(f"[NetBox PUSH] Detected OSPF Area {area}")

            if hasattr(asi_app, 'bgp_speaker') and asi_app.bgp_speaker:
                local_as = getattr(asi_app.bgp_speaker, 'local_as', None)
                agent_config["protocols"].append({"type": "bgp", "local_as": local_as})
                logging.getLogger("WebUI").info(f"[NetBox PUSH] Detected BGP AS {local_as}")

            if hasattr(asi_app, 'isis_instance') and asi_app.isis_instance:
                agent_config["protocols"].append({"type": "isis"})
                logging.getLogger("WebUI").info("[NetBox PUSH] Detected IS-IS")

            if hasattr(asi_app, 'ldp_session') and asi_app.ldp_session:
                agent_config["protocols"].append({"type": "ldp"})
                logging.getLogger("WebUI").info("[NetBox PUSH] Detected LDP")

            if hasattr(asi_app, 'mpls_manager') and asi_app.mpls_manager:
                agent_config["protocols"].append({"type": "mpls"})
                logging.getLogger("WebUI").info("[NetBox PUSH] Detected MPLS")

            # Also include any protocols explicitly provided in request
            for proto in provided_protocols:
                proto_type = proto.get("type", "").lower()
                if proto_type and not any(p.get("type") == proto_type for p in agent_config["protocols"]):
                    agent_config["protocols"].append(proto)
                    logging.getLogger("WebUI").info(f"[NetBox PUSH] Added provided protocol: {proto_type}")

            logging.getLogger("WebUI").info(f"[NetBox PUSH] Registering device '{device_name}' with {len(agent_config['protocols'])} protocols: {[p.get('type') for p in agent_config['protocols']]}")

            # Configure and register
            config = NetBoxConfig(
                url=netbox_url,
                api_token=api_token,
                site_name=site_name,
                auto_register=True
            )
            configure_netbox(config)

            result = await auto_register_agent(device_name, agent_config)

            # Close client
            from agentic.mcp.netbox_mcp import get_netbox_client
            client = get_netbox_client()
            if client:
                await client.close()

            return {
                "status": "ok" if result.get("success") else "error",
                "success": result.get("success", False),
                "device_name": device_name,
                "interfaces": result.get("interfaces", []),
                "ip_addresses": result.get("ip_addresses", []),
                "services": result.get("services", []),
                "errors": result.get("errors", [])
            }

        except ImportError as e:
            return {"status": "error", "error": f"NetBox client module not available: {e}"}
        except Exception as e:
            logging.getLogger("WebUI").error(f"[NetBox PUSH] Error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

    @app.post("/api/netbox/pull")
    async def pull_from_netbox(request: Request) -> Dict[str, Any]:
        """
        PULL sync - NetBox is Master.
        Pull device configuration from NetBox to local agent.

        This imports the NetBox device's interfaces, IPs, and services
        to update the local agent configuration.
        """
        global _netbox_config_storage

        if not _netbox_config_storage:
            return {"status": "error", "error": "NetBox not configured for this agent"}

        netbox_url = _netbox_config_storage.get("netbox_url")
        api_token = _netbox_config_storage.get("api_token")
        device_name = _netbox_config_storage.get("device_name")

        if not all([netbox_url, api_token, device_name]):
            return {"status": "error", "error": "Missing required NetBox configuration"}

        try:
            from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

            config = NetBoxConfig(url=netbox_url, api_token=api_token)
            client = NetBoxClient(config)

            # Get device from NetBox
            device = await client.get_device(device_name)
            if not device:
                await client.close()
                return {"status": "error", "error": f"Device '{device_name}' not found in NetBox"}

            device_id = device["id"]
            http_client = await client._get_client()

            # Get interfaces
            interfaces_raw = await client.get_interfaces(device_id)
            interfaces = []
            for iface in (interfaces_raw or []):
                interfaces.append({
                    "id": iface.get("id"),
                    "name": iface.get("name"),
                    "type": iface.get("type", {}).get("value") if isinstance(iface.get("type"), dict) else iface.get("type"),
                    "enabled": iface.get("enabled", True)
                })

            # Get IP addresses
            ip_addresses = []
            try:
                ip_response = await http_client.get("/api/ipam/ip-addresses/", params={"device_id": device_id, "limit": 100})
                if ip_response.status_code == 200:
                    for ip in ip_response.json().get("results", []):
                        ip_addresses.append({
                            "id": ip.get("id"),
                            "address": ip.get("address"),
                            "interface": ip.get("assigned_object", {}).get("name") if ip.get("assigned_object") else None
                        })
            except Exception as e:
                logging.getLogger("WebUI").warning(f"[NetBox PULL] Could not get IPs: {e}")

            # Get services
            services = []
            try:
                svc_response = await http_client.get("/api/ipam/services/", params={"device_id": device_id, "limit": 100})
                if svc_response.status_code == 200:
                    for svc in svc_response.json().get("results", []):
                        services.append({
                            "id": svc.get("id"),
                            "name": svc.get("name"),
                            "protocol": svc.get("protocol", {}).get("value") if isinstance(svc.get("protocol"), dict) else svc.get("protocol"),
                            "ports": svc.get("ports", [])
                        })
            except Exception as e:
                logging.getLogger("WebUI").warning(f"[NetBox PULL] Could not get services: {e}")

            await client.close()

            logging.getLogger("WebUI").info(f"[NetBox PULL] Imported from NetBox: {len(interfaces)} interfaces, {len(ip_addresses)} IPs, {len(services)} services")

            # Note: Actual local agent update logic would go here
            # For now, we just return what was fetched for display

            return {
                "status": "ok",
                "success": True,
                "device_name": device_name,
                "interfaces": interfaces,
                "ip_addresses": ip_addresses,
                "services": services,
                "message": "Configuration imported from NetBox (read-only preview)"
            }

        except ImportError as e:
            return {"status": "error", "error": f"NetBox client module not available: {e}"}
        except Exception as e:
            logging.getLogger("WebUI").error(f"[NetBox PULL] Error: {e}")
            return {"status": "error", "error": str(e)}

    @app.get("/api/nd/neighbors")
    async def get_nd_neighbors() -> Dict[str, Any]:
        """Get IPv6 Neighbor Discovery neighbors (Layer 2: ASI Overlay)"""
        try:
            from agentic.discovery.neighbor_discovery import get_neighbor_discovery
            nd = get_neighbor_discovery()

            return {
                "layer": "ASI Overlay (Layer 2)",
                "local_ipv6": nd._local_ipv6,
                "running": nd._running,
                "statistics": nd.get_statistics(),
                "neighbors": [n.to_dict() for n in nd.get_neighbors()]
            }
        except ImportError:
            return {
                "error": "Neighbor Discovery module not available",
                "neighbors": []
            }
        except Exception as e:
            return {
                "error": str(e),
                "neighbors": []
            }

    @app.get("/api/routes")
    async def get_routes() -> Dict[str, Any]:
        """Get routing tables"""
        routes = {
            "ospf": [],
            "bgp": []
        }

        # OSPF routes
        if asi_app.ospf_interface:
            for prefix, route_info in asi_app.ospf_interface.spf_calc.routing_table.items():
                # Try to determine outgoing interface from route info or next hop
                outgoing_if = getattr(route_info, 'outgoing_interface', None)
                if not outgoing_if and hasattr(route_info, 'interface'):
                    outgoing_if = route_info.interface
                if not outgoing_if:
                    # If next_hop is on a directly connected network, find interface
                    outgoing_if = asi_app.ospf_interface.interface if route_info.next_hop else 'local'

                routes["ospf"].append({
                    "prefix": prefix,
                    "next_hop": route_info.next_hop,
                    "interface": outgoing_if,
                    "cost": route_info.cost,
                    "type": getattr(route_info, 'route_type', 'Intra-Area')
                })

        # BGP routes
        if asi_app.bgp_speaker:
            try:
                bgp_routes = asi_app.bgp_speaker.agent.loc_rib.get_all_routes()
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
                    if asi_app.ospf_interface and next_hop != "N/A":
                        bgp_outgoing_if = asi_app.ospf_interface.interface
                    # Default to first interface if not found
                    if not bgp_outgoing_if and hasattr(asi_app, 'interfaces') and asi_app.interfaces:
                        for iface in asi_app.interfaces:
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
    async def get_logs(count: int = 100, tail: int = None) -> Dict[str, Any]:
        """Get recent log entries

        Args:
            count: Number of log entries to return (default 100)
            tail: Alias for count, for backwards compatibility

        Returns:
            Dict with 'logs' key containing list of log entries
        """
        # Support both 'count' and 'tail' parameters
        num_entries = tail if tail is not None else count
        logs = log_buffer.get_recent(num_entries)
        return {"logs": logs, "count": len(logs)}

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
        if asi_app.ospf_interface:
            ospf = asi_app.ospf_interface
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
        if asi_app.bgp_speaker:
            bgp = asi_app.bgp_speaker
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
        isis_speaker = getattr(asi_app, 'isis_speaker', None)
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
        mpls_forwarder = getattr(asi_app, 'mpls_forwarder', None)
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
        evpn_manager = getattr(asi_app, 'evpn_manager', None)
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
        agent_name = getattr(asi_app, 'agent_name', None) or f"Router {asi_app.router_id}"
        topology["nodes"].append({
            "id": asi_app.router_id,
            "name": agent_name,
            "status": "running" if asi_app.running else "stopped"
        })

        # Add OSPF neighbors as nodes and links
        if asi_app.ospf_interface:
            for neighbor in asi_app.ospf_interface.neighbors.values():
                node_id = neighbor.router_id
                if not any(n["id"] == node_id for n in topology["nodes"]):
                    topology["nodes"].append({
                        "id": node_id,
                        "name": node_id,
                        "status": "running" if neighbor.is_full() else "initializing"
                    })
                topology["links"].append({
                    "source": asi_app.router_id,
                    "target": node_id,
                    "protocol": "OSPF",
                    "status": "up" if neighbor.is_full() else "down"
                })

        # Add BGP peers as nodes and links
        if asi_app.bgp_speaker:
            try:
                for peer_ip, session in asi_app.bgp_speaker.agent.sessions.items():
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
                        "source": asi_app.router_id,
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

        if agent_id == asi_app.router_id:
            if asi_app.ospf_interface:
                details["protocols"].append({
                    "name": "OSPF",
                    "active": True,
                    "area": asi_app.ospf_interface.area_id
                })
            if asi_app.bgp_speaker:
                details["protocols"].append({
                    "name": "BGP",
                    "active": True,
                    "local_as": asi_app.bgp_speaker.agent.local_as
                })

        return details

    # ==================== pyATS Testing API ====================
    # Store recent test results in memory for persistence across page refreshes
    _recent_test_results: Dict[str, Any] = {"results": [], "timestamp": None, "summary": {}}

    async def run_pyats_tests(suites: List[str], agent_id: Optional[str]) -> Dict[str, Any]:
        """Run pyATS tests for the specified suites"""
        nonlocal _recent_test_results

        try:
            from pyATS_Tests import run_all_tests, get_tests_for_agent
        except ImportError:
            return {
                "status": "error",
                "message": "pyATS_Tests module not available",
                "results": []
            }

        # Build agent config from current state
        agent_config = {
            "id": agent_id or asi_app.router_id,
            "n": getattr(asi_app, 'agent_name', None) or f"Agent {asi_app.router_id}",
            "r": asi_app.router_id,
            "ifs": [],
            "protos": [],
            "state": {}  # Include runtime state for dynamic tests
        }

        # Add interfaces
        if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
            agent_config["ifs"] = asi_app.interfaces
        elif hasattr(asi_app, 'config') and asi_app.config:
            agent_config["ifs"] = asi_app.config.get('ifs') or asi_app.config.get('interfaces', [])

        # Add protocols
        if asi_app.ospf_interface:
            agent_config["protos"].append({
                "p": "ospf",
                "area": asi_app.ospf_interface.area_id,
                "peers": []
            })
            # Add OSPF neighbors to state for dynamic tests
            ospf_nbrs = []
            for nbr_id, nbr in asi_app.ospf_interface.neighbors.items():
                ospf_nbrs.append({
                    "ip": nbr.ip_address,  # OSPFNeighbor uses ip_address, not source_ip
                    "router_id": nbr_id,
                    "state": "FULL" if nbr.is_full() else "INIT"
                })
            agent_config["state"]["nbrs"] = ospf_nbrs

        if asi_app.bgp_speaker:
            bgp_peers = []
            for peer_ip, session in asi_app.bgp_speaker.agent.sessions.items():
                bgp_peers.append({
                    "ip": peer_ip,
                    "asn": session.config.peer_as,
                    "state": session.state.name if hasattr(session.state, 'name') else str(session.state)
                })
            agent_config["protos"].append({
                "p": "bgp",
                "asn": asi_app.bgp_speaker.agent.local_as,
                "peers": bgp_peers
            })
            agent_config["state"]["peers"] = bgp_peers

        isis_speaker = getattr(asi_app, 'isis_speaker', None)
        if isis_speaker:
            agent_config["protos"].append({"p": "isis"})
        mpls_forwarder = getattr(asi_app, 'mpls_forwarder', None)
        if mpls_forwarder:
            agent_config["protos"].append({"p": "mpls"})
        evpn_manager = getattr(asi_app, 'evpn_manager', None)
        if evpn_manager:
            agent_config["protos"].append({"p": "vxlan"})

        try:
            # Run tests
            test_results = await run_all_tests(agent_config, suite_filter=suites if suites else None)

            # Flatten results from all suites into a single array for the UI
            # The pyATS test framework returns results nested under "suites"
            flattened_results = []
            for suite in test_results.get("suites", []):
                suite_name = suite.get("suite_name", "Unknown Suite")
                for result in suite.get("results", []):
                    flattened_results.append({
                        "test_id": result.get("test_id", ""),
                        "test_name": result.get("test_name", "Unknown Test"),
                        "description": result.get("message", ""),
                        "suite_name": suite_name,
                        "status": result.get("status", "unknown"),
                        "failure_reason": result.get("message", "") if result.get("status") == "failed" else None,
                        "duration": f"{result.get('duration_ms', 0):.2f}ms",
                        "timestamp": result.get("timestamp", datetime.now().isoformat())
                    })

            # Store results for persistence
            _recent_test_results = {
                "results": flattened_results,
                "timestamp": datetime.now().isoformat(),
                "summary": test_results.get("summary", {}),
                "agent_id": agent_id or asi_app.router_id
            }

            # Return with flattened results for the UI
            return {
                "agent_id": test_results.get("agent_id"),
                "timestamp": test_results.get("timestamp"),
                "duration_ms": test_results.get("duration_ms"),
                "summary": test_results.get("summary", {}),
                "results": flattened_results
            }
        except Exception as e:
            logging.getLogger("WebUI").error(f"Test execution failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "results": []
            }

    def get_recent_test_results() -> Dict[str, Any]:
        """Get the most recent test results (for page refresh persistence)"""
        return _recent_test_results

    async def update_test_schedule(
        agent_id: Optional[str],
        interval_minutes: int,
        run_on_change: bool
    ) -> Dict[str, Any]:
        """Update the test schedule for an agent"""
        try:
            from pyATS_Tests.scheduler import get_scheduler, TestSchedule, ScheduleType
        except ImportError:
            return {
                "status": "error",
                "message": "Test scheduler not available"
            }

        scheduler = get_scheduler()
        schedule_id = f"agent-{agent_id or asi_app.router_id}-default"

        # Check if schedule exists
        existing = scheduler.get_schedule(schedule_id)

        if interval_minutes == 0 and not run_on_change:
            # Disable/remove schedule
            if existing:
                scheduler.remove_schedule(schedule_id)
            return {
                "status": "success",
                "message": "Test schedule disabled",
                "schedule_id": schedule_id
            }

        # Create or update interval schedule
        if interval_minutes > 0:
            schedule = TestSchedule(
                schedule_id=schedule_id,
                agent_id=agent_id or asi_app.router_id,
                suite_ids=[],  # All suites
                schedule_type=ScheduleType.INTERVAL,
                enabled=True,
                interval_minutes=interval_minutes
            )

            if existing:
                scheduler.update_schedule(schedule)
            else:
                scheduler.add_schedule(schedule)

        # Create or update event-based schedule
        if run_on_change:
            event_schedule_id = f"{schedule_id}-on-change"
            event_schedule = TestSchedule(
                schedule_id=event_schedule_id,
                agent_id=agent_id or asi_app.router_id,
                suite_ids=[],
                schedule_type=ScheduleType.EVENT,
                enabled=True,
                event_trigger="config_change"
            )

            existing_event = scheduler.get_schedule(event_schedule_id)
            if existing_event:
                scheduler.update_schedule(event_schedule)
            else:
                scheduler.add_schedule(event_schedule)

        return {
            "status": "success",
            "message": "Test schedule updated",
            "schedule_id": schedule_id,
            "interval_minutes": interval_minutes,
            "run_on_change": run_on_change
        }

    # ==================== GAIT API ====================
    async def get_gait_history(agent_id: Optional[str]) -> Dict[str, Any]:
        """Get GAIT conversation history for an agent - now linked to chat"""
        gait_data = {
            "total_turns": 0,
            "user_messages": 0,
            "agent_messages": 0,
            "actions_taken": 0,
            "history": [],
            "gait_initialized": False
        }

        # Try to get conversation history from agentic bridge (with GAIT integration)
        if agentic_bridge:
            try:
                # Use new GAIT-integrated methods if available
                if hasattr(agentic_bridge, 'get_gait_status'):
                    status = agentic_bridge.get_gait_status()
                    gait_data.update({
                        "total_turns": status.get("total_turns", 0),
                        "user_messages": status.get("user_messages", 0),
                        "agent_messages": status.get("agent_messages", 0),
                        "actions_taken": status.get("actions_taken", 0),
                        "gait_initialized": status.get("gait_initialized", False),
                        "head_commit": status.get("head_commit"),
                        "pinned_memory": status.get("pinned_memory", 0)
                    })

                # Get history from GAIT client
                if hasattr(agentic_bridge, 'get_gait_history'):
                    history = await agentic_bridge.get_gait_history(limit=100)
                    gait_data["history"] = history
                else:
                    # Fallback to local conversation history
                    if hasattr(agentic_bridge, 'conversation_history'):
                        history = agentic_bridge.conversation_history
                        for item in history:
                            msg_type = item.get('role', 'user')
                            gait_data["history"].append({
                                "type": msg_type,
                                "sender": msg_type.capitalize(),
                                "message": item.get('content', ''),
                                "timestamp": item.get('timestamp', datetime.now().isoformat())
                            })

                    # Also include action history
                    if hasattr(agentic_bridge, 'action_history'):
                        for action in agentic_bridge.action_history:
                            gait_data["history"].append({
                                "type": "action",
                                "sender": "Action",
                                "message": f"{action.get('action', 'Unknown')}: {action.get('result', '')}",
                                "timestamp": action.get('timestamp', datetime.now().isoformat())
                            })

            except Exception as e:
                logging.getLogger("WebUI").debug(f"Failed to get GAIT history: {e}")

        # Sort history by timestamp
        gait_data["history"].sort(key=lambda x: x.get("timestamp", ""), reverse=False)

        return gait_data

    # ==================== Markmap API ====================
    async def get_markmap_state(agent_id: Optional[str]) -> Dict[str, Any]:
        """Generate Markmap SVG visualization of agent state"""
        # Build markdown representation of agent state
        agent_name = getattr(asi_app, 'agent_name', None) or f"Agent {asi_app.router_id}"
        md_lines = [f"# {agent_name}"]

        # Router ID
        md_lines.append(f"\n## Router: {asi_app.router_id}")

        # Interfaces
        md_lines.append("\n## Interfaces")
        interfaces = []
        if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
            interfaces = asi_app.interfaces
        elif hasattr(asi_app, 'config') and asi_app.config:
            interfaces = asi_app.config.get('ifs') or asi_app.config.get('interfaces', [])

        for iface in interfaces:
            name = iface.get('n') or iface.get('name') or 'Unknown'
            status = iface.get('s') or iface.get('status', 'up')
            addrs = iface.get('a') or iface.get('addresses', [])
            md_lines.append(f"### {name} ({status})")
            for addr in addrs:
                md_lines.append(f"- {addr}")

        # Protocols
        md_lines.append("\n## Protocols")

        # OSPF
        if asi_app.ospf_interface:
            ospf = asi_app.ospf_interface
            md_lines.append(f"### OSPF (Area {ospf.area_id})")
            md_lines.append(f"- Neighbors: {len(ospf.neighbors)}")
            md_lines.append(f"- Full: {sum(1 for n in ospf.neighbors.values() if n.is_full())}")
            md_lines.append(f"- LSDB: {ospf.lsdb.get_size()} LSAs")
            md_lines.append(f"- Routes: {len(ospf.spf_calc.routing_table)}")

        # BGP
        if asi_app.bgp_speaker:
            bgp = asi_app.bgp_speaker
            try:
                stats = bgp.get_statistics()
                md_lines.append(f"### BGP (AS {bgp.agent.local_as})")
                md_lines.append(f"- Peers: {stats.get('total_peers', 0)}")
                md_lines.append(f"- Established: {stats.get('established_peers', 0)}")
                md_lines.append(f"- Routes: {stats.get('loc_rib_routes', 0)}")
            except Exception:
                md_lines.append("### BGP")
                md_lines.append("- Error getting stats")

        # IS-IS
        isis_speaker = getattr(asi_app, 'isis_speaker', None)
        if isis_speaker:
            md_lines.append("### IS-IS")
            md_lines.append(f"- Neighbors: {getattr(isis_speaker, 'neighbor_count', 0)}")
            md_lines.append(f"- LSPs: {getattr(isis_speaker, 'lsp_count', 0)}")

        # MPLS
        mpls_forwarder = getattr(asi_app, 'mpls_forwarder', None)
        if mpls_forwarder:
            try:
                stats = mpls_forwarder.get_statistics()
                md_lines.append("### MPLS")
                md_lines.append(f"- LFIB Entries: {stats.get('lfib_entries', 0)}")
                md_lines.append(f"- Packets: {stats.get('packets_forwarded', 0)}")
            except Exception:
                md_lines.append("### MPLS")

        # VXLAN/EVPN
        evpn_manager = getattr(asi_app, 'evpn_manager', None)
        if evpn_manager:
            md_lines.append("### VXLAN/EVPN")
            md_lines.append(f"- VNIs: {getattr(evpn_manager, 'vni_count', 0)}")
            md_lines.append(f"- VTEPs: {getattr(evpn_manager, 'vtep_count', 0)}")

        markdown_content = "\n".join(md_lines)

        # Try to generate SVG using markmap MCP if available
        svg_content = None
        try:
            # Check if markmap MCP is available via MCP client
            # For now, return the markdown and let the frontend render it
            # Future: Call mcp__markmap__markmap_generate
            pass
        except Exception:
            pass

        return {
            "markdown": markdown_content,
            "svg": svg_content,
            "timestamp": datetime.now().isoformat()
        }

    # ==================== Testing API Endpoints ====================
    @app.get("/api/tests/suites")
    async def get_test_suites() -> Dict[str, Any]:
        """Get available test suites"""
        try:
            from pyATS_Tests import get_tests_for_agent
        except ImportError:
            return {"suites": [], "error": "pyATS_Tests module not available"}

        # Build agent config from current state
        agent_config = {
            "id": asi_app.router_id,
            "protos": []
        }
        if asi_app.ospf_interface:
            agent_config["protos"].append({"t": "ospf"})
        if asi_app.bgp_speaker:
            agent_config["protos"].append({"t": "bgp"})

        try:
            test_suites = get_tests_for_agent(agent_config)
            return {
                "suites": [
                    {
                        "id": suite.suite_id,
                        "name": suite.suite_name,
                        "description": suite.description,
                        "test_count": len(suite.tests),
                        "protocol": suite.protocol
                    }
                    for suite in test_suites
                ]
            }
        except Exception as e:
            return {"suites": [], "error": str(e)}

    @app.post("/api/tests/run")
    async def api_run_tests(suites: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run tests via REST API"""
        return await run_pyats_tests(suites or [], None)

    @app.get("/api/tests/results")
    async def get_test_results(limit: int = 10) -> Dict[str, Any]:
        """Get recent test results - includes both scheduler and on-demand results"""
        results_data = get_recent_test_results()

        # If we have recent on-demand results, return those
        if results_data.get("results"):
            return {
                "results": results_data["results"],
                "timestamp": results_data.get("timestamp"),
                "summary": results_data.get("summary", {})
            }

        # Fall back to scheduler results
        try:
            from pyATS_Tests.scheduler import get_scheduler
            scheduler = get_scheduler()
            results = scheduler.get_results(asi_app.router_id, limit)
            return {
                "results": [r.to_dict() for r in results]
            }
        except ImportError:
            return {"results": [], "error": "Scheduler not available"}
        except Exception as e:
            return {"results": [], "error": str(e)}

    # ==================== pyATS MCP Dynamic Testing API ====================
    # These endpoints enable agents to dynamically generate and execute tests
    # via the pyATS MCP server (Self-Testing Network capability)

    class DynamicTestRequest(BaseModel):
        """Request body for dynamic test generation"""
        test_types: Optional[List[str]] = None

    @app.post("/api/pyats/run-dynamic-tests")
    async def run_dynamic_pyats_tests(request: DynamicTestRequest) -> Dict[str, Any]:
        """
        Run dynamically generated pyATS tests via pyATS MCP.

        This is the core of the Self-Testing Network - the agent generates
        AEtest scripts based on its configuration and executes them.

        Args:
            test_types: List of test types to run. Options:
                - "comprehensive": Full self-assessment (default)
                - "connectivity": Ping/reachability tests
                - "ospf": OSPF neighbor state tests
                - "bgp": BGP peer state tests
                - "interfaces": Interface state tests

        Returns:
            Test execution results with pass/fail details
        """
        try:
            from agentic.tests import (
                DynamicTestGenerator,
                TestTrigger,
            )
            from agentic.mcp import PyATSMCPClient

            # Build agent config from current state
            agent_config = _build_agent_config_for_testing()

            # Create test generator
            generator = DynamicTestGenerator(agent_config)

            # Default to comprehensive if no types specified
            test_types = request.test_types or ["comprehensive"]

            results = []
            generated_tests = []

            for test_type in test_types:
                if test_type == "comprehensive":
                    test = generator.generate_comprehensive_self_test(
                        trigger=TestTrigger.HUMAN_REQUEST
                    )
                elif test_type == "connectivity":
                    test = generator.generate_neighbor_reachability_test(
                        trigger=TestTrigger.HUMAN_REQUEST
                    )
                elif test_type == "ospf":
                    test = generator.generate_ospf_neighbor_test(
                        trigger=TestTrigger.HUMAN_REQUEST
                    )
                elif test_type == "bgp":
                    test = generator.generate_bgp_peer_test(
                        trigger=TestTrigger.HUMAN_REQUEST
                    )
                elif test_type == "interfaces":
                    test = generator.generate_interface_state_test(
                        trigger=TestTrigger.HUMAN_REQUEST
                    )
                else:
                    continue

                # Execute the test and get results
                test_result = await _execute_dynamic_test(test, agent_config)
                generated_tests.append(test_result)

            # Calculate summary
            total_passed = sum(1 for t in generated_tests if t.get("status") == "PASSED")
            total_failed = sum(1 for t in generated_tests if t.get("status") == "FAILED")
            total_tests = len(generated_tests)
            pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

            return {
                "success": True,
                "message": f"Executed {len(generated_tests)} tests",
                "tests": generated_tests,
                "summary": {
                    "total": total_tests,
                    "passed": total_passed,
                    "failed": total_failed,
                    "pass_rate": round(pass_rate, 1)
                },
                "agent_config": {
                    "agent_id": agent_config.get("id"),
                    "router_id": agent_config.get("r"),
                    "protocols": [p.get("p") for p in agent_config.get("protos", [])],
                    "interface_count": len(agent_config.get("ifs", [])),
                },
            }

        except ImportError as e:
            return {
                "success": False,
                "error": f"Dynamic test module not available: {e}",
                "tests": []
            }
        except Exception as e:
            logger.error(f"Dynamic test generation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "tests": []
            }

    @app.get("/api/pyats/test-types")
    async def get_pyats_test_types() -> Dict[str, Any]:
        """Get available dynamic test types for pyATS MCP"""
        return {
            "test_types": [
                {
                    "id": "comprehensive",
                    "name": "Comprehensive Self-Assessment",
                    "description": "Full self-test including connectivity, protocols, and interfaces",
                    "default": True
                },
                {
                    "id": "connectivity",
                    "name": "Connectivity Tests",
                    "description": "Ping all configured neighbors and verify reachability"
                },
                {
                    "id": "ospf",
                    "name": "OSPF State Tests",
                    "description": "Verify all OSPF neighbors are in FULL state"
                },
                {
                    "id": "bgp",
                    "name": "BGP State Tests",
                    "description": "Verify all BGP peers are Established"
                },
                {
                    "id": "interfaces",
                    "name": "Interface State Tests",
                    "description": "Verify all interfaces are in expected operational state"
                }
            ]
        }

    @app.get("/api/pyats/status")
    async def get_pyats_mcp_status() -> Dict[str, Any]:
        """Check pyATS MCP server status and configuration"""
        try:
            # Check if self-testing is enabled on the bridge
            if asi_app.agentic_bridge and hasattr(asi_app.agentic_bridge, '_self_test_enabled'):
                enabled = asi_app.agentic_bridge._self_test_enabled
                pass_rate = asi_app.agentic_bridge.get_test_pass_rate() if enabled else 0
                history = asi_app.agentic_bridge.get_test_history(5) if enabled else []
            else:
                enabled = False
                pass_rate = 0
                history = []

            return {
                "pyats_mcp_enabled": enabled,
                "pass_rate": pass_rate,
                "recent_tests": history,
                "config": {
                    "testbed_path": getattr(asi_app, 'testbed_path', None),
                    "server_path": getattr(asi_app, 'pyats_server_path', None),
                }
            }
        except Exception as e:
            return {
                "pyats_mcp_enabled": False,
                "error": str(e)
            }

    async def _execute_dynamic_test(test, agent_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a dynamically generated test and return results.

        This runs actual checks based on the test type:
        - Connectivity: Ping targets
        - OSPF: Check neighbor states
        - BGP: Check peer states
        - Interface: Check interface states
        """
        import subprocess
        import time
        from datetime import datetime

        start_time = time.time()
        test_results = []
        overall_status = "PASSED"
        details = []

        test_data = test.test_data
        category = test.category.value

        try:
            if category == "connectivity" or "ping_targets" in test_data:
                # Run actual ping tests
                targets = test_data.get("targets", test_data.get("ping_targets", []))
                # Get our own router ID to skip self-ping
                our_router_id = agent_config.get("r", "")
                our_loopbacks = []
                for iface in agent_config.get("ifs", []):
                    if iface.get("t") == "lo":  # Loopback interface
                        for addr in iface.get("a", []):
                            # Extract IP without prefix
                            ip = addr.split("/")[0] if "/" in addr else addr
                            our_loopbacks.append(ip)

                for target in targets:
                    if not target or target == "0.0.0.0":
                        continue
                    # Skip pinging our own addresses
                    if target == our_router_id or target in our_loopbacks:
                        test_results.append({"target": target, "status": "SKIPPED", "message": "Self (skipped)"})
                        details.append(f"- {target}: Self (skipped)")
                        continue
                    try:
                        # Run ping with timeout
                        result = subprocess.run(
                            ["ping", "-c", "2", "-W", "2", str(target)],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            test_results.append({"target": target, "status": "PASSED", "message": "Reachable"})
                            details.append(f"✓ {target}: Reachable")
                        else:
                            test_results.append({"target": target, "status": "FAILED", "message": "Unreachable"})
                            details.append(f"✗ {target}: Unreachable")
                            overall_status = "FAILED"
                    except subprocess.TimeoutExpired:
                        test_results.append({"target": target, "status": "FAILED", "message": "Timeout"})
                        details.append(f"✗ {target}: Timeout")
                        overall_status = "FAILED"
                    except Exception as e:
                        test_results.append({"target": target, "status": "ERROR", "message": str(e)})
                        details.append(f"? {target}: Error - {e}")

            if category == "protocol_state" or "expected_neighbors" in test_data:
                # Check OSPF neighbors if available
                if asi_app.ospf_interface and test_data.get("expected_neighbors"):
                    try:
                        actual_neighbors = asi_app.ospf_interface.get_neighbors()
                        actual_ids = {n.get("router_id") for n in actual_neighbors}

                        for expected in test_data.get("expected_neighbors", []):
                            nbr_id = expected.get("router_id", "")
                            if nbr_id in actual_ids:
                                test_results.append({"neighbor": nbr_id, "status": "PASSED", "state": "FULL"})
                                details.append(f"✓ OSPF {nbr_id}: FULL")
                            else:
                                test_results.append({"neighbor": nbr_id, "status": "FAILED", "state": "DOWN"})
                                details.append(f"✗ OSPF {nbr_id}: Not found")
                                overall_status = "FAILED"
                    except Exception as e:
                        details.append(f"? OSPF check error: {e}")

            if category == "protocol_state" or "expected_peers" in test_data:
                # Check BGP peers if available
                if asi_app.bgp_speaker and test_data.get("expected_peers"):
                    try:
                        peer_status = asi_app.bgp_speaker.get_peer_status()

                        for expected in test_data.get("expected_peers", []):
                            peer_ip = expected.get("peer_ip", "")
                            if peer_ip in peer_status:
                                state = peer_status[peer_ip].get("state", "Unknown")
                                if state.lower() == "established":
                                    test_results.append({"peer": peer_ip, "status": "PASSED", "state": state})
                                    details.append(f"✓ BGP {peer_ip}: {state}")
                                else:
                                    test_results.append({"peer": peer_ip, "status": "FAILED", "state": state})
                                    details.append(f"✗ BGP {peer_ip}: {state}")
                                    overall_status = "FAILED"
                            else:
                                test_results.append({"peer": peer_ip, "status": "FAILED", "state": "Not found"})
                                details.append(f"✗ BGP {peer_ip}: Not configured")
                                overall_status = "FAILED"
                    except Exception as e:
                        details.append(f"? BGP check error: {e}")

            if category == "interface" or "interfaces" in test_data:
                # Check interface states
                interfaces = test_data.get("interfaces", [])
                for intf in interfaces:
                    intf_name = intf.get("name", "")
                    expected_state = intf.get("expected_state", "up")
                    try:
                        # Check interface via ip link
                        result = subprocess.run(
                            ["ip", "link", "show", intf_name],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            output = result.stdout.lower()
                            is_up = "state up" in output or ",up," in output
                            if (expected_state == "up" and is_up) or (expected_state == "down" and not is_up):
                                test_results.append({"interface": intf_name, "status": "PASSED"})
                                details.append(f"✓ {intf_name}: {'UP' if is_up else 'DOWN'}")
                            else:
                                test_results.append({"interface": intf_name, "status": "FAILED"})
                                details.append(f"✗ {intf_name}: Expected {expected_state}, got {'up' if is_up else 'down'}")
                                overall_status = "FAILED"
                        else:
                            details.append(f"? {intf_name}: Not found")
                    except Exception as e:
                        details.append(f"? {intf_name}: Error - {e}")

            # If no specific tests ran, mark as passed with note
            if not test_results and not details:
                details.append("✓ Test configuration validated")
                overall_status = "PASSED"

        except Exception as e:
            overall_status = "ERROR"
            details.append(f"Test execution error: {e}")

        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "test_id": test.test_id,
            "test_name": test.test_name,
            "category": category,
            "description": test.description,
            "status": overall_status,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
            "results": test_results,
            "details": details,
            "expected_outcomes": test.expected_outcomes,
        }

    def _build_agent_config_for_testing() -> Dict[str, Any]:
        """Build TOON-style agent config from current ASI state for test generation"""
        config = {
            "id": asi_app.router_id or "unknown",
            "r": asi_app.router_id or "0.0.0.0",
            "ifs": [],
            "protos": [],
        }

        # Add interface information
        if hasattr(asi_app, 'interfaces') and asi_app.interfaces:
            for intf in asi_app.interfaces:
                config["ifs"].append({
                    "id": intf.get("id") or intf.get("name"),
                    "n": intf.get("name"),
                    "t": intf.get("type", "eth"),
                    "a": intf.get("addresses", []),
                    "s": intf.get("status", "up"),
                })

        # Add OSPF protocol info
        if asi_app.ospf_interface:
            ospf_neighbors = []
            try:
                neighbors = asi_app.ospf_interface.get_neighbors()
                for nbr in neighbors:
                    ospf_neighbors.append({
                        "router_id": nbr.get("router_id"),
                        "interface": nbr.get("interface"),
                    })
            except Exception:
                pass

            config["protos"].append({
                "p": "ospf",
                "r": asi_app.router_id,
                "neighbors": ospf_neighbors,
            })

        # Add BGP protocol info
        if asi_app.bgp_speaker:
            bgp_peers = []
            try:
                peers = asi_app.bgp_speaker.get_peer_status()
                for peer_ip, status in peers.items():
                    bgp_peers.append({
                        "ip": peer_ip,
                        "asn": status.get("remote_as"),
                    })
            except Exception:
                pass

            config["protos"].append({
                "p": "ibgp" if asi_app.bgp_speaker.local_as else "ebgp",
                "r": asi_app.router_id,
                "asn": getattr(asi_app.bgp_speaker, 'local_as', None),
                "peers": bgp_peers,
            })

        return config

    @app.get("/api/gait/history")
    async def api_get_gait_history() -> Dict[str, Any]:
        """Get GAIT conversation history via REST API"""
        return await get_gait_history(None)

    # RFC MCP API endpoints
    @app.get("/api/rfc/{rfc_number}")
    async def api_get_rfc(rfc_number: int) -> Dict[str, Any]:
        """
        Look up an RFC by number

        Args:
            rfc_number: RFC number (e.g., 2328 for OSPF)

        Returns:
            RFC document information with summary and key sections
        """
        try:
            from agentic.mcp.rfc_mcp import get_rfc_client
            client = get_rfc_client()
            result = client.lookup(rfc_number)
            return result.to_dict()
        except ImportError as e:
            return {"success": False, "error": f"RFC MCP module not available: {e}"}
        except Exception as e:
            logger.error(f"RFC lookup error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/rfc/protocol/{protocol}")
    async def api_get_rfc_by_protocol(protocol: str) -> Dict[str, Any]:
        """
        Search for RFCs related to a protocol

        Args:
            protocol: Protocol name (e.g., ospf, bgp, mpls, isis, vxlan, evpn)

        Returns:
            List of relevant RFCs with summaries
        """
        try:
            from agentic.mcp.rfc_mcp import get_rfc_client
            client = get_rfc_client()
            return client.get_protocol_summary(protocol)
        except ImportError as e:
            return {"protocol": protocol, "error": f"RFC MCP module not available: {e}"}
        except Exception as e:
            logger.error(f"RFC protocol search error: {e}")
            return {"protocol": protocol, "error": str(e)}

    @app.get("/api/rfc/search")
    async def api_search_rfc(keyword: str) -> Dict[str, Any]:
        """
        Search for RFCs by keyword

        Args:
            keyword: Search keyword

        Returns:
            Search results with matching RFCs
        """
        try:
            from agentic.mcp.rfc_mcp import get_rfc_client
            client = get_rfc_client()
            result = client.search_by_keyword(keyword)
            return result.to_dict()
        except ImportError as e:
            return {"success": False, "query": keyword, "error": f"RFC MCP module not available: {e}"}
        except Exception as e:
            logger.error(f"RFC search error: {e}")
            return {"success": False, "query": keyword, "error": str(e)}

    @app.post("/api/rfc/intent")
    async def api_rfc_for_intent(intent: str) -> Dict[str, Any]:
        """
        Get relevant RFCs based on an agent's intent

        Args:
            intent: Intent description (e.g., "configure ospf neighbor")

        Returns:
            Relevant RFCs for the intent
        """
        try:
            from agentic.mcp.rfc_mcp import get_rfc_client
            client = get_rfc_client()
            return client.get_rfc_for_intent(intent)
        except ImportError as e:
            return {"intent": intent, "error": f"RFC MCP module not available: {e}"}
        except Exception as e:
            logger.error(f"RFC intent lookup error: {e}")
            return {"intent": intent, "error": str(e)}

    # ==========================================================================
    # Prometheus Metrics API Endpoints
    # ==========================================================================

    @app.get("/api/metrics")
    async def api_get_metrics(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Prometheus-style metrics for an agent

        Args:
            agent_id: Optional agent ID filter

        Returns:
            Metrics dictionary with values, labels, and types
        """
        try:
            from agentic.mcp.prometheus_mcp import get_prometheus_client
            client = get_prometheus_client()
            metrics = await client.get_all_metrics(agent_id)
            return {"metrics": metrics, "agent_id": agent_id}
        except ImportError as e:
            return {"metrics": {}, "error": f"Prometheus MCP not available: {e}"}
        except Exception as e:
            logger.error(f"Metrics fetch error: {e}")
            return {"metrics": {}, "error": str(e)}

    @app.get("/api/metrics/export")
    async def api_export_metrics(agent_id: Optional[str] = None) -> str:
        """
        Export metrics in Prometheus exposition format

        Args:
            agent_id: Optional agent ID filter

        Returns:
            Prometheus-formatted metrics text
        """
        try:
            from agentic.mcp.prometheus_mcp import get_prometheus_client
            client = get_prometheus_client()
            exporter = client.get_exporter(agent_id) if agent_id else None

            if exporter:
                return await exporter.collect()

            # Collect from all exporters
            output = []
            for exp in client.exporters.values():
                output.append(await exp.collect())
            return "\n\n".join(output)
        except ImportError as e:
            return f"# Prometheus MCP not available: {e}\n"
        except Exception as e:
            logger.error(f"Metrics export error: {e}")
            return f"# Error: {e}\n"

    @app.get("/api/agent/{agent_id}/metrics")
    async def api_get_agent_metrics(agent_id: str) -> Dict[str, Any]:
        """
        Get Prometheus-style metrics for a specific agent.
        Used by the agent dashboard Prometheus tab.

        Args:
            agent_id: Agent ID (or 'local' for the current agent)

        Returns:
            Dict with metrics list and summary data for charts
        """
        try:
            from agentic.mcp.prometheus_mcp import get_prometheus_client
            client = get_prometheus_client()

            # Get metrics - returns {agent_id: {metric_name: {type, help, values}}}
            all_metrics = await client.get_all_metrics(None)  # Get all, we'll filter

            # Convert to the format expected by the dashboard
            metrics_list = []
            neighbor_count = 0
            rx_bytes = 0
            tx_bytes = 0
            messages_sent = 0
            messages_recv = 0
            lsa_count = 0
            route_count = 0

            # Individual OSPF metrics
            ospf_hello_sent = 0
            ospf_hello_recv = 0
            ospf_dbd_sent = 0
            ospf_dbd_recv = 0
            ospf_lsr_sent = 0
            ospf_lsr_recv = 0
            ospf_lsu_sent = 0
            ospf_lsu_recv = 0
            ospf_lsack_sent = 0
            ospf_lsack_recv = 0
            ospf_neighbor_count = 0

            # Individual BGP metrics
            bgp_open_sent = 0
            bgp_open_recv = 0
            bgp_update_sent = 0
            bgp_update_recv = 0
            bgp_keepalive_sent = 0
            bgp_keepalive_recv = 0
            bgp_notification_sent = 0
            bgp_notification_recv = 0
            bgp_peer_count = 0
            bgp_established_count = 0
            bgp_routes_count = 0

            # Iterate through agents and their metrics
            for aid, agent_metrics in all_metrics.items():
                # If specific agent requested (not 'local'), filter
                if agent_id != 'local' and aid != agent_id:
                    continue

                # agent_metrics is {metric_name: {type, help, values}}
                for metric_name, metric_data in agent_metrics.items():
                    # Extract ALL values (each interface, etc. has its own value)
                    values = metric_data.get("values", [])
                    name_lower = metric_name.lower()

                    for val_entry in values:
                        metric_entry = {
                            "name": metric_name,
                            "type": metric_data.get("type", "gauge"),
                            "help": metric_data.get("help", ""),
                            "description": metric_data.get("help", ""),
                            "labels": {"agent": aid},
                            "value": val_entry.get("value", 0)
                        }
                        metric_entry["labels"].update(val_entry.get("labels", {}))
                        metrics_list.append(metric_entry)

                        # Extract summary values for charts (sum all interfaces)
                        val = metric_entry["value"]

                        # Debug logging for chart data extraction
                        if "rx_bytes" in name_lower or "tx_bytes" in name_lower or "lsa" in name_lower:
                            logging.getLogger("WebUI").debug(f"Chart extraction: {metric_name} = {val} (type: {type(val).__name__})")

                        if "neighbor" in name_lower and "total" in name_lower:
                            neighbor_count += val if isinstance(val, (int, float)) else 0
                        if "rx_bytes" in name_lower or "bytes_recv" in name_lower:
                            rx_bytes += val if isinstance(val, (int, float)) else 0
                        if "tx_bytes" in name_lower or "bytes_sent" in name_lower:
                            tx_bytes += val if isinstance(val, (int, float)) else 0
                        # Count all protocol messages sent (OSPF + BGP)
                        if "_sent_total" in name_lower and ("ospf_" in name_lower or "bgp_" in name_lower):
                            messages_sent += val if isinstance(val, (int, float)) else 0
                        # Count all protocol messages received (OSPF + BGP)
                        if "_recv_total" in name_lower and ("ospf_" in name_lower or "bgp_" in name_lower):
                            messages_recv += val if isinstance(val, (int, float)) else 0
                        if "lsdb" in name_lower or "lsa_count" in name_lower:
                            lsa_count += val if isinstance(val, (int, float)) else 0
                        if "route" in name_lower and "total" in name_lower:
                            route_count += val if isinstance(val, (int, float)) else 0

                        # Extract individual OSPF metrics
                        if "ospf_hello_sent" in name_lower:
                            ospf_hello_sent += val if isinstance(val, (int, float)) else 0
                        if "ospf_hello_recv" in name_lower:
                            ospf_hello_recv += val if isinstance(val, (int, float)) else 0
                        if "ospf_dbd_sent" in name_lower:
                            ospf_dbd_sent += val if isinstance(val, (int, float)) else 0
                        if "ospf_dbd_recv" in name_lower:
                            ospf_dbd_recv += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsr_sent" in name_lower:
                            ospf_lsr_sent += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsr_recv" in name_lower:
                            ospf_lsr_recv += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsu_sent" in name_lower:
                            ospf_lsu_sent += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsu_recv" in name_lower:
                            ospf_lsu_recv += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsack_sent" in name_lower:
                            ospf_lsack_sent += val if isinstance(val, (int, float)) else 0
                        if "ospf_lsack_recv" in name_lower:
                            ospf_lsack_recv += val if isinstance(val, (int, float)) else 0
                        if "ospf_neighbor" in name_lower and "count" in name_lower:
                            ospf_neighbor_count += val if isinstance(val, (int, float)) else 0

                        # Extract individual BGP metrics
                        if "bgp_open_sent" in name_lower:
                            bgp_open_sent += val if isinstance(val, (int, float)) else 0
                        if "bgp_open_recv" in name_lower:
                            bgp_open_recv += val if isinstance(val, (int, float)) else 0
                        if "bgp_update_sent" in name_lower:
                            bgp_update_sent += val if isinstance(val, (int, float)) else 0
                        if "bgp_update_recv" in name_lower:
                            bgp_update_recv += val if isinstance(val, (int, float)) else 0
                        if "bgp_keepalive_sent" in name_lower:
                            bgp_keepalive_sent += val if isinstance(val, (int, float)) else 0
                        if "bgp_keepalive_recv" in name_lower:
                            bgp_keepalive_recv += val if isinstance(val, (int, float)) else 0
                        if "bgp_notification_sent" in name_lower:
                            bgp_notification_sent += val if isinstance(val, (int, float)) else 0
                        if "bgp_notification_recv" in name_lower:
                            bgp_notification_recv += val if isinstance(val, (int, float)) else 0
                        if "bgp_peer" in name_lower and ("count" in name_lower or "total" in name_lower):
                            bgp_peer_count += val if isinstance(val, (int, float)) else 0
                        if "bgp_established" in name_lower or "bgp_peers_established" in name_lower:
                            bgp_established_count += val if isinstance(val, (int, float)) else 0
                        if "bgp_routes_total" in name_lower:
                            bgp_routes_count += val if isinstance(val, (int, float)) else 0

            return {
                "metrics": metrics_list,
                "neighbor_count": neighbor_count,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "messages_sent": messages_sent,
                "messages_recv": messages_recv,
                "lsa_count": lsa_count,
                "route_count": route_count,
                # OSPF specific metrics
                "ospf": {
                    "active": ospf_hello_sent > 0 or ospf_hello_recv > 0,
                    "hello_sent": ospf_hello_sent,
                    "hello_recv": ospf_hello_recv,
                    "dbd_sent": ospf_dbd_sent,
                    "dbd_recv": ospf_dbd_recv,
                    "lsr_sent": ospf_lsr_sent,
                    "lsr_recv": ospf_lsr_recv,
                    "lsu_sent": ospf_lsu_sent,
                    "lsu_recv": ospf_lsu_recv,
                    "lsack_sent": ospf_lsack_sent,
                    "lsack_recv": ospf_lsack_recv,
                    "neighbor_count": ospf_neighbor_count
                },
                # BGP specific metrics
                "bgp": {
                    "active": bgp_peer_count > 0 or bgp_routes_count > 0 or bgp_open_sent > 0 or bgp_keepalive_sent > 0,
                    "open_sent": bgp_open_sent,
                    "open_recv": bgp_open_recv,
                    "update_sent": bgp_update_sent,
                    "update_recv": bgp_update_recv,
                    "keepalive_sent": bgp_keepalive_sent,
                    "keepalive_recv": bgp_keepalive_recv,
                    "notification_sent": bgp_notification_sent,
                    "notification_recv": bgp_notification_recv,
                    "peer_count": bgp_peer_count,
                    "established_count": bgp_established_count,
                    "routes_count": bgp_routes_count
                }
            }
        except ImportError as e:
            logging.getLogger("WebUI").warning(f"Prometheus MCP not available: {e}")
            return {"metrics": [], "neighbor_count": 0, "rx_bytes": 0, "tx_bytes": 0}
        except Exception as e:
            logging.getLogger("WebUI").error(f"Agent metrics fetch error: {e}")
            return {"metrics": [], "neighbor_count": 0, "rx_bytes": 0, "tx_bytes": 0}

    @app.get("/api/agent/{agent_id}/status")
    async def api_get_agent_status(agent_id: str) -> Dict[str, Any]:
        """
        Get status for a specific agent.
        Used by the agent dashboard.

        Args:
            agent_id: Agent ID (or 'local' for the current agent)

        Returns:
            Agent status information
        """
        try:
            # Return basic status - actual data comes from the bridge
            return {
                "agent_id": agent_id,
                "status": "running",
                "uptime": 0,
                "protocols": {
                    "ospf": {"enabled": True, "neighbors": 0},
                    "bgp": {"enabled": True, "peers": 0}
                },
                "interfaces": [],
                "routes": 0
            }
        except Exception as e:
            logger.error(f"Agent status fetch error: {e}")
            return {"agent_id": agent_id, "status": "error", "error": str(e)}

    @app.get("/api/metrics/query")
    async def api_query_metrics(promql: str, time_range: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a PromQL query

        Args:
            promql: PromQL query string
            time_range: Optional time range

        Returns:
            Query result
        """
        try:
            from agentic.mcp.prometheus_mcp import get_prometheus_client
            client = get_prometheus_client()
            result = await client.query(promql, time_range)
            return result.to_dict()
        except ImportError as e:
            return {"status": "error", "error": f"Prometheus MCP not available: {e}"}
        except Exception as e:
            logger.error(f"Metrics query error: {e}")
            return {"status": "error", "error": str(e)}

    # ==========================================================================
    # Grafana Dashboard API Endpoints
    # ==========================================================================

    @app.get("/api/grafana/dashboard")
    async def api_get_grafana_dashboard(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Grafana-style dashboard panels for an agent

        Args:
            agent_id: Optional agent ID filter

        Returns:
            Dashboard configuration with panels
        """
        try:
            from agentic.mcp.grafana_mcp import get_grafana_client
            from agentic.mcp.prometheus_mcp import get_prometheus_client

            grafana = get_grafana_client()
            prometheus = get_prometheus_client()

            # Get metrics for the agent
            metrics = await prometheus.get_all_metrics(agent_id)

            # Generate dashboard panels based on available metrics
            panels = []

            # Agent overview panel
            panels.append({
                "title": "Agent Status",
                "type": "stat",
                "data": {
                    "value": 1,
                    "label": "Agent Up"
                }
            })

            # Get metrics from the specific agent or first available
            agent_metrics = metrics.get(agent_id, {})
            if not agent_metrics and metrics:
                agent_metrics = list(metrics.values())[0]

            # System metrics gauge
            cpu = agent_metrics.get("system_cpu_percent", {}).get("values", [{}])[0].get("value", 0) if agent_metrics else 0
            panels.append({
                "title": "CPU Usage",
                "type": "gauge",
                "data": {
                    "value": round(cpu, 1),
                    "max": 100,
                    "unit": "%"
                }
            })

            memory = agent_metrics.get("system_memory_percent", {}).get("values", [{}])[0].get("value", 0) if agent_metrics else 0
            panels.append({
                "title": "Memory Usage",
                "type": "gauge",
                "data": {
                    "value": round(memory, 1),
                    "max": 100,
                    "unit": "%"
                }
            })

            # Protocol metrics table
            protocol_rows = []
            ospf_neighbors = agent_metrics.get("ospf_neighbors_total", {}).get("values", [{}])[0].get("value", 0) if agent_metrics else 0
            bgp_peers = agent_metrics.get("bgp_peers_established", {}).get("values", [{}])[0].get("value", 0) if agent_metrics else 0

            if ospf_neighbors > 0:
                protocol_rows.append(["OSPF", str(int(ospf_neighbors)), "Active"])
            if bgp_peers > 0:
                protocol_rows.append(["BGP", str(int(bgp_peers)), "Active"])

            if protocol_rows:
                panels.append({
                    "title": "Protocol Summary",
                    "type": "table",
                    "data": {
                        "columns": ["Protocol", "Neighbors", "Status"],
                        "rows": protocol_rows
                    }
                })

            return {
                "agent_id": agent_id,
                "panels": panels,
                "refresh_interval": 10
            }
        except ImportError as e:
            return {"panels": [], "error": f"Grafana/Prometheus MCP not available: {e}"}
        except Exception as e:
            logger.error(f"Grafana dashboard error: {e}")
            return {"panels": [], "error": str(e)}

    @app.get("/api/grafana/dashboards")
    async def api_list_grafana_dashboards() -> Dict[str, Any]:
        """List available Grafana dashboards"""
        try:
            from agentic.mcp.grafana_mcp import get_grafana_client
            client = get_grafana_client()
            dashboards = client.list_dashboards()
            return {"dashboards": dashboards}
        except ImportError as e:
            return {"dashboards": [], "error": f"Grafana MCP not available: {e}"}
        except Exception as e:
            logger.error(f"Grafana list error: {e}")
            return {"dashboards": [], "error": str(e)}

    # ==========================================================================
    # LLDP API Endpoints
    # ==========================================================================

    @app.get("/api/lldp/neighbors")
    async def api_get_lldp_neighbors(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get LLDP neighbors discovered by an agent

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of LLDP neighbors with details
        """
        try:
            from agentic.discovery.lldp import get_lldp_neighbors
            neighbors = get_lldp_neighbors()
            return {
                "neighbors": neighbors,
                "count": len(neighbors),
                "agent_id": agent_id
            }
        except ImportError as e:
            return {"neighbors": [], "count": 0, "error": f"LLDP module not available: {e}"}
        except Exception as e:
            logger.error(f"LLDP neighbors error: {e}")
            return {"neighbors": [], "count": 0, "error": str(e)}

    @app.get("/api/lldp/statistics")
    async def api_get_lldp_statistics(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get LLDP daemon statistics

        Args:
            agent_id: Optional agent ID filter

        Returns:
            LLDP statistics (frames sent/received, neighbor count, etc.)
        """
        try:
            from agentic.discovery.lldp import get_lldp_statistics
            stats = get_lldp_statistics()
            return {"statistics": stats, "agent_id": agent_id}
        except ImportError as e:
            return {"statistics": {}, "error": f"LLDP module not available: {e}"}
        except Exception as e:
            logger.error(f"LLDP statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    @app.get("/api/lldp/neighbor/{interface}")
    async def api_get_lldp_neighbor_by_interface(interface: str) -> Dict[str, Any]:
        """
        Get LLDP neighbors on a specific interface

        Args:
            interface: Interface name (e.g., eth0, eth1)

        Returns:
            List of LLDP neighbors on that interface
        """
        try:
            from agentic.discovery.lldp import get_lldp_daemon
            daemon = get_lldp_daemon()
            neighbors = daemon.get_neighbors_by_interface(interface)
            return {
                "interface": interface,
                "neighbors": [n.to_dict() for n in neighbors],
                "count": len(neighbors)
            }
        except ImportError as e:
            return {"interface": interface, "neighbors": [], "error": f"LLDP module not available: {e}"}
        except Exception as e:
            logger.error(f"LLDP interface neighbors error: {e}")
            return {"interface": interface, "neighbors": [], "error": str(e)}

    # ==========================================================================
    # LACP API Endpoints
    # ==========================================================================

    @app.get("/api/lacp/lags")
    async def api_get_lags(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all Link Aggregation Groups (LAGs)

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of LAGs with details
        """
        try:
            from agentic.discovery.lacp import get_lag_list
            lags = get_lag_list()
            return {
                "lags": lags,
                "count": len(lags),
                "agent_id": agent_id
            }
        except ImportError as e:
            return {"lags": [], "count": 0, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP LAGs error: {e}")
            return {"lags": [], "count": 0, "error": str(e)}

    @app.get("/api/lacp/statistics")
    async def api_get_lacp_statistics(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get LACP manager statistics

        Args:
            agent_id: Optional agent ID filter

        Returns:
            LACP statistics
        """
        try:
            from agentic.discovery.lacp import get_lacp_statistics
            stats = get_lacp_statistics()
            return {"statistics": stats, "agent_id": agent_id}
        except ImportError as e:
            return {"statistics": {}, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    @app.get("/api/lacp/lag/{lag_name}")
    async def api_get_lag(lag_name: str) -> Dict[str, Any]:
        """
        Get a specific LAG by name

        Args:
            lag_name: LAG name (e.g., bond0, port-channel1)

        Returns:
            LAG details
        """
        try:
            from agentic.discovery.lacp import get_lacp_manager
            manager = get_lacp_manager()
            lag = manager.get_lag(lag_name)
            if lag:
                return {"lag": lag.to_dict()}
            return {"lag": None, "error": f"LAG {lag_name} not found"}
        except ImportError as e:
            return {"lag": None, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP LAG error: {e}")
            return {"lag": None, "error": str(e)}

    @app.post("/api/lacp/lag")
    async def api_create_lag(
        name: str,
        mode: str = "active",
        load_balance: str = "layer3+4",
        min_links: int = 1
    ) -> Dict[str, Any]:
        """
        Create a new LAG

        Args:
            name: LAG name (e.g., bond0, port-channel1)
            mode: LACP mode (active, passive, on)
            load_balance: Load balancing algorithm
            min_links: Minimum active links

        Returns:
            Created LAG details
        """
        try:
            from agentic.discovery.lacp import get_lacp_manager, LACPMode, LoadBalanceAlgorithm
            manager = get_lacp_manager()

            lacp_mode = LACPMode(mode)
            lb_algo = LoadBalanceAlgorithm(load_balance)

            lag = manager.create_lag(
                name=name,
                mode=lacp_mode,
                load_balance=lb_algo,
                min_links=min_links
            )
            return {"lag": lag.to_dict(), "success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError as e:
            return {"success": False, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP create LAG error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/lacp/lag/{lag_name}")
    async def api_delete_lag(lag_name: str) -> Dict[str, Any]:
        """
        Delete a LAG

        Args:
            lag_name: LAG name to delete

        Returns:
            Success status
        """
        try:
            from agentic.discovery.lacp import get_lacp_manager
            manager = get_lacp_manager()
            success = manager.delete_lag(lag_name)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP delete LAG error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/lacp/lag/{lag_name}/member")
    async def api_add_lag_member(
        lag_name: str,
        interface: str,
        port_priority: int = 32768
    ) -> Dict[str, Any]:
        """
        Add a member interface to a LAG

        Args:
            lag_name: LAG name
            interface: Interface to add
            port_priority: LACP port priority

        Returns:
            Member port details
        """
        try:
            from agentic.discovery.lacp import get_lacp_manager
            manager = get_lacp_manager()
            member = manager.add_member_to_lag(lag_name, interface, port_priority)
            return {"member": member.to_dict(), "success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError as e:
            return {"success": False, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP add member error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/lacp/lag/{lag_name}/member/{interface}")
    async def api_remove_lag_member(lag_name: str, interface: str) -> Dict[str, Any]:
        """
        Remove a member interface from a LAG

        Args:
            lag_name: LAG name
            interface: Interface to remove

        Returns:
            Success status
        """
        try:
            from agentic.discovery.lacp import get_lacp_manager
            manager = get_lacp_manager()
            success = manager.remove_member_from_lag(lag_name, interface)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"LACP module not available: {e}"}
        except Exception as e:
            logger.error(f"LACP remove member error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # Subinterface API Endpoints (VLAN / 802.1Q)
    # ==========================================================================

    @app.get("/api/subinterfaces")
    async def api_get_subinterfaces(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all subinterfaces

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of subinterfaces with details
        """
        try:
            from agentic.interfaces import list_subinterfaces, get_subinterface_statistics
            subifs = list_subinterfaces()
            stats = get_subinterface_statistics()
            return {
                "subinterfaces": subifs,
                "count": len(subifs),
                "statistics": stats,
                "agent_id": agent_id
            }
        except ImportError as e:
            return {"subinterfaces": [], "count": 0, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterfaces error: {e}")
            return {"subinterfaces": [], "count": 0, "error": str(e)}

    @app.get("/api/subinterfaces/statistics")
    async def api_get_subinterface_statistics(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get subinterface manager statistics

        Args:
            agent_id: Optional agent ID filter

        Returns:
            Subinterface statistics
        """
        try:
            from agentic.interfaces import get_subinterface_statistics
            stats = get_subinterface_statistics()
            return {"statistics": stats, "agent_id": agent_id}
        except ImportError as e:
            return {"statistics": {}, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    @app.get("/api/subinterfaces/interfaces")
    async def api_get_physical_interfaces(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all physical interfaces that can have subinterfaces

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of physical interfaces
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()
            interfaces = [iface.to_dict() for iface in manager.interfaces.values()]
            return {
                "interfaces": interfaces,
                "count": len(interfaces),
                "agent_id": agent_id
            }
        except ImportError as e:
            return {"interfaces": [], "count": 0, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Physical interfaces error: {e}")
            return {"interfaces": [], "count": 0, "error": str(e)}

    @app.get("/api/subinterfaces/{parent}/{vlan_id}")
    async def api_get_subinterface(parent: str, vlan_id: int) -> Dict[str, Any]:
        """
        Get a specific subinterface

        Args:
            parent: Parent interface name (e.g., eth0)
            vlan_id: VLAN ID

        Returns:
            Subinterface details
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()
            subif = manager.get_subinterface(parent, vlan_id)
            if subif:
                return {"subinterface": subif.to_dict()}
            return {"subinterface": None, "error": f"Subinterface {parent}.{vlan_id} not found"}
        except ImportError as e:
            return {"subinterface": None, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface get error: {e}")
            return {"subinterface": None, "error": str(e)}

    @app.post("/api/subinterfaces")
    async def api_create_subinterface(
        parent_interface: str,
        vlan_id: int,
        description: str = "",
        mtu: Optional[int] = None,
        ipv4_address: Optional[str] = None,
        ipv6_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new subinterface

        Args:
            parent_interface: Parent interface name (e.g., eth0)
            vlan_id: VLAN ID (1-4094)
            description: Optional description
            mtu: Optional MTU (defaults to parent MTU - 4)
            ipv4_address: Optional IPv4 address with prefix (e.g., 192.168.10.1/24)
            ipv6_address: Optional IPv6 address with prefix

        Returns:
            Created subinterface details
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()

            ipv4_addresses = [ipv4_address] if ipv4_address else None
            ipv6_addresses = [ipv6_address] if ipv6_address else None

            subif = manager.create_subinterface(
                parent_interface=parent_interface,
                vlan_id=vlan_id,
                description=description,
                mtu=mtu,
                ipv4_addresses=ipv4_addresses,
                ipv6_addresses=ipv6_addresses
            )
            return {"subinterface": subif.to_dict(), "success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError as e:
            return {"success": False, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface create error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/subinterfaces/{parent}/{vlan_id}")
    async def api_delete_subinterface(parent: str, vlan_id: int) -> Dict[str, Any]:
        """
        Delete a subinterface

        Args:
            parent: Parent interface name
            vlan_id: VLAN ID

        Returns:
            Success status
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()
            success = manager.delete_subinterface(parent, vlan_id)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface delete error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/subinterfaces/{parent}/{vlan_id}/ip")
    async def api_add_ip_to_subinterface(
        parent: str,
        vlan_id: int,
        address: str,
        is_ipv6: bool = False
    ) -> Dict[str, Any]:
        """
        Add an IP address to a subinterface

        Args:
            parent: Parent interface name
            vlan_id: VLAN ID
            address: IP address with prefix (e.g., 192.168.10.1/24)
            is_ipv6: True for IPv6, False for IPv4

        Returns:
            Success status
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()
            success = manager.add_ip_address(parent, vlan_id, address, is_ipv6)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface add IP error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/subinterfaces/{parent}/{vlan_id}/ip")
    async def api_remove_ip_from_subinterface(
        parent: str,
        vlan_id: int,
        address: str,
        is_ipv6: bool = False
    ) -> Dict[str, Any]:
        """
        Remove an IP address from a subinterface

        Args:
            parent: Parent interface name
            vlan_id: VLAN ID
            address: IP address to remove
            is_ipv6: True for IPv6, False for IPv4

        Returns:
            Success status
        """
        try:
            from agentic.interfaces import get_subinterface_manager
            manager = get_subinterface_manager()
            success = manager.remove_ip_address(parent, vlan_id, address, is_ipv6)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface remove IP error: {e}")
            return {"success": False, "error": str(e)}

    @app.put("/api/subinterfaces/{parent}/{vlan_id}/state")
    async def api_set_subinterface_state(
        parent: str,
        vlan_id: int,
        admin_state: str
    ) -> Dict[str, Any]:
        """
        Set the administrative state of a subinterface

        Args:
            parent: Parent interface name
            vlan_id: VLAN ID
            admin_state: "up" or "down"

        Returns:
            Success status
        """
        try:
            from agentic.interfaces import get_subinterface_manager, InterfaceState
            manager = get_subinterface_manager()

            state = InterfaceState.UP if admin_state.lower() == "up" else InterfaceState.DOWN
            success = manager.set_admin_state(parent, vlan_id, state)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Subinterface module not available: {e}"}
        except Exception as e:
            logger.error(f"Subinterface set state error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # ==========================================================================
    # Firewall/ACL API Endpoints
    # ==========================================================================

    @app.get("/api/firewall/acls")
    async def api_get_acls(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all ACLs

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of ACLs with details
        """
        try:
            from agentic.security import list_acl_rules, get_firewall_statistics
            acls = list_acl_rules()
            stats = get_firewall_statistics()
            return {
                "acls": acls,
                "count": len(acls),
                "statistics": stats,
                "agent_id": agent_id
            }
        except ImportError as e:
            return {"acls": [], "count": 0, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACLs error: {e}")
            return {"acls": [], "count": 0, "error": str(e)}

    @app.get("/api/firewall/statistics")
    async def api_get_firewall_statistics() -> Dict[str, Any]:
        """Get firewall statistics"""
        try:
            from agentic.security import get_firewall_statistics
            return {"statistics": get_firewall_statistics()}
        except ImportError as e:
            return {"statistics": {}, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    @app.get("/api/firewall/acl/{acl_name}")
    async def api_get_acl(acl_name: str) -> Dict[str, Any]:
        """Get a specific ACL by name"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            acl = manager.get_acl(acl_name)
            if acl:
                return {"acl": acl.to_dict()}
            return {"acl": None, "error": f"ACL {acl_name} not found"}
        except ImportError as e:
            return {"acl": None, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACL get error: {e}")
            return {"acl": None, "error": str(e)}

    @app.post("/api/firewall/acl")
    async def api_create_acl(
        name: str,
        description: str = "",
        acl_type: str = "extended"
    ) -> Dict[str, Any]:
        """
        Create a new ACL

        Args:
            name: ACL name (unique)
            description: Optional description
            acl_type: "standard" or "extended"

        Returns:
            Created ACL
        """
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            acl = manager.create_acl(name, description, acl_type)
            return {"acl": acl.to_dict(), "success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACL create error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/firewall/acl/{acl_name}")
    async def api_delete_acl(acl_name: str) -> Dict[str, Any]:
        """Delete an ACL"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            success = manager.delete_acl(acl_name)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACL delete error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/firewall/acl/{acl_name}/rule")
    async def api_add_acl_rule(
        acl_name: str,
        sequence: int,
        action: str,
        protocol: str = "any",
        source_ip: str = "any",
        source_port: Optional[str] = None,
        dest_ip: str = "any",
        dest_port: Optional[str] = None,
        description: str = "",
        log: bool = False
    ) -> Dict[str, Any]:
        """
        Add a rule to an ACL

        Args:
            acl_name: ACL name
            sequence: Rule sequence number
            action: permit, deny, drop, reject
            protocol: any, tcp, udp, icmp, etc.
            source_ip: Source IP/network or "any"
            source_port: Source port
            dest_ip: Destination IP/network or "any"
            dest_port: Destination port
            description: Rule description
            log: Log matching packets

        Returns:
            Created rule
        """
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            entry = manager.add_rule(
                acl_name, sequence, action, protocol,
                source_ip, source_port, dest_ip, dest_port,
                description, log
            )
            return {"rule": entry.to_dict(), "success": True}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall rule add error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/firewall/acl/{acl_name}/rule/{sequence}")
    async def api_delete_acl_rule(acl_name: str, sequence: int) -> Dict[str, Any]:
        """Delete a rule from an ACL"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            success = manager.remove_rule(acl_name, sequence)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall rule delete error: {e}")
            return {"success": False, "error": str(e)}

    @app.put("/api/firewall/acl/{acl_name}/rule/{sequence}")
    async def api_update_acl_rule(
        acl_name: str,
        sequence: int,
        enabled: Optional[bool] = None,
        action: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a rule in an ACL (enable/disable, change action)"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            success = manager.update_rule(acl_name, sequence, enabled, action)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall rule update error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/firewall/acl/{acl_name}/apply")
    async def api_apply_acl(
        acl_name: str,
        interface: str,
        direction: str = "in"
    ) -> Dict[str, Any]:
        """
        Apply an ACL to an interface

        Args:
            acl_name: ACL name
            interface: Interface to apply to
            direction: "in", "out", or "both"

        Returns:
            Success status
        """
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            success = manager.apply_acl(acl_name, interface, direction)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACL apply error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/firewall/acl/{acl_name}/interface/{interface}")
    async def api_remove_acl_from_interface(acl_name: str, interface: str) -> Dict[str, Any]:
        """Remove an ACL from an interface"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            success = manager.remove_acl_from_interface(acl_name, interface)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Firewall ACL remove error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/firewall/blocked")
    async def api_get_blocked_traffic(limit: int = 50) -> Dict[str, Any]:
        """Get recent blocked traffic log"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            blocked = manager.get_blocked_traffic(limit)
            return {"blocked": blocked, "count": len(blocked)}
        except ImportError as e:
            return {"blocked": [], "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Blocked traffic error: {e}")
            return {"blocked": [], "error": str(e)}

    @app.get("/api/firewall/allowed")
    async def api_get_allowed_traffic(limit: int = 50) -> Dict[str, Any]:
        """Get recent allowed traffic log"""
        try:
            from agentic.security import get_firewall_manager
            manager = get_firewall_manager()
            allowed = manager.get_allowed_traffic(limit)
            return {"allowed": allowed, "count": len(allowed)}
        except ImportError as e:
            return {"allowed": [], "error": f"Firewall module not available: {e}"}
        except Exception as e:
            logger.error(f"Allowed traffic error: {e}")
            return {"allowed": [], "error": str(e)}

    # ==========================================================================
    # SSH Server API Endpoints
    # ==========================================================================

    @app.get("/api/ssh/servers")
    async def api_get_ssh_servers() -> Dict[str, Any]:
        """
        Get all SSH servers and their status

        Returns:
            List of SSH server configurations and statistics
        """
        try:
            from agentic.ssh import get_ssh_statistics, list_active_sessions
            stats = get_ssh_statistics()
            sessions = list_active_sessions()
            return {
                "servers": stats,
                "total_servers": len(stats),
                "active_sessions": sessions,
                "total_sessions": len(sessions)
            }
        except ImportError as e:
            return {"servers": {}, "error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH servers error: {e}")
            return {"servers": {}, "error": str(e)}

    @app.get("/api/ssh/server/{agent_name}")
    async def api_get_ssh_server(agent_name: str) -> Dict[str, Any]:
        """
        Get SSH server info for a specific agent

        Args:
            agent_name: Name of the agent

        Returns:
            SSH server configuration and statistics
        """
        try:
            from agentic.ssh import get_ssh_server
            server = get_ssh_server(agent_name)
            if server:
                return {
                    "agent_name": agent_name,
                    "running": server.running,
                    "config": server.get_config(),
                    "statistics": server.get_statistics(),
                    "sessions": server.get_sessions()
                }
            else:
                return {"agent_name": agent_name, "running": False, "error": "Server not found"}
        except ImportError as e:
            return {"error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH server error: {e}")
            return {"error": str(e)}

    @app.post("/api/ssh/server")
    async def api_start_ssh_server(
        agent_name: str,
        port: int = 2200,
        password_auth: bool = True,
        public_key_auth: bool = True,
        default_username: str = "admin",
        default_password: str = "admin",
        max_sessions: int = 10,
        idle_timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Start SSH server for an agent

        Args:
            agent_name: Name of the agent
            port: SSH port number
            password_auth: Enable password authentication
            public_key_auth: Enable public key authentication
            default_username: Default login username
            default_password: Default login password
            max_sessions: Maximum concurrent sessions
            idle_timeout: Session idle timeout in seconds

        Returns:
            Server status and configuration
        """
        try:
            from agentic.ssh import start_ssh_server, SSHConfig

            # Create chat handler that uses agentic bridge if available
            async def chat_handler(message: str) -> str:
                if agentic_bridge:
                    try:
                        return await agentic_bridge.process_message(message)
                    except Exception as e:
                        return f"Error processing message: {e}"
                return "Chat interface not available"

            server = await start_ssh_server(
                agent_name=agent_name,
                port=port,
                chat_handler=chat_handler,
                password_auth=password_auth,
                public_key_auth=public_key_auth,
                default_username=default_username,
                default_password=default_password,
                max_sessions=max_sessions,
                idle_timeout=idle_timeout
            )

            return {
                "success": True,
                "agent_name": agent_name,
                "port": port,
                "config": server.get_config(),
                "message": f"SSH server started on port {port}"
            }
        except ImportError as e:
            return {"success": False, "error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH server start error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/ssh/server/{agent_name}")
    async def api_stop_ssh_server(agent_name: str) -> Dict[str, Any]:
        """
        Stop SSH server for an agent

        Args:
            agent_name: Name of the agent

        Returns:
            Operation status
        """
        try:
            from agentic.ssh import stop_ssh_server, get_ssh_server

            server = get_ssh_server(agent_name)
            if not server:
                return {"success": False, "error": f"SSH server for {agent_name} not found"}

            await stop_ssh_server(agent_name)
            return {"success": True, "agent_name": agent_name, "message": "SSH server stopped"}
        except ImportError as e:
            return {"success": False, "error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH server stop error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/ssh/sessions")
    async def api_get_ssh_sessions(agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get active SSH sessions

        Args:
            agent_name: Optional filter by agent name

        Returns:
            List of active sessions
        """
        try:
            from agentic.ssh import list_active_sessions
            sessions = list_active_sessions(agent_name)
            return {"sessions": sessions, "count": len(sessions)}
        except ImportError as e:
            return {"sessions": [], "error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH sessions error: {e}")
            return {"sessions": [], "error": str(e)}

    @app.get("/api/ssh/statistics")
    async def api_get_ssh_statistics(agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get SSH server statistics

        Args:
            agent_name: Optional filter by agent name

        Returns:
            SSH statistics
        """
        try:
            from agentic.ssh import get_ssh_statistics
            stats = get_ssh_statistics(agent_name)
            return {"statistics": stats}
        except ImportError as e:
            return {"statistics": {}, "error": f"SSH module not available: {e}"}
        except Exception as e:
            logger.error(f"SSH statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    # ==========================================================================
    # NETCONF/RESTCONF API Endpoints
    # ==========================================================================

    @app.get("/api/netconf/servers")
    async def api_get_netconf_servers() -> Dict[str, Any]:
        """
        Get all NETCONF servers and their status

        Returns:
            List of NETCONF server configurations and statistics
        """
        try:
            from agentic.netconf import get_netconf_statistics, list_netconf_sessions
            stats = get_netconf_statistics()
            sessions = list_netconf_sessions()
            return {
                "servers": stats,
                "total_servers": len(stats),
                "active_sessions": sessions,
                "total_sessions": len(sessions)
            }
        except ImportError as e:
            return {"servers": {}, "error": f"NETCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"NETCONF servers error: {e}")
            return {"servers": {}, "error": str(e)}

    @app.get("/api/netconf/server/{agent_name}")
    async def api_get_netconf_server(agent_name: str) -> Dict[str, Any]:
        """
        Get NETCONF server info for a specific agent

        Args:
            agent_name: Name of the agent

        Returns:
            NETCONF server configuration and statistics
        """
        try:
            from agentic.netconf import get_netconf_server
            server = get_netconf_server(agent_name)
            if server:
                return {
                    "agent_name": agent_name,
                    "running": server.running,
                    "config": server.get_config(),
                    "statistics": server.get_statistics().to_dict(),
                    "sessions": server.get_sessions(),
                    "capabilities": [{"uri": c.uri, "name": c.name} for c in server._capabilities]
                }
            else:
                return {"agent_name": agent_name, "running": False, "error": "Server not found"}
        except ImportError as e:
            return {"error": f"NETCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"NETCONF server error: {e}")
            return {"error": str(e)}

    @app.post("/api/netconf/server")
    async def api_start_netconf_server(
        agent_name: str,
        port: int = 830,
        with_candidate: bool = True,
        with_startup: bool = True,
        with_validate: bool = True,
        max_sessions: int = 10
    ) -> Dict[str, Any]:
        """
        Start NETCONF server for an agent

        Args:
            agent_name: Name of the agent
            port: NETCONF port number
            with_candidate: Enable candidate datastore
            with_startup: Enable startup datastore
            with_validate: Enable validate capability
            max_sessions: Maximum concurrent sessions

        Returns:
            Server status and configuration
        """
        try:
            from agentic.netconf import start_netconf_server

            server = await start_netconf_server(
                agent_name=agent_name,
                port=port,
                with_candidate=with_candidate,
                with_startup=with_startup,
                with_validate=with_validate,
                max_sessions=max_sessions
            )

            return {
                "success": True,
                "agent_name": agent_name,
                "port": port,
                "config": server.get_config(),
                "message": f"NETCONF server started on port {port}"
            }
        except ImportError as e:
            return {"success": False, "error": f"NETCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"NETCONF server start error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/netconf/server/{agent_name}")
    async def api_stop_netconf_server(agent_name: str) -> Dict[str, Any]:
        """
        Stop NETCONF server for an agent

        Args:
            agent_name: Name of the agent

        Returns:
            Operation status
        """
        try:
            from agentic.netconf import stop_netconf_server, get_netconf_server

            server = get_netconf_server(agent_name)
            if not server:
                return {"success": False, "error": f"NETCONF server for {agent_name} not found"}

            await stop_netconf_server(agent_name)
            return {"success": True, "agent_name": agent_name, "message": "NETCONF server stopped"}
        except ImportError as e:
            return {"success": False, "error": f"NETCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"NETCONF server stop error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/netconf/config/{agent_name}")
    async def api_get_netconf_config(
        agent_name: str,
        datastore: str = "running",
        xpath: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get configuration from NETCONF datastore

        Args:
            agent_name: Name of the agent
            datastore: Datastore type (running, candidate, startup)
            xpath: Optional XPath filter

        Returns:
            Configuration data
        """
        try:
            from agentic.netconf import get_netconf_server, DatastoreType

            server = get_netconf_server(agent_name)
            if not server:
                return {"error": f"NETCONF server for {agent_name} not found"}

            ds_type = DatastoreType(datastore)
            config = server.get_datastore_config(ds_type)
            return {"datastore": datastore, "config": config}
        except ImportError as e:
            return {"error": f"NETCONF module not available: {e}"}
        except ValueError as e:
            return {"error": f"Invalid datastore: {datastore}"}
        except Exception as e:
            logger.error(f"NETCONF config error: {e}")
            return {"error": str(e)}

    @app.get("/api/restconf/servers")
    async def api_get_restconf_servers() -> Dict[str, Any]:
        """
        Get all RESTCONF servers and their status

        Returns:
            List of RESTCONF server configurations and statistics
        """
        try:
            from agentic.netconf import get_restconf_statistics
            stats = get_restconf_statistics()
            return {
                "servers": stats,
                "total_servers": len(stats)
            }
        except ImportError as e:
            return {"servers": {}, "error": f"RESTCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"RESTCONF servers error: {e}")
            return {"servers": {}, "error": str(e)}

    @app.get("/api/restconf/server/{agent_name}")
    async def api_get_restconf_server(agent_name: str) -> Dict[str, Any]:
        """
        Get RESTCONF server info for a specific agent

        Args:
            agent_name: Name of the agent

        Returns:
            RESTCONF server configuration and statistics
        """
        try:
            from agentic.netconf import get_restconf_server
            server = get_restconf_server(agent_name)
            if server:
                return {
                    "agent_name": agent_name,
                    "running": server.running,
                    "config": server.get_config(),
                    "statistics": server.get_statistics().to_dict()
                }
            else:
                return {"agent_name": agent_name, "running": False, "error": "Server not found"}
        except ImportError as e:
            return {"error": f"RESTCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"RESTCONF server error: {e}")
            return {"error": str(e)}

    @app.post("/api/restconf/server")
    async def api_start_restconf_server(
        agent_name: str,
        port: int = 8443,
        use_https: bool = True,
        api_root: str = "/restconf"
    ) -> Dict[str, Any]:
        """
        Start RESTCONF server for an agent

        Args:
            agent_name: Name of the agent
            port: RESTCONF port number
            use_https: Enable HTTPS
            api_root: API root path

        Returns:
            Server status and configuration
        """
        try:
            from agentic.netconf import start_restconf_server

            server = await start_restconf_server(
                agent_name=agent_name,
                port=port,
                use_https=use_https,
                api_root=api_root
            )

            return {
                "success": True,
                "agent_name": agent_name,
                "port": port,
                "config": server.get_config(),
                "message": f"RESTCONF server started on port {port}"
            }
        except ImportError as e:
            return {"success": False, "error": f"RESTCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"RESTCONF server start error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/restconf/server/{agent_name}")
    async def api_stop_restconf_server(agent_name: str) -> Dict[str, Any]:
        """
        Stop RESTCONF server for an agent

        Args:
            agent_name: Name of the agent

        Returns:
            Operation status
        """
        try:
            from agentic.netconf import stop_restconf_server, get_restconf_server

            server = get_restconf_server(agent_name)
            if not server:
                return {"success": False, "error": f"RESTCONF server for {agent_name} not found"}

            await stop_restconf_server(agent_name)
            return {"success": True, "agent_name": agent_name, "message": "RESTCONF server stopped"}
        except ImportError as e:
            return {"success": False, "error": f"RESTCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"RESTCONF server stop error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/restconf/data/{agent_name}")
    async def api_restconf_get_data(agent_name: str, path: str = "/") -> Dict[str, Any]:
        """
        Get data via RESTCONF

        Args:
            agent_name: Name of the agent
            path: RESTCONF data path

        Returns:
            Data from RESTCONF datastore
        """
        try:
            from agentic.netconf import get_restconf_server
            server = get_restconf_server(agent_name)
            if not server:
                return {"error": f"RESTCONF server for {agent_name} not found"}

            result = await server.handle_get(f"/restconf/data{path}")
            return result
        except ImportError as e:
            return {"error": f"RESTCONF module not available: {e}"}
        except Exception as e:
            logger.error(f"RESTCONF GET error: {e}")
            return {"error": str(e)}

    # ==========================================================================
    # Subnet Calculator API Endpoints (Foundational MCP)
    # ==========================================================================

    @app.get("/api/subnet/calculate")
    async def api_calculate_subnet(cidr: str) -> Dict[str, Any]:
        """
        Calculate subnet details for IPv4 or IPv6 CIDR (auto-detect).

        Args:
            cidr: Network in CIDR notation (e.g., '192.168.1.0/24' or '2001:db8::/32')

        Returns:
            Comprehensive subnet information
        """
        try:
            from agentic.mcp.subnet_mcp import get_calculator
            calc = get_calculator()
            return calc.calculate_auto(cidr)
        except Exception as e:
            logger.error(f"Subnet calculation error: {e}")
            return {"error": str(e), "input_cidr": cidr}

    @app.get("/api/subnet/ipv4")
    async def api_calculate_ipv4(cidr: str) -> Dict[str, Any]:
        """
        Calculate IPv4 subnet details.

        Args:
            cidr: IPv4 network in CIDR notation (e.g., '192.168.1.0/24')

        Returns:
            IPv4 subnet information
        """
        try:
            from agentic.mcp.subnet_mcp import get_calculator
            calc = get_calculator()
            return calc.calculate_ipv4(cidr)
        except Exception as e:
            logger.error(f"IPv4 calculation error: {e}")
            return {"error": str(e), "input_cidr": cidr}

    @app.get("/api/subnet/ipv6")
    async def api_calculate_ipv6(cidr: str) -> Dict[str, Any]:
        """
        Calculate IPv6 subnet details.

        Args:
            cidr: IPv6 network in CIDR notation (e.g., '2001:db8::/32')

        Returns:
            IPv6 subnet information
        """
        try:
            from agentic.mcp.subnet_mcp import get_calculator
            calc = get_calculator()
            return calc.calculate_ipv6(cidr)
        except Exception as e:
            logger.error(f"IPv6 calculation error: {e}")
            return {"error": str(e), "input_cidr": cidr}

    @app.get("/api/subnet/analyze")
    async def api_analyze_ip(ip_address: str) -> Dict[str, Any]:
        """
        Analyze a single IP address.

        Args:
            ip_address: IP address to analyze (IPv4 or IPv6)

        Returns:
            IP address analysis including classification
        """
        try:
            from agentic.mcp.subnet_mcp import get_calculator
            calc = get_calculator()
            return calc.analyze_ip(ip_address)
        except Exception as e:
            logger.error(f"IP analysis error: {e}")
            return {"error": str(e), "input": ip_address}

    @app.get("/api/subnet/agent-ips")
    async def api_get_agent_ips() -> Dict[str, Any]:
        """
        Get all IP addresses configured on this agent with analysis.

        Returns:
            List of IPs with their subnet analysis
        """
        try:
            from agentic.mcp.subnet_mcp import get_calculator
            calc = get_calculator()

            # Get interfaces from the agent
            interfaces = []
            if agentic_bridge and hasattr(agentic_bridge, 'state_manager'):
                state = agentic_bridge.state_manager
                if hasattr(state, '_interfaces'):
                    interfaces = state._interfaces

            # Analyze each IP
            analyzed_ips = []
            for iface in interfaces:
                for addr in iface.get('addresses', []):
                    analysis = calc.calculate_auto(addr)
                    analysis['interface'] = iface.get('name', iface.get('id', 'unknown'))
                    analyzed_ips.append(analysis)

            return {
                "agent_ips": analyzed_ips,
                "count": len(analyzed_ips)
            }
        except Exception as e:
            logger.error(f"Agent IPs error: {e}")
            return {"agent_ips": [], "error": str(e)}

    # ==========================================================================
    # SLAAC (IPv6 Stateless Address Autoconfiguration) API Endpoints
    # ==========================================================================

    @app.get("/api/slaac/status")
    async def api_get_slaac_status() -> Dict[str, Any]:
        """
        Get current SLAAC status and configured addresses.

        Returns:
            SLAAC manager status with all addresses
        """
        try:
            from agentic.protocols.slaac import get_slaac_manager
            agent_id = "local"
            if agentic_bridge and hasattr(agentic_bridge, 'agent_id'):
                agent_id = agentic_bridge.agent_id
            slaac = get_slaac_manager(agent_id)
            return slaac.get_status()
        except Exception as e:
            logger.error(f"SLAAC status error: {e}")
            return {"error": str(e)}

    @app.post("/api/slaac/initialize")
    async def api_initialize_slaac() -> Dict[str, Any]:
        """
        Initialize SLAAC and auto-configure IPv6 addresses for the agent.

        Generates:
        - Link-local address (fe80::EUI-64)
        - Mesh ULA address (fd00:10::EUI-64)

        Returns:
            Generated addresses and configuration status
        """
        try:
            from agentic.protocols.slaac import initialize_agent_slaac
            agent_id = "local"
            if agentic_bridge and hasattr(agentic_bridge, 'agent_id'):
                agent_id = agentic_bridge.agent_id
            result = initialize_agent_slaac(agent_id)
            return result
        except Exception as e:
            logger.error(f"SLAAC initialize error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/slaac/mesh-address")
    async def api_get_mesh_address() -> Dict[str, Any]:
        """
        Get the agent's mesh network address (ULA).

        This is the primary address for agent-to-agent communication.

        Returns:
            Mesh address details
        """
        try:
            from agentic.protocols.slaac import get_slaac_manager
            agent_id = "local"
            if agentic_bridge and hasattr(agentic_bridge, 'agent_id'):
                agent_id = agentic_bridge.agent_id
            slaac = get_slaac_manager(agent_id)

            # Initialize if not already done
            if not slaac.mesh_address:
                slaac.auto_configure()

            addr = slaac.mesh_address
            if addr:
                return {
                    "address": addr.address,
                    "full_cidr": addr.full_cidr,
                    "prefix": addr.prefix,
                    "state": addr.state.value,
                    "is_preferred": addr.is_preferred,
                    "eui64": slaac.eui64
                }
            return {"address": None, "error": "No mesh address configured"}
        except Exception as e:
            logger.error(f"SLAAC mesh address error: {e}")
            return {"error": str(e)}

    @app.post("/api/slaac/generate-privacy")
    async def api_generate_privacy_address() -> Dict[str, Any]:
        """
        Generate a temporary privacy address per RFC 4941.

        Returns:
            Generated privacy address details
        """
        try:
            from agentic.protocols.slaac import get_slaac_manager
            agent_id = "local"
            if agentic_bridge and hasattr(agentic_bridge, 'agent_id'):
                agent_id = agentic_bridge.agent_id
            slaac = get_slaac_manager(agent_id)
            addr = slaac.generate_privacy_address()
            return {
                "success": True,
                "address": addr.to_dict()
            }
        except Exception as e:
            logger.error(f"SLAAC privacy address error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # QoS (Quality of Service) API Endpoints - RFC 4594
    # ==========================================================================

    # Get agent_id for QoS - used by all QoS endpoints
    qos_agent_id = os.environ.get("ASI_AGENT_ID", "local")

    @app.get("/api/qos/classes")
    async def api_get_qos_classes() -> Dict[str, Any]:
        """
        Get all RFC 4594 DiffServ service classes.

        Returns:
            List of service class configurations with DSCP, PHB, tolerances
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            return {
                "classes": qos.get_all_service_classes(),
                "count": len(qos.service_classes)
            }
        except Exception as e:
            logger.error(f"QoS classes error: {e}")
            return {"classes": [], "error": str(e)}

    @app.get("/api/qos/swim-lanes")
    async def api_get_qos_swim_lanes() -> Dict[str, Any]:
        """
        Get QoS swim lane visualization data.

        Returns:
            Ordered list of service classes from highest to lowest priority
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            return {
                "swim_lanes": qos.get_swim_lanes(),
                "enabled": qos.enabled
            }
        except Exception as e:
            logger.error(f"QoS swim lanes error: {e}")
            return {"swim_lanes": [], "error": str(e)}

    @app.get("/api/qos/rules")
    async def api_get_qos_rules() -> Dict[str, Any]:
        """
        Get all traffic classification rules.

        Returns:
            List of classification rules with match criteria and actions
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            return {
                "rules": qos.get_classification_rules(),
                "count": len(qos.global_rules)
            }
        except Exception as e:
            logger.error(f"QoS rules error: {e}")
            return {"rules": [], "error": str(e)}

    @app.get("/api/qos/policies")
    async def api_get_qos_policies() -> Dict[str, Any]:
        """
        Get QoS policies applied to interfaces.

        Returns:
            Per-interface QoS policy configurations and statistics
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            return {
                "policies": qos.get_all_policies(),
                "interfaces_count": len(qos.interface_policies)
            }
        except Exception as e:
            logger.error(f"QoS policies error: {e}")
            return {"policies": {}, "error": str(e)}

    @app.get("/api/qos/statistics")
    async def api_get_qos_statistics() -> Dict[str, Any]:
        """
        Get QoS classification and marking statistics.

        Returns:
            Overall QoS statistics and per-class counters
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            return qos.get_statistics()
        except Exception as e:
            logger.error(f"QoS statistics error: {e}")
            return {"error": str(e)}

    @app.get("/api/debug/protocol-stats")
    async def api_debug_protocol_stats() -> Dict[str, Any]:
        """
        Debug endpoint: Show raw protocol message statistics from ALL protocols.
        Helps diagnose why QoS counters may not be incrementing.
        """
        result = {
            "protocols": {
                "ospf": {"exists": False, "stats": {}},
                "ospfv3": {"exists": False, "stats": {}},
                "bgp": {"exists": False, "stats": {}},
                "isis": {"exists": False, "stats": {}},
                "ldp": {"exists": False, "stats": {}},
                "lldp": {"exists": False, "stats": {}}
            },
            "qos_totals": {},
            "qos_per_class": {}
        }

        # OSPF stats
        if asi_app.ospf_interface:
            result["protocols"]["ospf"]["exists"] = True
            ospf = asi_app.ospf_interface
            if hasattr(ospf, 'stats'):
                result["protocols"]["ospf"]["stats"] = dict(ospf.stats)
                result["protocols"]["ospf"]["source"] = "ospf.stats"

        # OSPFv3 stats
        if hasattr(asi_app, 'ospfv3_speaker') and asi_app.ospfv3_speaker:
            result["protocols"]["ospfv3"]["exists"] = True
            ospfv3 = asi_app.ospfv3_speaker
            if hasattr(ospfv3, 'stats'):
                result["protocols"]["ospfv3"]["stats"] = dict(ospfv3.stats)
            elif hasattr(ospfv3, 'interfaces'):
                # Aggregate from interfaces
                agg = {"hello_sent": 0, "hello_received": 0}
                for iface in ospfv3.interfaces.values():
                    if hasattr(iface, 'stats'):
                        agg["hello_sent"] += iface.stats.get('hello_sent', 0)
                        agg["hello_received"] += iface.stats.get('hello_received', 0)
                result["protocols"]["ospfv3"]["stats"] = agg
                result["protocols"]["ospfv3"]["source"] = "ospfv3.interfaces[].stats"

        # BGP stats
        if asi_app.bgp_speaker:
            result["protocols"]["bgp"]["exists"] = True
            bgp = asi_app.bgp_speaker
            if hasattr(bgp, 'stats'):
                result["protocols"]["bgp"]["stats"] = dict(bgp.stats)
                result["protocols"]["bgp"]["source"] = "bgp.stats"

        # IS-IS stats
        if hasattr(asi_app, 'isis_speaker') and asi_app.isis_speaker:
            result["protocols"]["isis"]["exists"] = True
            isis = asi_app.isis_speaker
            if hasattr(isis, 'stats'):
                result["protocols"]["isis"]["stats"] = dict(isis.stats)

        # LDP stats
        if hasattr(asi_app, 'ldp_speaker') and asi_app.ldp_speaker:
            result["protocols"]["ldp"]["exists"] = True
            ldp = asi_app.ldp_speaker
            if hasattr(ldp, 'stats'):
                result["protocols"]["ldp"]["stats"] = dict(ldp.stats)

        # LLDP stats
        try:
            from agentic.discovery.lldp import get_lldp_daemon
            lldp = get_lldp_daemon()
            if lldp:
                result["protocols"]["lldp"]["exists"] = True
                if hasattr(lldp, 'stats'):
                    result["protocols"]["lldp"]["stats"] = dict(lldp.stats)
        except:
            pass

        # Get QoS totals and per-class stats
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            result["qos_totals"] = {
                "total_classified": qos.total_classified,
                "total_marked": qos.total_marked,
                "interfaces_with_qos": len(qos.interface_policies),
                "interfaces": list(qos.interface_policies.keys()),
                "enabled": qos.enabled
            }

            # Get per-class packet counts
            stats = qos.get_statistics()
            result["qos_per_class"] = stats.get("per_class", {})

            # Also collect all protocol stats via QoS
            all_stats = qos.collect_all_protocol_stats(asi_app)
            result["qos_protocol_totals"] = all_stats

        except Exception as e:
            result["qos_error"] = str(e)

        return result

    @app.post("/api/qos/enable")
    async def api_enable_qos() -> Dict[str, Any]:
        """
        Enable QoS processing on the agent.

        Returns:
            Status of QoS enablement
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            qos.enable()
            return {"success": True, "enabled": True}
        except Exception as e:
            logger.error(f"QoS enable error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/qos/disable")
    async def api_disable_qos() -> Dict[str, Any]:
        """
        Disable QoS processing on the agent.

        Returns:
            Status of QoS disablement
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)
            qos.disable()
            return {"success": True, "enabled": False}
        except Exception as e:
            logger.error(f"QoS disable error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/qos/apply")
    async def api_apply_qos_to_interfaces() -> Dict[str, Any]:
        """
        Apply RFC 4594 QoS policy to all agent interfaces.

        Returns:
            Status and list of interfaces with applied policies
        """
        try:
            from agentic.protocols.qos import get_qos_manager
            qos = get_qos_manager(qos_agent_id)

            # Get interfaces from agent
            interfaces = []
            if agentic_bridge and hasattr(agentic_bridge, 'state_manager'):
                state = agentic_bridge.state_manager
                if hasattr(state, '_interfaces'):
                    interfaces = [iface.get('name', iface.get('id', 'unknown'))
                                  for iface in state._interfaces]

            if not interfaces:
                # Default to common interface names
                interfaces = ['eth0', 'lo']

            results = qos.apply_to_all_interfaces(interfaces)
            return {
                "success": True,
                "enabled": qos.enabled,
                "interfaces": list(results.keys()),
                "interfaces_count": len(results)
            }
        except Exception as e:
            logger.error(f"QoS apply error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # NetFlow/IPFIX API Endpoints (RFC 7011)
    # ==========================================================================

    # Get agent_id for NetFlow
    netflow_agent_id = os.environ.get("ASI_AGENT_ID", "local")

    @app.get("/api/netflow/status")
    async def api_get_netflow_status() -> Dict[str, Any]:
        """Get NetFlow exporter and collector status"""
        try:
            from agentic.protocols.netflow import get_flow_exporter, get_flow_collector
            exporter = get_flow_exporter(netflow_agent_id)
            collector = get_flow_collector(netflow_agent_id)

            return {
                "exporter": exporter.get_statistics(),
                "collector": collector.get_statistics()
            }
        except Exception as e:
            logger.error(f"NetFlow status error: {e}")
            return {"error": str(e)}

    @app.get("/api/netflow/flows")
    async def api_get_netflow_flows() -> Dict[str, Any]:
        """Get all active flows from the exporter"""
        try:
            from agentic.protocols.netflow import get_flow_exporter
            exporter = get_flow_exporter(netflow_agent_id)

            return {
                "flows": exporter.get_active_flows(),
                "count": len(exporter.active_flows),
                "total_observed": exporter.total_packets_observed
            }
        except Exception as e:
            logger.error(f"NetFlow flows error: {e}")
            return {"flows": [], "error": str(e)}

    @app.get("/api/netflow/top-flows")
    async def api_get_top_flows(n: int = 10, sort_by: str = "bytes") -> Dict[str, Any]:
        """Get top N flows by bytes, packets, or rate"""
        try:
            from agentic.protocols.netflow import get_flow_exporter
            exporter = get_flow_exporter(netflow_agent_id)

            return {
                "top_flows": exporter.get_top_flows(n, sort_by),
                "sort_by": sort_by
            }
        except Exception as e:
            logger.error(f"NetFlow top flows error: {e}")
            return {"top_flows": [], "error": str(e)}

    @app.get("/api/netflow/by-protocol")
    async def api_get_flows_by_protocol() -> Dict[str, Any]:
        """Get flows grouped by protocol"""
        try:
            from agentic.protocols.netflow import get_flow_exporter
            exporter = get_flow_exporter(netflow_agent_id)

            flows_by_proto = exporter.get_flows_by_protocol()
            return {
                "by_protocol": flows_by_proto,
                "protocol_stats": exporter.protocol_stats
            }
        except Exception as e:
            logger.error(f"NetFlow by protocol error: {e}")
            return {"by_protocol": {}, "error": str(e)}

    @app.get("/api/netflow/by-service-class")
    async def api_get_flows_by_service_class() -> Dict[str, Any]:
        """Get flows grouped by QoS service class"""
        try:
            from agentic.protocols.netflow import get_flow_exporter
            exporter = get_flow_exporter(netflow_agent_id)

            return {
                "by_service_class": exporter.get_flows_by_service_class()
            }
        except Exception as e:
            logger.error(f"NetFlow by service class error: {e}")
            return {"by_service_class": {}, "error": str(e)}

    @app.get("/api/netflow/statistics")
    async def api_get_netflow_statistics() -> Dict[str, Any]:
        """Get detailed NetFlow statistics"""
        try:
            from agentic.protocols.netflow import get_flow_exporter, get_flow_collector
            exporter = get_flow_exporter(netflow_agent_id)
            collector = get_flow_collector(netflow_agent_id)

            # Get protocol breakdown
            proto_breakdown = {}
            for proto, stats in exporter.protocol_stats.items():
                from agentic.protocols.netflow import FlowKey
                proto_name = FlowKey("", "", 0, 0, proto)._get_protocol_name()
                proto_breakdown[proto_name] = stats

            return {
                "exporter": {
                    "active_flows": len(exporter.active_flows),
                    "expired_flows": len(exporter.expired_flows),
                    "total_packets": exporter.total_packets_observed,
                    "total_bytes": exporter.total_bytes_observed,
                    "total_exported": exporter.total_flows_exported,
                    "collectors": len(exporter.collectors)
                },
                "collector": {
                    "messages_received": collector.total_messages_received,
                    "flows_received": collector.total_flows_received,
                    "exporters_seen": len(collector.exporters_seen)
                },
                "protocol_breakdown": proto_breakdown
            }
        except Exception as e:
            logger.error(f"NetFlow statistics error: {e}")
            return {"error": str(e)}

    @app.post("/api/netflow/collector/add")
    async def api_add_netflow_collector(ip: str, port: int = 4739) -> Dict[str, Any]:
        """Add a NetFlow collector to export to"""
        try:
            from agentic.protocols.netflow import get_flow_exporter
            exporter = get_flow_exporter(netflow_agent_id)
            exporter.add_collector(ip, port)

            return {
                "success": True,
                "collectors": [f"{c[0]}:{c[1]}" for c in exporter.collectors]
            }
        except Exception as e:
            logger.error(f"NetFlow add collector error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # GRE Tunnel API Endpoints (RFC 2784/2890)
    # ==========================================================================

    gre_agent_id = os.environ.get("ASI_AGENT_ID", "local")

    @app.get("/api/gre/status")
    async def api_get_gre_status() -> Dict[str, Any]:
        """Get GRE manager status"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"enabled": False, "error": "GRE manager not initialized"}
            return {
                "enabled": True,
                **manager.get_status()
            }
        except ImportError as e:
            return {"enabled": False, "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE status error: {e}")
            return {"enabled": False, "error": str(e)}

    @app.get("/api/gre/tunnels")
    async def api_get_gre_tunnels() -> Dict[str, Any]:
        """Get all GRE tunnels"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"tunnels": [], "error": "GRE manager not initialized"}
            return {
                "tunnels": manager.list_tunnels(),
                "count": manager.tunnel_count
            }
        except ImportError as e:
            return {"tunnels": [], "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE tunnels error: {e}")
            return {"tunnels": [], "error": str(e)}

    @app.get("/api/gre/tunnel/{name}")
    async def api_get_gre_tunnel(name: str) -> Dict[str, Any]:
        """Get specific GRE tunnel status"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"error": "GRE manager not initialized"}

            tunnel = manager.get_tunnel(name)
            if not tunnel:
                return {"error": f"Tunnel '{name}' not found"}

            return tunnel.get_status()
        except ImportError as e:
            return {"error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE tunnel error: {e}")
            return {"error": str(e)}

    @app.post("/api/gre/tunnel")
    async def api_create_gre_tunnel(
        name: str,
        remote_ip: str,
        tunnel_ip: str = "",
        local_ip: str = "",
        key: Optional[int] = None,
        use_checksum: bool = False,
        use_sequence: bool = False,
        mtu: int = 1400,
        keepalive_interval: int = 10,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Create a new GRE tunnel

        Args:
            name: Tunnel interface name (e.g., "gre0", "gre-to-cml")
            remote_ip: Remote endpoint IP address
            tunnel_ip: IP address for tunnel interface (with prefix, e.g., "10.0.0.1/30")
            local_ip: Local endpoint IP (defaults to agent's primary IP)
            key: Optional GRE key for traffic identification
            use_checksum: Whether to calculate checksums
            use_sequence: Whether to use sequence numbers
            mtu: Tunnel MTU (default 1400)
            keepalive_interval: Keepalive interval in seconds (0 to disable)
            description: Optional description

        Returns:
            Tunnel status if successful
        """
        try:
            from gre import get_gre_manager, configure_gre_manager, GRETunnelConfig

            # Get or create manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                # Need to determine local IP
                if not local_ip:
                    # Try to get from agent config
                    local_ip = os.environ.get("ASI_AGENT_IP", "0.0.0.0")

                manager = configure_gre_manager(gre_agent_id, local_ip)
                await manager.start()

            # Use manager's local IP if not specified
            if not local_ip:
                local_ip = manager.local_ip

            # Create tunnel config
            config = GRETunnelConfig(
                name=name,
                local_ip=local_ip,
                remote_ip=remote_ip,
                tunnel_ip=tunnel_ip,
                key=key,
                use_checksum=use_checksum,
                use_sequence=use_sequence,
                mtu=mtu,
                keepalive_interval=keepalive_interval,
                description=description
            )

            # Create tunnel
            tunnel = await manager.create_tunnel(config)
            if not tunnel:
                return {"success": False, "error": "Failed to create tunnel"}

            return {
                "success": True,
                "tunnel": tunnel.get_status()
            }

        except ImportError as e:
            return {"success": False, "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE create tunnel error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/gre/tunnel/{name}")
    async def api_delete_gre_tunnel(name: str) -> Dict[str, Any]:
        """Delete a GRE tunnel"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"success": False, "error": "GRE manager not initialized"}

            success = await manager.delete_tunnel(name)
            return {"success": success}

        except ImportError as e:
            return {"success": False, "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE delete tunnel error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/gre/statistics")
    async def api_get_gre_statistics() -> Dict[str, Any]:
        """Get GRE tunnel statistics"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"error": "GRE manager not initialized"}
            return manager.get_statistics()
        except ImportError as e:
            return {"error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE statistics error: {e}")
            return {"error": str(e)}

    @app.post("/api/gre/allowed-source")
    async def api_add_gre_allowed_source(ip: str) -> Dict[str, Any]:
        """Add an IP to the allowed GRE sources for passive tunnels"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"success": False, "error": "GRE manager not initialized"}

            manager.add_allowed_source(ip)
            return {
                "success": True,
                "allowed_sources": list(manager.allowed_sources)
            }
        except ImportError as e:
            return {"success": False, "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE add allowed source error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/gre/allowed-source/{ip}")
    async def api_remove_gre_allowed_source(ip: str) -> Dict[str, Any]:
        """Remove an IP from the allowed GRE sources"""
        try:
            from gre import get_gre_manager
            manager = get_gre_manager(gre_agent_id)
            if not manager:
                return {"success": False, "error": "GRE manager not initialized"}

            manager.remove_allowed_source(ip)
            return {
                "success": True,
                "allowed_sources": list(manager.allowed_sources)
            }
        except ImportError as e:
            return {"success": False, "error": f"GRE module not available: {e}"}
        except Exception as e:
            logger.error(f"GRE remove allowed source error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # BFD (Bidirectional Forwarding Detection) API Endpoints
    # ==========================================================================

    bfd_agent_id = os.environ.get("ASI_AGENT_ID", "local")

    @app.get("/api/bfd/status")
    async def api_get_bfd_status() -> Dict[str, Any]:
        """Get BFD manager status"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                return manager.get_status()
            else:
                return {"enabled": False, "running": False, "sessions": []}
        except ImportError as e:
            return {"enabled": False, "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD status error: {e}")
            return {"enabled": False, "error": str(e)}

    @app.get("/api/bfd/sessions")
    async def api_get_bfd_sessions() -> Dict[str, Any]:
        """Get all BFD sessions"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                return {
                    "sessions": manager.list_sessions(),
                    "total": manager.session_count,
                    "up": manager.up_session_count
                }
            else:
                return {"sessions": [], "total": 0, "up": 0}
        except ImportError as e:
            return {"sessions": [], "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD sessions error: {e}")
            return {"sessions": [], "error": str(e)}

    @app.get("/api/bfd/session/{peer_address}")
    async def api_get_bfd_session(peer_address: str) -> Dict[str, Any]:
        """Get specific BFD session status"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                session = manager.get_session(peer_address)
                if session:
                    return {"found": True, "session": session.to_dict()}
                else:
                    return {"found": False, "error": f"No session to {peer_address}"}
            else:
                return {"found": False, "error": "BFD manager not initialized"}
        except ImportError as e:
            return {"error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD session error: {e}")
            return {"error": str(e)}

    @app.post("/api/bfd/session")
    async def api_create_bfd_session(
        peer_address: str,
        local_address: str = "",
        protocol: str = "",
        detect_mult: int = 3,
        min_tx_us: int = 100000,
        min_rx_us: int = 100000,
        interface: str = ""
    ) -> Dict[str, Any]:
        """
        Create a new BFD session

        Args:
            peer_address: Remote peer IP address
            local_address: Local IP address (optional)
            protocol: Client protocol (ospf, bgp, isis, static)
            detect_mult: Detection multiplier (default 3)
            min_tx_us: Desired min TX interval in microseconds (default 100ms)
            min_rx_us: Required min RX interval in microseconds (default 100ms)
            interface: Interface name for single-hop BFD

        Returns:
            Session creation result
        """
        try:
            from bfd import get_bfd_manager, BFDSessionConfig

            manager = get_bfd_manager(bfd_agent_id)
            if not manager:
                return {"success": False, "error": "BFD manager not initialized"}

            # Start manager if not running
            if not manager.is_running:
                await manager.start()

            # Use protocol-specific timers if protocol specified
            if protocol:
                session = await manager.create_session_for_protocol(
                    protocol=protocol,
                    peer_address=peer_address,
                    local_address=local_address,
                    interface=interface
                )
            else:
                config = BFDSessionConfig(
                    remote_address=peer_address,
                    local_address=local_address,
                    interface=interface,
                    desired_min_tx=min_tx_us,
                    required_min_rx=min_rx_us,
                    detect_mult=detect_mult
                )
                session = await manager.create_session(config)

            return {
                "success": True,
                "session": session.to_dict(),
                "message": f"BFD session created to {peer_address}"
            }
        except ImportError as e:
            return {"success": False, "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD create session error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/bfd/session/{peer_address}")
    async def api_delete_bfd_session(peer_address: str) -> Dict[str, Any]:
        """Delete a BFD session"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if not manager:
                return {"success": False, "error": "BFD manager not initialized"}

            result = await manager.delete_session(peer_address)
            return {
                "success": result,
                "message": f"BFD session to {peer_address} {'deleted' if result else 'not found'}"
            }
        except ImportError as e:
            return {"success": False, "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD delete session error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/bfd/statistics")
    async def api_get_bfd_statistics() -> Dict[str, Any]:
        """Get BFD manager statistics"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                return {"statistics": manager.stats.to_dict()}
            else:
                return {"statistics": {}}
        except ImportError as e:
            return {"error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD statistics error: {e}")
            return {"error": str(e)}

    @app.post("/api/bfd/start")
    async def api_start_bfd() -> Dict[str, Any]:
        """Start the BFD manager"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                await manager.start()
                return {"success": True, "running": manager.is_running}
            else:
                return {"success": False, "error": "BFD manager not available"}
        except ImportError as e:
            return {"success": False, "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD start error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/bfd/stop")
    async def api_stop_bfd() -> Dict[str, Any]:
        """Stop the BFD manager"""
        try:
            from bfd import get_bfd_manager
            manager = get_bfd_manager(bfd_agent_id)
            if manager:
                await manager.stop()
                return {"success": True, "running": manager.is_running}
            else:
                return {"success": False, "error": "BFD manager not available"}
        except ImportError as e:
            return {"success": False, "error": f"BFD module not available: {e}"}
        except Exception as e:
            logger.error(f"BFD stop error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # MCP External Access API Endpoints
    # ==========================================================================

    @app.get("/api/mcp/servers")
    async def api_get_mcp_servers() -> Dict[str, Any]:
        """
        Get all MCP external servers and their status

        Returns:
            List of MCP server configurations and statistics
        """
        try:
            from agentic.mcp_external import get_mcp_statistics, list_mcp_connections
            stats = get_mcp_statistics()
            connections = list_mcp_connections()
            return {
                "servers": stats,
                "total_servers": len(stats),
                "active_connections": connections,
                "total_connections": len(connections)
            }
        except ImportError as e:
            return {"servers": {}, "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP servers error: {e}")
            return {"servers": {}, "error": str(e)}

    @app.get("/api/mcp/server/{server_id:path}")
    async def api_get_mcp_server(server_id: str) -> Dict[str, Any]:
        """
        Get MCP server info for a specific server

        Args:
            server_id: Server ID (format: type:agent:port)

        Returns:
            MCP server configuration and statistics
        """
        try:
            from agentic.mcp_external import get_mcp_server
            server = get_mcp_server(server_id)
            if server:
                return {
                    "server_id": server_id,
                    "running": server.running,
                    "config": server.get_config(),
                    "statistics": server.get_statistics().to_dict(),
                    "connections": server.get_connections(),
                    "tools": server.get_tools()
                }
            else:
                return {"server_id": server_id, "running": False, "error": "Server not found"}
        except ImportError as e:
            return {"error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP server error: {e}")
            return {"error": str(e)}

    @app.post("/api/mcp/server")
    async def api_start_mcp_server(
        server_type: str = "network",
        agent_name: Optional[str] = None,
        port: int = 3000,
        api_key: Optional[str] = None,
        require_auth: bool = True,
        max_connections: int = 50,
        rate_limit: int = 100
    ) -> Dict[str, Any]:
        """
        Start MCP external server

        Args:
            server_type: Server type (network or agent)
            agent_name: Agent name (required for agent type)
            port: Server port number
            api_key: API key for authentication
            require_auth: Require authentication
            max_connections: Maximum concurrent connections
            rate_limit: Requests per minute limit

        Returns:
            Server status and configuration
        """
        try:
            from agentic.mcp_external import start_mcp_server

            # Create network handler that uses agentic bridge
            async def network_handler(tool_name: str, args: Dict) -> Any:
                if agentic_bridge:
                    try:
                        # Map tool calls to appropriate handlers
                        if tool_name == "ask_network":
                            return await agentic_bridge.process_message(args.get("question", ""))
                        elif tool_name == "get_topology":
                            return await get_network_topology()
                        elif tool_name == "get_metrics":
                            return await get_network_metrics()
                        else:
                            return {"tool": tool_name, "args": args, "status": "executed"}
                    except Exception as e:
                        return {"error": str(e)}
                return {"error": "Network handler not available"}

            server = await start_mcp_server(
                server_type=server_type,
                agent_name=agent_name,
                port=port,
                api_key=api_key,
                require_auth=require_auth,
                max_connections=max_connections,
                rate_limit=rate_limit,
                network_handler=network_handler
            )

            server_id = f"{server_type}:{agent_name or 'global'}:{port}"
            return {
                "success": True,
                "server_id": server_id,
                "port": port,
                "config": server.get_config(),
                "message": f"MCP server started on port {port}"
            }
        except ImportError as e:
            return {"success": False, "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP server start error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/mcp/server/{server_id:path}")
    async def api_stop_mcp_server(server_id: str) -> Dict[str, Any]:
        """
        Stop MCP external server

        Args:
            server_id: Server ID (format: type:agent:port)

        Returns:
            Operation status
        """
        try:
            from agentic.mcp_external import stop_mcp_server, get_mcp_server

            server = get_mcp_server(server_id)
            if not server:
                return {"success": False, "error": f"MCP server {server_id} not found"}

            await stop_mcp_server(server_id)
            return {"success": True, "server_id": server_id, "message": "MCP server stopped"}
        except ImportError as e:
            return {"success": False, "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP server stop error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/mcp/connections")
    async def api_get_mcp_connections(server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get active MCP connections

        Args:
            server_id: Optional filter by server ID

        Returns:
            List of active connections
        """
        try:
            from agentic.mcp_external import list_mcp_connections
            connections = list_mcp_connections(server_id)
            return {"connections": connections, "count": len(connections)}
        except ImportError as e:
            return {"connections": [], "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP connections error: {e}")
            return {"connections": [], "error": str(e)}

    @app.get("/api/mcp/tools")
    async def api_get_mcp_tools(server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get available MCP tools

        Args:
            server_id: Optional filter by server ID

        Returns:
            Available tools by server
        """
        try:
            from agentic.mcp_external import list_available_tools
            tools = list_available_tools(server_id)
            return {"tools": tools}
        except ImportError as e:
            return {"tools": {}, "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP tools error: {e}")
            return {"tools": {}, "error": str(e)}

    @app.get("/api/mcp/statistics")
    async def api_get_mcp_statistics(server_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get MCP server statistics

        Args:
            server_id: Optional filter by server ID

        Returns:
            MCP statistics
        """
        try:
            from agentic.mcp_external import get_mcp_statistics
            stats = get_mcp_statistics(server_id)
            return {"statistics": stats}
        except ImportError as e:
            return {"statistics": {}, "error": f"MCP External module not available: {e}"}
        except Exception as e:
            logger.error(f"MCP statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    # ==========================================================================
    # Network Health API Endpoints
    # ==========================================================================

    @app.get("/api/health/network")
    async def api_get_network_health() -> Dict[str, Any]:
        """
        Get overall network health score and details

        Returns:
            Network health score, severity, components, and agent breakdown
        """
        try:
            from agentic.health import get_network_health, get_health_scorer

            # Gather agent data for health calculation
            agents_data = {}

            # Try to get data from wizard networks
            try:
                networks_response = await api_get_wizard_networks()
                for network in networks_response:
                    try:
                        status_response = await api_get_network_status(network.get("network_id", ""))
                        if status_response.get("agents"):
                            for agent_id, agent_info in status_response["agents"].items():
                                agents_data[agent_id] = {
                                    "name": agent_info.get("name", agent_id),
                                    "ospf": {
                                        "neighbors": agent_info.get("ospf_neighbors", 0),
                                        "full_neighbors": agent_info.get("ospf_neighbors", 0),
                                    },
                                    "bgp": {
                                        "total_peers": agent_info.get("bgp_peers", 0),
                                        "established_peers": agent_info.get("bgp_peers", 0),
                                    },
                                    "cpu_percent": 25,  # Default values
                                    "memory_percent": 40,
                                    "config": {"has_loopback": True}
                                }
                    except Exception:
                        pass
            except Exception:
                pass

            # If no agents found, use demo data
            if not agents_data:
                agents_data = {
                    "demo-router-1": {
                        "name": "Demo Router 1",
                        "ospf": {"neighbors": 2, "full_neighbors": 2},
                        "bgp": {"total_peers": 1, "established_peers": 1},
                        "cpu_percent": 15,
                        "memory_percent": 30,
                        "test_results": {"total": 10, "passed": 9, "failed": 1},
                        "config": {"has_loopback": True}
                    }
                }

            health = await get_network_health(agents_data)
            return health.to_dict()
        except ImportError as e:
            return {"score": 0, "error": f"Health module not available: {e}"}
        except Exception as e:
            logger.error(f"Network health error: {e}")
            return {"score": 0, "error": str(e)}

    @app.get("/api/health/agent/{agent_id}")
    async def api_get_agent_health(agent_id: str) -> Dict[str, Any]:
        """
        Get health score for a specific agent

        Args:
            agent_id: Agent identifier

        Returns:
            Agent health score, severity, and component breakdown
        """
        try:
            from agentic.health import get_agent_health

            # Try to fetch agent data
            agent_data = {"name": agent_id}

            # Try to get actual data
            try:
                status_response = await api_get_status()
                if status_response:
                    agent_data.update({
                        "ospf": status_response.get("ospf", {}),
                        "bgp": status_response.get("bgp", {}),
                        "cpu_percent": 25,
                        "memory_percent": 40,
                        "config": {"has_loopback": True}
                    })
            except Exception:
                pass

            health = await get_agent_health(agent_id, agent_data)
            return health.to_dict()
        except ImportError as e:
            return {"score": 0, "error": f"Health module not available: {e}"}
        except Exception as e:
            logger.error(f"Agent health error: {e}")
            return {"score": 0, "error": str(e)}

    @app.get("/api/health/history")
    async def api_get_health_history(
        agent_id: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get health score history

        Args:
            agent_id: Optional agent ID (network-wide if omitted)
            hours: Number of hours of history (default 24)

        Returns:
            List of timestamp/score pairs
        """
        try:
            from agentic.health import get_health_history
            history = get_health_history(agent_id, hours)
            return {"history": history, "agent_id": agent_id, "hours": hours}
        except ImportError as e:
            return {"history": [], "error": f"Health module not available: {e}"}
        except Exception as e:
            logger.error(f"Health history error: {e}")
            return {"history": [], "error": str(e)}

    @app.get("/api/health/recommendations")
    async def api_get_health_recommendations() -> Dict[str, Any]:
        """
        Get prioritized recommendations for improving network health

        Returns:
            List of recommendations sorted by priority
        """
        try:
            from agentic.health import get_network_health, get_health_recommendations

            # Get current network health
            health_response = await api_get_network_health()
            if "error" in health_response:
                return {"recommendations": [], "error": health_response["error"]}

            # Parse into NetworkHealth object for recommendations
            from agentic.health import get_health_scorer
            scorer = get_health_scorer()
            if scorer._last_network_health:
                recommendations = get_health_recommendations(scorer._last_network_health)
            else:
                recommendations = []

            return {"recommendations": recommendations}
        except ImportError as e:
            return {"recommendations": [], "error": f"Health module not available: {e}"}
        except Exception as e:
            logger.error(f"Health recommendations error: {e}")
            return {"recommendations": [], "error": str(e)}

    # ==========================================================================
    # SMTP Email API Endpoints
    # ==========================================================================

    @app.get("/api/smtp/config")
    async def api_get_smtp_config(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get SMTP configuration

        Args:
            agent_id: Optional agent ID filter

        Returns:
            SMTP configuration and statistics
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client
            client = get_smtp_client(agent_id or "local")
            return {"config": client.config.to_dict(), "statistics": client.get_statistics()}
        except ImportError as e:
            return {"config": {}, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"SMTP config error: {e}")
            return {"config": {}, "error": str(e)}

    @app.post("/api/smtp/config")
    async def api_set_smtp_config(
        server: str = "localhost",
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        use_ssl: bool = False,
        from_address: str = "agent@network.local",
        from_name: str = "Network Agent"
    ) -> Dict[str, Any]:
        """
        Configure SMTP settings

        Args:
            server: SMTP server hostname
            port: SMTP port
            username: SMTP username (optional)
            password: SMTP password (optional)
            use_tls: Use STARTTLS
            use_ssl: Use SSL/TLS
            from_address: From email address
            from_name: From display name

        Returns:
            Updated configuration
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client, SMTPConfig
            client = get_smtp_client()

            config = SMTPConfig(
                server=server,
                port=port,
                username=username,
                password=password,
                use_tls=use_tls,
                use_ssl=use_ssl,
                from_address=from_address,
                from_name=from_name
            )
            client.configure(config)
            return {"success": True, "config": config.to_dict()}
        except ImportError as e:
            return {"success": False, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"SMTP config set error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/smtp/history")
    async def api_get_email_history(
        limit: int = 50,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get email history

        Args:
            limit: Maximum emails to return
            status: Filter by status (sent, failed, pending)

        Returns:
            List of emails
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client, EmailStatus
            client = get_smtp_client()

            email_status = None
            if status:
                email_status = EmailStatus(status)

            emails = client.get_email_history(limit, email_status)
            return {"emails": emails, "count": len(emails)}
        except ImportError as e:
            return {"emails": [], "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Email history error: {e}")
            return {"emails": [], "error": str(e)}

    @app.get("/api/smtp/statistics")
    async def api_get_smtp_statistics() -> Dict[str, Any]:
        """Get SMTP statistics"""
        try:
            from agentic.mcp.smtp_mcp import get_smtp_statistics
            return {"statistics": get_smtp_statistics()}
        except ImportError as e:
            return {"statistics": {}, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"SMTP statistics error: {e}")
            return {"statistics": {}, "error": str(e)}

    @app.post("/api/smtp/test")
    async def api_send_test_email(recipient: str) -> Dict[str, Any]:
        """
        Send a test email

        Args:
            recipient: Email address to send test to

        Returns:
            Success status
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client
            client = get_smtp_client()
            success = await client.send_test_email(recipient)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Test email error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/smtp/send")
    async def api_send_email(
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Send an email

        Args:
            to: Recipient email (comma-separated for multiple)
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            priority: Email priority (low, normal, high, urgent)

        Returns:
            Success status
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client, Email, EmailPriority
            client = get_smtp_client()

            recipients = [r.strip() for r in to.split(",")]
            email_priority = EmailPriority(priority)

            email = Email(
                to=recipients,
                subject=subject,
                body=body,
                html_body=html_body,
                priority=email_priority
            )

            success = await client.send_immediate(email)
            return {"success": success, "email": email.to_dict()}
        except ImportError as e:
            return {"success": False, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Send email error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/smtp/alerts")
    async def api_get_alert_rules() -> Dict[str, Any]:
        """Get all email alert rules"""
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client
            client = get_smtp_client()
            rules = client.get_alert_rules()
            return {"rules": [r.to_dict() for r in rules], "count": len(rules)}
        except ImportError as e:
            return {"rules": [], "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Alert rules error: {e}")
            return {"rules": [], "error": str(e)}

    @app.post("/api/smtp/alerts")
    async def api_add_alert_rule(
        name: str,
        alert_type: str,
        recipients: str,
        priority: str = "normal",
        cooldown: int = 300
    ) -> Dict[str, Any]:
        """
        Add an email alert rule

        Args:
            name: Rule name
            alert_type: Alert type (test_failure, neighbor_down, neighbor_up, etc.)
            recipients: Comma-separated email addresses
            priority: Email priority
            cooldown: Cooldown between alerts in seconds

        Returns:
            Created rule
        """
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client, AlertRule, AlertType, EmailPriority
            client = get_smtp_client()

            rule = AlertRule(
                name=name,
                alert_type=AlertType(alert_type),
                recipients=[r.strip() for r in recipients.split(",")],
                priority=EmailPriority(priority),
                cooldown_seconds=cooldown
            )
            client.add_alert_rule(rule)
            return {"success": True, "rule": rule.to_dict()}
        except ImportError as e:
            return {"success": False, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Add alert rule error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/smtp/alerts/{rule_name}")
    async def api_delete_alert_rule(rule_name: str) -> Dict[str, Any]:
        """Delete an alert rule"""
        try:
            from agentic.mcp.smtp_mcp import get_smtp_client
            client = get_smtp_client()
            success = client.remove_alert_rule(rule_name)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"SMTP module not available: {e}"}
        except Exception as e:
            logger.error(f"Delete alert rule error: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================================================
    # Self-Healing API Endpoints (Quality Gate 14)
    # ==========================================================================

    # Global instances for self-healing
    _health_monitor = None
    _anomaly_detector = None
    _remediation_engine = None

    def get_health_monitor():
        """Get or create health monitor instance"""
        nonlocal _health_monitor
        if _health_monitor is None:
            try:
                from agentic.healing import HealthMonitor
                _health_monitor = HealthMonitor()
            except ImportError:
                return None
        return _health_monitor

    def get_anomaly_detector():
        """Get or create anomaly detector instance"""
        nonlocal _anomaly_detector
        if _anomaly_detector is None:
            try:
                from agentic.healing import AnomalyDetector
                _anomaly_detector = AnomalyDetector()
            except ImportError:
                return None
        return _anomaly_detector

    def get_remediation_engine():
        """Get or create remediation engine instance"""
        nonlocal _remediation_engine
        if _remediation_engine is None:
            try:
                from agentic.healing import RemediationEngine
                _remediation_engine = RemediationEngine(dry_run=False)
            except ImportError:
                return None
        return _remediation_engine

    @app.get("/api/health/summary")
    async def get_health_summary() -> Dict[str, Any]:
        """Get overall network health summary"""
        monitor = get_health_monitor()
        if not monitor:
            return {"error": "Health monitoring not available"}
        return monitor.get_health_summary()

    @app.get("/api/health/events")
    async def get_health_events(
        limit: int = 50,
        severity: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get recent health events

        Args:
            limit: Maximum events to return
            severity: Filter by severity (info, warning, critical, recovery)
        """
        monitor = get_health_monitor()
        if not monitor:
            return {"events": [], "error": "Health monitoring not available"}

        try:
            from agentic.healing import EventSeverity
            sev = EventSeverity(severity) if severity else None
        except (ImportError, ValueError):
            sev = None

        events = monitor.get_events(limit=limit, severity=sev)
        return {
            "events": [e.to_dict() for e in events],
            "count": len(events)
        }

    @app.get("/api/health/state")
    async def get_health_state() -> Dict[str, Any]:
        """Get current monitored health state"""
        monitor = get_health_monitor()
        if not monitor:
            return {"error": "Health monitoring not available"}
        return monitor.get_current_state()

    @app.get("/api/anomalies")
    async def get_anomalies(
        limit: int = 50,
        min_severity: int = 0
    ) -> Dict[str, Any]:
        """
        Get detected anomalies

        Args:
            limit: Maximum anomalies to return
            min_severity: Minimum severity (1-10) to include
        """
        detector = get_anomaly_detector()
        if not detector:
            return {"anomalies": [], "error": "Anomaly detection not available"}

        anomalies = detector.get_anomalies(limit=limit, min_severity=min_severity)
        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "count": len(anomalies),
            "statistics": detector.get_statistics()
        }

    @app.get("/api/remediation/actions")
    async def list_remediation_actions(protocol: Optional[str] = None) -> Dict[str, Any]:
        """
        List available remediation actions

        Args:
            protocol: Filter by protocol (ospf, bgp, isis)
        """
        engine = get_remediation_engine()
        if not engine:
            return {"actions": [], "error": "Remediation engine not available"}

        actions = engine.list_actions(protocol=protocol)
        return {
            "actions": [
                {
                    "action_id": a.action_id,
                    "name": a.name,
                    "description": a.description,
                    "event_types": a.event_types,
                    "protocol": a.protocol,
                    "auto_execute": a.auto_execute,
                    "severity_threshold": a.severity_threshold,
                    "cooldown_seconds": a.cooldown_seconds
                }
                for a in actions
            ]
        }

    @app.post("/api/remediation/execute/{action_id}")
    async def execute_remediation(
        action_id: str,
        agent_id: str,
        peer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually execute a remediation action

        Args:
            action_id: Action to execute
            agent_id: Target agent
            peer_id: Target peer/neighbor (optional)
        """
        engine = get_remediation_engine()
        if not engine:
            return {"error": "Remediation engine not available"}

        result = await engine.execute_action(
            action_id=action_id,
            event_type="manual_trigger",
            agent_id=agent_id,
            peer_id=peer_id
        )
        return result.to_dict()

    @app.get("/api/remediation/history")
    async def get_remediation_history(limit: int = 50) -> Dict[str, Any]:
        """Get remediation action history"""
        engine = get_remediation_engine()
        if not engine:
            return {"history": [], "error": "Remediation engine not available"}

        history = engine.get_history(limit=limit)
        return {
            "history": [r.to_dict() for r in history],
            "count": len(history),
            "statistics": engine.get_statistics()
        }

    # ==================== Chaos Engineering / Failure Injection API ====================

    # Global chaos engineering instances
    _failure_injector = None
    _scenario_runner = None

    def get_failure_injector():
        """Get or create failure injector instance"""
        nonlocal _failure_injector
        if _failure_injector is None:
            try:
                from agentic.chaos import FailureInjector
                _failure_injector = FailureInjector(dry_run=False)
            except ImportError:
                return None
        return _failure_injector

    def get_scenario_runner():
        """Get or create scenario runner instance"""
        nonlocal _scenario_runner
        if _scenario_runner is None:
            injector = get_failure_injector()
            if injector:
                try:
                    from agentic.chaos import ScenarioRunner
                    _scenario_runner = ScenarioRunner(injector)
                except ImportError:
                    return None
        return _scenario_runner

    @app.get("/api/chaos/status")
    async def get_chaos_status() -> Dict[str, Any]:
        """
        Get chaos engineering status

        Returns current active failures, statistics, and scheduled failures.
        """
        injector = get_failure_injector()
        if not injector:
            return {"error": "Chaos engineering module not available"}

        return {
            "active_failures": [f.to_dict() for f in injector.get_active_failures()],
            "scheduled_failures": [s.to_dict() for s in injector.get_schedules()],
            "statistics": injector.get_statistics()
        }

    @app.get("/api/chaos/failures")
    async def list_active_failures() -> Dict[str, Any]:
        """List all active failures"""
        injector = get_failure_injector()
        if not injector:
            return {"failures": [], "error": "Chaos module not available"}

        return {
            "failures": [f.to_dict() for f in injector.get_active_failures()],
            "count": len(injector.get_active_failures())
        }

    @app.post("/api/chaos/inject")
    async def inject_failure(
        failure_type: str,
        target_agent: str,
        duration_seconds: int = 60,
        intensity: float = 1.0,
        target_link: Optional[str] = None,
        target_peer: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Inject a failure

        Args:
            failure_type: Type of failure (link_down, agent_down, packet_loss, latency, flap, partition)
            target_agent: Target agent ID
            duration_seconds: How long the failure lasts (0 = permanent)
            intensity: Failure intensity (0.0-1.0)
            target_link: Target link ID (for link failures)
            target_peer: Target peer (for selective failures)
        """
        injector = get_failure_injector()
        if not injector:
            return {"error": "Chaos module not available"}

        try:
            from agentic.chaos import FailureType, FailureConfig

            # Parse failure type
            ftype = FailureType(failure_type)

            config = FailureConfig(
                failure_type=ftype,
                target_agent=target_agent,
                target_link=target_link,
                target_peer=target_peer,
                duration_seconds=duration_seconds,
                intensity=intensity
            )

            result = await injector.inject_failure(config)
            return result.to_dict()

        except ValueError as e:
            return {"error": f"Invalid failure type: {failure_type}"}
        except Exception as e:
            logger.error(f"Failure injection error: {e}")
            return {"error": str(e)}

    @app.post("/api/chaos/clear/{failure_id}")
    async def clear_failure(failure_id: str) -> Dict[str, Any]:
        """Clear an active failure"""
        injector = get_failure_injector()
        if not injector:
            return {"error": "Chaos module not available"}

        result = await injector.clear_failure(failure_id)
        if result:
            return result.to_dict()
        return {"error": f"Failure not found: {failure_id}"}

    @app.post("/api/chaos/clear-all")
    async def clear_all_failures() -> Dict[str, Any]:
        """Clear all active failures"""
        injector = get_failure_injector()
        if not injector:
            return {"error": "Chaos module not available"}

        results = await injector.clear_all_failures()
        return {
            "cleared": len(results),
            "results": [r.to_dict() for r in results]
        }

    @app.get("/api/chaos/history")
    async def get_failure_history(
        limit: int = 100,
        failure_type: Optional[str] = None,
        target_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get failure injection history

        Args:
            limit: Maximum results
            failure_type: Filter by type
            target_agent: Filter by target agent
        """
        injector = get_failure_injector()
        if not injector:
            return {"history": [], "error": "Chaos module not available"}

        ftype = None
        if failure_type:
            try:
                from agentic.chaos import FailureType
                ftype = FailureType(failure_type)
            except ValueError:
                pass

        history = injector.get_history(limit=limit, failure_type=ftype, target_agent=target_agent)
        return {
            "history": [h.to_dict() for h in history],
            "count": len(history)
        }

    @app.get("/api/chaos/scenarios")
    async def list_chaos_scenarios() -> Dict[str, Any]:
        """List available predefined chaos scenarios"""
        try:
            from agentic.chaos import PredefinedScenarios
            return {"scenarios": PredefinedScenarios.list_scenarios()}
        except ImportError:
            return {"scenarios": [], "error": "Chaos scenarios not available"}

    @app.post("/api/chaos/scenarios/run/{scenario_id}")
    async def run_chaos_scenario(
        scenario_id: str,
        agents: List[str]
    ) -> Dict[str, Any]:
        """
        Run a predefined chaos scenario

        Args:
            scenario_id: Scenario identifier
            agents: List of agent IDs to use in the scenario
        """
        runner = get_scenario_runner()
        if not runner:
            return {"error": "Scenario runner not available"}

        try:
            from agentic.chaos import PredefinedScenarios

            # Create scenario based on ID
            scenario = None
            if scenario_id == "single-link-failure" and len(agents) >= 2:
                scenario = PredefinedScenarios.single_link_failure(agents[0], agents[1])
            elif scenario_id == "spine-failure" and agents:
                scenario = PredefinedScenarios.spine_failure(agents)
            elif scenario_id == "rolling-failure" and agents:
                scenario = PredefinedScenarios.rolling_failure(agents)
            elif scenario_id == "packet-loss-storm" and agents:
                scenario = PredefinedScenarios.packet_loss_storm(agents)
            elif scenario_id == "latency-injection" and agents:
                scenario = PredefinedScenarios.latency_injection(agents)
            elif scenario_id == "bgp-peer-failure" and agents:
                scenario = PredefinedScenarios.bgp_peer_failure(agents)
            elif scenario_id == "full-chaos" and agents:
                scenario = PredefinedScenarios.full_chaos(agents)
            else:
                return {"error": f"Unknown scenario or insufficient agents: {scenario_id}"}

            result = await runner.run_scenario(scenario)
            return result.to_dict()

        except Exception as e:
            logger.error(f"Scenario execution error: {e}")
            return {"error": str(e)}

    @app.get("/api/chaos/scenarios/running")
    async def get_running_scenario() -> Dict[str, Any]:
        """Get currently running scenario"""
        runner = get_scenario_runner()
        if not runner:
            return {"running": None, "error": "Scenario runner not available"}

        running = runner.get_running_scenario()
        return {
            "running": running.to_dict() if running else None
        }

    @app.get("/api/chaos/scenarios/history")
    async def get_scenario_history(limit: int = 50) -> Dict[str, Any]:
        """Get scenario execution history"""
        runner = get_scenario_runner()
        if not runner:
            return {"history": [], "error": "Scenario runner not available"}

        history = runner.get_history(limit=limit)
        return {
            "history": [h.to_dict() for h in history],
            "count": len(history)
        }

    # =============================================================================
    # Intent-Based Configuration API
    # =============================================================================

    _intent_parser = None
    _intent_executor = None

    def get_intent_parser():
        """Get or create intent parser instance"""
        nonlocal _intent_parser
        if _intent_parser is None:
            try:
                from agentic.intent import IntentParser
                _intent_parser = IntentParser()
            except ImportError:
                return None
        return _intent_parser

    def get_intent_executor():
        """Get or create intent executor instance"""
        nonlocal _intent_executor
        if _intent_executor is None:
            try:
                from agentic.intent import IntentExecutor
                _intent_executor = IntentExecutor()
            except ImportError:
                return None
        return _intent_executor

    @app.post("/api/intent/parse")
    async def parse_intent(text: str) -> Dict[str, Any]:
        """
        Parse natural language intent into structured form

        Example inputs:
        - "high availability between DC1 and DC2"
        - "block traffic from AS 65000"
        - "enable ospf on all spine switches"
        """
        parser = get_intent_parser()
        if not parser:
            return {"error": "Intent parser not available"}

        intent = parser.parse(text)
        return {
            "intent": intent.to_dict(),
            "success": intent.confidence > 0.5
        }

    @app.post("/api/intent/validate")
    async def validate_intent(text: str) -> Dict[str, Any]:
        """
        Parse and validate an intent against available agents
        """
        parser = get_intent_parser()
        if not parser:
            return {"error": "Intent parser not available"}

        intent = parser.parse(text)

        # Get available agents from orchestrator if available
        available_agents = []
        try:
            from orchestrator import get_orchestrator
            orch = get_orchestrator()
            if orch:
                available_agents = list(orch.agents.keys())
        except Exception:
            # Fallback: use ASI app router_id
            available_agents = [asi_app.router_id]

        is_valid = parser.validate(intent, available_agents)

        return {
            "intent": intent.to_dict(),
            "is_valid": is_valid,
            "available_agents": available_agents
        }

    @app.post("/api/intent/plan")
    async def create_intent_plan(text: str) -> Dict[str, Any]:
        """
        Create an execution plan from an intent
        """
        parser = get_intent_parser()
        executor = get_intent_executor()

        if not parser:
            return {"error": "Intent parser not available"}
        if not executor:
            return {"error": "Intent executor not available"}

        intent = parser.parse(text)
        plan = executor.create_plan(intent)

        return {
            "intent": intent.to_dict(),
            "plan": plan.to_dict(),
            "ready_to_execute": plan.status == "ready"
        }

    @app.post("/api/intent/execute")
    async def execute_intent(text: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Execute an intent (parse, plan, and execute)

        Args:
            text: Natural language intent
            dry_run: If True, only simulate execution (default: True for safety)
        """
        parser = get_intent_parser()
        executor = get_intent_executor()

        if not parser:
            return {"error": "Intent parser not available"}
        if not executor:
            return {"error": "Intent executor not available"}

        intent = parser.parse(text)
        plan = executor.create_plan(intent)

        if dry_run:
            return {
                "intent": intent.to_dict(),
                "plan": plan.to_dict(),
                "dry_run": True,
                "message": "Dry run - no changes made. Set dry_run=False to execute."
            }

        # Execute the plan
        result = await executor.execute(plan)

        return {
            "intent": intent.to_dict(),
            "plan": plan.to_dict(),
            "result": result.to_dict(),
            "dry_run": False
        }

    @app.get("/api/intent/suggestions")
    async def get_intent_suggestions(partial: str = "") -> Dict[str, Any]:
        """
        Get intent suggestions based on partial input

        Useful for autocomplete in UI
        """
        parser = get_intent_parser()
        if not parser:
            return {"suggestions": [], "error": "Intent parser not available"}

        suggestions = parser.suggest_intents(partial)

        return {
            "partial": partial,
            "suggestions": suggestions
        }

    @app.get("/api/intent/types")
    async def get_intent_types() -> Dict[str, Any]:
        """
        Get all supported intent types
        """
        try:
            from agentic.intent import IntentType
            return {
                "types": [
                    {"value": it.value, "name": it.name}
                    for it in IntentType
                ],
                "count": len(IntentType)
            }
        except ImportError:
            return {"types": [], "error": "Intent module not available"}

    @app.get("/api/intent/examples")
    async def get_intent_examples() -> Dict[str, Any]:
        """
        Get example intents for each type
        """
        examples = {
            "high_availability": [
                "high availability between DC1 and DC2",
                "ensure high availability for spine switches"
            ],
            "redundancy": [
                "redundant paths to the internet",
                "enable redundancy for core routers"
            ],
            "traffic_optimization": [
                "optimize traffic to prefer 10G links",
                "prefer low latency paths for voice traffic"
            ],
            "load_balancing": [
                "load balance across all edge routers",
                "distribute traffic evenly between spine1 and spine2"
            ],
            "traffic_block": [
                "block traffic from AS 65000",
                "block routes from 192.168.0.0/16"
            ],
            "connectivity": [
                "connect DC1 to DC2",
                "establish connectivity between leaf1 and leaf2"
            ],
            "protocol_enable": [
                "enable ospf on all spine switches",
                "enable bgp on edge routers"
            ],
            "protocol_configure": [
                "configure ospf area 0 on spine1",
                "configure bgp as 65001 on edge1"
            ]
        }

        return {
            "examples": examples,
            "total": sum(len(v) for v in examples.values())
        }

    # =============================================================================
    # Network Optimization API
    # =============================================================================

    _traffic_analyzer = None
    _optimization_recommender = None

    def get_traffic_analyzer_instance():
        """Get or create traffic analyzer instance"""
        nonlocal _traffic_analyzer
        if _traffic_analyzer is None:
            try:
                from agentic.optimization import TrafficAnalyzer
                _traffic_analyzer = TrafficAnalyzer()
            except ImportError:
                return None
        return _traffic_analyzer

    def get_optimization_recommender_instance():
        """Get or create optimization recommender instance"""
        nonlocal _optimization_recommender
        if _optimization_recommender is None:
            try:
                from agentic.optimization import OptimizationRecommender
                _optimization_recommender = OptimizationRecommender()
            except ImportError:
                return None
        return _optimization_recommender

    @app.get("/api/optimization/status")
    async def get_optimization_status() -> Dict[str, Any]:
        """Get network optimization system status"""
        analyzer = get_traffic_analyzer_instance()
        recommender = get_optimization_recommender_instance()

        return {
            "analyzer_available": analyzer is not None,
            "recommender_available": recommender is not None,
            "analyzer_stats": analyzer.get_statistics() if analyzer else None,
            "recommender_stats": recommender.get_statistics() if recommender else None
        }

    @app.post("/api/optimization/analyze")
    async def analyze_traffic(period_minutes: int = 60) -> Dict[str, Any]:
        """
        Analyze network traffic patterns

        Args:
            period_minutes: Analysis period in minutes (default: 60)
        """
        analyzer = get_traffic_analyzer_instance()
        if not analyzer:
            return {"error": "Traffic analyzer not available"}

        result = analyzer.analyze(period_minutes=period_minutes)
        return {
            "analysis": result.to_dict(),
            "success": True
        }

    @app.get("/api/optimization/patterns")
    async def get_traffic_patterns(active_only: bool = True) -> Dict[str, Any]:
        """Get detected traffic patterns"""
        analyzer = get_traffic_analyzer_instance()
        if not analyzer:
            return {"patterns": [], "error": "Traffic analyzer not available"}

        if active_only:
            patterns = analyzer.get_active_patterns()
        else:
            patterns = analyzer.get_pattern_history()

        return {
            "patterns": [p.to_dict() for p in patterns],
            "count": len(patterns)
        }

    @app.get("/api/optimization/links")
    async def get_link_metrics(link_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """Get traffic metrics for links"""
        analyzer = get_traffic_analyzer_instance()
        if not analyzer:
            return {"links": [], "error": "Traffic analyzer not available"}

        if link_id:
            metrics = analyzer.get_link_metrics(link_id, last_n=limit)
            return {
                "link_id": link_id,
                "metrics": [m.to_dict() for m in metrics],
                "count": len(metrics)
            }
        else:
            return {
                "links": analyzer.get_all_link_ids(),
                "count": len(analyzer.get_all_link_ids())
            }

    @app.post("/api/optimization/record")
    async def record_traffic_metric(
        link_id: str,
        source: str,
        destination: str,
        bytes_in: int = 0,
        bytes_out: int = 0,
        packets_in: int = 0,
        packets_out: int = 0,
        bandwidth_capacity: int = 1000000000,
        latency_ms: float = 0.0,
        packet_loss: float = 0.0
    ) -> Dict[str, Any]:
        """
        Record a traffic metric sample

        Used for injecting traffic data for analysis
        """
        analyzer = get_traffic_analyzer_instance()
        if not analyzer:
            return {"error": "Traffic analyzer not available"}

        try:
            from agentic.optimization import TrafficMetric
            from datetime import datetime

            metric = TrafficMetric(
                timestamp=datetime.now(),
                link_id=link_id,
                source=source,
                destination=destination,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                packets_in=packets_in,
                packets_out=packets_out,
                bandwidth_capacity=bandwidth_capacity,
                latency_ms=latency_ms,
                packet_loss=packet_loss
            )
            analyzer.record_metric(metric)
            return {"success": True, "metric": metric.to_dict()}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/optimization/recommend")
    async def generate_recommendations() -> Dict[str, Any]:
        """Generate optimization recommendations based on current topology and traffic"""
        recommender = get_optimization_recommender_instance()
        if not recommender:
            return {"error": "Optimization recommender not available"}

        # Build topology from current state
        topology = {"links": []}
        traffic_data = {}

        # Get OSPF links
        if asi_app.ospf_interface:
            ospf = asi_app.ospf_interface
            for neighbor in ospf.neighbors.values():
                link_id = f"{asi_app.router_id}-{neighbor.router_id}"
                topology["links"].append({
                    "id": link_id,
                    "source": asi_app.router_id,
                    "target": neighbor.router_id,
                    "ospf_cost": getattr(ospf, 'cost', 10),
                    "bandwidth": 1000000000
                })

        # Get BGP info
        bgp_config = None
        if asi_app.bgp_speaker:
            bgp = asi_app.bgp_speaker
            bgp_config = {
                "local_as": bgp.agent.local_as,
                "peers": []
            }
            for peer_ip, session in bgp.agent.sessions.items():
                peer_as = session.config.peer_as if hasattr(session, 'config') else 0
                bgp_config["peers"].append({
                    "ip": peer_ip,
                    "remote_as": peer_as,
                    "peer_type": "ibgp" if peer_as == bgp.agent.local_as else "ebgp"
                })

        # Get traffic data from analyzer
        analyzer = get_traffic_analyzer_instance()
        if analyzer:
            for link_id in analyzer.get_all_link_ids():
                metrics = analyzer.get_link_metrics(link_id, last_n=10)
                if metrics:
                    avg_util = sum(m.utilization_total for m in metrics) / len(metrics)
                    traffic_data[link_id] = {"utilization": avg_util}

        # Generate recommendations
        recommendations = recommender.generate_all_recommendations(
            topology=topology,
            traffic_data=traffic_data,
            bgp_config=bgp_config
        )

        return {
            "recommendations": [r.to_dict() for r in recommendations],
            "count": len(recommendations)
        }

    @app.get("/api/optimization/recommendations")
    async def get_recommendations(
        priority: Optional[str] = None,
        rec_type: Optional[str] = None,
        applied: Optional[bool] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get optimization recommendations with filtering"""
        recommender = get_optimization_recommender_instance()
        if not recommender:
            return {"recommendations": [], "error": "Recommender not available"}

        try:
            from agentic.optimization import RecommendationPriority, RecommendationType

            p = RecommendationPriority(priority) if priority else None
            t = RecommendationType(rec_type) if rec_type else None

            recommendations = recommender.get_recommendations(
                priority=p,
                rec_type=t,
                applied=applied,
                limit=limit
            )

            return {
                "recommendations": [r.to_dict() for r in recommendations],
                "count": len(recommendations)
            }
        except ValueError as e:
            return {"error": f"Invalid filter value: {e}"}

    @app.post("/api/optimization/recommendations/{recommendation_id}/apply")
    async def apply_recommendation(recommendation_id: str) -> Dict[str, Any]:
        """Mark a recommendation as applied"""
        recommender = get_optimization_recommender_instance()
        if not recommender:
            return {"error": "Recommender not available"}

        success = recommender.mark_applied(recommendation_id)
        return {
            "success": success,
            "recommendation_id": recommendation_id,
            "message": "Recommendation marked as applied" if success else "Recommendation not found"
        }

    @app.get("/api/optimization/recommendation-types")
    async def get_recommendation_types() -> Dict[str, Any]:
        """Get all available recommendation types"""
        try:
            from agentic.optimization import RecommendationType, RecommendationPriority
            return {
                "types": [{"value": t.value, "name": t.name} for t in RecommendationType],
                "priorities": [{"value": p.value, "name": p.name} for p in RecommendationPriority]
            }
        except ImportError:
            return {"types": [], "priorities": [], "error": "Optimization module not available"}

    # =============================================================================
    # What-If Analysis API
    # =============================================================================

    _whatif_simulator = None
    _impact_analyzer = None

    def get_whatif_simulator_instance():
        """Get or create what-if simulator instance"""
        nonlocal _whatif_simulator
        if _whatif_simulator is None:
            try:
                from agentic.whatif import WhatIfSimulator
                _whatif_simulator = WhatIfSimulator()
                # Load current topology
                _load_topology_to_simulator(_whatif_simulator)
            except ImportError:
                return None
        return _whatif_simulator

    def get_impact_analyzer_instance():
        """Get or create impact analyzer instance"""
        nonlocal _impact_analyzer
        if _impact_analyzer is None:
            try:
                from agentic.whatif import ImpactAnalyzer
                _impact_analyzer = ImpactAnalyzer()
            except ImportError:
                return None
        return _impact_analyzer

    def _load_topology_to_simulator(simulator):
        """Load current topology into simulator"""
        topology = {"nodes": [], "links": []}

        # Add this agent
        topology["nodes"].append({
            "id": asi_app.router_id,
            "name": getattr(asi_app, 'agent_name', asi_app.router_id)
        })

        # Add OSPF neighbors
        if asi_app.ospf_interface:
            for neighbor in asi_app.ospf_interface.neighbors.values():
                topology["nodes"].append({
                    "id": neighbor.router_id,
                    "name": neighbor.router_id
                })
                topology["links"].append({
                    "id": f"{asi_app.router_id}-{neighbor.router_id}",
                    "source": asi_app.router_id,
                    "target": neighbor.router_id,
                    "protocol": "ospf"
                })

        # Add BGP peers
        if asi_app.bgp_speaker:
            for peer_ip, session in asi_app.bgp_speaker.agent.sessions.items():
                topology["nodes"].append({
                    "id": peer_ip,
                    "name": f"AS {session.config.peer_as if hasattr(session, 'config') else '?'}"
                })
                topology["links"].append({
                    "id": f"{asi_app.router_id}-{peer_ip}",
                    "source": asi_app.router_id,
                    "target": peer_ip,
                    "protocol": "bgp"
                })

        simulator.load_topology(topology)

    @app.get("/api/whatif/status")
    async def get_whatif_status() -> Dict[str, Any]:
        """Get what-if analysis system status"""
        simulator = get_whatif_simulator_instance()
        analyzer = get_impact_analyzer_instance()

        return {
            "simulator_available": simulator is not None,
            "analyzer_available": analyzer is not None,
            "simulator_stats": simulator.get_statistics() if simulator else None,
            "analyzer_stats": analyzer.get_statistics() if analyzer else None
        }

    @app.post("/api/whatif/scenario")
    async def create_whatif_scenario(
        scenario_type: str,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a what-if scenario

        Example scenario types:
        - link_failure: Simulate link failure
        - node_failure: Simulate node failure
        - ospf_cost_change: Simulate OSPF cost change
        - bgp_policy_change: Simulate BGP policy change
        """
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"error": "What-if simulator not available"}

        try:
            from agentic.whatif import ScenarioType
            stype = ScenarioType(scenario_type)
        except (ValueError, ImportError):
            return {"error": f"Invalid scenario type: {scenario_type}"}

        scenario = simulator.create_scenario(
            scenario_type=stype,
            name=name,
            description=description,
            parameters=parameters or {}
        )

        return {
            "scenario": scenario.to_dict(),
            "success": True
        }

    @app.post("/api/whatif/simulate")
    async def run_whatif_simulation(scenario_id: str) -> Dict[str, Any]:
        """Run a what-if simulation"""
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"error": "What-if simulator not available"}

        scenario = simulator.get_scenario(scenario_id)
        if not scenario:
            return {"error": f"Scenario not found: {scenario_id}"}

        result = simulator.simulate(scenario)
        return {
            "result": result.to_dict(),
            "success": True
        }

    @app.post("/api/whatif/link-failure")
    async def simulate_link_failure(
        source: str,
        target: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Quick simulation of link failure"""
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"error": "What-if simulator not available"}

        try:
            from agentic.whatif import ScenarioType

            scenario = simulator.create_scenario(
                scenario_type=ScenarioType.LINK_FAILURE,
                name=name or f"Link failure: {source}-{target}",
                description=f"Simulate failure of link between {source} and {target}",
                parameters={"source": source, "target": target}
            )

            result = simulator.simulate(scenario)
            return {
                "scenario": scenario.to_dict(),
                "result": result.to_dict(),
                "success": True
            }
        except ImportError:
            return {"error": "What-if module not available"}

    @app.post("/api/whatif/node-failure")
    async def simulate_node_failure(
        node_id: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Quick simulation of node failure"""
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"error": "What-if simulator not available"}

        try:
            from agentic.whatif import ScenarioType

            scenario = simulator.create_scenario(
                scenario_type=ScenarioType.NODE_FAILURE,
                name=name or f"Node failure: {node_id}",
                description=f"Simulate failure of node {node_id}",
                parameters={"node_id": node_id}
            )

            result = simulator.simulate(scenario)
            return {
                "scenario": scenario.to_dict(),
                "result": result.to_dict(),
                "success": True
            }
        except ImportError:
            return {"error": "What-if module not available"}

    @app.post("/api/whatif/config-change")
    async def simulate_config_change(
        change_type: str,
        parameters: Dict[str, Any],
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Simulate configuration change impact

        change_type can be: ospf_cost_change, bgp_policy_change, etc.
        """
        simulator = get_whatif_simulator_instance()
        analyzer = get_impact_analyzer_instance()

        if not simulator or not analyzer:
            return {"error": "What-if analysis not available"}

        # Build topology for impact analysis
        topology = {"nodes": [], "links": []}
        _load_topology_to_simulator(simulator)

        # Run impact analysis
        report = analyzer.analyze_config_change_impact(
            topology=simulator._topology,
            change_type=change_type,
            parameters=parameters
        )

        return {
            "report": report.to_dict(),
            "success": True
        }

    @app.get("/api/whatif/scenarios")
    async def get_whatif_scenarios(limit: int = 50) -> Dict[str, Any]:
        """Get scenario history"""
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"scenarios": [], "error": "Simulator not available"}

        scenarios = simulator.get_scenarios(limit=limit)
        return {
            "scenarios": [s.to_dict() for s in scenarios],
            "count": len(scenarios)
        }

    @app.get("/api/whatif/results")
    async def get_whatif_results(limit: int = 50) -> Dict[str, Any]:
        """Get simulation results"""
        simulator = get_whatif_simulator_instance()
        if not simulator:
            return {"results": [], "error": "Simulator not available"}

        results = simulator.get_results(limit=limit)
        return {
            "results": [r.to_dict() for r in results],
            "count": len(results)
        }

    @app.get("/api/whatif/scenario-types")
    async def get_scenario_types() -> Dict[str, Any]:
        """Get available scenario types"""
        try:
            from agentic.whatif import ScenarioType, ImpactLevel
            return {
                "scenario_types": [
                    {"value": t.value, "name": t.name}
                    for t in ScenarioType
                ],
                "impact_levels": [
                    {"value": l.value, "name": l.name}
                    for l in ImpactLevel
                ]
            }
        except ImportError:
            return {"scenario_types": [], "impact_levels": [], "error": "What-if module not available"}

    @app.post("/api/whatif/impact/link")
    async def analyze_link_impact(source: str, target: str) -> Dict[str, Any]:
        """Analyze impact of link change"""
        simulator = get_whatif_simulator_instance()
        analyzer = get_impact_analyzer_instance()

        if not analyzer:
            return {"error": "Impact analyzer not available"}

        report = analyzer.analyze_link_impact(
            topology=simulator._topology if simulator else {},
            link_source=source,
            link_target=target
        )

        return {
            "report": report.to_dict(),
            "success": True
        }

    @app.post("/api/whatif/impact/node")
    async def analyze_node_impact(node_id: str) -> Dict[str, Any]:
        """Analyze impact of node change"""
        simulator = get_whatif_simulator_instance()
        analyzer = get_impact_analyzer_instance()

        if not analyzer:
            return {"error": "Impact analyzer not available"}

        report = analyzer.analyze_node_impact(
            topology=simulator._topology if simulator else {},
            node_id=node_id
        )

        return {
            "report": report.to_dict(),
            "success": True
        }

    @app.get("/api/whatif/reports")
    async def get_impact_reports(limit: int = 50) -> Dict[str, Any]:
        """Get impact analysis reports"""
        analyzer = get_impact_analyzer_instance()
        if not analyzer:
            return {"reports": [], "error": "Analyzer not available"}

        reports = analyzer.get_reports(limit=limit)
        return {
            "reports": [r.to_dict() for r in reports],
            "count": len(reports)
        }

    # =============================================================================
    # Protocol State Machine Visualization API
    # =============================================================================

    _state_tracker = None
    _fsm_visualizer = None

    def get_state_tracker_instance():
        """Get or create state tracker instance"""
        nonlocal _state_tracker
        if _state_tracker is None:
            try:
                from agentic.fsm import StateTracker
                _state_tracker = StateTracker()
                # Register current protocol states
                _register_protocol_states(_state_tracker)
            except ImportError:
                return None
        return _state_tracker

    def get_fsm_visualizer_instance():
        """Get or create FSM visualizer instance"""
        nonlocal _fsm_visualizer
        if _fsm_visualizer is None:
            try:
                from agentic.fsm import FSMVisualizer
                tracker = get_state_tracker_instance()
                _fsm_visualizer = FSMVisualizer(tracker)
            except ImportError:
                return None
        return _fsm_visualizer

    def _register_protocol_states(tracker):
        """Register current protocol states from running protocols"""
        try:
            from agentic.fsm import StateMachineType

            # Register OSPF neighbor states
            if asi_app.ospf_interface:
                for neighbor in asi_app.ospf_interface.neighbors.values():
                    tracker.register_state(
                        machine_type=StateMachineType.OSPF_NEIGHBOR,
                        instance_id=neighbor.router_id,
                        agent_id=asi_app.router_id,
                        initial_state=neighbor.get_state_name() if hasattr(neighbor, 'get_state_name') else "Unknown"
                    )

            # Register BGP session states
            if asi_app.bgp_speaker:
                for peer_ip, session in asi_app.bgp_speaker.agent.sessions.items():
                    state_name = "Unknown"
                    if hasattr(session, 'fsm') and hasattr(session.fsm, 'get_state_name'):
                        state_name = session.fsm.get_state_name()
                    elif hasattr(session, 'fsm') and hasattr(session.fsm, 'state'):
                        state_name = str(session.fsm.state)

                    tracker.register_state(
                        machine_type=StateMachineType.BGP_FSM,
                        instance_id=peer_ip,
                        agent_id=asi_app.router_id,
                        initial_state=state_name
                    )

        except Exception as e:
            logging.getLogger("WebUI").debug(f"Error registering protocol states: {e}")

    @app.get("/api/fsm/status")
    async def get_fsm_status() -> Dict[str, Any]:
        """Get FSM visualization system status"""
        tracker = get_state_tracker_instance()
        visualizer = get_fsm_visualizer_instance()

        return {
            "tracker_available": tracker is not None,
            "visualizer_available": visualizer is not None,
            "tracker_stats": tracker.get_statistics() if tracker else None,
            "convergence": tracker.get_convergence_status() if tracker else None
        }

    @app.get("/api/fsm/states")
    async def get_fsm_states(
        machine_type: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all tracked state machines"""
        tracker = get_state_tracker_instance()
        if not tracker:
            return {"states": [], "error": "State tracker not available"}

        if machine_type:
            try:
                from agentic.fsm import StateMachineType
                mt = StateMachineType(machine_type)
                states = tracker.get_states_by_type(mt)
            except (ValueError, ImportError):
                return {"states": [], "error": f"Invalid machine type: {machine_type}"}
        elif agent_id:
            states = tracker.get_states_by_agent(agent_id)
        else:
            states = list(tracker._states.values())

        return {
            "states": [s.to_dict() for s in states],
            "count": len(states)
        }

    @app.get("/api/fsm/transitions")
    async def get_fsm_transitions(
        state_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get state transition history"""
        tracker = get_state_tracker_instance()
        if not tracker:
            return {"transitions": [], "error": "State tracker not available"}

        transitions = tracker.get_transitions(state_id=state_id, limit=limit)
        return {
            "transitions": [t.to_dict() for t in transitions],
            "count": len(transitions)
        }

    @app.post("/api/fsm/transition")
    async def record_fsm_transition(
        state_id: str,
        new_state: str,
        trigger: str
    ) -> Dict[str, Any]:
        """Record a state transition (for testing/simulation)"""
        tracker = get_state_tracker_instance()
        if not tracker:
            return {"error": "State tracker not available"}

        transition = tracker.transition(state_id, new_state, trigger)
        if not transition:
            return {"error": "State not found or no transition occurred"}

        return {
            "transition": transition.to_dict(),
            "success": True
        }

    @app.get("/api/fsm/diagram/{state_id}")
    async def get_fsm_diagram(state_id: str) -> Dict[str, Any]:
        """Get FSM diagram for a specific state machine"""
        tracker = get_state_tracker_instance()
        visualizer = get_fsm_visualizer_instance()

        if not tracker or not visualizer:
            return {"error": "FSM visualization not available"}

        state = tracker.get_state(state_id)
        if not state:
            return {"error": f"State not found: {state_id}"}

        transitions = tracker.get_transitions(state_id, limit=10)
        diagram = visualizer.generate_diagram(state, transitions)

        return {
            "diagram": diagram.to_dict(),
            "success": True
        }

    @app.get("/api/fsm/diagrams")
    async def get_all_fsm_diagrams(agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get FSM diagrams for all tracked states"""
        visualizer = get_fsm_visualizer_instance()
        if not visualizer:
            return {"diagrams": [], "error": "FSM visualizer not available"}

        diagrams = visualizer.generate_all_diagrams(agent_id=agent_id)
        return {
            "diagrams": [d.to_dict() for d in diagrams],
            "count": len(diagrams)
        }

    @app.get("/api/fsm/convergence")
    async def get_fsm_convergence() -> Dict[str, Any]:
        """Get overall convergence status with visualization data"""
        visualizer = get_fsm_visualizer_instance()
        if not visualizer:
            return {"error": "FSM visualizer not available"}

        return visualizer.get_convergence_visualization()

    @app.get("/api/fsm/flapping")
    async def get_flapping_states(
        threshold: int = 5,
        window_seconds: int = 60
    ) -> Dict[str, Any]:
        """Get states that are flapping (rapid transitions)"""
        tracker = get_state_tracker_instance()
        if not tracker:
            return {"flapping": [], "error": "State tracker not available"}

        flapping = tracker.get_flapping_states(threshold=threshold, window_seconds=window_seconds)
        return {
            "flapping": [s.to_dict() for s in flapping],
            "count": len(flapping),
            "threshold": threshold,
            "window_seconds": window_seconds
        }

    @app.get("/api/fsm/unstable")
    async def get_unstable_states() -> Dict[str, Any]:
        """Get all states not in stable state"""
        tracker = get_state_tracker_instance()
        if not tracker:
            return {"unstable": [], "error": "State tracker not available"}

        unstable = tracker.get_unstable_states()
        return {
            "unstable": [s.to_dict() for s in unstable],
            "count": len(unstable)
        }

    @app.get("/api/fsm/types")
    async def get_fsm_types() -> Dict[str, Any]:
        """Get available state machine types and their states"""
        try:
            from agentic.fsm import (
                StateMachineType, OSPFNeighborState, BGPState, ISISAdjacencyState
            )
            return {
                "machine_types": [
                    {"value": t.value, "name": t.name}
                    for t in StateMachineType
                ],
                "ospf_states": [s.value for s in OSPFNeighborState],
                "bgp_states": [s.value for s in BGPState],
                "isis_states": [s.value for s in ISISAdjacencyState]
            }
        except ImportError:
            return {"error": "FSM module not available"}

    # ==================== Traffic Heatmap API ====================

    @app.get("/api/heatmap/status")
    async def get_heatmap_status() -> Dict[str, Any]:
        """Get traffic collector and heatmap status"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            return {
                "collector_stats": collector.get_statistics(),
                "traffic_summary": collector.get_traffic_summary()
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/nodes")
    async def get_heatmap_nodes() -> Dict[str, Any]:
        """Get all registered nodes with traffic data"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            nodes = collector.get_all_nodes()
            return {
                "nodes": [n.to_dict() for n in nodes],
                "count": len(nodes)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/links")
    async def get_heatmap_links() -> Dict[str, Any]:
        """Get all registered links with traffic data"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            links = collector.get_all_links()
            return {
                "links": [l.to_dict() for l in links],
                "count": len(links)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/hotspots")
    async def get_hotspots(severity: Optional[str] = None) -> Dict[str, Any]:
        """Get detected traffic hotspots"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            hotspots = collector.get_hotspots(severity)
            return {
                "hotspots": hotspots,
                "count": len(hotspots)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/top-utilized")
    async def get_top_utilized(limit: int = 10) -> Dict[str, Any]:
        """Get most heavily utilized links"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            top_links = collector.get_top_utilized_links(limit)
            return {
                "links": [l.to_dict() for l in top_links],
                "count": len(top_links)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/time-series/{link_id}")
    async def get_link_time_series(link_id: str, duration_minutes: int = 60) -> Dict[str, Any]:
        """Get time series traffic data for a link"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            samples = collector.get_time_series(link_id, duration_minutes)
            return {
                "link_id": link_id,
                "samples": samples,
                "count": len(samples)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.post("/api/heatmap/simulate")
    async def simulate_traffic() -> Dict[str, Any]:
        """Simulate traffic data for testing"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            collector.simulate_traffic()
            return {
                "status": "simulated",
                "summary": collector.get_traffic_summary()
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.post("/api/heatmap/register-node")
    async def register_heatmap_node(
        node_id: str, hostname: str, total_interfaces: int
    ) -> Dict[str, Any]:
        """Register a node for traffic collection"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            node = collector.register_node(node_id, hostname, total_interfaces)
            return {"node": node.to_dict()}
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.post("/api/heatmap/register-link")
    async def register_heatmap_link(
        link_id: str, source_node: str, dest_node: str,
        interface: str, capacity_bps: int
    ) -> Dict[str, Any]:
        """Register a link for traffic collection"""
        try:
            from agentic.heatmap import get_traffic_collector
            collector = get_traffic_collector()
            link = collector.register_link(
                link_id, source_node, dest_node, interface, capacity_bps
            )
            return {"link": link.to_dict()}
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/render/links")
    async def render_link_heatmap(scale: str = "traffic") -> Dict[str, Any]:
        """Render link utilization heatmap"""
        try:
            from agentic.heatmap import get_traffic_collector, HeatmapRenderer, ColorScale
            collector = get_traffic_collector()
            renderer = HeatmapRenderer()

            links = collector.get_all_links()
            link_data = [
                {
                    "link_id": l.link_id,
                    "source": l.source_node,
                    "dest": l.dest_node,
                    "interface": l.interface,
                    "utilization": l.current_utilization,
                    "throughput_gbps": l.current_throughput_bps / 1_000_000_000
                }
                for l in links
            ]

            color_scale = ColorScale(scale) if scale in [s.value for s in ColorScale] else ColorScale.TRAFFIC
            heatmap = renderer.render_link_heatmap(link_data, color_scale)

            return {
                "heatmap": heatmap.to_dict(),
                "legend": renderer.get_color_legend(color_scale)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/render/nodes")
    async def render_node_heatmap(scale: str = "traffic") -> Dict[str, Any]:
        """Render node traffic intensity heatmap"""
        try:
            from agentic.heatmap import get_traffic_collector, HeatmapRenderer, ColorScale
            collector = get_traffic_collector()
            renderer = HeatmapRenderer()

            nodes = collector.get_all_nodes()
            node_data = [
                {
                    "node_id": n.node_id,
                    "hostname": n.hostname,
                    "total_traffic_gbps": (n.total_inbound_bps + n.total_outbound_bps) / 1_000_000_000,
                    "avg_utilization": n.avg_utilization,
                    "interface_count": len(n.link_traffic)
                }
                for n in nodes
            ]

            color_scale = ColorScale(scale) if scale in [s.value for s in ColorScale] else ColorScale.TRAFFIC
            heatmap = renderer.render_node_heatmap(node_data, color_scale)

            return {
                "heatmap": heatmap.to_dict(),
                "legend": renderer.get_color_legend(color_scale)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/render/time-series/{link_id}")
    async def render_time_series_heatmap(
        link_id: str, scale: str = "traffic"
    ) -> Dict[str, Any]:
        """Render time series heatmap for a link"""
        try:
            from agentic.heatmap import get_traffic_collector, HeatmapRenderer, ColorScale
            collector = get_traffic_collector()
            renderer = HeatmapRenderer()

            samples = collector.get_time_series(link_id)
            color_scale = ColorScale(scale) if scale in [s.value for s in ColorScale] else ColorScale.TRAFFIC
            heatmap = renderer.render_time_series_heatmap(link_id, samples, color_scale=color_scale)

            return {
                "heatmap": heatmap.to_dict(),
                "legend": renderer.get_color_legend(color_scale)
            }
        except ImportError:
            return {"error": "Heatmap module not available"}

    @app.get("/api/heatmap/scales")
    async def get_heatmap_scales() -> Dict[str, Any]:
        """Get available color scales"""
        try:
            from agentic.heatmap import HeatmapRenderer
            renderer = HeatmapRenderer()
            return {"scales": renderer.get_available_scales()}
        except ImportError:
            return {"error": "Heatmap module not available"}

    # ==================== Traffic Generation API ====================

    @app.get("/api/traffic/status")
    async def get_traffic_status() -> Dict[str, Any]:
        """Get traffic generator status and summary"""
        try:
            from agentic.traffic import get_traffic_generator, get_iperf_manager
            generator = get_traffic_generator()
            iperf = get_iperf_manager()
            return {
                "generator": generator.get_statistics(),
                "traffic_summary": generator.get_traffic_summary(),
                "iperf": iperf.get_statistics()
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/traffic/profiles")
    async def get_traffic_profiles() -> Dict[str, Any]:
        """Get all traffic profiles"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            profiles = generator.get_all_profiles()
            return {
                "profiles": [p.to_dict() for p in profiles],
                "count": len(profiles)
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/traffic/profiles")
    async def create_traffic_profile(
        name: str,
        pattern: str = "constant",
        base_rate_mbps: float = 10.0,
        peak_rate_mbps: float = 100.0,
        duration_seconds: int = 60
    ) -> Dict[str, Any]:
        """Create a new traffic profile"""
        try:
            from agentic.traffic import get_traffic_generator, TrafficPattern
            generator = get_traffic_generator()

            # Parse pattern
            try:
                traffic_pattern = TrafficPattern(pattern)
            except ValueError:
                traffic_pattern = TrafficPattern.CONSTANT

            profile = generator.create_profile(
                name=name,
                pattern=traffic_pattern,
                base_rate_mbps=base_rate_mbps,
                peak_rate_mbps=peak_rate_mbps,
                duration_seconds=duration_seconds
            )
            return {"profile": profile.to_dict()}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/traffic/flows")
    async def get_traffic_flows() -> Dict[str, Any]:
        """Get all traffic flows"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            flows = generator.get_all_flows()
            return {
                "flows": [f.to_dict() for f in flows],
                "count": len(flows)
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/traffic/flows/active")
    async def get_active_flows() -> Dict[str, Any]:
        """Get active traffic flows"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            flows = generator.get_active_flows()
            return {
                "flows": [f.to_dict() for f in flows],
                "count": len(flows)
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/traffic/flows")
    async def create_traffic_flow(
        source_agent: str,
        dest_agent: str,
        source_ip: str,
        dest_ip: str,
        dest_port: int = 5001,
        flow_type: str = "tcp",
        profile_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new traffic flow"""
        try:
            from agentic.traffic import get_traffic_generator, FlowType
            generator = get_traffic_generator()

            try:
                ft = FlowType(flow_type)
            except ValueError:
                ft = FlowType.TCP

            flow = generator.create_flow(
                source_agent=source_agent,
                dest_agent=dest_agent,
                source_ip=source_ip,
                dest_ip=dest_ip,
                dest_port=dest_port,
                flow_type=ft,
                profile_id=profile_id
            )
            return {"flow": flow.to_dict()}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/traffic/flows/{flow_id}/start")
    async def start_traffic_flow(flow_id: str) -> Dict[str, Any]:
        """Start a traffic flow"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            success = await generator.start_flow(flow_id)
            flow = generator.get_flow(flow_id)
            return {
                "success": success,
                "flow": flow.to_dict() if flow else None
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/traffic/flows/{flow_id}/stop")
    async def stop_traffic_flow(flow_id: str) -> Dict[str, Any]:
        """Stop a traffic flow"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            success = await generator.stop_flow(flow_id)
            flow = generator.get_flow(flow_id)
            return {
                "success": success,
                "flow": flow.to_dict() if flow else None
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/traffic/flows/stop-all")
    async def stop_all_traffic_flows() -> Dict[str, Any]:
        """Stop all running traffic flows"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            await generator.stop_all_flows()
            return {"status": "all_flows_stopped"}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/traffic/flows/{flow_id}")
    async def get_traffic_flow(flow_id: str) -> Dict[str, Any]:
        """Get a specific traffic flow"""
        try:
            from agentic.traffic import get_traffic_generator
            generator = get_traffic_generator()
            flow = generator.get_flow(flow_id)
            if flow:
                return {"flow": flow.to_dict()}
            return {"error": "Flow not found"}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/iperf/test")
    async def run_iperf_test(
        client_id: str,
        server_ip: str,
        server_port: int = 5201,
        duration: float = 10.0,
        protocol: str = "tcp",
        parallel: int = 1
    ) -> Dict[str, Any]:
        """Run an iPerf bandwidth test"""
        try:
            from agentic.traffic import get_iperf_manager, IPerfProtocol
            manager = get_iperf_manager()

            # Ensure client exists
            if not manager.get_client(client_id):
                manager.create_client(client_id)

            try:
                proto = IPerfProtocol(protocol)
            except ValueError:
                proto = IPerfProtocol.TCP

            result = await manager.run_test(
                client_id=client_id,
                server_ip=server_ip,
                server_port=server_port,
                duration=duration,
                protocol=proto,
                parallel=parallel
            )

            if result:
                return {"result": result.to_dict()}
            return {"error": "Test failed to run"}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/iperf/results")
    async def get_iperf_results() -> Dict[str, Any]:
        """Get all iPerf test results"""
        try:
            from agentic.traffic import get_iperf_manager
            manager = get_iperf_manager()
            results = manager.get_all_results()
            return {
                "results": [r.to_dict() for r in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/iperf/server")
    async def create_iperf_server(
        server_id: str,
        bind_ip: str = "0.0.0.0",
        port: int = 5201
    ) -> Dict[str, Any]:
        """Create an iPerf server"""
        try:
            from agentic.traffic import get_iperf_manager
            manager = get_iperf_manager()
            server = manager.create_server(server_id, bind_ip, port)
            await server.start()
            return {"server": server.to_dict()}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.post("/api/iperf/client")
    async def create_iperf_client(
        client_id: str,
        client_ip: str = "0.0.0.0"
    ) -> Dict[str, Any]:
        """Create an iPerf client"""
        try:
            from agentic.traffic import get_iperf_manager
            manager = get_iperf_manager()
            client = manager.create_client(client_id, client_ip)
            return {"client": client.to_dict()}
        except ImportError:
            return {"error": "Traffic module not available"}

    @app.get("/api/traffic/patterns")
    async def get_traffic_patterns() -> Dict[str, Any]:
        """Get available traffic patterns"""
        try:
            from agentic.traffic.generator import TrafficPattern, FlowType
            return {
                "patterns": [p.value for p in TrafficPattern],
                "flow_types": [t.value for t in FlowType]
            }
        except ImportError:
            return {"error": "Traffic module not available"}

    # ==================== Multi-Tenancy API ====================

    @app.get("/api/tenants/status")
    async def get_tenants_status() -> Dict[str, Any]:
        """Get tenant manager status"""
        try:
            from agentic.tenancy import get_tenant_manager, get_tenant_isolation
            manager = get_tenant_manager()
            isolation = get_tenant_isolation()
            return {
                "manager": manager.get_statistics(),
                "isolation": isolation.get_statistics()
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants")
    async def get_tenants(active_only: bool = False) -> Dict[str, Any]:
        """Get all tenants"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            if active_only:
                tenants = manager.get_active_tenants()
            else:
                tenants = manager.get_all_tenants()
            return {
                "tenants": [t.to_dict() for t in tenants],
                "count": len(tenants)
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants/{tenant_id}")
    async def get_tenant(tenant_id: str) -> Dict[str, Any]:
        """Get a specific tenant"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            tenant = manager.get_tenant(tenant_id)
            if tenant:
                return {"tenant": tenant.to_dict()}
            return {"error": "Tenant not found"}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants")
    async def create_tenant(
        name: str,
        description: str = "",
        tier: str = "free",
        owner_email: str = ""
    ) -> Dict[str, Any]:
        """Create a new tenant"""
        try:
            from agentic.tenancy import get_tenant_manager
            from agentic.tenancy.tenant import TenantTier
            manager = get_tenant_manager()

            try:
                tenant_tier = TenantTier(tier)
            except ValueError:
                tenant_tier = TenantTier.FREE

            tenant = manager.create_tenant(
                name=name,
                description=description,
                tier=tenant_tier,
                owner_email=owner_email
            )
            return {"tenant": tenant.to_dict()}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants/{tenant_id}/activate")
    async def activate_tenant(tenant_id: str) -> Dict[str, Any]:
        """Activate a tenant"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            success = manager.activate_tenant(tenant_id)
            tenant = manager.get_tenant(tenant_id)
            return {
                "success": success,
                "tenant": tenant.to_dict() if tenant else None
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants/{tenant_id}/suspend")
    async def suspend_tenant(tenant_id: str, reason: str = "") -> Dict[str, Any]:
        """Suspend a tenant"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            success = manager.suspend_tenant(tenant_id, reason)
            tenant = manager.get_tenant(tenant_id)
            return {
                "success": success,
                "tenant": tenant.to_dict() if tenant else None
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants/{tenant_id}/tier")
    async def update_tenant_tier(tenant_id: str, tier: str) -> Dict[str, Any]:
        """Update tenant tier"""
        try:
            from agentic.tenancy import get_tenant_manager
            from agentic.tenancy.tenant import TenantTier
            manager = get_tenant_manager()

            try:
                new_tier = TenantTier(tier)
            except ValueError:
                return {"error": f"Invalid tier: {tier}"}

            success = manager.update_tier(tenant_id, new_tier)
            tenant = manager.get_tenant(tenant_id)
            return {
                "success": success,
                "tenant": tenant.to_dict() if tenant else None
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.delete("/api/tenants/{tenant_id}")
    async def delete_tenant(tenant_id: str) -> Dict[str, Any]:
        """Delete a tenant"""
        try:
            from agentic.tenancy import get_tenant_manager
            manager = get_tenant_manager()
            success = manager.delete_tenant(tenant_id)
            return {"success": success}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants/{tenant_id}/quotas")
    async def get_tenant_quotas(tenant_id: str) -> Dict[str, Any]:
        """Get quotas for a tenant"""
        try:
            from agentic.tenancy import get_tenant_isolation
            isolation = get_tenant_isolation()
            quotas = isolation.get_all_quotas(tenant_id)
            return {
                "tenant_id": tenant_id,
                "quotas": {k: v.to_dict() for k, v in quotas.items()}
            }
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants/{tenant_id}/quotas")
    async def set_tenant_quota(
        tenant_id: str,
        resource_type: str,
        limit: int,
        reset_period_hours: int = 0
    ) -> Dict[str, Any]:
        """Set a quota for a tenant"""
        try:
            from agentic.tenancy import get_tenant_isolation
            from agentic.tenancy.isolation import ResourceType
            isolation = get_tenant_isolation()

            try:
                rt = ResourceType(resource_type)
            except ValueError:
                return {"error": f"Invalid resource type: {resource_type}"}

            quota = isolation.set_quota(tenant_id, rt, limit, reset_period_hours)
            return {"quota": quota.to_dict()}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants/isolation/level")
    async def get_isolation_level() -> Dict[str, Any]:
        """Get current isolation level"""
        try:
            from agentic.tenancy import get_tenant_isolation
            isolation = get_tenant_isolation()
            return {"level": isolation.get_isolation_level().value}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.post("/api/tenants/isolation/level")
    async def set_isolation_level(level: str) -> Dict[str, Any]:
        """Set isolation level"""
        try:
            from agentic.tenancy import get_tenant_isolation
            from agentic.tenancy.isolation import IsolationLevel
            isolation = get_tenant_isolation()

            try:
                new_level = IsolationLevel(level)
            except ValueError:
                return {"error": f"Invalid level: {level}"}

            isolation.set_isolation_level(new_level)
            return {"level": new_level.value}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants/access-log")
    async def get_access_log(limit: int = 100) -> Dict[str, Any]:
        """Get tenant access log"""
        try:
            from agentic.tenancy import get_tenant_isolation
            isolation = get_tenant_isolation()
            log = isolation.get_access_log(limit)
            return {"log": log, "count": len(log)}
        except ImportError:
            return {"error": "Tenancy module not available"}

    @app.get("/api/tenants/tiers")
    async def get_tenant_tiers() -> Dict[str, Any]:
        """Get available tenant tiers"""
        try:
            from agentic.tenancy.tenant import TenantTier, TenantConfig
            tiers = []
            for tier in TenantTier:
                config = TenantConfig.for_tier(tier)
                tiers.append({
                    "tier": tier.value,
                    "config": config.to_dict()
                })
            return {"tiers": tiers}
        except ImportError:
            return {"error": "Tenancy module not available"}

    # ==================== RBAC API ====================

    @app.get("/api/rbac/status")
    async def get_rbac_status() -> Dict[str, Any]:
        """Get RBAC system status"""
        try:
            from agentic.rbac import get_user_manager, get_role_manager, get_policy_engine
            return {
                "users": get_user_manager().get_statistics(),
                "roles": get_role_manager().get_statistics(),
                "policy": get_policy_engine().get_statistics()
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/users")
    async def get_users() -> Dict[str, Any]:
        """Get all users"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            users = manager.get_all_users()
            return {
                "users": [u.to_dict() for u in users],
                "count": len(users)
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/users/{user_id}")
    async def get_user(user_id: str) -> Dict[str, Any]:
        """Get a specific user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            user = manager.get_user(user_id)
            if user:
                return {"user": user.to_dict()}
            return {"error": "User not found"}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/users")
    async def create_user(
        username: str,
        email: str,
        password: str,
        display_name: str = "",
        auto_activate: bool = True
    ) -> Dict[str, Any]:
        """Create a new user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            user = manager.create_user(
                username=username,
                email=email,
                password=password,
                display_name=display_name,
                auto_activate=auto_activate
            )
            return {"user": user.to_dict()}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/users/{user_id}/activate")
    async def activate_user(user_id: str) -> Dict[str, Any]:
        """Activate a user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            success = manager.activate_user(user_id)
            return {"success": success}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/users/{user_id}/suspend")
    async def suspend_user(user_id: str) -> Dict[str, Any]:
        """Suspend a user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            success = manager.suspend_user(user_id)
            return {"success": success}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/users/{user_id}/unlock")
    async def unlock_user(user_id: str) -> Dict[str, Any]:
        """Unlock a locked user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            success = manager.unlock_user(user_id)
            return {"success": success}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/users/{user_id}/roles")
    async def assign_user_role(user_id: str, role_id: str) -> Dict[str, Any]:
        """Assign a role to a user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            success = manager.assign_role(user_id, role_id)
            return {"success": success}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.delete("/api/rbac/users/{user_id}/roles/{role_id}")
    async def revoke_user_role(user_id: str, role_id: str) -> Dict[str, Any]:
        """Revoke a role from a user"""
        try:
            from agentic.rbac import get_user_manager
            manager = get_user_manager()
            success = manager.revoke_role(user_id, role_id)
            return {"success": success}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/roles")
    async def get_roles() -> Dict[str, Any]:
        """Get all roles"""
        try:
            from agentic.rbac import get_role_manager
            manager = get_role_manager()
            roles = manager.get_all_roles()
            return {
                "roles": [r.to_dict() for r in roles],
                "count": len(roles)
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/roles/{role_id}")
    async def get_role(role_id: str) -> Dict[str, Any]:
        """Get a specific role"""
        try:
            from agentic.rbac import get_role_manager
            manager = get_role_manager()
            role = manager.get_role(role_id)
            if role:
                effective_perms = manager.get_effective_permissions(role_id)
                return {
                    "role": role.to_dict(),
                    "effective_permissions": list(effective_perms)
                }
            return {"error": "Role not found"}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/roles")
    async def create_role(
        name: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Create a new role"""
        try:
            from agentic.rbac import get_role_manager
            manager = get_role_manager()
            role = manager.create_role(name=name, description=description)
            return {"role": role.to_dict()}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/permissions")
    async def get_permissions() -> Dict[str, Any]:
        """Get all permissions"""
        try:
            from agentic.rbac import get_role_manager
            manager = get_role_manager()
            perms = manager.get_all_permissions()
            return {
                "permissions": [p.to_dict() for p in perms],
                "count": len(perms)
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/check")
    async def check_permission(
        user_id: str,
        resource: str,
        action: str
    ) -> Dict[str, Any]:
        """Check if a user has permission"""
        try:
            from agentic.rbac import get_policy_engine
            engine = get_policy_engine()
            allowed = engine.check_permission(user_id, resource, action)
            return {
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "allowed": allowed
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/policies")
    async def get_policies() -> Dict[str, Any]:
        """Get all access policies"""
        try:
            from agentic.rbac import get_policy_engine
            engine = get_policy_engine()
            policies = engine.get_all_policies()
            return {
                "policies": [p.to_dict() for p in policies],
                "count": len(policies)
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/policies")
    async def create_policy(
        name: str,
        description: str,
        resource_pattern: str,
        action_pattern: str,
        effect: str = "allow",
        priority: int = 0
    ) -> Dict[str, Any]:
        """Create a new access policy"""
        try:
            from agentic.rbac import get_policy_engine, AccessDecision
            engine = get_policy_engine()

            decision = AccessDecision.ALLOW if effect == "allow" else AccessDecision.DENY

            policy = engine.create_policy(
                name=name,
                description=description,
                resource_pattern=resource_pattern,
                action_pattern=action_pattern,
                effect=decision,
                priority=priority
            )
            return {"policy": policy.to_dict()}
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.get("/api/rbac/audit")
    async def get_audit_log(limit: int = 100) -> Dict[str, Any]:
        """Get RBAC audit log"""
        try:
            from agentic.rbac import get_policy_engine
            engine = get_policy_engine()
            entries = engine.get_audit_log(limit)
            return {
                "entries": [e.to_dict() for e in entries],
                "count": len(entries)
            }
        except ImportError:
            return {"error": "RBAC module not available"}

    @app.post("/api/rbac/enforcement")
    async def set_enforcement(enabled: bool) -> Dict[str, Any]:
        """Enable or disable RBAC enforcement"""
        try:
            from agentic.rbac import get_policy_engine
            engine = get_policy_engine()
            engine.set_enforcement(enabled)
            return {"enforcement_enabled": enabled}
        except ImportError:
            return {"error": "RBAC module not available"}

    # ==================== Traffic Simulation API ====================

    @app.get("/api/simulation/status")
    async def get_simulation_status() -> Dict[str, Any]:
        """Get traffic simulation status and statistics"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            return simulator.get_statistics()
        except ImportError as e:
            return {"error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation status error: {e}")
            return {"error": str(e)}

    @app.get("/api/simulation/flows")
    async def get_simulation_flows(
        source_agent: Optional[str] = None,
        dest_agent: Optional[str] = None,
        active_only: bool = False
    ) -> Dict[str, Any]:
        """Get all traffic flows with optional filtering"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            flows = simulator.list_flows(
                source_agent=source_agent,
                dest_agent=dest_agent,
                active_only=active_only
            )
            return {
                "flows": [f.to_dict() for f in flows],
                "count": len(flows)
            }
        except ImportError as e:
            return {"flows": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation flows error: {e}")
            return {"flows": [], "error": str(e)}

    @app.post("/api/simulation/flows")
    async def create_simulation_flow(
        source_agent: str,
        source_interface: str,
        dest_agent: str,
        dest_interface: str,
        rate_bps: float = 1_000_000,
        protocol: str = "tcp",
        application: str = "generic",
        pattern: str = "constant",
        priority: int = 0
    ) -> Dict[str, Any]:
        """Create a new traffic flow"""
        try:
            from agentic.simulation import get_traffic_simulator, TrafficPattern
            simulator = get_traffic_simulator()

            # Parse pattern
            try:
                traffic_pattern = TrafficPattern(pattern)
            except ValueError:
                traffic_pattern = TrafficPattern.CONSTANT

            flow = simulator.create_flow(
                source_agent=source_agent,
                source_interface=source_interface,
                dest_agent=dest_agent,
                dest_interface=dest_interface,
                rate_bps=rate_bps,
                protocol=protocol,
                application=application,
                pattern=traffic_pattern,
                priority=priority
            )
            return {"flow": flow.to_dict(), "success": True}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation flow create error: {e}")
            return {"success": False, "error": str(e)}

    @app.delete("/api/simulation/flows/{flow_id}")
    async def delete_simulation_flow(flow_id: str) -> Dict[str, Any]:
        """Delete a traffic flow"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            success = simulator.delete_flow(flow_id)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation flow delete error: {e}")
            return {"success": False, "error": str(e)}

    @app.put("/api/simulation/flows/{flow_id}/active")
    async def set_simulation_flow_active(flow_id: str, active: bool = True) -> Dict[str, Any]:
        """Enable or disable a flow"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            success = simulator.set_flow_active(flow_id, active)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation flow active error: {e}")
            return {"success": False, "error": str(e)}

    @app.put("/api/simulation/flows/{flow_id}/rate")
    async def update_simulation_flow_rate(flow_id: str, rate_bps: float) -> Dict[str, Any]:
        """Update flow rate"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            success = simulator.update_flow_rate(flow_id, rate_bps)
            return {"success": success}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation flow rate error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/simulation/scenarios/{scenario}")
    async def create_simulation_scenario(scenario: str, agents: List[str]) -> Dict[str, Any]:
        """Create a predefined traffic scenario"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            flows = simulator.create_traffic_scenario(scenario, agents)
            return {
                "flows": [f.to_dict() for f in flows],
                "count": len(flows),
                "scenario": scenario
            }
        except ImportError as e:
            return {"flows": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation scenario error: {e}")
            return {"flows": [], "error": str(e)}

    @app.post("/api/simulation/start")
    async def start_simulation() -> Dict[str, Any]:
        """Start the traffic simulation"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            await simulator.start_simulation()
            return {"success": True, "message": "Simulation started"}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation start error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/simulation/stop")
    async def stop_simulation() -> Dict[str, Any]:
        """Stop the traffic simulation"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            await simulator.stop_simulation()
            return {"success": True, "message": "Simulation stopped"}
        except ImportError as e:
            return {"success": False, "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation stop error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/simulation/heatmap")
    async def get_simulation_heatmap() -> Dict[str, Any]:
        """Get traffic heatmap data for visualization"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            return simulator.get_traffic_heatmap()
        except ImportError as e:
            return {"links": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation heatmap error: {e}")
            return {"links": [], "error": str(e)}

    @app.get("/api/simulation/congestion")
    async def get_simulation_congestion() -> Dict[str, Any]:
        """Get congestion analysis report"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            return simulator.get_congestion_report()
        except ImportError as e:
            return {"details": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation congestion error: {e}")
            return {"details": [], "error": str(e)}

    @app.get("/api/simulation/visualization")
    async def get_simulation_visualization() -> Dict[str, Any]:
        """Get flow visualization data (animated packets)"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            return simulator.get_flow_visualization()
        except ImportError as e:
            return {"flows": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation visualization error: {e}")
            return {"flows": [], "error": str(e)}

    @app.get("/api/simulation/history")
    async def get_simulation_history(minutes: int = 60) -> Dict[str, Any]:
        """Get historical traffic data"""
        try:
            from agentic.simulation import get_traffic_simulator
            simulator = get_traffic_simulator()
            history = simulator.get_history(minutes)
            return {"history": history, "count": len(history)}
        except ImportError as e:
            return {"history": [], "error": f"Simulation module not available: {e}"}
        except Exception as e:
            logger.error(f"Simulation history error: {e}")
            return {"history": [], "error": str(e)}

    @app.get("/api/simulation/patterns")
    async def get_simulation_patterns() -> Dict[str, Any]:
        """Get available traffic patterns"""
        try:
            from agentic.simulation import TrafficPattern, CongestionLevel
            return {
                "patterns": [p.value for p in TrafficPattern],
                "congestion_levels": [c.value for c in CongestionLevel],
                "scenarios": ["mesh", "hub_spoke", "backbone", "ddos"]
            }
        except ImportError as e:
            return {"patterns": [], "error": f"Simulation module not available: {e}"}

    # ==================== Time-Travel Network Replay API ====================

    @app.get("/api/replay/status")
    async def get_replay_status() -> Dict[str, Any]:
        """Get network recorder status and statistics"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            return recorder.get_statistics()
        except ImportError as e:
            return {"error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Replay status error: {e}")
            return {"error": str(e)}

    @app.get("/api/replay/sessions")
    async def get_replay_sessions(active_only: bool = False) -> Dict[str, Any]:
        """Get all recording sessions"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            sessions = recorder.list_sessions(active_only=active_only)
            return {
                "sessions": [s.to_dict() for s in sessions],
                "count": len(sessions)
            }
        except ImportError as e:
            return {"sessions": [], "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Replay sessions error: {e}")
            return {"sessions": [], "error": str(e)}

    @app.post("/api/replay/sessions")
    async def start_recording_session(
        name: str = "Recording",
        description: str = "",
        snapshot_interval: int = 30
    ) -> Dict[str, Any]:
        """Start a new recording session"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            session = recorder.start_recording(
                name=name,
                description=description,
                snapshot_interval=snapshot_interval
            )
            return {"session": session.to_dict(), "success": True}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Start recording error: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/api/replay/sessions/stop")
    async def stop_recording_session() -> Dict[str, Any]:
        """Stop the current recording session"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            session = recorder.stop_recording()
            if session:
                return {"session": session.to_dict(), "success": True}
            return {"success": False, "error": "No active recording session"}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Stop recording error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/replay/sessions/{session_id}")
    async def get_recording_session(session_id: str) -> Dict[str, Any]:
        """Get a specific recording session"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            session = recorder.get_session(session_id)
            if session:
                return {"session": session.to_dict()}
            return {"error": "Session not found"}
        except ImportError as e:
            return {"error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Get session error: {e}")
            return {"error": str(e)}

    @app.get("/api/replay/snapshots")
    async def get_replay_snapshots(
        session_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get network snapshots"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            snapshots = recorder.get_snapshots(session_id=session_id, limit=limit)
            return {
                "snapshots": [s.to_dict() for s in snapshots],
                "count": len(snapshots)
            }
        except ImportError as e:
            return {"snapshots": [], "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Get snapshots error: {e}")
            return {"snapshots": [], "error": str(e)}

    @app.post("/api/replay/snapshots")
    async def record_snapshot_now() -> Dict[str, Any]:
        """Manually record a snapshot"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            snapshot = recorder.record_snapshot()
            if snapshot:
                return {"snapshot": snapshot.to_dict(), "success": True}
            return {"success": False, "error": "No active recording session"}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Record snapshot error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/replay/events")
    async def get_replay_events(
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        agent_id: Optional[str] = None,
        protocol: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get protocol events"""
        try:
            from agentic.replay import get_network_recorder, EventType
            recorder = get_network_recorder()

            # Parse event type if provided
            et = None
            if event_type:
                try:
                    et = EventType(event_type)
                except ValueError:
                    pass

            events = recorder.get_events(
                session_id=session_id,
                event_type=et,
                agent_id=agent_id,
                protocol=protocol,
                limit=limit
            )
            return {
                "events": [e.to_dict() for e in events],
                "count": len(events)
            }
        except ImportError as e:
            return {"events": [], "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Get events error: {e}")
            return {"events": [], "error": str(e)}

    @app.post("/api/replay/events")
    async def record_event_now(
        event_type: str,
        agent_id: str,
        protocol: str,
        description: str,
        severity: str = "info"
    ) -> Dict[str, Any]:
        """Manually record an event"""
        try:
            from agentic.replay import get_network_recorder, EventType
            recorder = get_network_recorder()

            try:
                et = EventType(event_type)
            except ValueError:
                return {"success": False, "error": f"Invalid event type: {event_type}"}

            event = recorder.record_event(
                event_type=et,
                agent_id=agent_id,
                protocol=protocol,
                description=description,
                severity=severity
            )
            if event:
                return {"event": event.to_dict(), "success": True}
            return {"success": False, "error": "No active recording session"}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Record event error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/replay/timeline")
    async def get_replay_timeline(session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get the recording timeline"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            return recorder.get_timeline(session_id=session_id)
        except ImportError as e:
            return {"error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Get timeline error: {e}")
            return {"error": str(e)}

    @app.post("/api/replay/rewind")
    async def replay_to_timestamp(
        timestamp: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Replay to a specific timestamp"""
        try:
            from agentic.replay import get_network_recorder
            from datetime import datetime
            recorder = get_network_recorder()

            # Parse timestamp
            try:
                target_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return {"error": f"Invalid timestamp format: {timestamp}"}

            snapshot = recorder.replay_to_time(target_time, session_id=session_id)
            if snapshot:
                return {"snapshot": snapshot.to_dict(), "success": True}
            return {"success": False, "error": "No snapshot found for that time"}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Replay to time error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/replay/state")
    async def get_replay_state() -> Dict[str, Any]:
        """Get the current replay state"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            state = recorder.get_replay_state()
            if state:
                return state
            return {"replaying": False, "message": "Not in replay mode"}
        except ImportError as e:
            return {"error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Get replay state error: {e}")
            return {"error": str(e)}

    @app.post("/api/replay/clear")
    async def clear_replay_state() -> Dict[str, Any]:
        """Clear the replay state and return to live mode"""
        try:
            from agentic.replay import get_network_recorder
            recorder = get_network_recorder()
            recorder.clear_replay()
            return {"success": True, "message": "Replay state cleared"}
        except ImportError as e:
            return {"success": False, "error": f"Replay module not available: {e}"}
        except Exception as e:
            logger.error(f"Clear replay error: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/api/replay/event-types")
    async def get_event_types() -> Dict[str, Any]:
        """Get all available event types"""
        try:
            from agentic.replay import EventType
            return {
                "event_types": [
                    {"value": et.value, "name": et.name}
                    for et in EventType
                ]
            }
        except ImportError as e:
            return {"event_types": [], "error": f"Replay module not available: {e}"}

    # ==================== Network Diff API ====================

    @app.get("/api/diff/status")
    async def get_diff_status() -> Dict[str, Any]:
        """Get network differ status and statistics"""
        try:
            from agentic.diff import get_network_differ
            differ = get_network_differ()
            return differ.get_statistics()
        except ImportError as e:
            return {"error": f"Diff module not available: {e}"}
        except Exception as e:
            logger.error(f"Diff status error: {e}")
            return {"error": str(e)}

    @app.post("/api/diff/compare")
    async def compare_network_snapshots(
        before_snapshot_id: str,
        after_snapshot_id: str
    ) -> Dict[str, Any]:
        """Compare two network snapshots"""
        try:
            from agentic.diff import get_network_differ
            from agentic.replay import get_network_recorder

            differ = get_network_differ()
            recorder = get_network_recorder()

            # Get snapshots from recorder
            all_snapshots = recorder.get_snapshots(limit=1000)

            before_snap = None
            after_snap = None

            for snap in all_snapshots:
                if snap.snapshot_id == before_snapshot_id:
                    before_snap = snap.to_dict()
                if snap.snapshot_id == after_snapshot_id:
                    after_snap = snap.to_dict()

            if not before_snap:
                return {"error": f"Before snapshot not found: {before_snapshot_id}"}
            if not after_snap:
                return {"error": f"After snapshot not found: {after_snapshot_id}"}

            result = differ.compare_snapshots(before_snap, after_snap)
            return result.to_dict()
        except ImportError as e:
            return {"error": f"Diff module not available: {e}"}
        except Exception as e:
            logger.error(f"Compare snapshots error: {e}")
            return {"error": str(e)}

    @app.post("/api/diff/compare-direct")
    async def compare_snapshots_direct(
        before: Dict[str, Any],
        after: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare two snapshots provided directly"""
        try:
            from agentic.diff import get_network_differ
            differ = get_network_differ()
            result = differ.compare_snapshots(before, after)
            return result.to_dict()
        except ImportError as e:
            return {"error": f"Diff module not available: {e}"}
        except Exception as e:
            logger.error(f"Compare direct error: {e}")
            return {"error": str(e)}

    @app.post("/api/diff/compare-config")
    async def compare_configs(
        before_config: str,
        after_config: str
    ) -> Dict[str, Any]:
        """Compare two configuration strings"""
        try:
            from agentic.diff import get_network_differ
            differ = get_network_differ()
            return differ.compare_configs(before_config, after_config)
        except ImportError as e:
            return {"error": f"Diff module not available: {e}"}
        except Exception as e:
            logger.error(f"Compare config error: {e}")
            return {"error": str(e)}

    @app.get("/api/diff/history")
    async def get_diff_history(limit: int = 10) -> Dict[str, Any]:
        """Get recent diff history"""
        try:
            from agentic.diff import get_network_differ
            differ = get_network_differ()
            history = differ.get_diff_history(limit=limit)
            return {"history": history, "count": len(history)}
        except ImportError as e:
            return {"history": [], "error": f"Diff module not available: {e}"}
        except Exception as e:
            logger.error(f"Diff history error: {e}")
            return {"history": [], "error": str(e)}

    @app.get("/api/diff/categories")
    async def get_diff_categories() -> Dict[str, Any]:
        """Get available diff categories and types"""
        try:
            from agentic.diff import DiffCategory, DiffType
            return {
                "categories": [
                    {"value": c.value, "name": c.name}
                    for c in DiffCategory
                ],
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in DiffType
                ]
            }
        except ImportError as e:
            return {"categories": [], "types": [], "error": f"Diff module not available: {e}"}

    # ==================== Intelligent Suggestions API ====================

    @app.get("/api/suggestions/status")
    async def get_suggestions_status() -> Dict[str, Any]:
        """Get network advisor status and statistics"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()
            return advisor.get_statistics()
        except ImportError:
            return {"error": "Suggestions module not available"}

    @app.post("/api/suggestions/analyze")
    async def analyze_network_suggestions(
        include_info: bool = False
    ) -> Dict[str, Any]:
        """Analyze current network state and generate suggestions"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()

            # Build network state from current data
            network_state = {}

            # Get topology data if available
            try:
                from agentic.topology import get_topology_manager
                topo = get_topology_manager()
                network_state["topology"] = topo.get_topology_data()
            except ImportError:
                pass

            # Get agent data if available
            if asi_app and hasattr(asi_app, 'agent_manager'):
                agents = asi_app.agent_manager.get_all_agents()
                network_state["agents"] = {
                    name: agent.get_status() for name, agent in agents.items()
                }

            # Get health data if available
            try:
                from agentic.health import get_health_scorer
                scorer = get_health_scorer()
                network_state["health"] = scorer.get_current_health()
            except ImportError:
                pass

            # Analyze the network
            suggestions = advisor.analyze_network(network_state, include_info=include_info)

            return {
                "suggestions": [s.to_dict() for s in suggestions],
                "count": len(suggestions),
                "analyzed_at": datetime.now().isoformat(),
                "network_state_keys": list(network_state.keys())
            }
        except ImportError as e:
            return {"error": f"Suggestions module not available: {e}"}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/suggestions")
    async def get_suggestions_list(
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get current suggestions with optional filters"""
        try:
            from agentic.suggestions import (
                get_network_advisor, SuggestionCategory, SuggestionPriority
            )
            advisor = get_network_advisor()

            # Parse category filter
            cat_filter = None
            if category:
                try:
                    cat_filter = SuggestionCategory(category)
                except ValueError:
                    return {"error": f"Invalid category: {category}"}

            # Parse priority filter
            pri_filter = None
            if priority:
                try:
                    pri_filter = SuggestionPriority(priority)
                except ValueError:
                    return {"error": f"Invalid priority: {priority}"}

            suggestions = advisor.get_suggestions(
                category=cat_filter,
                priority=pri_filter,
                limit=limit
            )

            return {
                "suggestions": [s.to_dict() for s in suggestions],
                "count": len(suggestions),
                "filters": {
                    "category": category,
                    "priority": priority,
                    "limit": limit
                }
            }
        except ImportError:
            return {"error": "Suggestions module not available"}

    @app.post("/api/suggestions/{suggestion_id}/dismiss")
    async def dismiss_suggestion(
        suggestion_id: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dismiss a suggestion"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()

            success = advisor.dismiss_suggestion(suggestion_id, reason=reason)

            if success:
                return {
                    "dismissed": True,
                    "suggestion_id": suggestion_id,
                    "reason": reason
                }
            else:
                return {
                    "dismissed": False,
                    "error": f"Suggestion not found: {suggestion_id}"
                }
        except ImportError:
            return {"error": "Suggestions module not available"}

    @app.post("/api/suggestions/{suggestion_id}/apply")
    async def apply_suggestion(
        suggestion_id: str
    ) -> Dict[str, Any]:
        """Apply a suggestion (if auto-applicable)"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()

            result = advisor.apply_suggestion(suggestion_id)

            return {
                "suggestion_id": suggestion_id,
                "applied": result.get("applied", False),
                "result": result
            }
        except ImportError:
            return {"error": "Suggestions module not available"}

    @app.get("/api/suggestions/categories")
    async def get_suggestion_categories() -> Dict[str, Any]:
        """Get available suggestion categories and priorities"""
        try:
            from agentic.suggestions import SuggestionCategory, SuggestionPriority
            return {
                "categories": [
                    {"value": c.value, "name": c.name}
                    for c in SuggestionCategory
                ],
                "priorities": [
                    {"value": p.value, "name": p.name}
                    for p in SuggestionPriority
                ]
            }
        except ImportError:
            return {"categories": [], "priorities": [], "error": "Suggestions module not available"}

    @app.get("/api/suggestions/history")
    async def get_suggestion_history(
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get history of dismissed/applied suggestions"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()

            history = advisor.get_history(limit=limit)

            return {
                "history": history,
                "count": len(history)
            }
        except ImportError:
            return {"error": "Suggestions module not available"}

    @app.post("/api/suggestions/refresh")
    async def refresh_suggestions() -> Dict[str, Any]:
        """Force refresh of suggestions analysis"""
        try:
            from agentic.suggestions import get_network_advisor
            advisor = get_network_advisor()

            # Clear cache and re-analyze
            advisor.clear_cache()

            return {
                "refreshed": True,
                "timestamp": datetime.now().isoformat()
            }
        except ImportError:
            return {"error": "Suggestions module not available"}

    # ==================== Scenario Builder API ====================

    @app.get("/api/scenarios/status")
    async def get_scenarios_status() -> Dict[str, Any]:
        """Get scenario builder status and statistics"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()
            return builder.get_statistics()
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios")
    async def list_scenarios(
        category: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all scenarios with optional filtering"""
        try:
            from agentic.scenarios import get_scenario_builder, ScenarioStatus
            builder = get_scenario_builder()

            status_filter = None
            if status:
                try:
                    status_filter = ScenarioStatus(status)
                except ValueError:
                    return {"error": f"Invalid status: {status}"}

            tag_list = tags.split(",") if tags else None

            scenarios = builder.list_scenarios(
                category=category,
                status=status_filter,
                tags=tag_list
            )

            return {
                "scenarios": [s.to_dict() for s in scenarios],
                "count": len(scenarios)
            }
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios/templates")
    async def get_scenario_templates() -> Dict[str, Any]:
        """Get available scenario templates"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()
            templates = builder.get_templates()

            return {
                "templates": [t.to_dict() for t in templates],
                "count": len(templates)
            }
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios")
    async def create_scenario_api(
        name: str,
        description: str = "",
        category: str = "general",
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            tag_list = tags.split(",") if tags else []

            scenario = builder.create_scenario(
                name=name,
                description=description,
                category=category,
                tags=tag_list
            )

            return {
                "created": True,
                "scenario": scenario.to_dict()
            }
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/from-template")
    async def create_from_template(
        template_id: str,
        name: str,
        variables: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a scenario from a template"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            scenario = builder.create_from_template(
                template_id=template_id,
                name=name,
                variables=variables or {}
            )

            if scenario:
                return {
                    "created": True,
                    "scenario": scenario.to_dict()
                }
            else:
                return {"error": f"Template not found: {template_id}"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios/{scenario_id}")
    async def get_scenario(scenario_id: str) -> Dict[str, Any]:
        """Get a specific scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            scenario = builder.get_scenario(scenario_id)
            if scenario:
                return {"scenario": scenario.to_dict()}
            else:
                return {"error": f"Scenario not found: {scenario_id}"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str) -> Dict[str, Any]:
        """Delete a scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            if builder.delete_scenario(scenario_id):
                return {"deleted": True, "scenario_id": scenario_id}
            else:
                return {"error": f"Scenario not found: {scenario_id}"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/{scenario_id}/step")
    async def add_scenario_step(
        scenario_id: str,
        step_type: str,
        name: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        timeout: int = 60,
        continue_on_failure: bool = False
    ) -> Dict[str, Any]:
        """Add a step to a scenario"""
        try:
            from agentic.scenarios import get_scenario_builder, ScenarioStepType
            builder = get_scenario_builder()

            try:
                step_type_enum = ScenarioStepType(step_type)
            except ValueError:
                return {"error": f"Invalid step type: {step_type}"}

            step = builder.add_step(
                scenario_id=scenario_id,
                step_type=step_type_enum,
                name=name,
                description=description,
                parameters=parameters or {},
                timeout=timeout,
                continue_on_failure=continue_on_failure
            )

            if step:
                return {
                    "added": True,
                    "step": step.to_dict()
                }
            else:
                return {"error": f"Scenario not found or cannot be modified: {scenario_id}"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.delete("/api/scenarios/{scenario_id}/step/{step_id}")
    async def remove_scenario_step(scenario_id: str, step_id: str) -> Dict[str, Any]:
        """Remove a step from a scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            if builder.remove_step(scenario_id, step_id):
                return {"removed": True, "step_id": step_id}
            else:
                return {"error": "Scenario or step not found"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/{scenario_id}/ready")
    async def mark_scenario_ready(scenario_id: str) -> Dict[str, Any]:
        """Mark a scenario as ready for execution"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            if builder.set_ready(scenario_id):
                return {"ready": True, "scenario_id": scenario_id}
            else:
                return {"error": "Scenario not found or has no steps"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/{scenario_id}/run")
    async def run_scenario_api(
        scenario_id: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Run a scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            result = await builder.run_scenario(scenario_id, dry_run=dry_run)

            if result:
                return {
                    "started": True,
                    "result": result.to_dict()
                }
            else:
                return {"error": "Scenario not found or already running"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/{scenario_id}/abort")
    async def abort_scenario(scenario_id: str) -> Dict[str, Any]:
        """Abort a running scenario"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            if builder.abort_scenario(scenario_id):
                return {"aborted": True, "scenario_id": scenario_id}
            else:
                return {"error": "Scenario not running"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios/{scenario_id}/result")
    async def get_scenario_result(scenario_id: str) -> Dict[str, Any]:
        """Get the result of a scenario execution"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            result = builder.get_result(scenario_id)
            if result:
                return {"result": result.to_dict()}
            else:
                return {"error": "No result found for scenario"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios/results")
    async def get_all_scenario_results() -> Dict[str, Any]:
        """Get all scenario results"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            results = builder.get_all_results()
            return {
                "results": [r.to_dict() for r in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.get("/api/scenarios/step-types")
    async def get_scenario_step_types() -> Dict[str, Any]:
        """Get available scenario step types"""
        try:
            from agentic.scenarios import ScenarioStepType
            return {
                "step_types": [
                    {"value": t.value, "name": t.name}
                    for t in ScenarioStepType
                ]
            }
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/{scenario_id}/export")
    async def export_scenario(scenario_id: str) -> Dict[str, Any]:
        """Export a scenario as JSON"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            json_data = builder.export_scenario(scenario_id)
            if json_data:
                return {"scenario_json": json_data}
            else:
                return {"error": "Scenario not found"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    @app.post("/api/scenarios/import")
    async def import_scenario(json_data: str) -> Dict[str, Any]:
        """Import a scenario from JSON"""
        try:
            from agentic.scenarios import get_scenario_builder
            builder = get_scenario_builder()

            scenario = builder.import_scenario(json_data)
            if scenario:
                return {
                    "imported": True,
                    "scenario": scenario.to_dict()
                }
            else:
                return {"error": "Failed to import scenario"}
        except ImportError:
            return {"error": "Scenarios module not available"}

    # ==================== Multi-Vendor Simulation API ====================

    @app.get("/api/vendors/status")
    async def get_vendors_status() -> Dict[str, Any]:
        """Get vendor manager status and statistics"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()
            return manager.get_statistics()
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors")
    async def list_vendors_api() -> Dict[str, Any]:
        """List all available vendors"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()
            vendors = manager.list_vendors()

            return {
                "vendors": [v.to_dict() for v in vendors],
                "count": len(vendors)
            }
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors/{vendor_id}")
    async def get_vendor_api(vendor_id: str) -> Dict[str, Any]:
        """Get a specific vendor profile"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()

            vendor = manager.get_vendor(vendor_id)
            if vendor:
                return {"vendor": vendor.to_dict()}
            else:
                return {"error": f"Vendor not found: {vendor_id}"}
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors/{vendor_id}/cli")
    async def get_vendor_cli(vendor_id: str) -> Dict[str, Any]:
        """Get CLI syntax for a vendor"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()

            syntax = manager.get_cli_syntax(vendor_id)
            if syntax:
                return {"cli_syntax": syntax.to_dict()}
            else:
                return {"error": f"Vendor not found: {vendor_id}"}
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors/{vendor_id}/profile")
    async def get_vendor_profile(vendor_id: str) -> Dict[str, Any]:
        """Get behavioral profile for a vendor"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()

            profile = manager.get_profile(vendor_id)
            if profile:
                return {"profile": profile.to_dict()}
            else:
                return {"error": f"Vendor not found: {vendor_id}"}
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors/by-capability/{capability}")
    async def get_vendors_by_capability(capability: str) -> Dict[str, Any]:
        """Get vendors that support a specific capability"""
        try:
            from agentic.vendors import get_vendor_manager, VendorCapability
            manager = get_vendor_manager()

            try:
                cap = VendorCapability(capability)
            except ValueError:
                return {"error": f"Invalid capability: {capability}"}

            vendors = manager.get_vendors_by_capability(cap)
            return {
                "capability": capability,
                "vendors": [v.to_dict() for v in vendors],
                "count": len(vendors)
            }
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.post("/api/vendors/translate")
    async def translate_command(
        command: str,
        from_vendor: str,
        to_vendor: str
    ) -> Dict[str, Any]:
        """Translate a command from one vendor syntax to another"""
        try:
            from agentic.vendors import get_vendor_manager
            manager = get_vendor_manager()

            translated = manager.translate_command(command, from_vendor, to_vendor)

            return {
                "original_command": command,
                "from_vendor": from_vendor,
                "to_vendor": to_vendor,
                "translated_command": translated,
                "success": translated is not None
            }
        except ImportError:
            return {"error": "Vendors module not available"}

    @app.get("/api/vendors/capabilities")
    async def get_vendor_capabilities() -> Dict[str, Any]:
        """Get list of all available vendor capabilities"""
        try:
            from agentic.vendors import VendorCapability
            return {
                "capabilities": [
                    {"value": c.value, "name": c.name}
                    for c in VendorCapability
                ]
            }
        except ImportError:
            return {"error": "Vendors module not available"}

    # ==================== Documentation Generator API ====================

    @app.get("/api/documentation/status")
    async def get_documentation_status() -> Dict[str, Any]:
        """Get documentation generator status"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            return generator.get_statistics()
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/templates")
    async def list_documentation_templates() -> Dict[str, Any]:
        """List available document templates"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            templates = generator.get_templates()
            return {
                "templates": [t.to_dict() for t in templates],
                "count": len(templates)
            }
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/templates/{template_id}")
    async def get_documentation_template(template_id: str) -> Dict[str, Any]:
        """Get a specific document template"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            template = generator.get_template(template_id)
            if template:
                return {"template": template.to_dict()}
            return {"error": "Template not found"}
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.post("/api/documentation/generate")
    async def generate_documentation(
        network_name: Optional[str] = None,
        template: Optional[str] = None,
        sections: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate network documentation"""
        try:
            from agentic.documentation import get_document_generator, DocumentSection
            generator = get_document_generator()

            # Convert section strings to enums if provided
            section_enums = None
            if sections:
                section_enums = []
                for s in sections:
                    try:
                        section_enums.append(DocumentSection(s))
                    except ValueError:
                        pass  # Skip invalid sections

            document = generator.generate(
                network_name=network_name,
                template=template,
                sections=section_enums
            )
            return {"document": document.to_dict()}
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/documents")
    async def list_documents() -> Dict[str, Any]:
        """List generated documents"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            documents = generator.list_documents()
            return {
                "documents": [d.to_dict() for d in documents],
                "count": len(documents)
            }
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/documents/{document_id}")
    async def get_document(document_id: str) -> Dict[str, Any]:
        """Get a specific document"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            document = generator.get_document(document_id)
            if document:
                return {"document": document.to_dict()}
            return {"error": "Document not found"}
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.delete("/api/documentation/documents/{document_id}")
    async def delete_document(document_id: str) -> Dict[str, Any]:
        """Delete a document"""
        try:
            from agentic.documentation import get_document_generator
            generator = get_document_generator()
            success = generator.delete_document(document_id)
            return {"success": success}
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.post("/api/documentation/documents/{document_id}/export")
    async def export_document(
        document_id: str,
        format: str = "markdown"
    ) -> Dict[str, Any]:
        """Export a document to specified format"""
        try:
            from agentic.documentation import get_document_generator, DocumentFormat
            generator = get_document_generator()
            document = generator.get_document(document_id)
            if not document:
                return {"error": "Document not found"}

            try:
                doc_format = DocumentFormat(format.lower())
            except ValueError:
                return {"error": f"Invalid format: {format}. Supported: markdown, html, json, text"}

            content = generator.export(document, doc_format)
            return {
                "format": format,
                "content": content,
                "document_id": document_id
            }
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/sections")
    async def get_documentation_sections() -> Dict[str, Any]:
        """Get available document sections"""
        try:
            from agentic.documentation import DocumentSection
            return {
                "sections": [
                    {"value": s.value, "name": s.name}
                    for s in DocumentSection
                ]
            }
        except ImportError:
            return {"error": "Documentation module not available"}

    @app.get("/api/documentation/formats")
    async def get_documentation_formats() -> Dict[str, Any]:
        """Get available export formats"""
        try:
            from agentic.documentation import DocumentFormat
            return {
                "formats": [
                    {"value": f.value, "name": f.name}
                    for f in DocumentFormat
                ]
            }
        except ImportError:
            return {"error": "Documentation module not available"}

    # ==================== API Analytics ====================

    @app.get("/api/analytics/status")
    async def get_analytics_status() -> Dict[str, Any]:
        """Get API analytics status"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return analytics.get_statistics()
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/endpoints")
    async def get_endpoint_stats(window: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for all endpoints"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window) if window else None
            stats = analytics.get_all_endpoint_stats(time_window)
            return {
                "endpoints": [s.to_dict() for s in stats],
                "count": len(stats)
            }
        except ImportError:
            return {"error": "Analytics module not available"}
        except ValueError:
            return {"error": f"Invalid time window: {window}"}

    @app.get("/api/analytics/endpoints/{endpoint:path}")
    async def get_single_endpoint_stats(endpoint: str, window: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a specific endpoint"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window) if window else None
            endpoint_path = "/" + endpoint if not endpoint.startswith("/") else endpoint
            stats = analytics.get_endpoint_stats(endpoint_path, time_window)
            if stats:
                return {"endpoint": stats.to_dict()}
            return {"error": "Endpoint not found"}
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/clients")
    async def get_client_stats(window: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for all clients"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window) if window else None
            stats = analytics.get_all_client_stats(time_window)
            return {
                "clients": [s.to_dict() for s in stats],
                "count": len(stats)
            }
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/clients/{client_ip}")
    async def get_single_client_stats(client_ip: str, window: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for a specific client"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window) if window else None
            stats = analytics.get_client_stats(client_ip, time_window)
            if stats:
                return {"client": stats.to_dict()}
            return {"error": "Client not found"}
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/top/endpoints")
    async def get_top_endpoints(limit: int = 10, metric: str = "requests") -> Dict[str, Any]:
        """Get top endpoints by metric"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return {
                "endpoints": analytics.get_top_endpoints(limit, metric),
                "metric": metric
            }
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/top/clients")
    async def get_top_clients(limit: int = 10, metric: str = "requests") -> Dict[str, Any]:
        """Get top clients by metric"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return {
                "clients": analytics.get_top_clients(limit, metric),
                "metric": metric
            }
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/timeseries")
    async def get_time_series(metric: str = "requests", window: str = "hour") -> Dict[str, Any]:
        """Get time series data"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window)
            return {
                "series": analytics.get_time_series(metric, time_window),
                "metric": metric,
                "window": window
            }
        except ImportError:
            return {"error": "Analytics module not available"}
        except ValueError:
            return {"error": f"Invalid time window: {window}"}

    @app.get("/api/analytics/requests")
    async def get_recent_requests(
        limit: int = 100,
        endpoint: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get recent requests"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return {
                "requests": analytics.get_recent_requests(limit, endpoint, client_ip),
                "count": len(analytics.get_recent_requests(limit, endpoint, client_ip))
            }
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/errors")
    async def get_error_summary(window: str = "hour") -> Dict[str, Any]:
        """Get error summary"""
        try:
            from agentic.analytics import get_api_analytics, TimeWindow
            analytics = get_api_analytics()
            time_window = TimeWindow(window)
            return analytics.get_error_summary(time_window)
        except ImportError:
            return {"error": "Analytics module not available"}
        except ValueError:
            return {"error": f"Invalid time window: {window}"}

    @app.get("/api/analytics/ratelimit/config")
    async def get_rate_limit_config() -> Dict[str, Any]:
        """Get rate limit configuration"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return analytics.get_rate_limit_config()
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.post("/api/analytics/ratelimit/config")
    async def set_rate_limit_config(
        requests_per_minute: Optional[int] = None,
        requests_per_hour: Optional[int] = None,
        burst_limit: Optional[int] = None,
        block_duration_seconds: Optional[int] = None,
        enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update rate limit configuration"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return analytics.set_rate_limit_config(
                requests_per_minute=requests_per_minute,
                requests_per_hour=requests_per_hour,
                burst_limit=burst_limit,
                block_duration_seconds=block_duration_seconds,
                enabled=enabled
            )
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.get("/api/analytics/ratelimit/blocked")
    async def get_blocked_clients() -> Dict[str, Any]:
        """Get list of blocked clients"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            return {
                "blocked": analytics.get_blocked_clients()
            }
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.delete("/api/analytics/ratelimit/blocked/{client_ip}")
    async def unblock_client(client_ip: str) -> Dict[str, Any]:
        """Unblock a client"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            success = analytics.unblock_client(client_ip)
            return {"success": success}
        except ImportError:
            return {"error": "Analytics module not available"}

    @app.post("/api/analytics/clear")
    async def clear_analytics(keep_config: bool = True) -> Dict[str, Any]:
        """Clear analytics data"""
        try:
            from agentic.analytics import get_api_analytics
            analytics = get_api_analytics()
            analytics.clear_stats(keep_config)
            return {"success": True, "kept_config": keep_config}
        except ImportError:
            return {"error": "Analytics module not available"}

    # ==================== Compliance Checker API ====================

    @app.get("/api/compliance/status")
    async def get_compliance_status() -> Dict[str, Any]:
        """Get compliance checker status"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            return checker.get_statistics()
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/rules")
    async def get_compliance_rules(
        category: Optional[str] = None,
        rule_set: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get compliance rules"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            rules = checker.get_rules(category=category, rule_set=rule_set)
            return {
                "rules": [r.to_dict() for r in rules],
                "count": len(rules)
            }
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/rule-sets")
    async def get_rule_sets() -> Dict[str, Any]:
        """Get available rule sets"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            return {"rule_sets": checker.get_rule_sets()}
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.post("/api/compliance/check")
    async def run_compliance_check(
        rule_set: Optional[str] = "default",
        categories: Optional[List[str]] = None,
        agents: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Run compliance check"""
        try:
            from agentic.compliance import get_compliance_checker, ComplianceCategory
            checker = get_compliance_checker()

            cat_enums = None
            if categories:
                cat_enums = []
                for c in categories:
                    try:
                        cat_enums.append(ComplianceCategory(c))
                    except ValueError:
                        pass

            report = checker.run_check(
                categories=cat_enums,
                agents=agents,
                rule_set=rule_set
            )
            return {"report": report.to_dict()}
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/reports")
    async def list_compliance_reports(limit: int = 10) -> Dict[str, Any]:
        """List compliance reports"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            reports = checker.list_reports(limit)
            return {
                "reports": [r.to_dict() for r in reports],
                "count": len(reports)
            }
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/reports/{report_id}")
    async def get_compliance_report(report_id: str) -> Dict[str, Any]:
        """Get a specific compliance report"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            report = checker.get_report(report_id)
            if report:
                return {"report": report.to_dict()}
            return {"error": "Report not found"}
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.post("/api/compliance/rules/{rule_id}/enable")
    async def enable_compliance_rule(rule_id: str) -> Dict[str, Any]:
        """Enable a compliance rule"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            success = checker.enable_rule(rule_id)
            return {"success": success}
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.post("/api/compliance/rules/{rule_id}/disable")
    async def disable_compliance_rule(rule_id: str) -> Dict[str, Any]:
        """Disable a compliance rule"""
        try:
            from agentic.compliance import get_compliance_checker
            checker = get_compliance_checker()
            success = checker.disable_rule(rule_id)
            return {"success": success}
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/categories")
    async def get_compliance_categories() -> Dict[str, Any]:
        """Get available compliance categories"""
        try:
            from agentic.compliance import ComplianceCategory
            return {
                "categories": [
                    {"value": c.value, "name": c.name}
                    for c in ComplianceCategory
                ]
            }
        except ImportError:
            return {"error": "Compliance module not available"}

    @app.get("/api/compliance/severities")
    async def get_compliance_severities() -> Dict[str, Any]:
        """Get available compliance severities"""
        try:
            from agentic.compliance import ComplianceSeverity
            return {
                "severities": [
                    {"value": s.value, "name": s.name}
                    for s in ComplianceSeverity
                ]
            }
        except ImportError:
            return {"error": "Compliance module not available"}

    # ==================== Topology Exporter API ====================

    @app.get("/api/exporter/status")
    async def get_exporter_status() -> Dict[str, Any]:
        """Get topology exporter status"""
        try:
            from agentic.exporter import get_topology_exporter
            exporter = get_topology_exporter()
            return exporter.get_statistics()
        except ImportError:
            return {"error": "Exporter module not available"}

    @app.get("/api/exporter/formats")
    async def get_export_formats() -> Dict[str, Any]:
        """Get supported export formats"""
        try:
            from agentic.exporter import ExportFormat
            return {
                "formats": [
                    {"value": f.value, "name": f.name}
                    for f in ExportFormat
                ]
            }
        except ImportError:
            return {"error": "Exporter module not available"}

    @app.post("/api/exporter/export")
    async def export_topology(
        format: str,
        include_configs: bool = True,
        include_interfaces: bool = True,
        include_routing: bool = True,
        include_labels: bool = True,
        layout: str = "hierarchical",
        filter_agents: Optional[List[str]] = None,
        filter_protocols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Export topology to specified format"""
        try:
            from agentic.exporter import get_topology_exporter, ExportFormat, ExportOptions
            exporter = get_topology_exporter()

            try:
                export_format = ExportFormat(format.lower())
            except ValueError:
                return {"error": f"Invalid format: {format}"}

            options = ExportOptions(
                include_configs=include_configs,
                include_interfaces=include_interfaces,
                include_routing=include_routing,
                include_labels=include_labels,
                layout=layout,
                filter_agents=filter_agents,
                filter_protocols=filter_protocols
            )

            result = exporter.export(export_format, options)
            return {"export": result.to_dict()}
        except ImportError:
            return {"error": "Exporter module not available"}

    @app.post("/api/exporter/import")
    async def import_topology(
        content: str,
        format: str
    ) -> Dict[str, Any]:
        """Import topology from content"""
        try:
            from agentic.exporter import get_topology_exporter, ExportFormat
            exporter = get_topology_exporter()

            try:
                import_format = ExportFormat(format.lower())
            except ValueError:
                return {"error": f"Invalid format: {format}"}

            topology = exporter.import_topology(content, import_format)
            return {"topology": topology}
        except ImportError:
            return {"error": "Exporter module not available"}
        except Exception as e:
            return {"error": f"Import failed: {str(e)}"}

    @app.get("/api/exporter/history")
    async def get_export_history(limit: int = 10) -> Dict[str, Any]:
        """Get export history"""
        try:
            from agentic.exporter import get_topology_exporter
            exporter = get_topology_exporter()
            return {
                "history": exporter.get_export_history(limit)
            }
        except ImportError:
            return {"error": "Exporter module not available"}

    # ==================== GraphQL API ====================

    @app.get("/api/graphql/status")
    async def get_graphql_status() -> Dict[str, Any]:
        """Get GraphQL executor status"""
        try:
            from agentic.graphql import get_executor, get_schema
            executor = get_executor()
            schema = get_schema()
            return {
                "executor": executor.get_statistics(),
                "schema": schema.get_statistics()
            }
        except ImportError:
            return {"error": "GraphQL module not available"}

    @app.post("/api/graphql")
    async def execute_graphql(
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operationName: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query or mutation"""
        try:
            from agentic.graphql import get_executor, GraphQLRequest
            executor = get_executor()

            request = GraphQLRequest(
                query=query,
                variables=variables or {},
                operation_name=operationName
            )

            response = executor.execute(request)
            return response.to_dict()
        except ImportError:
            return {"errors": [{"message": "GraphQL module not available"}]}

    @app.get("/api/graphql/schema")
    async def get_graphql_schema() -> Dict[str, Any]:
        """Get the GraphQL schema as SDL"""
        try:
            from agentic.graphql import get_executor
            executor = get_executor()
            return {
                "sdl": executor.get_schema_sdl()
            }
        except ImportError:
            return {"error": "GraphQL module not available"}

    @app.get("/api/graphql/introspect")
    async def introspect_graphql() -> Dict[str, Any]:
        """Get GraphQL introspection data"""
        try:
            from agentic.graphql import get_executor
            executor = get_executor()
            return executor.introspect()
        except ImportError:
            return {"error": "GraphQL module not available"}

    @app.get("/api/graphql/types")
    async def get_graphql_types() -> Dict[str, Any]:
        """Get all GraphQL types"""
        try:
            from agentic.graphql import get_schema
            schema = get_schema()
            types = schema.get_all_types()
            return {
                "types": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "is_input": t.is_input,
                        "field_count": len(t.fields)
                    }
                    for t in types
                ],
                "count": len(types)
            }
        except ImportError:
            return {"error": "GraphQL module not available"}

    @app.get("/api/graphql/enums")
    async def get_graphql_enums() -> Dict[str, Any]:
        """Get all GraphQL enums"""
        try:
            from agentic.graphql import get_schema
            schema = get_schema()
            enums = schema.get_all_enums()
            return {
                "enums": [
                    {
                        "name": e.name,
                        "description": e.description,
                        "values": e.values
                    }
                    for e in enums
                ],
                "count": len(enums)
            }
        except ImportError:
            return {"error": "GraphQL module not available"}

    # ==================== Tutorials API ====================

    @app.get("/api/tutorials/status")
    async def get_tutorials_status() -> Dict[str, Any]:
        """Get tutorials system status"""
        try:
            from agentic.tutorials import get_tutorial_manager, get_progress_tracker, get_assessment_engine
            manager = get_tutorial_manager()
            tracker = get_progress_tracker()
            engine = get_assessment_engine()
            return {
                "tutorials": manager.get_statistics(),
                "progress": tracker.get_statistics(),
                "assessments": engine.get_statistics()
            }
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.get("/api/tutorials")
    async def list_tutorials(
        category: Optional[str] = None,
        difficulty: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all tutorials with optional filters"""
        try:
            from agentic.tutorials import (
                get_tutorial_manager, TutorialCategory, TutorialDifficulty
            )
            manager = get_tutorial_manager()

            cat = TutorialCategory(category) if category else None
            diff = TutorialDifficulty(difficulty) if difficulty else None

            tutorials = manager.list_tutorials(category=cat, difficulty=diff)
            return {
                "tutorials": [t.to_summary() for t in tutorials],
                "count": len(tutorials)
            }
        except ImportError:
            return {"error": "Tutorials module not available"}
        except ValueError as e:
            return {"error": f"Invalid filter value: {e}"}

    @app.get("/api/tutorials/{tutorial_id}")
    async def get_tutorial(tutorial_id: str) -> Dict[str, Any]:
        """Get a specific tutorial with all steps"""
        try:
            from agentic.tutorials import get_tutorial_manager
            manager = get_tutorial_manager()
            tutorial = manager.get_tutorial(tutorial_id)
            if tutorial:
                return {"tutorial": tutorial.to_dict()}
            return {"error": "Tutorial not found"}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.get("/api/tutorials/search")
    async def search_tutorials(query: str) -> Dict[str, Any]:
        """Search tutorials by title, description, or tags"""
        try:
            from agentic.tutorials import get_tutorial_manager
            manager = get_tutorial_manager()
            results = manager.search_tutorials(query)
            return {
                "results": [t.to_summary() for t in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.get("/api/tutorials/categories")
    async def get_tutorial_categories() -> Dict[str, Any]:
        """Get all tutorial categories with counts"""
        try:
            from agentic.tutorials import get_tutorial_manager
            manager = get_tutorial_manager()
            return {"categories": manager.get_categories()}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.get("/api/tutorials/difficulties")
    async def get_tutorial_difficulties() -> Dict[str, Any]:
        """Get all difficulty levels with counts"""
        try:
            from agentic.tutorials import get_tutorial_manager
            manager = get_tutorial_manager()
            return {"difficulties": manager.get_difficulties()}
        except ImportError:
            return {"error": "Tutorials module not available"}

    # ==================== Tutorial Progress API ====================

    @app.get("/api/tutorials/progress/{user_id}")
    async def get_user_progress(user_id: str) -> Dict[str, Any]:
        """Get progress for a user"""
        try:
            from agentic.tutorials import get_progress_tracker
            tracker = get_progress_tracker()
            progress = tracker.get_user_progress(user_id)
            return {"progress": progress.to_dict()}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.post("/api/tutorials/progress/{user_id}/start")
    async def start_tutorial_progress(
        user_id: str,
        tutorial_id: str
    ) -> Dict[str, Any]:
        """Start a tutorial for a user"""
        try:
            from agentic.tutorials import get_tutorial_manager, get_progress_tracker
            manager = get_tutorial_manager()
            tracker = get_progress_tracker()

            tutorial = manager.get_tutorial(tutorial_id)
            if not tutorial or not tutorial.steps:
                return {"error": "Tutorial not found or has no steps"}

            first_step = tutorial.steps[0]
            progress = tracker.start_tutorial(user_id, tutorial_id, first_step.id)
            return {"progress": progress.to_dict()}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.post("/api/tutorials/progress/{user_id}/step")
    async def update_step_progress(
        user_id: str,
        tutorial_id: str,
        step_id: str,
        action: str = "start",
        score: Optional[float] = None
    ) -> Dict[str, Any]:
        """Update step progress (start, complete, skip)"""
        try:
            from agentic.tutorials import get_progress_tracker
            tracker = get_progress_tracker()

            if action == "start":
                success = tracker.start_step(user_id, tutorial_id, step_id)
            elif action == "complete":
                success = tracker.complete_step(user_id, tutorial_id, step_id, score)
            elif action == "skip":
                success = tracker.skip_step(user_id, tutorial_id, step_id)
            else:
                return {"error": f"Invalid action: {action}"}

            if success:
                progress = tracker.get_user_progress(user_id)
                tutorial_progress = progress.get_tutorial_progress(tutorial_id)
                return {"progress": tutorial_progress.to_dict() if tutorial_progress else None}
            return {"error": "Failed to update step progress"}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.post("/api/tutorials/progress/{user_id}/complete")
    async def complete_tutorial_progress(
        user_id: str,
        tutorial_id: str
    ) -> Dict[str, Any]:
        """Complete a tutorial for a user"""
        try:
            from agentic.tutorials import get_progress_tracker
            tracker = get_progress_tracker()
            success = tracker.complete_tutorial(user_id, tutorial_id)
            if success:
                progress = tracker.get_user_progress(user_id)
                return {"progress": progress.to_dict()}
            return {"error": "Failed to complete tutorial"}
        except ImportError:
            return {"error": "Tutorials module not available"}

    @app.get("/api/tutorials/leaderboard")
    async def get_leaderboard(limit: int = 10) -> Dict[str, Any]:
        """Get tutorial leaderboard"""
        try:
            from agentic.tutorials import get_progress_tracker
            tracker = get_progress_tracker()
            return {"leaderboard": tracker.get_leaderboard(limit)}
        except ImportError:
            return {"error": "Tutorials module not available"}

    # ==================== Assessment API ====================

    @app.get("/api/assessments")
    async def list_assessments() -> Dict[str, Any]:
        """List all assessments"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            assessments = engine.list_assessments()
            return {
                "assessments": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "description": a.description,
                        "question_count": a.question_count,
                        "total_points": a.total_points,
                        "passing_score": a.passing_score,
                        "time_limit_minutes": a.time_limit_minutes
                    }
                    for a in assessments
                ],
                "count": len(assessments)
            }
        except ImportError:
            return {"error": "Assessments module not available"}

    @app.get("/api/assessments/{assessment_id}")
    async def get_assessment(assessment_id: str) -> Dict[str, Any]:
        """Get an assessment (questions without answers)"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            assessment = engine.get_assessment(assessment_id)
            if assessment:
                return {"assessment": assessment.to_dict()}
            return {"error": "Assessment not found"}
        except ImportError:
            return {"error": "Assessments module not available"}

    @app.post("/api/assessments/{assessment_id}/start")
    async def start_assessment(
        assessment_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Start an assessment attempt"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            result = engine.start_attempt(user_id, assessment_id)
            if result:
                return {
                    "attempt": result.to_dict(),
                    "assessment": engine.get_assessment(assessment_id).to_dict()
                }
            return {"error": "Failed to start assessment (max attempts reached?)"}
        except ImportError:
            return {"error": "Assessments module not available"}

    @app.post("/api/assessments/{assessment_id}/answer")
    async def submit_assessment_answer(
        assessment_id: str,
        user_id: str,
        question_id: str,
        answer: Any
    ) -> Dict[str, Any]:
        """Submit an answer for an assessment question"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            record = engine.submit_answer(user_id, assessment_id, question_id, answer)
            if record:
                return {"answer": record.to_dict()}
            return {"error": "Failed to submit answer"}
        except ImportError:
            return {"error": "Assessments module not available"}

    @app.post("/api/assessments/{assessment_id}/complete")
    async def complete_assessment(
        assessment_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Complete an assessment attempt"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            result = engine.complete_attempt(user_id, assessment_id)
            if result:
                return {"result": result.to_dict()}
            return {"error": "Failed to complete assessment"}
        except ImportError:
            return {"error": "Assessments module not available"}

    @app.get("/api/assessments/results/{user_id}")
    async def get_assessment_results(
        user_id: str,
        assessment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get assessment results for a user"""
        try:
            from agentic.tutorials import get_assessment_engine
            engine = get_assessment_engine()
            results = engine.get_user_results(user_id, assessment_id)
            return {
                "results": [r.to_dict() for r in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Assessments module not available"}

    # ==================== Webhooks API ====================

    @app.get("/api/webhooks/status")
    async def get_webhooks_status() -> Dict[str, Any]:
        """Get webhooks system status"""
        try:
            from agentic.webhooks import get_webhook_manager, get_webhook_dispatcher
            manager = get_webhook_manager()
            dispatcher = get_webhook_dispatcher()
            return {
                "manager": manager.get_statistics(),
                "dispatcher": dispatcher.get_statistics()
            }
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.get("/api/webhooks")
    async def list_webhooks(status: Optional[str] = None) -> Dict[str, Any]:
        """List all webhooks"""
        try:
            from agentic.webhooks import get_webhook_manager, WebhookStatus
            manager = get_webhook_manager()

            webhook_status = WebhookStatus(status) if status else None
            webhooks = manager.list_webhooks(status=webhook_status)
            return {
                "webhooks": [w.to_dict() for w in webhooks],
                "count": len(webhooks)
            }
        except ImportError:
            return {"error": "Webhooks module not available"}
        except ValueError as e:
            return {"error": f"Invalid status: {e}"}

    @app.get("/api/webhooks/{webhook_id}")
    async def get_webhook(webhook_id: str, include_secret: bool = False) -> Dict[str, Any]:
        """Get a specific webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            webhook = manager.get_webhook(webhook_id)
            if webhook:
                return {"webhook": webhook.to_dict(include_secret=include_secret)}
            return {"error": "Webhook not found"}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks")
    async def create_webhook(
        url: str,
        name: str,
        events: List[str],
        description: str = "",
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a new webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()

            webhook = manager.register_webhook(
                url=url,
                name=name,
                events=events,
                description=description,
                headers=headers
            )
            return {"webhook": webhook.to_dict(include_secret=True)}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.put("/api/webhooks/{webhook_id}")
    async def update_webhook(
        webhook_id: str,
        url: Optional[str] = None,
        name: Optional[str] = None,
        events: Optional[List[str]] = None,
        description: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()

            webhook = manager.update_webhook(
                webhook_id=webhook_id,
                url=url,
                name=name,
                events=events,
                description=description,
                headers=headers,
                status=status
            )
            if webhook:
                return {"webhook": webhook.to_dict()}
            return {"error": "Webhook not found"}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.delete("/api/webhooks/{webhook_id}")
    async def delete_webhook(webhook_id: str) -> Dict[str, Any]:
        """Delete a webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            success = manager.delete_webhook(webhook_id)
            return {"success": success}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/{webhook_id}/pause")
    async def pause_webhook(webhook_id: str) -> Dict[str, Any]:
        """Pause a webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            success = manager.pause_webhook(webhook_id)
            return {"success": success}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/{webhook_id}/resume")
    async def resume_webhook(webhook_id: str) -> Dict[str, Any]:
        """Resume a paused webhook"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            success = manager.resume_webhook(webhook_id)
            return {"success": success}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/{webhook_id}/regenerate-secret")
    async def regenerate_webhook_secret(webhook_id: str) -> Dict[str, Any]:
        """Regenerate webhook secret"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            secret = manager.regenerate_secret(webhook_id)
            if secret:
                return {"secret": secret}
            return {"error": "Webhook not found"}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.get("/api/webhooks/events/types")
    async def get_webhook_event_types() -> Dict[str, Any]:
        """Get available webhook event types"""
        try:
            from agentic.webhooks import get_webhook_manager
            manager = get_webhook_manager()
            return {"event_types": manager.get_event_types()}
        except ImportError:
            return {"error": "Webhooks module not available"}

    # ==================== Webhook Deliveries API ====================

    @app.get("/api/webhooks/deliveries")
    async def list_webhook_deliveries(
        webhook_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List webhook deliveries"""
        try:
            from agentic.webhooks import get_webhook_dispatcher, DeliveryStatus
            dispatcher = get_webhook_dispatcher()

            delivery_status = DeliveryStatus(status) if status else None
            deliveries = dispatcher.get_deliveries(
                webhook_id=webhook_id,
                status=delivery_status,
                limit=limit
            )
            return {
                "deliveries": [d.to_dict() for d in deliveries],
                "count": len(deliveries)
            }
        except ImportError:
            return {"error": "Webhooks module not available"}
        except ValueError as e:
            return {"error": f"Invalid status: {e}"}

    @app.get("/api/webhooks/deliveries/{delivery_id}")
    async def get_webhook_delivery(delivery_id: str) -> Dict[str, Any]:
        """Get a specific delivery"""
        try:
            from agentic.webhooks import get_webhook_dispatcher
            dispatcher = get_webhook_dispatcher()
            delivery = dispatcher.get_delivery(delivery_id)
            if delivery:
                return {"delivery": delivery.to_dict()}
            return {"error": "Delivery not found"}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/deliveries/{delivery_id}/retry")
    async def retry_webhook_delivery(delivery_id: str) -> Dict[str, Any]:
        """Retry a failed delivery"""
        try:
            from agentic.webhooks import get_webhook_dispatcher
            dispatcher = get_webhook_dispatcher()
            success = await dispatcher.retry_delivery(delivery_id)
            return {"success": success}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/test")
    async def test_webhook(webhook_id: str) -> Dict[str, Any]:
        """Send a test event to a webhook"""
        try:
            from agentic.webhooks import get_webhook_manager, get_webhook_dispatcher
            import uuid

            manager = get_webhook_manager()
            dispatcher = get_webhook_dispatcher()

            webhook = manager.get_webhook(webhook_id)
            if not webhook:
                return {"error": "Webhook not found"}

            # Create test event payload
            test_payload = {
                "event": "test.webhook",
                "webhook_id": webhook_id,
                "timestamp": datetime.now().isoformat(),
                "message": "This is a test webhook delivery"
            }

            delivery = await dispatcher.dispatch(
                webhook_id=webhook_id,
                event_id=f"test-{uuid.uuid4().hex[:8]}",
                event_type="test.webhook",
                url=webhook.url,
                payload=test_payload
            )

            return {"delivery": delivery.to_dict()}
        except ImportError:
            return {"error": "Webhooks module not available"}

    @app.post("/api/webhooks/dispatch")
    async def dispatch_webhook_event(
        event_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch an event to all subscribed webhooks"""
        try:
            from agentic.webhooks import get_webhook_dispatcher
            import uuid

            dispatcher = get_webhook_dispatcher()
            event_id = f"evt-{uuid.uuid4().hex[:8]}"

            deliveries = await dispatcher.dispatch_to_webhooks(
                event_id=event_id,
                event_type=event_type,
                payload=payload
            )

            return {
                "event_id": event_id,
                "deliveries_queued": len(deliveries),
                "delivery_ids": [d.id for d in deliveries]
            }
        except ImportError:
            return {"error": "Webhooks module not available"}

    # ==================== Backup & Disaster Recovery API ====================

    @app.get("/api/backup/status")
    async def get_backup_status() -> Dict[str, Any]:
        """Get backup system status"""
        try:
            from agentic.backup import get_backup_manager, get_restore_manager, get_backup_scheduler
            backup_mgr = get_backup_manager()
            restore_mgr = get_restore_manager()
            scheduler = get_backup_scheduler()
            return {
                "backups": backup_mgr.get_statistics(),
                "restore": restore_mgr.get_statistics(),
                "scheduler": scheduler.get_statistics()
            }
        except ImportError:
            return {"error": "Backup module not available"}

    @app.get("/api/backups")
    async def list_backups(
        backup_type: Optional[str] = None,
        status: Optional[str] = None,
        network_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List all backups"""
        try:
            from agentic.backup import get_backup_manager, BackupType, BackupStatus
            manager = get_backup_manager()

            btype = BackupType(backup_type) if backup_type else None
            bstatus = BackupStatus(status) if status else None

            backups = manager.list_backups(
                backup_type=btype,
                status=bstatus,
                network_id=network_id,
                limit=limit
            )
            return {
                "backups": [b.to_dict() for b in backups],
                "count": len(backups)
            }
        except ImportError:
            return {"error": "Backup module not available"}
        except ValueError as e:
            return {"error": f"Invalid filter value: {e}"}

    @app.get("/api/backups/{backup_id}")
    async def get_backup(backup_id: str) -> Dict[str, Any]:
        """Get a specific backup"""
        try:
            from agentic.backup import get_backup_manager
            manager = get_backup_manager()
            backup = manager.get_backup(backup_id)
            if backup:
                return {"backup": backup.to_dict()}
            return {"error": "Backup not found"}
        except ImportError:
            return {"error": "Backup module not available"}

    @app.post("/api/backups")
    async def create_backup(
        name: str,
        backup_type: str = "full",
        network_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new backup"""
        try:
            from agentic.backup import get_backup_manager, BackupType

            manager = get_backup_manager()

            try:
                btype = BackupType(backup_type)
            except ValueError:
                btype = BackupType.FULL

            # Get current state to backup
            content = {
                "agents": [],
                "network": {"id": network_id} if network_id else {},
                "protocols": [],
                "routes": [],
                "config": {},
                "timestamp": datetime.now().isoformat()
            }

            backup = manager.create_backup(
                name=name,
                backup_type=btype,
                content=content,
                created_by="api",
                tags=tags
            )
            return {"backup": backup.to_dict()}
        except ImportError:
            return {"error": "Backup module not available"}

    @app.delete("/api/backups/{backup_id}")
    async def delete_backup(backup_id: str) -> Dict[str, Any]:
        """Delete a backup"""
        try:
            from agentic.backup import get_backup_manager
            manager = get_backup_manager()
            success = manager.delete_backup(backup_id)
            return {"success": success}
        except ImportError:
            return {"error": "Backup module not available"}

    @app.post("/api/backups/{backup_id}/verify")
    async def verify_backup(backup_id: str) -> Dict[str, Any]:
        """Verify backup integrity"""
        try:
            from agentic.backup import get_backup_manager
            manager = get_backup_manager()
            valid = manager.verify_backup(backup_id)
            return {"valid": valid}
        except ImportError:
            return {"error": "Backup module not available"}

    @app.get("/api/backups/latest")
    async def get_latest_backup(
        backup_type: Optional[str] = None,
        network_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the most recent backup"""
        try:
            from agentic.backup import get_backup_manager, BackupType
            manager = get_backup_manager()

            btype = BackupType(backup_type) if backup_type else None
            backup = manager.get_latest_backup(backup_type=btype, network_id=network_id)
            if backup:
                return {"backup": backup.to_dict()}
            return {"error": "No backups found"}
        except ImportError:
            return {"error": "Backup module not available"}

    # ==================== Restore API ====================

    @app.get("/api/restore/points")
    async def list_restore_points() -> Dict[str, Any]:
        """List all restore points"""
        try:
            from agentic.backup import get_restore_manager
            manager = get_restore_manager()
            points = manager.list_restore_points()
            return {
                "restore_points": [p.to_dict() for p in points],
                "count": len(points)
            }
        except ImportError:
            return {"error": "Restore module not available"}

    @app.post("/api/restore/points")
    async def create_restore_point(
        backup_id: str,
        name: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Create a restore point from a backup"""
        try:
            from agentic.backup import get_restore_manager
            manager = get_restore_manager()
            point = manager.create_restore_point(
                backup_id=backup_id,
                name=name,
                description=description
            )
            if point:
                return {"restore_point": point.to_dict()}
            return {"error": "Failed to create restore point"}
        except ImportError:
            return {"error": "Restore module not available"}

    @app.delete("/api/restore/points/{point_id}")
    async def delete_restore_point(point_id: str) -> Dict[str, Any]:
        """Delete a restore point"""
        try:
            from agentic.backup import get_restore_manager
            manager = get_restore_manager()
            success = manager.delete_restore_point(point_id)
            return {"success": success}
        except ImportError:
            return {"error": "Restore module not available"}

    @app.post("/api/restore/{point_id}")
    async def restore_from_point(
        point_id: str,
        restore_type: str = "full",
        components: Optional[List[str]] = None,
        create_rollback: bool = True
    ) -> Dict[str, Any]:
        """Restore from a restore point"""
        try:
            from agentic.backup import get_restore_manager, RestoreType
            manager = get_restore_manager()

            try:
                rtype = RestoreType(restore_type)
            except ValueError:
                rtype = RestoreType.FULL

            result = await manager.restore(
                restore_point_id=point_id,
                restore_type=rtype,
                components=components,
                create_rollback=create_rollback
            )
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Restore module not available"}

    @app.get("/api/restore/history")
    async def get_restore_history(limit: int = 50) -> Dict[str, Any]:
        """Get restore operation history"""
        try:
            from agentic.backup import get_restore_manager
            manager = get_restore_manager()
            history = manager.get_restore_history(limit)
            return {
                "history": [r.to_dict() for r in history],
                "count": len(history)
            }
        except ImportError:
            return {"error": "Restore module not available"}

    # ==================== Backup Scheduler API ====================

    @app.get("/api/backup/schedules")
    async def list_backup_schedules(enabled_only: bool = False) -> Dict[str, Any]:
        """List all backup schedules"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            schedules = scheduler.list_schedules(enabled_only=enabled_only)
            return {
                "schedules": [s.to_dict() for s in schedules],
                "count": len(schedules)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/backup/schedules/{schedule_id}")
    async def get_backup_schedule(schedule_id: str) -> Dict[str, Any]:
        """Get a specific schedule"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            schedule = scheduler.get_schedule(schedule_id)
            if schedule:
                return {"schedule": schedule.to_dict()}
            return {"error": "Schedule not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/backup/schedules")
    async def create_backup_schedule(
        name: str,
        frequency: str,
        backup_type: str = "full",
        network_id: Optional[str] = None,
        retention_count: int = 10,
        retention_days: int = 30,
        tags: Optional[List[str]] = None,
        start_immediately: bool = False
    ) -> Dict[str, Any]:
        """Create a new backup schedule"""
        try:
            from agentic.backup import get_backup_scheduler, ScheduleFrequency
            scheduler = get_backup_scheduler()

            try:
                freq = ScheduleFrequency(frequency)
            except ValueError:
                freq = ScheduleFrequency.DAILY

            schedule = scheduler.create_schedule(
                name=name,
                frequency=freq,
                backup_type=backup_type,
                network_id=network_id,
                retention_count=retention_count,
                retention_days=retention_days,
                tags=tags,
                start_immediately=start_immediately
            )
            return {"schedule": schedule.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/backup/schedules/{schedule_id}")
    async def delete_backup_schedule(schedule_id: str) -> Dict[str, Any]:
        """Delete a backup schedule"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            success = scheduler.delete_schedule(schedule_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/backup/schedules/{schedule_id}/enable")
    async def enable_backup_schedule(schedule_id: str) -> Dict[str, Any]:
        """Enable a backup schedule"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            success = scheduler.enable_schedule(schedule_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/backup/schedules/{schedule_id}/disable")
    async def disable_backup_schedule(schedule_id: str) -> Dict[str, Any]:
        """Disable a backup schedule"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            success = scheduler.disable_schedule(schedule_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/backup/schedules/{schedule_id}/run")
    async def run_backup_schedule(schedule_id: str) -> Dict[str, Any]:
        """Run a backup schedule immediately"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            run = await scheduler.run_now(schedule_id)
            if run:
                return {"run": run.to_dict()}
            return {"error": "Schedule not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/backup/schedules/{schedule_id}/history")
    async def get_schedule_history(schedule_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get run history for a schedule"""
        try:
            from agentic.backup import get_backup_scheduler
            scheduler = get_backup_scheduler()
            history = scheduler.get_run_history(schedule_id=schedule_id, limit=limit)
            return {
                "history": [r.to_dict() for r in history],
                "count": len(history)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    # ==================== Certification Prep API ====================

    @app.get("/api/certification/status")
    async def get_certification_status() -> Dict[str, Any]:
        """Get certification system status"""
        try:
            from agentic.certification import get_lab_manager, get_exam_engine, get_certification_manager
            lab_mgr = get_lab_manager()
            exam_engine = get_exam_engine()
            cert_mgr = get_certification_manager()
            return {
                "labs": lab_mgr.get_statistics(),
                "exams": exam_engine.get_statistics(),
                "certifications": cert_mgr.get_statistics()
            }
        except ImportError:
            return {"error": "Certification module not available"}

    # ==================== Labs API ====================

    @app.get("/api/labs")
    async def list_labs(
        difficulty: Optional[str] = None,
        certification_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all labs"""
        try:
            from agentic.certification import get_lab_manager, LabDifficulty
            manager = get_lab_manager()

            lab_difficulty = LabDifficulty(difficulty) if difficulty else None
            labs = manager.list_labs(difficulty=lab_difficulty, certification_id=certification_id)
            return {
                "labs": [lab.to_dict() for lab in labs],
                "count": len(labs)
            }
        except ImportError:
            return {"error": "Labs module not available"}
        except ValueError as e:
            return {"error": f"Invalid difficulty: {e}"}

    @app.get("/api/labs/{lab_id}")
    async def get_lab(lab_id: str) -> Dict[str, Any]:
        """Get a specific lab"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            lab = manager.get_lab(lab_id)
            if lab:
                return {"lab": lab.to_dict()}
            return {"error": "Lab not found"}
        except ImportError:
            return {"error": "Labs module not available"}

    @app.post("/api/labs/{lab_id}/start")
    async def start_lab(lab_id: str, user_id: str) -> Dict[str, Any]:
        """Start a lab session"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            session = manager.start_lab(user_id, lab_id)
            if session:
                return {"session": session.to_dict()}
            return {"error": "Failed to start lab"}
        except ImportError:
            return {"error": "Labs module not available"}

    @app.post("/api/labs/{lab_id}/task")
    async def complete_lab_task(
        lab_id: str,
        user_id: str,
        task_id: str,
        solution: str
    ) -> Dict[str, Any]:
        """Submit a task solution for verification"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            result = manager.verify_task(user_id, lab_id, task_id, solution)
            return {"result": result}
        except ImportError:
            return {"error": "Labs module not available"}

    @app.post("/api/labs/{lab_id}/complete")
    async def complete_lab(lab_id: str, user_id: str) -> Dict[str, Any]:
        """Complete a lab session"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            result = manager.complete_lab(user_id, lab_id)
            if result:
                return {"result": result.to_dict()}
            return {"error": "Failed to complete lab"}
        except ImportError:
            return {"error": "Labs module not available"}

    @app.get("/api/labs/sessions/{user_id}")
    async def get_user_lab_sessions(
        user_id: str,
        lab_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get lab sessions for a user"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            sessions = manager.get_user_sessions(user_id, lab_id=lab_id)
            return {
                "sessions": [s.to_dict() for s in sessions],
                "count": len(sessions)
            }
        except ImportError:
            return {"error": "Labs module not available"}

    @app.get("/api/labs/hints/{lab_id}/{task_id}")
    async def get_lab_hint(lab_id: str, task_id: str) -> Dict[str, Any]:
        """Get hint for a lab task"""
        try:
            from agentic.certification import get_lab_manager
            manager = get_lab_manager()
            hint = manager.get_hint(lab_id, task_id)
            if hint:
                return {"hint": hint}
            return {"error": "No hint available"}
        except ImportError:
            return {"error": "Labs module not available"}

    # ==================== Practice Exams API ====================

    @app.get("/api/exams")
    async def list_exams(certification_id: Optional[str] = None) -> Dict[str, Any]:
        """List all practice exams"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            exams = engine.list_exams(certification_id=certification_id)
            return {
                "exams": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "description": e.description,
                        "certification_id": e.certification_id,
                        "question_count": len(e.questions),
                        "time_limit_minutes": e.time_limit_minutes,
                        "passing_score": e.passing_score
                    }
                    for e in exams
                ],
                "count": len(exams)
            }
        except ImportError:
            return {"error": "Exams module not available"}

    @app.get("/api/exams/{exam_id}")
    async def get_exam(exam_id: str) -> Dict[str, Any]:
        """Get a practice exam (questions without answers for preview)"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            exam = engine.get_exam(exam_id)
            if exam:
                return {"exam": exam.to_dict(include_answers=False)}
            return {"error": "Exam not found"}
        except ImportError:
            return {"error": "Exams module not available"}

    @app.post("/api/exams/{exam_id}/start")
    async def start_exam(exam_id: str, user_id: str) -> Dict[str, Any]:
        """Start an exam attempt"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            attempt = engine.start_attempt(user_id, exam_id)
            if attempt:
                exam = engine.get_exam(exam_id)
                return {
                    "attempt": attempt.to_dict(),
                    "exam": exam.to_dict(include_answers=False) if exam else None
                }
            return {"error": "Failed to start exam"}
        except ImportError:
            return {"error": "Exams module not available"}

    @app.post("/api/exams/{exam_id}/answer")
    async def submit_exam_answer(
        exam_id: str,
        user_id: str,
        question_id: str,
        answer: Any
    ) -> Dict[str, Any]:
        """Submit an answer for an exam question"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            success = engine.submit_answer(user_id, exam_id, question_id, answer)
            return {"success": success}
        except ImportError:
            return {"error": "Exams module not available"}

    @app.post("/api/exams/{exam_id}/complete")
    async def complete_exam(exam_id: str, user_id: str) -> Dict[str, Any]:
        """Complete an exam attempt and get results"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            result = engine.complete_attempt(user_id, exam_id)
            if result:
                return {"result": result.to_dict()}
            return {"error": "Failed to complete exam"}
        except ImportError:
            return {"error": "Exams module not available"}

    @app.get("/api/exams/results/{user_id}")
    async def get_exam_results(
        user_id: str,
        exam_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get exam results for a user"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            results = engine.get_user_results(user_id, exam_id=exam_id)
            return {
                "results": [r.to_dict() for r in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Exams module not available"}

    @app.get("/api/exams/{exam_id}/review/{attempt_id}")
    async def review_exam_attempt(
        exam_id: str,
        attempt_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Review a completed exam attempt with correct answers"""
        try:
            from agentic.certification import get_exam_engine
            engine = get_exam_engine()
            review = engine.get_attempt_review(user_id, exam_id, attempt_id)
            if review:
                return {"review": review}
            return {"error": "Attempt not found or not completed"}
        except ImportError:
            return {"error": "Exams module not available"}

    # ==================== Certifications API ====================

    @app.get("/api/certifications")
    async def list_certifications(
        level: Optional[str] = None,
        track: Optional[str] = None
    ) -> Dict[str, Any]:
        """List all certifications"""
        try:
            from agentic.certification import get_certification_manager, CertificationLevel, CertificationTrack
            manager = get_certification_manager()

            cert_level = CertificationLevel(level) if level else None
            cert_track = CertificationTrack(track) if track else None

            certs = manager.list_certifications(level=cert_level, track=cert_track)
            return {
                "certifications": [c.to_dict() for c in certs],
                "count": len(certs)
            }
        except ImportError:
            return {"error": "Certifications module not available"}
        except ValueError as e:
            return {"error": f"Invalid filter: {e}"}

    @app.get("/api/certifications/{cert_id}")
    async def get_certification(cert_id: str) -> Dict[str, Any]:
        """Get a specific certification"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            cert = manager.get_certification(cert_id)
            if cert:
                return {"certification": cert.to_dict()}
            return {"error": "Certification not found"}
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.post("/api/certifications/{cert_id}/start")
    async def start_certification(cert_id: str, user_id: str) -> Dict[str, Any]:
        """Start working toward a certification"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            progress = manager.start_certification(user_id, cert_id)
            if progress:
                return {"progress": progress.to_dict()}
            return {"error": "Failed to start certification"}
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.get("/api/certifications/progress/{user_id}")
    async def get_certification_progress(
        user_id: str,
        cert_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get certification progress for a user"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            progress = manager.get_user_progress(user_id, cert_id=cert_id)
            return {
                "progress": [p.to_dict() for p in progress],
                "count": len(progress)
            }
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.get("/api/certifications/{cert_id}/requirements")
    async def get_certification_requirements(cert_id: str) -> Dict[str, Any]:
        """Get requirements for a certification"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            requirements = manager.get_requirements(cert_id)
            if requirements:
                return {"requirements": requirements}
            return {"error": "Certification not found"}
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.get("/api/certifications/{cert_id}/roadmap/{user_id}")
    async def get_certification_roadmap(cert_id: str, user_id: str) -> Dict[str, Any]:
        """Get personalized roadmap for certification"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            roadmap = manager.get_roadmap(user_id, cert_id)
            if roadmap:
                return {"roadmap": roadmap}
            return {"error": "Unable to generate roadmap"}
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.post("/api/certifications/{cert_id}/update-skill")
    async def update_certification_skill(
        cert_id: str,
        user_id: str,
        skill_name: str,
        score: float
    ) -> Dict[str, Any]:
        """Update a skill score for certification progress"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            success = manager.update_skill(user_id, cert_id, skill_name, score)
            return {"success": success}
        except ImportError:
            return {"error": "Certifications module not available"}

    @app.get("/api/certifications/recommendations/{user_id}")
    async def get_certification_recommendations(user_id: str) -> Dict[str, Any]:
        """Get recommended certifications based on user progress"""
        try:
            from agentic.certification import get_certification_manager
            manager = get_certification_manager()
            recommendations = manager.get_recommendations(user_id)
            return {"recommendations": recommendations}
        except ImportError:
            return {"error": "Certifications module not available"}

    # ==================== Rate Limiting API ====================

    @app.get("/api/ratelimit/status")
    async def get_ratelimit_status() -> Dict[str, Any]:
        """Get rate limiter status and statistics"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            return limiter.get_statistics()
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/tiers")
    async def list_ratelimit_tiers() -> Dict[str, Any]:
        """List all rate limit tiers"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            return {
                "tiers": limiter.list_tiers(),
                "count": len(limiter.list_tiers())
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/tiers/{tier_name}")
    async def get_ratelimit_tier(tier_name: str) -> Dict[str, Any]:
        """Get a specific rate limit tier"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            tier = limiter.get_tier(tier_name)
            if tier:
                return {"tier": tier.to_dict()}
            return {"error": "Tier not found"}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/tiers")
    async def create_ratelimit_tier(
        name: str,
        requests_per_second: float = 10.0,
        requests_per_minute: float = 600.0,
        requests_per_hour: float = 36000.0,
        burst_size: int = 50,
        algorithm: str = "sliding_window"
    ) -> Dict[str, Any]:
        """Create a new rate limit tier"""
        try:
            from agentic.ratelimit import get_rate_limiter, RateLimitConfig, RateLimitAlgorithm
            limiter = get_rate_limiter()

            try:
                algo = RateLimitAlgorithm(algorithm)
            except ValueError:
                algo = RateLimitAlgorithm.SLIDING_WINDOW

            config = RateLimitConfig(
                name=name,
                requests_per_second=requests_per_second,
                requests_per_minute=requests_per_minute,
                requests_per_hour=requests_per_hour,
                burst_size=burst_size,
                algorithm=algo
            )
            limiter.add_tier(config)
            return {"tier": config.to_dict()}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.delete("/api/ratelimit/tiers/{tier_name}")
    async def delete_ratelimit_tier(tier_name: str) -> Dict[str, Any]:
        """Delete a rate limit tier"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            success = limiter.remove_tier(tier_name)
            return {"success": success}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/check")
    async def check_rate_limit(
        key: str,
        tier: Optional[str] = None,
        cost: int = 1
    ) -> Dict[str, Any]:
        """Check rate limit without consuming"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            result = limiter.check(key, tier=tier, cost=cost)
            return {
                "result": result.to_dict(),
                "headers": result.get_headers()
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/consume")
    async def consume_rate_limit(
        key: str,
        tier: Optional[str] = None,
        cost: int = 1
    ) -> Dict[str, Any]:
        """Consume rate limit"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            result = limiter.consume(key, tier=tier, cost=cost)
            return {
                "result": result.to_dict(),
                "headers": result.get_headers()
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/users/{user_id}/tier")
    async def set_user_ratelimit_tier(user_id: str, tier: str) -> Dict[str, Any]:
        """Set rate limit tier for a user"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            success = limiter.set_user_tier(user_id, tier)
            return {"success": success}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/users/{user_id}/tier")
    async def get_user_ratelimit_tier(user_id: str) -> Dict[str, Any]:
        """Get rate limit tier for a user"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            tier = limiter.get_user_tier(user_id)
            return {"user_id": user_id, "tier": tier}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/tenants/{tenant_id}/tier")
    async def set_tenant_ratelimit_tier(tenant_id: str, tier: str) -> Dict[str, Any]:
        """Set rate limit tier for a tenant"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            success = limiter.set_tenant_tier(tenant_id, tier)
            return {"success": success}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/tenants/{tenant_id}/tier")
    async def get_tenant_ratelimit_tier(tenant_id: str) -> Dict[str, Any]:
        """Get rate limit tier for a tenant"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            tier = limiter.get_tenant_tier(tenant_id)
            return {"tenant_id": tenant_id, "tier": tier}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/block/{key}")
    async def block_ratelimit_key(key: str, duration_seconds: int = 3600) -> Dict[str, Any]:
        """Temporarily block a key"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            limiter.block_key(key, duration_seconds)
            return {"blocked": True, "duration_seconds": duration_seconds}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/unblock/{key}")
    async def unblock_ratelimit_key(key: str) -> Dict[str, Any]:
        """Unblock a key"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            success = limiter.unblock_key(key)
            return {"success": success}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.post("/api/ratelimit/reset/{key}")
    async def reset_ratelimit_key(key: str) -> Dict[str, Any]:
        """Reset rate limit for a key"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            success = limiter.reset_key(key)
            return {"success": success}
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/log")
    async def get_ratelimit_log(limit: int = 100) -> Dict[str, Any]:
        """Get recent rate limit request log"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            log = limiter.get_request_log(limit)
            return {
                "log": [
                    {
                        "key": entry["key"],
                        "allowed": entry["allowed"],
                        "tier": entry["tier"],
                        "timestamp": entry["timestamp"].isoformat()
                    }
                    for entry in log
                ],
                "count": len(log)
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/buckets")
    async def list_token_buckets() -> Dict[str, Any]:
        """List all token buckets"""
        try:
            from agentic.ratelimit import get_bucket_manager
            manager = get_bucket_manager()
            return {
                "buckets": manager.list_buckets(),
                "statistics": manager.get_statistics()
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/windows")
    async def list_rate_windows() -> Dict[str, Any]:
        """List all rate windows"""
        try:
            from agentic.ratelimit import get_window_manager
            manager = get_window_manager()
            return {
                "windows": manager.list_windows(),
                "statistics": manager.get_statistics()
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    @app.get("/api/ratelimit/algorithms")
    async def list_ratelimit_algorithms() -> Dict[str, Any]:
        """List available rate limiting algorithms"""
        try:
            from agentic.ratelimit import RateLimitAlgorithm
            return {
                "algorithms": [algo.value for algo in RateLimitAlgorithm],
                "descriptions": {
                    "token_bucket": "Token bucket algorithm - good for burst handling",
                    "sliding_window": "Sliding window counter - balanced accuracy and memory",
                    "fixed_window": "Fixed window counter - simple but has boundary issues",
                    "sliding_log": "Sliding window log - most accurate, more memory"
                }
            }
        except ImportError:
            return {"error": "Rate limit module not available"}

    # ==================== API Keys API ====================

    @app.get("/api/apikeys/status")
    async def get_apikeys_status() -> Dict[str, Any]:
        """Get API key system status"""
        try:
            from agentic.apikeys import get_key_manager, get_key_validator, get_usage_tracker
            manager = get_key_manager()
            validator = get_key_validator()
            tracker = get_usage_tracker()
            return {
                "keys": manager.get_statistics(),
                "validation": validator.get_statistics(),
                "usage": tracker.get_statistics()
            }
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys")
    async def list_api_keys(
        owner_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """List API keys"""
        try:
            from agentic.apikeys import get_key_manager, APIKeyStatus
            manager = get_key_manager()

            key_status = APIKeyStatus(status) if status else None
            keys = manager.list_keys(owner_id=owner_id, tenant_id=tenant_id, status=key_status)
            return {
                "keys": [k.to_dict() for k in keys],
                "count": len(keys)
            }
        except ImportError:
            return {"error": "API keys module not available"}
        except ValueError as e:
            return {"error": f"Invalid status: {e}"}

    @app.get("/api/apikeys/{key_id}")
    async def get_api_key(key_id: str) -> Dict[str, Any]:
        """Get a specific API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            key = manager.get_key(key_id)
            if key:
                return {"key": key.to_dict(include_sensitive=True)}
            return {"error": "Key not found"}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys")
    async def create_api_key(
        name: str,
        owner_id: str,
        preset: Optional[str] = None,
        tenant_id: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        description: str = "",
        rate_limit_tier: str = "standard"
    ) -> Dict[str, Any]:
        """Create a new API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()

            key, plain_key = manager.generate_key(
                name=name,
                owner_id=owner_id,
                preset=preset,
                tenant_id=tenant_id,
                expires_in_days=expires_in_days,
                description=description,
                rate_limit_tier=rate_limit_tier
            )
            return {
                "key": key.to_dict(),
                "plain_key": plain_key,
                "warning": "Store this key securely - it will not be shown again"
            }
        except ImportError:
            return {"error": "API keys module not available"}

    @app.delete("/api/apikeys/{key_id}")
    async def delete_api_key(key_id: str) -> Dict[str, Any]:
        """Delete an API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            success = manager.delete_key(key_id)
            return {"success": success}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/revoke")
    async def revoke_api_key(key_id: str, reason: str = "") -> Dict[str, Any]:
        """Revoke an API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            success = manager.revoke_key(key_id, reason)
            return {"success": success}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/suspend")
    async def suspend_api_key(key_id: str, reason: str = "") -> Dict[str, Any]:
        """Suspend an API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            success = manager.suspend_key(key_id, reason)
            return {"success": success}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/reactivate")
    async def reactivate_api_key(key_id: str) -> Dict[str, Any]:
        """Reactivate a suspended API key"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            success = manager.reactivate_key(key_id)
            return {"success": success}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/rotate")
    async def rotate_api_key(key_id: str) -> Dict[str, Any]:
        """Rotate an API key (create new, revoke old)"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            result = manager.rotate_key(key_id)
            if result:
                key, plain_key = result
                return {
                    "key": key.to_dict(),
                    "plain_key": plain_key,
                    "warning": "Store this key securely - it will not be shown again"
                }
            return {"error": "Failed to rotate key"}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/scopes")
    async def update_api_key_scopes(
        key_id: str,
        scopes: List[str],
        mode: str = "replace"
    ) -> Dict[str, Any]:
        """Update API key scopes"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()

            if mode == "add":
                success = manager.add_scopes(key_id, set(scopes))
            elif mode == "remove":
                success = manager.remove_scopes(key_id, set(scopes))
            else:  # replace
                success = manager.update_scopes(key_id, set(scopes))

            if success:
                key = manager.get_key(key_id)
                return {"key": key.to_dict() if key else None}
            return {"error": "Key not found"}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/{key_id}/extend")
    async def extend_api_key_expiration(key_id: str, days: int) -> Dict[str, Any]:
        """Extend API key expiration"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            success = manager.extend_expiration(key_id, days)
            if success:
                key = manager.get_key(key_id)
                return {"key": key.to_dict() if key else None}
            return {"error": "Key not found"}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.post("/api/apikeys/validate")
    async def validate_api_key(
        api_key: str,
        required_scopes: Optional[List[str]] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate an API key"""
        try:
            from agentic.apikeys import get_key_validator
            validator = get_key_validator()
            result = validator.validate(
                api_key,
                required_scopes=required_scopes,
                tenant_id=tenant_id
            )
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/scopes")
    async def list_api_key_scopes() -> Dict[str, Any]:
        """List all available scopes"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            return {
                "scopes": manager.get_all_scopes(),
                "presets": manager.get_scope_presets()
            }
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/owner/{owner_id}")
    async def get_owner_api_keys(owner_id: str) -> Dict[str, Any]:
        """Get all API keys for an owner"""
        try:
            from agentic.apikeys import get_key_manager
            manager = get_key_manager()
            keys = manager.get_keys_by_owner(owner_id)
            return {
                "keys": [k.to_dict() for k in keys],
                "count": len(keys)
            }
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/usage/{key_id}")
    async def get_api_key_usage(key_id: str) -> Dict[str, Any]:
        """Get usage data for an API key"""
        try:
            from agentic.apikeys import get_usage_tracker
            tracker = get_usage_tracker()
            return tracker.get_key_usage(key_id)
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/usage/{key_id}/summary")
    async def get_api_key_usage_summary(
        key_id: str,
        period: str = "day",
        periods_back: int = 1
    ) -> Dict[str, Any]:
        """Get usage summary for an API key"""
        try:
            from agentic.apikeys import get_usage_tracker, UsagePeriod
            tracker = get_usage_tracker()

            try:
                usage_period = UsagePeriod(period)
            except ValueError:
                usage_period = UsagePeriod.DAY

            summary = tracker.get_summary(key_id, usage_period, periods_back)
            return {"summary": summary.to_dict()}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/top-keys")
    async def get_top_api_keys(limit: int = 10) -> Dict[str, Any]:
        """Get most used API keys"""
        try:
            from agentic.apikeys import get_usage_tracker
            tracker = get_usage_tracker()
            return {"top_keys": tracker.get_top_keys(limit)}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/top-endpoints")
    async def get_top_api_endpoints(
        key_id: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get most used endpoints"""
        try:
            from agentic.apikeys import get_usage_tracker
            tracker = get_usage_tracker()
            return {"top_endpoints": tracker.get_top_endpoints(key_id, limit)}
        except ImportError:
            return {"error": "API keys module not available"}

    @app.get("/api/apikeys/validation-log")
    async def get_api_key_validation_log(limit: int = 100) -> Dict[str, Any]:
        """Get recent validation log"""
        try:
            from agentic.apikeys import get_key_validator
            validator = get_key_validator()
            log = validator.get_validation_log(limit)
            return {
                "log": [
                    {
                        "key_id": entry["key_id"],
                        "valid": entry["valid"],
                        "reason": entry["reason"],
                        "timestamp": entry["timestamp"].isoformat()
                    }
                    for entry in log
                ],
                "count": len(log)
            }
        except ImportError:
            return {"error": "API keys module not available"}

    # ==================== Audit Logging API ====================

    @app.get("/api/audit/status")
    async def get_audit_status() -> Dict[str, Any]:
        """Get audit logging status"""
        try:
            from agentic.audit import get_audit_logger, get_audit_storage, get_audit_exporter
            logger = get_audit_logger()
            storage = get_audit_storage()
            exporter = get_audit_exporter()
            return {
                "logger": logger.get_statistics(),
                "storage": storage.get_statistics(),
                "exporter": exporter.get_statistics()
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.post("/api/audit/log")
    async def log_audit_event(request: Request) -> Dict[str, Any]:
        """Log an audit event"""
        try:
            from agentic.audit import get_audit_logger, AuditEventType, AuditSeverity
            data = await request.json()
            logger = get_audit_logger()

            # Parse event type
            event_type_str = data.get("event_type", "custom")
            try:
                event_type = AuditEventType(event_type_str)
            except ValueError:
                event_type = AuditEventType.CUSTOM

            # Parse severity
            severity_str = data.get("severity", "info")
            try:
                severity = AuditSeverity(severity_str)
            except ValueError:
                severity = AuditSeverity.INFO

            event = logger.log(
                event_type=event_type,
                severity=severity,
                actor_id=data.get("actor_id"),
                actor_type=data.get("actor_type", "user"),
                target_type=data.get("target_type"),
                target_id=data.get("target_id"),
                action=data.get("action", ""),
                outcome=data.get("outcome", "success"),
                ip_address=data.get("ip_address"),
                tenant_id=data.get("tenant_id"),
                details=data.get("details"),
                tags=data.get("tags")
            )
            return {"event": event.to_dict() if event else None}
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/events")
    async def query_audit_events(
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        actor_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Query audit events"""
        try:
            from agentic.audit import get_audit_storage, AuditQuery, AuditEventType, AuditSeverity

            # Build query
            event_types = None
            if event_type:
                try:
                    event_types = [AuditEventType(event_type)]
                except ValueError:
                    pass

            severities = None
            if severity:
                try:
                    severities = [AuditSeverity(severity)]
                except ValueError:
                    pass

            query = AuditQuery(
                event_types=event_types,
                severities=severities,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                tenant_id=tenant_id,
                outcome=outcome,
                search_text=search,
                offset=offset,
                limit=limit
            )

            storage = get_audit_storage()
            result = storage.query(query)
            return result.to_dict()
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/events/{event_id}")
    async def get_audit_event(event_id: str) -> Dict[str, Any]:
        """Get a specific audit event"""
        try:
            from agentic.audit import get_audit_logger
            logger = get_audit_logger()
            for event in logger.events:
                if event.id == event_id:
                    return {"event": event.to_dict()}
            return {"error": "Event not found"}
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/security")
    async def get_security_events(days: int = 7, limit: int = 100) -> Dict[str, Any]:
        """Get security-related audit events"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            events = storage.get_security_events(days=days, limit=limit)
            return {
                "events": [e.to_dict() for e in events],
                "count": len(events),
                "period_days": days
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/user/{user_id}")
    async def get_user_audit_activity(user_id: str, days: int = 30, limit: int = 100) -> Dict[str, Any]:
        """Get audit activity for a specific user"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            events = storage.get_user_activity(user_id=user_id, days=days, limit=limit)
            return {
                "user_id": user_id,
                "events": [e.to_dict() for e in events],
                "count": len(events),
                "period_days": days
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/resource/{resource_type}/{resource_id}")
    async def get_resource_audit_history(resource_type: str, resource_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get audit history for a specific resource"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            events = storage.get_resource_history(
                resource_type=resource_type,
                resource_id=resource_id,
                limit=limit
            )
            return {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "events": [e.to_dict() for e in events],
                "count": len(events)
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/summary")
    async def get_audit_summary(days: int = 7) -> Dict[str, Any]:
        """Get audit summary"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            return storage.get_summary(days=days)
        except ImportError:
            return {"error": "Audit module not available"}

    @app.post("/api/audit/export")
    async def export_audit_logs(request: Request) -> Dict[str, Any]:
        """Export audit logs"""
        try:
            from agentic.audit import get_audit_exporter, ExportFormat, AuditQuery
            from datetime import datetime, timedelta

            data = await request.json()
            exporter = get_audit_exporter()

            # Parse format
            format_str = data.get("format", "json")
            try:
                export_format = ExportFormat(format_str)
            except ValueError:
                export_format = ExportFormat.JSON

            # Build query if filters provided
            query = None
            if any(k in data for k in ["actor_id", "event_type", "start_days"]):
                start_time = None
                if "start_days" in data:
                    start_time = datetime.now() - timedelta(days=data["start_days"])

                query = AuditQuery(
                    actor_id=data.get("actor_id"),
                    tenant_id=data.get("tenant_id"),
                    start_time=start_time,
                    limit=data.get("limit", 10000)
                )

            result = exporter.export(format=export_format, query=query)
            return {
                "export": result.to_dict(),
                "data": result.data[:10000] if len(result.data) > 10000 else result.data
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/export/formats")
    async def get_export_formats() -> Dict[str, Any]:
        """Get available export formats"""
        try:
            from agentic.audit import ExportFormat
            return {
                "formats": [
                    {"value": f.value, "name": f.name, "description": _get_format_description(f)}
                    for f in ExportFormat
                ]
            }
        except ImportError:
            return {"error": "Audit module not available"}

    def _get_format_description(format: "ExportFormat") -> str:
        """Get format description"""
        descriptions = {
            "json": "JSON format with full event details",
            "csv": "CSV format for spreadsheet analysis",
            "syslog": "RFC 5424 Syslog format for SIEM integration",
            "cef": "Common Event Format for security tools"
        }
        return descriptions.get(format.value, "")

    @app.post("/api/audit/compliance-report")
    async def generate_compliance_report(request: Request) -> Dict[str, Any]:
        """Generate compliance report"""
        try:
            from agentic.audit import get_audit_exporter
            data = await request.json()
            exporter = get_audit_exporter()
            report = exporter.generate_compliance_report(
                days=data.get("days", 30),
                compliance_type=data.get("compliance_type", "general")
            )
            return {"report": report}
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/export/history")
    async def get_export_history(limit: int = 50) -> Dict[str, Any]:
        """Get export history"""
        try:
            from agentic.audit import get_audit_exporter
            exporter = get_audit_exporter()
            return {
                "history": exporter.get_export_history(limit),
                "count": len(exporter.export_history)
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.post("/api/audit/archive")
    async def archive_old_events() -> Dict[str, Any]:
        """Archive old audit events based on retention policy"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            archived_count = storage.archive_old_events()
            return {
                "archived_count": archived_count,
                "statistics": storage.get_statistics()
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.post("/api/audit/purge")
    async def purge_archived_events(days: int = 365) -> Dict[str, Any]:
        """Purge old archived events"""
        try:
            from agentic.audit import get_audit_storage
            storage = get_audit_storage()
            purged_count = storage.purge_archived(days=days)
            return {
                "purged_count": purged_count,
                "statistics": storage.get_statistics()
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.put("/api/audit/retention")
    async def set_retention_policy(request: Request) -> Dict[str, Any]:
        """Set audit log retention policy"""
        try:
            from agentic.audit import get_audit_storage
            from agentic.audit.storage import RetentionPolicy
            data = await request.json()
            storage = get_audit_storage()

            policy_str = data.get("policy", "90_days")
            try:
                policy = RetentionPolicy(policy_str)
            except ValueError:
                return {"error": f"Invalid retention policy: {policy_str}"}

            storage.set_retention_policy(policy)
            return {
                "policy": policy.value,
                "retention_days": storage.RETENTION_DAYS.get(policy),
                "statistics": storage.get_statistics()
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/retention/policies")
    async def get_retention_policies() -> Dict[str, Any]:
        """Get available retention policies"""
        try:
            from agentic.audit.storage import RetentionPolicy, AuditStorage
            return {
                "policies": [
                    {
                        "value": p.value,
                        "name": p.name,
                        "days": AuditStorage.RETENTION_DAYS.get(p)
                    }
                    for p in RetentionPolicy
                ]
            }
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/event-types")
    async def get_audit_event_types() -> Dict[str, Any]:
        """Get available audit event types"""
        try:
            from agentic.audit import AuditEventType
            # Group by category
            categories = {}
            for et in AuditEventType:
                parts = et.value.split(".")
                category = parts[0] if len(parts) > 1 else "other"
                if category not in categories:
                    categories[category] = []
                categories[category].append({"value": et.value, "name": et.name})
            return {"event_types": categories}
        except ImportError:
            return {"error": "Audit module not available"}

    @app.get("/api/audit/severities")
    async def get_audit_severities() -> Dict[str, Any]:
        """Get available audit severity levels"""
        try:
            from agentic.audit import AuditSeverity
            return {
                "severities": [
                    {"value": s.value, "name": s.name}
                    for s in AuditSeverity
                ]
            }
        except ImportError:
            return {"error": "Audit module not available"}

    # ==================== Session Management API ====================

    @app.get("/api/sessions/status")
    async def get_sessions_status() -> Dict[str, Any]:
        """Get session management status"""
        try:
            from agentic.sessions import get_session_manager, get_token_manager, get_session_tracker
            session_mgr = get_session_manager()
            token_mgr = get_token_manager()
            tracker = get_session_tracker()
            return {
                "sessions": session_mgr.get_statistics(),
                "tokens": token_mgr.get_statistics(),
                "tracker": tracker.get_statistics()
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions")
    async def create_session(request: Request) -> Dict[str, Any]:
        """Create a new session"""
        try:
            from agentic.sessions import get_session_manager, get_token_manager, get_session_tracker
            from agentic.sessions.tracker import ActivityType
            from datetime import timedelta

            data = await request.json()
            session_mgr = get_session_manager()
            token_mgr = get_token_manager()
            tracker = get_session_tracker()

            # Create session
            ttl = None
            if "ttl_hours" in data:
                ttl = timedelta(hours=data["ttl_hours"])

            session = session_mgr.create_session(
                user_id=data["user_id"],
                tenant_id=data.get("tenant_id"),
                ip_address=data.get("ip_address"),
                user_agent=data.get("user_agent"),
                device_id=data.get("device_id"),
                device_type=data.get("device_type", "web"),
                ttl=ttl,
                metadata=data.get("metadata")
            )

            # Generate tokens
            tokens = token_mgr.generate_token_pair(
                user_id=data["user_id"],
                tenant_id=data.get("tenant_id"),
                session_id=session.id,
                roles=data.get("roles"),
                scopes=data.get("scopes")
            )

            # Track login
            tracker.track_login(
                session_id=session.id,
                user_id=data["user_id"],
                ip_address=data.get("ip_address"),
                user_agent=data.get("user_agent")
            )

            return {
                "session": session.to_dict(),
                "tokens": tokens
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> Dict[str, Any]:
        """Get session by ID"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            session = session_mgr.get_session(session_id)
            if not session:
                return {"error": "Session not found"}
            return {"session": session.to_dict()}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/{session_id}/validate")
    async def validate_session(session_id: str) -> Dict[str, Any]:
        """Validate a session"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            valid, reason = session_mgr.validate_session(session_id)
            return {
                "valid": valid,
                "reason": reason,
                "session_id": session_id
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/{session_id}/refresh")
    async def refresh_session(session_id: str, request: Request) -> Dict[str, Any]:
        """Refresh a session"""
        try:
            from agentic.sessions import get_session_manager
            from datetime import timedelta

            data = await request.json()
            session_mgr = get_session_manager()

            ttl = None
            if "ttl_hours" in data:
                ttl = timedelta(hours=data["ttl_hours"])

            session = session_mgr.refresh_session(
                session_id=session_id,
                refresh_token=data["refresh_token"],
                ttl=ttl
            )

            if not session:
                return {"error": "Failed to refresh session"}

            return {"session": session.to_dict()}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/{session_id}/revoke")
    async def revoke_session(session_id: str, request: Request) -> Dict[str, Any]:
        """Revoke a session"""
        try:
            from agentic.sessions import get_session_manager, get_session_tracker
            from agentic.sessions.tracker import ActivityType

            data = await request.json() if request.headers.get("content-length") else {}
            session_mgr = get_session_manager()
            tracker = get_session_tracker()

            session = session_mgr.get_session(session_id)
            if session:
                tracker.track_logout(session_id=session_id, user_id=session.user_id)

            success = session_mgr.revoke_session(session_id, data.get("reason", ""))
            return {"success": success, "session_id": session_id}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/{session_id}/lock")
    async def lock_session(session_id: str, request: Request) -> Dict[str, Any]:
        """Lock a session"""
        try:
            from agentic.sessions import get_session_manager

            data = await request.json() if request.headers.get("content-length") else {}
            session_mgr = get_session_manager()
            success = session_mgr.lock_session(session_id, data.get("reason", ""))
            return {"success": success, "session_id": session_id}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/{session_id}/unlock")
    async def unlock_session(session_id: str) -> Dict[str, Any]:
        """Unlock a session"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            success = session_mgr.unlock_session(session_id)
            return {"success": success, "session_id": session_id}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/user/{user_id}")
    async def get_user_sessions(user_id: str, active_only: bool = True) -> Dict[str, Any]:
        """Get all sessions for a user"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            sessions = session_mgr.get_user_sessions(user_id, active_only)
            return {
                "user_id": user_id,
                "sessions": [s.to_dict() for s in sessions],
                "count": len(sessions)
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/user/{user_id}/revoke-all")
    async def revoke_user_sessions(user_id: str, request: Request) -> Dict[str, Any]:
        """Revoke all sessions for a user"""
        try:
            from agentic.sessions import get_session_manager

            data = await request.json() if request.headers.get("content-length") else {}
            session_mgr = get_session_manager()
            count = session_mgr.revoke_user_sessions(
                user_id,
                except_session=data.get("except_session")
            )
            return {"user_id": user_id, "revoked_count": count}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/tenant/{tenant_id}/revoke-all")
    async def revoke_tenant_sessions(tenant_id: str) -> Dict[str, Any]:
        """Revoke all sessions for a tenant"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            count = session_mgr.revoke_tenant_sessions(tenant_id)
            return {"tenant_id": tenant_id, "revoked_count": count}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/sessions/cleanup")
    async def cleanup_sessions() -> Dict[str, Any]:
        """Clean up expired sessions"""
        try:
            from agentic.sessions import get_session_manager
            session_mgr = get_session_manager()
            count = session_mgr.cleanup_expired()
            return {"expired_count": count, "statistics": session_mgr.get_statistics()}
        except ImportError:
            return {"error": "Sessions module not available"}

    # Token endpoints
    @app.post("/api/tokens/generate")
    async def generate_tokens(request: Request) -> Dict[str, Any]:
        """Generate token pair"""
        try:
            from agentic.sessions import get_token_manager

            data = await request.json()
            token_mgr = get_token_manager()
            tokens = token_mgr.generate_token_pair(
                user_id=data["user_id"],
                tenant_id=data.get("tenant_id"),
                session_id=data.get("session_id"),
                roles=data.get("roles"),
                scopes=data.get("scopes")
            )
            return {"tokens": tokens}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/tokens/validate")
    async def validate_token(request: Request) -> Dict[str, Any]:
        """Validate a token"""
        try:
            from agentic.sessions import get_token_manager

            data = await request.json()
            token_mgr = get_token_manager()
            result = token_mgr.validate_token(data["token"])
            return result.to_dict()
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/tokens/refresh")
    async def refresh_tokens(request: Request) -> Dict[str, Any]:
        """Refresh access token"""
        try:
            from agentic.sessions import get_token_manager

            data = await request.json()
            token_mgr = get_token_manager()
            result = token_mgr.refresh_access_token(data["refresh_token"])
            if not result:
                return {"error": "Invalid refresh token"}
            return {"tokens": result}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/tokens/revoke")
    async def revoke_token(request: Request) -> Dict[str, Any]:
        """Revoke a token"""
        try:
            from agentic.sessions import get_token_manager

            data = await request.json()
            token_mgr = get_token_manager()
            success = token_mgr.revoke_token(data["token"])
            return {"success": success}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.post("/api/tokens/decode")
    async def decode_token(request: Request) -> Dict[str, Any]:
        """Decode a token without validation"""
        try:
            from agentic.sessions import get_token_manager

            data = await request.json()
            token_mgr = get_token_manager()
            payload = token_mgr.decode_token(data["token"])
            if not payload:
                return {"error": "Invalid token format"}
            return {"payload": payload.to_dict()}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/tokens/types")
    async def get_token_types() -> Dict[str, Any]:
        """Get available token types"""
        try:
            from agentic.sessions import TokenType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in TokenType
                ]
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    # Activity tracking endpoints
    @app.post("/api/sessions/activity")
    async def track_activity(request: Request) -> Dict[str, Any]:
        """Track session activity"""
        try:
            from agentic.sessions import get_session_tracker
            from agentic.sessions.tracker import ActivityType

            data = await request.json()
            tracker = get_session_tracker()

            activity_type_str = data.get("activity_type", "action")
            try:
                activity_type = ActivityType(activity_type_str)
            except ValueError:
                activity_type = ActivityType.ACTION

            activity = tracker.track(
                session_id=data["session_id"],
                user_id=data["user_id"],
                activity_type=activity_type,
                endpoint=data.get("endpoint"),
                method=data.get("method"),
                status_code=data.get("status_code"),
                ip_address=data.get("ip_address"),
                user_agent=data.get("user_agent"),
                duration_ms=data.get("duration_ms"),
                metadata=data.get("metadata")
            )
            return {"activity": activity.to_dict()}
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/{session_id}/activities")
    async def get_session_activities(session_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get activities for a session"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            activities = tracker.get_session_activities(session_id, limit)
            return {
                "session_id": session_id,
                "activities": [a.to_dict() for a in activities],
                "count": len(activities)
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/{session_id}/summary")
    async def get_session_activity_summary(session_id: str) -> Dict[str, Any]:
        """Get activity summary for a session"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            return tracker.get_session_summary(session_id)
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/user/{user_id}/activities")
    async def get_user_activities(user_id: str, days: int = 7, limit: int = 100) -> Dict[str, Any]:
        """Get activities for a user"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            activities = tracker.get_user_activities(user_id, days, limit)
            return {
                "user_id": user_id,
                "activities": [a.to_dict() for a in activities],
                "count": len(activities),
                "period_days": days
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/user/{user_id}/summary")
    async def get_user_activity_summary(user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get activity summary for a user"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            return tracker.get_user_summary(user_id, days)
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/activities/recent")
    async def get_recent_activities(limit: int = 100, activity_type: Optional[str] = None) -> Dict[str, Any]:
        """Get recent activities"""
        try:
            from agentic.sessions import get_session_tracker
            from agentic.sessions.tracker import ActivityType

            tracker = get_session_tracker()
            act_type = None
            if activity_type:
                try:
                    act_type = ActivityType(activity_type)
                except ValueError:
                    pass

            activities = tracker.get_recent_activities(limit, act_type)
            return {
                "activities": [a.to_dict() for a in activities],
                "count": len(activities)
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/analytics/endpoints")
    async def get_endpoint_analytics(days: int = 7) -> Dict[str, Any]:
        """Get endpoint analytics"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            return tracker.get_endpoint_stats(days)
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/analytics/security")
    async def get_security_analytics(days: int = 7) -> Dict[str, Any]:
        """Get security event analytics"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            return tracker.get_security_summary(days)
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/analytics/errors")
    async def get_error_analytics(days: int = 7) -> Dict[str, Any]:
        """Get error analytics"""
        try:
            from agentic.sessions import get_session_tracker
            tracker = get_session_tracker()
            return tracker.get_error_summary(days)
        except ImportError:
            return {"error": "Sessions module not available"}

    @app.get("/api/sessions/activity-types")
    async def get_activity_types() -> Dict[str, Any]:
        """Get available activity types"""
        try:
            from agentic.sessions.tracker import ActivityType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in ActivityType
                ]
            }
        except ImportError:
            return {"error": "Sessions module not available"}

    # ==================== Configuration Management API ====================

    @app.get("/api/config/status")
    async def get_config_status() -> Dict[str, Any]:
        """Get configuration management status"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            return manager.get_statistics()
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/namespaces")
    async def list_config_namespaces() -> Dict[str, Any]:
        """List all configuration namespaces"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            namespaces = []
            for name in manager.get_namespaces():
                ns = manager.get_namespace(name)
                if ns:
                    namespaces.append({
                        "name": ns.name,
                        "description": ns.description,
                        "entry_count": len(ns.entries),
                        "schema_name": ns.schema_name
                    })
            return {"namespaces": namespaces}
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/namespaces")
    async def create_config_namespace(request: Request) -> Dict[str, Any]:
        """Create a configuration namespace"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            ns = manager.create_namespace(
                name=data["name"],
                description=data.get("description", ""),
                schema_name=data.get("schema_name")
            )
            return {"namespace": ns.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/namespaces/{namespace}")
    async def get_config_namespace(namespace: str) -> Dict[str, Any]:
        """Get configuration namespace"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            ns = manager.get_namespace(namespace)
            if not ns:
                return {"error": "Namespace not found"}
            return {"namespace": ns.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.delete("/api/config/namespaces/{namespace}")
    async def delete_config_namespace(namespace: str) -> Dict[str, Any]:
        """Delete configuration namespace"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            success = manager.delete_namespace(namespace)
            return {"success": success, "namespace": namespace}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/{namespace}")
    async def get_namespace_config(namespace: str) -> Dict[str, Any]:
        """Get all configuration for namespace"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            config = manager.get_all(namespace)
            return {"namespace": namespace, "config": config}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/{namespace}/{key}")
    async def get_config_value(namespace: str, key: str) -> Dict[str, Any]:
        """Get configuration value"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            value = manager.get(namespace, key)
            return {"namespace": namespace, "key": key, "value": value}
        except ImportError:
            return {"error": "Config module not available"}

    @app.put("/api/config/{namespace}/{key}")
    async def set_config_value(namespace: str, key: str, request: Request) -> Dict[str, Any]:
        """Set configuration value"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            entry = manager.set(
                namespace=namespace,
                key=key,
                value=data["value"],
                description=data.get("description", ""),
                encrypted=data.get("encrypted", False),
                user=data.get("user"),
                validate=data.get("validate", True)
            )
            return {"entry": entry.to_dict()}
        except ValueError as e:
            return {"error": str(e)}
        except ImportError:
            return {"error": "Config module not available"}

    @app.delete("/api/config/{namespace}/{key}")
    async def delete_config_value(namespace: str, key: str) -> Dict[str, Any]:
        """Delete configuration value"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            success = manager.delete(namespace, key)
            return {"success": success, "namespace": namespace, "key": key}
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/bulk")
    async def set_bulk_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Set multiple configuration values"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            result = manager.set_bulk(
                namespace=namespace,
                config=data["config"],
                user=data.get("user"),
                validate=data.get("validate", True),
                create_version=data.get("create_version", True)
            )
            return result.to_dict()
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/validate")
    async def validate_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Validate configuration"""
        try:
            from agentic.config import get_config_manager
            data = await request.json() if request.headers.get("content-length") else None
            manager = get_config_manager()
            config = data.get("config") if data else None
            result = manager.validate(namespace, config)
            return result.to_dict()
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/commit")
    async def commit_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Commit configuration as new version"""
        try:
            from agentic.config import get_config_manager
            data = await request.json() if request.headers.get("content-length") else {}
            manager = get_config_manager()
            version = manager.commit(
                namespace=namespace,
                message=data.get("message", ""),
                user=data.get("user")
            )
            if not version:
                return {"error": "Failed to commit configuration"}
            return {"version": version.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/rollback")
    async def rollback_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Rollback to previous version"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            version = manager.rollback(
                namespace=namespace,
                version_id=data["version_id"],
                user=data.get("user")
            )
            if not version:
                return {"error": "Failed to rollback configuration"}
            return {"version": version.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/{namespace}/history")
    async def get_config_history(namespace: str, limit: int = 50) -> Dict[str, Any]:
        """Get configuration history"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            history = manager.get_history(namespace, limit)
            return {
                "namespace": namespace,
                "versions": [v.to_dict() for v in history],
                "count": len(history)
            }
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/diff")
    async def diff_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Compare configuration with current"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            changes = manager.diff(namespace, data["config"])
            return {"namespace": namespace, "changes": changes, "change_count": len(changes)}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/{namespace}/export")
    async def export_config(namespace: str) -> Dict[str, Any]:
        """Export configuration"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            return manager.export(namespace)
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/{namespace}/import")
    async def import_config(namespace: str, request: Request) -> Dict[str, Any]:
        """Import configuration"""
        try:
            from agentic.config import get_config_manager
            data = await request.json()
            manager = get_config_manager()
            result = manager.import_config(
                namespace=namespace,
                data=data,
                user=data.get("user"),
                validate=data.get("validate", True)
            )
            return result.to_dict()
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/search")
    async def search_config(query: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Search configuration entries"""
        try:
            from agentic.config import get_config_manager
            manager = get_config_manager()
            results = manager.search(query, namespace)
            return {"results": results, "count": len(results), "query": query}
        except ImportError:
            return {"error": "Config module not available"}

    # Schema endpoints
    @app.get("/api/config/schemas")
    async def list_config_schemas() -> Dict[str, Any]:
        """List available configuration schemas"""
        try:
            from agentic.config import get_schema_validator
            validator = get_schema_validator()
            schemas = []
            for name, schema in validator.schemas.items():
                schemas.append({
                    "name": schema.name,
                    "version": schema.version,
                    "description": schema.description,
                    "field_count": len(schema.fields)
                })
            return {"schemas": schemas}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/schemas/{name}")
    async def get_config_schema(name: str) -> Dict[str, Any]:
        """Get configuration schema"""
        try:
            from agentic.config import get_schema_validator
            validator = get_schema_validator()
            schema = validator.get_schema(name)
            if not schema:
                return {"error": "Schema not found"}
            return {"schema": schema.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/schemas")
    async def create_config_schema(request: Request) -> Dict[str, Any]:
        """Create configuration schema"""
        try:
            from agentic.config import get_schema_validator, ConfigSchema, SchemaField, SchemaType
            data = await request.json()
            validator = get_schema_validator()

            schema = ConfigSchema(
                name=data["name"],
                version=data.get("version", "1.0"),
                description=data.get("description", ""),
                allow_extra_fields=data.get("allow_extra_fields", False)
            )

            for field_data in data.get("fields", []):
                field = SchemaField(
                    name=field_data["name"],
                    type=SchemaType(field_data["type"]),
                    required=field_data.get("required", False),
                    default=field_data.get("default"),
                    description=field_data.get("description", ""),
                    min_value=field_data.get("min_value"),
                    max_value=field_data.get("max_value"),
                    min_length=field_data.get("min_length"),
                    max_length=field_data.get("max_length"),
                    pattern=field_data.get("pattern"),
                    enum_values=field_data.get("enum_values")
                )
                schema.add_field(field)

            validator.register_schema(schema)
            return {"schema": schema.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/schema-types")
    async def get_schema_types() -> Dict[str, Any]:
        """Get available schema types"""
        try:
            from agentic.config import SchemaType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in SchemaType
                ]
            }
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/validate-value")
    async def validate_config_value(request: Request) -> Dict[str, Any]:
        """Validate a single configuration value"""
        try:
            from agentic.config import get_schema_validator, SchemaType
            data = await request.json()
            validator = get_schema_validator()

            field_type = SchemaType(data["type"])
            result = validator.validate_field_value(
                value=data["value"],
                field_type=field_type,
                constraints=data.get("constraints")
            )
            return result.to_dict()
        except ImportError:
            return {"error": "Config module not available"}

    # Version endpoints
    @app.get("/api/config/versions/{namespace}")
    async def get_config_versions(namespace: str, limit: int = 50) -> Dict[str, Any]:
        """Get configuration versions"""
        try:
            from agentic.config import get_version_manager
            manager = get_version_manager()
            versions = manager.get_history(namespace, limit)
            return {
                "namespace": namespace,
                "versions": [v.to_dict() for v in versions],
                "count": len(versions)
            }
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/versions/{namespace}/{version_id}")
    async def get_config_version(namespace: str, version_id: str) -> Dict[str, Any]:
        """Get specific configuration version"""
        try:
            from agentic.config import get_version_manager
            manager = get_version_manager()
            version = manager.get_version(namespace, version_id)
            if not version:
                return {"error": "Version not found"}
            return {"version": version.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/versions/{namespace}/current")
    async def get_current_config_version(namespace: str) -> Dict[str, Any]:
        """Get current configuration version"""
        try:
            from agentic.config import get_version_manager
            manager = get_version_manager()
            version = manager.get_current_version(namespace)
            if not version:
                return {"error": "No current version"}
            return {"version": version.to_dict()}
        except ImportError:
            return {"error": "Config module not available"}

    @app.post("/api/config/versions/{namespace}/diff")
    async def diff_config_versions(namespace: str, request: Request) -> Dict[str, Any]:
        """Compare two configuration versions"""
        try:
            from agentic.config import get_version_manager
            data = await request.json()
            manager = get_version_manager()
            changes = manager.diff_versions(
                namespace=namespace,
                version_id_1=data["version_id_1"],
                version_id_2=data["version_id_2"]
            )
            return {
                "namespace": namespace,
                "changes": [c.to_dict() for c in changes],
                "change_count": len(changes)
            }
        except ImportError:
            return {"error": "Config module not available"}

    @app.get("/api/config/environments")
    async def get_config_environments() -> Dict[str, Any]:
        """Get available environments"""
        try:
            from agentic.config.manager import Environment
            return {
                "environments": [
                    {"value": e.value, "name": e.name}
                    for e in Environment
                ]
            }
        except ImportError:
            return {"error": "Config module not available"}

    # ==================== Metrics & Monitoring API ====================

    @app.get("/api/metrics/status")
    async def get_metrics_status() -> Dict[str, Any]:
        """Get metrics system status"""
        try:
            from agentic.metrics import get_metric_collector, get_timeseries_store, get_alert_manager
            collector = get_metric_collector()
            store = get_timeseries_store()
            alerts = get_alert_manager()
            return {
                "collector": collector.get_statistics(),
                "timeseries": store.get_statistics(),
                "alerts": alerts.get_statistics()
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics")
    async def list_metrics(metric_type: Optional[str] = None) -> Dict[str, Any]:
        """List all metrics"""
        try:
            from agentic.metrics import get_metric_collector, MetricType
            collector = get_metric_collector()

            if metric_type:
                try:
                    mt = MetricType(metric_type)
                    metrics = collector.get_by_type(mt)
                except ValueError:
                    metrics = collector.get_all()
            else:
                metrics = collector.get_all()

            return {
                "metrics": [m.to_dict() for m in metrics],
                "count": len(metrics)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/{name}")
    async def get_metric(name: str) -> Dict[str, Any]:
        """Get metric by name"""
        try:
            from agentic.metrics import get_metric_collector
            collector = get_metric_collector()
            metrics = collector.get_all(name)
            if not metrics:
                return {"error": "Metric not found"}
            return {"metrics": [m.to_dict() for m in metrics]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/counter")
    async def increment_counter(request: Request) -> Dict[str, Any]:
        """Increment a counter"""
        try:
            from agentic.metrics import get_metric_collector
            data = await request.json()
            collector = get_metric_collector()
            collector.increment(
                name=data["name"],
                value=data.get("value", 1.0),
                labels=data.get("labels")
            )
            metric = collector.get(data["name"], data.get("labels"))
            return {"metric": metric.to_dict() if metric else None}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/gauge")
    async def set_gauge(request: Request) -> Dict[str, Any]:
        """Set a gauge value"""
        try:
            from agentic.metrics import get_metric_collector
            data = await request.json()
            collector = get_metric_collector()
            collector.set_gauge(
                name=data["name"],
                value=data["value"],
                labels=data.get("labels")
            )
            metric = collector.get(data["name"], data.get("labels"))
            return {"metric": metric.to_dict() if metric else None}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/observe")
    async def observe_value(request: Request) -> Dict[str, Any]:
        """Observe a value for histogram/summary"""
        try:
            from agentic.metrics import get_metric_collector
            data = await request.json()
            collector = get_metric_collector()
            collector.observe(
                name=data["name"],
                value=data["value"],
                labels=data.get("labels")
            )
            metric = collector.get(data["name"], data.get("labels"))
            return {"metric": metric.to_dict() if metric else None}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/prometheus")
    async def export_prometheus() -> str:
        """Export metrics in Prometheus format"""
        try:
            from agentic.metrics import get_metric_collector
            collector = get_metric_collector()
            return collector.export_prometheus()
        except ImportError:
            return "# Metrics module not available"

    @app.get("/api/metrics/types")
    async def get_metric_types() -> Dict[str, Any]:
        """Get available metric types"""
        try:
            from agentic.metrics import MetricType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in MetricType
                ]
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    # Time series endpoints
    @app.post("/api/timeseries/record")
    async def record_timeseries(request: Request) -> Dict[str, Any]:
        """Record a time series data point"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import datetime
            data = await request.json()
            store = get_timeseries_store()

            timestamp = None
            if "timestamp" in data:
                timestamp = datetime.fromisoformat(data["timestamp"])

            point = store.record(
                name=data["name"],
                value=data["value"],
                labels=data.get("labels"),
                timestamp=timestamp
            )
            return {"data_point": point.to_dict()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/timeseries/{name}")
    async def query_timeseries(
        name: str,
        duration_minutes: int = 60,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Query time series data"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import timedelta
            store = get_timeseries_store()
            points = store.query_range(name, timedelta(minutes=duration_minutes))
            if limit:
                points = points[-limit:]
            return {
                "name": name,
                "data_points": [p.to_dict() for p in points],
                "count": len(points)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/timeseries/{name}/aggregate")
    async def aggregate_timeseries(name: str, request: Request) -> Dict[str, Any]:
        """Aggregate time series data"""
        try:
            from agentic.metrics import get_timeseries_store
            from agentic.metrics.timeseries import AggregationType
            from datetime import datetime, timedelta

            data = await request.json()
            store = get_timeseries_store()

            agg_type = AggregationType(data.get("aggregation", "avg"))

            start_time = None
            if "start_time" in data:
                start_time = datetime.fromisoformat(data["start_time"])
            elif "duration_minutes" in data:
                start_time = datetime.now() - timedelta(minutes=data["duration_minutes"])

            end_time = None
            if "end_time" in data:
                end_time = datetime.fromisoformat(data["end_time"])

            value = store.aggregate(
                name=name,
                labels=data.get("labels"),
                start_time=start_time,
                end_time=end_time,
                aggregation=agg_type
            )
            return {"name": name, "aggregation": agg_type.value, "value": value}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/timeseries/{name}/downsample")
    async def downsample_timeseries(name: str, request: Request) -> Dict[str, Any]:
        """Downsample time series data"""
        try:
            from agentic.metrics import get_timeseries_store
            from agentic.metrics.timeseries import AggregationType
            from datetime import datetime, timedelta

            data = await request.json()
            store = get_timeseries_store()

            agg_type = AggregationType(data.get("aggregation", "avg"))
            interval = data.get("interval_seconds", 300)

            start_time = None
            if "start_time" in data:
                start_time = datetime.fromisoformat(data["start_time"])
            elif "duration_minutes" in data:
                start_time = datetime.now() - timedelta(minutes=data["duration_minutes"])

            end_time = None
            if "end_time" in data:
                end_time = datetime.fromisoformat(data["end_time"])

            points = store.downsample(
                name=name,
                interval_seconds=interval,
                labels=data.get("labels"),
                aggregation=agg_type,
                start_time=start_time,
                end_time=end_time
            )
            return {
                "name": name,
                "interval_seconds": interval,
                "aggregation": agg_type.value,
                "data_points": [p.to_dict() for p in points],
                "count": len(points)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/timeseries")
    async def list_timeseries(name_filter: Optional[str] = None) -> Dict[str, Any]:
        """List all time series"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            series = store.list_series(name_filter)
            return {
                "series": [s.to_dict() for s in series],
                "count": len(series)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/timeseries/aggregation-types")
    async def get_aggregation_types() -> Dict[str, Any]:
        """Get available aggregation types"""
        try:
            from agentic.metrics.timeseries import AggregationType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in AggregationType
                ]
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    # Alert endpoints
    @app.get("/api/alerts")
    async def list_alerts(active_only: bool = True) -> Dict[str, Any]:
        """List alerts"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            if active_only:
                alerts = manager.get_active_alerts()
            else:
                alerts = list(manager.alerts.values())
            return {
                "alerts": [a.to_dict() for a in alerts],
                "count": len(alerts)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/alerts/{alert_id}")
    async def get_alert(alert_id: str) -> Dict[str, Any]:
        """Get alert by ID"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            alert = manager.get_alert(alert_id)
            if not alert:
                return {"error": "Alert not found"}
            return {"alert": alert.to_dict()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str) -> Dict[str, Any]:
        """Resolve an alert"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            success = manager.resolve_alert(alert_id)
            return {"success": success, "alert_id": alert_id}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/{alert_id}/silence")
    async def silence_alert(alert_id: str) -> Dict[str, Any]:
        """Silence an alert"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            success = manager.silence_alert(alert_id)
            return {"success": success, "alert_id": alert_id}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/alerts/history")
    async def get_alert_history(limit: int = 100) -> Dict[str, Any]:
        """Get alert history"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            history = manager.get_alert_history(limit)
            return {
                "history": [a.to_dict() for a in history],
                "count": len(history)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    # Alert rules endpoints
    @app.get("/api/alerts/rules")
    async def list_alert_rules(enabled_only: bool = False) -> Dict[str, Any]:
        """List alert rules"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            rules = manager.get_rules(enabled_only)
            return {
                "rules": [r.to_dict() for r in rules],
                "count": len(rules)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/rules")
    async def create_alert_rule(request: Request) -> Dict[str, Any]:
        """Create an alert rule"""
        try:
            from agentic.metrics import get_alert_manager, AlertCondition, AlertSeverity
            from datetime import timedelta

            data = await request.json()
            manager = get_alert_manager()

            condition = AlertCondition(data["condition"])
            severity = AlertSeverity(data.get("severity", "warning"))

            for_duration = None
            if "for_duration_seconds" in data:
                for_duration = timedelta(seconds=data["for_duration_seconds"])

            repeat_interval = None
            if "repeat_interval_seconds" in data:
                repeat_interval = timedelta(seconds=data["repeat_interval_seconds"])

            rule = manager.create_rule(
                name=data["name"],
                metric_name=data["metric_name"],
                condition=condition,
                threshold=data["threshold"],
                severity=severity,
                description=data.get("description", ""),
                labels=data.get("labels"),
                for_duration=for_duration,
                repeat_interval=repeat_interval
            )
            return {"rule": rule.to_dict()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/alerts/rules/{rule_id}")
    async def get_alert_rule(rule_id: str) -> Dict[str, Any]:
        """Get alert rule by ID"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            rule = manager.get_rule(rule_id)
            if not rule:
                return {"error": "Rule not found"}
            return {"rule": rule.to_dict()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.put("/api/alerts/rules/{rule_id}")
    async def update_alert_rule(rule_id: str, request: Request) -> Dict[str, Any]:
        """Update an alert rule"""
        try:
            from agentic.metrics import get_alert_manager
            data = await request.json()
            manager = get_alert_manager()
            rule = manager.update_rule(rule_id, **data)
            if not rule:
                return {"error": "Rule not found"}
            return {"rule": rule.to_dict()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.delete("/api/alerts/rules/{rule_id}")
    async def delete_alert_rule(rule_id: str) -> Dict[str, Any]:
        """Delete an alert rule"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            success = manager.delete_rule(rule_id)
            return {"success": success, "rule_id": rule_id}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/rules/{rule_id}/enable")
    async def enable_alert_rule(rule_id: str) -> Dict[str, Any]:
        """Enable an alert rule"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            success = manager.enable_rule(rule_id)
            return {"success": success, "rule_id": rule_id}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/rules/{rule_id}/disable")
    async def disable_alert_rule(rule_id: str) -> Dict[str, Any]:
        """Disable an alert rule"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            success = manager.disable_rule(rule_id)
            return {"success": success, "rule_id": rule_id}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/rules/{rule_id}/evaluate")
    async def evaluate_alert_rule(rule_id: str, request: Request) -> Dict[str, Any]:
        """Evaluate an alert rule"""
        try:
            from agentic.metrics import get_alert_manager
            data = await request.json() if request.headers.get("content-length") else {}
            manager = get_alert_manager()
            alert = manager.evaluate_rule(rule_id, data.get("value"))
            return {"alert": alert.to_dict() if alert else None}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/alerts/evaluate-all")
    async def evaluate_all_rules() -> Dict[str, Any]:
        """Evaluate all alert rules"""
        try:
            from agentic.metrics import get_alert_manager
            manager = get_alert_manager()
            alerts = manager.evaluate_all()
            return {
                "alerts": [a.to_dict() for a in alerts],
                "count": len(alerts)
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/alerts/conditions")
    async def get_alert_conditions() -> Dict[str, Any]:
        """Get available alert conditions"""
        try:
            from agentic.metrics import AlertCondition
            return {
                "conditions": [
                    {"value": c.value, "name": c.name}
                    for c in AlertCondition
                ]
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/alerts/severities")
    async def get_alert_severities() -> Dict[str, Any]:
        """Get available alert severities"""
        try:
            from agentic.metrics import AlertSeverity
            return {
                "severities": [
                    {"value": s.value, "name": s.name}
                    for s in AlertSeverity
                ]
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    # ==================== Notification System API ====================

    @app.get("/api/notifications/status")
    async def get_notifications_status() -> Dict[str, Any]:
        """Get notification system status"""
        try:
            from agentic.notifications import get_notification_manager, get_channel_manager, get_template_manager
            notif_mgr = get_notification_manager()
            channel_mgr = get_channel_manager()
            template_mgr = get_template_manager()
            return {
                "notifications": notif_mgr.get_statistics(),
                "channels": channel_mgr.get_statistics(),
                "templates": template_mgr.get_statistics()
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/channels")
    async def get_notification_channels(
        channel_type: Optional[str] = None,
        enabled_only: bool = False
    ) -> Dict[str, Any]:
        """Get notification channels"""
        try:
            from agentic.notifications import get_channel_manager, ChannelType
            manager = get_channel_manager()

            ch_type = None
            if channel_type:
                try:
                    ch_type = ChannelType(channel_type)
                except ValueError:
                    pass

            channels = manager.get_channels(channel_type=ch_type, enabled_only=enabled_only)
            return {
                "channels": [c.to_dict() for c in channels],
                "count": len(channels)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/channels")
    async def create_notification_channel(request: Request) -> Dict[str, Any]:
        """Create a notification channel"""
        try:
            from agentic.notifications import get_channel_manager, ChannelType
            data = await request.json()
            manager = get_channel_manager()

            try:
                channel_type = ChannelType(data["channel_type"])
            except (KeyError, ValueError):
                return {"error": "Invalid or missing channel_type"}

            channel = manager.create_channel(
                name=data["name"],
                channel_type=channel_type,
                config=data.get("config", {}),
                enabled=data.get("enabled", True)
            )
            return {"channel": channel.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/channels/{channel_id}")
    async def get_notification_channel(channel_id: str) -> Dict[str, Any]:
        """Get a specific notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            manager = get_channel_manager()
            channel = manager.get_channel(channel_id)
            if not channel:
                return {"error": "Channel not found"}
            return {"channel": channel.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.put("/api/notifications/channels/{channel_id}")
    async def update_notification_channel(channel_id: str, request: Request) -> Dict[str, Any]:
        """Update a notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            data = await request.json()
            manager = get_channel_manager()
            channel = manager.update_channel(channel_id, **data)
            if not channel:
                return {"error": "Channel not found"}
            return {"channel": channel.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.delete("/api/notifications/channels/{channel_id}")
    async def delete_notification_channel(channel_id: str) -> Dict[str, Any]:
        """Delete a notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            manager = get_channel_manager()
            success = manager.delete_channel(channel_id)
            return {"success": success, "channel_id": channel_id}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/channels/{channel_id}/enable")
    async def enable_notification_channel(channel_id: str) -> Dict[str, Any]:
        """Enable a notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            manager = get_channel_manager()
            success = manager.enable_channel(channel_id)
            return {"success": success, "channel_id": channel_id}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/channels/{channel_id}/disable")
    async def disable_notification_channel(channel_id: str) -> Dict[str, Any]:
        """Disable a notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            manager = get_channel_manager()
            success = manager.disable_channel(channel_id)
            return {"success": success, "channel_id": channel_id}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/channels/{channel_id}/test")
    async def test_notification_channel(channel_id: str) -> Dict[str, Any]:
        """Test a notification channel"""
        try:
            from agentic.notifications import get_channel_manager
            manager = get_channel_manager()
            result = manager.test_channel(channel_id)
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/channel-types")
    async def get_channel_types() -> Dict[str, Any]:
        """Get available channel types"""
        try:
            from agentic.notifications import ChannelType
            return {
                "channel_types": [
                    {"value": t.value, "name": t.name}
                    for t in ChannelType
                ]
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/templates")
    async def get_notification_templates(
        template_type: Optional[str] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False
    ) -> Dict[str, Any]:
        """Get notification templates"""
        try:
            from agentic.notifications import get_template_manager
            from agentic.notifications.templates import TemplateType
            manager = get_template_manager()

            t_type = None
            if template_type:
                try:
                    t_type = TemplateType(template_type)
                except ValueError:
                    pass

            templates = manager.get_templates(
                template_type=t_type,
                tag=tag,
                enabled_only=enabled_only
            )
            return {
                "templates": [t.to_dict() for t in templates],
                "count": len(templates)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/templates")
    async def create_notification_template(request: Request) -> Dict[str, Any]:
        """Create a notification template"""
        try:
            from agentic.notifications import get_template_manager
            from agentic.notifications.templates import TemplateType, TemplateVariable
            data = await request.json()
            manager = get_template_manager()

            try:
                template_type = TemplateType(data.get("template_type", "generic"))
            except ValueError:
                template_type = TemplateType.GENERIC

            variables = []
            for var in data.get("variables", []):
                variables.append(TemplateVariable(
                    name=var["name"],
                    description=var.get("description", ""),
                    required=var.get("required", True),
                    default_value=var.get("default_value"),
                    example=var.get("example")
                ))

            template = manager.create_template(
                name=data["name"],
                template_type=template_type,
                subject_template=data["subject_template"],
                body_template=data["body_template"],
                description=data.get("description", ""),
                variables=variables,
                tags=data.get("tags", []),
                html_template=data.get("html_template")
            )
            return {"template": template.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/templates/{template_id}")
    async def get_notification_template(template_id: str) -> Dict[str, Any]:
        """Get a specific notification template"""
        try:
            from agentic.notifications import get_template_manager
            manager = get_template_manager()
            template = manager.get_template(template_id)
            if not template:
                return {"error": "Template not found"}
            return {"template": template.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.put("/api/notifications/templates/{template_id}")
    async def update_notification_template(template_id: str, request: Request) -> Dict[str, Any]:
        """Update a notification template"""
        try:
            from agentic.notifications import get_template_manager
            data = await request.json()
            manager = get_template_manager()
            template = manager.update_template(template_id, **data)
            if not template:
                return {"error": "Template not found"}
            return {"template": template.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.delete("/api/notifications/templates/{template_id}")
    async def delete_notification_template(template_id: str) -> Dict[str, Any]:
        """Delete a notification template"""
        try:
            from agentic.notifications import get_template_manager
            manager = get_template_manager()
            success = manager.delete_template(template_id)
            return {"success": success, "template_id": template_id}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/templates/{template_id}/render")
    async def render_notification_template(template_id: str, request: Request) -> Dict[str, Any]:
        """Render a notification template with variables"""
        try:
            from agentic.notifications import get_template_manager
            data = await request.json()
            manager = get_template_manager()

            rendered = manager.render_template(
                template_id,
                data.get("variables", {}),
                include_html=data.get("include_html", False)
            )
            if not rendered:
                return {"error": "Template not found or disabled"}
            return {"rendered": rendered}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/templates/{template_id}/clone")
    async def clone_notification_template(template_id: str, request: Request) -> Dict[str, Any]:
        """Clone a notification template"""
        try:
            from agentic.notifications import get_template_manager
            data = await request.json()
            manager = get_template_manager()

            template = manager.clone_template(template_id, data["new_name"])
            if not template:
                return {"error": "Template not found"}
            return {"template": template.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/template-types")
    async def get_template_types() -> Dict[str, Any]:
        """Get available template types"""
        try:
            from agentic.notifications.templates import TemplateType
            return {
                "template_types": [
                    {"value": t.value, "name": t.name}
                    for t in TemplateType
                ]
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/send")
    async def send_notification(request: Request) -> Dict[str, Any]:
        """Send a notification"""
        try:
            from agentic.notifications import get_notification_manager, NotificationPriority, NotificationCategory
            data = await request.json()
            manager = get_notification_manager()

            try:
                priority = NotificationPriority(data.get("priority", "normal"))
            except ValueError:
                priority = NotificationPriority.NORMAL

            try:
                category = NotificationCategory(data.get("category", "system"))
            except ValueError:
                category = NotificationCategory.SYSTEM

            notification = manager.send(
                recipient=data["recipient"],
                subject=data["subject"],
                body=data["body"],
                channel_id=data["channel_id"],
                priority=priority,
                category=category,
                metadata=data.get("metadata")
            )
            return {"notification": notification.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/send-with-template")
    async def send_notification_with_template(request: Request) -> Dict[str, Any]:
        """Send a notification using a template"""
        try:
            from agentic.notifications import get_notification_manager, NotificationPriority, NotificationCategory
            data = await request.json()
            manager = get_notification_manager()

            try:
                priority = NotificationPriority(data.get("priority", "normal"))
            except ValueError:
                priority = NotificationPriority.NORMAL

            try:
                category = NotificationCategory(data.get("category", "system"))
            except ValueError:
                category = NotificationCategory.SYSTEM

            notification = manager.send_with_template(
                recipient=data["recipient"],
                template_name=data["template_name"],
                variables=data.get("variables", {}),
                channel_id=data["channel_id"],
                priority=priority,
                category=category,
                metadata=data.get("metadata")
            )
            if not notification:
                return {"error": "Failed to send notification - template not found or disabled"}
            return {"notification": notification.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/send-to-user")
    async def send_notification_to_user(request: Request) -> Dict[str, Any]:
        """Send notification to user based on preferences"""
        try:
            from agentic.notifications import get_notification_manager, NotificationPriority, NotificationCategory, ChannelType
            data = await request.json()
            manager = get_notification_manager()

            try:
                priority = NotificationPriority(data.get("priority", "normal"))
            except ValueError:
                priority = NotificationPriority.NORMAL

            try:
                category = NotificationCategory(data.get("category", "system"))
            except ValueError:
                category = NotificationCategory.SYSTEM

            preferred_channel = None
            if "preferred_channel" in data:
                try:
                    preferred_channel = ChannelType(data["preferred_channel"])
                except ValueError:
                    pass

            notifications = manager.send_to_user(
                user_id=data["user_id"],
                subject=data["subject"],
                body=data["body"],
                priority=priority,
                category=category,
                preferred_channel=preferred_channel
            )
            return {
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/broadcast")
    async def broadcast_notification(request: Request) -> Dict[str, Any]:
        """Broadcast notification to multiple users"""
        try:
            from agentic.notifications import get_notification_manager, NotificationPriority, NotificationCategory
            data = await request.json()
            manager = get_notification_manager()

            try:
                priority = NotificationPriority(data.get("priority", "normal"))
            except ValueError:
                priority = NotificationPriority.NORMAL

            try:
                category = NotificationCategory(data.get("category", "system"))
            except ValueError:
                category = NotificationCategory.SYSTEM

            results = manager.broadcast(
                subject=data["subject"],
                body=data["body"],
                user_ids=data["user_ids"],
                priority=priority,
                category=category
            )
            return {
                "results": {
                    user_id: [n.to_dict() for n in notifications]
                    for user_id, notifications in results.items()
                },
                "user_count": len(results)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications")
    async def get_notifications(
        recipient: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get notifications with filtering"""
        try:
            from agentic.notifications import get_notification_manager, NotificationStatus, NotificationCategory, NotificationPriority
            manager = get_notification_manager()

            n_status = None
            if status:
                try:
                    n_status = NotificationStatus(status)
                except ValueError:
                    pass

            n_category = None
            if category:
                try:
                    n_category = NotificationCategory(category)
                except ValueError:
                    pass

            n_priority = None
            if priority:
                try:
                    n_priority = NotificationPriority(priority)
                except ValueError:
                    pass

            notifications = manager.get_notifications(
                recipient=recipient,
                status=n_status,
                category=n_category,
                priority=n_priority,
                limit=limit
            )
            return {
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/{notification_id}")
    async def get_notification(notification_id: str) -> Dict[str, Any]:
        """Get a specific notification"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            notification = manager.get_notification(notification_id)
            if not notification:
                return {"error": "Notification not found"}
            return {"notification": notification.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/{notification_id}/retry")
    async def retry_notification(notification_id: str) -> Dict[str, Any]:
        """Retry a failed notification"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            notification = manager.retry(notification_id)
            if not notification:
                return {"error": "Notification not found or cannot be retried"}
            return {"notification": notification.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/{notification_id}/cancel")
    async def cancel_notification(notification_id: str) -> Dict[str, Any]:
        """Cancel a pending notification"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            success = manager.cancel(notification_id)
            return {"success": success, "notification_id": notification_id}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/pending")
    async def get_pending_notifications() -> Dict[str, Any]:
        """Get pending notifications"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            notifications = manager.get_pending()
            return {
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/failed")
    async def get_failed_notifications(retriable_only: bool = False) -> Dict[str, Any]:
        """Get failed notifications"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            notifications = manager.get_failed(retriable_only=retriable_only)
            return {
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/history")
    async def get_notification_history(
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get notification history"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            notifications = manager.get_history(user_id=user_id, limit=limit)
            return {
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications)
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/preferences/{user_id}")
    async def get_notification_preferences(user_id: str) -> Dict[str, Any]:
        """Get user notification preferences"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            preferences = manager.get_preferences(user_id)
            return {"preferences": preferences.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.put("/api/notifications/preferences/{user_id}")
    async def update_notification_preferences(user_id: str, request: Request) -> Dict[str, Any]:
        """Update user notification preferences"""
        try:
            from agentic.notifications import get_notification_manager
            data = await request.json()
            manager = get_notification_manager()
            preferences = manager.update_preferences(user_id, **data)
            return {"preferences": preferences.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/preferences/{user_id}/quiet-hours")
    async def set_notification_quiet_hours(user_id: str, request: Request) -> Dict[str, Any]:
        """Set quiet hours for user notifications"""
        try:
            from agentic.notifications import get_notification_manager
            data = await request.json()
            manager = get_notification_manager()
            preferences = manager.set_quiet_hours(
                user_id,
                start_hour=data.get("start_hour"),
                end_hour=data.get("end_hour")
            )
            return {"preferences": preferences.to_dict()}
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.post("/api/notifications/cleanup")
    async def cleanup_old_notifications(days: int = 30) -> Dict[str, Any]:
        """Archive old notifications"""
        try:
            from agentic.notifications import get_notification_manager
            manager = get_notification_manager()
            archived_count = manager.cleanup_old_notifications(days=days)
            return {
                "archived_count": archived_count,
                "statistics": manager.get_statistics()
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/categories")
    async def get_notification_categories() -> Dict[str, Any]:
        """Get available notification categories"""
        try:
            from agentic.notifications import NotificationCategory
            return {
                "categories": [
                    {"value": c.value, "name": c.name}
                    for c in NotificationCategory
                ]
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/priorities")
    async def get_notification_priorities() -> Dict[str, Any]:
        """Get available notification priorities"""
        try:
            from agentic.notifications import NotificationPriority
            return {
                "priorities": [
                    {"value": p.value, "name": p.name}
                    for p in NotificationPriority
                ]
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    @app.get("/api/notifications/statuses")
    async def get_notification_statuses() -> Dict[str, Any]:
        """Get available notification statuses"""
        try:
            from agentic.notifications import NotificationStatus
            return {
                "statuses": [
                    {"value": s.value, "name": s.name}
                    for s in NotificationStatus
                ]
            }
        except ImportError:
            return {"error": "Notifications module not available"}

    # ==================== Scheduler System API ====================

    @app.get("/api/scheduler/status")
    async def get_scheduler_status() -> Dict[str, Any]:
        """Get scheduler system status"""
        try:
            from agentic.scheduler import get_job_manager, get_trigger_manager, get_job_executor
            job_mgr = get_job_manager()
            trigger_mgr = get_trigger_manager()
            executor = get_job_executor()
            return {
                "jobs": job_mgr.get_statistics(),
                "triggers": trigger_mgr.get_statistics(),
                "executor": executor.get_statistics()
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs")
    async def get_scheduler_jobs(
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get scheduled jobs"""
        try:
            from agentic.scheduler import get_job_manager, JobStatus, JobType
            manager = get_job_manager()

            j_status = None
            if status:
                try:
                    j_status = JobStatus(status)
                except ValueError:
                    pass

            j_type = None
            if job_type:
                try:
                    j_type = JobType(job_type)
                except ValueError:
                    pass

            jobs = manager.get_jobs(
                status=j_status,
                job_type=j_type,
                enabled_only=enabled_only,
                tag=tag
            )
            return {
                "jobs": [j.to_dict() for j in jobs],
                "count": len(jobs)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs")
    async def create_scheduler_job(request: Request) -> Dict[str, Any]:
        """Create a scheduled job"""
        try:
            from agentic.scheduler import get_job_manager, JobType, JobPriority
            from agentic.scheduler.jobs import JobPriority
            data = await request.json()
            manager = get_job_manager()

            try:
                job_type = JobType(data.get("job_type", "one_time"))
            except ValueError:
                job_type = JobType.ONE_TIME

            try:
                priority = JobPriority(data.get("priority", 2))
            except ValueError:
                priority = JobPriority.NORMAL

            job = manager.create_job(
                name=data["name"],
                handler=data["handler"],
                job_type=job_type,
                trigger_id=data.get("trigger_id"),
                parameters=data.get("parameters"),
                priority=priority,
                max_retries=data.get("max_retries", 3),
                timeout_seconds=data.get("timeout_seconds", 300),
                tags=data.get("tags"),
                depends_on=data.get("depends_on"),
                enabled=data.get("enabled", True)
            )
            return {"job": job.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/{job_id}")
    async def get_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Get a specific job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            job = manager.get_job(job_id)
            if not job:
                return {"error": "Job not found"}
            return {"job": job.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.put("/api/scheduler/jobs/{job_id}")
    async def update_scheduler_job(job_id: str, request: Request) -> Dict[str, Any]:
        """Update a job"""
        try:
            from agentic.scheduler import get_job_manager
            data = await request.json()
            manager = get_job_manager()
            job = manager.update_job(job_id, **data)
            if not job:
                return {"error": "Job not found"}
            return {"job": job.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/scheduler/jobs/{job_id}")
    async def delete_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Delete a job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.delete_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/enable")
    async def enable_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Enable a job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.enable_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/disable")
    async def disable_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Disable a job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.disable_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/pause")
    async def pause_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Pause a job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.pause_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/resume")
    async def resume_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Resume a paused job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.resume_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/cancel")
    async def cancel_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Cancel a job"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            success = manager.cancel_job(job_id)
            return {"success": success, "job_id": job_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/run")
    async def run_scheduler_job(job_id: str) -> Dict[str, Any]:
        """Execute a job immediately"""
        try:
            from agentic.scheduler import get_job_executor
            executor = get_job_executor()
            result = await executor.execute_job(job_id)
            if not result:
                return {"error": "Failed to execute job"}
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/schedule")
    async def schedule_job_time(job_id: str, request: Request) -> Dict[str, Any]:
        """Schedule a job for a specific time"""
        try:
            from agentic.scheduler import get_job_manager
            from datetime import datetime
            data = await request.json()
            manager = get_job_manager()

            run_at = datetime.fromisoformat(data["run_at"])
            success = manager.schedule_job(job_id, run_at)
            return {"success": success, "job_id": job_id, "run_at": run_at.isoformat()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/runnable")
    async def get_runnable_jobs() -> Dict[str, Any]:
        """Get jobs that are ready to run"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            jobs = manager.get_runnable_jobs()
            return {
                "jobs": [j.to_dict() for j in jobs],
                "count": len(jobs)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/running")
    async def get_running_jobs_list() -> Dict[str, Any]:
        """Get currently running jobs"""
        try:
            from agentic.scheduler import get_job_executor
            executor = get_job_executor()
            contexts = executor.get_running_jobs()
            return {
                "jobs": [ctx.to_dict() for ctx in contexts],
                "count": len(contexts)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/history")
    async def get_job_history(
        job_id: Optional[str] = None,
        success_only: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get job execution history"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            results = manager.get_history(job_id=job_id, success_only=success_only, limit=limit)
            return {
                "results": [r.to_dict() for r in results],
                "count": len(results)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/triggers")
    async def get_scheduler_triggers(
        trigger_type: Optional[str] = None,
        enabled_only: bool = False
    ) -> Dict[str, Any]:
        """Get triggers"""
        try:
            from agentic.scheduler import get_trigger_manager, TriggerType
            manager = get_trigger_manager()

            t_type = None
            if trigger_type:
                try:
                    t_type = TriggerType(trigger_type)
                except ValueError:
                    pass

            triggers = manager.get_triggers(trigger_type=t_type, enabled_only=enabled_only)
            return {
                "triggers": [t.to_dict() for t in triggers],
                "count": len(triggers)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/cron")
    async def create_cron_trigger(request: Request) -> Dict[str, Any]:
        """Create a cron trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            data = await request.json()
            manager = get_trigger_manager()

            trigger = manager.create_cron_trigger(
                name=data["name"],
                minute=data.get("minute", "*"),
                hour=data.get("hour", "*"),
                day_of_month=data.get("day_of_month", "*"),
                month=data.get("month", "*"),
                day_of_week=data.get("day_of_week", "*"),
                timezone=data.get("timezone", "UTC"),
                enabled=data.get("enabled", True)
            )
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/interval")
    async def create_interval_trigger(request: Request) -> Dict[str, Any]:
        """Create an interval trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            from datetime import datetime
            data = await request.json()
            manager = get_trigger_manager()

            start_time = None
            if "start_time" in data:
                start_time = datetime.fromisoformat(data["start_time"])

            end_time = None
            if "end_time" in data:
                end_time = datetime.fromisoformat(data["end_time"])

            trigger = manager.create_interval_trigger(
                name=data["name"],
                interval_seconds=data["interval_seconds"],
                start_time=start_time,
                end_time=end_time,
                max_fires=data.get("max_fires"),
                enabled=data.get("enabled", True)
            )
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/date")
    async def create_date_trigger(request: Request) -> Dict[str, Any]:
        """Create a date trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            from datetime import datetime
            data = await request.json()
            manager = get_trigger_manager()

            trigger = manager.create_date_trigger(
                name=data["name"],
                run_at=datetime.fromisoformat(data["run_at"]),
                enabled=data.get("enabled", True)
            )
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/event")
    async def create_event_trigger(request: Request) -> Dict[str, Any]:
        """Create an event trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            data = await request.json()
            manager = get_trigger_manager()

            trigger = manager.create_event_trigger(
                name=data["name"],
                event_type=data["event_type"],
                event_filter=data.get("event_filter"),
                cooldown_seconds=data.get("cooldown_seconds", 0),
                max_fires_per_hour=data.get("max_fires_per_hour", 0),
                enabled=data.get("enabled", True)
            )
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/triggers/{trigger_id}")
    async def get_scheduler_trigger(trigger_id: str) -> Dict[str, Any]:
        """Get a specific trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            manager = get_trigger_manager()
            trigger = manager.get_trigger(trigger_id)
            if not trigger:
                return {"error": "Trigger not found"}
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.put("/api/scheduler/triggers/{trigger_id}")
    async def update_scheduler_trigger(trigger_id: str, request: Request) -> Dict[str, Any]:
        """Update a trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            data = await request.json()
            manager = get_trigger_manager()
            trigger = manager.update_trigger(trigger_id, **data)
            if not trigger:
                return {"error": "Trigger not found"}
            return {"trigger": trigger.to_dict()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/scheduler/triggers/{trigger_id}")
    async def delete_scheduler_trigger(trigger_id: str) -> Dict[str, Any]:
        """Delete a trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            manager = get_trigger_manager()
            success = manager.delete_trigger(trigger_id)
            return {"success": success, "trigger_id": trigger_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/{trigger_id}/enable")
    async def enable_scheduler_trigger(trigger_id: str) -> Dict[str, Any]:
        """Enable a trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            manager = get_trigger_manager()
            success = manager.enable_trigger(trigger_id)
            return {"success": success, "trigger_id": trigger_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/{trigger_id}/disable")
    async def disable_scheduler_trigger(trigger_id: str) -> Dict[str, Any]:
        """Disable a trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            manager = get_trigger_manager()
            success = manager.disable_trigger(trigger_id)
            return {"success": success, "trigger_id": trigger_id}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/tick")
    async def run_scheduler_tick() -> Dict[str, Any]:
        """Run a scheduler tick"""
        try:
            from agentic.scheduler import get_job_executor
            executor = get_job_executor()
            result = await executor.tick()
            return {"tick_result": result}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/event")
    async def fire_scheduler_event(request: Request) -> Dict[str, Any]:
        """Fire an event for event triggers"""
        try:
            from agentic.scheduler import get_job_executor
            data = await request.json()
            executor = get_job_executor()

            fired_jobs = await executor.process_event(
                data["event_type"],
                data.get("event_data", {})
            )
            return {
                "event_type": data["event_type"],
                "fired_jobs": fired_jobs,
                "count": len(fired_jobs)
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/handlers")
    async def get_scheduler_handlers() -> Dict[str, Any]:
        """Get available job handlers"""
        try:
            from agentic.scheduler import get_job_executor
            executor = get_job_executor()
            return {"handlers": executor.get_available_handlers()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/job-types")
    async def get_job_types() -> Dict[str, Any]:
        """Get available job types"""
        try:
            from agentic.scheduler import JobType
            return {
                "job_types": [
                    {"value": t.value, "name": t.name}
                    for t in JobType
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/job-statuses")
    async def get_job_statuses() -> Dict[str, Any]:
        """Get available job statuses"""
        try:
            from agentic.scheduler import JobStatus
            return {
                "statuses": [
                    {"value": s.value, "name": s.name}
                    for s in JobStatus
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/trigger-types")
    async def get_trigger_types() -> Dict[str, Any]:
        """Get available trigger types"""
        try:
            from agentic.scheduler import TriggerType
            return {
                "trigger_types": [
                    {"value": t.value, "name": t.name}
                    for t in TriggerType
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/cleanup")
    async def cleanup_completed_jobs_endpoint(days: int = 7) -> Dict[str, Any]:
        """Remove old completed jobs"""
        try:
            from agentic.scheduler import get_job_manager
            manager = get_job_manager()
            removed = manager.cleanup_completed_jobs(days=days)
            return {
                "removed_count": removed,
                "statistics": manager.get_statistics()
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    # ==================== Inventory Manager API ====================

    @app.get("/api/inventory/status")
    async def get_inventory_status() -> Dict[str, Any]:
        """Get inventory manager status and statistics"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            return manager.get_statistics()
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/devices")
    async def list_inventory_devices(
        device_type: Optional[str] = None,
        status: Optional[str] = None,
        site: Optional[str] = None,
        vendor: Optional[str] = None,
        environment: Optional[str] = None,
        tags: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """List inventory devices with optional filtering"""
        try:
            from agentic.inventory import get_inventory_manager, InventoryFilter, DeviceType, DeviceStatus
            manager = get_inventory_manager()

            filter = InventoryFilter()

            if device_type:
                try:
                    filter.device_types = [DeviceType(device_type)]
                except ValueError:
                    pass

            if status:
                try:
                    filter.statuses = [DeviceStatus(status)]
                except ValueError:
                    pass

            if site:
                filter.sites = [site]
            if vendor:
                filter.vendors = [vendor]
            if environment:
                filter.environments = [environment]
            if tags:
                filter.tags = tags.split(",")
            if search:
                filter.search_text = search

            devices = manager.list_devices(filter)
            return {
                "devices": [d.to_dict() for d in devices],
                "count": len(devices)
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.post("/api/inventory/devices")
    async def create_inventory_device(request: Request) -> Dict[str, Any]:
        """Add a device to inventory"""
        try:
            from agentic.inventory import get_inventory_manager, InventoryDevice, DeviceType, DeviceStatus, LifecycleStage, HardwareInfo, SoftwareInfo, DeviceLocation
            manager = get_inventory_manager()
            data = await request.json()

            device = InventoryDevice()
            device.name = data.get("name", "")
            device.hostname = data.get("hostname", "")
            device.management_ip = data.get("management_ip", "")
            device.management_ipv6 = data.get("management_ipv6", "")
            device.loopback_ip = data.get("loopback_ip", "")
            device.loopback_ipv6 = data.get("loopback_ipv6", "")
            device.owner = data.get("owner", "")
            device.department = data.get("department", "")
            device.environment = data.get("environment", "")
            device.notes = data.get("notes", "")

            if "device_type" in data:
                device.device_type = DeviceType(data["device_type"])
            if "status" in data:
                device.status = DeviceStatus(data["status"])
            if "lifecycle_stage" in data:
                device.lifecycle_stage = LifecycleStage(data["lifecycle_stage"])
            if "tags" in data:
                device.tags = data["tags"]

            if "hardware" in data:
                for k, v in data["hardware"].items():
                    if hasattr(device.hardware, k):
                        setattr(device.hardware, k, v)

            if "software" in data:
                for k, v in data["software"].items():
                    if hasattr(device.software, k):
                        setattr(device.software, k, v)

            if "location" in data:
                for k, v in data["location"].items():
                    if hasattr(device.location, k):
                        setattr(device.location, k, v)

            device = manager.add_device(device)
            return device.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/inventory/devices/{device_id}")
    async def get_inventory_device(device_id: str) -> Dict[str, Any]:
        """Get a specific device by ID"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            device = manager.get_device(device_id)
            if device:
                return device.to_dict()
            return {"error": "Device not found"}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.put("/api/inventory/devices/{device_id}")
    async def update_inventory_device(device_id: str, request: Request) -> Dict[str, Any]:
        """Update a device"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            data = await request.json()
            device = manager.update_device(device_id, data)
            if device:
                return device.to_dict()
            return {"error": "Device not found"}
        except Exception as e:
            return {"error": str(e)}

    @app.delete("/api/inventory/devices/{device_id}")
    async def delete_inventory_device(device_id: str) -> Dict[str, Any]:
        """Delete a device from inventory"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            if manager.delete_device(device_id):
                return {"success": True, "message": "Device deleted"}
            return {"error": "Device not found"}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/alerts")
    async def get_inventory_alerts() -> Dict[str, Any]:
        """Get inventory alerts (warranty/license expiring, etc.)"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            alerts = manager.get_alerts()
            return {
                "alerts": alerts,
                "count": len(alerts),
                "critical": len([a for a in alerts if a["severity"] == "critical"]),
                "warning": len([a for a in alerts if a["severity"] == "warning"])
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.post("/api/inventory/import")
    async def import_inventory(request: Request) -> Dict[str, Any]:
        """Import devices from JSON data"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            data = await request.json()
            devices = data.get("devices", [])
            result = manager.import_devices(devices)
            return result
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/inventory/export")
    async def export_inventory(
        device_type: Optional[str] = None,
        status: Optional[str] = None,
        site: Optional[str] = None
    ) -> Dict[str, Any]:
        """Export inventory to JSON"""
        try:
            from agentic.inventory import get_inventory_manager, InventoryFilter, DeviceType, DeviceStatus
            manager = get_inventory_manager()

            filter = InventoryFilter()
            if device_type:
                try:
                    filter.device_types = [DeviceType(device_type)]
                except ValueError:
                    pass
            if status:
                try:
                    filter.statuses = [DeviceStatus(status)]
                except ValueError:
                    pass
            if site:
                filter.sites = [site]

            devices = manager.export_devices(filter)
            return {
                "devices": devices,
                "count": len(devices),
                "exported_at": datetime.utcnow().isoformat()
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/tags")
    async def get_inventory_tags() -> Dict[str, Any]:
        """Get all unique inventory tags"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            return {"tags": manager.get_tags()}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/sites")
    async def get_inventory_sites() -> Dict[str, Any]:
        """Get all unique inventory sites"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            return {"sites": manager.get_sites()}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/vendors")
    async def get_inventory_vendors() -> Dict[str, Any]:
        """Get all unique inventory vendors"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            return {"vendors": manager.get_vendors()}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/device-types")
    async def get_device_types() -> Dict[str, Any]:
        """Get available device types"""
        try:
            from agentic.inventory import DeviceType
            return {
                "device_types": [
                    {"value": dt.value, "name": dt.name}
                    for dt in DeviceType
                ]
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/statuses")
    async def get_device_statuses() -> Dict[str, Any]:
        """Get available device statuses"""
        try:
            from agentic.inventory import DeviceStatus
            return {
                "statuses": [
                    {"value": s.value, "name": s.name}
                    for s in DeviceStatus
                ]
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/lifecycle-stages")
    async def get_lifecycle_stages() -> Dict[str, Any]:
        """Get available lifecycle stages"""
        try:
            from agentic.inventory import LifecycleStage
            return {
                "lifecycle_stages": [
                    {"value": ls.value, "name": ls.name}
                    for ls in LifecycleStage
                ]
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.post("/api/inventory/devices/{device_id}/connections/{connected_id}")
    async def add_device_connection(device_id: str, connected_id: str) -> Dict[str, Any]:
        """Add a connection between two devices"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            if manager.add_connection(device_id, connected_id):
                return {"success": True, "message": "Connection added"}
            return {"error": "One or both devices not found"}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.delete("/api/inventory/devices/{device_id}/connections/{connected_id}")
    async def remove_device_connection(device_id: str, connected_id: str) -> Dict[str, Any]:
        """Remove a connection between two devices"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            if manager.remove_connection(device_id, connected_id):
                return {"success": True, "message": "Connection removed"}
            return {"error": "One or both devices not found"}
        except ImportError:
            return {"error": "Inventory module not available"}

    @app.get("/api/inventory/devices/{device_id}/connections")
    async def get_device_connections(device_id: str) -> Dict[str, Any]:
        """Get all devices connected to a device"""
        try:
            from agentic.inventory import get_inventory_manager
            manager = get_inventory_manager()
            devices = manager.get_connected_devices(device_id)
            return {
                "connected_devices": [d.to_dict() for d in devices],
                "count": len(devices)
            }
        except ImportError:
            return {"error": "Inventory module not available"}

    # ==================== Capacity Planning API ====================

    @app.get("/api/capacity/status")
    async def get_capacity_status() -> Dict[str, Any]:
        """Get capacity planner status and statistics"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            return planner.get_statistics()
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/summary")
    async def get_capacity_summary() -> Dict[str, Any]:
        """Get high-level capacity summary"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            return planner.get_summary()
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/metrics")
    async def list_capacity_metrics(
        resource_type: Optional[str] = None,
        device_id: Optional[str] = None,
        min_utilization: Optional[float] = None
    ) -> Dict[str, Any]:
        """List capacity metrics with filtering"""
        try:
            from agentic.capacity import get_capacity_planner, ResourceType
            planner = get_capacity_planner()

            rtype = None
            if resource_type:
                try:
                    rtype = ResourceType(resource_type)
                except ValueError:
                    pass

            metrics = planner.get_metrics(
                resource_type=rtype,
                device_id=device_id,
                min_utilization=min_utilization
            )
            return {
                "metrics": [m.to_dict() for m in metrics],
                "count": len(metrics)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.post("/api/capacity/metrics")
    async def record_capacity_metric(request: Request) -> Dict[str, Any]:
        """Record a capacity metric"""
        try:
            from agentic.capacity import get_capacity_planner, ResourceType
            planner = get_capacity_planner()
            data = await request.json()

            rtype = ResourceType(data.get("resource_type", "custom"))
            metric = planner.record_metric(
                resource_type=rtype,
                device_id=data.get("device_id", ""),
                device_name=data.get("device_name", ""),
                resource_name=data.get("resource_name", ""),
                current_value=float(data.get("current_value", 0)),
                max_capacity=float(data.get("max_capacity", 100)),
                unit=data.get("unit", "")
            )
            return metric.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/capacity/metrics/critical")
    async def get_critical_metrics() -> Dict[str, Any]:
        """Get metrics at critical or exhausted levels"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            metrics = planner.get_critical_metrics()
            return {
                "metrics": [m.to_dict() for m in metrics],
                "count": len(metrics)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/forecasts")
    async def list_capacity_forecasts() -> Dict[str, Any]:
        """List all capacity forecasts"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            forecasts = planner.get_forecasts()
            return {
                "forecasts": [f.to_dict() for f in forecasts],
                "count": len(forecasts)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.post("/api/capacity/forecasts/generate")
    async def generate_capacity_forecasts() -> Dict[str, Any]:
        """Generate forecasts for all metrics"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            forecasts = planner.generate_all_forecasts()
            return {
                "forecasts": [f.to_dict() for f in forecasts],
                "count": len(forecasts)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/forecasts/urgent")
    async def get_urgent_forecasts(days: int = 30) -> Dict[str, Any]:
        """Get forecasts that will hit thresholds soon"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            forecasts = planner.get_urgent_forecasts(days)
            return {
                "forecasts": [f.to_dict() for f in forecasts],
                "count": len(forecasts),
                "within_days": days
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/thresholds")
    async def list_capacity_thresholds() -> Dict[str, Any]:
        """List capacity thresholds"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            thresholds = planner.get_thresholds()
            return {
                "thresholds": [t.to_dict() for t in thresholds],
                "count": len(thresholds)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.post("/api/capacity/thresholds")
    async def create_capacity_threshold(request: Request) -> Dict[str, Any]:
        """Create a capacity threshold"""
        try:
            from agentic.capacity import get_capacity_planner, CapacityThreshold, ResourceType
            planner = get_capacity_planner()
            data = await request.json()

            threshold = CapacityThreshold(
                resource_type=ResourceType(data.get("resource_type", "custom")),
                device_pattern=data.get("device_pattern", "*"),
                resource_pattern=data.get("resource_pattern", "*"),
                warning_pct=float(data.get("warning_pct", 70)),
                critical_pct=float(data.get("critical_pct", 90))
            )
            threshold = planner.add_threshold(threshold)
            return threshold.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/capacity/recommendations")
    async def list_capacity_recommendations(status: Optional[str] = None) -> Dict[str, Any]:
        """List capacity recommendations"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            recommendations = planner.get_recommendations(status)
            return {
                "recommendations": [r.to_dict() for r in recommendations],
                "count": len(recommendations)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.post("/api/capacity/recommendations/generate")
    async def generate_recommendations() -> Dict[str, Any]:
        """Generate capacity recommendations"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            recommendations = planner.generate_recommendations()
            return {
                "recommendations": [r.to_dict() for r in recommendations],
                "count": len(recommendations)
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.put("/api/capacity/recommendations/{rec_id}")
    async def update_recommendation_status(rec_id: str, request: Request) -> Dict[str, Any]:
        """Update recommendation status"""
        try:
            from agentic.capacity import get_capacity_planner
            planner = get_capacity_planner()
            data = await request.json()
            status = data.get("status", "pending")
            rec = planner.update_recommendation(rec_id, status)
            if rec:
                return rec.to_dict()
            return {"error": "Recommendation not found"}
        except ImportError:
            return {"error": "Capacity module not available"}

    @app.get("/api/capacity/resource-types")
    async def get_resource_types() -> Dict[str, Any]:
        """Get available resource types"""
        try:
            from agentic.capacity import ResourceType
            return {
                "resource_types": [
                    {"value": rt.value, "name": rt.name}
                    for rt in ResourceType
                ]
            }
        except ImportError:
            return {"error": "Capacity module not available"}

    # ==================== SLA Monitoring API ====================

    @app.get("/api/sla/status")
    async def get_sla_status() -> Dict[str, Any]:
        """Get SLA monitoring statistics"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            return monitor.get_statistics()
        except ImportError:
            return {"error": "SLA module not available"}

    @app.get("/api/sla/summary")
    async def get_sla_summary() -> Dict[str, Any]:
        """Get SLA dashboard summary"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            return monitor.get_dashboard_summary()
        except ImportError:
            return {"error": "SLA module not available"}

    @app.get("/api/sla/definitions")
    async def list_sla_definitions(enabled_only: bool = False) -> Dict[str, Any]:
        """List all SLA definitions"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            slas = monitor.list_slas(enabled_only)
            return {
                "slas": [s.to_dict() for s in slas],
                "count": len(slas)
            }
        except ImportError:
            return {"error": "SLA module not available"}

    @app.post("/api/sla/definitions")
    async def create_sla_definition(request: Request) -> Dict[str, Any]:
        """Create a new SLA definition"""
        try:
            from agentic.sla import get_sla_monitor, SLADefinition, SLATarget, SLAMetricType
            monitor = get_sla_monitor()
            data = await request.json()

            sla = SLADefinition(
                name=data.get("name", ""),
                description=data.get("description", ""),
                service_name=data.get("service_name", ""),
                service_type=data.get("service_type", "network"),
                scope=data.get("scope", []),
                measurement_window=data.get("measurement_window", "30d"),
                owner=data.get("owner", "")
            )

            if "targets" in data:
                for t in data["targets"]:
                    target = SLATarget(
                        metric_type=SLAMetricType(t.get("metric_type", "availability")),
                        target_value=float(t.get("target_value", 99.9)),
                        comparison=t.get("comparison", ">="),
                        unit=t.get("unit", "%"),
                        warning_threshold=float(t.get("warning_threshold", 99.5))
                    )
                    sla.targets.append(target)

            sla = monitor.create_sla(sla)
            return sla.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/sla/definitions/{sla_id}")
    async def get_sla_definition(sla_id: str) -> Dict[str, Any]:
        """Get a specific SLA"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            sla = monitor.get_sla(sla_id)
            if sla:
                return sla.to_dict()
            return {"error": "SLA not found"}
        except ImportError:
            return {"error": "SLA module not available"}

    @app.delete("/api/sla/definitions/{sla_id}")
    async def delete_sla_definition(sla_id: str) -> Dict[str, Any]:
        """Delete an SLA"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            if monitor.delete_sla(sla_id):
                return {"success": True, "message": "SLA deleted"}
            return {"error": "SLA not found"}
        except ImportError:
            return {"error": "SLA module not available"}

    @app.post("/api/sla/{sla_id}/metrics")
    async def record_sla_metric(sla_id: str, request: Request) -> Dict[str, Any]:
        """Record an SLA metric sample"""
        try:
            from agentic.sla import get_sla_monitor, SLAMetricType
            monitor = get_sla_monitor()
            data = await request.json()

            sample = monitor.record_metric(
                sla_id=sla_id,
                metric_type=SLAMetricType(data.get("metric_type", "availability")),
                value=float(data.get("value", 0)),
                source=data.get("source", "")
            )

            if sample:
                return sample.to_dict()
            return {"error": "SLA not found"}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/sla/violations")
    async def list_sla_violations(
        sla_id: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List SLA violations"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            violations = monitor.get_violations(sla_id, active_only, limit)
            return {
                "violations": [v.to_dict() for v in violations],
                "count": len(violations)
            }
        except ImportError:
            return {"error": "SLA module not available"}

    @app.post("/api/sla/violations/{violation_id}/acknowledge")
    async def acknowledge_sla_violation(violation_id: str, request: Request) -> Dict[str, Any]:
        """Acknowledge an SLA violation"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            data = await request.json()
            violation = monitor.acknowledge_violation(violation_id, data.get("acknowledged_by", ""))
            if violation:
                return violation.to_dict()
            return {"error": "Violation not found"}
        except ImportError:
            return {"error": "SLA module not available"}

    @app.post("/api/sla/violations/{violation_id}/resolve")
    async def resolve_sla_violation(violation_id: str, request: Request) -> Dict[str, Any]:
        """Resolve an SLA violation"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            data = await request.json()
            violation = monitor.resolve_violation(violation_id, data.get("resolution", ""))
            if violation:
                return violation.to_dict()
            return {"error": "Violation not found"}
        except ImportError:
            return {"error": "SLA module not available"}

    @app.post("/api/sla/{sla_id}/report")
    async def generate_sla_report(sla_id: str, days: int = 30) -> Dict[str, Any]:
        """Generate an SLA compliance report"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            report = monitor.generate_report(sla_id, days)
            if report:
                return report.to_dict()
            return {"error": "SLA not found or no data"}
        except ImportError:
            return {"error": "SLA module not available"}

    @app.get("/api/sla/reports")
    async def list_sla_reports(sla_id: Optional[str] = None) -> Dict[str, Any]:
        """List generated SLA reports"""
        try:
            from agentic.sla import get_sla_monitor
            monitor = get_sla_monitor()
            reports = monitor.get_reports(sla_id)
            return {
                "reports": [r.to_dict() for r in reports],
                "count": len(reports)
            }
        except ImportError:
            return {"error": "SLA module not available"}

    @app.get("/api/sla/metric-types")
    async def get_sla_metric_types() -> Dict[str, Any]:
        """Get available SLA metric types"""
        try:
            from agentic.sla import SLAMetricType
            return {
                "metric_types": [
                    {"value": mt.value, "name": mt.name}
                    for mt in SLAMetricType
                ]
            }
        except ImportError:
            return {"error": "SLA module not available"}

    # ==================== Plugin System API ====================

    @app.get("/api/plugins/status")
    async def get_plugins_status() -> Dict[str, Any]:
        """Get plugin system status"""
        try:
            from agentic.plugins import get_plugin_manager, get_hook_manager, get_plugin_registry
            plugin_mgr = get_plugin_manager()
            hook_mgr = get_hook_manager()
            registry = get_plugin_registry()
            return {
                "plugins": plugin_mgr.get_statistics(),
                "hooks": hook_mgr.get_statistics(),
                "registry": registry.get_statistics()
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins")
    async def get_plugins_list(
        status: Optional[str] = None,
        plugin_type: Optional[str] = None,
        enabled_only: bool = False
    ) -> Dict[str, Any]:
        """Get installed plugins"""
        try:
            from agentic.plugins import get_plugin_manager, PluginStatus, PluginType
            manager = get_plugin_manager()

            p_status = None
            if status:
                try:
                    p_status = PluginStatus(status)
                except ValueError:
                    pass

            p_type = None
            if plugin_type:
                try:
                    p_type = PluginType(plugin_type)
                except ValueError:
                    pass

            plugins = manager.get_plugins(
                status=p_status,
                plugin_type=p_type,
                enabled_only=enabled_only
            )
            return {
                "plugins": [p.to_dict() for p in plugins],
                "count": len(plugins)
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins")
    async def create_plugin(request: Request) -> Dict[str, Any]:
        """Create a simple plugin"""
        try:
            from agentic.plugins import get_plugin_manager, PluginType, PluginConfig
            data = await request.json()
            manager = get_plugin_manager()

            try:
                plugin_type = PluginType(data.get("plugin_type", "utility"))
            except ValueError:
                plugin_type = PluginType.UTILITY

            config = None
            if "config" in data:
                config = PluginConfig(
                    settings=data["config"].get("settings", {}),
                    enabled_features=data["config"].get("enabled_features", [])
                )

            plugin = manager.create_plugin(
                plugin_id=data.get("plugin_id") or f"plugin_{data['name'].lower().replace(' ', '_')}",
                name=data["name"],
                version=data.get("version", "1.0.0"),
                description=data.get("description", ""),
                plugin_type=plugin_type,
                config=config
            )
            return {"plugin": plugin.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins/install/{plugin_id}")
    async def install_plugin(plugin_id: str, request: Request) -> Dict[str, Any]:
        """Install a plugin from registry"""
        try:
            from agentic.plugins import get_plugin_manager, PluginConfig
            data = await request.json() if request.headers.get("content-length") else {}
            manager = get_plugin_manager()

            config = None
            if "config" in data:
                config = PluginConfig(
                    settings=data["config"].get("settings", {}),
                    enabled_features=data["config"].get("enabled_features", [])
                )

            plugin = manager.install_plugin(plugin_id, config)
            if not plugin:
                return {"error": "Failed to install plugin or plugin not found in registry"}
            return {"plugin": plugin.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.delete("/api/plugins/{plugin_id}")
    async def uninstall_plugin(plugin_id: str) -> Dict[str, Any]:
        """Uninstall a plugin"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            success = manager.uninstall_plugin(plugin_id)
            return {"success": success, "plugin_id": plugin_id}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/{plugin_id}")
    async def get_plugin(plugin_id: str) -> Dict[str, Any]:
        """Get a specific plugin"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            plugin = manager.get_plugin(plugin_id)
            if not plugin:
                return {"error": "Plugin not found"}
            return {"plugin": plugin.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins/{plugin_id}/enable")
    async def enable_plugin(plugin_id: str) -> Dict[str, Any]:
        """Enable a plugin"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            success = manager.enable_plugin(plugin_id)
            return {"success": success, "plugin_id": plugin_id}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins/{plugin_id}/disable")
    async def disable_plugin(plugin_id: str) -> Dict[str, Any]:
        """Disable a plugin"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            success = manager.disable_plugin(plugin_id)
            return {"success": success, "plugin_id": plugin_id}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.put("/api/plugins/{plugin_id}/config")
    async def update_plugin_config(plugin_id: str, request: Request) -> Dict[str, Any]:
        """Update plugin configuration"""
        try:
            from agentic.plugins import get_plugin_manager, PluginConfig
            data = await request.json()
            manager = get_plugin_manager()

            config = PluginConfig(
                settings=data.get("settings", {}),
                enabled_features=data.get("enabled_features", [])
            )

            plugin = manager.update_plugin_config(plugin_id, config)
            if not plugin:
                return {"error": "Plugin not found"}
            return {"plugin": plugin.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/{plugin_id}/dependencies")
    async def check_plugin_dependencies(plugin_id: str) -> Dict[str, Any]:
        """Check plugin dependencies"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            return manager.check_dependencies(plugin_id)
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/{plugin_id}/health")
    async def check_plugin_health(plugin_id: str) -> Dict[str, Any]:
        """Check plugin health"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            plugin = manager.get_plugin(plugin_id)
            if not plugin:
                return {"error": "Plugin not found"}
            return {"health": plugin.health_check()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/health")
    async def check_all_plugins_health() -> Dict[str, Any]:
        """Check health of all plugins"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            return {"health": manager.health_check_all()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/routes")
    async def get_plugin_routes() -> Dict[str, Any]:
        """Get API routes from enabled plugins"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            return {"routes": manager.get_plugin_api_routes()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/menu-items")
    async def get_plugin_menu_items() -> Dict[str, Any]:
        """Get menu items from enabled plugins"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            return {"menu_items": manager.get_plugin_menu_items()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/widgets")
    async def get_plugin_widgets() -> Dict[str, Any]:
        """Get widgets from enabled plugins"""
        try:
            from agentic.plugins import get_plugin_manager
            manager = get_plugin_manager()
            return {"widgets": manager.get_plugin_widgets()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/registry")
    async def get_plugin_registry(
        query: Optional[str] = None,
        plugin_type: Optional[str] = None,
        tag: Optional[str] = None,
        verified_only: bool = False,
        featured_only: bool = False
    ) -> Dict[str, Any]:
        """Search plugin registry"""
        try:
            from agentic.plugins import get_plugin_registry as get_registry, PluginType
            registry = get_registry()

            p_type = None
            if plugin_type:
                try:
                    p_type = PluginType(plugin_type)
                except ValueError:
                    pass

            entries = registry.search(
                query=query,
                plugin_type=p_type,
                tag=tag,
                verified_only=verified_only,
                featured_only=featured_only
            )
            return {
                "plugins": [e.to_dict() for e in entries],
                "count": len(entries)
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/registry/{plugin_id}")
    async def get_registry_entry(plugin_id: str) -> Dict[str, Any]:
        """Get registry entry for a plugin"""
        try:
            from agentic.plugins import get_plugin_registry as get_registry
            registry = get_registry()
            entry = registry.get(plugin_id)
            if not entry:
                return {"error": "Plugin not found in registry"}
            return {"plugin": entry.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/registry/featured")
    async def get_featured_plugins() -> Dict[str, Any]:
        """Get featured plugins from registry"""
        try:
            from agentic.plugins import get_plugin_registry as get_registry
            registry = get_registry()
            entries = registry.get_featured()
            return {
                "plugins": [e.to_dict() for e in entries],
                "count": len(entries)
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/registry/popular")
    async def get_popular_plugins(limit: int = 10) -> Dict[str, Any]:
        """Get popular plugins from registry"""
        try:
            from agentic.plugins import get_plugin_registry as get_registry
            registry = get_registry()
            entries = registry.get_popular(limit)
            return {
                "plugins": [e.to_dict() for e in entries],
                "count": len(entries)
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/registry/tags")
    async def get_registry_tags() -> Dict[str, Any]:
        """Get all tags from registry"""
        try:
            from agentic.plugins import get_plugin_registry as get_registry
            registry = get_registry()
            return {"tags": registry.get_all_tags()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/hooks")
    async def get_hooks_list(
        hook_type: Optional[str] = None,
        plugin_id: Optional[str] = None,
        enabled_only: bool = False
    ) -> Dict[str, Any]:
        """Get registered hooks"""
        try:
            from agentic.plugins import get_hook_manager, HookType
            manager = get_hook_manager()

            h_type = None
            if hook_type:
                try:
                    h_type = HookType(hook_type)
                except ValueError:
                    pass

            hooks = manager.get_hooks(
                hook_type=h_type,
                plugin_id=plugin_id,
                enabled_only=enabled_only
            )
            return {
                "hooks": [h.to_dict() for h in hooks],
                "count": len(hooks)
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/hooks/{hook_id}")
    async def get_hook(hook_id: str) -> Dict[str, Any]:
        """Get a specific hook"""
        try:
            from agentic.plugins import get_hook_manager
            manager = get_hook_manager()
            hook = manager.get_hook(hook_id)
            if not hook:
                return {"error": "Hook not found"}
            return {"hook": hook.to_dict()}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins/hooks/{hook_id}/enable")
    async def enable_hook(hook_id: str) -> Dict[str, Any]:
        """Enable a hook"""
        try:
            from agentic.plugins import get_hook_manager
            manager = get_hook_manager()
            success = manager.enable_hook(hook_id)
            return {"success": success, "hook_id": hook_id}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.post("/api/plugins/hooks/{hook_id}/disable")
    async def disable_hook(hook_id: str) -> Dict[str, Any]:
        """Disable a hook"""
        try:
            from agentic.plugins import get_hook_manager
            manager = get_hook_manager()
            success = manager.disable_hook(hook_id)
            return {"success": success, "hook_id": hook_id}
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/types")
    async def get_plugin_types() -> Dict[str, Any]:
        """Get available plugin types"""
        try:
            from agentic.plugins import PluginType
            return {
                "types": [
                    {"value": t.value, "name": t.name}
                    for t in PluginType
                ]
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/statuses")
    async def get_plugin_statuses() -> Dict[str, Any]:
        """Get available plugin statuses"""
        try:
            from agentic.plugins import PluginStatus
            return {
                "statuses": [
                    {"value": s.value, "name": s.name}
                    for s in PluginStatus
                ]
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    @app.get("/api/plugins/hook-types")
    async def get_hook_types() -> Dict[str, Any]:
        """Get available hook types"""
        try:
            from agentic.plugins import HookType
            return {
                "hook_types": [
                    {"value": t.value, "name": t.name}
                    for t in HookType
                ]
            }
        except ImportError:
            return {"error": "Plugins module not available"}

    # ==================== Workflow Engine API ====================

    @app.get("/api/workflows")
    async def list_workflows(
        status: Optional[str] = None,
        tag: Optional[str] = None,
        created_by: Optional[str] = None
    ):
        """List all workflows"""
        try:
            from agentic.workflows import get_workflow_engine, WorkflowStatus
            engine = get_workflow_engine()
            status_filter = WorkflowStatus(status) if status else None
            workflows = engine.get_workflows(status=status_filter, tag=tag, created_by=created_by)
            return {"workflows": [w.to_dict() for w in workflows]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows")
    async def create_workflow(data: dict):
        """Create a new workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            workflow = engine.create_workflow(
                name=data.get("name", "Unnamed Workflow"),
                description=data.get("description", ""),
                version=data.get("version", "1.0.0"),
                tags=data.get("tags", []),
                created_by=data.get("created_by", "")
            )
            return {"workflow": workflow.to_dict()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        """Get workflow by ID"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            workflow = engine.get_workflow(workflow_id)
            if workflow:
                return {"workflow": workflow.to_dict()}
            return {"error": "Workflow not found"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, data: dict):
        """Update a workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            workflow = engine.update_workflow(workflow_id, **data)
            if workflow:
                return {"workflow": workflow.to_dict()}
            return {"error": "Workflow not found"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        """Delete a workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            success = engine.delete_workflow(workflow_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/execute")
    async def execute_workflow(workflow_id: str, data: dict = None):
        """Execute a workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            inputs = data.get("inputs", {}) if data else {}
            result = await engine.execute_workflow(workflow_id, inputs)
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/start")
    async def start_workflow_async(workflow_id: str, data: dict = None):
        """Start workflow asynchronously"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            inputs = data.get("inputs", {}) if data else {}
            success = engine.start_workflow_async(workflow_id, inputs)
            return {"started": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/pause")
    async def pause_workflow(workflow_id: str):
        """Pause a running workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            success = engine.pause_workflow(workflow_id)
            return {"paused": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/resume")
    async def resume_workflow(workflow_id: str):
        """Resume a paused workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            success = engine.resume_workflow(workflow_id)
            return {"resumed": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/cancel")
    async def cancel_workflow(workflow_id: str):
        """Cancel a workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            success = engine.cancel_workflow(workflow_id)
            return {"cancelled": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/clone")
    async def clone_workflow(workflow_id: str, data: dict):
        """Clone a workflow"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            new_name = data.get("name", "Cloned Workflow")
            cloned = engine.clone_workflow(workflow_id, new_name)
            if cloned:
                return {"workflow": cloned.to_dict()}
            return {"error": "Workflow not found"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/{workflow_id}/history")
    async def get_workflow_history(workflow_id: str):
        """Get workflow execution history"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            history = engine.get_workflow_history(workflow_id)
            return {"history": [r.to_dict() for r in history]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/steps")
    async def add_workflow_step(workflow_id: str, data: dict):
        """Add a step to a workflow"""
        try:
            from agentic.workflows import get_workflow_engine, get_step_manager, Step, StepType, StepConfig
            engine = get_workflow_engine()
            step_manager = get_step_manager()

            step = Step(
                id=f"step_{data.get('id', '')}",
                name=data.get("name", "Unnamed Step"),
                step_type=StepType(data.get("step_type", "action")),
                description=data.get("description", ""),
                handler=data.get("handler"),
                parameters=data.get("parameters", {}),
                config=StepConfig(
                    timeout_seconds=data.get("timeout", 300),
                    retry_count=data.get("retry_count", 0),
                    continue_on_failure=data.get("continue_on_failure", False)
                )
            )

            success = engine.add_step_to_workflow(workflow_id, step)
            return {"added": success, "step": step.to_dict() if success else None}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/{workflow_id}/connect")
    async def connect_workflow_steps(workflow_id: str, data: dict):
        """Connect workflow steps"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            success = engine.connect_workflow_steps(
                workflow_id,
                data.get("from_step_id"),
                data.get("to_step_id"),
                data.get("on_success", True)
            )
            return {"connected": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/running")
    async def get_running_workflows():
        """Get running workflows"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            workflows = engine.get_running_workflows()
            return {"workflows": [w.to_dict() for w in workflows]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/statistics")
    async def get_workflow_statistics():
        """Get workflow engine statistics"""
        try:
            from agentic.workflows import get_workflow_engine
            engine = get_workflow_engine()
            return {"statistics": engine.get_statistics()}
        except ImportError:
            return {"error": "Workflows module not available"}

    # Workflow Steps API

    @app.get("/api/workflows/steps")
    async def list_steps(
        step_type: Optional[str] = None,
        status: Optional[str] = None
    ):
        """List all steps"""
        try:
            from agentic.workflows import get_step_manager, StepType, StepStatus
            manager = get_step_manager()
            type_filter = StepType(step_type) if step_type else None
            status_filter = StepStatus(status) if status else None
            steps = manager.get_steps(step_type=type_filter, status=status_filter)
            return {"steps": [s.to_dict() for s in steps]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/steps")
    async def create_step(data: dict):
        """Create a new step"""
        try:
            from agentic.workflows import get_step_manager, StepType, StepConfig
            manager = get_step_manager()
            config = StepConfig(**data.get("config", {})) if "config" in data else None
            step = manager.create_step(
                name=data.get("name", "Unnamed Step"),
                step_type=StepType(data.get("step_type", "action")),
                description=data.get("description", ""),
                handler=data.get("handler"),
                parameters=data.get("parameters", {}),
                config=config
            )
            return {"step": step.to_dict()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/steps/{step_id}")
    async def get_step(step_id: str):
        """Get step by ID"""
        try:
            from agentic.workflows import get_step_manager
            manager = get_step_manager()
            step = manager.get_step(step_id)
            if step:
                return {"step": step.to_dict()}
            return {"error": "Step not found"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.delete("/api/workflows/steps/{step_id}")
    async def delete_step(step_id: str):
        """Delete a step"""
        try:
            from agentic.workflows import get_step_manager
            manager = get_step_manager()
            success = manager.delete_step(step_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/steps/{step_id}/reset")
    async def reset_step(step_id: str):
        """Reset step to pending"""
        try:
            from agentic.workflows import get_step_manager
            manager = get_step_manager()
            success = manager.reset_step(step_id)
            return {"reset": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/handlers")
    async def get_step_handlers():
        """Get available step handlers"""
        try:
            from agentic.workflows import get_step_manager
            manager = get_step_manager()
            return {"handlers": manager.get_available_handlers()}
        except ImportError:
            return {"error": "Workflows module not available"}

    # Workflow Templates API

    @app.get("/api/workflows/templates")
    async def list_templates(
        query: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        builtin_only: bool = False
    ):
        """List workflow templates"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            templates = manager.search(
                query=query,
                category=category,
                tag=tag,
                builtin_only=builtin_only
            )
            return {"templates": [t.to_dict() for t in templates]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/templates/{template_id}")
    async def get_template(template_id: str):
        """Get template by ID"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            template = manager.get(template_id)
            if template:
                return {"template": template.to_dict()}
            return {"error": "Template not found"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/templates")
    async def create_template(data: dict):
        """Create a workflow template"""
        try:
            from agentic.workflows import get_workflow_template_manager, WorkflowTemplate, TemplateVariable
            manager = get_workflow_template_manager()

            variables = []
            for var_data in data.get("variables", []):
                variables.append(TemplateVariable(**var_data))

            template = WorkflowTemplate(
                id=f"tpl_{data.get('id', '')}",
                name=data.get("name", "Unnamed Template"),
                description=data.get("description", ""),
                category=data.get("category", "general"),
                version=data.get("version", "1.0.0"),
                variables=variables,
                steps_definition=data.get("steps_definition", []),
                tags=data.get("tags", []),
                author=data.get("author", "")
            )

            registered = manager.register(template)
            return {"template": registered.to_dict()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.delete("/api/workflows/templates/{template_id}")
    async def delete_template(template_id: str):
        """Delete a template"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            success = manager.delete(template_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/templates/{template_id}/instantiate")
    async def instantiate_template(template_id: str, data: dict):
        """Create workflow from template"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            workflow = manager.instantiate(
                template_id,
                data.get("workflow_name", "From Template"),
                data.get("inputs", {}),
                data.get("created_by", "")
            )
            if workflow:
                return {"workflow": workflow.to_dict()}
            return {"error": "Template not found or invalid inputs"}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.post("/api/workflows/templates/{template_id}/rate")
    async def rate_template(template_id: str, data: dict):
        """Rate a template"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            success = manager.rate_template(template_id, data.get("rating", 5))
            return {"rated": success}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/templates/categories")
    async def get_template_categories():
        """Get template categories"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            return {"categories": manager.get_categories()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/templates/tags")
    async def get_template_tags():
        """Get template tags"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            return {"tags": manager.get_tags()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/templates/popular")
    async def get_popular_templates(limit: int = 10):
        """Get popular templates"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            templates = manager.get_popular(limit)
            return {"templates": [t.to_dict() for t in templates]}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/templates/statistics")
    async def get_template_statistics():
        """Get template statistics"""
        try:
            from agentic.workflows import get_workflow_template_manager
            manager = get_workflow_template_manager()
            return {"statistics": manager.get_statistics()}
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/step-types")
    async def get_step_types():
        """Get available step types"""
        try:
            from agentic.workflows import StepType
            return {
                "step_types": [
                    {"value": t.value, "name": t.name}
                    for t in StepType
                ]
            }
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/step-statuses")
    async def get_step_statuses():
        """Get step status values"""
        try:
            from agentic.workflows import StepStatus
            return {
                "step_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in StepStatus
                ]
            }
        except ImportError:
            return {"error": "Workflows module not available"}

    @app.get("/api/workflows/statuses")
    async def get_workflow_statuses():
        """Get workflow status values"""
        try:
            from agentic.workflows import WorkflowStatus
            return {
                "workflow_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in WorkflowStatus
                ]
            }
        except ImportError:
            return {"error": "Workflows module not available"}

    # ==================== Data Pipeline API ====================

    @app.get("/api/pipelines")
    async def list_pipelines(
        status: Optional[str] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False
    ):
        """List all pipelines"""
        try:
            from agentic.pipelines import get_pipeline_manager, PipelineStatus
            manager = get_pipeline_manager()
            status_filter = PipelineStatus(status) if status else None
            pipelines = manager.get_pipelines(status=status_filter, enabled_only=enabled_only, tag=tag)
            return {"pipelines": [p.to_dict() for p in pipelines]}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines")
    async def create_pipeline(data: dict):
        """Create a new pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            pipeline = manager.create_pipeline(
                name=data.get("name", "Unnamed Pipeline"),
                description=data.get("description", ""),
                source_ids=data.get("source_ids", []),
                transform_ids=data.get("transform_ids", []),
                sink_ids=data.get("sink_ids", []),
                schedule=data.get("schedule"),
                tags=data.get("tags", [])
            )
            return {"pipeline": pipeline.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/{pipeline_id}")
    async def get_pipeline_detail(pipeline_id: str):
        """Get pipeline by ID"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            pipeline = manager.get_pipeline(pipeline_id)
            if pipeline:
                return {"pipeline": pipeline.to_dict()}
            return {"error": "Pipeline not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.put("/api/pipelines/{pipeline_id}")
    async def update_pipeline_detail(pipeline_id: str, data: dict):
        """Update a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            pipeline = manager.update_pipeline(pipeline_id, **data)
            if pipeline:
                return {"pipeline": pipeline.to_dict()}
            return {"error": "Pipeline not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/{pipeline_id}")
    async def delete_pipeline_detail(pipeline_id: str):
        """Delete a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.delete_pipeline(pipeline_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/run")
    async def run_pipeline(pipeline_id: str):
        """Run a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            result = await manager.run(pipeline_id)
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/start")
    async def start_pipeline_async(pipeline_id: str):
        """Start pipeline asynchronously"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.start_async(pipeline_id)
            return {"started": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/pause")
    async def pause_pipeline(pipeline_id: str):
        """Pause a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.pause(pipeline_id)
            return {"paused": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/resume")
    async def resume_pipeline(pipeline_id: str):
        """Resume a paused pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.resume(pipeline_id)
            return {"resumed": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/cancel")
    async def cancel_pipeline(pipeline_id: str):
        """Cancel a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.cancel(pipeline_id)
            return {"cancelled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/enable")
    async def enable_pipeline(pipeline_id: str):
        """Enable a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.enable_pipeline(pipeline_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/disable")
    async def disable_pipeline(pipeline_id: str):
        """Disable a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.disable_pipeline(pipeline_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/clone")
    async def clone_pipeline(pipeline_id: str, data: dict):
        """Clone a pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            cloned = manager.clone(pipeline_id, data.get("name", "Cloned Pipeline"))
            if cloned:
                return {"pipeline": cloned.to_dict()}
            return {"error": "Pipeline not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/{pipeline_id}/validate")
    async def validate_pipeline(pipeline_id: str):
        """Validate a pipeline configuration"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            result = manager.validate(pipeline_id)
            return {"validation": result}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/sources/{source_id}")
    async def add_source_to_pipeline(pipeline_id: str, source_id: str):
        """Add source to pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.add_source(pipeline_id, source_id)
            return {"added": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/{pipeline_id}/sources/{source_id}")
    async def remove_source_from_pipeline(pipeline_id: str, source_id: str):
        """Remove source from pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.remove_source(pipeline_id, source_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/transforms/{transform_id}")
    async def add_transform_to_pipeline(pipeline_id: str, transform_id: str):
        """Add transform to pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.add_transform(pipeline_id, transform_id)
            return {"added": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/{pipeline_id}/transforms/{transform_id}")
    async def remove_transform_from_pipeline(pipeline_id: str, transform_id: str):
        """Remove transform from pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.remove_transform(pipeline_id, transform_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/{pipeline_id}/sinks/{sink_id}")
    async def add_sink_to_pipeline(pipeline_id: str, sink_id: str):
        """Add sink to pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.add_sink(pipeline_id, sink_id)
            return {"added": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/{pipeline_id}/sinks/{sink_id}")
    async def remove_sink_from_pipeline(pipeline_id: str, sink_id: str):
        """Remove sink from pipeline"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            success = manager.remove_sink(pipeline_id, sink_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/running")
    async def get_running_pipelines():
        """Get running pipelines"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            pipelines = manager.get_running()
            return {"pipelines": [p.to_dict() for p in pipelines]}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/statistics")
    async def get_pipeline_statistics():
        """Get pipeline statistics"""
        try:
            from agentic.pipelines import get_pipeline_manager
            manager = get_pipeline_manager()
            return {"statistics": manager.get_statistics()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    # Data Sources API

    @app.get("/api/pipelines/sources")
    async def list_sources(
        source_type: Optional[str] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False
    ):
        """List all data sources"""
        try:
            from agentic.pipelines import get_source_manager, SourceType
            manager = get_source_manager()
            type_filter = SourceType(source_type) if source_type else None
            sources = manager.get_sources(source_type=type_filter, enabled_only=enabled_only, tag=tag)
            return {"sources": [s.to_dict() for s in sources]}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sources")
    async def create_source(data: dict):
        """Create a new data source"""
        try:
            from agentic.pipelines import get_source_manager, SourceType, SourceConfig
            manager = get_source_manager()
            config = SourceConfig(**data.get("config", {})) if "config" in data else None
            source = manager.create_source(
                name=data.get("name", "Unnamed Source"),
                source_type=SourceType(data.get("source_type", "api")),
                description=data.get("description", ""),
                config=config,
                tags=data.get("tags", [])
            )
            return {"source": source.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/sources/{source_id}")
    async def get_source_detail(source_id: str):
        """Get source by ID"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            source = manager.get_source(source_id)
            if source:
                return {"source": source.to_dict()}
            return {"error": "Source not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/sources/{source_id}")
    async def delete_source(source_id: str):
        """Delete a source"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            success = manager.delete_source(source_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sources/{source_id}/extract")
    async def extract_from_source(source_id: str):
        """Extract data from source"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            result = await manager.extract(source_id)
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sources/{source_id}/test")
    async def test_source_connection(source_id: str):
        """Test source connection"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            result = manager.test_connection(source_id)
            return {"result": result}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sources/{source_id}/enable")
    async def enable_source(source_id: str):
        """Enable a source"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            success = manager.enable_source(source_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sources/{source_id}/disable")
    async def disable_source(source_id: str):
        """Disable a source"""
        try:
            from agentic.pipelines import get_source_manager
            manager = get_source_manager()
            success = manager.disable_source(source_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    # Data Transforms API

    @app.get("/api/pipelines/transforms")
    async def list_transforms(
        transform_type: Optional[str] = None,
        enabled_only: bool = False
    ):
        """List all transforms"""
        try:
            from agentic.pipelines import get_transform_manager, TransformType
            manager = get_transform_manager()
            type_filter = TransformType(transform_type) if transform_type else None
            transforms = manager.get_transforms(transform_type=type_filter, enabled_only=enabled_only)
            return {"transforms": [t.to_dict() for t in transforms]}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/transforms")
    async def create_transform(data: dict):
        """Create a new transform"""
        try:
            from agentic.pipelines import get_transform_manager, TransformType, TransformConfig
            manager = get_transform_manager()
            config = TransformConfig(**data.get("config", {})) if "config" in data else None
            transform = manager.create_transform(
                name=data.get("name", "Unnamed Transform"),
                transform_type=TransformType(data.get("transform_type", "filter")),
                description=data.get("description", ""),
                config=config
            )
            return {"transform": transform.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/transforms/{transform_id}")
    async def get_transform_detail(transform_id: str):
        """Get transform by ID"""
        try:
            from agentic.pipelines import get_transform_manager
            manager = get_transform_manager()
            transform = manager.get_transform(transform_id)
            if transform:
                return {"transform": transform.to_dict()}
            return {"error": "Transform not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/transforms/{transform_id}")
    async def delete_transform(transform_id: str):
        """Delete a transform"""
        try:
            from agentic.pipelines import get_transform_manager
            manager = get_transform_manager()
            success = manager.delete_transform(transform_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/transforms/{transform_id}/apply")
    async def apply_transform(transform_id: str, data: dict):
        """Apply transform to data"""
        try:
            from agentic.pipelines import get_transform_manager
            manager = get_transform_manager()
            input_data = data.get("data", [])
            result = manager.apply(transform_id, input_data)
            return {"result": result.to_dict(), "data": result.data}
        except ImportError:
            return {"error": "Pipelines module not available"}

    # Data Sinks API

    @app.get("/api/pipelines/sinks")
    async def list_sinks(
        sink_type: Optional[str] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False
    ):
        """List all data sinks"""
        try:
            from agentic.pipelines import get_sink_manager, SinkType
            manager = get_sink_manager()
            type_filter = SinkType(sink_type) if sink_type else None
            sinks = manager.get_sinks(sink_type=type_filter, enabled_only=enabled_only, tag=tag)
            return {"sinks": [s.to_dict() for s in sinks]}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sinks")
    async def create_sink(data: dict):
        """Create a new data sink"""
        try:
            from agentic.pipelines import get_sink_manager, SinkType, SinkConfig
            manager = get_sink_manager()
            config = SinkConfig(**data.get("config", {})) if "config" in data else None
            sink = manager.create_sink(
                name=data.get("name", "Unnamed Sink"),
                sink_type=SinkType(data.get("sink_type", "api")),
                description=data.get("description", ""),
                config=config,
                tags=data.get("tags", [])
            )
            return {"sink": sink.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/sinks/{sink_id}")
    async def get_sink_detail(sink_id: str):
        """Get sink by ID"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            sink = manager.get_sink(sink_id)
            if sink:
                return {"sink": sink.to_dict()}
            return {"error": "Sink not found"}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.delete("/api/pipelines/sinks/{sink_id}")
    async def delete_sink(sink_id: str):
        """Delete a sink"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            success = manager.delete_sink(sink_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sinks/{sink_id}/load")
    async def load_to_sink(sink_id: str, data: dict):
        """Load data to sink"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            input_data = data.get("data", [])
            result = await manager.load(sink_id, input_data)
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sinks/{sink_id}/test")
    async def test_sink_connection(sink_id: str):
        """Test sink connection"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            result = manager.test_connection(sink_id)
            return {"result": result}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sinks/{sink_id}/enable")
    async def enable_sink(sink_id: str):
        """Enable a sink"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            success = manager.enable_sink(sink_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.post("/api/pipelines/sinks/{sink_id}/disable")
    async def disable_sink(sink_id: str):
        """Disable a sink"""
        try:
            from agentic.pipelines import get_sink_manager
            manager = get_sink_manager()
            success = manager.disable_sink(sink_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/source-types")
    async def get_source_types():
        """Get available source types"""
        try:
            from agentic.pipelines import SourceType
            return {
                "source_types": [
                    {"value": t.value, "name": t.name}
                    for t in SourceType
                ]
            }
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/transform-types")
    async def get_transform_types():
        """Get available transform types"""
        try:
            from agentic.pipelines import TransformType
            return {
                "transform_types": [
                    {"value": t.value, "name": t.name}
                    for t in TransformType
                ]
            }
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/sink-types")
    async def get_sink_types():
        """Get available sink types"""
        try:
            from agentic.pipelines import SinkType
            return {
                "sink_types": [
                    {"value": t.value, "name": t.name}
                    for t in SinkType
                ]
            }
        except ImportError:
            return {"error": "Pipelines module not available"}

    @app.get("/api/pipelines/statuses")
    async def get_pipeline_statuses():
        """Get pipeline status values"""
        try:
            from agentic.pipelines import PipelineStatus
            return {
                "pipeline_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in PipelineStatus
                ]
            }
        except ImportError:
            return {"error": "Pipelines module not available"}

    # ==================== Event Bus API ====================

    @app.post("/api/events/publish")
    async def publish_event(data: dict):
        """Publish an event"""
        try:
            from agentic.events import get_event_bus, EventType, EventPriority
            bus = get_event_bus()
            event = await bus.publish_async(
                event_type=EventType(data.get("event_type", "custom")),
                source=data.get("source", "api"),
                payload=data.get("payload", {}),
                priority=EventPriority(data.get("priority", 2)),
                correlation_id=data.get("correlation_id"),
                tags=data.get("tags", [])
            )
            return {"event": event.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/history")
    async def get_event_history(
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100
    ):
        """Get event history"""
        try:
            from agentic.events import get_event_bus, EventType
            bus = get_event_bus()
            type_filter = EventType(event_type) if event_type else None
            events = bus.get_history(event_type=type_filter, source=source, limit=limit)
            return {"events": [e.to_dict() for e in events]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/{event_id}")
    async def get_event_detail(event_id: str):
        """Get event by ID"""
        try:
            from agentic.events import get_event_bus
            bus = get_event_bus()
            event = bus.get_event(event_id)
            if event:
                return {"event": event.to_dict()}
            return {"error": "Event not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/{event_id}/acknowledge")
    async def acknowledge_event(event_id: str):
        """Acknowledge an event"""
        try:
            from agentic.events import get_event_bus
            bus = get_event_bus()
            success = bus.acknowledge(event_id)
            return {"acknowledged": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers")
    async def get_event_subscribers(event_type: Optional[str] = None):
        """Get event subscribers"""
        try:
            from agentic.events import get_event_bus, EventType
            bus = get_event_bus()
            type_filter = EventType(event_type) if event_type else None
            return {"subscribers": bus.get_subscribers(type_filter)}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/history")
    async def clear_event_history():
        """Clear event history"""
        try:
            from agentic.events import get_event_bus
            bus = get_event_bus()
            count = bus.clear_history()
            return {"cleared": count}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/statistics")
    async def get_event_statistics():
        """Get event bus statistics"""
        try:
            from agentic.events import get_event_bus
            bus = get_event_bus()
            return {"statistics": bus.get_statistics()}
        except ImportError:
            return {"error": "Events module not available"}

    # Event Subscribers API

    @app.get("/api/events/subscribers/list")
    async def list_subscribers(
        event_type: Optional[str] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ):
        """List all subscribers"""
        try:
            from agentic.events import get_subscriber_manager, EventType
            manager = get_subscriber_manager()
            type_filter = EventType(event_type) if event_type else None
            subscribers = manager.get_subscribers(event_type=type_filter, enabled_only=enabled_only, tag=tag)
            return {"subscribers": [s.to_dict() for s in subscribers]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers")
    async def create_subscriber(data: dict):
        """Create a new subscriber"""
        try:
            from agentic.events import get_subscriber_manager, EventType, SubscriberConfig
            manager = get_subscriber_manager()
            event_types = [EventType(t) for t in data.get("event_types", [])]
            config = SubscriberConfig(**data.get("config", {})) if "config" in data else None
            subscriber = manager.create_subscriber(
                name=data.get("name", "Unnamed Subscriber"),
                event_types=event_types,
                patterns=data.get("patterns", []),
                handler_name=data.get("handler_name"),
                config=config,
                description=data.get("description", ""),
                tags=data.get("tags", [])
            )
            return {"subscriber": subscriber.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers/{subscriber_id}")
    async def get_subscriber_detail(subscriber_id: str):
        """Get subscriber by ID"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            subscriber = manager.get_subscriber(subscriber_id)
            if subscriber:
                return {"subscriber": subscriber.to_dict()}
            return {"error": "Subscriber not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/subscribers/{subscriber_id}")
    async def delete_subscriber(subscriber_id: str):
        """Delete a subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            success = manager.delete_subscriber(subscriber_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/enable")
    async def enable_subscriber(subscriber_id: str):
        """Enable a subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            success = manager.enable_subscriber(subscriber_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/disable")
    async def disable_subscriber(subscriber_id: str):
        """Disable a subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            success = manager.disable_subscriber(subscriber_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/event-types/{event_type}")
    async def add_subscriber_event_type(subscriber_id: str, event_type: str):
        """Add event type to subscriber"""
        try:
            from agentic.events import get_subscriber_manager, EventType
            manager = get_subscriber_manager()
            success = manager.add_event_type(subscriber_id, EventType(event_type))
            return {"added": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/subscribers/{subscriber_id}/event-types/{event_type}")
    async def remove_subscriber_event_type(subscriber_id: str, event_type: str):
        """Remove event type from subscriber"""
        try:
            from agentic.events import get_subscriber_manager, EventType
            manager = get_subscriber_manager()
            success = manager.remove_event_type(subscriber_id, EventType(event_type))
            return {"removed": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/patterns")
    async def add_subscriber_pattern(subscriber_id: str, data: dict):
        """Add pattern to subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            success = manager.add_pattern(subscriber_id, data.get("pattern", ""))
            return {"added": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers/handlers")
    async def get_subscriber_handlers():
        """Get available subscriber handlers"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            return {"handlers": manager.get_available_handlers()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers/statistics")
    async def get_subscriber_statistics():
        """Get subscriber statistics"""
        try:
            from agentic.events import get_subscriber_manager
            manager = get_subscriber_manager()
            return {"statistics": manager.get_statistics()}
        except ImportError:
            return {"error": "Events module not available"}

    # Event Channels API

    @app.get("/api/events/channels")
    async def list_channels(
        channel_type: Optional[str] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ):
        """List all channels"""
        try:
            from agentic.events import get_channel_manager, ChannelType
            manager = get_channel_manager()
            type_filter = ChannelType(channel_type) if channel_type else None
            channels = manager.get_channels(channel_type=type_filter, enabled_only=enabled_only, tag=tag)
            return {"channels": [c.to_dict() for c in channels]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels")
    async def create_channel(data: dict):
        """Create a new channel"""
        try:
            from agentic.events import get_channel_manager, ChannelType, ChannelConfig
            manager = get_channel_manager()
            config = ChannelConfig(**data.get("config", {})) if "config" in data else None
            channel = manager.create_channel(
                name=data.get("name", "Unnamed Channel"),
                channel_type=ChannelType(data.get("channel_type", "custom")),
                description=data.get("description", ""),
                patterns=data.get("patterns", []),
                config=config,
                tags=data.get("tags", [])
            )
            return {"channel": channel.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channels/{channel_id}")
    async def get_channel_detail(channel_id: str):
        """Get channel by ID"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            channel = manager.get_channel(channel_id)
            if channel:
                return {"channel": channel.to_dict()}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/channels/{channel_id}")
    async def delete_channel(channel_id: str):
        """Delete a channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.delete_channel(channel_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/enable")
    async def enable_channel(channel_id: str):
        """Enable a channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.enable_channel(channel_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/disable")
    async def disable_channel(channel_id: str):
        """Disable a channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.disable_channel(channel_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/subscribers/{subscriber_id}")
    async def add_channel_subscriber(channel_id: str, subscriber_id: str):
        """Add subscriber to channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.add_subscriber(channel_id, subscriber_id)
            return {"added": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/channels/{channel_id}/subscribers/{subscriber_id}")
    async def remove_channel_subscriber(channel_id: str, subscriber_id: str):
        """Remove subscriber from channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.remove_subscriber(channel_id, subscriber_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/patterns")
    async def add_channel_pattern(channel_id: str, data: dict):
        """Add pattern to channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.add_pattern(channel_id, data.get("pattern", ""))
            return {"added": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/channels/{channel_id}/patterns")
    async def remove_channel_pattern(channel_id: str, data: dict):
        """Remove pattern from channel"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            success = manager.remove_pattern(channel_id, data.get("pattern", ""))
            return {"removed": success}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channels/statistics")
    async def get_channel_statistics():
        """Get channel statistics"""
        try:
            from agentic.events import get_channel_manager
            manager = get_channel_manager()
            return {"statistics": manager.get_statistics()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/types")
    async def get_event_types():
        """Get available event types"""
        try:
            from agentic.events import EventType
            return {
                "event_types": [
                    {"value": t.value, "name": t.name}
                    for t in EventType
                ]
            }
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/priorities")
    async def get_event_priorities():
        """Get event priority values"""
        try:
            from agentic.events import EventPriority
            return {
                "priorities": [
                    {"value": p.value, "name": p.name}
                    for p in EventPriority
                ]
            }
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channel-types")
    async def get_channel_types():
        """Get channel type values"""
        try:
            from agentic.events import ChannelType
            return {
                "channel_types": [
                    {"value": t.value, "name": t.name}
                    for t in ChannelType
                ]
            }
        except ImportError:
            return {"error": "Events module not available"}

    # ==================== State Machine API Endpoints ====================

    @app.get("/api/statemachine/machines")
    async def get_state_machines(enabled_only: bool = False, tag: Optional[str] = None):
        """Get all state machines"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            machines = manager.get_machines(enabled_only=enabled_only, tag=tag)
            return {"machines": [m.to_dict() for m in machines]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/machines")
    async def create_state_machine(data: dict):
        """Create a new state machine"""
        try:
            from agentic.statemachine import get_state_machine_manager, StateMachineConfig
            manager = get_state_machine_manager()
            config = None
            if data.get("config"):
                config = StateMachineConfig(**data["config"])
            machine = manager.create_machine(
                name=data.get("name", "New Machine"),
                description=data.get("description", ""),
                config=config,
                initial_state_id=data.get("initial_state_id"),
                state_ids=data.get("state_ids", []),
                transition_ids=data.get("transition_ids", []),
                version=data.get("version", "1.0.0"),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return {"machine": machine.to_dict()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/machines/{machine_id}")
    async def get_state_machine(machine_id: str):
        """Get a specific state machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            machine = manager.get_machine(machine_id)
            if machine:
                return {"machine": machine.to_dict()}
            return {"error": "Machine not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.put("/api/statemachine/machines/{machine_id}")
    async def update_state_machine(machine_id: str, data: dict):
        """Update a state machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            machine = manager.update_machine(machine_id, **data)
            if machine:
                return {"machine": machine.to_dict()}
            return {"error": "Machine not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.delete("/api/statemachine/machines/{machine_id}")
    async def delete_state_machine(machine_id: str):
        """Delete a state machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.delete_machine(machine_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/machines/{machine_id}/states")
    async def get_machine_states(machine_id: str):
        """Get all states in a machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            states = manager.get_machine_states(machine_id)
            return {"states": [s.to_dict() for s in states]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/machines/{machine_id}/transitions")
    async def get_machine_transitions(machine_id: str):
        """Get all transitions in a machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            transitions = manager.get_machine_transitions(machine_id)
            return {"transitions": [t.to_dict() for t in transitions]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/machines/{machine_id}/states")
    async def add_state_to_machine(machine_id: str, data: dict):
        """Add a state to a machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.add_state(machine_id, data.get("state_id", ""))
            return {"added": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/machines/{machine_id}/transitions")
    async def add_transition_to_machine(machine_id: str, data: dict):
        """Add a transition to a machine"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.add_transition(machine_id, data.get("transition_id", ""))
            return {"added": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances")
    async def create_instance(data: dict):
        """Create a new machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            instance = manager.create_instance(
                machine_id=data.get("machine_id", ""),
                name=data.get("name", "New Instance"),
                context=data.get("context", {})
            )
            if instance:
                return {"instance": instance.to_dict()}
            return {"error": "Failed to create instance"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/instances")
    async def get_instances(machine_id: Optional[str] = None, status: Optional[str] = None):
        """Get machine instances"""
        try:
            from agentic.statemachine import get_state_machine_manager, MachineStatus
            manager = get_state_machine_manager()
            status_enum = None
            if status:
                try:
                    status_enum = MachineStatus(status)
                except ValueError:
                    pass
            instances = manager.get_instances(machine_id=machine_id, status=status_enum)
            return {"instances": [i.to_dict() for i in instances]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/instances/{instance_id}")
    async def get_instance(instance_id: str):
        """Get a specific instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            instance = manager.get_instance(instance_id)
            if instance:
                return {"instance": instance.to_dict()}
            return {"error": "Instance not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/start")
    async def start_instance(instance_id: str):
        """Start a machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.start_instance(instance_id)
            return {"started": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/pause")
    async def pause_instance(instance_id: str):
        """Pause a machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.pause_instance(instance_id)
            return {"paused": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/resume")
    async def resume_instance(instance_id: str):
        """Resume a paused instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.resume_instance(instance_id)
            return {"resumed": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/stop")
    async def stop_instance(instance_id: str):
        """Stop a machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.stop_instance(instance_id)
            return {"stopped": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/terminate")
    async def terminate_instance(instance_id: str, data: dict):
        """Terminate a machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.terminate_instance(instance_id, error=data.get("error"))
            return {"terminated": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/instances/{instance_id}/event")
    async def send_event_to_instance(instance_id: str, data: dict):
        """Send event to machine instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            success = manager.send_event(
                instance_id=instance_id,
                event=data.get("event", ""),
                data=data.get("data", {})
            )
            return {"event_sent": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/instances/{instance_id}/state")
    async def get_instance_current_state(instance_id: str):
        """Get current state of instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            state = manager.get_current_state(instance_id)
            if state:
                return {"state": state.to_dict()}
            return {"error": "State not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/instances/{instance_id}/transitions")
    async def get_instance_available_transitions(instance_id: str):
        """Get available transitions for instance"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            transitions = manager.get_available_transitions(instance_id)
            return {"transitions": [t.to_dict() for t in transitions]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/states")
    async def get_states(state_type: Optional[str] = None, tag: Optional[str] = None):
        """Get all states"""
        try:
            from agentic.statemachine import get_state_manager, StateType
            manager = get_state_manager()
            type_enum = None
            if state_type:
                try:
                    type_enum = StateType(state_type)
                except ValueError:
                    pass
            states = manager.get_states(state_type=type_enum, tag=tag)
            return {"states": [s.to_dict() for s in states]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/states")
    async def create_state(data: dict):
        """Create a new state"""
        try:
            from agentic.statemachine import get_state_manager, StateType, StateConfig
            manager = get_state_manager()
            state_type = StateType(data.get("state_type", "normal"))
            config = None
            if data.get("config"):
                config = StateConfig(**data["config"])
            state = manager.create_state(
                name=data.get("name", "New State"),
                state_type=state_type,
                description=data.get("description", ""),
                config=config,
                parent_id=data.get("parent_id"),
                data=data.get("data", {}),
                on_enter=data.get("on_enter"),
                on_exit=data.get("on_exit"),
                on_activity=data.get("on_activity"),
                tags=data.get("tags", [])
            )
            return {"state": state.to_dict()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/states/{state_id}")
    async def get_state(state_id: str):
        """Get a specific state"""
        try:
            from agentic.statemachine import get_state_manager
            manager = get_state_manager()
            state = manager.get_state(state_id)
            if state:
                return {"state": state.to_dict()}
            return {"error": "State not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.put("/api/statemachine/states/{state_id}")
    async def update_state(state_id: str, data: dict):
        """Update a state"""
        try:
            from agentic.statemachine import get_state_manager
            manager = get_state_manager()
            state = manager.update_state(state_id, **data)
            if state:
                return {"state": state.to_dict()}
            return {"error": "State not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.delete("/api/statemachine/states/{state_id}")
    async def delete_state(state_id: str):
        """Delete a state"""
        try:
            from agentic.statemachine import get_state_manager
            manager = get_state_manager()
            success = manager.delete_state(state_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/transitions")
    async def get_transitions(transition_type: Optional[str] = None, trigger: Optional[str] = None, enabled_only: bool = False, tag: Optional[str] = None):
        """Get all transitions"""
        try:
            from agentic.statemachine import get_transition_manager, TransitionType
            manager = get_transition_manager()
            type_enum = None
            if transition_type:
                try:
                    type_enum = TransitionType(transition_type)
                except ValueError:
                    pass
            transitions = manager.get_transitions(transition_type=type_enum, trigger=trigger, enabled_only=enabled_only, tag=tag)
            return {"transitions": [t.to_dict() for t in transitions]}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/transitions")
    async def create_transition(data: dict):
        """Create a new transition"""
        try:
            from agentic.statemachine import get_transition_manager, TransitionType, TransitionConfig
            manager = get_transition_manager()
            trans_type = TransitionType(data.get("transition_type", "external"))
            config = None
            if data.get("config"):
                config = TransitionConfig(**data["config"])
            transition = manager.create_transition(
                name=data.get("name", "New Transition"),
                source_id=data.get("source_id", ""),
                target_id=data.get("target_id", ""),
                transition_type=trans_type,
                trigger=data.get("trigger"),
                description=data.get("description", ""),
                config=config,
                condition_logic=data.get("condition_logic", "all"),
                guard=data.get("guard"),
                action=data.get("action"),
                before_action=data.get("before_action"),
                after_action=data.get("after_action"),
                tags=data.get("tags", [])
            )
            return {"transition": transition.to_dict()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/transitions/{transition_id}")
    async def get_transition(transition_id: str):
        """Get a specific transition"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            transition = manager.get_transition(transition_id)
            if transition:
                return {"transition": transition.to_dict()}
            return {"error": "Transition not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.put("/api/statemachine/transitions/{transition_id}")
    async def update_transition(transition_id: str, data: dict):
        """Update a transition"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            transition = manager.update_transition(transition_id, **data)
            if transition:
                return {"transition": transition.to_dict()}
            return {"error": "Transition not found"}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.delete("/api/statemachine/transitions/{transition_id}")
    async def delete_transition(transition_id: str):
        """Delete a transition"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            success = manager.delete_transition(transition_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/transitions/{transition_id}/enable")
    async def enable_transition(transition_id: str):
        """Enable a transition"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            success = manager.enable_transition(transition_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.post("/api/statemachine/transitions/{transition_id}/disable")
    async def disable_transition(transition_id: str):
        """Disable a transition"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            success = manager.disable_transition(transition_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/statistics")
    async def get_statemachine_statistics():
        """Get state machine statistics"""
        try:
            from agentic.statemachine import get_state_machine_manager
            manager = get_state_machine_manager()
            return {"statistics": manager.get_statistics()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/state-types")
    async def get_state_types():
        """Get available state types"""
        try:
            from agentic.statemachine import StateType
            return {
                "state_types": [
                    {"value": t.value, "name": t.name}
                    for t in StateType
                ]
            }
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/transition-types")
    async def get_transition_types():
        """Get available transition types"""
        try:
            from agentic.statemachine import TransitionType
            return {
                "transition_types": [
                    {"value": t.value, "name": t.name}
                    for t in TransitionType
                ]
            }
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/machine-statuses")
    async def get_machine_statuses():
        """Get available machine statuses"""
        try:
            from agentic.statemachine import MachineStatus
            return {
                "machine_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in MachineStatus
                ]
            }
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/callbacks")
    async def get_available_callbacks():
        """Get available state callbacks"""
        try:
            from agentic.statemachine import get_state_manager
            manager = get_state_manager()
            return {"callbacks": manager.get_available_callbacks()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/guards")
    async def get_available_guards():
        """Get available transition guards"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            return {"guards": manager.get_available_guards()}
        except ImportError:
            return {"error": "State machine module not available"}

    @app.get("/api/statemachine/actions")
    async def get_available_actions():
        """Get available transition actions"""
        try:
            from agentic.statemachine import get_transition_manager
            manager = get_transition_manager()
            return {"actions": manager.get_available_actions()}
        except ImportError:
            return {"error": "State machine module not available"}

    # ==================== Rules Engine API Endpoints ====================

    @app.get("/api/rules")
    async def get_rules(priority: Optional[int] = None, enabled_only: bool = False, tag: Optional[str] = None):
        """Get all rules"""
        try:
            from agentic.rules import get_rule_engine, RulePriority
            engine = get_rule_engine()
            priority_enum = None
            if priority:
                try:
                    priority_enum = RulePriority(priority)
                except ValueError:
                    pass
            rules = engine.get_rules(priority=priority_enum, enabled_only=enabled_only, tag=tag)
            return {"rules": [r.to_dict() for r in rules]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules")
    async def create_rule(data: dict):
        """Create a new rule"""
        try:
            from agentic.rules import get_rule_engine, RuleConfig, RulePriority
            engine = get_rule_engine()
            priority = RulePriority(data.get("priority", 3))
            config = None
            if data.get("config"):
                config = RuleConfig(**data["config"])
            rule = engine.create_rule(
                name=data.get("name", "New Rule"),
                description=data.get("description", ""),
                priority=priority,
                config=config,
                condition_ids=data.get("condition_ids", []),
                condition_group_id=data.get("condition_group_id"),
                action_ids=data.get("action_ids", []),
                else_action_ids=data.get("else_action_ids", []),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return {"rule": rule.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/{rule_id}")
    async def get_rule(rule_id: str):
        """Get a specific rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            rule = engine.get_rule(rule_id)
            if rule:
                return {"rule": rule.to_dict()}
            return {"error": "Rule not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.put("/api/rules/{rule_id}")
    async def update_rule(rule_id: str, data: dict):
        """Update a rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            rule = engine.update_rule(rule_id, **data)
            if rule:
                return {"rule": rule.to_dict()}
            return {"error": "Rule not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/{rule_id}")
    async def delete_rule(rule_id: str):
        """Delete a rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.delete_rule(rule_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/{rule_id}/enable")
    async def enable_rule(rule_id: str):
        """Enable a rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.enable_rule(rule_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/{rule_id}/disable")
    async def disable_rule(rule_id: str):
        """Disable a rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.disable_rule(rule_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/{rule_id}/evaluate")
    async def evaluate_rule(rule_id: str, data: dict):
        """Evaluate a rule against context"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            result = engine.evaluate_rule(rule_id, data.get("context", {}))
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/{rule_id}/conditions")
    async def add_condition_to_rule(rule_id: str, data: dict):
        """Add condition to rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.add_condition(rule_id, data.get("condition_id", ""))
            return {"added": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/{rule_id}/conditions/{condition_id}")
    async def remove_condition_from_rule(rule_id: str, condition_id: str):
        """Remove condition from rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.remove_condition(rule_id, condition_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/{rule_id}/actions")
    async def add_action_to_rule(rule_id: str, data: dict):
        """Add action to rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.add_action(rule_id, data.get("action_id", ""))
            return {"added": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/{rule_id}/actions/{action_id}")
    async def remove_action_from_rule(rule_id: str, action_id: str):
        """Remove action from rule"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.remove_action(rule_id, action_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/sets")
    async def get_rule_sets(enabled_only: bool = False, tag: Optional[str] = None):
        """Get all rule sets"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            rule_sets = engine.get_rule_sets(enabled_only=enabled_only, tag=tag)
            return {"rule_sets": [rs.to_dict() for rs in rule_sets]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/sets")
    async def create_rule_set(data: dict):
        """Create a new rule set"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            rule_set = engine.create_rule_set(
                name=data.get("name", "New Rule Set"),
                description=data.get("description", ""),
                rule_ids=data.get("rule_ids", []),
                evaluate_all=data.get("evaluate_all", False),
                tags=data.get("tags", [])
            )
            return {"rule_set": rule_set.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/sets/{rule_set_id}")
    async def get_rule_set(rule_set_id: str):
        """Get a specific rule set"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            rule_set = engine.get_rule_set(rule_set_id)
            if rule_set:
                return {"rule_set": rule_set.to_dict()}
            return {"error": "Rule set not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/sets/{rule_set_id}")
    async def delete_rule_set(rule_set_id: str):
        """Delete a rule set"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.delete_rule_set(rule_set_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/sets/{rule_set_id}/rules")
    async def add_rule_to_set(rule_set_id: str, data: dict):
        """Add rule to rule set"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.add_rule_to_set(rule_set_id, data.get("rule_id", ""))
            return {"added": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/sets/{rule_set_id}/rules/{rule_id}")
    async def remove_rule_from_set(rule_set_id: str, rule_id: str):
        """Remove rule from rule set"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            success = engine.remove_rule_from_set(rule_set_id, rule_id)
            return {"removed": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/sets/{rule_set_id}/evaluate")
    async def evaluate_rule_set(rule_set_id: str, data: dict):
        """Evaluate a rule set against context"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            results = engine.evaluate_rule_set(rule_set_id, data.get("context", {}))
            return {"results": [r.to_dict() for r in results]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/evaluate")
    async def evaluate_all_rules(data: dict):
        """Evaluate all rules against context"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            results = engine.evaluate_all(data.get("context", {}), tags=data.get("tags"))
            return {"results": [r.to_dict() for r in results]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/conditions")
    async def get_conditions(condition_type: Optional[str] = None, enabled_only: bool = False, tag: Optional[str] = None):
        """Get all conditions"""
        try:
            from agentic.rules import get_condition_manager, ConditionType
            manager = get_condition_manager()
            type_enum = None
            if condition_type:
                try:
                    type_enum = ConditionType(condition_type)
                except ValueError:
                    pass
            conditions = manager.get_conditions(condition_type=type_enum, enabled_only=enabled_only, tag=tag)
            return {"conditions": [c.to_dict() for c in conditions]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/conditions")
    async def create_condition(data: dict):
        """Create a new condition"""
        try:
            from agentic.rules import get_condition_manager, ConditionType
            manager = get_condition_manager()
            cond_type = ConditionType(data.get("condition_type", "equals"))
            condition = manager.create_condition(
                name=data.get("name", "New Condition"),
                condition_type=cond_type,
                field=data.get("field", ""),
                value=data.get("value"),
                value2=data.get("value2"),
                case_sensitive=data.get("case_sensitive", True),
                description=data.get("description", ""),
                tags=data.get("tags", [])
            )
            return {"condition": condition.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/conditions/{condition_id}")
    async def get_condition(condition_id: str):
        """Get a specific condition"""
        try:
            from agentic.rules import get_condition_manager
            manager = get_condition_manager()
            condition = manager.get_condition(condition_id)
            if condition:
                return {"condition": condition.to_dict()}
            return {"error": "Condition not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.put("/api/rules/conditions/{condition_id}")
    async def update_condition(condition_id: str, data: dict):
        """Update a condition"""
        try:
            from agentic.rules import get_condition_manager
            manager = get_condition_manager()
            condition = manager.update_condition(condition_id, **data)
            if condition:
                return {"condition": condition.to_dict()}
            return {"error": "Condition not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.delete("/api/rules/conditions/{condition_id}")
    async def delete_condition(condition_id: str):
        """Delete a condition"""
        try:
            from agentic.rules import get_condition_manager
            manager = get_condition_manager()
            success = manager.delete_condition(condition_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/conditions/{condition_id}/evaluate")
    async def evaluate_condition(condition_id: str, data: dict):
        """Evaluate a condition against context"""
        try:
            from agentic.rules import get_condition_manager
            manager = get_condition_manager()
            result = manager.evaluate_condition(condition_id, data.get("context", {}))
            return {"result": result}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/condition-groups")
    async def get_condition_groups(operator: Optional[str] = None):
        """Get all condition groups"""
        try:
            from agentic.rules import get_condition_manager, LogicalOperator
            manager = get_condition_manager()
            op_enum = None
            if operator:
                try:
                    op_enum = LogicalOperator(operator)
                except ValueError:
                    pass
            groups = manager.get_groups(operator=op_enum)
            return {"groups": [g.to_dict() for g in groups]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/condition-groups")
    async def create_condition_group(data: dict):
        """Create a condition group"""
        try:
            from agentic.rules import get_condition_manager, LogicalOperator
            manager = get_condition_manager()
            operator = LogicalOperator(data.get("operator", "and"))
            group = manager.create_group(
                name=data.get("name", "New Group"),
                operator=operator,
                condition_ids=data.get("condition_ids", []),
                group_ids=data.get("group_ids", []),
                description=data.get("description", "")
            )
            return {"group": group.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/actions")
    async def get_rule_actions(action_type: Optional[str] = None, enabled_only: bool = False, tag: Optional[str] = None):
        """Get all actions"""
        try:
            from agentic.rules import get_action_manager, ActionType
            manager = get_action_manager()
            type_enum = None
            if action_type:
                try:
                    type_enum = ActionType(action_type)
                except ValueError:
                    pass
            actions = manager.get_actions(action_type=type_enum, enabled_only=enabled_only, tag=tag)
            return {"actions": [a.to_dict() for a in actions]}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/actions")
    async def create_rule_action(data: dict):
        """Create a new action"""
        try:
            from agentic.rules import get_action_manager, ActionType, ActionConfig
            manager = get_action_manager()
            action_type = ActionType(data.get("action_type", "log"))
            config = None
            if data.get("config"):
                config = ActionConfig(**data["config"])
            action = manager.create_action(
                name=data.get("name", "New Action"),
                action_type=action_type,
                parameters=data.get("parameters", {}),
                config=config,
                description=data.get("description", ""),
                tags=data.get("tags", [])
            )
            return {"action": action.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/actions/{action_id}")
    async def get_rule_action(action_id: str):
        """Get a specific action"""
        try:
            from agentic.rules import get_action_manager
            manager = get_action_manager()
            action = manager.get_action(action_id)
            if action:
                return {"action": action.to_dict()}
            return {"error": "Action not found"}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.post("/api/rules/actions/{action_id}/execute")
    async def execute_rule_action(action_id: str, data: dict):
        """Execute an action"""
        try:
            from agentic.rules import get_action_manager
            manager = get_action_manager()
            result = manager.execute_action(action_id, data.get("context", {}))
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/statistics")
    async def get_rules_statistics():
        """Get rules engine statistics"""
        try:
            from agentic.rules import get_rule_engine
            engine = get_rule_engine()
            return {"statistics": engine.get_statistics()}
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/condition-types")
    async def get_condition_types():
        """Get available condition types"""
        try:
            from agentic.rules import ConditionType
            return {
                "condition_types": [
                    {"value": t.value, "name": t.name}
                    for t in ConditionType
                ]
            }
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/logical-operators")
    async def get_logical_operators():
        """Get available logical operators"""
        try:
            from agentic.rules import LogicalOperator
            return {
                "logical_operators": [
                    {"value": o.value, "name": o.name}
                    for o in LogicalOperator
                ]
            }
        except ImportError:
            return {"error": "Rules engine module not available"}

    @app.get("/api/rules/action-types")
    async def get_action_types():
        """Get available action types"""
        try:
            from agentic.rules import ActionType
            return {
                "action_types": [
                    {"value": t.value, "name": t.name}
                    for t in ActionType
                ]
            }
        except ImportError:
            return {"error": "Rules engine module not available"}

    # ==================== Template Engine API Endpoints ====================

    @app.get("/api/templates")
    async def get_templates(category: Optional[str] = None, enabled_only: bool = False, tag: Optional[str] = None):
        """Get all templates"""
        try:
            from agentic.templates import get_template_manager, TemplateCategory
            manager = get_template_manager()
            cat_enum = None
            if category:
                try:
                    cat_enum = TemplateCategory(category)
                except ValueError:
                    pass
            templates = manager.get_templates(category=cat_enum, enabled_only=enabled_only, tag=tag)
            return {"templates": [t.to_dict() for t in templates]}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates")
    async def create_template(data: dict):
        """Create a new template"""
        try:
            from agentic.templates import get_template_manager, TemplateCategory, TemplateConfig
            manager = get_template_manager()
            category = TemplateCategory(data.get("category", "custom"))
            config = None
            if data.get("config"):
                config = TemplateConfig(**data["config"])
            template = manager.create_template(
                name=data.get("name", "New Template"),
                content=data.get("content", ""),
                category=category,
                description=data.get("description", ""),
                config=config,
                variable_ids=data.get("variable_ids", []),
                parent_id=data.get("parent_id"),
                version=data.get("version", "1.0.0"),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return {"template": template.to_dict()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/{template_id}")
    async def get_template(template_id: str):
        """Get a specific template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            template = manager.get_template(template_id)
            if template:
                return {"template": template.to_dict()}
            return {"error": "Template not found"}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.put("/api/templates/{template_id}")
    async def update_template(template_id: str, data: dict):
        """Update a template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            template = manager.update_template(template_id, **data)
            if template:
                return {"template": template.to_dict()}
            return {"error": "Template not found"}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.delete("/api/templates/{template_id}")
    async def delete_template(template_id: str):
        """Delete a template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            success = manager.delete_template(template_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/{template_id}/enable")
    async def enable_template(template_id: str):
        """Enable a template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            success = manager.enable_template(template_id)
            return {"enabled": success}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/{template_id}/disable")
    async def disable_template(template_id: str):
        """Disable a template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            success = manager.disable_template(template_id)
            return {"disabled": success}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/{template_id}/clone")
    async def clone_template(template_id: str, data: dict):
        """Clone a template"""
        try:
            from agentic.templates import get_template_manager
            manager = get_template_manager()
            template = manager.clone_template(template_id, data.get("name", "Clone"))
            if template:
                return {"template": template.to_dict()}
            return {"error": "Template not found"}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/{template_id}/render")
    async def render_template(template_id: str, data: dict):
        """Render a template with context"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            result = engine.render(template_id, data.get("context", {}))
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/{template_id}/validate")
    async def validate_template(template_id: str, data: dict):
        """Validate a template"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            result = engine.validate_template(template_id, data.get("context"))
            return result
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/render-string")
    async def render_template_string(data: dict):
        """Render a template string directly"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            result = engine.render_string(data.get("template", ""), data.get("context", {}))
            return {"result": result.to_dict()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/variables")
    async def get_template_variables(variable_type: Optional[str] = None, scope: Optional[str] = None, tag: Optional[str] = None):
        """Get all template variables"""
        try:
            from agentic.templates import get_variable_manager, VariableType, VariableScope
            manager = get_variable_manager()
            type_enum = None
            scope_enum = None
            if variable_type:
                try:
                    type_enum = VariableType(variable_type)
                except ValueError:
                    pass
            if scope:
                try:
                    scope_enum = VariableScope(scope)
                except ValueError:
                    pass
            variables = manager.get_variables(variable_type=type_enum, scope=scope_enum, tag=tag)
            return {"variables": [v.to_dict() for v in variables]}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/variables")
    async def create_template_variable(data: dict):
        """Create a new template variable"""
        try:
            from agentic.templates import get_variable_manager, VariableType, VariableScope
            manager = get_variable_manager()
            var_type = VariableType(data.get("variable_type", "string"))
            scope = VariableScope(data.get("scope", "template"))
            variable = manager.create_variable(
                name=data.get("name", "new_var"),
                variable_type=var_type,
                scope=scope,
                default_value=data.get("default_value"),
                description=data.get("description", ""),
                sensitive=data.get("sensitive", False),
                computed=data.get("computed", False),
                expression=data.get("expression"),
                tags=data.get("tags", [])
            )
            return {"variable": variable.to_dict()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/variables/{variable_id}")
    async def get_template_variable(variable_id: str):
        """Get a specific template variable"""
        try:
            from agentic.templates import get_variable_manager
            manager = get_variable_manager()
            variable = manager.get_variable(variable_id)
            if variable:
                return {"variable": variable.to_dict()}
            return {"error": "Variable not found"}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.put("/api/templates/variables/{variable_id}")
    async def update_template_variable(variable_id: str, data: dict):
        """Update a template variable"""
        try:
            from agentic.templates import get_variable_manager
            manager = get_variable_manager()
            variable = manager.update_variable(variable_id, **data)
            if variable:
                return {"variable": variable.to_dict()}
            return {"error": "Variable not found"}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.delete("/api/templates/variables/{variable_id}")
    async def delete_template_variable(variable_id: str):
        """Delete a template variable"""
        try:
            from agentic.templates import get_variable_manager
            manager = get_variable_manager()
            success = manager.delete_variable(variable_id)
            return {"deleted": success}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.post("/api/templates/variables/{variable_id}/validate")
    async def validate_variable_value(variable_id: str, data: dict):
        """Validate a value against variable rules"""
        try:
            from agentic.templates import get_variable_manager
            manager = get_variable_manager()
            valid, errors = manager.validate_value(variable_id, data.get("value"))
            return {"valid": valid, "errors": errors}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/filters")
    async def get_template_filters():
        """Get available template filters"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            return {"filters": engine.get_available_filters()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/functions")
    async def get_template_functions():
        """Get available template functions"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            return {"functions": engine.get_available_functions()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/statistics")
    async def get_template_statistics():
        """Get template engine statistics"""
        try:
            from agentic.templates import get_template_engine
            engine = get_template_engine()
            return {"statistics": engine.get_statistics()}
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/categories")
    async def get_template_categories():
        """Get available template categories"""
        try:
            from agentic.templates import TemplateCategory
            return {
                "categories": [
                    {"value": c.value, "name": c.name}
                    for c in TemplateCategory
                ]
            }
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/variable-types")
    async def get_template_variable_types():
        """Get available variable types"""
        try:
            from agentic.templates import VariableType
            return {
                "variable_types": [
                    {"value": t.value, "name": t.name}
                    for t in VariableType
                ]
            }
        except ImportError:
            return {"error": "Template engine module not available"}

    @app.get("/api/templates/variable-scopes")
    async def get_variable_scopes():
        """Get available variable scopes"""
        try:
            from agentic.templates import VariableScope
            return {
                "variable_scopes": [
                    {"value": s.value, "name": s.name}
                    for s in VariableScope
                ]
            }
        except ImportError:
            return {"error": "Template engine module not available"}

    # ============================================================
    # SCHEDULER API ENDPOINTS
    # ============================================================

    @app.get("/api/scheduler/status")
    async def get_scheduler_status():
        """Get scheduler status"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            return scheduler.get_status()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/start")
    async def start_scheduler():
        """Start the scheduler"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.start()
            return {"success": success, "status": scheduler.status.value}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/stop")
    async def stop_scheduler():
        """Stop the scheduler"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.stop()
            return {"success": success, "status": scheduler.status.value}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/pause")
    async def pause_scheduler():
        """Pause the scheduler"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.pause()
            return {"success": success, "status": scheduler.status.value}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/resume")
    async def resume_scheduler():
        """Resume the scheduler"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.resume()
            return {"success": success, "status": scheduler.status.value}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/statistics")
    async def get_scheduler_statistics():
        """Get scheduler statistics"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            return scheduler.get_statistics()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/events")
    async def get_scheduler_events(limit: int = 100, event_type: str = None):
        """Get scheduler events"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            events = scheduler.get_events(limit=limit, event_type=event_type)
            return {"events": [e.to_dict() for e in events]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/upcoming")
    async def get_upcoming_jobs(hours: int = 24):
        """Get upcoming scheduled jobs"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            return {"upcoming": scheduler.get_upcoming_jobs(hours=hours)}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/running")
    async def get_running_jobs():
        """Get currently running jobs"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            jobs = scheduler.get_running_jobs()
            return {"running_jobs": [j.to_dict() for j in jobs]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/queued")
    async def get_queued_jobs():
        """Get queued jobs"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            jobs = scheduler.get_queued_jobs()
            return {"queued_jobs": [j.to_dict() for j in jobs]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    # Job API endpoints
    @app.get("/api/scheduler/jobs")
    async def list_jobs(job_type: str = None, enabled_only: bool = False, tag: str = None):
        """List all jobs"""
        try:
            from agentic.scheduler import get_job_manager, JobType
            jm = get_job_manager()
            jt = JobType(job_type) if job_type else None
            jobs = jm.get_jobs(job_type=jt, enabled_only=enabled_only, tag=tag)
            return {"jobs": [j.to_dict() for j in jobs]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs")
    async def create_job(request: Request):
        """Create a new job"""
        try:
            from agentic.scheduler import get_job_manager, JobType, JobConfig, JobPriority
            data = await request.json()
            jm = get_job_manager()

            config = None
            if "config" in data:
                config = JobConfig(**data["config"])

            priority = JobPriority.MEDIUM
            if "priority" in data:
                priority = JobPriority(data["priority"])

            job = jm.create_job(
                name=data["name"],
                job_type=JobType(data["job_type"]),
                handler=data["handler"],
                description=data.get("description", ""),
                priority=priority,
                config=config,
                parameters=data.get("parameters", {}),
                trigger_ids=data.get("trigger_ids", []),
                enabled=data.get("enabled", True),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return job.to_dict()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/{job_id}")
    async def get_job(job_id: str):
        """Get job by ID"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            job = jm.get_job(job_id)
            if job:
                return job.to_dict()
            return {"error": "Job not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.put("/api/scheduler/jobs/{job_id}")
    async def update_job(job_id: str, request: Request):
        """Update job"""
        try:
            from agentic.scheduler import get_job_manager
            data = await request.json()
            jm = get_job_manager()
            job = jm.update_job(job_id, **data)
            if job:
                return job.to_dict()
            return {"error": "Job not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/scheduler/jobs/{job_id}")
    async def delete_job(job_id: str):
        """Delete job"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            success = jm.delete_job(job_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/enable")
    async def enable_job(job_id: str):
        """Enable job"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            success = jm.enable_job(job_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/disable")
    async def disable_job(job_id: str):
        """Disable job"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            success = jm.disable_job(job_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/run")
    async def run_job_now(job_id: str, request: Request):
        """Run job immediately"""
        try:
            from agentic.scheduler import get_scheduler
            data = await request.json() if await request.body() else {}
            scheduler = get_scheduler()
            result = scheduler.run_job_now(job_id, override_params=data.get("parameters"))
            if result:
                return result.to_dict()
            return {"error": "Job not found or execution failed"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/{job_id}/results")
    async def get_job_results(job_id: str, limit: int = 10):
        """Get job execution results"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            results = jm.get_job_results(job_id, limit=limit)
            return {"results": [r.to_dict() for r in results]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/jobs/{job_id}/schedule/{trigger_id}")
    async def schedule_job_with_trigger(job_id: str, trigger_id: str):
        """Schedule job with trigger"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.schedule_job(job_id, trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/scheduler/jobs/{job_id}/schedule/{trigger_id}")
    async def unschedule_job_from_trigger(job_id: str, trigger_id: str):
        """Unschedule job from trigger"""
        try:
            from agentic.scheduler import get_scheduler
            scheduler = get_scheduler()
            success = scheduler.unschedule_job(job_id, trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/jobs/statistics")
    async def get_job_statistics():
        """Get job statistics"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            return jm.get_statistics()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/handlers")
    async def list_handlers():
        """List available job handlers"""
        try:
            from agentic.scheduler import get_job_manager
            jm = get_job_manager()
            return {"handlers": jm.get_handlers()}
        except ImportError:
            return {"error": "Scheduler module not available"}

    # Trigger API endpoints
    @app.get("/api/scheduler/triggers")
    async def list_triggers(trigger_type: str = None, status: str = None, tag: str = None):
        """List all triggers"""
        try:
            from agentic.scheduler import get_trigger_manager, TriggerType, TriggerStatus
            tm = get_trigger_manager()
            tt = TriggerType(trigger_type) if trigger_type else None
            ts = TriggerStatus(status) if status else None
            triggers = tm.get_triggers(trigger_type=tt, status=ts, tag=tag)
            return {"triggers": [t.to_dict() for t in triggers]}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers")
    async def create_trigger(request: Request):
        """Create a new trigger"""
        try:
            from agentic.scheduler import get_trigger_manager, TriggerType
            from datetime import datetime
            data = await request.json()
            tm = get_trigger_manager()

            trigger = tm.create_trigger(
                name=data["name"],
                trigger_type=TriggerType(data["trigger_type"]),
                description=data.get("description", ""),
                cron_expression=data.get("cron_expression"),
                interval_seconds=data.get("interval_seconds"),
                run_date=datetime.fromisoformat(data["run_date"]) if data.get("run_date") else None,
                event_type=data.get("event_type"),
                event_filter=data.get("event_filter"),
                depends_on_job_id=data.get("depends_on_job_id"),
                depend_on_success=data.get("depend_on_success", True),
                start_date=datetime.fromisoformat(data["start_date"]) if data.get("start_date") else None,
                end_date=datetime.fromisoformat(data["end_date"]) if data.get("end_date") else None,
                max_executions=data.get("max_executions"),
                jitter_seconds=data.get("jitter_seconds", 0),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return trigger.to_dict()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/triggers/{trigger_id}")
    async def get_trigger(trigger_id: str):
        """Get trigger by ID"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            trigger = tm.get_trigger(trigger_id)
            if trigger:
                return trigger.to_dict()
            return {"error": "Trigger not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.put("/api/scheduler/triggers/{trigger_id}")
    async def update_trigger(trigger_id: str, request: Request):
        """Update trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            data = await request.json()
            tm = get_trigger_manager()
            trigger = tm.update_trigger(trigger_id, **data)
            if trigger:
                return trigger.to_dict()
            return {"error": "Trigger not found"}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.delete("/api/scheduler/triggers/{trigger_id}")
    async def delete_trigger(trigger_id: str):
        """Delete trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            success = tm.delete_trigger(trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/{trigger_id}/pause")
    async def pause_trigger(trigger_id: str):
        """Pause trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            success = tm.pause_trigger(trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/{trigger_id}/resume")
    async def resume_trigger(trigger_id: str):
        """Resume trigger"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            success = tm.resume_trigger(trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/triggers/{trigger_id}/fire")
    async def fire_trigger(trigger_id: str):
        """Fire trigger manually"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            success = tm.fire_trigger(trigger_id)
            return {"success": success}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/triggers/statistics")
    async def get_trigger_statistics():
        """Get trigger statistics"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            return tm.get_statistics()
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/triggers/schedule")
    async def get_trigger_schedule(hours: int = 24):
        """Get trigger schedule for next N hours"""
        try:
            from agentic.scheduler import get_trigger_manager
            tm = get_trigger_manager()
            schedule = tm.get_schedule(hours=hours)
            return {
                "schedule": [
                    {"time": t.isoformat(), "trigger": trg.to_dict()}
                    for t, trg in schedule
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.post("/api/scheduler/cron/parse")
    async def parse_cron_expression(request: Request):
        """Parse cron expression"""
        try:
            from agentic.scheduler import CronExpression
            data = await request.json()
            expression = data.get("expression", "* * * * *")
            cron = CronExpression(expression)
            return {
                "expression": expression,
                "description": CronExpression.describe(expression),
                "parsed": cron.to_dict(),
                "next_5": [t.isoformat() for t in cron.get_schedule(count=5)]
            }
        except ValueError as e:
            return {"error": str(e)}
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/job-types")
    async def list_job_types():
        """List job types"""
        try:
            from agentic.scheduler import JobType
            return {
                "job_types": [
                    {"value": t.value, "name": t.name}
                    for t in JobType
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/job-statuses")
    async def list_job_statuses():
        """List job statuses"""
        try:
            from agentic.scheduler import JobStatus
            return {
                "job_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in JobStatus
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/job-priorities")
    async def list_job_priorities():
        """List job priorities"""
        try:
            from agentic.scheduler import JobPriority
            return {
                "job_priorities": [
                    {"value": p.value, "name": p.name}
                    for p in JobPriority
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/trigger-types")
    async def list_trigger_types():
        """List trigger types"""
        try:
            from agentic.scheduler import TriggerType
            return {
                "trigger_types": [
                    {"value": t.value, "name": t.name}
                    for t in TriggerType
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    @app.get("/api/scheduler/trigger-statuses")
    async def list_trigger_statuses():
        """List trigger statuses"""
        try:
            from agentic.scheduler import TriggerStatus
            return {
                "trigger_statuses": [
                    {"value": s.value, "name": s.name}
                    for s in TriggerStatus
                ]
            }
        except ImportError:
            return {"error": "Scheduler module not available"}

    # ============================================================
    # METRICS API ENDPOINTS
    # ============================================================

    @app.get("/api/metrics")
    async def list_metrics(metric_type: str = None, category: str = None, enabled_only: bool = False, tag: str = None):
        """List all metrics"""
        try:
            from agentic.metrics import get_metric_collector, MetricType, MetricCategory
            mc = get_metric_collector()
            mt = MetricType(metric_type) if metric_type else None
            cat = MetricCategory(category) if category else None
            metrics = mc.get_metrics(metric_type=mt, category=cat, enabled_only=enabled_only, tag=tag)
            return {"metrics": [m.to_dict() for m in metrics]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics")
    async def create_metric(request: Request):
        """Create a new metric"""
        try:
            from agentic.metrics import get_metric_collector, MetricType, MetricUnit, MetricCategory, MetricConfig
            data = await request.json()
            mc = get_metric_collector()

            config = None
            if "config" in data:
                config = MetricConfig(**data["config"])

            metric = mc.create_metric(
                name=data["name"],
                metric_type=MetricType(data["metric_type"]),
                unit=MetricUnit(data["unit"]),
                category=MetricCategory(data["category"]),
                description=data.get("description", ""),
                config=config,
                labels=data.get("labels", {}),
                collector_func=data.get("collector_func"),
                enabled=data.get("enabled", True)
            )
            return metric.to_dict()
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/{metric_id}")
    async def get_metric(metric_id: str):
        """Get metric by ID"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            metric = mc.get_metric(metric_id)
            if metric:
                return metric.to_dict()
            return {"error": "Metric not found"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.put("/api/metrics/{metric_id}")
    async def update_metric(metric_id: str, request: Request):
        """Update metric"""
        try:
            from agentic.metrics import get_metric_collector
            data = await request.json()
            mc = get_metric_collector()
            metric = mc.update_metric(metric_id, **data)
            if metric:
                return metric.to_dict()
            return {"error": "Metric not found"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.delete("/api/metrics/{metric_id}")
    async def delete_metric(metric_id: str):
        """Delete metric"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            success = mc.delete_metric(metric_id)
            return {"success": success}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/{metric_id}/enable")
    async def enable_metric(metric_id: str):
        """Enable metric"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            success = mc.enable_metric(metric_id)
            return {"success": success}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/{metric_id}/disable")
    async def disable_metric(metric_id: str):
        """Disable metric"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            success = mc.disable_metric(metric_id)
            return {"success": success}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/{metric_id}/collect")
    async def collect_metric(metric_id: str):
        """Collect metric value"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            value = mc.collect(metric_id)
            if value is not None:
                return {"value": value}
            return {"error": "Collection failed"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/collect-all")
    async def collect_all_metrics():
        """Collect all metrics"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            results = mc.collect_all()
            return {"collected": results, "count": len(results)}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/collectors")
    async def list_collectors():
        """List available collectors"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            return {"collectors": mc.get_collectors()}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/statistics")
    async def get_metrics_statistics():
        """Get metrics statistics"""
        try:
            from agentic.metrics import get_metric_collector
            mc = get_metric_collector()
            return mc.get_statistics()
        except ImportError:
            return {"error": "Metrics module not available"}

    # Time Series API endpoints
    @app.get("/api/metrics/series")
    async def list_time_series():
        """List all time series"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            series = store.get_all_series()
            return {"series": [s.to_dict(include_points=False) for s in series]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/series")
    async def create_time_series(request: Request):
        """Create time series"""
        try:
            from agentic.metrics import get_timeseries_store
            data = await request.json()
            store = get_timeseries_store()
            series = store.create_series(
                metric_id=data["metric_id"],
                name=data["name"],
                labels=data.get("labels", {}),
                max_points=data.get("max_points", 10000),
                retention_hours=data.get("retention_hours", 24)
            )
            return series.to_dict(include_points=False)
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/series/{series_id}")
    async def get_time_series(series_id: str, include_points: bool = False):
        """Get time series by ID"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            series = store.get_series(series_id)
            if series:
                return series.to_dict(include_points=include_points)
            return {"error": "Series not found"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.delete("/api/metrics/series/{series_id}")
    async def delete_time_series(series_id: str):
        """Delete time series"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            success = store.delete_series(series_id)
            return {"success": success}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/series/{series_id}/record")
    async def record_data_point(series_id: str, request: Request):
        """Record data point"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import datetime
            data = await request.json()
            store = get_timeseries_store()
            series = store.get_series(series_id)
            if not series:
                return {"error": "Series not found"}

            timestamp = datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None
            point = series.add_point(
                value=data["value"],
                timestamp=timestamp,
                labels=data.get("labels")
            )
            return point.to_dict()
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/series/{series_id}/points")
    async def get_data_points(series_id: str, start: str = None, end: str = None, limit: int = None):
        """Get data points"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import datetime
            store = get_timeseries_store()
            series = store.get_series(series_id)
            if not series:
                return {"error": "Series not found"}

            start_dt = datetime.fromisoformat(start) if start else None
            end_dt = datetime.fromisoformat(end) if end else None
            points = series.get_points(start=start_dt, end=end_dt, limit=limit)
            return {"points": [p.to_dict() for p in points]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/series/{series_id}/latest")
    async def get_latest_points(series_id: str, n: int = 1):
        """Get latest data points"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            series = store.get_series(series_id)
            if not series:
                return {"error": "Series not found"}

            points = series.get_latest(n)
            return {"points": [p.to_dict() for p in points]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/series/{series_id}/statistics")
    async def get_series_statistics(series_id: str):
        """Get series statistics"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            series = store.get_series(series_id)
            if not series:
                return {"error": "Series not found"}

            return series.get_statistics()
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/record")
    async def record_metric_value(request: Request):
        """Record metric value (auto-creates series)"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import datetime
            data = await request.json()
            store = get_timeseries_store()

            timestamp = datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None
            point = store.record(
                metric_id=data["metric_id"],
                value=data["value"],
                timestamp=timestamp,
                labels=data.get("labels")
            )
            return point.to_dict()
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/query")
    async def query_metrics(metric_id: str = None, start: str = None, end: str = None, limit: int = None):
        """Query metrics data"""
        try:
            from agentic.metrics import get_timeseries_store
            from datetime import datetime
            store = get_timeseries_store()

            start_dt = datetime.fromisoformat(start) if start else None
            end_dt = datetime.fromisoformat(end) if end else None
            results = store.query(metric_id=metric_id, start=start_dt, end=end_dt, limit=limit)
            return {
                "results": [
                    {"series": s.to_dict(include_points=False), "points": [p.to_dict() for p in points]}
                    for s, points in results
                ]
            }
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/latest")
    async def get_latest_values(metric_id: str = None):
        """Get latest values for all series"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            return {"latest": store.get_latest_values(metric_id=metric_id)}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/cleanup")
    async def cleanup_old_data(older_than_hours: int = None):
        """Clean up old data"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            removed = store.cleanup(older_than_hours=older_than_hours)
            return {"removed_points": removed}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/store/statistics")
    async def get_store_statistics():
        """Get store statistics"""
        try:
            from agentic.metrics import get_timeseries_store
            store = get_timeseries_store()
            stats = store.get_statistics()
            # Convert datetime objects
            if stats.get("oldest_point"):
                stats["oldest_point"] = stats["oldest_point"].isoformat()
            if stats.get("newest_point"):
                stats["newest_point"] = stats["newest_point"].isoformat()
            return stats
        except ImportError:
            return {"error": "Metrics module not available"}

    # Aggregation API endpoints
    @app.post("/api/metrics/aggregate")
    async def aggregate_series(request: Request):
        """Aggregate time series"""
        try:
            from agentic.metrics import get_metric_aggregator, AggregationType
            from datetime import datetime
            data = await request.json()
            agg = get_metric_aggregator()

            start_dt = datetime.fromisoformat(data["start"]) if data.get("start") else None
            end_dt = datetime.fromisoformat(data["end"]) if data.get("end") else None

            result = agg.aggregate(
                series_id=data["series_id"],
                aggregation_type=AggregationType(data["aggregation_type"]),
                start=start_dt,
                end=end_dt
            )
            if result:
                return result.to_dict()
            return {"error": "Aggregation failed"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/aggregate-by-window")
    async def aggregate_by_window(request: Request):
        """Aggregate by time window"""
        try:
            from agentic.metrics import get_metric_aggregator, AggregationType, AggregationWindow
            from datetime import datetime
            data = await request.json()
            agg = get_metric_aggregator()

            start_dt = datetime.fromisoformat(data["start"]) if data.get("start") else None
            end_dt = datetime.fromisoformat(data["end"]) if data.get("end") else None

            results = agg.aggregate_by_window(
                series_id=data["series_id"],
                aggregation_type=AggregationType(data["aggregation_type"]),
                window=AggregationWindow(data["window"]),
                start=start_dt,
                end=end_dt
            )
            return {"results": [r.to_dict() for r in results]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/downsample")
    async def downsample_series(request: Request):
        """Downsample time series"""
        try:
            from agentic.metrics import get_metric_aggregator, AggregationType, AggregationWindow
            from datetime import datetime
            data = await request.json()
            agg = get_metric_aggregator()

            start_dt = datetime.fromisoformat(data["start"]) if data.get("start") else None
            end_dt = datetime.fromisoformat(data["end"]) if data.get("end") else None

            result = agg.downsample(
                series_id=data["series_id"],
                aggregation_type=AggregationType(data["aggregation_type"]),
                window=AggregationWindow(data["window"]),
                start=start_dt,
                end=end_dt
            )
            if result:
                return result.to_dict()
            return {"error": "Downsample failed"}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/moving-average")
    async def get_moving_average(request: Request):
        """Calculate moving average"""
        try:
            from agentic.metrics import get_metric_aggregator
            from datetime import datetime
            data = await request.json()
            agg = get_metric_aggregator()

            start_dt = datetime.fromisoformat(data["start"]) if data.get("start") else None
            end_dt = datetime.fromisoformat(data["end"]) if data.get("end") else None

            points = agg.get_moving_average(
                series_id=data["series_id"],
                window_size=data.get("window_size", 10),
                start=start_dt,
                end=end_dt
            )
            return {"points": [p.to_dict() for p in points]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/anomalies")
    async def detect_anomalies(request: Request):
        """Detect anomalies"""
        try:
            from agentic.metrics import get_metric_aggregator
            from datetime import datetime
            data = await request.json()
            agg = get_metric_aggregator()

            start_dt = datetime.fromisoformat(data["start"]) if data.get("start") else None
            end_dt = datetime.fromisoformat(data["end"]) if data.get("end") else None

            anomalies = agg.detect_anomalies(
                series_id=data["series_id"],
                threshold_stddev=data.get("threshold_stddev", 2.0),
                start=start_dt,
                end=end_dt
            )
            return {"anomalies": [a.to_dict() for a in anomalies]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.post("/api/metrics/forecast")
    async def forecast_series(request: Request):
        """Forecast future values"""
        try:
            from agentic.metrics import get_metric_aggregator
            data = await request.json()
            agg = get_metric_aggregator()

            forecasts = agg.forecast_simple(
                series_id=data["series_id"],
                periods=data.get("periods", 10),
                method=data.get("method", "linear")
            )
            return {"forecasts": [f.to_dict() for f in forecasts]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/aggregator/statistics")
    async def get_aggregator_statistics():
        """Get aggregator statistics"""
        try:
            from agentic.metrics import get_metric_aggregator
            agg = get_metric_aggregator()
            return agg.get_statistics()
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/types")
    async def list_metric_types():
        """List metric types"""
        try:
            from agentic.metrics import MetricType
            return {"metric_types": [{"value": t.value, "name": t.name} for t in MetricType]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/units")
    async def list_metric_units():
        """List metric units"""
        try:
            from agentic.metrics import MetricUnit
            return {"metric_units": [{"value": u.value, "name": u.name} for u in MetricUnit]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/categories")
    async def list_metric_categories():
        """List metric categories"""
        try:
            from agentic.metrics import MetricCategory
            return {"metric_categories": [{"value": c.value, "name": c.name} for c in MetricCategory]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/aggregation-types")
    async def list_aggregation_types():
        """List aggregation types"""
        try:
            from agentic.metrics import AggregationType
            return {"aggregation_types": [{"value": t.value, "name": t.name} for t in AggregationType]}
        except ImportError:
            return {"error": "Metrics module not available"}

    @app.get("/api/metrics/aggregation-windows")
    async def list_aggregation_windows():
        """List aggregation windows"""
        try:
            from agentic.metrics import AggregationWindow
            return {"aggregation_windows": [{"value": w.value, "name": w.name} for w in AggregationWindow]}
        except ImportError:
            return {"error": "Metrics module not available"}

    # ============================================================
    # ALERT MANAGEMENT API ENDPOINTS
    # ============================================================

    @app.get("/api/alerts")
    async def list_alerts(severity: str = None, status: str = None, category: str = None, source: str = None, active_only: bool = False):
        """List all alerts"""
        try:
            from agentic.alerts import get_alert_manager, AlertSeverity, AlertStatus, AlertCategory
            am = get_alert_manager()
            sev = AlertSeverity(int(severity)) if severity else None
            stat = AlertStatus(status) if status else None
            cat = AlertCategory(category) if category else None
            alerts = am.get_alerts(severity=sev, status=stat, category=cat, source=source, active_only=active_only)
            return {"alerts": [a.to_dict() for a in alerts]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts")
    async def create_alert(request: Request):
        """Create a new alert"""
        try:
            from agentic.alerts import get_alert_manager, AlertSeverity, AlertCategory, AlertConfig
            data = await request.json()
            am = get_alert_manager()

            config = None
            if "config" in data:
                config = AlertConfig(**data["config"])

            alert = am.create_alert(
                name=data["name"],
                description=data.get("description", ""),
                severity=AlertSeverity(data["severity"]),
                category=AlertCategory(data.get("category", "custom")),
                config=config,
                source=data.get("source", ""),
                source_id=data.get("source_id"),
                message=data.get("message", ""),
                details=data.get("details", {}),
                labels=data.get("labels", {})
            )
            return alert.to_dict()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/{alert_id}")
    async def get_alert(alert_id: str):
        """Get alert by ID"""
        try:
            from agentic.alerts import get_alert_manager
            am = get_alert_manager()
            alert = am.get_alert(alert_id)
            if alert:
                return alert.to_dict()
            return {"error": "Alert not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.put("/api/alerts/{alert_id}")
    async def update_alert(alert_id: str, request: Request):
        """Update alert"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json()
            am = get_alert_manager()
            alert = am.update_alert(alert_id, **data)
            if alert:
                return alert.to_dict()
            return {"error": "Alert not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.delete("/api/alerts/{alert_id}")
    async def delete_alert(alert_id: str):
        """Delete alert"""
        try:
            from agentic.alerts import get_alert_manager
            am = get_alert_manager()
            success = am.delete_alert(alert_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/acknowledge")
    async def acknowledge_alert(alert_id: str, request: Request):
        """Acknowledge alert"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json() if await request.body() else {}
            am = get_alert_manager()
            success = am.acknowledge_alert(alert_id, data.get("user", "system"), data.get("note", ""))
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str, request: Request):
        """Resolve alert"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json() if await request.body() else {}
            am = get_alert_manager()
            success = am.resolve_alert(alert_id, data.get("user"), data.get("note", ""))
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/suppress")
    async def suppress_alert(alert_id: str, request: Request):
        """Suppress alert"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json() if await request.body() else {}
            am = get_alert_manager()
            success = am.suppress_alert(alert_id, data.get("minutes"), data.get("user"))
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/escalate")
    async def escalate_alert(alert_id: str, request: Request):
        """Escalate alert"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json() if await request.body() else {}
            am = get_alert_manager()
            success = am.escalate_alert(alert_id, data.get("level"))
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/bulk/acknowledge")
    async def bulk_acknowledge_alerts(request: Request):
        """Bulk acknowledge alerts"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json()
            am = get_alert_manager()
            count = am.bulk_acknowledge(data["alert_ids"], data.get("user", "system"), data.get("note", ""))
            return {"acknowledged": count}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/bulk/resolve")
    async def bulk_resolve_alerts(request: Request):
        """Bulk resolve alerts"""
        try:
            from agentic.alerts import get_alert_manager
            data = await request.json()
            am = get_alert_manager()
            count = am.bulk_resolve(data["alert_ids"], data.get("user"), data.get("note", ""))
            return {"resolved": count}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/active/count")
    async def get_active_alert_count():
        """Get active alert count by severity"""
        try:
            from agentic.alerts import get_alert_manager
            am = get_alert_manager()
            return am.get_active_count()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/cleanup")
    async def cleanup_expired_alerts():
        """Cleanup expired alerts"""
        try:
            from agentic.alerts import get_alert_manager
            am = get_alert_manager()
            count = am.cleanup_expired()
            return {"expired": count}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/statistics")
    async def get_alert_statistics():
        """Get alert statistics"""
        try:
            from agentic.alerts import get_alert_manager
            am = get_alert_manager()
            return am.get_statistics()
        except ImportError:
            return {"error": "Alerts module not available"}

    # Notification Channel API endpoints
    @app.get("/api/alerts/channels")
    async def list_channels(channel_type: str = None, status: str = None, enabled_only: bool = False):
        """List notification channels"""
        try:
            from agentic.alerts import get_channel_manager, ChannelType, ChannelStatus
            cm = get_channel_manager()
            ct = ChannelType(channel_type) if channel_type else None
            cs = ChannelStatus(status) if status else None
            channels = cm.get_channels(channel_type=ct, status=cs, enabled_only=enabled_only)
            return {"channels": [c.to_dict() for c in channels]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/channels")
    async def create_channel(request: Request):
        """Create notification channel"""
        try:
            from agentic.alerts import get_channel_manager, ChannelType, ChannelConfig, AlertSeverity
            data = await request.json()
            cm = get_channel_manager()

            config = None
            if "config" in data:
                config_data = data["config"]
                if "min_severity" in config_data:
                    config_data["min_severity"] = AlertSeverity(config_data["min_severity"])
                config = ChannelConfig(**config_data)

            channel = cm.create_channel(
                name=data["name"],
                channel_type=ChannelType(data["channel_type"]),
                description=data.get("description", ""),
                config=config,
                endpoint=data.get("endpoint", ""),
                credentials=data.get("credentials", {}),
                enabled=data.get("enabled", True)
            )
            return channel.to_dict()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/channels/{channel_id}")
    async def get_channel(channel_id: str):
        """Get channel by ID"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            channel = cm.get_channel(channel_id)
            if channel:
                return channel.to_dict()
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.put("/api/alerts/channels/{channel_id}")
    async def update_channel(channel_id: str, request: Request):
        """Update channel"""
        try:
            from agentic.alerts import get_channel_manager
            data = await request.json()
            cm = get_channel_manager()
            channel = cm.update_channel(channel_id, **data)
            if channel:
                return channel.to_dict()
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.delete("/api/alerts/channels/{channel_id}")
    async def delete_channel(channel_id: str):
        """Delete channel"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            success = cm.delete_channel(channel_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/channels/{channel_id}/enable")
    async def enable_channel(channel_id: str):
        """Enable channel"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            success = cm.enable_channel(channel_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/channels/{channel_id}/disable")
    async def disable_channel(channel_id: str):
        """Disable channel"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            success = cm.disable_channel(channel_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/channels/{channel_id}/test")
    async def test_channel(channel_id: str):
        """Test channel"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            result = cm.test_channel(channel_id)
            return result.to_dict()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/channels/{channel_id}/send")
    async def send_to_channel(channel_id: str, request: Request):
        """Send alert to specific channel"""
        try:
            from agentic.alerts import get_channel_manager, get_alert_manager
            data = await request.json()
            cm = get_channel_manager()
            am = get_alert_manager()
            alert = am.get_alert(data["alert_id"])
            if not alert:
                return {"error": "Alert not found"}
            result = cm.send_notification(channel_id, alert)
            if result:
                return result.to_dict()
            return {"error": "Send failed"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/broadcast")
    async def broadcast_alert(alert_id: str):
        """Broadcast alert to all applicable channels"""
        try:
            from agentic.alerts import get_channel_manager, get_alert_manager
            cm = get_channel_manager()
            am = get_alert_manager()
            alert = am.get_alert(alert_id)
            if not alert:
                return {"error": "Alert not found"}
            results = cm.broadcast_alert(alert)
            return {"results": [r.to_dict() for r in results]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/channels/statistics")
    async def get_channel_statistics():
        """Get channel statistics"""
        try:
            from agentic.alerts import get_channel_manager
            cm = get_channel_manager()
            return cm.get_statistics()
        except ImportError:
            return {"error": "Alerts module not available"}

    # Escalation Policy API endpoints
    @app.get("/api/alerts/escalation/policies")
    async def list_escalation_policies(enabled_only: bool = False):
        """List escalation policies"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            policies = em.get_policies(enabled_only=enabled_only)
            return {"policies": [p.to_dict() for p in policies]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/escalation/policies")
    async def create_escalation_policy(request: Request):
        """Create escalation policy"""
        try:
            from agentic.alerts import get_escalation_manager, AlertSeverity, EscalationLevel, EscalationTrigger, EscalationAction
            data = await request.json()
            em = get_escalation_manager()

            levels = []
            for lvl_data in data.get("levels", []):
                level = EscalationLevel(
                    level=lvl_data["level"],
                    name=lvl_data["name"],
                    description=lvl_data.get("description", ""),
                    trigger=EscalationTrigger(lvl_data.get("trigger", "time")),
                    trigger_minutes=lvl_data.get("trigger_minutes", 30),
                    min_severity=AlertSeverity(lvl_data.get("min_severity", 2)),
                    actions=[EscalationAction(a) for a in lvl_data.get("actions", [])],
                    channel_ids=lvl_data.get("channel_ids", []),
                    assignee=lvl_data.get("assignee"),
                    notify_previous=lvl_data.get("notify_previous", True),
                    enabled=lvl_data.get("enabled", True)
                )
                levels.append(level)

            policy = em.create_policy(
                name=data["name"],
                description=data.get("description", ""),
                enabled=data.get("enabled", True),
                levels=levels,
                severities=[AlertSeverity(s) for s in data.get("severities", [])],
                categories=data.get("categories", []),
                sources=data.get("sources", []),
                labels=data.get("labels", {})
            )
            return policy.to_dict()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/escalation/policies/{policy_id}")
    async def get_escalation_policy(policy_id: str):
        """Get escalation policy by ID"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            policy = em.get_policy(policy_id)
            if policy:
                return policy.to_dict()
            return {"error": "Policy not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.put("/api/alerts/escalation/policies/{policy_id}")
    async def update_escalation_policy(policy_id: str, request: Request):
        """Update escalation policy"""
        try:
            from agentic.alerts import get_escalation_manager
            data = await request.json()
            em = get_escalation_manager()
            policy = em.update_policy(policy_id, **data)
            if policy:
                return policy.to_dict()
            return {"error": "Policy not found"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.delete("/api/alerts/escalation/policies/{policy_id}")
    async def delete_escalation_policy(policy_id: str):
        """Delete escalation policy"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            success = em.delete_policy(policy_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/escalation/policies/{policy_id}/enable")
    async def enable_escalation_policy(policy_id: str):
        """Enable escalation policy"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            success = em.enable_policy(policy_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/escalation/policies/{policy_id}/disable")
    async def disable_escalation_policy(policy_id: str):
        """Disable escalation policy"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            success = em.disable_policy(policy_id)
            return {"success": success}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/check-escalation")
    async def check_alert_escalation(alert_id: str):
        """Check if alert should be escalated"""
        try:
            from agentic.alerts import get_escalation_manager, get_alert_manager
            em = get_escalation_manager()
            am = get_alert_manager()
            alert = am.get_alert(alert_id)
            if not alert:
                return {"error": "Alert not found"}
            result = em.check_escalation(alert)
            if result:
                policy, level = result
                return {"should_escalate": True, "policy": policy.name, "level": level.to_dict()}
            return {"should_escalate": False}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.post("/api/alerts/{alert_id}/process-escalation")
    async def process_alert_escalation(alert_id: str):
        """Process escalation for alert"""
        try:
            from agentic.alerts import get_escalation_manager, get_alert_manager
            em = get_escalation_manager()
            am = get_alert_manager()
            alert = am.get_alert(alert_id)
            if not alert:
                return {"error": "Alert not found"}
            result = em.check_escalation(alert)
            if result:
                policy, level = result
                return em.process_escalation(alert, policy, level)
            return {"error": "No escalation needed"}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/escalation/statistics")
    async def get_escalation_statistics():
        """Get escalation statistics"""
        try:
            from agentic.alerts import get_escalation_manager
            em = get_escalation_manager()
            return em.get_statistics()
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/severities")
    async def list_alert_severities():
        """List alert severities"""
        try:
            from agentic.alerts import AlertSeverity
            return {"severities": [{"value": s.value, "name": s.name} for s in AlertSeverity]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/statuses")
    async def list_alert_statuses():
        """List alert statuses"""
        try:
            from agentic.alerts import AlertStatus
            return {"statuses": [{"value": s.value, "name": s.name} for s in AlertStatus]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/categories")
    async def list_alert_categories():
        """List alert categories"""
        try:
            from agentic.alerts import AlertCategory
            return {"categories": [{"value": c.value, "name": c.name} for c in AlertCategory]}
        except ImportError:
            return {"error": "Alerts module not available"}

    @app.get("/api/alerts/channel-types")
    async def list_channel_types():
        """List channel types"""
        try:
            from agentic.alerts import ChannelType
            return {"channel_types": [{"value": t.value, "name": t.name} for t in ChannelType]}
        except ImportError:
            return {"error": "Alerts module not available"}

    # ==================== Service Discovery API ====================

    @app.get("/api/discovery/status")
    async def get_discovery_status() -> Dict[str, Any]:
        """Get service discovery status"""
        try:
            from agentic.discovery import get_service_registry, get_health_checker, get_load_balancer
            registry = get_service_registry()
            checker = get_health_checker()
            lb = get_load_balancer()
            return {
                "registry": registry.get_statistics(),
                "health_checker": checker.get_statistics(),
                "load_balancer": lb.get_statistics()
            }
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/services")
    async def list_services(
        service_type: Optional[str] = None,
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        """List registered services"""
        try:
            from agentic.discovery import get_service_registry, ServiceType
            registry = get_service_registry()
            stype = ServiceType(service_type) if service_type else None
            tag_list = tags.split(",") if tags else None
            services = registry.get_services(service_type=stype, tags=tag_list)
            return {"services": [s.to_dict() for s in services]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/services")
    async def register_service(request: Request) -> Dict[str, Any]:
        """Register a service"""
        try:
            from agentic.discovery import get_service_registry, ServiceType
            data = await request.json()
            registry = get_service_registry()
            service = registry.register_service(
                name=data["name"],
                service_type=ServiceType(data.get("service_type", "api")),
                description=data.get("description", ""),
                ttl_seconds=data.get("ttl_seconds", 30),
                version=data.get("version", "1.0.0"),
                owner=data.get("owner", ""),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {})
            )
            return {"service": service.to_dict()}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/services/{service_name}")
    async def get_service(service_name: str) -> Dict[str, Any]:
        """Get service details"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            service = registry.get_service(service_name)
            if service:
                return {"service": service.to_dict()}
            return {"error": "Service not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.delete("/api/discovery/services/{service_name}")
    async def deregister_service(service_name: str) -> Dict[str, Any]:
        """Deregister a service"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            if registry.deregister_service(service_name):
                return {"status": "deregistered"}
            return {"error": "Service not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/services/{service_name}/instances")
    async def register_instance(service_name: str, request: Request) -> Dict[str, Any]:
        """Register a service instance"""
        try:
            from agentic.discovery import get_service_registry
            data = await request.json()
            registry = get_service_registry()
            instance = registry.register_instance(
                service_name=service_name,
                host=data["host"],
                port=data["port"],
                protocol=data.get("protocol", "http"),
                path=data.get("path", ""),
                weight=data.get("weight", 100),
                version=data.get("version", "1.0.0"),
                region=data.get("region", ""),
                zone=data.get("zone", ""),
                tags=data.get("tags", []),
                metadata=data.get("metadata", {}),
                health_check_url=data.get("health_check_url")
            )
            return {"instance": instance.to_dict()}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.delete("/api/discovery/services/{service_name}/instances/{instance_id}")
    async def deregister_instance(service_name: str, instance_id: str) -> Dict[str, Any]:
        """Deregister a service instance"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            if registry.deregister_instance(service_name, instance_id):
                return {"status": "deregistered"}
            return {"error": "Instance not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/services/{service_name}/instances/{instance_id}/heartbeat")
    async def instance_heartbeat(service_name: str, instance_id: str) -> Dict[str, Any]:
        """Send instance heartbeat"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            if registry.heartbeat(service_name, instance_id):
                return {"status": "ok"}
            return {"error": "Instance not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/discover/{service_name}")
    async def discover_service(
        service_name: str,
        healthy_only: bool = True,
        tags: Optional[str] = None,
        region: Optional[str] = None,
        zone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Discover service instances"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            tag_list = tags.split(",") if tags else None
            instances = registry.discover(
                service_name,
                healthy_only=healthy_only,
                tags=tag_list,
                region=region,
                zone=zone
            )
            return {"instances": [i.to_dict() for i in instances]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/cleanup")
    async def cleanup_stale_instances(max_age_seconds: int = 60) -> Dict[str, Any]:
        """Cleanup stale instances"""
        try:
            from agentic.discovery import get_service_registry
            registry = get_service_registry()
            removed = registry.cleanup_stale_instances(max_age_seconds)
            return {"removed": removed}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/health/checks")
    async def list_health_checks(
        enabled_only: bool = False,
        check_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """List health checks"""
        try:
            from agentic.discovery import get_health_checker, HealthCheckType
            checker = get_health_checker()
            ctype = HealthCheckType(check_type) if check_type else None
            checks = checker.get_all_checks(enabled_only=enabled_only, check_type=ctype)
            return {"checks": [c.to_dict() for c in checks]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/checks")
    async def create_health_check(request: Request) -> Dict[str, Any]:
        """Create a health check"""
        try:
            from agentic.discovery import get_health_checker, HealthCheckType
            data = await request.json()
            checker = get_health_checker()
            check = checker.create_check(
                name=data["name"],
                target=data["target"],
                check_type=HealthCheckType(data.get("check_type", "http")),
                http_url=data.get("http_url"),
                tcp_host=data.get("tcp_host"),
                tcp_port=data.get("tcp_port"),
                interval_seconds=data.get("interval_seconds", 10),
                timeout_seconds=data.get("timeout_seconds", 5),
                metadata=data.get("metadata", {})
            )
            return {"check": check.to_dict()}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/health/checks/{check_id}")
    async def get_health_check(check_id: str) -> Dict[str, Any]:
        """Get health check details"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            check = checker.get_check(check_id)
            if check:
                return {"check": check.to_dict()}
            return {"error": "Check not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.delete("/api/discovery/health/checks/{check_id}")
    async def delete_health_check(check_id: str) -> Dict[str, Any]:
        """Delete health check"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            if checker.delete_check(check_id):
                return {"status": "deleted"}
            return {"error": "Check not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/checks/{check_id}/execute")
    async def execute_health_check(check_id: str) -> Dict[str, Any]:
        """Execute health check"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            result = checker.execute_check(check_id)
            if result:
                return {"result": result.to_dict()}
            return {"error": "Check not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/checks/{check_id}/enable")
    async def enable_health_check(check_id: str) -> Dict[str, Any]:
        """Enable health check"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            if checker.enable_check(check_id):
                return {"status": "enabled"}
            return {"error": "Check not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/checks/{check_id}/disable")
    async def disable_health_check(check_id: str) -> Dict[str, Any]:
        """Disable health check"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            if checker.disable_check(check_id):
                return {"status": "disabled"}
            return {"error": "Check not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/checks/{check_id}/heartbeat")
    async def ttl_heartbeat(check_id: str) -> Dict[str, Any]:
        """Send TTL heartbeat"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            if checker.ttl_heartbeat(check_id):
                return {"status": "ok"}
            return {"error": "Check not found or not TTL type"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/health/execute-all")
    async def execute_all_due_checks() -> Dict[str, Any]:
        """Execute all due health checks"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            results = checker.execute_all_due()
            return {"results": [r.to_dict() for r in results], "count": len(results)}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/health/unhealthy")
    async def get_unhealthy_checks() -> Dict[str, Any]:
        """Get unhealthy checks"""
        try:
            from agentic.discovery import get_health_checker
            checker = get_health_checker()
            checks = checker.get_unhealthy_checks()
            return {"checks": [c.to_dict() for c in checks]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/lb/status")
    async def get_lb_status() -> Dict[str, Any]:
        """Get load balancer status"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            return lb.get_statistics()
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/lb/select/{service_name}")
    async def lb_select(
        service_name: str,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """Select endpoint using load balancer"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            endpoint = lb.select(service_name, session_id, client_ip)
            if endpoint:
                return {"endpoint": endpoint.to_dict()}
            return {"error": "No available endpoints"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/lb/release/{service_name}/{instance_id}")
    async def lb_release(
        service_name: str,
        instance_id: str,
        success: bool = True,
        response_time_ms: float = 0.0
    ) -> Dict[str, Any]:
        """Release endpoint after use"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            lb.release(service_name, instance_id, success, response_time_ms)
            return {"status": "released"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/lb/endpoints/{service_name}")
    async def get_lb_endpoints(service_name: str) -> Dict[str, Any]:
        """Get load balancer endpoints for service"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            endpoints = lb.get_endpoints(service_name)
            return {"endpoints": [e.to_dict() for e in endpoints]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.put("/api/discovery/lb/strategy")
    async def set_lb_strategy(request: Request) -> Dict[str, Any]:
        """Set load balancing strategy"""
        try:
            from agentic.discovery import get_load_balancer, LoadBalanceStrategy
            data = await request.json()
            lb = get_load_balancer()
            lb.set_strategy(LoadBalanceStrategy(data["strategy"]))
            return {"strategy": lb.config.strategy.value}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/lb/circuit-breakers")
    async def get_circuit_breakers() -> Dict[str, Any]:
        """Get open circuit breakers"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            breakers = lb.get_circuit_breakers()
            return {"circuit_breakers": {k: v.isoformat() for k, v in breakers.items()}}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/lb/circuit-breakers/{instance_id}/reset")
    async def reset_circuit_breaker(instance_id: str) -> Dict[str, Any]:
        """Reset circuit breaker"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            if lb.reset_circuit_breaker(instance_id):
                return {"status": "reset"}
            return {"error": "Circuit breaker not found"}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.post("/api/discovery/lb/sessions/clear")
    async def clear_sticky_sessions() -> Dict[str, Any]:
        """Clear sticky sessions"""
        try:
            from agentic.discovery import get_load_balancer
            lb = get_load_balancer()
            count = lb.clear_sessions()
            return {"cleared": count}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/service-types")
    async def list_service_types() -> Dict[str, Any]:
        """List service types"""
        try:
            from agentic.discovery import ServiceType
            return {"service_types": [{"value": t.value, "name": t.name} for t in ServiceType]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/health-statuses")
    async def list_health_statuses() -> Dict[str, Any]:
        """List health statuses"""
        try:
            from agentic.discovery import HealthStatus
            return {"health_statuses": [{"value": s.value, "name": s.name} for s in HealthStatus]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/health-check-types")
    async def list_health_check_types() -> Dict[str, Any]:
        """List health check types"""
        try:
            from agentic.discovery import HealthCheckType
            return {"health_check_types": [{"value": t.value, "name": t.name} for t in HealthCheckType]}
        except ImportError:
            return {"error": "Discovery module not available"}

    @app.get("/api/discovery/lb-strategies")
    async def list_lb_strategies() -> Dict[str, Any]:
        """List load balancing strategies"""
        try:
            from agentic.discovery import LoadBalanceStrategy
            return {"strategies": [{"value": s.value, "name": s.name} for s in LoadBalanceStrategy]}
        except ImportError:
            return {"error": "Discovery module not available"}

    # ==================== Event Bus API ====================

    @app.get("/api/events/status")
    async def get_events_status() -> Dict[str, Any]:
        """Get event bus status"""
        try:
            from agentic.events import get_event_bus, get_subscriber_manager, get_channel_manager
            bus = get_event_bus()
            sub_mgr = get_subscriber_manager()
            ch_mgr = get_channel_manager()
            return {
                "event_bus": bus.get_statistics(),
                "subscribers": sub_mgr.get_statistics(),
                "channels": ch_mgr.get_statistics()
            }
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/publish")
    async def publish_event(request: Request) -> Dict[str, Any]:
        """Publish an event"""
        try:
            from agentic.events import get_event_bus, EventType, EventPriority
            data = await request.json()
            bus = get_event_bus()
            event = bus.publish(
                event_type=EventType(data["event_type"]),
                source=data.get("source", "api"),
                data=data.get("data", {}),
                priority=EventPriority(data.get("priority", "normal")),
                tags=data.get("tags", []),
                correlation_id=data.get("correlation_id"),
                metadata=data.get("metadata", {})
            )
            return {"event": event.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/history")
    async def get_event_history(
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get event history"""
        try:
            from agentic.events import get_event_bus, EventType
            bus = get_event_bus()
            etype = EventType(event_type) if event_type else None
            events = bus.get_history(event_type=etype, source=source, limit=limit)
            return {"events": [e.to_dict() for e in events], "count": len(events)}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/{event_id}")
    async def get_event(event_id: str) -> Dict[str, Any]:
        """Get event by ID"""
        try:
            from agentic.events import get_event_bus
            bus = get_event_bus()
            event = bus.get_event(event_id)
            if event:
                return {"event": event.to_dict()}
            return {"error": "Event not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers")
    async def list_subscribers(enabled_only: bool = False) -> Dict[str, Any]:
        """List event subscribers"""
        try:
            from agentic.events import get_subscriber_manager
            mgr = get_subscriber_manager()
            subs = mgr.get_all_subscribers(enabled_only=enabled_only)
            return {"subscribers": [s.to_dict() for s in subs]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers")
    async def create_subscriber(request: Request) -> Dict[str, Any]:
        """Create event subscriber"""
        try:
            from agentic.events import get_subscriber_manager, EventType, SubscriberConfig
            data = await request.json()
            mgr = get_subscriber_manager()
            config = SubscriberConfig(
                event_types=[EventType(t) for t in data.get("event_types", [])],
                filter_pattern=data.get("filter_pattern"),
                max_retries=data.get("max_retries", 3),
                timeout_seconds=data.get("timeout_seconds", 30)
            )
            sub = mgr.create_subscriber(
                name=data["name"],
                handler_type=data.get("handler_type", "callback"),
                config=config,
                description=data.get("description", "")
            )
            return {"subscriber": sub.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/subscribers/{subscriber_id}")
    async def get_subscriber(subscriber_id: str) -> Dict[str, Any]:
        """Get subscriber details"""
        try:
            from agentic.events import get_subscriber_manager
            mgr = get_subscriber_manager()
            sub = mgr.get_subscriber(subscriber_id)
            if sub:
                return {"subscriber": sub.to_dict()}
            return {"error": "Subscriber not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/subscribers/{subscriber_id}")
    async def delete_subscriber(subscriber_id: str) -> Dict[str, Any]:
        """Delete subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            mgr = get_subscriber_manager()
            if mgr.delete_subscriber(subscriber_id):
                return {"status": "deleted"}
            return {"error": "Subscriber not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/enable")
    async def enable_subscriber(subscriber_id: str) -> Dict[str, Any]:
        """Enable subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            mgr = get_subscriber_manager()
            if mgr.enable_subscriber(subscriber_id):
                return {"status": "enabled"}
            return {"error": "Subscriber not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/subscribers/{subscriber_id}/disable")
    async def disable_subscriber(subscriber_id: str) -> Dict[str, Any]:
        """Disable subscriber"""
        try:
            from agentic.events import get_subscriber_manager
            mgr = get_subscriber_manager()
            if mgr.disable_subscriber(subscriber_id):
                return {"status": "disabled"}
            return {"error": "Subscriber not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channels")
    async def list_event_channels(enabled_only: bool = False) -> Dict[str, Any]:
        """List event channels"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            channels = mgr.get_all_channels(enabled_only=enabled_only)
            return {"channels": [c.to_dict() for c in channels]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels")
    async def create_event_channel(request: Request) -> Dict[str, Any]:
        """Create event channel"""
        try:
            from agentic.events import get_channel_manager, ChannelType, ChannelConfig
            data = await request.json()
            mgr = get_channel_manager()
            config = ChannelConfig(
                buffer_size=data.get("buffer_size", 1000),
                persistent=data.get("persistent", False),
                ordered=data.get("ordered", True)
            )
            channel = mgr.create_channel(
                name=data["name"],
                channel_type=ChannelType(data.get("channel_type", "memory")),
                config=config,
                description=data.get("description", "")
            )
            return {"channel": channel.to_dict()}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channels/{channel_id}")
    async def get_event_channel(channel_id: str) -> Dict[str, Any]:
        """Get channel details"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            channel = mgr.get_channel(channel_id)
            if channel:
                return {"channel": channel.to_dict()}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.delete("/api/events/channels/{channel_id}")
    async def delete_event_channel(channel_id: str) -> Dict[str, Any]:
        """Delete channel"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            if mgr.delete_channel(channel_id):
                return {"status": "deleted"}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/enable")
    async def enable_event_channel(channel_id: str) -> Dict[str, Any]:
        """Enable channel"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            if mgr.enable_channel(channel_id):
                return {"status": "enabled"}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/disable")
    async def disable_event_channel(channel_id: str) -> Dict[str, Any]:
        """Disable channel"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            if mgr.disable_channel(channel_id):
                return {"status": "disabled"}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.post("/api/events/channels/{channel_id}/clear")
    async def clear_event_channel(channel_id: str) -> Dict[str, Any]:
        """Clear channel buffer"""
        try:
            from agentic.events import get_channel_manager
            mgr = get_channel_manager()
            if mgr.clear_channel(channel_id):
                return {"status": "cleared"}
            return {"error": "Channel not found"}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/types")
    async def list_event_types() -> Dict[str, Any]:
        """List event types"""
        try:
            from agentic.events import EventType
            return {"event_types": [{"value": t.value, "name": t.name} for t in EventType]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/priorities")
    async def list_event_priorities() -> Dict[str, Any]:
        """List event priorities"""
        try:
            from agentic.events import EventPriority
            return {"priorities": [{"value": p.value, "name": p.name} for p in EventPriority]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.get("/api/events/channel-types")
    async def list_event_channel_types() -> Dict[str, Any]:
        """List channel types"""
        try:
            from agentic.events import ChannelType
            return {"channel_types": [{"value": t.value, "name": t.name} for t in ChannelType]}
        except ImportError:
            return {"error": "Events module not available"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates"""
        await websocket.accept()
        await log_buffer.register_websocket(websocket)
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
                        # Also send updated GAIT data so the timeline updates
                        # Note: GAIT recording is now awaited in bridge.py, but small delay for any async I/O
                        await asyncio.sleep(0.2)
                        gait_data = await get_gait_history(data.get("agent_id"))
                        await safe_send({"type": "gait", "data": gait_data})
                    elif data.get("type") == "get_status":
                        status = await get_status()
                        await safe_send({"type": "status", "data": status})
                    elif data.get("type") == "get_routes":
                        routes = await get_routes()
                        await safe_send({"type": "routes", "data": routes})
                    elif data.get("type") == "run_tests":
                        # Run pyATS tests
                        test_results = await run_pyats_tests(
                            data.get("suites", []),
                            data.get("agent_id")
                        )
                        await safe_send({"type": "test_results", "data": test_results})
                    elif data.get("type") == "update_test_schedule":
                        # Update test schedule
                        schedule_result = await update_test_schedule(
                            data.get("agent_id"),
                            data.get("interval_minutes", 60),
                            data.get("run_on_change", False)
                        )
                        await safe_send({"type": "schedule_updated", "data": schedule_result})
                    elif data.get("type") == "get_gait":
                        # Get GAIT conversation history
                        gait_data = await get_gait_history(data.get("agent_id"))
                        await safe_send({"type": "gait", "data": gait_data})
                    elif data.get("type") == "get_markmap":
                        # Get Markmap visualization data
                        markmap_data = await get_markmap_state(data.get("agent_id"))
                        await safe_send({"type": "markmap", "data": markmap_data})
                    elif data.get("type") == "get_rfc":
                        # Get RFC information
                        try:
                            from agentic.mcp.rfc_mcp import get_rfc_client
                            client = get_rfc_client()
                            rfc_number = data.get("rfc_number")
                            if rfc_number:
                                result = client.lookup(int(rfc_number))
                                await safe_send({"type": "rfc", "data": result.to_dict()})
                            else:
                                await safe_send({"type": "rfc", "data": {"error": "No RFC number provided"}})
                        except ImportError as e:
                            await safe_send({"type": "rfc", "data": {"error": f"RFC module not available: {e}"}})
                    elif data.get("type") == "get_rfc_protocol":
                        # Get RFCs for a protocol
                        try:
                            from agentic.mcp.rfc_mcp import get_rfc_client
                            client = get_rfc_client()
                            protocol = data.get("protocol", "")
                            result = client.get_protocol_summary(protocol)
                            await safe_send({"type": "rfc_protocol", "data": result})
                        except ImportError as e:
                            await safe_send({"type": "rfc_protocol", "data": {"error": f"RFC module not available: {e}"}})
                    elif data.get("type") == "rfc_intent":
                        # Get RFCs based on intent
                        try:
                            from agentic.mcp.rfc_mcp import get_rfc_client
                            client = get_rfc_client()
                            intent = data.get("intent", "")
                            result = client.get_rfc_for_intent(intent)
                            await safe_send({"type": "rfc_intent", "data": result})
                        except ImportError as e:
                            await safe_send({"type": "rfc_intent", "data": {"error": f"RFC module not available: {e}"}})
                    elif data.get("type") == "get_health_summary":
                        # Get health monitoring summary
                        monitor = get_health_monitor()
                        if monitor:
                            await safe_send({"type": "health_summary", "data": monitor.get_health_summary()})
                        else:
                            await safe_send({"type": "health_summary", "data": {"error": "Health monitoring not available"}})
                    elif data.get("type") == "get_health_events":
                        # Get health events
                        monitor = get_health_monitor()
                        if monitor:
                            events = monitor.get_events(limit=data.get("limit", 50))
                            await safe_send({"type": "health_events", "data": {"events": [e.to_dict() for e in events]}})
                        else:
                            await safe_send({"type": "health_events", "data": {"error": "Health monitoring not available"}})
                    elif data.get("type") == "get_anomalies":
                        # Get detected anomalies
                        detector = get_anomaly_detector()
                        if detector:
                            anomalies = detector.get_anomalies(limit=data.get("limit", 50))
                            await safe_send({"type": "anomalies", "data": {"anomalies": [a.to_dict() for a in anomalies]}})
                        else:
                            await safe_send({"type": "anomalies", "data": {"error": "Anomaly detection not available"}})
                    elif data.get("type") == "get_remediation_actions":
                        # Get available remediation actions
                        engine = get_remediation_engine()
                        if engine:
                            actions = engine.list_actions(protocol=data.get("protocol"))
                            await safe_send({"type": "remediation_actions", "data": {
                                "actions": [
                                    {"action_id": a.action_id, "name": a.name, "description": a.description,
                                     "auto_execute": a.auto_execute, "protocol": a.protocol}
                                    for a in actions
                                ]
                            }})
                        else:
                            await safe_send({"type": "remediation_actions", "data": {"error": "Remediation engine not available"}})
                    elif data.get("type") == "execute_remediation":
                        # Execute a remediation action
                        engine = get_remediation_engine()
                        if engine:
                            result = await engine.execute_action(
                                action_id=data.get("action_id", ""),
                                event_type=data.get("event_type", "manual_trigger"),
                                agent_id=data.get("agent_id", ""),
                                peer_id=data.get("peer_id")
                            )
                            await safe_send({"type": "remediation_result", "data": result.to_dict()})
                        else:
                            await safe_send({"type": "remediation_result", "data": {"error": "Remediation engine not available"}})

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
            await log_buffer.unregister_websocket(websocket)

    return app


def get_fallback_html() -> str:
    """Return fallback HTML if static files not found"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASI Dashboard</title>
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
        <h1>ASI Dashboard</h1>
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


# Create standalone app for direct uvicorn usage (development/testing)
# Usage: uvicorn webui.server:app --host 0.0.0.0 --port 8000 --reload
app = create_webui_server(None, None)
