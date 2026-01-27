"""
OSPF Hello Protocol Handler
RFC 2328 Section 9.5 - Sending Hello packets
RFC 2328 Section 10.5 - Receiving Hello packets
"""

import time
import logging
from typing import Dict, Optional, Callable
from ospf.packets import OSPFHeader, OSPFHello, parse_ospf_packet
from ospf.constants import (
    HELLO_PACKET, HELLO_INTERVAL, ROUTER_DEAD_INTERVAL,
    ALLSPFROUTERS, NETWORK_TYPE_BROADCAST, NETWORK_TYPE_POINT_TO_MULTIPOINT,
    NETWORK_TYPE_POINT_TO_POINT, DEFAULT_NETWORK_TYPE
)

logger = logging.getLogger(__name__)


class HelloHandler:
    """
    Manage OSPF Hello protocol for neighbor discovery and maintenance
    """

    def __init__(self, router_id: str, area_id: str, interface: str,
                 network_mask: str = "255.255.255.0",
                 hello_interval: int = HELLO_INTERVAL,
                 dead_interval: int = ROUTER_DEAD_INTERVAL,
                 priority: int = 1,
                 network_type: str = DEFAULT_NETWORK_TYPE):
        """
        Initialize Hello handler

        Args:
            router_id: This router's ID
            area_id: OSPF area ID
            interface: Network interface name
            network_mask: Subnet mask
            hello_interval: Seconds between Hello packets
            dead_interval: Seconds before declaring neighbor dead
            priority: Router priority for DR/BDR election (0 for p2mp/p2p)
            network_type: Network type (broadcast, point-to-multipoint, point-to-point, etc.)
        """
        self.router_id = router_id
        self.area_id = area_id
        self.interface = interface
        self.network_mask = network_mask
        self.hello_interval = hello_interval
        self.dead_interval = dead_interval
        self.network_type = network_type

        # For point-to-multipoint and point-to-point, priority is always 0
        if network_type in [NETWORK_TYPE_POINT_TO_MULTIPOINT, NETWORK_TYPE_POINT_TO_POINT]:
            self.priority = 0
        else:
            self.priority = priority

        # Neighbor tracking (router_id -> last_seen_timestamp)
        self.neighbors: Dict[str, float] = {}

        # DR/BDR (initially none)
        self.designated_router = "0.0.0.0"
        self.backup_designated_router = "0.0.0.0"

        # Callbacks
        self.on_neighbor_discovered: Optional[Callable] = None
        self.on_neighbor_dead: Optional[Callable] = None
        self.on_hello_received: Optional[Callable] = None

        # Message statistics
        self.stats = {
            'hello_sent': 0,
            'hello_recv': 0,
            'dbd_sent': 0,
            'dbd_recv': 0,
            'lsr_sent': 0,
            'lsr_recv': 0,
            'lsu_sent': 0,
            'lsu_recv': 0,
            'lsack_sent': 0,
            'lsack_recv': 0
        }

        logger.info(f"Hello handler initialized for {router_id} on {interface}")

    def build_hello_packet(self, active_neighbors: Optional[list] = None) -> bytes:
        """
        Build OSPF Hello packet

        Args:
            active_neighbors: List of neighbor router IDs to include in Hello.
                            If None, uses self.neighbors (for backward compatibility)

        Returns:
            Hello packet as bytes
        """
        # Use provided neighbor list or fall back to internal tracking
        if active_neighbors is None:
            active_neighbors = list(self.neighbors.keys())

        # Build OSPF header
        header = OSPFHeader(
            version=2,
            type=HELLO_PACKET,
            router_id=self.router_id,
            area_id=self.area_id,
            auth_type=0  # No authentication for now
        )

        # Build Hello packet
        hello = OSPFHello(
            network_mask=self.network_mask,
            hello_interval=self.hello_interval,
            options=0x02,  # E-bit (external routing capability)
            router_priority=self.priority,
            router_dead_interval=self.dead_interval,
            designated_router=self.designated_router,
            backup_designated_router=self.backup_designated_router,
            neighbors=active_neighbors  # Use provided or internal neighbor list
        )

        # Combine and serialize
        packet = header / hello

        # Increment send counter
        self.stats['hello_sent'] += 1

        return bytes(packet)

    def process_hello(self, packet_data: bytes, source_ip: str) -> Optional[str]:
        """
        Process received Hello packet

        Args:
            packet_data: Raw packet bytes
            source_ip: Source IP address

        Returns:
            Neighbor router ID if valid, None otherwise
        """
        try:
            # Parse packet
            packet = parse_ospf_packet(packet_data)
            if not packet or packet.type != HELLO_PACKET:
                logger.warning(f"Invalid Hello packet from {source_ip}")
                return None

            # Validate area
            if packet.area_id != self.area_id:
                logger.warning(f"Hello from {source_ip} with mismatched area: {packet.area_id} != {self.area_id}")
                return None

            # Extract Hello fields
            hello = packet[OSPFHello]

            # Validate Hello parameters (RFC 2328 Section 10.5)
            if hello.network_mask != self.network_mask:
                logger.warning(f"Hello from {source_ip} with mismatched network mask")
                return None

            if hello.hello_interval != self.hello_interval:
                logger.warning(f"Hello from {source_ip} with mismatched hello interval")
                return None

            if hello.router_dead_interval != self.dead_interval:
                logger.warning(f"Hello from {source_ip} with mismatched dead interval")
                return None

            # Extract neighbor router ID
            neighbor_id = packet.router_id
            logger.debug(f"Received valid Hello from {neighbor_id} ({source_ip})")

            # Increment receive counter
            self.stats['hello_recv'] += 1

            # Update neighbor last seen time
            now = time.time()
            is_new = neighbor_id not in self.neighbors
            self.neighbors[neighbor_id] = now

            # Check if we're in their neighbor list (bidirectional check)
            bidirectional = self.router_id in hello.neighbors

            # Update DR/BDR
            self.designated_router = hello.designated_router
            self.backup_designated_router = hello.backup_designated_router

            # Trigger callbacks
            if is_new and self.on_neighbor_discovered:
                self.on_neighbor_discovered(neighbor_id, source_ip, hello.router_priority)

            if self.on_hello_received:
                self.on_hello_received(neighbor_id, source_ip, bidirectional, hello)

            return neighbor_id

        except Exception as e:
            logger.error(f"Error processing Hello from {source_ip}: {e}")
            return None

    def check_dead_neighbors(self) -> list:
        """
        Check for dead neighbors (no Hello in dead_interval)

        Returns:
            List of dead neighbor router IDs
        """
        now = time.time()
        dead_neighbors = []

        for neighbor_id, last_seen in list(self.neighbors.items()):
            if now - last_seen > self.dead_interval:
                logger.warning(f"Neighbor {neighbor_id} declared dead (timeout)")
                dead_neighbors.append(neighbor_id)
                del self.neighbors[neighbor_id]

                # Trigger callback
                if self.on_neighbor_dead:
                    self.on_neighbor_dead(neighbor_id)

        return dead_neighbors

    def get_neighbors(self) -> Dict[str, float]:
        """
        Get current neighbors

        Returns:
            Dict of neighbor_id -> last_seen_timestamp
        """
        return self.neighbors.copy()

    def remove_neighbor(self, neighbor_id: str):
        """
        Remove neighbor from list

        Args:
            neighbor_id: Neighbor router ID to remove
        """
        if neighbor_id in self.neighbors:
            del self.neighbors[neighbor_id]
            logger.info(f"Removed neighbor {neighbor_id}")

    def get_neighbor_count(self) -> int:
        """
        Get number of active neighbors

        Returns:
            Count of neighbors
        """
        return len(self.neighbors)

    def should_form_adjacency(self, neighbor_id: str, neighbor_priority: int) -> bool:
        """
        Determine if we should form full adjacency with a neighbor
        based on network type (RFC 2328 Section 10.4)

        Args:
            neighbor_id: Neighbor router ID
            neighbor_priority: Neighbor's router priority

        Returns:
            True if adjacency should be formed
        """
        # Point-to-point and point-to-multipoint: Always form adjacency
        if self.network_type in [NETWORK_TYPE_POINT_TO_POINT, NETWORK_TYPE_POINT_TO_MULTIPOINT]:
            return True

        # Broadcast and NBMA: Form adjacency if we are DR or BDR, or if neighbor is DR or BDR
        if self.network_type == NETWORK_TYPE_BROADCAST:
            # Check if we are DR or BDR
            if self.designated_router == self.router_id or self.backup_designated_router == self.router_id:
                return True

            # Check if neighbor is DR or BDR
            if self.designated_router == neighbor_id or self.backup_designated_router == neighbor_id:
                return True

            # Otherwise, stay in 2-Way state
            return False

        # Default: form adjacency
        return True

    def __repr__(self) -> str:
        return (f"HelloHandler(router_id={self.router_id}, "
                f"interface={self.interface}, "
                f"network_type={self.network_type}, "
                f"neighbors={len(self.neighbors)})")
