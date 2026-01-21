"""
DNS Server Implementation

Provides DNS server functionality for name resolution in the network.
Implements basic DNS protocol per RFC 1035.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum


# DNS Constants
DNS_PORT = 53
DNS_MAX_UDP_SIZE = 512

# DNS Record Types
DNS_TYPE_A = 1         # IPv4 address
DNS_TYPE_NS = 2        # Nameserver
DNS_TYPE_CNAME = 5     # Canonical name (alias)
DNS_TYPE_SOA = 6       # Start of Authority
DNS_TYPE_PTR = 12      # Pointer (reverse lookup)
DNS_TYPE_MX = 15       # Mail exchange
DNS_TYPE_TXT = 16      # Text record
DNS_TYPE_AAAA = 28     # IPv6 address
DNS_TYPE_SRV = 33      # Service record

# DNS Classes
DNS_CLASS_IN = 1       # Internet

# DNS Response Codes
DNS_RCODE_OK = 0           # No error
DNS_RCODE_FORMAT = 1       # Format error
DNS_RCODE_SERVFAIL = 2     # Server failure
DNS_RCODE_NXDOMAIN = 3     # Name doesn't exist
DNS_RCODE_NOTIMPL = 4      # Not implemented
DNS_RCODE_REFUSED = 5      # Refused


class RecordType(Enum):
    """DNS Record Types"""
    A = DNS_TYPE_A
    NS = DNS_TYPE_NS
    CNAME = DNS_TYPE_CNAME
    SOA = DNS_TYPE_SOA
    PTR = DNS_TYPE_PTR
    MX = DNS_TYPE_MX
    TXT = DNS_TYPE_TXT
    AAAA = DNS_TYPE_AAAA
    SRV = DNS_TYPE_SRV


@dataclass
class DNSRecord:
    """
    DNS Resource Record.

    Represents a single DNS record entry.
    """
    name: str                         # Domain name
    record_type: RecordType           # Record type
    value: str                        # Record value (IP, hostname, etc.)
    ttl: int = 3600                   # Time to live (seconds)
    priority: int = 0                 # Priority (for MX, SRV)
    dns_class: int = DNS_CLASS_IN

    def matches(self, query_name: str, query_type: int) -> bool:
        """Check if record matches query"""
        name_match = self.name.lower() == query_name.lower()
        type_match = self.record_type.value == query_type

        # CNAME matches any type query
        if name_match and self.record_type == RecordType.CNAME:
            return True

        return name_match and type_match

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "type": self.record_type.name,
            "value": self.value,
            "ttl": self.ttl,
            "priority": self.priority if self.record_type in (RecordType.MX, RecordType.SRV) else None,
        }


@dataclass
class DNSZone:
    """
    DNS Zone.

    A collection of DNS records for a domain.
    """
    domain: str                       # Zone domain (e.g., "example.com")
    records: List[DNSRecord] = field(default_factory=list)

    # SOA record fields
    primary_ns: str = ""              # Primary nameserver
    admin_email: str = ""             # Admin email (@ replaced with .)
    serial: int = 1                   # Zone serial number
    refresh: int = 3600               # Refresh interval
    retry: int = 600                  # Retry interval
    expire: int = 604800              # Expire time
    minimum_ttl: int = 3600           # Minimum TTL

    def add_record(self, record: DNSRecord) -> None:
        """Add record to zone"""
        self.records.append(record)

    def remove_record(self, name: str, record_type: RecordType) -> bool:
        """Remove record from zone"""
        for i, record in enumerate(self.records):
            if record.name.lower() == name.lower() and record.record_type == record_type:
                self.records.pop(i)
                return True
        return False

    def find_records(self, name: str, record_type: int) -> List[DNSRecord]:
        """Find matching records"""
        return [r for r in self.records if r.matches(name, record_type)]

    def add_a_record(self, name: str, ip: str, ttl: int = 3600) -> None:
        """Add A record"""
        self.add_record(DNSRecord(name=name, record_type=RecordType.A, value=ip, ttl=ttl))

    def add_cname_record(self, name: str, target: str, ttl: int = 3600) -> None:
        """Add CNAME record"""
        self.add_record(DNSRecord(name=name, record_type=RecordType.CNAME, value=target, ttl=ttl))

    def add_ptr_record(self, ip: str, hostname: str, ttl: int = 3600) -> None:
        """Add PTR record for reverse lookup"""
        # Convert IP to PTR name (e.g., 1.0.168.192.in-addr.arpa)
        parts = ip.split('.')
        ptr_name = '.'.join(reversed(parts)) + '.in-addr.arpa'
        self.add_record(DNSRecord(name=ptr_name, record_type=RecordType.PTR, value=hostname, ttl=ttl))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "domain": self.domain,
            "primary_ns": self.primary_ns,
            "admin_email": self.admin_email,
            "serial": self.serial,
            "records": [r.to_dict() for r in self.records],
        }


class DNSServer:
    """
    DNS Server.

    Provides DNS resolution services for the network.
    """

    def __init__(
        self,
        listen_ip: str = "0.0.0.0",
        upstream_dns: Optional[List[str]] = None,
    ):
        """
        Initialize DNS server.

        Args:
            listen_ip: IP to listen on
            upstream_dns: Upstream DNS servers for forwarding
        """
        self.listen_ip = listen_ip
        self.upstream_dns = upstream_dns or ["8.8.8.8", "8.8.4.4"]

        # Zones: {domain: DNSZone}
        self._zones: Dict[str, DNSZone] = {}

        # Cache: {(name, type): (records, expire_time)}
        self._cache: Dict[Tuple[str, int], Tuple[List[DNSRecord], datetime]] = {}

        # UDP socket
        self._socket: Optional[socket.socket] = None
        self._receive_task: Optional[asyncio.Task] = None

        # Statistics
        self._queries_received = 0
        self._queries_answered = 0
        self._queries_forwarded = 0
        self._cache_hits = 0

        # Running state
        self.running = False

        self.logger = logging.getLogger("DNSServer")

    def add_zone(self, zone: DNSZone) -> None:
        """Add DNS zone"""
        self._zones[zone.domain.lower()] = zone
        self.logger.info(f"Added zone: {zone.domain}")

    def remove_zone(self, domain: str) -> bool:
        """Remove DNS zone"""
        zone = self._zones.pop(domain.lower(), None)
        return zone is not None

    def get_zone(self, domain: str) -> Optional[DNSZone]:
        """Get zone by domain"""
        return self._zones.get(domain.lower())

    async def start(self) -> None:
        """Start DNS server"""
        self.logger.info(f"Starting DNS server at {self.listen_ip}")
        self.running = True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.listen_ip, DNS_PORT))
            self._socket.setblocking(False)

            self._receive_task = asyncio.create_task(self._receive_loop())

            self.logger.info("DNS server started")

        except Exception as e:
            self.logger.error(f"Failed to start DNS server: {e}")
            self.running = False
            raise

    async def stop(self) -> None:
        """Stop DNS server"""
        self.logger.info("Stopping DNS server")
        self.running = False

        if self._receive_task:
            self._receive_task.cancel()

        if self._socket:
            self._socket.close()

        self.logger.info("DNS server stopped")

    async def _receive_loop(self) -> None:
        """Receive and process DNS queries"""
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                data, addr = await loop.run_in_executor(
                    None,
                    lambda: self._socket.recvfrom(DNS_MAX_UDP_SIZE)
                )

                self._queries_received += 1

                # Process in background task
                asyncio.create_task(self._handle_query(data, addr))

            except asyncio.CancelledError:
                break
            except BlockingIOError:
                await asyncio.sleep(0.01)
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in receive loop: {e}")

    async def _handle_query(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Handle DNS query"""
        try:
            # Parse query
            query = self._parse_query(data)
            if not query:
                return

            name = query['name']
            qtype = query['type']

            self.logger.debug(f"Query: {name} type={qtype} from {addr[0]}")

            # Check cache first
            cached = self._check_cache(name, qtype)
            if cached:
                self._cache_hits += 1
                response = self._build_response(query, cached)
                self._send_response(response, addr)
                return

            # Check local zones
            records = self._lookup_local(name, qtype)

            if records:
                self._queries_answered += 1
                response = self._build_response(query, records)
                self._send_response(response, addr)

                # Cache the response
                self._add_to_cache(name, qtype, records)
            else:
                # Forward to upstream
                await self._forward_query(data, addr)

        except Exception as e:
            self.logger.error(f"Error handling query: {e}")

    def _parse_query(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse DNS query packet"""
        if len(data) < 12:
            return None

        query = {}

        # Header
        query['id'] = struct.unpack('!H', data[0:2])[0]
        flags = struct.unpack('!H', data[2:4])[0]
        query['qr'] = (flags >> 15) & 1
        query['opcode'] = (flags >> 11) & 0xF
        query['rd'] = (flags >> 8) & 1

        qdcount = struct.unpack('!H', data[4:6])[0]

        if qdcount < 1:
            return None

        # Parse question
        offset = 12
        name_parts = []
        max_iterations = 255  # Prevent infinite loops from malformed data

        while offset < len(data) and max_iterations > 0:
            max_iterations -= 1
            length = data[offset]
            if length == 0:
                offset += 1
                break
            # Bounds check: ensure we have enough data for the label
            if offset + 1 + length > len(data):
                self.logger.warning(f"DNS query truncated: label needs {length} bytes at offset {offset}")
                return None
            try:
                name_parts.append(data[offset + 1:offset + 1 + length].decode('ascii'))
            except UnicodeDecodeError as e:
                self.logger.warning(f"DNS query contains non-ASCII label: {e}")
                return None
            offset += 1 + length

        query['name'] = '.'.join(name_parts)

        if offset + 4 > len(data):
            return None

        query['type'] = struct.unpack('!H', data[offset:offset + 2])[0]
        query['class'] = struct.unpack('!H', data[offset + 2:offset + 4])[0]

        return query

    def _lookup_local(self, name: str, qtype: int) -> List[DNSRecord]:
        """Look up name in local zones"""
        # Find matching zone
        name_lower = name.lower()
        matching_zone = None

        for domain, zone in self._zones.items():
            if name_lower.endswith(domain) or name_lower == domain:
                matching_zone = zone
                break

        if not matching_zone:
            return []

        # Find matching records
        records = matching_zone.find_records(name, qtype)

        # Follow CNAME if needed
        if not records or (records[0].record_type == RecordType.CNAME and qtype != DNS_TYPE_CNAME):
            cnames = matching_zone.find_records(name, DNS_TYPE_CNAME)
            if cnames:
                # Return CNAME and try to resolve target
                target_records = matching_zone.find_records(cnames[0].value, qtype)
                return cnames + target_records

        return records

    def _check_cache(self, name: str, qtype: int) -> Optional[List[DNSRecord]]:
        """Check cache for records"""
        key = (name.lower(), qtype)
        cached = self._cache.get(key)

        if cached:
            records, expire_time = cached
            if datetime.now() < expire_time:
                return records
            else:
                # Expired
                del self._cache[key]

        return None

    def _add_to_cache(self, name: str, qtype: int, records: List[DNSRecord]) -> None:
        """Add records to cache"""
        if not records:
            return

        # Use minimum TTL from records
        min_ttl = min(r.ttl for r in records)
        expire_time = datetime.now() + timedelta(seconds=min_ttl)

        self._cache[(name.lower(), qtype)] = (records, expire_time)

    def _build_response(self, query: Dict[str, Any], records: List[DNSRecord]) -> bytes:
        """Build DNS response packet"""
        response = bytearray()

        # Header
        response.extend(struct.pack('!H', query['id']))

        # Flags: QR=1, AA=1, RD=query['rd'], RA=1, RCODE=0
        flags = 0x8400 | (query['rd'] << 8)
        if not records:
            flags |= DNS_RCODE_NXDOMAIN
        response.extend(struct.pack('!H', flags))

        # Question count
        response.extend(struct.pack('!H', 1))

        # Answer count
        response.extend(struct.pack('!H', len(records)))

        # Authority count
        response.extend(struct.pack('!H', 0))

        # Additional count
        response.extend(struct.pack('!H', 0))

        # Question section
        response.extend(self._encode_name(query['name']))
        response.extend(struct.pack('!HH', query['type'], query['class']))

        # Answer section
        for record in records:
            response.extend(self._encode_name(record.name))
            response.extend(struct.pack('!HH', record.record_type.value, record.dns_class))
            response.extend(struct.pack('!I', record.ttl))

            # RDATA
            rdata = self._encode_rdata(record)
            response.extend(struct.pack('!H', len(rdata)))
            response.extend(rdata)

        return bytes(response)

    def _encode_name(self, name: str) -> bytes:
        """Encode domain name"""
        result = bytearray()
        for part in name.split('.'):
            result.append(len(part))
            result.extend(part.encode('ascii'))
        result.append(0)
        return bytes(result)

    def _encode_rdata(self, record: DNSRecord) -> bytes:
        """Encode record data"""
        if record.record_type == RecordType.A:
            parts = record.value.split('.')
            return bytes(int(p) for p in parts)

        elif record.record_type == RecordType.AAAA:
            # IPv6 address
            import ipaddress
            return ipaddress.IPv6Address(record.value).packed

        elif record.record_type in (RecordType.CNAME, RecordType.NS, RecordType.PTR):
            return self._encode_name(record.value)

        elif record.record_type == RecordType.MX:
            result = struct.pack('!H', record.priority)
            result += self._encode_name(record.value)
            return result

        elif record.record_type == RecordType.TXT:
            txt_bytes = record.value.encode('utf-8')
            return bytes([len(txt_bytes)]) + txt_bytes

        else:
            return record.value.encode('utf-8')

    def _send_response(self, response: bytes, addr: Tuple[str, int]) -> None:
        """Send DNS response"""
        if self._socket:
            try:
                self._socket.sendto(response, addr)
            except Exception as e:
                self.logger.error(f"Failed to send response: {e}")

    async def _forward_query(self, query_data: bytes, client_addr: Tuple[str, int]) -> None:
        """Forward query to upstream DNS"""
        if not self.upstream_dns:
            return

        self._queries_forwarded += 1
        sock = None

        try:
            # Create socket for forwarding
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)

            # Forward to first upstream
            upstream = self.upstream_dns[0]
            sock.sendto(query_data, (upstream, DNS_PORT))

            # Wait for response
            response, _ = sock.recvfrom(DNS_MAX_UDP_SIZE)

            # Forward back to client
            self._socket.sendto(response, client_addr)

        except (socket.timeout, socket.error, OSError) as e:
            self.logger.error(f"Failed to forward query: {e}")
        finally:
            if sock:
                sock.close()

    def add_host(self, hostname: str, ip: str, zone_domain: str) -> None:
        """Convenience method to add a host record"""
        zone = self.get_zone(zone_domain)
        if zone:
            fqdn = f"{hostname}.{zone_domain}" if not hostname.endswith(zone_domain) else hostname
            zone.add_a_record(fqdn, ip)
            self.logger.debug(f"Added host: {fqdn} -> {ip}")

    def clear_cache(self) -> None:
        """Clear DNS cache"""
        self._cache.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get DNS server statistics"""
        return {
            "listen_ip": self.listen_ip,
            "running": self.running,
            "zones": len(self._zones),
            "cached_entries": len(self._cache),
            "queries_received": self._queries_received,
            "queries_answered": self._queries_answered,
            "queries_forwarded": self._queries_forwarded,
            "cache_hits": self._cache_hits,
            "upstream_dns": self.upstream_dns,
        }
