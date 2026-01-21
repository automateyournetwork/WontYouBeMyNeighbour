"""
VXLAN Tunnel Endpoint (VTEP)

Implements the VXLAN data plane encapsulation and decapsulation
as per RFC 7348.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from datetime import datetime

from .vni import VNI, VNIManager


# VXLAN Header Constants
VXLAN_PORT = 4789           # Standard VXLAN UDP port
VXLAN_HEADER_LEN = 8        # VXLAN header is 8 bytes
VXLAN_FLAGS = 0x08          # I flag set, indicating valid VNI


@dataclass
class VXLANHeader:
    """
    VXLAN Header structure (RFC 7348).

    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |R|R|R|R|I|R|R|R|            Reserved                           |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                VXLAN Network Identifier (VNI) |   Reserved    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    """
    vni: int
    i_flag: bool = True  # VNI valid flag

    def to_bytes(self) -> bytes:
        """Serialize VXLAN header to bytes"""
        flags = VXLAN_FLAGS if self.i_flag else 0
        # Flags (1 byte) + Reserved (3 bytes) + VNI (3 bytes) + Reserved (1 byte)
        return struct.pack(
            "!BBBBBBBB",
            flags, 0, 0, 0,              # Flags and reserved
            (self.vni >> 16) & 0xFF,     # VNI high byte
            (self.vni >> 8) & 0xFF,      # VNI middle byte
            self.vni & 0xFF,             # VNI low byte
            0                             # Reserved
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'VXLANHeader':
        """Parse VXLAN header from bytes"""
        if len(data) < VXLAN_HEADER_LEN:
            raise ValueError(f"VXLAN header too short: {len(data)}")

        flags = data[0]
        i_flag = (flags & VXLAN_FLAGS) != 0
        vni = (data[4] << 16) | (data[5] << 8) | data[6]

        return cls(vni=vni, i_flag=i_flag)


@dataclass
class VXLANTunnel:
    """
    Represents a VXLAN tunnel to a remote VTEP.
    """
    remote_ip: str                    # Remote VTEP IP
    vnis: Set[int] = field(default_factory=set)  # VNIs on this tunnel
    state: str = "up"                 # Tunnel state

    # Statistics
    packets_tx: int = 0
    packets_rx: int = 0
    bytes_tx: int = 0
    bytes_rx: int = 0
    last_packet_time: Optional[datetime] = None

    # Configuration
    source_port_range: Tuple[int, int] = (49152, 65535)  # Entropy source port range

    def add_vni(self, vni: int) -> None:
        """Add VNI to tunnel"""
        self.vnis.add(vni)

    def remove_vni(self, vni: int) -> None:
        """Remove VNI from tunnel"""
        self.vnis.discard(vni)

    def update_stats_tx(self, packet_len: int) -> None:
        """Update transmit statistics"""
        self.packets_tx += 1
        self.bytes_tx += packet_len
        self.last_packet_time = datetime.now()

    def update_stats_rx(self, packet_len: int) -> None:
        """Update receive statistics"""
        self.packets_rx += 1
        self.bytes_rx += packet_len
        self.last_packet_time = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "remote_ip": self.remote_ip,
            "vnis": list(self.vnis),
            "state": self.state,
            "packets_tx": self.packets_tx,
            "packets_rx": self.packets_rx,
            "bytes_tx": self.bytes_tx,
            "bytes_rx": self.bytes_rx,
        }


class VTEP:
    """
    VXLAN Tunnel Endpoint.

    Handles VXLAN encapsulation/decapsulation and tunnel management.
    Integrates with EVPN for MAC/IP learning.
    """

    def __init__(
        self,
        local_ip: str,
        vni_manager: Optional[VNIManager] = None,
        source_interface: Optional[str] = None,
        udp_port: int = VXLAN_PORT,
    ):
        """
        Initialize VTEP.

        Args:
            local_ip: Local VTEP IP address (tunnel source)
            vni_manager: VNI manager instance
            source_interface: Source interface for tunnels
            udp_port: VXLAN UDP destination port
        """
        self.local_ip = local_ip
        self.vni_manager = vni_manager or VNIManager()
        self.source_interface = source_interface
        self.udp_port = udp_port

        # Remote VTEP tunnels: {remote_ip: VXLANTunnel}
        self._tunnels: Dict[str, VXLANTunnel] = {}

        # Flood list per VNI: {vni: [remote_vtep_ips]}
        self._flood_lists: Dict[int, Set[str]] = {}

        # MAC to VTEP mapping: {(vni, mac): vtep_ip}
        self._mac_table: Dict[Tuple[int, str], str] = {}

        # Callbacks
        self.on_mac_learned: Optional[Callable[[int, str, str], None]] = None
        self.on_tunnel_state_change: Optional[Callable[[str, str], None]] = None

        # UDP socket
        self._socket: Optional[socket.socket] = None
        self._receive_task: Optional[asyncio.Task] = None

        # Running state
        self.running = False

        self.logger = logging.getLogger(f"VTEP[{local_ip}]")

    async def start(self) -> None:
        """Start VTEP"""
        self.logger.info(f"Starting VTEP at {self.local_ip}")
        self.running = True

        # Create UDP socket for VXLAN
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.local_ip, self.udp_port))
            self._socket.setblocking(False)

            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_loop())

            self.logger.info(f"VTEP started, listening on UDP {self.udp_port}")
        except Exception as e:
            self.logger.error(f"Failed to start VTEP: {e}")
            self.running = False
            raise

    async def stop(self) -> None:
        """Stop VTEP"""
        self.logger.info("Stopping VTEP")
        self.running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._socket:
            self._socket.close()
            self._socket = None

        self.logger.info("VTEP stopped")

    def add_tunnel(self, remote_ip: str, vnis: Optional[List[int]] = None) -> VXLANTunnel:
        """
        Add tunnel to remote VTEP.

        Args:
            remote_ip: Remote VTEP IP
            vnis: Initial VNIs for tunnel

        Returns:
            Created tunnel
        """
        if remote_ip in self._tunnels:
            tunnel = self._tunnels[remote_ip]
            if vnis:
                for vni in vnis:
                    tunnel.add_vni(vni)
            return tunnel

        tunnel = VXLANTunnel(remote_ip=remote_ip)
        if vnis:
            tunnel.vnis = set(vnis)

        self._tunnels[remote_ip] = tunnel
        self.logger.info(f"Added tunnel to {remote_ip}")

        # Update flood lists
        for vni in tunnel.vnis:
            self._add_to_flood_list(vni, remote_ip)

        return tunnel

    def remove_tunnel(self, remote_ip: str) -> bool:
        """
        Remove tunnel to remote VTEP.

        Args:
            remote_ip: Remote VTEP IP

        Returns:
            True if removed
        """
        tunnel = self._tunnels.pop(remote_ip, None)
        if not tunnel:
            return False

        # Remove from flood lists
        for vni in tunnel.vnis:
            self._remove_from_flood_list(vni, remote_ip)

        # Remove MAC entries for this VTEP
        macs_to_remove = [
            key for key, vtep in self._mac_table.items()
            if vtep == remote_ip
        ]
        for key in macs_to_remove:
            del self._mac_table[key]

        self.logger.info(f"Removed tunnel to {remote_ip}")
        return True

    def get_tunnel(self, remote_ip: str) -> Optional[VXLANTunnel]:
        """Get tunnel by remote IP"""
        return self._tunnels.get(remote_ip)

    def add_vni_to_tunnel(self, remote_ip: str, vni: int) -> None:
        """Add VNI to existing tunnel"""
        tunnel = self._tunnels.get(remote_ip)
        if tunnel:
            tunnel.add_vni(vni)
            self._add_to_flood_list(vni, remote_ip)

    def _add_to_flood_list(self, vni: int, remote_ip: str) -> None:
        """Add VTEP to VNI flood list"""
        if vni not in self._flood_lists:
            self._flood_lists[vni] = set()
        self._flood_lists[vni].add(remote_ip)

    def _remove_from_flood_list(self, vni: int, remote_ip: str) -> None:
        """Remove VTEP from VNI flood list"""
        if vni in self._flood_lists:
            self._flood_lists[vni].discard(remote_ip)

    def learn_mac(self, vni: int, mac: str, vtep_ip: str) -> None:
        """
        Learn MAC address from remote VTEP.

        Args:
            vni: VNI
            mac: MAC address
            vtep_ip: VTEP IP where MAC is located
        """
        key = (vni, mac.upper())
        old_vtep = self._mac_table.get(key)

        self._mac_table[key] = vtep_ip

        # Update VNI manager
        vni_obj = self.vni_manager.get_vni(vni)
        if vni_obj:
            vni_obj.add_learned_mac(mac, vtep_ip)

        if old_vtep != vtep_ip:
            self.logger.debug(f"Learned MAC {mac} on VNI {vni} -> VTEP {vtep_ip}")
            if self.on_mac_learned:
                self.on_mac_learned(vni, mac, vtep_ip)

    def get_vtep_for_mac(self, vni: int, mac: str) -> Optional[str]:
        """Get VTEP IP for destination MAC"""
        return self._mac_table.get((vni, mac.upper()))

    def encapsulate(
        self,
        inner_frame: bytes,
        vni: int,
        dest_mac: str,
    ) -> Optional[Tuple[bytes, str]]:
        """
        Encapsulate frame in VXLAN.

        Args:
            inner_frame: Inner Ethernet frame
            vni: VNI to use
            dest_mac: Destination MAC address

        Returns:
            Tuple of (VXLAN packet, destination VTEP IP) or None
        """
        # Look up destination VTEP
        vtep_ip = self.get_vtep_for_mac(vni, dest_mac)

        if vtep_ip:
            # Unicast to known VTEP
            header = VXLANHeader(vni=vni)
            packet = header.to_bytes() + inner_frame

            # Update VNI stats
            vni_obj = self.vni_manager.get_vni(vni)
            if vni_obj:
                vni_obj.packets_encap += 1
                vni_obj.bytes_encap += len(packet)

            return (packet, vtep_ip)
        else:
            # Unknown unicast - will need to flood
            return None

    def encapsulate_flood(
        self,
        inner_frame: bytes,
        vni: int,
    ) -> List[Tuple[bytes, str]]:
        """
        Encapsulate frame for flooding (BUM traffic).

        Args:
            inner_frame: Inner Ethernet frame
            vni: VNI to flood on

        Returns:
            List of (VXLAN packet, destination VTEP IP) tuples
        """
        header = VXLANHeader(vni=vni)
        packet = header.to_bytes() + inner_frame

        flood_list = self._flood_lists.get(vni, set())

        return [(packet, vtep_ip) for vtep_ip in flood_list]

    async def send(
        self,
        vxlan_packet: bytes,
        dest_vtep: str,
    ) -> None:
        """
        Send VXLAN packet to remote VTEP.

        Args:
            vxlan_packet: VXLAN-encapsulated packet
            dest_vtep: Destination VTEP IP
        """
        if not self._socket:
            return

        try:
            self._socket.sendto(vxlan_packet, (dest_vtep, self.udp_port))

            # Update tunnel stats
            tunnel = self._tunnels.get(dest_vtep)
            if tunnel:
                tunnel.update_stats_tx(len(vxlan_packet))

        except Exception as e:
            self.logger.error(f"Failed to send to {dest_vtep}: {e}")

    def decapsulate(self, vxlan_packet: bytes, source_ip: str) -> Optional[Tuple[int, bytes]]:
        """
        Decapsulate VXLAN packet.

        Args:
            vxlan_packet: Received VXLAN packet
            source_ip: Source VTEP IP

        Returns:
            Tuple of (VNI, inner frame) or None
        """
        if len(vxlan_packet) < VXLAN_HEADER_LEN:
            self.logger.warning(f"Packet too short from {source_ip}")
            return None

        try:
            header = VXLANHeader.from_bytes(vxlan_packet[:VXLAN_HEADER_LEN])

            if not header.i_flag:
                self.logger.warning(f"Invalid VXLAN header (I flag not set) from {source_ip}")
                return None

            inner_frame = vxlan_packet[VXLAN_HEADER_LEN:]

            # Update stats
            vni_obj = self.vni_manager.get_vni(header.vni)
            if vni_obj:
                vni_obj.packets_decap += 1
                vni_obj.bytes_decap += len(vxlan_packet)

            tunnel = self._tunnels.get(source_ip)
            if tunnel:
                tunnel.update_stats_rx(len(vxlan_packet))

            # Learn source MAC from inner frame
            if len(inner_frame) >= 14:
                src_mac = self._extract_src_mac(inner_frame)
                self.learn_mac(header.vni, src_mac, source_ip)

            return (header.vni, inner_frame)

        except Exception as e:
            self.logger.error(f"Failed to decapsulate from {source_ip}: {e}")
            return None

    def _extract_src_mac(self, frame: bytes) -> str:
        """Extract source MAC from Ethernet frame"""
        # Ethernet header: dst_mac (6) + src_mac (6) + ethertype (2)
        src_mac_bytes = frame[6:12]
        return ":".join(f"{b:02X}" for b in src_mac_bytes)

    async def _receive_loop(self) -> None:
        """Receive loop for VXLAN packets"""
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                # Use run_in_executor for non-blocking receive
                data, addr = await loop.run_in_executor(
                    None,
                    lambda: self._socket.recvfrom(65535)
                )

                source_ip = addr[0]
                result = self.decapsulate(data, source_ip)

                if result:
                    vni, inner_frame = result
                    # Process inner frame (could emit event or forward)
                    self.logger.debug(f"Received frame on VNI {vni} from {source_ip}")

            except asyncio.CancelledError:
                break
            except BlockingIOError:
                await asyncio.sleep(0.01)
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in receive loop: {e}")

    def get_all_tunnels(self) -> List[VXLANTunnel]:
        """Get all tunnels"""
        return list(self._tunnels.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get VTEP statistics"""
        total_tx = sum(t.packets_tx for t in self._tunnels.values())
        total_rx = sum(t.packets_rx for t in self._tunnels.values())

        return {
            "local_ip": self.local_ip,
            "udp_port": self.udp_port,
            "running": self.running,
            "tunnels": len(self._tunnels),
            "mac_entries": len(self._mac_table),
            "vnis_configured": self.vni_manager.get_statistics()["total_vnis"],
            "total_packets_tx": total_tx,
            "total_packets_rx": total_rx,
        }
