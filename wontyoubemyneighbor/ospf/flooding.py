"""
OSPF LSA Flooding Manager
RFC 2328 Section 13 - The Flooding Procedure
RFC 2328 Section 13.3 - Next step in the flooding procedure
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from scapy.packet import Raw
from ospf.packets import (
    OSPFHeader, OSPFLSUpdate, OSPFLSAck, OSPFLSRequest, LSRequest,
    LSAHeader, RouterLSA, NetworkLSA, parse_ospf_packet
)
from ospf.neighbor import OSPFNeighbor
from ospf.lsdb import LinkStateDatabase, LSA
from ospf.constants import (
    LINK_STATE_REQUEST, LINK_STATE_UPDATE, LINK_STATE_ACK,
    STATE_FULL, STATE_LOADING, EVENT_LOADING_DONE,
    ROUTER_LSA, NETWORK_LSA
)

logger = logging.getLogger(__name__)


class LSAFloodingManager:
    """
    Manage LSA flooding procedure per RFC 2328 Section 13
    """

    def __init__(self, router_id: str, lsdb: LinkStateDatabase):
        """
        Initialize LSA flooding manager

        Args:
            router_id: This router's ID
            lsdb: Link State Database
        """
        self.router_id = router_id
        self.lsdb = lsdb

        # Track pending LSA requests
        self.pending_requests: Dict[str, List[Tuple]] = {}  # neighbor_id -> [(type, id, adv_router)]

        # Track retransmission timestamps: neighbor_id -> {lsa_key: timestamp}
        self.retransmit_timestamps: Dict[str, Dict[Tuple, float]] = {}

        # Retransmission interval (RFC 2328: RxmtInterval)
        self.retransmit_interval = 5  # seconds

        logger.info(f"Initialized LSAFloodingManager for {router_id}")

    def build_ls_request(self, neighbor: OSPFNeighbor, area_id: str) -> Optional[bytes]:
        """
        Build Link State Request packet

        Args:
            neighbor: Neighbor to request from
            area_id: OSPF area ID

        Returns:
            LSR packet as bytes, or None if no requests needed
        """
        if not neighbor.ls_request_list:
            logger.debug(f"No LSA requests needed for {neighbor.router_id}")
            return None

        # Build LSR packet
        header = OSPFHeader(
            version=2,
            type=LINK_STATE_REQUEST,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        # Build request entries
        requests = []
        for lsa_header in neighbor.ls_request_list[:10]:  # Limit to 10 per packet
            request = LSRequest(
                ls_type=lsa_header.ls_type,
                link_state_id=lsa_header.link_state_id,
                advertising_router=lsa_header.advertising_router
            )
            requests.append(request)

        lsr = OSPFLSRequest(requests=requests)
        packet = header / lsr

        logger.info(f"Built LSR for {neighbor.router_id} with {len(requests)} requests")

        return bytes(packet)

    def process_ls_request(self, packet_data: bytes, neighbor: OSPFNeighbor,
                          area_id: str) -> Optional[bytes]:
        """
        Process Link State Request and build Link State Update response

        Args:
            packet_data: Raw LSR packet
            neighbor: Neighbor who sent the request
            area_id: OSPF area ID

        Returns:
            LSU packet as bytes, or None if no LSAs to send
        """
        try:
            # Parse LSR packet
            packet = parse_ospf_packet(packet_data)
            if not packet or packet.type != LINK_STATE_REQUEST:
                logger.warning(f"Invalid LSR packet from {neighbor.router_id}")
                return None

            lsr = packet[OSPFLSRequest]

            # Collect requested LSAs
            lsas_to_send = []
            for request in lsr.requests:
                lsa = self.lsdb.get_lsa(
                    request.ls_type,
                    request.link_state_id,
                    request.advertising_router
                )

                if lsa:
                    lsas_to_send.append(lsa)
                    logger.debug(f"Found requested LSA: {lsa}")
                else:
                    logger.warning(f"Requested LSA not found: type={request.ls_type}, "
                                 f"id={request.link_state_id}, adv={request.advertising_router}")

            if not lsas_to_send:
                return None

            # Build LSU packet
            return self.build_ls_update(lsas_to_send, area_id)

        except Exception as e:
            logger.error(f"Error processing LSR from {neighbor.router_id}: {e}")
            return None

    def process_ls_update(self, packet_data: bytes, neighbor: OSPFNeighbor) -> Tuple[bool, Optional[bytes], List[LSA]]:
        """
        Process Link State Update packet

        Args:
            packet_data: Raw LSU packet
            neighbor: Neighbor who sent the update

        Returns:
            Tuple of (success, LSAck packet bytes or None, list of newly installed LSAs)
        """
        try:
            # Parse LSU packet
            packet = parse_ospf_packet(packet_data)
            if not packet or packet.type != LINK_STATE_UPDATE:
                logger.warning(f"Invalid LSU packet from {neighbor.router_id}")
                return (False, None, [])

            lsu = packet[OSPFLSUpdate]

            # Process each LSA
            acked_headers = []
            updated_lsas = []

            num_lsas = lsu.num_lsas if lsu.num_lsas is not None else 0
            logger.info(f"Processing LSU from {neighbor.router_id} with {num_lsas} LSAs")

            # Extract LSAs from packet payload
            lsas = self._extract_lsas_from_lsu(packet_data)

            for lsa in lsas:
                try:
                    # DETAILED DEBUGGING: Show exactly what we're processing
                    logger.info(f"Processing LSA from packet: Type={lsa.header.ls_type}, "
                              f"LinkStateID={lsa.header.link_state_id}, "
                              f"AdvRouter={lsa.header.advertising_router}, "
                              f"Seq={hex(lsa.header.ls_sequence_number)}")

                    # Check if this is a newer LSA
                    is_newer = self.lsdb.is_lsa_newer(lsa.header)

                    if is_newer:
                        # Install in LSDB (header and body)
                        self.lsdb.add_lsa(lsa.header, lsa_body=lsa.body)
                        logger.debug(f"Installed LSA: Type {lsa.header.ls_type}, "
                                   f"ID {lsa.header.link_state_id}")
                        updated_lsas.append(lsa)

                    # Add to acknowledgment list
                    acked_headers.append(lsa.header)

                    # Remove from neighbor's request list if present
                    if neighbor.get_state() == STATE_LOADING:
                        # Check if this LSA was in our request list
                        neighbor.ls_request_list = [
                            h for h in neighbor.ls_request_list
                            if not (h.ls_type == lsa.header.ls_type and
                                   h.link_state_id == lsa.header.link_state_id and
                                   h.advertising_router == lsa.header.advertising_router)
                        ]

                except Exception as e:
                    logger.error(f"Error processing LSA from {neighbor.router_id}: {e}")

            # Check if this completes loading state
            if neighbor.get_state() == STATE_LOADING:
                if len(neighbor.ls_request_list) == 0:
                    logger.info(f"Loading complete for {neighbor.router_id}")
                    neighbor.loading_done()

            # Return updated LSAs for flooding to other neighbors
            logger.info(f"Processed {len(updated_lsas)} new/updated LSAs from {neighbor.router_id}")

            # Build LSAck if we have headers to acknowledge
            lsack_packet = None
            if acked_headers:
                area_id = packet.area_id
                lsack_packet = self.build_ls_ack(acked_headers, area_id)

            return (True, lsack_packet, updated_lsas)

        except Exception as e:
            logger.error(f"Error processing LSU from {neighbor.router_id}: {e}")
            return (False, None, [])

    def process_ls_ack(self, packet_data: bytes, neighbor: OSPFNeighbor) -> bool:
        """
        Process Link State Acknowledgment packet

        Args:
            packet_data: Raw LSAck packet
            neighbor: Neighbor who sent the ack

        Returns:
            True if processed successfully
        """
        try:
            # Parse LSAck packet
            packet = parse_ospf_packet(packet_data)
            if not packet or packet.type != LINK_STATE_ACK:
                logger.warning(f"Invalid LSAck packet from {neighbor.router_id}")
                return False

            # In real implementation, would:
            # 1. Extract acknowledged LSA headers
            # 2. Remove from neighbor's ls_retransmission_list
            # 3. Update retransmission timers

            logger.debug(f"Processed LSAck from {neighbor.router_id}")

            return True

        except Exception as e:
            logger.error(f"Error processing LSAck from {neighbor.router_id}: {e}")
            return False

    def build_ls_update(self, lsas: List[LSA], area_id: str) -> bytes:
        """
        Build Link State Update packet

        Args:
            lsas: List of LSAs to include
            area_id: OSPF area ID

        Returns:
            LSU packet as bytes
        """
        header = OSPFHeader(
            version=2,
            type=LINK_STATE_UPDATE,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        lsu = OSPFLSUpdate(
            num_lsas=len(lsas)
        )

        # Attach each LSA (header + body) as raw payload
        lsa_bytes = b''
        for lsa in lsas:
            # Build complete LSA packet (header / body) so Scapy can auto-calculate length/checksum
            if lsa.body:
                # Force recalculation of length and checksum
                lsa.header.length = None
                lsa.header.ls_checksum = None
                # Build complete packet
                complete_lsa_packet = lsa.header / lsa.body
                # Serialize the complete packet (Scapy will auto-calculate length/checksum in post_build)
                complete_lsa_bytes = bytes(complete_lsa_packet)
            else:
                # Just header, no body
                lsa.header.length = 20
                lsa.header.ls_checksum = None
                complete_lsa_bytes = bytes(lsa.header)

            # Add to LSU payload
            lsa_bytes += complete_lsa_bytes

        # Build packet: OSPF header / LSU header / LSA payload
        # CRITICAL: Build in correct order so OSPF header checksum includes everything
        header.len = None  # Will be auto-calculated
        header.chksum = None  # Will be auto-calculated

        if lsa_bytes:
            # Build with LSAs attached
            packet = header / lsu / Raw(load=lsa_bytes)
        else:
            # Just header + LSU
            packet = header / lsu

        # Debug: Show OSPF packet header details
        final_packet_bytes = bytes(packet)
        logger.debug(f"Built LSU with {len(lsas)} LSAs, total {len(lsa_bytes)} bytes of LSA data")
        logger.debug(f"Final LSU packet length: {len(final_packet_bytes)} bytes")
        logger.debug(f"OSPF header (24 bytes): {final_packet_bytes[:24].hex()}")
        logger.debug(f"LSU header: {final_packet_bytes[24:28].hex() if len(final_packet_bytes) > 28 else 'N/A'}")

        # Debug: Show details of each LSA being sent
        offset = 0
        for i, lsa in enumerate(lsas):
            # Calculate the size of this LSA in the payload
            if lsa.body:
                lsa_size = 20 + len(bytes(lsa.body))
            else:
                lsa_size = 20

            logger.debug(f"  LSA {i}: type={lsa.header.ls_type}, "
                       f"adv={lsa.header.advertising_router}, "
                       f"size={lsa_size} bytes, "
                       f"has_body={lsa.body is not None}")
            if lsa.body and hasattr(lsa.body, 'links'):
                logger.debug(f"    Body has {len(lsa.body.links)} links")

            # Show hex of this LSA
            lsa_hex = lsa_bytes[offset:offset+min(lsa_size, 48)].hex()
            logger.debug(f"    Hex (first 48 bytes): {lsa_hex}")
            offset += lsa_size

        return bytes(packet)

    def build_ls_ack(self, lsa_headers: List[LSAHeader], area_id: str) -> bytes:
        """
        Build Link State Acknowledgment packet

        Args:
            lsa_headers: List of LSA headers to acknowledge
            area_id: OSPF area ID

        Returns:
            LSAck packet as bytes
        """
        header = OSPFHeader(
            version=2,
            type=LINK_STATE_ACK,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        ack = OSPFLSAck()

        # Build packet
        packet = header / ack

        # Attach LSA headers as payload (each header is 20 bytes)
        if lsa_headers:
            headers_bytes = b''
            for lsa_header in lsa_headers:
                # Serialize each LSA header (20 bytes)
                header_bytes = bytes(lsa_header)
                headers_bytes += header_bytes

            # Attach as Raw payload
            packet = packet / Raw(load=headers_bytes)

        # Force OSPF header checksum recalculation
        header.len = None
        header.chksum = None
        if lsa_headers:
            packet = header / ack / Raw(load=headers_bytes)
        else:
            packet = header / ack

        logger.debug(f"Built LSAck with {len(lsa_headers)} headers, {len(lsa_headers) * 20} bytes")

        return bytes(packet)

    def flood_lsa(self, lsa: LSA, exclude_neighbor: Optional[OSPFNeighbor] = None,
                  neighbors: Optional[List[OSPFNeighbor]] = None,
                  area_id: str = "0.0.0.0") -> int:
        """
        Flood LSA to all neighbors except specified one

        Args:
            lsa: LSA to flood
            exclude_neighbor: Neighbor to exclude (usually the sender)
            neighbors: List of all neighbors
            area_id: OSPF area ID

        Returns:
            Number of neighbors LSA was flooded to
        """
        if neighbors is None:
            neighbors = []

        flooded_count = 0

        for neighbor in neighbors:
            # Skip excluded neighbor
            if exclude_neighbor and neighbor.router_id == exclude_neighbor.router_id:
                continue

            # Only flood to Full neighbors
            if neighbor.get_state() != STATE_FULL:
                continue

            # Add to retransmission list
            if lsa not in neighbor.ls_retransmission_list:
                neighbor.ls_retransmission_list.append(lsa)

            flooded_count += 1

        logger.info(f"Flooded LSA {lsa} to {flooded_count} neighbors")

        return flooded_count

    def send_ls_request(self, neighbor: OSPFNeighbor, area_id: str) -> bool:
        """
        Send Link State Request to neighbor (Loading state)

        Args:
            neighbor: Neighbor to request from
            area_id: OSPF area ID

        Returns:
            True if request sent (or none needed)
        """
        if not neighbor.ls_request_list:
            # No LSAs to request, transition to Full
            logger.info(f"No LSAs to request from {neighbor.router_id}, going to Full")
            neighbor.loading_done()
            return True

        # Build and send LSR
        lsr_packet = self.build_ls_request(neighbor, area_id)

        if lsr_packet:
            # In real implementation, would actually send the packet
            # For now, just log
            logger.info(f"Would send LSR to {neighbor.router_id} requesting {len(neighbor.ls_request_list)} LSAs")
            return True

        return False

    def check_request_list(self, neighbor: OSPFNeighbor):
        """
        Check if neighbor's request list is empty and transition to Full if so

        Args:
            neighbor: Neighbor to check
        """
        if neighbor.get_state() == STATE_LOADING and len(neighbor.ls_request_list) == 0:
            logger.info(f"Request list empty for {neighbor.router_id}, transitioning to Full")
            neighbor.loading_done()

    def add_lsa_to_retransmission_list(self, lsa: LSA, neighbor: OSPFNeighbor):
        """
        Add LSA to neighbor's retransmission list with timestamp tracking

        Args:
            lsa: LSA to add
            neighbor: Target neighbor
        """
        if lsa not in neighbor.ls_retransmission_list:
            neighbor.ls_retransmission_list.append(lsa)

            # Track timestamp for retransmission timing
            if neighbor.router_id not in self.retransmit_timestamps:
                self.retransmit_timestamps[neighbor.router_id] = {}

            lsa_key = lsa.get_key()
            self.retransmit_timestamps[neighbor.router_id][lsa_key] = time.time()

            logger.debug(f"Added LSA to retransmission list for {neighbor.router_id}: {lsa}")

    def remove_from_retransmission_list(self, lsa_header: LSAHeader, neighbor: OSPFNeighbor):
        """
        Remove LSA from neighbor's retransmission list (after ACK received)

        Args:
            lsa_header: LSA header that was acknowledged
            neighbor: Neighbor who acknowledged
        """
        # Remove matching LSA from retransmission list
        neighbor.ls_retransmission_list = [
            lsa for lsa in neighbor.ls_retransmission_list
            if not (lsa.header.ls_type == lsa_header.ls_type and
                   lsa.header.link_state_id == lsa_header.link_state_id and
                   lsa.header.advertising_router == lsa_header.advertising_router)
        ]

        # Clean up timestamp tracking
        if neighbor.router_id in self.retransmit_timestamps:
            lsa_key = (lsa_header.ls_type, lsa_header.link_state_id, lsa_header.advertising_router)
            if lsa_key in self.retransmit_timestamps[neighbor.router_id]:
                del self.retransmit_timestamps[neighbor.router_id][lsa_key]

        logger.debug(f"Removed LSA from retransmission list for {neighbor.router_id}")

    def _extract_lsas_from_lsu(self, packet_data: bytes) -> List[LSA]:
        """
        Extract LSAs from Link State Update packet

        Args:
            packet_data: Raw LSU packet bytes

        Returns:
            List of LSA objects
        """
        lsas = []

        try:
            # Parse packet
            packet = parse_ospf_packet(packet_data)
            if not packet or not packet.haslayer(OSPFLSUpdate):
                return lsas

            lsu = packet[OSPFLSUpdate]

            # LSAs are in the payload
            # Note: In production, would properly parse each LSA type
            # For now, we extract LSA headers and create basic LSA objects
            payload = bytes(lsu.payload) if lsu.payload else b''

            offset = 0
            while offset + 20 <= len(payload):  # At least LSA header (20 bytes)
                try:
                    # Extract LSA header (20 bytes)
                    header_bytes = payload[offset:offset+20]
                    lsa_header = LSAHeader(header_bytes)

                    # Get LSA length from header
                    lsa_length = lsa_header.length if lsa_header.length else 20

                    # Extract full LSA
                    if offset + lsa_length <= len(payload):
                        lsa_bytes = payload[offset:offset+lsa_length]

                        # Parse LSA body based on type
                        body = None
                        body_bytes = lsa_bytes[20:]  # Body starts after 20-byte header

                        try:
                            if lsa_header.ls_type == ROUTER_LSA:
                                logger.debug(f"Parsing Router LSA: lsa_length={lsa_length}, "
                                           f"body_bytes length={len(body_bytes)}, "
                                           f"body_hex={body_bytes[:32].hex() if len(body_bytes) <= 32 else body_bytes[:32].hex() + '...'}")

                                # Manual parsing due to Scapy bug with RouterLSA links
                                body = self._parse_router_lsa_body(body_bytes)

                                num_links = body.num_links if hasattr(body, 'num_links') else 0
                                actual_links = len(body.links) if hasattr(body, 'links') else 0
                                logger.debug(f"Parsed Router LSA from {lsa_header.advertising_router}, "
                                           f"num_links field={num_links}, actual links parsed={actual_links}")
                                if num_links != actual_links:
                                    logger.warning(f"Link count mismatch! Expected {num_links}, parsed {actual_links}")
                                if actual_links > 0:
                                    for i, link in enumerate(body.links):
                                        logger.debug(f"  Link {i}: type={link.link_type}, id={link.link_id}, "
                                                   f"data={link.link_data}, metric={link.metric}")
                            elif lsa_header.ls_type == NETWORK_LSA:
                                body = NetworkLSA(body_bytes)
                                logger.debug(f"Parsed Network LSA from {lsa_header.advertising_router}")
                            # Other LSA types can be added here
                        except Exception as e:
                            logger.debug(f"Could not parse LSA body type {lsa_header.ls_type}: {e}")
                            # Continue with body=None if parsing fails

                        # Create LSA object with header and body
                        lsa = LSA(header=lsa_header, body=body)

                        lsas.append(lsa)
                        offset += lsa_length
                    else:
                        break

                except Exception as e:
                    logger.warning(f"Error parsing LSA at offset {offset}: {e}")
                    break

        except Exception as e:
            logger.error(f"Error extracting LSAs from LSU: {e}")

        return lsas

    def get_lsas_needing_retransmission(self, neighbor: OSPFNeighbor) -> List[LSA]:
        """
        Get LSAs that need to be retransmitted to neighbor (timeout expired)

        Args:
            neighbor: Neighbor to check

        Returns:
            List of LSAs that need retransmission
        """
        lsas_to_retransmit = []

        if neighbor.router_id not in self.retransmit_timestamps:
            return lsas_to_retransmit

        now = time.time()

        for lsa in neighbor.ls_retransmission_list:
            lsa_key = lsa.get_key()
            if lsa_key in self.retransmit_timestamps[neighbor.router_id]:
                time_since_sent = now - self.retransmit_timestamps[neighbor.router_id][lsa_key]

                if time_since_sent >= self.retransmit_interval:
                    lsas_to_retransmit.append(lsa)
                    # Update timestamp for next retransmission
                    self.retransmit_timestamps[neighbor.router_id][lsa_key] = now

        return lsas_to_retransmit

    def flood_lsa_to_neighbors(self, lsa: LSA, neighbors: List[OSPFNeighbor],
                               area_id: str, exclude_neighbor: Optional[OSPFNeighbor] = None) -> List[bytes]:
        """
        Flood LSA to all neighbors except specified one

        Args:
            lsa: LSA to flood
            neighbors: List of all neighbors
            area_id: OSPF area ID
            exclude_neighbor: Neighbor to exclude from flooding (sender)

        Returns:
            List of LSU packets to send (one per neighbor)
        """
        lsu_packets = []

        for neighbor in neighbors:
            # Skip excluded neighbor and neighbors not in Full state
            if neighbor == exclude_neighbor:
                continue

            if neighbor.get_state() != STATE_FULL:
                continue

            # Build LSU packet with this LSA
            lsu_packet = self.build_ls_update([lsa], area_id)

            if lsu_packet:
                lsu_packets.append((neighbor, lsu_packet))

                # Add to retransmission list
                self.add_lsa_to_retransmission_list(lsa, neighbor)

                logger.debug(f"Flooding LSA to {neighbor.router_id}: {lsa}")

        return lsu_packets

    def _parse_router_lsa_body(self, body_bytes: bytes) -> RouterLSA:
        """
        Manually parse Router LSA body to work around Scapy parsing bug

        Args:
            body_bytes: Raw Router LSA body bytes

        Returns:
            RouterLSA object with all links parsed
        """
        import struct
        import socket
        from ospf.packets import RouterLink

        if len(body_bytes) < 4:
            return RouterLSA(body_bytes)

        # Parse header (4 bytes)
        flags_byte = body_bytes[0]
        v_bit = (flags_byte >> 2) & 1
        e_bit = (flags_byte >> 1) & 1
        b_bit = flags_byte & 1
        num_links = struct.unpack("!H", body_bytes[2:4])[0]

        # Parse links manually
        links = []
        offset = 4

        for i in range(num_links):
            if offset + 12 > len(body_bytes):
                logger.warning(f"Not enough bytes for link {i}, offset={offset}, total={len(body_bytes)}")
                break

            # Parse link (12 bytes each)
            link_id_bytes = body_bytes[offset:offset+4]
            link_data_bytes = body_bytes[offset+4:offset+8]
            link_type = body_bytes[offset+8]
            num_tos = body_bytes[offset+9]
            metric = struct.unpack("!H", body_bytes[offset+10:offset+12])[0]

            # Convert IPs to string format
            link_id = socket.inet_ntoa(link_id_bytes)
            link_data = socket.inet_ntoa(link_data_bytes)

            # Create RouterLink object
            link = RouterLink(
                link_id=link_id,
                link_data=link_data,
                link_type=link_type,
                num_tos=num_tos,
                metric=metric
            )
            links.append(link)
            offset += 12

            # Skip TOS entries if present (not commonly used)
            if num_tos > 0:
                offset += num_tos * 4  # Each TOS entry is 4 bytes

        # Create RouterLSA with parsed links
        lsa_body = RouterLSA(
            v_bit=v_bit,
            e_bit=e_bit,
            b_bit=b_bit,
            links=links
        )

        logger.debug(f"Manual parse: num_links={num_links}, parsed {len(links)} links")

        return lsa_body

    def __repr__(self) -> str:
        return f"LSAFloodingManager(router_id={self.router_id})"
