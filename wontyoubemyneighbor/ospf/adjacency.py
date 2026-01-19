"""
OSPF Adjacency Manager - Database Description Exchange
RFC 2328 Section 10.6 - Receiving Database Description Packets
RFC 2328 Section 10.8 - Sending Database Description Packets
"""

import time
import logging
from typing import List, Optional, Tuple
from ospf.packets import (
    OSPFHeader, OSPFDBDescription, LSAHeader, parse_ospf_packet
)
from ospf.neighbor import OSPFNeighbor
from ospf.lsdb import LinkStateDatabase
from ospf.constants import (
    DATABASE_DESCRIPTION, STATE_EXSTART, STATE_EXCHANGE, STATE_LOADING, STATE_FULL,
    EVENT_NEGOTIATION_DONE, EVENT_EXCHANGE_DONE
)

logger = logging.getLogger(__name__)


class AdjacencyManager:
    """
    Manage OSPF adjacency formation through Database Description exchange
    """

    def __init__(self, router_id: str, lsdb: LinkStateDatabase):
        """
        Initialize adjacency manager

        Args:
            router_id: This router's ID
            lsdb: Link State Database
        """
        self.router_id = router_id
        self.lsdb = lsdb
        self.interface_mtu = 1500

        logger.info(f"Initialized AdjacencyManager for {router_id}")

    def build_initial_dbd_packet(self, neighbor: OSPFNeighbor, area_id: str) -> bytes:
        """
        Build initial Database Description packet (ExStart state)

        Per RFC 2328 Section 10.6: In ExStart, both routers claim to be master
        by sending empty DBDs with I=1, M=1, MS=1 and their own sequence numbers.
        Master/slave is determined when the lower Router ID receives a DBD from
        the higher Router ID and switches to slave mode.

        Args:
            neighbor: Target neighbor
            area_id: OSPF area ID

        Returns:
            DBD packet as bytes
        """
        import struct
        import socket as sock
        import time

        # In ExStart, ALWAYS claim to be master with our own sequence number
        # The actual master/slave determination happens in process_dbd when we
        # compare router IDs and one side backs down
        if not neighbor.dd_sequence_number:
            neighbor.dd_sequence_number = int(time.time()) & 0xFFFFFFFF

        dd_sequence = neighbor.dd_sequence_number

        # Build DBD packet - in ExStart, ALWAYS use I=1, M=1, MS=1
        header = OSPFHeader(
            version=2,
            type=DATABASE_DESCRIPTION,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        dbd = OSPFDBDescription(
            interface_mtu=self.interface_mtu,
            options=0x02,  # E-bit
            flags=0x07,    # I=1, M=1, MS=1 - claim master in ExStart
            dd_sequence=dd_sequence
        )

        packet = header / dbd

        logger.debug(f"Built initial DBD for {neighbor.router_id}, "
                    f"flags=0x07 (I=1,M=1,MS=1), seq={dd_sequence}")

        return bytes(packet)

    def build_slave_ack_dbd_packet(self, neighbor: OSPFNeighbor, area_id: str) -> bytes:
        """
        Build slave acknowledgment DBD packet

        Per RFC 2328: When slave receives master's initial DBD in ExStart,
        slave responds with DBD having I=0, M=1, MS=0 and master's sequence number.
        This packet is empty (no LSA headers).

        Args:
            neighbor: Target neighbor
            area_id: OSPF area ID

        Returns:
            DBD packet as bytes
        """
        header = OSPFHeader(
            version=2,
            type=DATABASE_DESCRIPTION,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        # Slave ack: I=0, M=1, MS=0 = 0x02
        dbd = OSPFDBDescription(
            interface_mtu=self.interface_mtu,
            options=0x02,  # E-bit
            flags=0x02,    # I=0, M=1 (we have more), MS=0 (slave)
            dd_sequence=neighbor.dd_sequence_number
        )

        packet = header / dbd

        logger.info(f"Built slave ack DBD for {neighbor.router_id}, "
                   f"flags=0x02 (I=0,M=1,MS=0), seq={neighbor.dd_sequence_number}")

        return bytes(packet)

    def build_dbd_packet(self, neighbor: OSPFNeighbor, area_id: str,
                        lsa_headers: Optional[List[LSAHeader]] = None,
                        is_more: bool = False) -> bytes:
        """
        Build Database Description packet (Exchange state)

        Args:
            neighbor: Target neighbor
            area_id: OSPF area ID
            lsa_headers: List of LSA headers to include
            is_more: True if more DBD packets follow

        Returns:
            DBD packet as bytes
        """
        if lsa_headers is None:
            lsa_headers = []

        # Determine flags
        is_master = neighbor.is_master
        flags = 0x00

        if is_more:
            flags |= 0x02  # M-bit (More)

        if is_master:
            flags |= 0x01  # MS-bit (Master)

        # Build packet
        header = OSPFHeader(
            version=2,
            type=DATABASE_DESCRIPTION,
            router_id=self.router_id,
            area_id=area_id,
            auth_type=0
        )

        logger.info(f"Building DBD with neighbor.dd_sequence_number = {neighbor.dd_sequence_number}")

        dbd = OSPFDBDescription(
            interface_mtu=self.interface_mtu,
            options=0x02,
            flags=flags,
            dd_sequence=neighbor.dd_sequence_number
        )

        # Build LSA headers payload (20 bytes each)
        lsa_payload = b''
        for lsa_header in lsa_headers:
            # Serialize LSA header (20 bytes)
            lsa_payload += bytes(lsa_header)

        # Combine header, DBD, and LSA headers
        packet = header / dbd
        if lsa_payload:
            packet = packet / lsa_payload

        logger.debug(f"Built DBD for {neighbor.router_id}, "
                    f"seq={neighbor.dd_sequence_number}, "
                    f"more={is_more}, "
                    f"lsa_count={len(lsa_headers)}, "
                    f"lsa_payload_size={len(lsa_payload)}")

        return bytes(packet)

    def process_dbd(self, packet_data: bytes, neighbor: OSPFNeighbor) -> Tuple[bool, List, bool]:
        """
        Process received Database Description packet

        Args:
            packet_data: Raw packet bytes
            neighbor: Neighbor who sent the packet

        Returns:
            Tuple of (success, list of LSAs we need to request, exchange_complete)
            exchange_complete=True when neighbor has sent all DBD packets
        """
        try:
            # Parse packet
            packet = parse_ospf_packet(packet_data)
            if not packet or packet.type != DATABASE_DESCRIPTION:
                logger.warning(f"Invalid DBD packet from {neighbor.router_id}")
                return (False, [])

            dbd = packet[OSPFDBDescription]
            current_state = neighbor.get_state()

            logger.debug(f"Processing DBD from {neighbor.router_id}, "
                        f"state={neighbor.get_state_name()}, "
                        f"seq={dbd.dd_sequence}, "
                        f"flags={dbd.flags:#04x}")

            # Handle ExStart state
            if current_state == STATE_EXSTART:
                success, lsa_headers = self._process_dbd_exstart(dbd, neighbor)
                return (success, lsa_headers, False)  # Not complete yet in ExStart

            # Handle Exchange state
            elif current_state == STATE_EXCHANGE:
                return self._process_dbd_exchange(dbd, packet_data, neighbor)

            # Handle DBD in Loading/Full state (duplicate/retransmission from master)
            elif current_state == STATE_LOADING or current_state == STATE_FULL:
                # RFC 2328 Section 10.8: Slave should respond to duplicate DBDs
                # Master may retransmit if it didn't receive our last response
                if not neighbor.is_master:  # We are slave
                    logger.info(f"Received duplicate DBD from {neighbor.router_id} in {neighbor.get_state_name()}, "
                               f"responding to retransmission")
                    return (True, [], False)  # Signal to send response
                else:
                    logger.debug(f"Ignoring DBD from {neighbor.router_id} in {neighbor.get_state_name()}")
                    return (False, [], False)

            else:
                logger.warning(f"Received DBD in unexpected state: {neighbor.get_state_name()}")
                return (False, [], False)

        except Exception as e:
            logger.error(f"Error processing DBD from {neighbor.router_id}: {e}")
            return (False, [], False)

    def _process_dbd_exstart(self, dbd: OSPFDBDescription,
                             neighbor: OSPFNeighbor) -> Tuple[bool, List]:
        """
        Process DBD in ExStart state (master/slave negotiation)

        Args:
            dbd: DBD packet
            neighbor: Neighbor

        Returns:
            Tuple of (success, empty list)
        """
        # Check flags
        is_init = bool(dbd.flags & 0x04)
        is_more = bool(dbd.flags & 0x02)
        is_master_bit = bool(dbd.flags & 0x01)

        # Determine master/slave based on router IDs (numerical comparison)
        import struct
        import socket as sock
        our_id_int = struct.unpack("!I", sock.inet_aton(self.router_id))[0]
        neighbor_id_int = struct.unpack("!I", sock.inet_aton(neighbor.router_id))[0]

        # RFC 2328: In ExStart, if slave receives DBD from master, it responds with I=0, MS=0
        # So we need to accept DBDs without I-bit if we're master and they're acknowledging as slave
        if our_id_int > neighbor_id_int:
            # We are master
            neighbor.is_master = True

            if is_init and is_master_bit:
                # Neighbor's initial DBD - both claiming master, we win
                logger.info(f"We are MASTER over {neighbor.router_id} (both claimed master, we won)")
                logger.info(f"Keeping our sequence {neighbor.dd_sequence_number}, rejecting theirs {dbd.dd_sequence}")
            elif not is_init and not is_master_bit:
                # Slave's acknowledgment (I=0, MS=0) - ACCEPT and verify sequence
                if dbd.dd_sequence == neighbor.dd_sequence_number:
                    logger.info(f"Slave {neighbor.router_id} acknowledged, seq={dbd.dd_sequence}")
                else:
                    logger.warning(f"Slave seq mismatch: expected {neighbor.dd_sequence_number}, got {dbd.dd_sequence}")
                    return (False, [])
            else:
                # Other cases
                logger.info(f"We are MASTER, {neighbor.router_id} is SLAVE (I={is_init}, MS={is_master_bit})")

            logger.debug(f"Our sequence number: {neighbor.dd_sequence_number}")
        else:
            # We are slave (neighbor has higher Router ID)
            neighbor.is_master = False

            if is_init and is_master_bit:
                # Master's initial DBD - adopt their sequence
                logger.info(f"We are SLAVE, {neighbor.router_id} is MASTER, adopting seq={dbd.dd_sequence}")
                neighbor.dd_sequence_number = dbd.dd_sequence
            elif not is_master_bit:
                # Both think they're slave - neighbor wins because higher ID
                logger.info(f"{neighbor.router_id} is MASTER over us (both claimed slave)")
                neighbor.dd_sequence_number = dbd.dd_sequence
            else:
                logger.info(f"We are SLAVE to {neighbor.router_id}, seq={dbd.dd_sequence}")
                neighbor.dd_sequence_number = dbd.dd_sequence

        # Transition to Exchange state
        neighbor.handle_dbd_received(is_initial=True)

        return (True, [])

    def _process_dbd_exchange(self, dbd: OSPFDBDescription, packet_data: bytes,
                              neighbor: OSPFNeighbor) -> Tuple[bool, List]:
        """
        Process DBD in Exchange state

        Args:
            dbd: DBD packet
            packet_data: Raw packet for LSA header extraction
            neighbor: Neighbor

        Returns:
            Tuple of (success, list of LSA headers we need)
        """
        is_more = bool(dbd.flags & 0x02)
        is_master_bit = bool(dbd.flags & 0x01)

        # Validate sequence number
        if neighbor.is_master:
            # We are master, expect our sequence number
            if dbd.dd_sequence != neighbor.dd_sequence_number:
                logger.warning(f"DBD sequence mismatch from {neighbor.router_id}: "
                             f"expected {neighbor.dd_sequence_number}, got {dbd.dd_sequence}")
                return (False, [])
        else:
            # We are slave, accept neighbor's sequence number
            neighbor.dd_sequence_number = dbd.dd_sequence

        # Extract LSA headers from DBD packet payload
        lsa_headers = self._extract_lsa_headers_from_dbd(packet_data)

        logger.debug(f"Received {len(lsa_headers)} LSA headers from {neighbor.router_id}")

        # Compare with our LSDB and determine which LSAs we need
        lsa_headers_needed = []
        for lsa_header in lsa_headers:
            if self._need_lsa(lsa_header):
                lsa_headers_needed.append(lsa_header)
                logger.debug(f"Need LSA: Type {lsa_header.ls_type}, "
                           f"ID {lsa_header.link_state_id}, "
                           f"AdvRouter {lsa_header.advertising_router}")

        # Check if exchange is complete
        exchange_complete = not is_more
        if exchange_complete:
            # Neighbor has no more LSAs to send
            logger.info(f"DBD exchange complete with {neighbor.router_id}, "
                       f"need {len(lsa_headers_needed)} LSAs")
            # BUGFIX: Don't call exchange_done() here! Return exchange_complete flag so caller
            # can add lsa_headers_needed to ls_request_list first, then call exchange_done().

        # Do NOT increment here - we increment before sending next DBD
        # (see _send_dbd in wontyoubemyneighbor.py)

        return (True, lsa_headers_needed, exchange_complete)

    def start_adjacency(self, neighbor: OSPFNeighbor):
        """
        Start adjacency formation with neighbor

        Args:
            neighbor: Neighbor to form adjacency with
        """
        # Set master/slave based on router ID
        if self.router_id > neighbor.router_id:
            neighbor.is_master = True
            neighbor.dd_sequence_number = int(time.time()) & 0xFFFFFFFF
            logger.info(f"Starting adjacency with {neighbor.router_id} (we are MASTER)")
        else:
            neighbor.is_master = False
            logger.info(f"Starting adjacency with {neighbor.router_id} (we are SLAVE)")

    def get_lsa_headers_to_send(self, neighbor: OSPFNeighbor,
                               max_count: int = 10) -> Tuple[List[LSAHeader], bool]:
        """
        Get LSA headers to send in DBD packet

        Args:
            neighbor: Target neighbor
            max_count: Maximum number of headers to return

        Returns:
            Tuple of (list of LSA headers, has_more)
        """
        # Get all LSA headers from LSDB
        all_headers = self.lsdb.get_lsa_headers()

        # Check if neighbor already has db_summary_list
        if not hasattr(neighbor, 'db_summary_list') or not neighbor.db_summary_list:
            # Initialize with all our LSA headers
            neighbor.db_summary_list = all_headers.copy()

        # Get next batch
        headers_to_send = neighbor.db_summary_list[:max_count]
        neighbor.db_summary_list = neighbor.db_summary_list[max_count:]

        has_more = len(neighbor.db_summary_list) > 0

        logger.debug(f"Sending {len(headers_to_send)} LSA headers to {neighbor.router_id}, "
                    f"remaining: {len(neighbor.db_summary_list)}")

        return (headers_to_send, has_more)

    def _extract_lsa_headers_from_dbd(self, packet_data: bytes) -> List[LSAHeader]:
        """
        Extract LSA headers from DBD packet payload

        Args:
            packet_data: Raw packet bytes

        Returns:
            List of LSAHeader objects
        """
        lsa_headers = []

        try:
            # Parse the full packet
            packet = parse_ospf_packet(packet_data)
            if not packet:
                return lsa_headers

            # Get DBD layer
            if not packet.haslayer(OSPFDBDescription):
                return lsa_headers

            dbd = packet[OSPFDBDescription]

            # LSA headers are in the payload after the DBD packet
            # Each LSA header is 20 bytes
            payload = bytes(dbd.payload) if dbd.payload else b''

            offset = 0
            while offset + 20 <= len(payload):
                try:
                    # Extract 20-byte LSA header
                    header_bytes = payload[offset:offset+20]
                    lsa_header = LSAHeader(header_bytes)
                    lsa_headers.append(lsa_header)
                    offset += 20
                except Exception as e:
                    logger.warning(f"Error parsing LSA header at offset {offset}: {e}")
                    break

        except Exception as e:
            logger.error(f"Error extracting LSA headers from DBD: {e}")

        return lsa_headers

    def _need_lsa(self, lsa_header: LSAHeader) -> bool:
        """
        Determine if we need to request this LSA (it's newer or we don't have it)

        Args:
            lsa_header: LSA header from neighbor

        Returns:
            True if we need this LSA
        """
        # Check if we have this LSA in our LSDB
        our_lsa = self.lsdb.get_lsa(
            lsa_header.ls_type,
            lsa_header.link_state_id,
            lsa_header.advertising_router
        )

        if our_lsa is None:
            # We don't have this LSA
            return True

        # Compare sequence numbers (RFC 2328 Section 13.1)
        neighbor_seq = lsa_header.ls_sequence_number
        our_seq = our_lsa.header.ls_sequence_number

        # Higher sequence number = newer (accounting for wraparound)
        if neighbor_seq > our_seq:
            return True
        elif neighbor_seq == our_seq:
            # Same sequence, compare checksum
            if lsa_header.ls_checksum > our_lsa.header.ls_checksum:
                return True

        return False

    def __repr__(self) -> str:
        return f"AdjacencyManager(router_id={self.router_id})"
