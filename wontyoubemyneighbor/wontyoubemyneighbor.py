#!/usr/bin/env python3
"""
Won't You Be My Neighbor - Unified Routing Agent
Supports OSPFv2 (RFC 2328), OSPFv3 (RFC 5340), and BGP-4 (RFC 4271) routing protocols

Usage - OSPFv2 only:
    sudo python3 wontyoubemyneighbor.py \\
        --router-id 10.255.255.99 \\
        --area 0.0.0.0 \\
        --interface eth0

Usage - OSPFv3 only (IPv6):
    sudo python3 wontyoubemyneighbor.py \\
        --router-id 10.10.10.1 \\
        --ospfv3-interface eth0 \\
        --ospfv3-area 0.0.0.0 \\
        --ospfv3-link-local fe80::1

Usage - BGP only:
    python3 wontyoubemyneighbor.py \\
        --router-id 192.0.2.1 \\
        --bgp-local-as 65001 \\
        --bgp-peer 192.0.2.2 \\
        --bgp-peer-as 65002 \\
        --bgp-network 10.2.2.2/32

Usage - OSPFv2, OSPFv3, and BGP together:
    sudo python3 wontyoubemyneighbor.py \\
        --router-id 10.0.1.1 \\
        --area 0.0.0.0 \\
        --interface eth0 \\
        --ospfv3-interface eth0 \\
        --ospfv3-area 0.0.0.0 \\
        --ospfv3-link-local fe80::1 \\
        --bgp-local-as 65001 \\
        --bgp-peer 192.0.2.2 \\
        --bgp-peer-as 65002
"""

import asyncio
import argparse
import logging
import os
import signal
import sys
import subprocess
from typing import Dict, Optional, List

# OSPF imports
from ospf.hello import HelloHandler
from ospf.neighbor import OSPFNeighbor
from ospf.lsdb import LinkStateDatabase
from ospf.spf import SPFCalculator
from ospf.adjacency import AdjacencyManager
from ospf.flooding import LSAFloodingManager
from ospf.packets import OSPFHeader, parse_ospf_packet
from ospf.constants import (
    HELLO_PACKET, DATABASE_DESCRIPTION, LINK_STATE_REQUEST,
    LINK_STATE_UPDATE, LINK_STATE_ACK, STATE_NAMES,
    STATE_DOWN, STATE_INIT, STATE_2WAY,
    STATE_EXSTART, STATE_EXCHANGE, STATE_LOADING, STATE_FULL, LINK_TYPE_STUB,
    NETWORK_TYPE_POINT_TO_MULTIPOINT, DEFAULT_NETWORK_TYPE
)
from lib.socket_handler import OSPFSocket
from lib.interface import get_interface_info
from lib.kernel_routes import KernelRouteManager

# BGP imports
from bgp import BGPSpeaker

# OSPFv3 imports
from ospfv3.speaker import OSPFv3Speaker, OSPFv3Config


class WontYouBeMyNeighbor:
    """
    Main application class that holds all protocol instances.
    Used by the Web UI to access protocol state.
    """

    def __init__(self):
        self.ospf_interface: Optional["OSPFAgent"] = None
        self.ospfv3_speaker: Optional[OSPFv3Speaker] = None
        self.bgp_speaker: Optional[BGPSpeaker] = None
        self.agentic_bridge = None
        self.router_id: Optional[str] = None
        self.area_id: Optional[str] = None
        self.running = False
        self.interfaces: List[Dict] = []  # Interface configurations
        self.config: Optional[Dict] = None  # Full agent config

    def set_ospf(self, ospf_agent: "OSPFAgent"):
        """Set OSPF agent reference"""
        self.ospf_interface = ospf_agent
        self.router_id = ospf_agent.router_id
        self.area_id = ospf_agent.area_id

    def set_ospfv3(self, ospfv3_speaker: OSPFv3Speaker):
        """Set OSPFv3 speaker reference"""
        self.ospfv3_speaker = ospfv3_speaker

    def set_bgp(self, bgp_speaker: BGPSpeaker):
        """Set BGP speaker reference"""
        self.bgp_speaker = bgp_speaker
        if not self.router_id:
            self.router_id = bgp_speaker.router_id

    def set_agentic_bridge(self, bridge):
        """Set agentic bridge reference"""
        self.agentic_bridge = bridge

    def set_config(self, config: Dict):
        """Set full agent config and extract interfaces"""
        self.config = config
        # Extract interfaces from config (support both 'ifs' and 'interfaces' keys)
        raw_ifs = config.get('ifs') or config.get('interfaces', [])
        self.interfaces = []
        self.gre_tunnels = []  # Store GRE tunnel configs for later initialization
        for iface in raw_ifs:
            iface_config = {
                'id': iface.get('id') or iface.get('n'),
                'name': iface.get('n') or iface.get('name'),
                'type': iface.get('t') or iface.get('type', 'eth'),
                'addresses': iface.get('a') or iface.get('addresses', []),
                'status': iface.get('s') or iface.get('status', 'up'),
                'mtu': iface.get('mtu', 1500),
                'description': iface.get('description', '')
            }
            self.interfaces.append(iface_config)

            # Check for GRE tunnel configuration
            if iface_config['type'] == 'gre' and iface.get('tun'):
                tun_config = iface.get('tun')
                self.gre_tunnels.append({
                    'name': iface_config['name'],
                    'local_ip': tun_config.get('src', ''),
                    'remote_ip': tun_config.get('dst', ''),
                    'tunnel_ip': iface_config['addresses'][0] if iface_config['addresses'] else '',
                    'key': tun_config.get('key'),
                    'use_checksum': tun_config.get('csum', False),
                    'use_sequence': tun_config.get('seq', False),
                    'mtu': iface_config['mtu'],
                    'keepalive_interval': tun_config.get('ka', 10),
                    'description': tun_config.get('desc', '')
                })

    async def start_gre_tunnels(self):
        """Initialize GRE tunnels from config"""
        if not hasattr(self, 'gre_tunnels') or not self.gre_tunnels:
            return

        logger = logging.getLogger("WontYouBeMyNeighbor")
        logger.info(f"Starting {len(self.gre_tunnels)} GRE tunnel(s)")

        try:
            from gre import configure_gre_manager, GRETunnelConfig

            agent_id = os.environ.get('ASI_AGENT_ID', 'local')

            for tun in self.gre_tunnels:
                if not tun.get('remote_ip'):
                    logger.warning(f"GRE tunnel {tun['name']} missing remote_ip, skipping")
                    continue

                # Get local IP from config or first non-GRE interface
                local_ip = tun.get('local_ip')
                if not local_ip:
                    for iface in self.interfaces:
                        if iface['type'] != 'gre' and iface['addresses']:
                            local_ip = iface['addresses'][0].split('/')[0]
                            break

                if not local_ip:
                    logger.warning(f"GRE tunnel {tun['name']} could not determine local_ip, skipping")
                    continue

                # Create or get GRE manager
                manager = configure_gre_manager(agent_id, local_ip)
                if not manager.running:
                    await manager.start()

                # Create tunnel config
                config = GRETunnelConfig(
                    name=tun['name'],
                    local_ip=local_ip,
                    remote_ip=tun['remote_ip'],
                    tunnel_ip=tun.get('tunnel_ip', ''),
                    key=tun.get('key'),
                    use_checksum=tun.get('use_checksum', False),
                    use_sequence=tun.get('use_sequence', False),
                    mtu=tun.get('mtu', 1400),
                    keepalive_interval=tun.get('keepalive_interval', 10),
                    description=tun.get('description', '')
                )

                # Create the tunnel
                tunnel = await manager.create_tunnel(config)
                if tunnel:
                    logger.info(f"GRE tunnel {tun['name']} started: {local_ip} -> {tun['remote_ip']}")
                else:
                    logger.error(f"Failed to create GRE tunnel {tun['name']}")

        except ImportError as e:
            logger.warning(f"GRE module not available: {e}")
        except Exception as e:
            logger.error(f"Error starting GRE tunnels: {e}")

    def load_config_from_env(self):
        """Load agent config from environment variable"""
        import os
        import json
        config_json = os.environ.get('ASI_AGENT_CONFIG')
        if config_json:
            try:
                config = json.loads(config_json)
                self.set_config(config)
                logging.getLogger("WontYouBeMyNeighbor").info(
                    f"Loaded config from environment: {len(self.interfaces)} interfaces"
                )
            except json.JSONDecodeError as e:
                logging.getLogger("WontYouBeMyNeighbor").warning(
                    f"Failed to parse ASI_AGENT_CONFIG: {e}"
                )


class RouteRedistributor:
    """
    Universal route redistribution between any combination of routing protocols.
    Automatically handles: OSPF ↔ BGP ↔ IS-IS ↔ Static routes
    Runs on any router with multiple protocols enabled.
    """

    def __init__(self, router_id: str, local_ip: str,
                 ospf_agent: "OSPFAgent" = None,
                 bgp_speaker: BGPSpeaker = None,
                 isis_speaker = None,
                 static_routes: List[dict] = None):
        self.router_id = router_id
        self.local_ip = local_ip
        self.ospf_agent = ospf_agent
        self.bgp_speaker = bgp_speaker
        self.isis_speaker = isis_speaker
        self.static_routes = static_routes or []
        self.logger = logging.getLogger("Redistribution")
        self.running = False

        # Track route origins to prevent loops
        # Format: {prefix: "source_protocol"}
        self.route_origins: Dict[str, str] = {}

        # Track what's been redistributed to each protocol
        self.redistributed_to: Dict[str, set] = {
            "ospf": set(),
            "bgp": set(),
            "isis": set()
        }

        # Determine active protocols
        self.active_protocols = []
        if ospf_agent:
            self.active_protocols.append("ospf")
        if bgp_speaker:
            self.active_protocols.append("bgp")
        if isis_speaker:
            self.active_protocols.append("isis")

    async def start(self) -> None:
        """Start universal route redistribution loop"""
        self.running = True

        if len(self.active_protocols) < 2:
            self.logger.info("Only one protocol active - redistribution not needed")
            return

        self.logger.info("="*60)
        self.logger.info("  Universal Route Redistribution Enabled")
        self.logger.info(f"  Active protocols: {', '.join(p.upper() for p in self.active_protocols)}")
        self.logger.info("  Bidirectional redistribution between all protocols")
        self.logger.info("="*60)

        while self.running:
            try:
                # Collect routes from all protocols
                all_routes = await self._collect_all_routes()

                # Redistribute to each protocol
                for target_protocol in self.active_protocols:
                    await self._redistribute_to_protocol(target_protocol, all_routes)

                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                self.logger.error(f"Redistribution error: {e}")
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop redistribution"""
        self.running = False

    async def _collect_all_routes(self) -> List[dict]:
        """
        Collect routes from all active protocols.

        Returns:
            List of route dicts with keys: prefix, next_hop, metric, source, origin_protocol
        """
        all_routes = []

        # Collect OSPF routes
        if self.ospf_agent:
            try:
                routing_table = self.ospf_agent.spf_calc.routing_table
                for prefix, route_info in routing_table.items():
                    # Skip routes to self
                    if route_info.next_hop == self.router_id:
                        continue

                    # Skip routes that we redistributed FROM another protocol
                    # This prevents loops like: BGP → OSPF → BGP
                    if prefix in self.redistributed_to.get("ospf", set()):
                        continue

                    all_routes.append({
                        "prefix": prefix,
                        "next_hop": route_info.next_hop,
                        "metric": route_info.cost,
                        "source": "ospf",
                        "origin_protocol": "ospf"
                    })
                    self.route_origins[prefix] = "ospf"
            except Exception as e:
                self.logger.debug(f"Error collecting OSPF routes: {e}")

        # Collect BGP routes
        if self.bgp_speaker:
            try:
                bgp_routes = self.bgp_speaker.agent.loc_rib.get_all_routes()
                for route in bgp_routes:
                    # Skip locally originated routes (including redistributed routes)
                    if route.peer_id == "local":
                        continue

                    # Skip routes that we redistributed FROM another protocol
                    # This prevents loops like: OSPF → BGP → OSPF
                    if route.prefix in self.redistributed_to.get("bgp", set()):
                        continue

                    # Extract next-hop using the BGPRoute.next_hop property
                    # This correctly handles both IPv4 (NEXT_HOP attr) and IPv6 (_ipv6_next_hop)
                    next_hop = route.next_hop or self.local_ip
                    all_routes.append({
                        "prefix": route.prefix,
                        "next_hop": next_hop,
                        "metric": 20,  # Default external metric
                        "source": "bgp",
                        "origin_protocol": "bgp"
                    })
                    self.route_origins[route.prefix] = "bgp"
            except Exception as e:
                self.logger.debug(f"Error collecting BGP routes: {e}")

        # Collect IS-IS routes
        if self.isis_speaker:
            try:
                # IS-IS routes from SPF calculation using get_routes() method
                if hasattr(self.isis_speaker, 'get_routes'):
                    isis_routes = self.isis_speaker.get_routes()
                    for route in isis_routes:
                        # Skip external routes (already redistributed into IS-IS)
                        if hasattr(route, 'route_type') and route.route_type == "external":
                            continue
                        all_routes.append({
                            "prefix": route.prefix,
                            "next_hop": route.next_hop,
                            "metric": route.metric,
                            "source": "isis",
                            "origin_protocol": "isis"
                        })
                        self.route_origins[route.prefix] = "isis"
            except Exception as e:
                self.logger.debug(f"Error collecting IS-IS routes: {e}")

        # Add static routes
        for static in self.static_routes:
            prefix = static.get("prefix")
            if prefix:
                all_routes.append({
                    "prefix": prefix,
                    "next_hop": static.get("next_hop", self.local_ip),
                    "metric": static.get("metric", 1),
                    "source": "static",
                    "origin_protocol": "static"
                })
                self.route_origins[prefix] = "static"

        return all_routes

    async def _redistribute_to_protocol(self, target: str, routes: List[dict]):
        """
        Redistribute routes to a target protocol.

        Args:
            target: Target protocol name (ospf, bgp, isis)
            routes: List of route dictionaries
        """
        for route in routes:
            prefix = route["prefix"]
            source = route["source"]

            # Don't redistribute back to source protocol (avoid loops)
            if source == target:
                continue

            # Skip if already redistributed to this target
            if prefix in self.redistributed_to[target]:
                continue

            # Skip if this route was originally from the target (loop prevention)
            original_source = self.route_origins.get(prefix)
            if original_source == target:
                continue

            try:
                success = False

                if target == "ospf":
                    success = await self._inject_into_ospf(route)
                elif target == "bgp":
                    success = await self._inject_into_bgp(route)
                elif target == "isis":
                    success = await self._inject_into_isis(route)

                if success:
                    self.redistributed_to[target].add(prefix)
                    self.logger.info(f"✓ Redistributed {source.upper()}→{target.upper()}: {prefix}")

            except Exception as e:
                self.logger.error(f"Failed to redistribute {prefix} to {target}: {e}")

    async def _inject_into_ospf(self, route: dict) -> bool:
        """Inject route into OSPF as External LSA"""
        if not self.ospf_agent:
            return False

        prefix = route["prefix"]

        # Parse prefix to get network and mask
        if '/' in prefix:
            network, prefix_len = prefix.split('/')
            prefix_len = int(prefix_len)
        else:
            network = prefix
            prefix_len = 32

        # Convert prefix length to dotted decimal mask
        mask_int = (0xffffffff << (32 - prefix_len)) & 0xffffffff
        mask = f"{(mask_int >> 24) & 0xff}.{(mask_int >> 16) & 0xff}.{(mask_int >> 8) & 0xff}.{mask_int & 0xff}"

        # Metric based on source: static=50, isis=100, bgp=150
        source_metrics = {"static": 50, "isis": 100, "bgp": 150}
        metric = source_metrics.get(route["source"], 150)

        # Install External LSA
        success = self.ospf_agent.lsdb.install_external_lsa(
            router_id=self.router_id,
            prefix=network,
            mask=mask,
            metric=metric,
            forwarding_address=self.local_ip,
            external_type=2
        )

        if success:
            # Flood to neighbors
            await self.ospf_agent._flood_our_lsas_to_all_neighbors()

        return success

    async def _inject_into_bgp(self, route: dict) -> bool:
        """Inject route into BGP"""
        if not self.bgp_speaker:
            return False

        from bgp.constants import ORIGIN_INCOMPLETE

        return self.bgp_speaker.agent.originate_route(
            route["prefix"],
            next_hop=self.local_ip,
            local_pref=100,
            origin=ORIGIN_INCOMPLETE
        )

    async def _inject_into_isis(self, route: dict) -> bool:
        """Inject route into IS-IS as external route"""
        if not self.isis_speaker:
            return False

        try:
            # IS-IS external route injection
            if hasattr(self.isis_speaker, 'redistribute_route'):
                return self.isis_speaker.redistribute_route(
                    route["prefix"],
                    metric=route.get("metric", 64),
                    metric_type="external"
                )
        except Exception as e:
            self.logger.debug(f"IS-IS redistribution not available: {e}")

        return False

    def get_statistics(self) -> dict:
        """Get redistribution statistics"""
        return {
            "active_protocols": self.active_protocols,
            "route_origins": len(self.route_origins),
            "redistributed": {
                proto: len(prefixes)
                for proto, prefixes in self.redistributed_to.items()
            }
        }


class OSPFAgent:
    """
    Main OSPF Agent orchestrating all components
    """

    def __init__(self, router_id: str, area_id: str, interface: str,
                 hello_interval: int = 10, dead_interval: int = 40,
                 network_type: str = DEFAULT_NETWORK_TYPE,
                 source_ip: Optional[str] = None,
                 unicast_peer: Optional[str] = None,
                 kernel_route_manager: Optional[KernelRouteManager] = None):
        """
        Initialize OSPF agent

        Args:
            router_id: Router ID (e.g., "10.255.255.99")
            area_id: OSPF area (e.g., "0.0.0.0")
            interface: Network interface (e.g., "eth0")
            hello_interval: Hello packet interval (seconds)
            dead_interval: Neighbor dead interval (seconds)
            network_type: Network type (broadcast, point-to-multipoint, point-to-point)
            source_ip: Optional specific source IP to use (for multi-IP interfaces)
            unicast_peer: Optional unicast peer IP for point-to-point (bypasses multicast)
            kernel_route_manager: Optional kernel route manager for installing routes
        """
        self.router_id = router_id
        self.area_id = area_id
        self.interface = interface
        self.hello_interval = hello_interval
        self.dead_interval = dead_interval
        self.network_type = network_type
        self.unicast_peer = unicast_peer
        self.kernel_route_manager = kernel_route_manager

        # Get interface info (with optional source IP)
        self.interface_info = get_interface_info(interface, source_ip)
        if not self.interface_info:
            raise ValueError(f"Invalid interface: {interface}")

        self.source_ip = self.interface_info.ip_address
        self.netmask = self.interface_info.netmask

        # Components
        self.socket = OSPFSocket(interface, self.source_ip)
        self.hello_handler = HelloHandler(
            router_id, area_id, interface, self.netmask,
            hello_interval, dead_interval, network_type=network_type
        )
        self.lsdb = LinkStateDatabase(area_id)
        self.spf_calc = SPFCalculator(router_id, self.lsdb)
        self.adjacency_mgr = AdjacencyManager(router_id, self.lsdb)
        self.flooding_mgr = LSAFloodingManager(router_id, self.lsdb)

        # Neighbors
        self.neighbors: Dict[str, OSPFNeighbor] = {}

        # State
        self.running = False
        self.logger = logging.getLogger("OSPFAgent")

        # Setup callbacks
        self.hello_handler.on_neighbor_discovered = self._on_neighbor_discovered
        self.hello_handler.on_hello_received = self._on_hello_received

        self.logger.info(f"Initialized OSPF Agent: {router_id} on {interface} ({self.source_ip})")

    @property
    def stats(self):
        """Get combined message statistics from all handlers"""
        return self.hello_handler.stats if self.hello_handler else {}

    async def start(self):
        """
        Start OSPF agent
        """
        self.logger.info("="*70)
        self.logger.info("Starting OSPF Agent")
        self.logger.info("="*70)
        self.logger.info(f"  Router ID: {self.router_id}")
        self.logger.info(f"  Area: {self.area_id}")
        self.logger.info(f"  Interface: {self.interface}")
        self.logger.info(f"  IP: {self.source_ip}")
        self.logger.info(f"  Netmask: {self.netmask}")
        if self.unicast_peer:
            self.logger.info(f"  Unicast Peer: {self.unicast_peer} (UNICAST MODE)")
        self.logger.info("="*70)

        # Open socket
        if not self.socket.open():
            self.logger.error("Failed to open OSPF socket")
            return

        # Join multicast group
        if not self.socket.join_multicast():
            self.logger.error("Failed to join multicast group")
            return

        # Generate our own Router LSA
        self._generate_router_lsa()

        # Start running
        self.running = True

        # Start async tasks
        try:
            await asyncio.gather(
                self._hello_loop(),
                self._receive_loop(),
                self._aging_loop(),
                self._spf_loop(),
                self._monitor_neighbors(),
                self._retransmission_loop()
            )
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        finally:
            await self.stop()

    async def stop(self):
        """
        Stop OSPF agent gracefully
        """
        self.logger.info("Stopping OSPF Agent...")
        self.running = False
        self.socket.close()
        self.logger.info("OSPF Agent stopped")

    async def _hello_loop(self):
        """
        Send Hello packets periodically
        """
        while self.running:
            try:
                # Build Hello with current neighbor list from OSPFNeighbor objects
                # Filter for neighbors at least in Init state to include in Hello packet

                # DEBUG: Log all neighbors and their states
                self.logger.debug(f"Hello loop: Total neighbors in dict: {len(self.neighbors)}")
                for nid, n in self.neighbors.items():
                    state = n.get_state()
                    state_name = n.get_state_name()
                    passes_filter = state >= STATE_INIT
                    self.logger.debug(f"  Neighbor {nid}: state={state_name} ({state}), "
                                    f">= STATE_INIT({STATE_INIT})? {passes_filter}")

                active_neighbor_ids = [
                    nid for nid, n in self.neighbors.items()
                    if n.get_state() >= STATE_INIT
                ]

                self.logger.debug(f"Active neighbors for Hello packet: {active_neighbor_ids}")

                # Build and send Hello with proper neighbor list
                hello_pkt = self.hello_handler.build_hello_packet(
                    active_neighbors=active_neighbor_ids
                )

                # Send to unicast peer if specified, otherwise multicast
                if self.unicast_peer:
                    self.socket.send(hello_pkt, dest=self.unicast_peer)
                    self.logger.info(f"Sent Hello to {self.unicast_peer} with {len(active_neighbor_ids)} neighbors: {active_neighbor_ids}")
                else:
                    self.socket.send(hello_pkt)
                    self.logger.info(f"Sent Hello with {len(active_neighbor_ids)} neighbors: {active_neighbor_ids}")

                # Wait for next interval
                await asyncio.sleep(self.hello_interval)

            except Exception as e:
                self.logger.error(f"Hello loop error: {e}")
                await asyncio.sleep(1)

    async def _receive_loop(self):
        """
        Receive and process OSPF packets
        """
        while self.running:
            try:
                # Receive packet with DSCP value for QoS ingress trust
                result = self.socket.receive_with_dscp(timeout=0.5)
                if not result:
                    # Yield control to event loop to allow other tasks to run
                    await asyncio.sleep(0)
                    continue

                data, source_ip, dscp_value = result

                # QoS Ingress Trust - respect DSCP marking from other agents
                try:
                    from agentic.protocols.qos import get_qos_manager
                    import os
                    qos_agent_id = os.environ.get("ASI_AGENT_ID", "local")
                    qos_mgr = get_qos_manager(qos_agent_id)
                    if qos_mgr and qos_mgr.enabled and dscp_value > 0:
                        service_class, trusted = qos_mgr.trust_ingress(dscp_value, self.interface)
                        if trusted:
                            self.logger.debug(f"[QoS] Ingress trust: DSCP={dscp_value} -> {service_class.value} from {source_ip}")
                except ImportError:
                    pass  # QoS module not available
                except Exception as qos_err:
                    self.logger.debug(f"[QoS] Ingress trust error: {qos_err}")

                # Process packet
                await self._process_packet(data, source_ip)

                # Yield control to event loop after processing to allow other tasks to run
                await asyncio.sleep(0)

            except Exception as e:
                self.logger.error(f"Receive loop error: {e}")
                await asyncio.sleep(0.1)

    async def _process_packet(self, data: bytes, source_ip: str):
        """
        Process received OSPF packet

        Args:
            data: Packet bytes
            source_ip: Source IP address
        """
        try:
            # Parse packet
            packet = parse_ospf_packet(data)
            if not packet:
                return

            # Enhanced debugging for Router ID conflicts
            self.logger.debug(f"Received packet: Type={packet.type}, "
                            f"RouterID={packet.router_id}, "
                            f"SourceIP={source_ip}, "
                            f"OurRouterID={self.router_id}, "
                            f"OurIP={self.source_ip}")

            # Ignore packets from ourselves (safety check for multicast loopback)
            if packet.router_id == self.router_id:
                self.logger.warning(f"!!! Router ID CONFLICT: Received packet from {source_ip} "
                                  f"with same Router ID as us ({packet.router_id})! "
                                  f"Check if router at {source_ip} is configured with Router ID {packet.router_id}")
                return

            # Ignore packets from our own IP address
            if source_ip == self.source_ip:
                self.logger.debug(f"Ignoring packet from own IP ({source_ip})")
                return

            # Route by packet type
            packet_type = packet.type

            if packet_type == HELLO_PACKET:
                self.hello_handler.process_hello(data, source_ip)

            elif packet_type == DATABASE_DESCRIPTION:
                self.logger.debug(f"Received DBD from {source_ip}")
                await self._process_dbd(data, packet.router_id)

            elif packet_type == LINK_STATE_REQUEST:
                self.logger.debug(f"Received LSR from {source_ip}")
                await self._process_lsr(data, packet.router_id)

            elif packet_type == LINK_STATE_UPDATE:
                self.logger.debug(f"Received LSU from {source_ip}")
                await self._process_lsu(data, packet.router_id)

            elif packet_type == LINK_STATE_ACK:
                self.logger.debug(f"Received LSAck from {source_ip}")
                await self._process_lsack(data, packet.router_id)

        except Exception as e:
            self.logger.error(f"Error processing packet from {source_ip}: {e}")

    async def _aging_loop(self):
        """
        Age LSAs and remove expired ones
        """
        while self.running:
            try:
                # Age LSAs
                aged_count = self.lsdb.age_lsas()

                if aged_count > 0:
                    self.logger.info(f"Aged out {aged_count} LSAs")
                    # Run SPF after aging out LSAs
                    await self._run_spf()

                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Aging loop error: {e}")
                await asyncio.sleep(1)

    async def _spf_loop(self):
        """
        Periodically recalculate SPF
        """
        # Wait a bit before first calculation
        await asyncio.sleep(5)

        while self.running:
            try:
                await self._run_spf()
                await asyncio.sleep(30)  # Run every 30 seconds

            except Exception as e:
                self.logger.error(f"SPF loop error: {e}")
                await asyncio.sleep(5)

    async def _monitor_neighbors(self):
        """
        Monitor neighbors for inactivity
        """
        while self.running:
            try:
                # Check for dead neighbors in Hello handler
                dead = self.hello_handler.check_dead_neighbors()

                # Kill dead neighbors in our neighbor list
                for neighbor_id in dead:
                    if neighbor_id in self.neighbors:
                        neighbor = self.neighbors[neighbor_id]
                        neighbor.kill()
                        self.logger.warning(f"Neighbor {neighbor_id} killed (inactivity)")

                # Check inactivity for each neighbor
                for neighbor_id, neighbor in list(self.neighbors.items()):
                    if neighbor.check_inactivity(self.dead_interval):
                        self.logger.warning(f"Neighbor {neighbor_id} timed out")

                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1)

    async def _retransmission_loop(self):
        """
        Check for LSAs needing retransmission (RFC 2328 Section 13.7)
        """
        while self.running:
            try:
                # Check each neighbor's retransmission list
                for neighbor_id, neighbor in list(self.neighbors.items()):
                    # Only retransmit to Full neighbors
                    if neighbor.get_state() != STATE_FULL:
                        continue

                    # Get LSAs needing retransmission
                    lsas_to_retransmit = self.flooding_mgr.get_lsas_needing_retransmission(neighbor)

                    if lsas_to_retransmit:
                        self.logger.info(f"Retransmitting {len(lsas_to_retransmit)} LSAs to {neighbor_id}")

                        # Build and send LSU with LSAs needing retransmission
                        lsu_packet = self.flooding_mgr.build_ls_update(
                            lsas_to_retransmit, self.area_id
                        )

                        if lsu_packet:
                            self.socket.send(lsu_packet, dest=neighbor.ip_address)
                            self.logger.debug(f"Sent retransmission LSU to {neighbor_id} "
                                            f"with {len(lsas_to_retransmit)} LSAs")

                # Check every 5 seconds (matches retransmit_interval)
                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error(f"Retransmission loop error: {e}")
                await asyncio.sleep(1)

    async def _run_spf(self):
        """
        Run SPF calculation and install routes into kernel
        """
        try:
            self.spf_calc.calculate()
            stats = self.spf_calc.get_statistics()

            self.logger.info(f"SPF complete: {stats['routes']} routes, "
                           f"{stats['nodes']} nodes, {stats['edges']} edges")

            # Print routing table
            if stats['routes'] > 0:
                self.spf_calc.print_routing_table()

            # Install routes into kernel if route manager is available
            if self.kernel_route_manager and stats['routes'] > 0:
                for prefix, route_info in self.spf_calc.routing_table.items():
                    # next_hop from SPF is the router ID, not the interface IP
                    # We need to resolve it to the actual interface IP via neighbor table
                    next_hop_router_id = route_info.next_hop
                    cost = route_info.cost

                    if not next_hop_router_id or next_hop_router_id == self.router_id:
                        continue  # Skip routes to self

                    # Resolve router ID to interface IP using neighbor table
                    actual_gateway = None
                    if next_hop_router_id in self.neighbors:
                        neighbor = self.neighbors[next_hop_router_id]
                        actual_gateway = neighbor.ip_address
                        self.logger.debug(f"Resolved next-hop {next_hop_router_id} -> {actual_gateway}")
                    else:
                        # Fallback strategies for resolving next-hop:
                        # 1. Check if next_hop looks like an IP address already
                        import ipaddress
                        try:
                            ip_obj = ipaddress.ip_address(next_hop_router_id)
                            # If it's a valid IP and not the same as our router ID, use it directly
                            actual_gateway = str(ip_obj)
                            self.logger.debug(f"Using next-hop {next_hop_router_id} as IP address directly")
                        except ValueError:
                            pass

                        # 2. Try to find neighbor by scanning LSDB for router LSA links
                        if not actual_gateway and hasattr(self, 'lsdb'):
                            for lsa in self.lsdb.get_lsas_by_type(1):  # Router LSAs
                                if lsa.header.advertising_router == next_hop_router_id:
                                    # Found the router - check its links for a point-to-point link back to us
                                    for link in getattr(lsa, 'links', []):
                                        if hasattr(link, 'link_data') and link.link_data:
                                            # link_data often contains the interface IP
                                            actual_gateway = str(link.link_data)
                                            self.logger.debug(f"Resolved next-hop {next_hop_router_id} -> {actual_gateway} via LSDB")
                                            break
                                if actual_gateway:
                                    break

                        if not actual_gateway:
                            self.logger.warning(f"Cannot resolve next-hop router ID {next_hop_router_id} "
                                              f"to interface IP - neighbor not found, trying direct router ID")
                            # Last resort: try using the router ID itself as the gateway
                            # This works if router IDs are actual reachable IPs (common in lab setups)
                            actual_gateway = next_hop_router_id

                    if actual_gateway and actual_gateway != self.source_ip:
                        success = self.kernel_route_manager.install_route(
                            prefix, actual_gateway, metric=cost, protocol="ospf"
                        )
                        if not success:
                            self.logger.warning(f"Failed to install route {prefix}: "
                                              f"Error: Nexthop has invalid gateway.")

        except Exception as e:
            self.logger.error(f"SPF calculation error: {e}")

    async def _flood_our_lsas_to_neighbor(self, neighbor: OSPFNeighbor):
        """
        Flood our own LSAs to a newly Full neighbor

        Args:
            neighbor: Neighbor to send our LSAs to
        """
        try:
            # Get all our own LSAs (where we are the advertising router)
            our_lsas = [lsa for lsa in self.lsdb.get_all_lsas()
                       if lsa.header.advertising_router == self.router_id]

            if not our_lsas:
                self.logger.debug(f"No LSAs to flood to {neighbor.router_id}")
                return

            self.logger.info(f"Flooding {len(our_lsas)} of our LSAs to {neighbor.router_id}")

            # Build LSU packet with our LSAs
            lsu_packet = self.flooding_mgr.build_ls_update(our_lsas, self.area_id)

            if lsu_packet:
                self.socket.send(lsu_packet, dest=neighbor.ip_address)
                self.logger.debug(f"Sent LSU with {len(our_lsas)} LSAs to {neighbor.router_id}")

        except Exception as e:
            self.logger.error(f"Error flooding LSAs to {neighbor.router_id}: {e}")

    async def _flood_our_lsas_to_all_neighbors(self):
        """
        Flood our own LSAs to all Full neighbors
        """
        try:
            # Get all our own LSAs
            our_lsas = [lsa for lsa in self.lsdb.get_all_lsas()
                       if lsa.header.advertising_router == self.router_id]

            if not our_lsas:
                self.logger.debug("No LSAs to flood")
                return

            # Get all Full neighbors
            full_neighbors = [n for n in self.neighbors.values() if n.is_full()]

            if not full_neighbors:
                self.logger.debug("No Full neighbors to flood to")
                return

            self.logger.info(f"Flooding {len(our_lsas)} of our LSAs to {len(full_neighbors)} Full neighbors")

            # Build LSU packet
            lsu_packet = self.flooding_mgr.build_ls_update(our_lsas, self.area_id)

            if lsu_packet:
                # Send to each Full neighbor
                for neighbor in full_neighbors:
                    self.socket.send(lsu_packet, dest=neighbor.ip_address)
                    self.logger.debug(f"Sent LSU to {neighbor.router_id}")

        except Exception as e:
            self.logger.error(f"Error flooding LSAs to all neighbors: {e}")

    def _generate_router_lsa(self):
        """
        Generate our own Router LSA and add to LSDB
        Includes P2P links to Full neighbors and stub link for our /32
        """
        from ospf.constants import LINK_TYPE_PTP

        links = []

        # Add P2P links to all Full neighbors
        for neighbor_id, neighbor in self.neighbors.items():
            if neighbor.is_full():
                # Point-to-point link
                links.append({
                    'link_id': neighbor.router_id,      # Neighbor's Router ID
                    'link_data': self.source_ip,         # Our interface IP
                    'link_type': LINK_TYPE_PTP,
                    'metric': 10
                })
                self.logger.debug(f"Added P2P link to {neighbor.router_id} in Router LSA")

        # Add stub link for our /32 loopback/host route
        links.append({
            'link_id': self.router_id,
            'link_data': '255.255.255.255',  # /32 mask
            'link_type': LINK_TYPE_STUB,
            'metric': 1
        })

        # Install Router LSA
        self.lsdb.install_router_lsa(self.router_id, links)

        self.logger.info(f"Generated Router LSA for {self.router_id} with {len(links)} links")

    def _on_neighbor_discovered(self, neighbor_id: str, ip: str, priority: int):
        """
        Callback when new neighbor is discovered

        Args:
            neighbor_id: Neighbor router ID
            ip: Neighbor IP address
            priority: Neighbor priority
        """
        if neighbor_id not in self.neighbors:
            neighbor = OSPFNeighbor(neighbor_id, ip, priority, network_type=self.network_type)
            self.neighbors[neighbor_id] = neighbor
            self.logger.info(f"New neighbor discovered: {neighbor_id} ({ip})")

    def _on_hello_received(self, neighbor_id: str, ip: str, bidirectional: bool, hello_pkt):
        """
        Callback when Hello is received

        Args:
            neighbor_id: Neighbor router ID
            ip: Neighbor IP address
            bidirectional: True if we're in their neighbor list
            hello_pkt: Hello packet object
        """
        # Get or create neighbor
        if neighbor_id not in self.neighbors:
            neighbor = OSPFNeighbor(neighbor_id, ip, hello_pkt.router_priority, network_type=self.network_type)
            self.neighbors[neighbor_id] = neighbor
        else:
            neighbor = self.neighbors[neighbor_id]

        # Update neighbor FSM
        old_state = neighbor.get_state()
        neighbor.handle_hello_received(bidirectional)
        new_state = neighbor.get_state()

        if old_state != new_state:
            self.logger.info(f"Neighbor {neighbor_id}: "
                           f"{STATE_NAMES[old_state]} → {STATE_NAMES[new_state]}")

            # Handle state transitions
            if new_state == STATE_EXSTART:
                self.logger.info(f"Transitioning to ExStart, starting database exchange...")
                neighbor.start_database_exchange(self.router_id)
                # Send initial DBD packet
                try:
                    asyncio.create_task(self._send_initial_dbd(neighbor))
                    self.logger.debug(f"Created task to send initial DBD to {neighbor_id}")
                except Exception as e:
                    self.logger.error(f"Failed to create DBD task: {e}")

            elif new_state == STATE_FULL:
                self.logger.info(f"✓ Adjacency FULL with {neighbor_id}")
                # Regenerate our Router LSA (now includes P2P link to this neighbor)
                self._generate_router_lsa()
                # Flood our updated LSAs to ALL Full neighbors
                asyncio.create_task(self._flood_our_lsas_to_all_neighbors())
                # Run SPF
                asyncio.create_task(self._run_spf())

    async def _process_dbd(self, data: bytes, neighbor_id: str):
        """
        Process Database Description packet

        Args:
            data: Packet bytes
            neighbor_id: Neighbor router ID
        """
        if neighbor_id not in self.neighbors:
            self.logger.warning(f"Received DBD from unknown neighbor {neighbor_id}")
            return

        neighbor = self.neighbors[neighbor_id]
        current_state = neighbor.get_state()

        # Process DBD
        success, lsa_headers_needed, neighbor_dbd_complete = self.adjacency_mgr.process_dbd(data, neighbor)

        if not success:
            self.logger.warning(f"Failed to process DBD from {neighbor_id}")
            return

        # Add needed LSAs to request list
        if lsa_headers_needed:
            neighbor.ls_request_list.extend(lsa_headers_needed)
            self.logger.info(f"Added {len(lsa_headers_needed)} LSAs to request list for {neighbor_id}")
            self.logger.info(f"ls_request_list now has {len(neighbor.ls_request_list)} LSAs")

        # Track neighbor's DBD completion (M=0 received)
        if neighbor_dbd_complete:
            neighbor.mark_neighbor_dbd_complete()
            self.logger.info(f"Received final DBD from {neighbor_id} (M=0)")
            # Check if exchange is complete (both sides finished)
            if neighbor.is_exchange_complete():
                self.logger.info(f"Exchange complete with {neighbor_id}, transitioning state")
                neighbor.exchange_done()

        # Handle state transitions
        new_state = neighbor.get_state()
        if current_state != new_state:
            self.logger.info(f"Neighbor {neighbor_id}: "
                           f"{STATE_NAMES[current_state]} → {STATE_NAMES[new_state]}")

            if new_state == STATE_EXCHANGE:
                # Transitioning from ExStart to Exchange
                # If we're slave, we need to send a slave acknowledgment DBD first
                if current_state == STATE_EXSTART and not neighbor.is_master:
                    # Send slave acknowledgment DBD (empty, with M=1)
                    self.logger.info(f"Sending slave ack DBD to {neighbor_id}")
                    slave_ack = self.adjacency_mgr.build_slave_ack_dbd_packet(
                        neighbor, self.area_id
                    )
                    self.socket.send(slave_ack, dest=neighbor.ip_address)
                else:
                    # Start sending our DBD packets (with LSA headers)
                    await self._send_dbd(neighbor)

            elif new_state == STATE_LOADING:
                # Start requesting LSAs
                await self._send_lsr(neighbor)

            elif new_state == STATE_FULL:
                self.logger.info(f"✓ Adjacency FULL with {neighbor_id}")
                self._generate_router_lsa()
                await self._flood_our_lsas_to_all_neighbors()
                await self._run_spf()

        # Continue exchanging DBD packets if still in Exchange state
        elif new_state == STATE_EXCHANGE:
            # In Exchange state, we must respond to each received DBD
            # This is the request/response nature of OSPF DBD exchange
            await self._send_dbd(neighbor)

            # CRITICAL: _send_dbd() may call exchange_done() which transitions to Loading
            # We need to check if state changed and send LSR if needed
            post_dbd_state = neighbor.get_state()
            if post_dbd_state == STATE_LOADING:
                self.logger.info(f"Transitioned to Loading after sending final DBD")
                await self._send_lsr(neighbor)
            elif post_dbd_state == STATE_FULL:
                self.logger.info(f"✓ Adjacency FULL with {neighbor_id} (direct from Exchange)")
                self._generate_router_lsa()
                await self._flood_our_lsas_to_all_neighbors()
                await self._run_spf()

        # Handle duplicate DBD in Loading/Full (retransmission from master)
        elif new_state in (STATE_LOADING, STATE_FULL) and success:
            # We're slave and received a duplicate DBD - respond to acknowledge
            self.logger.info(f"Responding to duplicate DBD from {neighbor_id}")
            await self._send_dbd(neighbor)

    async def _process_lsr(self, data: bytes, neighbor_id: str):
        """
        Process Link State Request packet

        Args:
            data: Packet bytes
            neighbor_id: Neighbor router ID
        """
        if neighbor_id not in self.neighbors:
            self.logger.warning(f"Received LSR from unknown neighbor {neighbor_id}")
            return

        neighbor = self.neighbors[neighbor_id]

        # Process LSR and build LSU response
        lsu_packet = self.flooding_mgr.process_ls_request(data, neighbor, self.area_id)

        if lsu_packet:
            # Send LSU unicast to neighbor
            self.socket.send(lsu_packet, dest=neighbor.ip_address)
            self.logger.debug(f"Sent LSU to {neighbor_id} in response to LSR")

    async def _process_lsu(self, data: bytes, neighbor_id: str):
        """
        Process Link State Update packet

        Args:
            data: Packet bytes
            neighbor_id: Neighbor router ID
        """
        if neighbor_id not in self.neighbors:
            self.logger.warning(f"Received LSU from unknown neighbor {neighbor_id}")
            return

        neighbor = self.neighbors[neighbor_id]
        state_before_lsu = neighbor.get_state()

        # Process LSU - returns (success, ack_packet, updated_lsas)
        success, ack_packet, updated_lsas = self.flooding_mgr.process_ls_update(data, neighbor)

        if success:
            # Send LSAck if needed (unicast to neighbor)
            if ack_packet:
                self.socket.send(ack_packet, dest=neighbor.ip_address)
                self.logger.debug(f"Sent LSAck to {neighbor_id}")

            # Separate self-originated LSAs from others (RFC 2328 Section 13.4)
            self_originated_lsas = []
            external_lsas = []
            for lsa in updated_lsas:
                if lsa.header.advertising_router == self.router_id:
                    self_originated_lsas.append(lsa)
                else:
                    external_lsas.append(lsa)

            # Handle self-originated LSAs specially - re-originate with higher seq
            if self_originated_lsas:
                self.logger.info(f"Received {len(self_originated_lsas)} self-originated LSAs - re-originating")
                # Our own LSA came back with potentially higher seq, regenerate
                self._generate_router_lsa()
                await self._flood_our_lsas_to_all_neighbors()

            # Flood external LSAs to other neighbors (RFC 2328 Section 13.3)
            if external_lsas:
                self.logger.info(f"Flooding {len(external_lsas)} external LSAs to other neighbors")
                for lsa in external_lsas:
                    # Get all neighbors as list
                    neighbor_list = list(self.neighbors.values())

                    # Flood to all neighbors except sender
                    lsu_packets = self.flooding_mgr.flood_lsa_to_neighbors(
                        lsa, neighbor_list, self.area_id, exclude_neighbor=neighbor
                    )

                    # Send LSU packets unicast to each neighbor
                    for target_neighbor, lsu_packet in lsu_packets:
                        self.socket.send(lsu_packet, dest=target_neighbor.ip_address)
                        self.logger.debug(f"Flooded LSA to {target_neighbor.router_id}")

            # Run SPF if any LSAs were updated
            if updated_lsas:
                await self._run_spf()

            # Only regenerate Router LSA if state TRANSITIONED to Full
            # (not on every LSU when already Full - that causes flooding loop)
            state_after_lsu = neighbor.get_state()
            if state_after_lsu == STATE_FULL and state_before_lsu != STATE_FULL:
                self.logger.info(f"✓ Adjacency TRANSITIONED to FULL with {neighbor_id}")
                self._generate_router_lsa()
                await self._flood_our_lsas_to_all_neighbors()
                await self._run_spf()

    async def _process_lsack(self, data: bytes, neighbor_id: str):
        """
        Process Link State Acknowledgment packet

        Args:
            data: Packet bytes
            neighbor_id: Neighbor router ID
        """
        if neighbor_id not in self.neighbors:
            self.logger.warning(f"Received LSAck from unknown neighbor {neighbor_id}")
            return

        neighbor = self.neighbors[neighbor_id]

        # Process LSAck
        success = self.flooding_mgr.process_ls_ack(data, neighbor)
        if success:
            self.logger.debug(f"LSAck processed from {neighbor_id}")
        else:
            self.logger.warning(f"Failed to process LSAck from {neighbor_id}")

    async def _send_initial_dbd(self, neighbor: OSPFNeighbor):
        """
        Send initial Database Description packet to neighbor (ExStart state)

        Args:
            neighbor: Target neighbor
        """
        try:
            self.logger.info(f"Building initial DBD for {neighbor.router_id}...")
            # Build initial DBD packet
            dbd_packet = self.adjacency_mgr.build_initial_dbd_packet(neighbor, self.area_id)

            self.logger.info(f"Sending initial DBD to {neighbor.ip_address}...")
            # Send DBD unicast to neighbor
            self.socket.send(dbd_packet, dest=neighbor.ip_address)
            self.logger.info(f"Sent initial DBD to {neighbor.router_id} (ExStart)")
        except Exception as e:
            self.logger.error(f"Error sending initial DBD to {neighbor.router_id}: {e}", exc_info=True)

    async def _send_dbd(self, neighbor: OSPFNeighbor):
        """
        Send Database Description packet to neighbor

        Args:
            neighbor: Target neighbor
        """
        # If we're master, increment sequence number for new DBD
        if neighbor.is_master:
            neighbor.dd_sequence_number += 1
            self.logger.debug(f"Master incrementing sequence to {neighbor.dd_sequence_number}")

        # Get LSA headers to send
        lsa_headers, has_more = self.adjacency_mgr.get_lsa_headers_to_send(neighbor)

        # Build DBD packet
        dbd_packet = self.adjacency_mgr.build_dbd_packet(
            neighbor, self.area_id, lsa_headers, has_more
        )

        # Send DBD unicast to neighbor
        self.socket.send(dbd_packet, dest=neighbor.ip_address)
        self.logger.debug(f"Sent DBD to {neighbor.router_id} "
                        f"(headers: {len(lsa_headers)}, more: {has_more})")

        # Track our DBD completion
        if not has_more:
            neighbor.mark_our_dbd_complete()
            self.logger.info(f"Sent final DBD to {neighbor.router_id} (M=0)")
            # Check if exchange is complete (both sides finished)
            if neighbor.is_exchange_complete():
                self.logger.info(f"Exchange complete with {neighbor.router_id}, transitioning state")
                neighbor.exchange_done()

    async def _send_lsr(self, neighbor: OSPFNeighbor):
        """
        Send Link State Request to neighbor

        Args:
            neighbor: Target neighbor
        """
        # If no LSAs to request, transition directly to Full
        if not neighbor.ls_request_list:
            self.logger.info(f"No LSAs to request from {neighbor.router_id}, transitioning to Full")
            neighbor.loading_done()
            return

        # Build LSR packet
        lsr_packet = self.flooding_mgr.build_ls_request(neighbor, self.area_id)

        if lsr_packet:
            # Send LSR unicast to neighbor
            self.socket.send(lsr_packet, dest=neighbor.ip_address)
            self.logger.info(f"Sent LSR to {neighbor.router_id} "
                           f"requesting {len(neighbor.ls_request_list)} LSAs")

    def get_status(self) -> Dict:
        """
        Get agent status

        Returns:
            Status dictionary
        """
        return {
            'router_id': self.router_id,
            'area': self.area_id,
            'interface': self.interface,
            'ip': self.source_ip,
            'neighbors': len(self.neighbors),
            'full_neighbors': sum(1 for n in self.neighbors.values() if n.is_full()),
            'lsdb_size': self.lsdb.get_size(),
            'routes': len(self.spf_calc.routing_table)
        }


def setup_logging(log_level: str = "INFO"):
    """
    Setup logging configuration

    Args:
        log_level: Logging level
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def run_server_only(args: argparse.Namespace):
    """
    Run only the WebUI server for wizard/monitor functionality.
    No routing protocols are started.

    Args:
        args: Parsed command-line arguments
    """
    import webbrowser
    import threading

    logger = logging.getLogger("ServerOnly")

    # Determine display host (use localhost if binding to 0.0.0.0)
    display_host = "localhost" if args.webui_host == "0.0.0.0" else args.webui_host
    wizard_url = f"http://{display_host}:{args.webui_port}/wizard"

    logger.info("=" * 60)
    logger.info("  Won't You Be My Neighbor - Network Builder")
    logger.info("=" * 60)
    logger.info(f"  Builder: {wizard_url}")
    logger.info(f"  Monitor: http://{display_host}:{args.webui_port}/monitor")
    logger.info(f"  3D Topology: http://{display_host}:{args.webui_port}/topology3d")
    logger.info("")
    logger.info("  After building, agents will run on ports 8801, 8802, 8803...")
    logger.info("=" * 60)

    # Create minimal app instance (no routing)
    asi_app = WontYouBeMyNeighbor()
    asi_app.router_id = "0.0.0.0"  # Placeholder
    asi_app.running = True
    asi_app.load_config_from_env()  # Load interfaces from orchestrator config

    try:
        from webui.server import create_webui_server
        import uvicorn

        webui_app = create_webui_server(asi_app, None)

        webui_config = uvicorn.Config(
            webui_app,
            host=args.webui_host,
            port=args.webui_port,
            log_level="info"
        )
        webui_server = uvicorn.Server(webui_config)

        # Auto-launch browser after short delay (unless disabled)
        if not getattr(args, 'no_browser', False):
            def open_browser():
                import time
                time.sleep(1.5)  # Wait for server to start
                webbrowser.open(wizard_url)
                logger.info(f"Opened browser to {wizard_url}")

            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()

        # Run until interrupted
        await webui_server.serve()

    except ImportError as e:
        logger.error(f"Web UI dependencies not available: {e}")
        logger.error("Install with: pip install uvicorn fastapi")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


async def run_unified_agent(args: argparse.Namespace):
    """
    Run OSPF, BGP, or both based on command-line arguments

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger("UnifiedAgent")

    # Initialize WebUI log buffer early so ALL protocol logs are captured
    # This must happen BEFORE any protocols start logging
    from webui.server import LogBuffer, WebUILogHandler
    global_log_buffer = LogBuffer(maxlen=1000)  # Keep more log history
    log_handler = WebUILogHandler(global_log_buffer)
    log_handler.setLevel(logging.DEBUG)  # Capture all levels
    log_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
    logging.getLogger().addHandler(log_handler)
    logger.info("Log capture initialized - all protocol logs will be visible in dashboard")

    # Create main application instance
    asi_app = WontYouBeMyNeighbor()
    asi_app.router_id = args.router_id
    asi_app.load_config_from_env()  # Load interfaces from orchestrator config
    asi_app.log_buffer = global_log_buffer  # Store reference for WebUI

    ospf_agent = None
    ospfv3_speaker = None
    bgp_speaker = None
    agentic_api_server = None
    agentic_bridge = None
    tasks = []

    # Determine what protocols to run
    run_ospf = args.interface is not None  # OSPFv2 requires interface
    run_ospfv3 = args.ospfv3_interface is not None  # OSPFv3 requires interface
    run_bgp = args.bgp_local_as is not None  # BGP requires local AS

    if not run_ospf and not run_ospfv3 and not run_bgp:
        logger.error("Must specify OSPF (--interface), OSPFv3 (--ospfv3-interface), or BGP (--bgp-local-as)")
        sys.exit(1)

    # Determine agent type for banner
    protocols = []
    if run_ospf:
        protocols.append("OSPFv2")
    if run_ospfv3:
        protocols.append("OSPFv3")
    if run_bgp:
        protocols.append("BGP")

    agent_type = "+".join(protocols) + " Agent"

    # Standard mode
    logger.info(f"Starting Won't You Be My Neighbor - {agent_type} - Router ID: {args.router_id}")
    if run_ospf:
        logger.info(f"  OSPFv2: Enabled (Area {args.area}, Interface {args.interface})")
    if run_ospfv3:
        logger.info(f"  OSPFv3: Enabled (Area {args.ospfv3_area}, Interface {args.ospfv3_interface})")
    if run_bgp:
        logger.info(f"  BGP: Enabled (AS {args.bgp_local_as}, {len(args.bgp_peers or [])} peers)")

    try:
        # Create kernel route manager for installing routes
        kernel_route_manager = KernelRouteManager()

        # Enable IP forwarding in kernel
        try:
            subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=1"],
                          capture_output=True, timeout=5)
            logger.info("✓ IP forwarding enabled")
        except Exception as e:
            logger.warning(f"Could not enable IP forwarding: {e}")

        # Setup forwarding logging for loopback routes
        kernel_route_manager.setup_forwarding_logging(
            specific_prefixes=["10.10.10.1/32", "20.20.20.1/32"]
        )

        # Start forwarding monitor task
        tasks.append(asyncio.create_task(kernel_route_manager.monitor_forwarding(interval=30)))

        # Initialize GRE tunnels if configured
        if hasattr(asi_app, 'gre_tunnels') and asi_app.gre_tunnels:
            logger.info(f"Initializing {len(asi_app.gre_tunnels)} GRE tunnel(s)...")
            await asi_app.start_gre_tunnels()

        # Initialize OSPFv2 if requested
        if run_ospf:
            logger.info("Initializing OSPFv2 agent...")
            ospf_agent = OSPFAgent(
                router_id=args.router_id,
                area_id=args.area,
                interface=args.interface,
                hello_interval=args.hello_interval,
                dead_interval=args.dead_interval,
                network_type=args.network_type,
                source_ip=args.source_ip,
                unicast_peer=args.unicast_peer,
                kernel_route_manager=kernel_route_manager
            )
            asi_app.set_ospf(ospf_agent)
            asi_app.area_id = args.area
            tasks.append(asyncio.create_task(ospf_agent.start()))

        # Initialize OSPFv3 if requested
        if run_ospfv3:
            logger.info("Initializing OSPFv3 speaker...")

            # Create OSPFv3 configuration
            ospfv3_config = OSPFv3Config(
                router_id=args.router_id,
                areas=[args.ospfv3_area],
                log_level=args.log_level
            )

            ospfv3_speaker = OSPFv3Speaker(ospfv3_config)

            # Get interface ID (use interface index)
            import socket
            try:
                interface_id = socket.if_nametoindex(args.ospfv3_interface)
            except OSError:
                logger.error(f"Interface {args.ospfv3_interface} not found")
                sys.exit(1)

            # Determine link-local address
            link_local = args.ospfv3_link_local
            if not link_local:
                # Try to auto-detect link-local address
                import netifaces
                try:
                    addrs = netifaces.ifaddresses(args.ospfv3_interface)
                    if netifaces.AF_INET6 in addrs:
                        for addr_info in addrs[netifaces.AF_INET6]:
                            addr = addr_info['addr'].split('%')[0]  # Remove scope ID
                            if addr.startswith('fe80:'):
                                link_local = addr
                                break
                except (ValueError, KeyError, OSError) as e:
                    logger.debug(f"Failed to get interface addresses for {args.ospfv3_interface}: {e}")

                if not link_local:
                    logger.error(f"Could not find link-local address for {args.ospfv3_interface}. "
                               f"Please specify with --ospfv3-link-local")
                    sys.exit(1)

            logger.info(f"OSPFv3 using link-local address: {link_local}")

            # Get global addresses
            global_addresses = args.ospfv3_global_addresses or []

            # Add interface to OSPFv3
            ospfv3_speaker.add_interface(
                interface_name=args.ospfv3_interface,
                interface_id=interface_id,
                link_local_address=link_local,
                area_id=args.ospfv3_area,
                global_addresses=global_addresses,
                network_type=args.ospfv3_network_type,
                hello_interval=args.ospfv3_hello_interval,
                dead_interval=args.ospfv3_dead_interval,
                router_priority=args.ospfv3_priority
            )

            # Start OSPFv3 speaker
            asi_app.set_ospfv3(ospfv3_speaker)
            tasks.append(asyncio.create_task(ospfv3_speaker.start()))

        # Get local IP from interface if available (for BGP next-hop)
        local_bgp_ip = None
        if args.interface:
            interface_info = get_interface_info(args.interface, args.source_ip if hasattr(args, 'source_ip') else None)
            if interface_info:
                local_bgp_ip = interface_info.ip_address
                logger.info(f"Using interface {args.interface} IP {local_bgp_ip} for BGP")

        # Initialize BGP if requested
        if run_bgp:
            logger.info("Initializing BGP speaker...")
            bgp_speaker = BGPSpeaker(
                local_as=args.bgp_local_as,
                router_id=args.router_id,
                listen_ip=args.bgp_listen_ip,
                listen_port=args.bgp_listen_port,
                log_level=args.log_level,
                kernel_route_manager=kernel_route_manager
            )

            # Enable route reflection if requested
            if args.bgp_route_reflector:
                cluster_id = args.bgp_cluster_id if args.bgp_cluster_id else args.router_id
                bgp_speaker.enable_route_reflection(cluster_id=cluster_id)
                logger.info(f"BGP route reflection enabled (cluster ID: {cluster_id})")

            # Configure flap damping if enabled
            flap_config = None
            if args.bgp_enable_flap_damping:
                from bgp.flap_damping import FlapDampingConfig
                flap_config = FlapDampingConfig()
                flap_config.suppress_threshold = args.bgp_flap_suppress_threshold
                flap_config.reuse_threshold = args.bgp_flap_reuse_threshold
                flap_config.set_half_life(args.bgp_flap_half_life)
                logger.info(f"BGP flap damping enabled: suppress={flap_config.suppress_threshold}, "
                           f"reuse={flap_config.reuse_threshold}, half-life={flap_config.half_life}s")

            # Add BGP peers
            if args.bgp_peers:
                for i, peer_ip in enumerate(args.bgp_peers):
                    # Get corresponding peer AS
                    if args.bgp_peer_as_list and i < len(args.bgp_peer_as_list):
                        peer_as = args.bgp_peer_as_list[i]
                    else:
                        peer_as = args.bgp_local_as  # Default to iBGP

                    # Check if passive
                    passive = peer_ip in (args.bgp_passive or [])

                    # Check if route reflector client
                    rr_client = peer_ip in (args.bgp_rr_clients or [])

                    peer_type = "iBGP" if peer_as == args.bgp_local_as else "eBGP"
                    mode = "passive" if passive else "active"
                    rr_status = " (RR client)" if rr_client else ""

                    logger.info(f"Adding BGP peer {peer_ip}: {peer_type}, {mode}{rr_status}")

                    bgp_speaker.add_peer(
                        peer_ip=peer_ip,
                        peer_as=peer_as,
                        local_ip=local_bgp_ip,  # Use interface IP for next-hop
                        passive=passive,
                        route_reflector_client=rr_client,
                        hold_time=args.bgp_hold_time,
                        connect_retry_time=args.bgp_connect_retry,
                        enable_flap_damping=args.bgp_enable_flap_damping,
                        flap_damping_config=flap_config,
                        enable_graceful_restart=args.bgp_enable_graceful_restart,
                        graceful_restart_time=args.bgp_graceful_restart_time,
                        enable_rpki_validation=args.bgp_enable_rpki,
                        rpki_reject_invalid=args.bgp_rpki_reject_invalid,
                        enable_flowspec=args.bgp_enable_flowspec
                    )

            # Load RPKI ROAs if specified
            if args.bgp_enable_rpki and args.bgp_rpki_roa_file:
                logger.info(f"Loading RPKI ROAs from {args.bgp_rpki_roa_file}...")
                roa_count = bgp_speaker.agent.rpki_validator.load_roas_from_file(args.bgp_rpki_roa_file)
                if roa_count > 0:
                    logger.info(f"  ✓ Loaded {roa_count} ROAs")
                else:
                    logger.warning(f"  ⚠ No ROAs loaded from {args.bgp_rpki_roa_file}")

            # Start BGP speaker
            asi_app.set_bgp(bgp_speaker)
            await bgp_speaker.start()

            # Originate local networks if specified
            if args.bgp_networks:
                logger.info(f"Originating {len(args.bgp_networks)} local network(s)...")
                for network in args.bgp_networks:
                    if bgp_speaker.agent.originate_route(network):
                        logger.info(f"  ✓ Originated: {network}")
                    else:
                        logger.error(f"  ✗ Failed to originate: {network}")

            # Add BGP monitoring task
            tasks.append(asyncio.create_task(monitor_bgp(bgp_speaker, args.bgp_stats_interval)))

        # Start Route Redistribution if multiple protocols are running
        redistributor = None
        protocol_count = sum([
            1 if ospf_agent else 0,
            1 if bgp_speaker else 0,
            # Add IS-IS speaker here when implemented in main agent
        ])

        if protocol_count >= 2:
            logger.info(f"Multiple protocols enabled ({protocol_count}) - starting route redistribution...")
            redistributor = RouteRedistributor(
                router_id=args.router_id,
                local_ip=local_bgp_ip or args.router_id,
                ospf_agent=ospf_agent,
                bgp_speaker=bgp_speaker,
                isis_speaker=None,  # Will be set when IS-IS is integrated into main agent
                static_routes=[]    # Can be populated from config
            )
            tasks.append(asyncio.create_task(redistributor.start()))

            protocols = []
            if ospf_agent:
                protocols.append("OSPF")
            if bgp_speaker:
                protocols.append("BGP")
            logger.info(f"✓ Route redistribution enabled ({' ↔ '.join(protocols)})")

        # Initialize Agentic Bridge (for Web UI or API)
        # Import agentic modules
        from agentic.integration.bridge import AgenticBridge
        from agentic.integration.ospf_connector import OSPFConnector
        from agentic.integration.bgp_connector import BGPConnector

        # Get API keys from args or environment
        import os
        openai_key = args.openai_key or os.environ.get('OPENAI_API_KEY')
        claude_key = args.claude_key or os.environ.get('ANTHROPIC_API_KEY')
        gemini_key = args.gemini_key or os.environ.get('GOOGLE_API_KEY')

        logger.info("Initializing Agentic Interface...")

        # Check if at least one LLM API key is provided
        if not openai_key and not claude_key and not gemini_key:
            logger.warning("No LLM API keys provided. ASI will work but won't have AI responses. "
                         "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY environment variables "
                         "or use --openai-key, --claude-key, or --gemini-key flags.")

        # Determine ASI ID
        asi_id = args.asi_id if args.asi_id else f"asi-{args.router_id.replace('.', '-')}"

        # Create agentic bridge
        bridge = AgenticBridge(
            asi_id=asi_id,
            openai_key=openai_key,
            claude_key=claude_key,
            gemini_key=gemini_key,
            autonomous_mode=args.autonomous_mode
        )

        # Pass full agent config to bridge for LLM visibility
        if asi_app.config:
            bridge.set_agent_config(asi_app.config)
            logger.info(f"✓ Passed agent config to agentic bridge ({len(asi_app.interfaces)} interfaces)")

        # Connect OSPF if available
        if ospf_agent:
            connector = OSPFConnector(ospf_agent)
            bridge.set_ospf_connector(connector)
            logger.info(f"✓ Connected OSPF agent to agentic interface")

        # Connect OSPFv3 if available
        if ospfv3_speaker:
            # Note: OSPFv3 connector would need to be implemented
            logger.info(f"  OSPFv3 connector not yet implemented for agentic interface")

        # Connect BGP if available
        if bgp_speaker:
            connector = BGPConnector(bgp_speaker)
            bridge.set_bgp_connector(connector)
            logger.info(f"✓ Connected BGP speaker to agentic interface")

        # Initialize bridge
        await bridge.initialize()
        await bridge.start()

        # Store bridge reference
        agentic_bridge = bridge
        asi_app.set_agentic_bridge(bridge)

        # Initialize IPv6 Neighbor Discovery for ASI Overlay (Layer 2: Agent Mesh)
        nd_protocol = None
        ipv6_overlay = os.environ.get('ASI_OVERLAY_IPV6')
        nd_enabled = os.environ.get('ASI_OVERLAY_ND_ENABLED', 'true').lower() == 'true'

        if ipv6_overlay and nd_enabled:
            try:
                from agentic.discovery.neighbor_discovery import (
                    start_neighbor_discovery,
                    stop_neighbor_discovery,
                    get_neighbor_discovery
                )

                logger.info(f"Initializing IPv6 Neighbor Discovery...")
                logger.info(f"  Overlay IPv6: {ipv6_overlay}")

                # Configure IPv6 overlay address on a dummy interface for actual connectivity
                try:
                    import subprocess
                    ipv6_addr = ipv6_overlay.split('/')[0]
                    prefix_len = ipv6_overlay.split('/')[1] if '/' in ipv6_overlay else '64'

                    # Create dummy interface for ASI overlay
                    subprocess.run(['ip', 'link', 'add', 'asi0', 'type', 'dummy'],
                                   capture_output=True, check=False)
                    subprocess.run(['ip', 'link', 'set', 'asi0', 'up'],
                                   capture_output=True, check=False)
                    subprocess.run(['ip', '-6', 'addr', 'add', f'{ipv6_addr}/{prefix_len}', 'dev', 'asi0'],
                                   capture_output=True, check=False)

                    # Add route to the ASI overlay network via eth0 (Docker network)
                    # This enables IPv6 connectivity to other agents in the same Docker network
                    overlay_prefix = ':'.join(ipv6_addr.split(':')[:4]) + '::/64'
                    subprocess.run(['ip', '-6', 'route', 'add', overlay_prefix, 'dev', 'eth0'],
                                   capture_output=True, check=False)

                    logger.info(f"  ✓ Configured asi0 interface with {ipv6_addr}/{prefix_len}")
                    logger.info(f"  ✓ Added route for {overlay_prefix} via eth0")
                except Exception as e:
                    logger.warning(f"  Could not configure IPv6 overlay interface: {e}")

                agent_id = os.environ.get('ASI_AGENT_ID', asi_id)
                agent_name = os.environ.get('ASI_AGENT_NAME', f"agent-{args.router_id}")

                nd_protocol = await start_neighbor_discovery(
                    local_ipv6=ipv6_overlay,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    router_id=args.router_id
                )

                # Add listener for neighbor discovery events
                def nd_event_handler(event: str, neighbor):
                    if event == "neighbor_discovered":
                        logger.info(f"ND: Discovered neighbor {neighbor.agent_name or neighbor.ipv6_address}")
                    elif event == "neighbor_removed":
                        logger.info(f"ND: Lost neighbor {neighbor.agent_name or neighbor.ipv6_address}")

                nd_protocol.add_listener(nd_event_handler)

                logger.info(f"✓ IPv6 Neighbor Discovery started on ASI overlay")
            except ImportError as e:
                logger.warning(f"Neighbor Discovery module not available: {e}")
            except Exception as e:
                logger.warning(f"Could not start Neighbor Discovery: {e}")
        elif ipv6_overlay and not nd_enabled:
            logger.info(f"IPv6 Overlay configured ({ipv6_overlay}) but ND disabled")

        # Start REST API server if requested (optional, separate from Web UI)
        if args.agentic_api:
            from agentic.api.server import create_api_server
            try:
                import uvicorn
            except ImportError:
                logger.error("uvicorn not installed. Install with: pip install uvicorn")
                logger.error("API server requires uvicorn")
                raise

            # Create API server
            api, server_config = create_api_server(
                bridge,
                host=args.agentic_api_host,
                port=args.agentic_api_port
            )

            # Store for cleanup
            agentic_api_server = api

            # Start API server as background task
            config = uvicorn.Config(**server_config)
            server = uvicorn.Server(config)
            tasks.append(asyncio.create_task(server.serve()))

            logger.info(f"✓ REST API started at http://{args.agentic_api_host}:{args.agentic_api_port}")
            logger.info(f"  Documentation: http://{args.agentic_api_host}:{args.agentic_api_port}/docs")

        logger.info(f"  ASI ID: {asi_id}")
        if args.autonomous_mode:
            logger.warning(f"  ⚠ AUTONOMOUS MODE ENABLED - Actions may execute without approval")

        # Start Web UI if enabled
        webui_server = None
        if args.webui:
            try:
                from webui.server import create_webui_server
                import uvicorn

                # Create Web UI server with access to asi_app and bridge
                webui_app = create_webui_server(asi_app, bridge)

                # Start Web UI server as background task
                webui_config = uvicorn.Config(
                    webui_app,
                    host=args.webui_host,
                    port=args.webui_port,
                    log_level="warning"
                )
                webui_server = uvicorn.Server(webui_config)
                tasks.append(asyncio.create_task(webui_server.serve()))

                logger.info(f"✓ Web Dashboard started at http://{args.webui_host}:{args.webui_port}")

            except ImportError as e:
                logger.warning(f"Web UI not available ({e}). Install with: pip install uvicorn")
            except Exception as e:
                logger.warning(f"Could not start Web UI: {e}")

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()

        def signal_handler(signum):
            logger.info(f"Received signal {signum}, shutting down...")
            for task in tasks:
                task.cancel()
            if bgp_speaker:
                asyncio.create_task(bgp_speaker.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        # Cleanup
        if redistributor:
            logger.info("Stopping route redistribution...")
            await redistributor.stop()

        if ospfv3_speaker:
            logger.info("Stopping OSPFv3 speaker...")
            await ospfv3_speaker.stop()

        if bgp_speaker:
            logger.info("Stopping BGP speaker...")
            await bgp_speaker.stop()

        if agentic_api_server:
            logger.info("Stopping Agentic API server...")
            # uvicorn server cleanup handled by task cancellation

        if agentic_bridge:
            logger.info("Stopping Agentic bridge...")
            await agentic_bridge.stop()

        # Stop Neighbor Discovery if running
        if nd_protocol:
            logger.info("Stopping Neighbor Discovery...")
            try:
                from agentic.discovery.neighbor_discovery import stop_neighbor_discovery
                await stop_neighbor_discovery()
            except Exception as e:
                logger.warning(f"Error stopping ND: {e}")

        logger.info("Shutdown complete")


async def monitor_bgp(speaker: BGPSpeaker, interval: int):
    """
    Monitor BGP speaker and print statistics periodically

    Args:
        speaker: BGP speaker instance
        interval: Statistics interval in seconds
    """
    logger = logging.getLogger("BGPMonitor")

    while speaker.agent.running:
        await asyncio.sleep(interval)

        try:
            stats = speaker.get_statistics()
            logger.info("=" * 60)
            logger.info(f"BGP Statistics:")
            logger.info(f"  Total Peers:       {stats['total_peers']}")
            logger.info(f"  Established Peers: {stats['established_peers']}")
            logger.info(f"  Loc-RIB Routes:    {stats['loc_rib_routes']}")

            if 'route_reflector' in stats:
                rr_stats = stats['route_reflector']
                logger.info(f"  RR Clients:        {rr_stats['clients']}")

            # Display routing table (like "show ip route bgp")
            routes = speaker.agent.loc_rib.get_all_routes()
            if routes:
                logger.info("")
                logger.info("BGP Routing Table:")
                logger.info(f"{'Network':<20} {'Next Hop':<16} {'Path':<20} {'Source':<10}")
                logger.info("-" * 70)

                # Sort routes by prefix for consistent display
                sorted_routes = sorted(routes, key=lambda r: r.prefix)

                for route in sorted_routes[:20]:  # Show first 20 routes
                    # Extract next-hop from attributes
                    next_hop = "N/A"
                    if 3 in route.path_attributes:  # ATTR_NEXT_HOP
                        nh_attr = route.path_attributes[3]
                        if hasattr(nh_attr, 'next_hop'):
                            next_hop = nh_attr.next_hop

                    # Extract AS_PATH
                    as_path = ""
                    if 2 in route.path_attributes:  # ATTR_AS_PATH
                        path_attr = route.path_attributes[2]
                        if hasattr(path_attr, 'segments'):
                            try:
                                # Handle both object and tuple segments
                                as_list = []
                                for seg in path_attr.segments:
                                    if hasattr(seg, 'asns'):
                                        as_list.extend(str(asn) for asn in seg.asns)
                                    elif isinstance(seg, tuple):
                                        # Segment is (type, [asns])
                                        as_list.extend(str(asn) for asn in seg[1])
                                as_path = " ".join(as_list)
                            except Exception:
                                as_path = "?"

                    logger.info(f"{route.prefix:<20} {next_hop:<16} {as_path:<20} {route.source:<10}")

                if len(routes) > 20:
                    logger.info(f"... and {len(routes) - 20} more routes")
        except Exception as e:
            logger.error(f"Error getting BGP statistics: {e}")


def main():
    """
    Main entry point
    """
    parser = argparse.ArgumentParser(
        description="Won't You Be My Neighbor - Unified Routing Agent (OSPF + BGP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # OSPF only:
  sudo python3 wontyoubemyneighbor.py \\
      --router-id 10.255.255.99 \\
      --area 0.0.0.0 \\
      --interface eth0

  # BGP only (iBGP):
  python3 wontyoubemyneighbor.py \\
      --router-id 192.0.2.1 \\
      --bgp-local-as 65001 \\
      --bgp-peer 192.0.2.2 \\
      --bgp-peer-as 65001

  # BGP only (eBGP):
  python3 wontyoubemyneighbor.py \\
      --router-id 192.0.2.1 \\
      --bgp-local-as 65001 \\
      --bgp-peer 192.0.2.2 \\
      --bgp-peer-as 65002

  # Both OSPF and BGP:
  sudo python3 wontyoubemyneighbor.py \\
      --router-id 10.0.1.1 \\
      --area 0.0.0.0 \\
      --interface eth0 \\
      --bgp-local-as 65001 \\
      --bgp-peer 192.0.2.2 \\
      --bgp-peer-as 65002

  # BGP Route Reflector with clients:
  python3 wontyoubemyneighbor.py \\
      --router-id 192.0.2.1 \\
      --bgp-local-as 65001 \\
      --bgp-route-reflector \\
      --bgp-peer 192.0.2.2 --bgp-peer-as 65001 --bgp-rr-client 192.0.2.2 --bgp-passive 192.0.2.2 \\
      --bgp-peer 192.0.2.3 --bgp-peer-as 65001 --bgp-rr-client 192.0.2.3 --bgp-passive 192.0.2.3

Notes:
  - OSPF requires root privileges for raw sockets
  - BGP uses TCP port 179 (requires root for ports < 1024)
  - At least one protocol (OSPF or BGP) must be specified
        """
    )

    # Server-only mode (just WebUI wizard/monitor, no routing)
    parser.add_argument("--server-only", action="store_true",
                       help="Run only the WebUI server (wizard/monitor) without routing protocols")

    # Common arguments
    parser.add_argument("--router-id", required=False, default=None,
                       help="Router ID in IPv4 format (e.g., 10.255.255.99)")
    parser.add_argument("--log-level", default="INFO",
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help="Log level (default: INFO)")

    # OSPF arguments
    ospf_group = parser.add_argument_group('OSPF Options')
    ospf_group.add_argument("--area", default="0.0.0.0",
                       help="OSPF Area (default: 0.0.0.0)")
    ospf_group.add_argument("--interface", default=None,
                       help="Network interface for OSPF (e.g., eth0, en0)")
    ospf_group.add_argument("--source-ip", default=None,
                       help="Source IP address (optional, for multi-IP interfaces)")
    ospf_group.add_argument("--hello-interval", type=int, default=10,
                       help="OSPF Hello interval in seconds (default: 10)")
    ospf_group.add_argument("--dead-interval", type=int, default=40,
                       help="OSPF Dead interval in seconds (default: 40)")
    ospf_group.add_argument("--network-type", default="broadcast",
                       choices=['broadcast', 'point-to-multipoint', 'point-to-point', 'nbma'],
                       help="OSPF Network type (default: broadcast)")
    ospf_group.add_argument("--unicast-peer", default=None,
                       help="OSPF Unicast peer IP for point-to-point")

    # OSPFv3 arguments (IPv6)
    ospfv3_group = parser.add_argument_group('OSPFv3 Options (IPv6)')
    ospfv3_group.add_argument("--ospfv3-interface", default=None,
                       help="Network interface for OSPFv3 (e.g., eth0, en0)")
    ospfv3_group.add_argument("--ospfv3-area", default="0.0.0.0",
                       help="OSPFv3 Area (default: 0.0.0.0)")
    ospfv3_group.add_argument("--ospfv3-link-local", default=None,
                       help="IPv6 link-local address for OSPFv3 (fe80::)")
    ospfv3_group.add_argument("--ospfv3-global-address", dest="ospfv3_global_addresses",
                       action="append",
                       help="IPv6 global unicast address (can be specified multiple times)")
    ospfv3_group.add_argument("--ospfv3-network-type", default="broadcast",
                       choices=['broadcast', 'point-to-point', 'point-to-multipoint'],
                       help="OSPFv3 Network type (default: broadcast)")
    ospfv3_group.add_argument("--ospfv3-hello-interval", type=int, default=10,
                       help="OSPFv3 Hello interval in seconds (default: 10)")
    ospfv3_group.add_argument("--ospfv3-dead-interval", type=int, default=40,
                       help="OSPFv3 Dead interval in seconds (default: 40)")
    ospfv3_group.add_argument("--ospfv3-priority", type=int, default=1,
                       help="OSPFv3 Router priority for DR election (default: 1)")

    # BGP arguments
    bgp_group = parser.add_argument_group('BGP Options')
    bgp_group.add_argument("--bgp-local-as", type=int, default=None,
                       help="BGP Local AS number (e.g., 65001)")
    bgp_group.add_argument("--bgp-peer", dest="bgp_peers", action="append",
                       help="BGP Peer IP address (can be specified multiple times)")
    bgp_group.add_argument("--bgp-peer-as", dest="bgp_peer_as_list", type=int, action="append",
                       help="BGP Peer AS number for corresponding --bgp-peer")
    bgp_group.add_argument("--bgp-passive", dest="bgp_passive", action="append",
                       help="Mark BGP peer as passive (wait for incoming connection)")
    bgp_group.add_argument("--bgp-route-reflector", action="store_true",
                       help="Enable BGP route reflection")
    bgp_group.add_argument("--bgp-cluster-id", default=None,
                       help="BGP Route reflector cluster ID (default: router-id)")
    bgp_group.add_argument("--bgp-rr-client", dest="bgp_rr_clients", action="append",
                       help="Mark BGP peer as route reflector client")
    bgp_group.add_argument("--bgp-listen-ip", default="0.0.0.0",
                       help="BGP Listen IP address (default: 0.0.0.0)")
    bgp_group.add_argument("--bgp-listen-port", type=int, default=179,
                       help="BGP TCP port to listen on (default: 179)")
    bgp_group.add_argument("--bgp-hold-time", type=int, default=180,
                       help="BGP Hold time in seconds (default: 180)")
    bgp_group.add_argument("--bgp-connect-retry", type=int, default=120,
                       help="BGP Connect retry time in seconds (default: 120)")
    bgp_group.add_argument("--bgp-stats-interval", type=int, default=30,
                       help="BGP Statistics display interval in seconds (default: 30)")
    bgp_group.add_argument("--bgp-network", dest="bgp_networks", action="append",
                       help="BGP Network to originate/advertise (can be specified multiple times)")
    bgp_group.add_argument("--bgp-enable-flap-damping", action="store_true",
                       help="Enable BGP route flap damping (RFC 2439)")
    bgp_group.add_argument("--bgp-flap-suppress-threshold", type=int, default=3000,
                       help="Flap damping suppress threshold (default: 3000)")
    bgp_group.add_argument("--bgp-flap-reuse-threshold", type=int, default=750,
                       help="Flap damping reuse threshold (default: 750)")
    bgp_group.add_argument("--bgp-flap-half-life", type=int, default=900,
                       help="Flap damping half-life in seconds (default: 900 = 15 minutes)")

    bgp_group.add_argument("--bgp-enable-graceful-restart", action="store_true",
                       help="Enable BGP graceful restart (RFC 4724)")
    bgp_group.add_argument("--bgp-graceful-restart-time", type=int, default=120,
                       help="Graceful restart time in seconds (default: 120)")

    bgp_group.add_argument("--bgp-enable-rpki", action="store_true",
                       help="Enable RPKI route origin validation (RFC 6811)")
    bgp_group.add_argument("--bgp-rpki-reject-invalid", action="store_true",
                       help="Reject RPKI-invalid routes (default: accept with invalid state)")
    bgp_group.add_argument("--bgp-rpki-roa-file", type=str,
                       help="Load ROAs from JSON file")

    bgp_group.add_argument("--bgp-enable-flowspec", action="store_true",
                       help="Enable BGP FlowSpec for traffic filtering (RFC 5575)")

    # IS-IS Protocol arguments
    isis_group = parser.add_argument_group('IS-IS Options')
    isis_group.add_argument("--isis-system-id", default=None,
                       help="IS-IS System ID in format AABB.CCDD.EEFF (e.g., 0000.0000.0001)")
    isis_group.add_argument("--isis-area", dest="isis_areas", action="append",
                       help="IS-IS Area address (e.g., 49.0001) - can be specified multiple times")
    isis_group.add_argument("--isis-level", type=int, choices=[1, 2, 3], default=3,
                       help="IS-IS Level: 1 (L1), 2 (L2), or 3 (L1/L2) (default: 3)")
    isis_group.add_argument("--isis-interface", dest="isis_interfaces", action="append",
                       help="Enable IS-IS on interface (can be specified multiple times)")
    isis_group.add_argument("--isis-metric", type=int, default=10,
                       help="IS-IS Default metric (default: 10)")
    isis_group.add_argument("--isis-hello-interval", type=int, default=10,
                       help="IS-IS Hello interval in seconds (default: 10)")
    isis_group.add_argument("--isis-network", dest="isis_networks", action="append",
                       help="IS-IS Network to advertise (can be specified multiple times)")

    # MPLS/LDP Protocol arguments
    mpls_group = parser.add_argument_group('MPLS/LDP Options')
    mpls_group.add_argument("--mpls-router-id", default=None,
                       help="MPLS Router ID (default: uses main router-id)")
    mpls_group.add_argument("--ldp-interface", dest="ldp_interfaces", action="append",
                       help="Enable LDP on interface (can be specified multiple times)")
    mpls_group.add_argument("--ldp-neighbor", dest="ldp_neighbors", action="append",
                       help="LDP neighbor IP (can be specified multiple times)")
    mpls_group.add_argument("--mpls-label-range-start", type=int, default=16,
                       help="MPLS label range start (default: 16)")
    mpls_group.add_argument("--mpls-label-range-end", type=int, default=1048575,
                       help="MPLS label range end (default: 1048575)")

    # VXLAN/EVPN Protocol arguments
    vxlan_group = parser.add_argument_group('VXLAN/EVPN Options')
    vxlan_group.add_argument("--vtep-ip", default=None,
                       help="VXLAN VTEP source IP address")
    vxlan_group.add_argument("--vxlan-vni", dest="vxlan_vnis", type=int, action="append",
                       help="VXLAN VNI to configure (can be specified multiple times)")
    vxlan_group.add_argument("--vxlan-remote-vtep", dest="vxlan_remote_vteps", action="append",
                       help="Remote VTEP IP address (can be specified multiple times)")
    vxlan_group.add_argument("--vxlan-port", type=int, default=4789,
                       help="VXLAN UDP port (default: 4789)")
    vxlan_group.add_argument("--evpn-rd", default=None,
                       help="EVPN Route Distinguisher (e.g., 1:1)")
    vxlan_group.add_argument("--evpn-rt", dest="evpn_rts", action="append",
                       help="EVPN Route Target (can be specified multiple times)")

    # DHCP Server arguments
    dhcp_group = parser.add_argument_group('DHCP Server Options')
    dhcp_group.add_argument("--dhcp-server", action="store_true",
                       help="Enable DHCP server")
    dhcp_group.add_argument("--dhcp-pool", dest="dhcp_pools", action="append",
                       help="DHCP pool in format: name,start_ip,end_ip,subnet (e.g., pool1,10.0.0.100,10.0.0.200,10.0.0.0/24)")
    dhcp_group.add_argument("--dhcp-gateway", default=None,
                       help="DHCP default gateway option")
    dhcp_group.add_argument("--dhcp-dns", dest="dhcp_dns_servers", action="append",
                       help="DHCP DNS server option (can be specified multiple times)")
    dhcp_group.add_argument("--dhcp-lease-time", type=int, default=86400,
                       help="DHCP lease time in seconds (default: 86400 = 1 day)")

    # DNS Server arguments
    dns_group = parser.add_argument_group('DNS Server Options')
    dns_group.add_argument("--dns-server", action="store_true",
                       help="Enable DNS server")
    dns_group.add_argument("--dns-zone", dest="dns_zones", action="append",
                       help="DNS zone to serve (e.g., example.com)")
    dns_group.add_argument("--dns-record", dest="dns_records", action="append",
                       help="DNS record in format: name,type,value (e.g., www,A,10.0.0.1)")
    dns_group.add_argument("--dns-forwarder", dest="dns_forwarders", action="append",
                       help="DNS forwarder address (can be specified multiple times)")
    dns_group.add_argument("--dns-port", type=int, default=53,
                       help="DNS server port (default: 53)")

    # Agentic LLM Interface arguments
    agentic_group = parser.add_argument_group('Agentic LLM Interface Options')
    agentic_group.add_argument("--agentic-api", action="store_true",
                       help="Enable agentic LLM interface API server")
    agentic_group.add_argument("--agentic-api-host", default="0.0.0.0",
                       help="Agentic API host to bind to (default: 0.0.0.0)")
    agentic_group.add_argument("--agentic-api-port", type=int, default=8080,
                       help="Agentic API port to listen on (default: 8080)")
    agentic_group.add_argument("--openai-key", default=None,
                       help="OpenAI API key for agentic interface")
    agentic_group.add_argument("--claude-key", default=None,
                       help="Anthropic Claude API key for agentic interface")
    agentic_group.add_argument("--gemini-key", default=None,
                       help="Google Gemini API key for agentic interface")
    agentic_group.add_argument("--autonomous-mode", action="store_true",
                       help="Enable autonomous mode for agentic interface (dangerous actions without approval)")
    agentic_group.add_argument("--asi-id", default=None,
                       help="ASI instance ID for agentic interface (default: based on router-id)")

    # Web UI arguments
    webui_group = parser.add_argument_group('Web UI Options')
    webui_group.add_argument("--webui", action="store_true", default=True,
                       help="Enable Web Dashboard UI (default: enabled)")
    webui_group.add_argument("--webui-host", default="0.0.0.0",
                       help="Web UI host to bind to (default: 0.0.0.0)")
    webui_group.add_argument("--webui-port", type=int, default=8000,
                       help="Web UI port for builder (default: 8000)")
    webui_group.add_argument("--no-webui", action="store_true",
                       help="Disable Web UI")
    webui_group.add_argument("--no-browser", action="store_true",
                       help="Don't auto-launch browser on startup")

    args = parser.parse_args()

    # Handle Web UI flag logic
    if args.no_webui:
        args.webui = False

    # Setup logging
    setup_logging(args.log_level)

    # Determine if we should run in builder mode (default) or routing mode
    # Builder mode: no router-id specified, just launch the wizard
    # Routing mode: router-id and protocols specified (for containers)
    has_routing_config = (
        args.router_id is not None or
        args.interface is not None or
        args.bgp_local_as is not None or
        args.ospfv3_interface is not None
    )

    # Server-only/builder mode - default if no routing config provided
    if args.server_only or not has_routing_config:
        args.webui = True
        try:
            asyncio.run(run_server_only(args))
        except KeyboardInterrupt:
            print("\nShutting down...")
            sys.exit(0)
        except Exception as e:
            print(f"Fatal error: {e}")
            sys.exit(1)
        return

    # Validate configuration for routing mode (container/agent mode)
    if not args.router_id:
        print("Error: --router-id is required for routing mode")
        parser.print_help()
        sys.exit(1)

    if not args.interface and not args.bgp_local_as and not args.ospfv3_interface:
        print("Error: Must specify either OSPFv2 (--interface), OSPFv3 (--ospfv3-interface), or BGP (--bgp-local-as) configuration")
        parser.print_help()
        sys.exit(1)

    if args.bgp_local_as and not args.bgp_peers:
        print("Error: BGP requires at least one peer (--bgp-peer)")
        sys.exit(1)

    if args.bgp_peer_as_list and len(args.bgp_peer_as_list) != len(args.bgp_peers or []):
        print("Error: Number of --bgp-peer-as must match number of --bgp-peer")
        sys.exit(1)

    # Run unified agent
    try:
        asyncio.run(run_unified_agent(args))
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
