"""
OSPF Socket Handler - Raw socket management for OSPF protocol
Handles multicast, send/receive of OSPF packets
"""

import socket
import struct
import logging
from typing import Optional, Tuple
from ospf.constants import OSPF_PROTOCOL_NUMBER, ALLSPFROUTERS, OSPF_MULTICAST_TTL, OSPF_UNICAST_TTL

logger = logging.getLogger(__name__)


class OSPFSocket:
    """
    Handle raw sockets for OSPF multicast communication
    Uses IP protocol 89 (OSPF)
    """

    def __init__(self, interface: str, source_ip: str):
        """
        Initialize OSPF socket handler

        Args:
            interface: Network interface name (e.g., 'eth0')
            source_ip: Source IP address for this interface
        """
        self.interface = interface
        self.source_ip = source_ip
        self.sock: Optional[socket.socket] = None
        self.multicast_groups = []

    def open(self) -> bool:
        """
        Open raw socket for IP protocol 89 (OSPF)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create raw socket for OSPF protocol
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, OSPF_PROTOCOL_NUMBER)

            # Set socket options
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to INADDR_ANY to receive multicast packets
            # We still set IP_MULTICAST_IF below to send from the correct interface
            self.sock.bind(('', 0))

            # Set TTL for unicast packets (needed for point-to-point unicast neighbors)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, OSPF_UNICAST_TTL)

            # Set TTL for multicast (link-local only)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, OSPF_MULTICAST_TTL)

            # Set multicast interface
            self.sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(self.source_ip)
            )

            # Disable multicast loopback - don't receive our own packets
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)

            # Set DSCP for OSPF traffic - RFC 4594 Network Control (CS6)
            # DSCP CS6 = 48, TOS byte = DSCP << 2 = 192 (0xC0)
            try:
                tos_byte = 192  # CS6 for Network Control (OSPF)
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos_byte)
                logger.info(f"[QoS] Set OSPF socket TOS=0x{tos_byte:02X} (DSCP CS6 - Network Control)")
            except Exception as tos_err:
                logger.warning(f"[QoS] Could not set TOS on OSPF socket: {tos_err}")

            logger.info(f"Opened OSPF socket on {self.interface} ({self.source_ip})")
            return True

        except PermissionError:
            logger.error("Permission denied - OSPF requires root/admin privileges for raw sockets")
            return False
        except Exception as e:
            logger.error(f"Failed to open OSPF socket: {e}")
            return False

    def join_multicast(self, group: str = ALLSPFROUTERS) -> bool:
        """
        Join OSPF multicast group

        Args:
            group: Multicast group address (default: 224.0.0.5 - AllSPFRouters)

        Returns:
            True if successful
        """
        try:
            if not self.sock:
                logger.error("Socket not open")
                return False

            # Create multicast membership request
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(group),
                socket.inet_aton(self.source_ip)
            )

            # Join multicast group
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            self.multicast_groups.append(group)
            logger.info(f"Joined multicast group {group}")
            return True

        except Exception as e:
            logger.error(f"Failed to join multicast group {group}: {e}")
            return False

    def leave_multicast(self, group: str = ALLSPFROUTERS) -> bool:
        """
        Leave OSPF multicast group

        Args:
            group: Multicast group address

        Returns:
            True if successful
        """
        try:
            if not self.sock:
                return False

            if group not in self.multicast_groups:
                return True

            # Create multicast membership request
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(group),
                socket.inet_aton(self.source_ip)
            )

            # Leave multicast group
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)

            self.multicast_groups.remove(group)
            logger.info(f"Left multicast group {group}")
            return True

        except Exception as e:
            logger.error(f"Failed to leave multicast group {group}: {e}")
            return False

    def send(self, packet: bytes, dest: str = ALLSPFROUTERS) -> bool:
        """
        Send OSPF packet

        Args:
            packet: OSPF packet as bytes
            dest: Destination IP (default: multicast AllSPFRouters)

        Returns:
            True if successful
        """
        try:
            if not self.sock:
                logger.error("Socket not open")
                return False

            # Send packet
            bytes_sent = self.sock.sendto(packet, (dest, 0))

            if bytes_sent == len(packet):
                logger.debug(f"Sent {bytes_sent} bytes to {dest}")
                return True
            else:
                logger.warning(f"Partial send: {bytes_sent}/{len(packet)} bytes")
                return False

        except Exception as e:
            logger.error(f"Failed to send packet to {dest}: {e}")
            return False

    def receive(self, timeout: float = 1.0) -> Optional[Tuple[bytes, str]]:
        """
        Receive OSPF packet with timeout

        Args:
            timeout: Receive timeout in seconds

        Returns:
            Tuple of (packet_bytes, source_ip) or None if timeout/error
        """
        result = self.receive_with_dscp(timeout)
        if result:
            return (result[0], result[1])
        return None

    def receive_with_dscp(self, timeout: float = 1.0) -> Optional[Tuple[bytes, str, int]]:
        """
        Receive OSPF packet with timeout and extract DSCP value from IP header.

        Args:
            timeout: Receive timeout in seconds

        Returns:
            Tuple of (packet_bytes, source_ip, dscp_value) or None if timeout/error
        """
        try:
            if not self.sock:
                logger.error("Socket not open")
                return None

            # Set timeout
            self.sock.settimeout(timeout)

            # Receive packet
            data, addr = self.sock.recvfrom(65535)
            source_ip = addr[0]

            # Strip IP header (SOCK_RAW includes IP header in received data)
            # IP header length is in first byte: IHL field (lower 4 bits) * 4 bytes
            dscp_value = 0
            if len(data) > 1:
                ip_header_len = (data[0] & 0x0F) * 4
                # Extract DSCP from TOS byte (byte 1 of IP header)
                # TOS byte format: DSCP (6 bits) + ECN (2 bits)
                # DSCP = TOS >> 2
                tos_byte = data[1]
                dscp_value = tos_byte >> 2
                ospf_data = data[ip_header_len:]
                logger.debug(f"Received {len(data)} bytes from {source_ip}, "
                           f"TOS={tos_byte:#04x} DSCP={dscp_value}, "
                           f"stripped {ip_header_len} byte IP header, "
                           f"OSPF data: {len(ospf_data)} bytes")
                return (ospf_data, source_ip, dscp_value)

            return (data, source_ip, dscp_value)

        except socket.timeout:
            # Timeout is normal, not an error
            return None
        except Exception as e:
            logger.error(f"Failed to receive packet: {e}")
            return None

    def close(self):
        """
        Close socket and leave all multicast groups
        """
        try:
            # Leave all multicast groups
            for group in list(self.multicast_groups):
                self.leave_multicast(group)

            # Close socket
            if self.sock:
                self.sock.close()
                self.sock = None
                logger.info("Closed OSPF socket")

        except Exception as e:
            logger.error(f"Error closing socket: {e}")

    def is_open(self) -> bool:
        """
        Check if socket is open

        Returns:
            True if socket is open
        """
        return self.sock is not None

    def __enter__(self):
        """Context manager entry"""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class OSPFSocketError(Exception):
    """OSPF socket-related errors"""
    pass
