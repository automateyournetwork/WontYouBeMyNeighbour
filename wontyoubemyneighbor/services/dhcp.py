"""
DHCP Server Implementation

Provides DHCP server functionality for automatic IP address assignment
in network segments. Implements RFC 2131.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network, IPv4Address, IPv4Network
from enum import Enum


# DHCP Constants
DHCP_SERVER_PORT = 67
DHCP_CLIENT_PORT = 68
DHCP_MAGIC_COOKIE = 0x63825363

# DHCP Message Types
DHCP_DISCOVER = 1
DHCP_OFFER = 2
DHCP_REQUEST = 3
DHCP_DECLINE = 4
DHCP_ACK = 5
DHCP_NAK = 6
DHCP_RELEASE = 7
DHCP_INFORM = 8

# DHCP Options
OPT_SUBNET_MASK = 1
OPT_ROUTER = 3
OPT_DNS_SERVER = 6
OPT_HOSTNAME = 12
OPT_DOMAIN_NAME = 15
OPT_BROADCAST = 28
OPT_NTP_SERVER = 42
OPT_LEASE_TIME = 51
OPT_MESSAGE_TYPE = 53
OPT_SERVER_ID = 54
OPT_PARAM_REQUEST = 55
OPT_RENEWAL_TIME = 58
OPT_REBIND_TIME = 59
OPT_CLIENT_ID = 61
OPT_END = 255


class LeaseState(Enum):
    """DHCP Lease States"""
    OFFERED = "offered"      # Offered but not yet confirmed
    ACTIVE = "active"        # Confirmed and in use
    EXPIRED = "expired"      # Lease expired
    RELEASED = "released"    # Client released


@dataclass
class DHCPLease:
    """
    DHCP Lease record.

    Tracks IP address assignment to a client.
    """
    ip_address: str                   # Assigned IP
    mac_address: str                  # Client MAC
    hostname: Optional[str] = None    # Client hostname
    state: LeaseState = LeaseState.OFFERED

    lease_time: int = 86400           # Lease duration (seconds)
    start_time: Optional[datetime] = None
    expire_time: Optional[datetime] = None

    # Client info
    client_id: Optional[bytes] = None
    transaction_id: int = 0

    def __post_init__(self):
        """Initialize times"""
        if self.start_time is None:
            self.start_time = datetime.now()
        if self.expire_time is None:
            self.expire_time = self.start_time + timedelta(seconds=self.lease_time)

    def is_expired(self) -> bool:
        """Check if lease is expired"""
        return datetime.now() > self.expire_time

    def remaining_time(self) -> int:
        """Get remaining lease time in seconds"""
        if self.is_expired():
            return 0
        return int((self.expire_time - datetime.now()).total_seconds())

    def renew(self, lease_time: Optional[int] = None) -> None:
        """Renew the lease"""
        self.start_time = datetime.now()
        if lease_time:
            self.lease_time = lease_time
        self.expire_time = self.start_time + timedelta(seconds=self.lease_time)
        self.state = LeaseState.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "state": self.state.value,
            "lease_time": self.lease_time,
            "remaining_time": self.remaining_time(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "expire_time": self.expire_time.isoformat() if self.expire_time else None,
        }


@dataclass
class DHCPPool:
    """
    DHCP Address Pool.

    Defines a range of IP addresses available for assignment.
    """
    network: str                      # Network CIDR (e.g., "10.0.0.0/24")
    start_ip: str                     # First address in range
    end_ip: str                       # Last address in range

    # Pool options
    gateway: Optional[str] = None     # Default gateway
    dns_servers: List[str] = field(default_factory=list)
    domain_name: Optional[str] = None
    lease_time: int = 86400           # Default lease time

    # Reserved IPs (not assigned by DHCP)
    reserved: Set[str] = field(default_factory=set)

    # Static mappings: {mac: ip}
    static_mappings: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize pool"""
        self._network = ip_network(self.network, strict=False)
        self._start = ip_address(self.start_ip)
        self._end = ip_address(self.end_ip)

        # Auto-set gateway if not specified
        if self.gateway is None:
            self.gateway = str(list(self._network.hosts())[0])

    @property
    def subnet_mask(self) -> str:
        """Get subnet mask"""
        return str(self._network.netmask)

    @property
    def broadcast_address(self) -> str:
        """Get broadcast address"""
        return str(self._network.broadcast_address)

    def is_in_range(self, ip: str) -> bool:
        """Check if IP is in pool range"""
        addr = ip_address(ip)
        return self._start <= addr <= self._end

    def get_static_ip(self, mac: str) -> Optional[str]:
        """Get static IP for MAC if configured"""
        return self.static_mappings.get(mac.upper())

    def add_static_mapping(self, mac: str, ip: str) -> None:
        """Add static MAC to IP mapping"""
        if not self.is_in_range(ip):
            raise ValueError(f"IP {ip} not in pool range")
        self.static_mappings[mac.upper()] = ip

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "network": self.network,
            "range": f"{self.start_ip} - {self.end_ip}",
            "gateway": self.gateway,
            "dns_servers": self.dns_servers,
            "domain_name": self.domain_name,
            "lease_time": self.lease_time,
            "reserved_count": len(self.reserved),
            "static_mappings": len(self.static_mappings),
        }


class DHCPServer:
    """
    DHCP Server.

    Provides DHCP services for automatic IP address configuration.
    """

    def __init__(
        self,
        server_ip: str,
        interface: Optional[str] = None,
    ):
        """
        Initialize DHCP server.

        Args:
            server_ip: Server's IP address
            interface: Interface to bind to
        """
        self.server_ip = server_ip
        self.interface = interface

        # Address pools: {network: DHCPPool}
        self._pools: Dict[str, DHCPPool] = {}

        # Active leases: {ip: DHCPLease}
        self._leases: Dict[str, DHCPLease] = {}

        # MAC to IP mapping for quick lookup
        self._mac_to_ip: Dict[str, str] = {}

        # Pending offers: {(mac, transaction_id): DHCPLease}
        self._pending_offers: Dict[Tuple[str, int], DHCPLease] = {}

        # UDP socket
        self._socket: Optional[socket.socket] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # Running state
        self.running = False

        self.logger = logging.getLogger(f"DHCPServer[{server_ip}]")

    def add_pool(self, pool: DHCPPool) -> None:
        """Add address pool"""
        self._pools[pool.network] = pool
        self.logger.info(f"Added pool: {pool.network} ({pool.start_ip}-{pool.end_ip})")

    def remove_pool(self, network: str) -> bool:
        """Remove address pool"""
        pool = self._pools.pop(network, None)
        return pool is not None

    def get_pool(self, network: str) -> Optional[DHCPPool]:
        """Get pool by network"""
        return self._pools.get(network)

    def _find_pool_for_request(self, gateway_ip: Optional[str] = None) -> Optional[DHCPPool]:
        """Find appropriate pool for request"""
        # If gateway specified (relay), find matching pool
        if gateway_ip:
            gw = ip_address(gateway_ip)
            for pool in self._pools.values():
                net = ip_network(pool.network, strict=False)
                if gw in net:
                    return pool

        # Return first pool (simplified)
        if self._pools:
            return list(self._pools.values())[0]

        return None

    async def start(self) -> None:
        """Start DHCP server"""
        self.logger.info(f"Starting DHCP server at {self.server_ip}")
        self.running = True

        try:
            # Create UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._socket.bind(('0.0.0.0', DHCP_SERVER_PORT))
            self._socket.setblocking(False)

            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            self.logger.info("DHCP server started")

        except Exception as e:
            self.logger.error(f"Failed to start DHCP server: {e}")
            self.running = False
            raise

    async def stop(self) -> None:
        """Stop DHCP server"""
        self.logger.info("Stopping DHCP server")
        self.running = False

        if self._receive_task:
            self._receive_task.cancel()

        if self._cleanup_task:
            self._cleanup_task.cancel()

        if self._socket:
            self._socket.close()

        self.logger.info("DHCP server stopped")

    async def _receive_loop(self) -> None:
        """Receive and process DHCP packets"""
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                data, addr = await loop.run_in_executor(
                    None,
                    lambda: self._socket.recvfrom(4096)
                )

                # Process DHCP packet
                await self._process_packet(data, addr)

            except asyncio.CancelledError:
                break
            except BlockingIOError:
                await asyncio.sleep(0.01)
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in receive loop: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired leases"""
        while self.running:
            try:
                await asyncio.sleep(60)
                self._cleanup_expired_leases()
            except asyncio.CancelledError:
                break

    def _cleanup_expired_leases(self) -> None:
        """Remove expired leases"""
        expired = []
        for ip, lease in self._leases.items():
            if lease.is_expired():
                expired.append(ip)

        for ip in expired:
            lease = self._leases.pop(ip)
            self._mac_to_ip.pop(lease.mac_address, None)
            self.logger.debug(f"Expired lease: {ip} ({lease.mac_address})")

    async def _process_packet(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Process received DHCP packet"""
        if len(data) < 240:
            return

        # Parse DHCP packet
        try:
            packet = self._parse_dhcp_packet(data)
        except Exception as e:
            self.logger.error(f"Failed to parse DHCP packet: {e}")
            return

        msg_type = packet.get('message_type')
        mac = packet.get('client_mac')
        xid = packet.get('xid')

        self.logger.debug(f"Received DHCP {msg_type} from {mac}")

        if msg_type == DHCP_DISCOVER:
            await self._handle_discover(packet)
        elif msg_type == DHCP_REQUEST:
            await self._handle_request(packet)
        elif msg_type == DHCP_RELEASE:
            await self._handle_release(packet)
        elif msg_type == DHCP_DECLINE:
            await self._handle_decline(packet)

    def _parse_dhcp_packet(self, data: bytes) -> Dict[str, Any]:
        """Parse DHCP packet"""
        packet = {}

        # Fixed fields
        packet['op'] = data[0]
        packet['htype'] = data[1]
        packet['hlen'] = data[2]
        packet['hops'] = data[3]
        packet['xid'] = struct.unpack('!I', data[4:8])[0]
        packet['secs'] = struct.unpack('!H', data[8:10])[0]
        packet['flags'] = struct.unpack('!H', data[10:12])[0]
        packet['ciaddr'] = socket.inet_ntoa(data[12:16])
        packet['yiaddr'] = socket.inet_ntoa(data[16:20])
        packet['siaddr'] = socket.inet_ntoa(data[20:24])
        packet['giaddr'] = socket.inet_ntoa(data[24:28])

        # Client MAC
        mac_bytes = data[28:28 + packet['hlen']]
        packet['client_mac'] = ':'.join(f'{b:02X}' for b in mac_bytes)

        # Parse options (starting at byte 240 after magic cookie)
        packet['options'] = {}
        offset = 240

        while offset < len(data):
            opt_type = data[offset]
            if opt_type == OPT_END:
                break
            if opt_type == 0:  # Padding
                offset += 1
                continue

            opt_len = data[offset + 1]
            opt_data = data[offset + 2:offset + 2 + opt_len]
            packet['options'][opt_type] = opt_data
            offset += 2 + opt_len

        # Extract message type
        if OPT_MESSAGE_TYPE in packet['options']:
            packet['message_type'] = packet['options'][OPT_MESSAGE_TYPE][0]

        return packet

    async def _handle_discover(self, packet: Dict[str, Any]) -> None:
        """Handle DHCP DISCOVER"""
        mac = packet['client_mac']
        xid = packet['xid']
        giaddr = packet.get('giaddr', '0.0.0.0')

        pool = self._find_pool_for_request(giaddr if giaddr != '0.0.0.0' else None)
        if not pool:
            self.logger.warning(f"No pool available for {mac}")
            return

        # Check for static mapping
        offer_ip = pool.get_static_ip(mac)

        # Check for existing lease
        if not offer_ip and mac in self._mac_to_ip:
            existing_ip = self._mac_to_ip[mac]
            if existing_ip in self._leases:
                offer_ip = existing_ip

        # Allocate new IP
        if not offer_ip:
            offer_ip = self._allocate_ip(pool)

        if not offer_ip:
            self.logger.warning(f"No IP available for {mac}")
            return

        # Create lease offer
        lease = DHCPLease(
            ip_address=offer_ip,
            mac_address=mac,
            state=LeaseState.OFFERED,
            lease_time=pool.lease_time,
            transaction_id=xid,
        )

        self._pending_offers[(mac, xid)] = lease

        # Send OFFER
        await self._send_offer(packet, lease, pool)

    async def _handle_request(self, packet: Dict[str, Any]) -> None:
        """Handle DHCP REQUEST"""
        mac = packet['client_mac']
        xid = packet['xid']
        requested_ip = None

        # Get requested IP from options or ciaddr
        if 50 in packet['options']:  # Requested IP option
            requested_ip = socket.inet_ntoa(packet['options'][50])
        elif packet['ciaddr'] != '0.0.0.0':
            requested_ip = packet['ciaddr']

        # Check pending offer
        offer_key = (mac, xid)
        lease = self._pending_offers.pop(offer_key, None)

        if lease and lease.ip_address == requested_ip:
            # Confirm the offer
            lease.state = LeaseState.ACTIVE
            lease.renew()
            self._leases[lease.ip_address] = lease
            self._mac_to_ip[mac] = lease.ip_address

            pool = self._find_pool_for_request()
            await self._send_ack(packet, lease, pool)

            self.logger.info(f"Assigned {lease.ip_address} to {mac}")

        elif mac in self._mac_to_ip and requested_ip == self._mac_to_ip[mac]:
            # Renewal of existing lease
            lease = self._leases.get(requested_ip)
            if lease:
                lease.renew()
                pool = self._find_pool_for_request()
                await self._send_ack(packet, lease, pool)
                self.logger.info(f"Renewed {requested_ip} for {mac}")
        else:
            # NAK
            await self._send_nak(packet)
            self.logger.warning(f"NAK for {mac} requesting {requested_ip}")

    async def _handle_release(self, packet: Dict[str, Any]) -> None:
        """Handle DHCP RELEASE"""
        mac = packet['client_mac']
        released_ip = packet['ciaddr']

        if released_ip in self._leases:
            lease = self._leases.pop(released_ip)
            self._mac_to_ip.pop(mac, None)
            lease.state = LeaseState.RELEASED
            self.logger.info(f"Released {released_ip} from {mac}")

    async def _handle_decline(self, packet: Dict[str, Any]) -> None:
        """Handle DHCP DECLINE"""
        mac = packet['client_mac']
        declined_ip = None

        if 50 in packet['options']:
            declined_ip = socket.inet_ntoa(packet['options'][50])

        if declined_ip:
            # Mark IP as reserved (potential conflict)
            for pool in self._pools.values():
                if pool.is_in_range(declined_ip):
                    pool.reserved.add(declined_ip)
                    break

            self.logger.warning(f"IP {declined_ip} declined by {mac} - marked as reserved")

    def _allocate_ip(self, pool: DHCPPool) -> Optional[str]:
        """Allocate IP from pool"""
        start = ip_address(pool.start_ip)
        end = ip_address(pool.end_ip)

        current = start
        while current <= end:
            ip_str = str(current)

            # Skip if reserved
            if ip_str in pool.reserved:
                current += 1
                continue

            # Skip if already leased
            if ip_str in self._leases:
                current += 1
                continue

            return ip_str

        return None

    async def _send_offer(self, request: Dict, lease: DHCPLease, pool: DHCPPool) -> None:
        """Send DHCP OFFER"""
        response = self._build_response(
            request, lease, pool, DHCP_OFFER
        )
        await self._send_response(request, response)
        self.logger.debug(f"Sent OFFER {lease.ip_address} to {lease.mac_address}")

    async def _send_ack(self, request: Dict, lease: DHCPLease, pool: DHCPPool) -> None:
        """Send DHCP ACK"""
        response = self._build_response(
            request, lease, pool, DHCP_ACK
        )
        await self._send_response(request, response)
        self.logger.debug(f"Sent ACK {lease.ip_address} to {lease.mac_address}")

    async def _send_nak(self, request: Dict) -> None:
        """Send DHCP NAK"""
        # Simplified NAK
        self.logger.debug(f"Sent NAK to {request['client_mac']}")

    def _build_response(
        self,
        request: Dict,
        lease: DHCPLease,
        pool: DHCPPool,
        msg_type: int
    ) -> bytes:
        """Build DHCP response packet"""
        response = bytearray(240)

        # Fixed fields
        response[0] = 2  # BOOTREPLY
        response[1] = request['htype']
        response[2] = request['hlen']
        response[3] = 0  # hops

        # Transaction ID
        response[4:8] = struct.pack('!I', request['xid'])

        # Your IP address
        response[16:20] = socket.inet_aton(lease.ip_address)

        # Server IP
        response[20:24] = socket.inet_aton(self.server_ip)

        # Client MAC
        mac_bytes = bytes.fromhex(request['client_mac'].replace(':', ''))
        response[28:28 + len(mac_bytes)] = mac_bytes

        # Magic cookie
        response.extend(struct.pack('!I', DHCP_MAGIC_COOKIE))

        # Options
        # Message type
        response.extend(bytes([OPT_MESSAGE_TYPE, 1, msg_type]))

        # Server ID
        response.extend(bytes([OPT_SERVER_ID, 4]))
        response.extend(socket.inet_aton(self.server_ip))

        # Lease time
        response.extend(bytes([OPT_LEASE_TIME, 4]))
        response.extend(struct.pack('!I', lease.lease_time))

        # Subnet mask
        response.extend(bytes([OPT_SUBNET_MASK, 4]))
        response.extend(socket.inet_aton(pool.subnet_mask))

        # Router
        if pool.gateway:
            response.extend(bytes([OPT_ROUTER, 4]))
            response.extend(socket.inet_aton(pool.gateway))

        # DNS servers
        if pool.dns_servers:
            dns_data = b''.join(socket.inet_aton(dns) for dns in pool.dns_servers)
            response.extend(bytes([OPT_DNS_SERVER, len(dns_data)]))
            response.extend(dns_data)

        # Domain name
        if pool.domain_name:
            domain_bytes = pool.domain_name.encode('ascii')
            response.extend(bytes([OPT_DOMAIN_NAME, len(domain_bytes)]))
            response.extend(domain_bytes)

        # End
        response.extend(bytes([OPT_END]))

        return bytes(response)

    async def _send_response(self, request: Dict, response: bytes) -> None:
        """Send DHCP response"""
        if not self._socket:
            return

        # Determine destination
        if request['flags'] & 0x8000:  # Broadcast flag
            dest = ('255.255.255.255', DHCP_CLIENT_PORT)
        elif request['ciaddr'] != '0.0.0.0':
            dest = (request['ciaddr'], DHCP_CLIENT_PORT)
        elif request['giaddr'] != '0.0.0.0':
            dest = (request['giaddr'], DHCP_SERVER_PORT)
        else:
            dest = ('255.255.255.255', DHCP_CLIENT_PORT)

        try:
            self._socket.sendto(response, dest)
        except Exception as e:
            self.logger.error(f"Failed to send response: {e}")

    def get_leases(self) -> List[DHCPLease]:
        """Get all active leases"""
        return [l for l in self._leases.values() if l.state == LeaseState.ACTIVE]

    def get_statistics(self) -> Dict[str, Any]:
        """Get DHCP server statistics"""
        active = sum(1 for l in self._leases.values() if l.state == LeaseState.ACTIVE)
        offered = len(self._pending_offers)

        return {
            "server_ip": self.server_ip,
            "running": self.running,
            "pools": len(self._pools),
            "active_leases": active,
            "pending_offers": offered,
            "total_leases": len(self._leases),
        }
