"""
IS-IS Speaker - Main Protocol Engine

Provides high-level interface for running an IS-IS speaker.
Coordinates adjacency management, LSDB, flooding, and SPF calculation.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from ipaddress import ip_address, ip_network

from .constants import (
    LEVEL_1, LEVEL_2, LEVEL_1_2,
    DEFAULT_HELLO_INTERVAL, DEFAULT_HELLO_MULTIPLIER,
    DEFAULT_LSP_LIFETIME, DEFAULT_LSP_REFRESH_INTERVAL,
    DEFAULT_METRIC, DEFAULT_PRIORITY,
    PDU_L1_LAN_IIH, PDU_L2_LAN_IIH, PDU_P2P_IIH,
    CIRCUIT_BROADCAST, CIRCUIT_P2P,
    ISIS_PROTOCOL_DISCRIMINATOR,
    LSP_SEQUENCE_INITIAL,
    TLV_AREA_ADDRESSES, TLV_IP_INTERFACE_ADDR, TLV_HOSTNAME,
    TLV_IS_NEIGHBORS, TLV_IP_INT_REACH, TLV_IP_EXT_REACH, TLV_PROTOCOLS_SUPPORTED,
    NLPID_IPV4,
)
from .adjacency import ISISAdjacency, ISISAdjacencyManager, AdjacencyState, CircuitType
from .lsdb import LSDB, DualLSDB, LSP, TLV
from .spf import ISISSPFCalculator, DualSPFCalculator, SPFRoute


@dataclass
class ISISInterface:
    """
    Configuration for an IS-IS-enabled interface.
    """
    name: str                           # Interface name (e.g., "eth0")
    ip_address: str                     # Interface IP address
    network: str                        # Network prefix (e.g., "10.0.0.0/24")
    metric: int = DEFAULT_METRIC        # Interface metric
    level: int = LEVEL_1_2              # Level enabled on this interface
    circuit_type: CircuitType = CircuitType.BROADCAST  # Circuit type
    priority: int = DEFAULT_PRIORITY    # DIS priority
    hello_interval: int = DEFAULT_HELLO_INTERVAL
    hello_multiplier: int = DEFAULT_HELLO_MULTIPLIER
    passive: bool = False               # Passive interface (no hellos)

    @property
    def hold_time(self) -> int:
        return self.hello_interval * self.hello_multiplier


class ISISSpeaker:
    """
    IS-IS Speaker - Main protocol engine.

    Provides a high-level API for running an IS-IS router with:
    - Multiple interfaces
    - Level 1, Level 2, or Level 1/2 operation
    - Automatic adjacency formation
    - LSDB maintenance and flooding
    - SPF calculation and route installation
    """

    def __init__(
        self,
        system_id: str,
        area_addresses: List[str],
        hostname: Optional[str] = None,
        level: int = LEVEL_1_2,
        log_level: str = "INFO",
    ):
        """
        Initialize IS-IS speaker.

        Args:
            system_id: 6-byte system ID in format "AABB.CCDD.EEFF"
            area_addresses: List of area addresses (e.g., ["49.0001"])
            hostname: Router hostname for dynamic hostname TLV
            level: IS-IS level (1, 2, or 3 for L1/L2)
            log_level: Logging level
        """
        self.system_id = system_id
        self.area_addresses = area_addresses
        self.hostname = hostname or f"isis-{system_id}"
        self.level = level

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(f"ISIS[{system_id}]")

        # Interfaces
        self.interfaces: Dict[str, ISISInterface] = {}

        # Core components
        self.adjacency_manager = ISISAdjacencyManager(
            system_id=system_id,
            area_addresses=area_addresses,
            level=level,
        )

        self.dual_lsdb = DualLSDB(system_id, level)
        self.spf_calculator = DualSPFCalculator(system_id, self.dual_lsdb)

        # Local LSP sequence numbers
        self._l1_lsp_seq = LSP_SEQUENCE_INITIAL
        self._l2_lsp_seq = LSP_SEQUENCE_INITIAL

        # Tasks
        self._hello_tasks: Dict[str, asyncio.Task] = {}
        self._lsp_refresh_task: Optional[asyncio.Task] = None
        self._csnp_task: Optional[asyncio.Task] = None

        # Callbacks
        self.on_route_change: Optional[Callable[[SPFRoute], None]] = None

        # Running state
        self.running = False

        # Wire up callbacks
        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        """Setup internal callbacks"""
        # Adjacency callbacks
        self.adjacency_manager.on_adjacency_up = self._on_adjacency_up
        self.adjacency_manager.on_adjacency_down = self._on_adjacency_down
        self.adjacency_manager.on_dis_change = self._on_dis_change

        # LSDB callbacks
        if self.dual_lsdb.l1_lsdb:
            self.dual_lsdb.l1_lsdb.on_lsp_change = lambda lsp: self._on_lsp_change(lsp, LEVEL_1)

        if self.dual_lsdb.l2_lsdb:
            self.dual_lsdb.l2_lsdb.on_lsp_change = lambda lsp: self._on_lsp_change(lsp, LEVEL_2)

    def add_interface(
        self,
        name: str,
        ip_address: str,
        network: str,
        metric: int = DEFAULT_METRIC,
        level: int = LEVEL_1_2,
        circuit_type: str = "broadcast",
        priority: int = DEFAULT_PRIORITY,
        passive: bool = False,
    ) -> ISISInterface:
        """
        Add IS-IS-enabled interface.

        Args:
            name: Interface name
            ip_address: Interface IP address
            network: Network prefix
            metric: Interface metric
            level: Level enabled on interface
            circuit_type: "broadcast" or "point-to-point"
            priority: DIS priority
            passive: Passive interface (no hellos)

        Returns:
            ISISInterface configuration
        """
        ct = CircuitType.BROADCAST if circuit_type == "broadcast" else CircuitType.POINT_TO_POINT

        iface = ISISInterface(
            name=name,
            ip_address=ip_address,
            network=network,
            metric=metric,
            level=level,
            circuit_type=ct,
            priority=priority,
            passive=passive,
        )

        self.interfaces[name] = iface
        self.logger.info(f"Added interface {name}: {ip_address} metric={metric} L{level}")

        return iface

    async def start(self) -> None:
        """Start IS-IS speaker"""
        self.logger.info(f"Starting IS-IS speaker System-ID {self.system_id}")
        self.running = True

        # Start adjacency manager
        await self.adjacency_manager.start_hold_timer()

        # Start LSDB aging
        await self.dual_lsdb.start()

        # Originate our LSP
        self._originate_local_lsp()

        # Start hello transmission on all interfaces
        for name, iface in self.interfaces.items():
            if not iface.passive:
                self._hello_tasks[name] = asyncio.create_task(
                    self._hello_loop(iface)
                )

        # Start LSP refresh task
        self._lsp_refresh_task = asyncio.create_task(self._lsp_refresh_loop())

        self.logger.info("IS-IS speaker started")

    async def stop(self) -> None:
        """Stop IS-IS speaker"""
        self.logger.info("Stopping IS-IS speaker")
        self.running = False

        # Stop hello tasks
        for task in self._hello_tasks.values():
            task.cancel()

        for task in self._hello_tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Stop other tasks
        if self._lsp_refresh_task:
            self._lsp_refresh_task.cancel()
            try:
                await self._lsp_refresh_task
            except asyncio.CancelledError:
                pass

        if self._csnp_task:
            self._csnp_task.cancel()
            try:
                await self._csnp_task
            except asyncio.CancelledError:
                pass

        # Stop components
        await self.adjacency_manager.stop()
        await self.dual_lsdb.stop()

        self.logger.info("IS-IS speaker stopped")

    async def run(self) -> None:
        """
        Run IS-IS speaker (blocks until stopped).
        """
        await self.start()

        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        finally:
            await self.stop()

    def _originate_local_lsp(self) -> None:
        """Generate and install our local LSP(s)"""
        # Originate L1 LSP
        if self.level in (LEVEL_1, LEVEL_1_2):
            lsp = self._build_local_lsp(LEVEL_1)
            self.dual_lsdb.l1_lsdb.install_lsp(lsp)
            self.logger.debug(f"Originated L1 LSP seq={lsp.sequence_number}")

        # Originate L2 LSP
        if self.level in (LEVEL_2, LEVEL_1_2):
            lsp = self._build_local_lsp(LEVEL_2)
            self.dual_lsdb.l2_lsdb.install_lsp(lsp)
            self.logger.debug(f"Originated L2 LSP seq={lsp.sequence_number}")

    def _build_local_lsp(self, level: int) -> LSP:
        """Build local LSP for specified level"""
        # Increment sequence number
        if level == LEVEL_1:
            self._l1_lsp_seq += 1
            seq = self._l1_lsp_seq
        else:
            self._l2_lsp_seq += 1
            seq = self._l2_lsp_seq

        # LSP ID: system_id.00-00 (main fragment)
        lsp_id = f"{self.system_id}.00-00"

        # Build TLVs
        tlvs = []

        # Area Addresses TLV
        area_data = bytearray()
        for area in self.area_addresses:
            # Simple encoding: area as bytes
            area_bytes = area.encode('ascii')
            area_data.append(len(area_bytes))
            area_data.extend(area_bytes)
        tlvs.append(TLV(TLV_AREA_ADDRESSES, bytes(area_data)))

        # Protocols Supported TLV
        tlvs.append(TLV(TLV_PROTOCOLS_SUPPORTED, bytes([NLPID_IPV4])))

        # Hostname TLV
        tlvs.append(TLV(TLV_HOSTNAME, self.hostname.encode('ascii')))

        # IP Interface Addresses TLV
        for iface in self.interfaces.values():
            if iface.level == level or iface.level == LEVEL_1_2 or level == LEVEL_1_2:
                ip_bytes = socket.inet_aton(iface.ip_address)
                tlvs.append(TLV(TLV_IP_INTERFACE_ADDR, ip_bytes))

        # IS Neighbors TLV (from UP adjacencies)
        neighbor_data = bytearray([0])  # Virtual flag = 0
        for adj in self.adjacency_manager.get_adjacencies(level=level):
            if adj.is_up():
                # Find interface for this adjacency
                iface = self.interfaces.get(adj.interface)
                metric = iface.metric if iface else DEFAULT_METRIC

                # Default metric (1 byte, 6-bit metric)
                neighbor_data.append(metric & 0x3F)
                # Delay metric (set to unsupported)
                neighbor_data.append(0x80)
                # Expense metric (set to unsupported)
                neighbor_data.append(0x80)
                # Error metric (set to unsupported)
                neighbor_data.append(0x80)
                # Neighbor ID (7 bytes: system_id + pseudonode)
                neighbor_data.extend(self._system_id_to_bytes(adj.system_id))
                neighbor_data.append(0)  # Pseudonode ID

        if len(neighbor_data) > 1:
            tlvs.append(TLV(TLV_IS_NEIGHBORS, bytes(neighbor_data)))

        # IP Internal Reachability TLV
        for iface in self.interfaces.values():
            if iface.level == level or iface.level == LEVEL_1_2 or level == LEVEL_1_2:
                reach_data = bytearray()
                # Default metric
                reach_data.append(iface.metric & 0x3F)
                # Delay metric (unsupported)
                reach_data.append(0x80)
                # Expense metric (unsupported)
                reach_data.append(0x80)
                # Error metric (unsupported)
                reach_data.append(0x80)

                # IP address and mask
                network = ip_network(iface.network, strict=False)
                reach_data.extend(network.network_address.packed)
                reach_data.extend(network.netmask.packed)

                tlvs.append(TLV(TLV_IP_INT_REACH, bytes(reach_data)))

        # IP External Reachability TLV (TLV 130) for redistributed routes
        external_routes = self.get_external_routes()
        for prefix, route_info in external_routes.items():
            ext_data = bytearray()
            # Default metric (set external bit in high nibble if Type-2)
            metric = route_info.get("metric", 64) & 0x3F
            if route_info.get("external", True):
                metric |= 0x80  # Set I/E bit for external metric
            ext_data.append(metric)
            # Delay metric (unsupported)
            ext_data.append(0x80)
            # Expense metric (unsupported)
            ext_data.append(0x80)
            # Error metric (unsupported)
            ext_data.append(0x80)

            # IP address and mask
            network = ip_network(prefix, strict=False)
            ext_data.extend(network.network_address.packed)
            ext_data.extend(network.netmask.packed)

            tlvs.append(TLV(TLV_IP_EXT_REACH, bytes(ext_data)))

        # Create LSP
        lsp = LSP(
            lsp_id=lsp_id,
            sequence_number=seq,
            remaining_lifetime=DEFAULT_LSP_LIFETIME,
            is_type=self.level,
            level=level,
            tlvs=tlvs,
            received_from=None,  # Local LSP
        )

        # Calculate checksum
        lsp.checksum = lsp.calculate_checksum()

        return lsp

    def _system_id_to_bytes(self, system_id: str) -> bytes:
        """Convert system ID string to 6 bytes"""
        # Format: "AABB.CCDD.EEFF" -> 6 bytes
        parts = system_id.replace(".", "")
        return bytes.fromhex(parts)

    async def _hello_loop(self, iface: ISISInterface) -> None:
        """Send periodic hellos on interface"""
        while self.running:
            try:
                await asyncio.sleep(iface.hello_interval)
                await self._send_hello(iface)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in hello loop for {iface.name}: {e}")

    async def _send_hello(self, iface: ISISInterface) -> None:
        """Send IIH on interface"""
        # In a real implementation, this would build and send an actual IIH packet
        # For simulation, we just log the event
        self.logger.debug(f"Sending IIH on {iface.name} (L{iface.level})")

    async def _lsp_refresh_loop(self) -> None:
        """Periodically refresh our LSP before it expires"""
        while self.running:
            try:
                await asyncio.sleep(DEFAULT_LSP_REFRESH_INTERVAL)
                self._originate_local_lsp()
                self.logger.debug("Refreshed local LSPs")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in LSP refresh loop: {e}")

    def _on_adjacency_up(self, adj: ISISAdjacency) -> None:
        """Handle adjacency becoming UP"""
        self.logger.info(f"Adjacency UP: {adj.system_id} on {adj.interface} (L{adj.level})")

        # Register neighbor for flooding
        if adj.level in (LEVEL_1, LEVEL_1_2) and self.dual_lsdb.l1_lsdb:
            self.dual_lsdb.l1_lsdb.register_neighbor(adj.system_id)

        if adj.level in (LEVEL_2, LEVEL_1_2) and self.dual_lsdb.l2_lsdb:
            self.dual_lsdb.l2_lsdb.register_neighbor(adj.system_id)

        # Re-originate LSP to include new neighbor
        self._originate_local_lsp()

    def _on_adjacency_down(self, adj: ISISAdjacency) -> None:
        """Handle adjacency going DOWN"""
        self.logger.info(f"Adjacency DOWN: {adj.system_id} on {adj.interface}")

        # Unregister neighbor from flooding
        if self.dual_lsdb.l1_lsdb:
            self.dual_lsdb.l1_lsdb.unregister_neighbor(adj.system_id)

        if self.dual_lsdb.l2_lsdb:
            self.dual_lsdb.l2_lsdb.unregister_neighbor(adj.system_id)

        # Re-originate LSP to remove neighbor
        self._originate_local_lsp()

        # Trigger SPF
        self.spf_calculator.schedule_spf(adj.level)

    def _on_dis_change(self, interface: str, level: int, new_dis: str) -> None:
        """Handle DIS change on interface"""
        am_dis = new_dis == self.system_id
        self.logger.info(f"DIS change on {interface} L{level}: {new_dis} (am_dis={am_dis})")

        # If we became DIS, start CSNP transmission
        if am_dis:
            # Start CSNP task for this interface/level
            pass

    def _on_lsp_change(self, lsp: LSP, level: int) -> None:
        """Handle LSP change in LSDB"""
        self.logger.debug(f"LSP change: {lsp.lsp_id} L{level} seq={lsp.sequence_number}")

        # Trigger SPF calculation
        self.spf_calculator.schedule_spf(level)

    def receive_hello(
        self,
        interface: str,
        system_id: str,
        level: int,
        priority: int,
        area_addresses: List[str],
        ip_addresses: List[str],
        hold_time: int,
        neighbors_seen: Optional[List[str]] = None,
    ) -> Optional[ISISAdjacency]:
        """
        Process received IIH packet.

        Args:
            interface: Interface received on
            system_id: Sender's system ID
            level: Hello level
            priority: DIS priority
            area_addresses: Sender's areas
            ip_addresses: Sender's IPs
            hold_time: Hold time
            neighbors_seen: Neighbors sender sees (for 3-way)

        Returns:
            Updated adjacency or None
        """
        iface = self.interfaces.get(interface)
        if not iface:
            self.logger.warning(f"Received hello on unknown interface {interface}")
            return None

        circuit_type = iface.circuit_type

        return self.adjacency_manager.process_hello(
            interface=interface,
            system_id=system_id,
            level=level,
            circuit_type=circuit_type,
            priority=priority,
            area_addresses=area_addresses,
            ip_addresses=ip_addresses,
            hold_time=hold_time,
            neighbors_in_hello=neighbors_seen,
        )

    def receive_lsp(self, lsp: LSP) -> bool:
        """
        Process received LSP.

        Args:
            lsp: Received LSP

        Returns:
            True if LSP was installed
        """
        return self.dual_lsdb.install_lsp(lsp)

    def get_routes(self) -> List[SPFRoute]:
        """Get all computed routes"""
        return list(self.spf_calculator.get_combined_routing_table().values())

    def redistribute_route(self, prefix: str, metric: int = 64,
                          metric_type: str = "external") -> bool:
        """
        Redistribute an external route into IS-IS.

        External routes are advertised in LSPs using IP External Reachability TLV (type 130)
        or Extended IP Reachability TLV (type 135) with the down/external bit set.

        Args:
            prefix: Network prefix to redistribute (e.g., "10.0.0.0/24")
            metric: External metric (default 64)
            metric_type: "external" or "internal" (affects metric handling)

        Returns:
            True if route was added successfully
        """
        try:
            # Parse prefix
            if '/' in prefix:
                network, prefix_len = prefix.split('/')
                prefix_len = int(prefix_len)
            else:
                network = prefix
                prefix_len = 32

            # Add to our local LSP as an external reachability entry
            # This will be flooded to neighbors when LSP is refreshed

            # Store external routes for inclusion in next LSP origination
            if not hasattr(self, '_external_routes'):
                self._external_routes: Dict[str, dict] = {}

            self._external_routes[prefix] = {
                "network": network,
                "prefix_len": prefix_len,
                "metric": metric,
                "external": metric_type == "external"
            }

            self.logger.info(f"✓ Added external route {prefix} to IS-IS (metric={metric})")

            # Re-originate LSP to include the new route
            self._originate_local_lsp()

            return True

        except Exception as e:
            self.logger.error(f"Failed to redistribute route {prefix}: {e}")
            return False

    def get_external_routes(self) -> Dict[str, dict]:
        """Get all externally redistributed routes"""
        if not hasattr(self, '_external_routes'):
            self._external_routes = {}
        return self._external_routes

    def get_adjacencies(self) -> List[ISISAdjacency]:
        """Get all adjacencies"""
        return self.adjacency_manager.get_adjacencies()

    def get_statistics(self) -> Dict[str, Any]:
        """Get IS-IS speaker statistics"""
        return {
            "system_id": self.system_id,
            "hostname": self.hostname,
            "level": self.level,
            "area_addresses": self.area_addresses,
            "interfaces": {
                name: {
                    "ip_address": iface.ip_address,
                    "network": iface.network,
                    "metric": iface.metric,
                    "level": iface.level,
                    "circuit_type": iface.circuit_type.name,
                }
                for name, iface in self.interfaces.items()
            },
            "adjacencies": self.adjacency_manager.get_statistics(),
            "lsdb": self.dual_lsdb.get_statistics(),
            "spf": self.spf_calculator.get_statistics(),
        }

    def is_running(self) -> bool:
        """Check if speaker is running"""
        return self.running


# Convenience function for simple IS-IS speaker
async def run_isis_speaker(
    system_id: str,
    area_addresses: List[str],
    interfaces: List[Dict],
    level: int = LEVEL_1_2,
    hostname: Optional[str] = None,
) -> None:
    """
    Run IS-IS speaker with given configuration.

    Args:
        system_id: System ID
        area_addresses: Area addresses
        interfaces: List of interface configurations
        level: IS-IS level
        hostname: Router hostname

    Example:
        await run_isis_speaker(
            system_id="0010.0100.1001",
            area_addresses=["49.0001"],
            interfaces=[
                {"name": "eth0", "ip_address": "10.0.0.1", "network": "10.0.0.0/24"},
                {"name": "eth1", "ip_address": "10.1.0.1", "network": "10.1.0.0/24"},
            ],
            level=LEVEL_1_2,
        )
    """
    speaker = ISISSpeaker(
        system_id=system_id,
        area_addresses=area_addresses,
        hostname=hostname,
        level=level,
    )

    # Add interfaces
    for iface_config in interfaces:
        speaker.add_interface(**iface_config)

    # Run speaker
    await speaker.run()
