#!/usr/bin/env python3
"""
Won't You Be My Neighbor - Unified Routing Agent
Supports OSPF (RFC 2328) and BGP-4 (RFC 4271) routing protocols

Usage - OSPF only:
    sudo python3 wontyoubemyneighbor.py \\
        --router-id 10.255.255.99 \\
        --area 0.0.0.0 \\
        --interface eth0

Usage - BGP only:
    python3 wontyoubemyneighbor.py \\
        --router-id 192.0.2.1 \\
        --bgp-local-as 65001 \\
        --bgp-peer 192.0.2.2 \\
        --bgp-peer-as 65002 \\
        --bgp-network 10.2.2.2/32

Usage - Both OSPF and BGP:
    sudo python3 wontyoubemyneighbor.py \\
        --router-id 10.0.1.1 \\
        --area 0.0.0.0 \\
        --interface eth0 \\
        --bgp-local-as 65001 \\
        --bgp-peer 192.0.2.2 \\
        --bgp-peer-as 65002
"""

import asyncio
import argparse
import logging
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
                # Receive packet
                result = self.socket.receive(timeout=0.5)
                if not result:
                    # Yield control to event loop to allow other tasks to run
                    await asyncio.sleep(0)
                    continue

                data, source_ip = result

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
                    next_hop = route_info.next_hop
                    cost = route_info.cost
                    if next_hop and next_hop != self.source_ip:
                        self.kernel_route_manager.install_route(
                            prefix, next_hop, metric=cost, protocol="ospf"
                        )

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
        success, lsa_headers_needed, exchange_complete = self.adjacency_mgr.process_dbd(data, neighbor)

        if not success:
            self.logger.warning(f"Failed to process DBD from {neighbor_id}")
            return

        # Add needed LSAs to request list
        if lsa_headers_needed:
            neighbor.ls_request_list.extend(lsa_headers_needed)
            self.logger.info(f"Added {len(lsa_headers_needed)} LSAs to request list for {neighbor_id}")
            self.logger.info(f"ls_request_list now has {len(neighbor.ls_request_list)} LSAs")

        # CRITICAL FIX: Call exchange_done() AFTER populating ls_request_list
        # This ensures the correct state transition (Exchange -> Loading if LSAs needed, or -> Full if not)
        if exchange_complete:
            self.logger.info(f"Calling exchange_done() for {neighbor_id}, ls_request_list size={len(neighbor.ls_request_list)}")
            neighbor.exchange_done()

        # Handle state transitions
        new_state = neighbor.get_state()
        if current_state != new_state:
            self.logger.info(f"Neighbor {neighbor_id}: "
                           f"{STATE_NAMES[current_state]} → {STATE_NAMES[new_state]}")

            if new_state == STATE_EXCHANGE:
                # Start sending our DBD packets
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
            # Check if we still have more LSA headers to send
            if hasattr(neighbor, 'db_summary_list') and len(neighbor.db_summary_list) > 0:
                # We have more LSAs to send, continue exchange
                self.logger.debug(f"Continuing DBD exchange with {neighbor_id}, "
                                f"{len(neighbor.db_summary_list)} headers remaining")
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

        # Process LSU - returns (success, ack_packet, updated_lsas)
        success, ack_packet, updated_lsas = self.flooding_mgr.process_ls_update(data, neighbor)

        if success:
            # Send LSAck if needed (unicast to neighbor)
            if ack_packet:
                self.socket.send(ack_packet, dest=neighbor.ip_address)
                self.logger.debug(f"Sent LSAck to {neighbor_id}")

            # Flood new LSAs to other neighbors (RFC 2328 Section 13.3)
            if updated_lsas:
                self.logger.info(f"Flooding {len(updated_lsas)} LSAs to other neighbors")
                for lsa in updated_lsas:
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

                # Run SPF after topology changes
                await self._run_spf()

            # Check if loading is complete
            if neighbor.get_state() == STATE_FULL:
                self.logger.info(f"✓ Adjacency FULL with {neighbor_id}")
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

    async def _send_lsr(self, neighbor: OSPFNeighbor):
        """
        Send Link State Request to neighbor

        Args:
            neighbor: Target neighbor
        """
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


async def run_unified_agent(args: argparse.Namespace):
    """
    Run OSPF, BGP, or both based on command-line arguments

    Args:
        args: Parsed command-line arguments
    """
    logger = logging.getLogger("UnifiedAgent")

    ospf_agent = None
    bgp_speaker = None
    tasks = []

    # Determine what protocols to run
    run_ospf = args.interface is not None  # OSPF requires interface
    run_bgp = args.bgp_local_as is not None  # BGP requires local AS

    if not run_ospf and not run_bgp:
        logger.error("Must specify either OSPF (--interface) or BGP (--bgp-local-as) configuration")
        sys.exit(1)

    # Determine agent type for banner
    if run_ospf and run_bgp:
        agent_type = "Unified OSPF+BGP Agent"
    elif run_bgp:
        agent_type = "BGP Agent"
    else:
        agent_type = "OSPF Agent"

    logger.info(f"Starting Won't You Be My Neighbor - {agent_type} - Router ID: {args.router_id}")
    if run_ospf:
        logger.info(f"  OSPF: Enabled (Area {args.area}, Interface {args.interface})")
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

        # Initialize OSPF if requested
        if run_ospf:
            logger.info("Initializing OSPF agent...")
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
            tasks.append(asyncio.create_task(ospf_agent.start()))

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
                        connect_retry_time=args.bgp_connect_retry
                    )

            # Start BGP speaker
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
        if bgp_speaker:
            logger.info("Stopping BGP speaker...")
            await bgp_speaker.stop()

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

    # Common arguments
    parser.add_argument("--router-id", required=True,
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

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Validate configuration
    if not args.interface and not args.bgp_local_as:
        print("Error: Must specify either OSPF (--interface) or BGP (--bgp-local-as) configuration")
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
