"""
NetFlow/IPFIX Protocol Implementation for Agentic Networks

Based on:
- RFC 7011: IP Flow Information Export (IPFIX) Protocol Specification
- RFC 5102: Information Model for IP Flow Information Export

This module implements:
- Flow Exporter: Each agent exports flow data to collectors
- Flow Collector: Agents receive and aggregate flow data
- Flow Records: Track traffic flows between agents
- Integration with QoS for DSCP-aware flow tracking
"""

import logging
import asyncio
import struct
import socket
import time
import hashlib
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("NetFlow")

# IPFIX Protocol Constants (RFC 7011)
IPFIX_VERSION = 10  # 0x000a
IPFIX_DEFAULT_PORT = 4739  # UDP port for IPFIX
NETFLOW_V9_PORT = 2055  # Traditional NetFlow v9 port

# Template Set IDs (RFC 7011 Section 3.4.1)
TEMPLATE_SET_ID = 2
OPTIONS_TEMPLATE_SET_ID = 3
# Data Set IDs start at 256

# IANA IPFIX Information Elements (RFC 5102)
class InfoElement(IntEnum):
    """IPFIX Information Element IDs from IANA registry"""
    # Basic flow identifiers
    octetDeltaCount = 1
    packetDeltaCount = 2
    protocolIdentifier = 4
    ipClassOfService = 5  # DSCP/TOS
    sourceTransportPort = 7
    sourceIPv4Address = 8
    sourceIPv4PrefixLength = 9
    ingressInterface = 10
    destinationTransportPort = 11
    destinationIPv4Address = 12
    destinationIPv4PrefixLength = 13
    egressInterface = 14
    ipNextHopIPv4Address = 15
    bgpSourceAsNumber = 16
    bgpDestinationAsNumber = 17

    # Timestamps
    flowStartSeconds = 150
    flowEndSeconds = 151
    flowStartMilliseconds = 152
    flowEndMilliseconds = 153

    # IPv6
    sourceIPv6Address = 27
    destinationIPv6Address = 28
    sourceIPv6PrefixLength = 29
    destinationIPv6PrefixLength = 30

    # Additional flow info
    flowDirection = 61  # 0=ingress, 1=egress
    flowEndReason = 136
    observationDomainId = 149

    # Agent-specific (enterprise elements)
    agentId = 32768  # Enterprise-specific
    agentRouterId = 32769
    flowServiceClass = 32770  # QoS service class


@dataclass
class FlowKey:
    """
    5-tuple flow key for identifying unique flows.
    """
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int  # IP protocol number (6=TCP, 17=UDP, 89=OSPF)

    def __hash__(self):
        return hash((self.src_ip, self.dst_ip, self.src_port, self.dst_port, self.protocol))

    def __eq__(self, other):
        return (self.src_ip == other.src_ip and
                self.dst_ip == other.dst_ip and
                self.src_port == other.src_port and
                self.dst_port == other.dst_port and
                self.protocol == other.protocol)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
            "src_port": self.src_port,
            "dst_port": self.dst_port,
            "protocol": self.protocol,
            "protocol_name": self._get_protocol_name()
        }

    def _get_protocol_name(self) -> str:
        names = {
            1: "ICMP", 6: "TCP", 17: "UDP", 47: "GRE",
            50: "ESP", 51: "AH", 89: "OSPF", 132: "SCTP"
        }
        return names.get(self.protocol, f"IP-{self.protocol}")


@dataclass
class FlowRecord:
    """
    Individual flow record tracking packets between two endpoints.
    """
    flow_key: FlowKey

    # Counters
    packet_count: int = 0
    byte_count: int = 0

    # Timestamps (Unix epoch)
    start_time: float = 0.0
    end_time: float = 0.0

    # Interface info
    ingress_interface: str = ""
    egress_interface: str = ""

    # QoS info (integration with RFC 4594)
    dscp: int = 0
    service_class: str = "standard"

    # BGP info (if available)
    src_as: int = 0
    dst_as: int = 0

    # Agent info
    exporter_id: str = ""
    observation_domain: int = 0

    # Flow state
    is_active: bool = True
    direction: str = "egress"  # ingress or egress

    def update(self, bytes_count: int, packet_count: int = 1):
        """Update flow counters"""
        self.packet_count += packet_count
        self.byte_count += bytes_count
        self.end_time = time.time()

        if self.start_time == 0:
            self.start_time = self.end_time

    def duration_seconds(self) -> float:
        """Get flow duration in seconds"""
        if self.start_time == 0:
            return 0
        return self.end_time - self.start_time

    def bytes_per_second(self) -> float:
        """Calculate average throughput"""
        duration = self.duration_seconds()
        if duration == 0:
            return 0
        return self.byte_count / duration

    def packets_per_second(self) -> float:
        """Calculate packet rate"""
        duration = self.duration_seconds()
        if duration == 0:
            return 0
        return self.packet_count / duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_key": self.flow_key.to_dict(),
            "packet_count": self.packet_count,
            "byte_count": self.byte_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round(self.duration_seconds(), 2),
            "bytes_per_second": round(self.bytes_per_second(), 2),
            "packets_per_second": round(self.packets_per_second(), 2),
            "ingress_interface": self.ingress_interface,
            "egress_interface": self.egress_interface,
            "dscp": self.dscp,
            "service_class": self.service_class,
            "src_as": self.src_as,
            "dst_as": self.dst_as,
            "exporter_id": self.exporter_id,
            "direction": self.direction,
            "is_active": self.is_active
        }


@dataclass
class IPFIXMessageHeader:
    """
    IPFIX Message Header (RFC 7011 Section 3.1)
    """
    version: int = IPFIX_VERSION
    length: int = 0
    export_time: int = 0
    sequence_number: int = 0
    observation_domain_id: int = 0

    def pack(self) -> bytes:
        """Pack header to bytes for transmission"""
        return struct.pack(
            "!HHIII",
            self.version,
            self.length,
            self.export_time,
            self.sequence_number,
            self.observation_domain_id
        )

    @classmethod
    def unpack(cls, data: bytes) -> "IPFIXMessageHeader":
        """Unpack header from received bytes"""
        version, length, export_time, seq_num, obs_domain = struct.unpack("!HHIII", data[:16])
        return cls(
            version=version,
            length=length,
            export_time=export_time,
            sequence_number=seq_num,
            observation_domain_id=obs_domain
        )


class FlowExporter:
    """
    IPFIX/NetFlow Exporter - Exports flow data from this agent.

    Each agent runs an exporter that:
    1. Tracks flows for traffic passing through
    2. Periodically exports flow records to collectors
    3. Integrates with QoS for DSCP-aware flow tracking
    """

    def __init__(self, agent_id: str, router_id: str = "0.0.0.0"):
        self.agent_id = agent_id
        self.router_id = router_id
        self.observation_domain_id = self._generate_domain_id()

        # Active flows (keyed by FlowKey)
        self.active_flows: Dict[FlowKey, FlowRecord] = {}

        # Expired flows (for history)
        self.expired_flows: List[FlowRecord] = []
        self.max_expired_flows = 1000  # Keep last N expired flows

        # Export settings
        self.collectors: List[Tuple[str, int]] = []  # (ip, port) tuples
        self.export_interval = 60  # Export every 60 seconds
        self.flow_timeout = 300  # Flow inactive timeout (5 min)
        self.template_refresh = 600  # Re-send templates every 10 min

        # Counters
        self.sequence_number = 0
        self.total_flows_exported = 0
        self.total_packets_observed = 0
        self.total_bytes_observed = 0

        # Protocol statistics
        self.protocol_stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {"packets": 0, "bytes": 0, "flows": 0})

        # State
        self.running = False
        self.socket: Optional[socket.socket] = None

        # Templates
        self.template_id = 256
        self.last_template_time = 0

        logger.info(f"[NetFlow] Exporter initialized for agent {agent_id} (domain={self.observation_domain_id})")

    def _generate_domain_id(self) -> int:
        """Generate unique observation domain ID from agent ID"""
        return int(hashlib.md5(self.agent_id.encode()).hexdigest()[:8], 16) % (2**32)

    def add_collector(self, ip: str, port: int = IPFIX_DEFAULT_PORT):
        """Add a flow collector to export to"""
        self.collectors.append((ip, port))
        logger.info(f"[NetFlow] Added collector {ip}:{port}")

    def record_flow(
        self,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        protocol: int,
        bytes_count: int,
        packet_count: int = 1,
        dscp: int = 0,
        service_class: str = "standard",
        ingress_if: str = "",
        egress_if: str = "",
        direction: str = "egress",
        src_as: int = 0,
        dst_as: int = 0
    ):
        """
        Record a flow observation.
        Called when traffic is observed passing through the agent.
        """
        flow_key = FlowKey(src_ip, dst_ip, src_port, dst_port, protocol)

        if flow_key in self.active_flows:
            # Update existing flow
            flow = self.active_flows[flow_key]
            flow.update(bytes_count, packet_count)
        else:
            # Create new flow
            flow = FlowRecord(
                flow_key=flow_key,
                exporter_id=self.agent_id,
                observation_domain=self.observation_domain_id,
                dscp=dscp,
                service_class=service_class,
                ingress_interface=ingress_if,
                egress_interface=egress_if,
                direction=direction,
                src_as=src_as,
                dst_as=dst_as
            )
            flow.update(bytes_count, packet_count)
            self.active_flows[flow_key] = flow
            self.protocol_stats[protocol]["flows"] += 1

        # Update global counters
        self.total_packets_observed += packet_count
        self.total_bytes_observed += bytes_count
        self.protocol_stats[protocol]["packets"] += packet_count
        self.protocol_stats[protocol]["bytes"] += bytes_count

    def record_protocol_flow(
        self,
        protocol_name: str,
        src_ip: str,
        dst_ip: str,
        bytes_count: int,
        interface: str = "eth0",
        direction: str = "egress",
        dscp: int = 48,  # Default CS6 for control protocols
        service_class: str = "network_control"
    ):
        """
        Record a flow for a specific protocol (OSPF, BGP, etc.)
        Simplified interface for protocol implementations.
        """
        # Map protocol names to numbers
        protocol_map = {
            "ospf": 89, "bgp": 6, "isis": 124, "ldp": 6,
            "bfd": 17, "lldp": 0, "icmp": 1, "tcp": 6, "udp": 17
        }
        protocol_num = protocol_map.get(protocol_name.lower(), 0)

        # Protocol-specific ports
        port_map = {
            "bgp": 179, "ldp": 646, "bfd": 3784,
            "snmp": 161, "ssh": 22, "http": 80, "https": 443
        }
        port = port_map.get(protocol_name.lower(), 0)

        self.record_flow(
            src_ip=src_ip,
            dst_ip=dst_ip,
            src_port=port,
            dst_port=port,
            protocol=protocol_num,
            bytes_count=bytes_count,
            dscp=dscp,
            service_class=service_class,
            ingress_if=interface if direction == "ingress" else "",
            egress_if=interface if direction == "egress" else "",
            direction=direction
        )

    def expire_inactive_flows(self) -> List[FlowRecord]:
        """Check for and expire inactive flows"""
        now = time.time()
        expired = []

        for flow_key, flow in list(self.active_flows.items()):
            if now - flow.end_time > self.flow_timeout:
                flow.is_active = False
                expired.append(flow)
                del self.active_flows[flow_key]

        # Add to history
        self.expired_flows.extend(expired)

        # Trim history
        if len(self.expired_flows) > self.max_expired_flows:
            self.expired_flows = self.expired_flows[-self.max_expired_flows:]

        return expired

    def get_active_flows(self) -> List[Dict[str, Any]]:
        """Get all active flows as dictionaries"""
        return [flow.to_dict() for flow in self.active_flows.values()]

    def get_top_flows(self, n: int = 10, sort_by: str = "bytes") -> List[Dict[str, Any]]:
        """Get top N flows by bytes or packets"""
        flows = list(self.active_flows.values())

        if sort_by == "bytes":
            flows.sort(key=lambda f: f.byte_count, reverse=True)
        elif sort_by == "packets":
            flows.sort(key=lambda f: f.packet_count, reverse=True)
        elif sort_by == "rate":
            flows.sort(key=lambda f: f.bytes_per_second(), reverse=True)

        return [f.to_dict() for f in flows[:n]]

    def get_flows_by_protocol(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group flows by protocol"""
        by_protocol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for flow in self.active_flows.values():
            proto_name = flow.flow_key._get_protocol_name()
            by_protocol[proto_name].append(flow.to_dict())

        return dict(by_protocol)

    def get_flows_by_service_class(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group flows by QoS service class"""
        by_class: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for flow in self.active_flows.values():
            by_class[flow.service_class].append(flow.to_dict())

        return dict(by_class)

    def get_statistics(self) -> Dict[str, Any]:
        """Get exporter statistics"""
        return {
            "agent_id": self.agent_id,
            "observation_domain_id": self.observation_domain_id,
            "active_flows": len(self.active_flows),
            "expired_flows": len(self.expired_flows),
            "total_flows_exported": self.total_flows_exported,
            "total_packets_observed": self.total_packets_observed,
            "total_bytes_observed": self.total_bytes_observed,
            "collectors": [f"{ip}:{port}" for ip, port in self.collectors],
            "export_interval": self.export_interval,
            "flow_timeout": self.flow_timeout,
            "running": self.running,
            "protocol_stats": {
                FlowKey("", "", 0, 0, proto)._get_protocol_name(): stats
                for proto, stats in self.protocol_stats.items()
            }
        }

    def build_template_record(self) -> bytes:
        """Build IPFIX template record for flow data"""
        # Template fields we export
        fields = [
            (InfoElement.sourceIPv4Address, 4),
            (InfoElement.destinationIPv4Address, 4),
            (InfoElement.sourceTransportPort, 2),
            (InfoElement.destinationTransportPort, 2),
            (InfoElement.protocolIdentifier, 1),
            (InfoElement.octetDeltaCount, 8),
            (InfoElement.packetDeltaCount, 8),
            (InfoElement.flowStartSeconds, 4),
            (InfoElement.flowEndSeconds, 4),
            (InfoElement.ipClassOfService, 1),
            (InfoElement.ingressInterface, 4),
            (InfoElement.egressInterface, 4),
        ]

        # Template Set Header
        set_id = TEMPLATE_SET_ID
        field_count = len(fields)

        # Build field specifiers
        field_data = b""
        for element_id, length in fields:
            # Standard IANA element (enterprise bit = 0)
            field_data += struct.pack("!HH", element_id, length)

        # Template record header
        template_header = struct.pack("!HH", self.template_id, field_count)

        # Set header (set_id=2 for templates, length includes header)
        set_length = 4 + 4 + len(field_data)  # set header + template header + fields
        set_header = struct.pack("!HH", set_id, set_length)

        return set_header + template_header + field_data

    def build_data_record(self, flow: FlowRecord) -> bytes:
        """Build IPFIX data record for a flow"""
        # Pack flow data according to our template
        try:
            src_ip = socket.inet_aton(flow.flow_key.src_ip)
            dst_ip = socket.inet_aton(flow.flow_key.dst_ip)
        except:
            src_ip = b"\x00\x00\x00\x00"
            dst_ip = b"\x00\x00\x00\x00"

        data = b""
        data += src_ip
        data += dst_ip
        data += struct.pack("!H", flow.flow_key.src_port)
        data += struct.pack("!H", flow.flow_key.dst_port)
        data += struct.pack("!B", flow.flow_key.protocol)
        data += struct.pack("!Q", flow.byte_count)
        data += struct.pack("!Q", flow.packet_count)
        data += struct.pack("!I", int(flow.start_time))
        data += struct.pack("!I", int(flow.end_time))
        data += struct.pack("!B", flow.dscp)
        data += struct.pack("!I", hash(flow.ingress_interface) % (2**32) if flow.ingress_interface else 0)
        data += struct.pack("!I", hash(flow.egress_interface) % (2**32) if flow.egress_interface else 0)

        return data

    def build_export_message(self, flows: List[FlowRecord], include_template: bool = False) -> bytes:
        """Build complete IPFIX message for export"""
        # Start with empty payload
        payload = b""

        # Include template if needed
        if include_template:
            payload += self.build_template_record()

        # Build data set
        if flows:
            data_records = b""
            for flow in flows:
                data_records += self.build_data_record(flow)

            # Data Set header (set_id = template_id)
            set_length = 4 + len(data_records)
            data_set = struct.pack("!HH", self.template_id, set_length) + data_records
            payload += data_set

        # Build message header
        self.sequence_number += len(flows)
        header = IPFIXMessageHeader(
            version=IPFIX_VERSION,
            length=16 + len(payload),  # Header (16) + payload
            export_time=int(time.time()),
            sequence_number=self.sequence_number,
            observation_domain_id=self.observation_domain_id
        )

        return header.pack() + payload

    async def export_flows(self):
        """Export current flows to all collectors"""
        if not self.collectors:
            return

        # Check if we need to send template
        now = time.time()
        include_template = (now - self.last_template_time) > self.template_refresh
        if include_template:
            self.last_template_time = now

        # Get flows to export
        flows = list(self.active_flows.values())

        if not flows and not include_template:
            return

        # Build message
        message = self.build_export_message(flows, include_template)

        # Send to all collectors
        for ip, port in self.collectors:
            try:
                if not self.socket:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                self.socket.sendto(message, (ip, port))
                self.total_flows_exported += len(flows)
                logger.debug(f"[NetFlow] Exported {len(flows)} flows to {ip}:{port}")
            except Exception as e:
                logger.warning(f"[NetFlow] Export to {ip}:{port} failed: {e}")

    async def start(self):
        """Start the flow exporter background task"""
        self.running = True
        logger.info(f"[NetFlow] Exporter started for agent {self.agent_id}")

        while self.running:
            try:
                # Expire old flows
                expired = self.expire_inactive_flows()
                if expired:
                    logger.debug(f"[NetFlow] Expired {len(expired)} inactive flows")

                # Export flows
                await self.export_flows()

                # Wait for next export interval
                await asyncio.sleep(self.export_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[NetFlow] Exporter error: {e}")
                await asyncio.sleep(10)

        logger.info(f"[NetFlow] Exporter stopped for agent {self.agent_id}")

    def stop(self):
        """Stop the exporter"""
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None


class FlowCollector:
    """
    IPFIX/NetFlow Collector - Receives and aggregates flow data from exporters.

    Can be run on any agent to collect flows from the network.
    """

    def __init__(self, agent_id: str, listen_port: int = IPFIX_DEFAULT_PORT):
        self.agent_id = agent_id
        self.listen_port = listen_port

        # Received flows indexed by exporter
        self.flows_by_exporter: Dict[str, List[FlowRecord]] = defaultdict(list)

        # Aggregated statistics
        self.total_messages_received = 0
        self.total_flows_received = 0
        self.exporters_seen: Dict[int, str] = {}  # observation_domain -> last_seen

        # Templates received from exporters
        self.templates: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}  # (domain, template_id) -> fields

        # State
        self.running = False
        self.socket: Optional[socket.socket] = None

        logger.info(f"[NetFlow] Collector initialized on port {listen_port}")

    def parse_message(self, data: bytes, source_addr: Tuple[str, int]) -> List[FlowRecord]:
        """Parse received IPFIX message"""
        if len(data) < 16:
            return []

        # Parse header
        header = IPFIXMessageHeader.unpack(data)

        if header.version != IPFIX_VERSION:
            logger.warning(f"[NetFlow] Unsupported version: {header.version}")
            return []

        self.total_messages_received += 1
        self.exporters_seen[header.observation_domain_id] = time.time()

        # Parse sets
        flows = []
        offset = 16  # After header

        while offset < header.length:
            if offset + 4 > len(data):
                break

            set_id, set_length = struct.unpack("!HH", data[offset:offset+4])

            if set_length < 4:
                break

            set_data = data[offset+4:offset+set_length]

            if set_id == TEMPLATE_SET_ID:
                self._parse_template_set(set_data, header.observation_domain_id)
            elif set_id >= 256:
                flows.extend(self._parse_data_set(set_data, set_id, header.observation_domain_id, source_addr[0]))

            offset += set_length

        self.total_flows_received += len(flows)
        return flows

    def _parse_template_set(self, data: bytes, domain_id: int):
        """Parse template set and store template definitions"""
        offset = 0
        while offset + 4 <= len(data):
            template_id, field_count = struct.unpack("!HH", data[offset:offset+4])
            offset += 4

            fields = []
            for _ in range(field_count):
                if offset + 4 > len(data):
                    break

                element_id, length = struct.unpack("!HH", data[offset:offset+4])
                offset += 4

                # Check enterprise bit
                if element_id & 0x8000:
                    if offset + 4 > len(data):
                        break
                    offset += 4  # Skip enterprise number

                fields.append((element_id & 0x7FFF, length))

            self.templates[(domain_id, template_id)] = fields
            logger.debug(f"[NetFlow] Received template {template_id} with {len(fields)} fields")

    def _parse_data_set(self, data: bytes, template_id: int, domain_id: int, exporter_ip: str) -> List[FlowRecord]:
        """Parse data set using stored template"""
        flows = []

        # Get template for this data set
        template_key = (domain_id, template_id)
        if template_key not in self.templates:
            logger.warning(f"[NetFlow] No template for set {template_id}")
            return flows

        template = self.templates[template_key]
        record_length = sum(length for _, length in template)

        offset = 0
        while offset + record_length <= len(data):
            # Parse record using template
            record_data = {}
            field_offset = offset

            for element_id, length in template:
                if field_offset + length > len(data):
                    break

                field_data = data[field_offset:field_offset+length]
                record_data[element_id] = self._parse_field(element_id, field_data)
                field_offset += length

            # Convert to FlowRecord
            flow = self._create_flow_record(record_data, domain_id, exporter_ip)
            if flow:
                flows.append(flow)

            offset += record_length

        return flows

    def _parse_field(self, element_id: int, data: bytes) -> Any:
        """Parse a single field value"""
        length = len(data)

        if element_id in (InfoElement.sourceIPv4Address, InfoElement.destinationIPv4Address, InfoElement.ipNextHopIPv4Address):
            return socket.inet_ntoa(data) if length == 4 else ""
        elif element_id in (InfoElement.octetDeltaCount, InfoElement.packetDeltaCount):
            return struct.unpack("!Q", data)[0] if length == 8 else struct.unpack("!I", data)[0]
        elif element_id in (InfoElement.sourceTransportPort, InfoElement.destinationTransportPort):
            return struct.unpack("!H", data)[0]
        elif element_id in (InfoElement.protocolIdentifier, InfoElement.ipClassOfService):
            return data[0]
        elif element_id in (InfoElement.flowStartSeconds, InfoElement.flowEndSeconds, InfoElement.ingressInterface, InfoElement.egressInterface):
            return struct.unpack("!I", data)[0]
        else:
            return data

    def _create_flow_record(self, data: Dict[int, Any], domain_id: int, exporter_ip: str) -> Optional[FlowRecord]:
        """Create FlowRecord from parsed data"""
        try:
            flow_key = FlowKey(
                src_ip=data.get(InfoElement.sourceIPv4Address, "0.0.0.0"),
                dst_ip=data.get(InfoElement.destinationIPv4Address, "0.0.0.0"),
                src_port=data.get(InfoElement.sourceTransportPort, 0),
                dst_port=data.get(InfoElement.destinationTransportPort, 0),
                protocol=data.get(InfoElement.protocolIdentifier, 0)
            )

            flow = FlowRecord(
                flow_key=flow_key,
                packet_count=data.get(InfoElement.packetDeltaCount, 0),
                byte_count=data.get(InfoElement.octetDeltaCount, 0),
                start_time=data.get(InfoElement.flowStartSeconds, 0),
                end_time=data.get(InfoElement.flowEndSeconds, 0),
                dscp=data.get(InfoElement.ipClassOfService, 0),
                observation_domain=domain_id,
                exporter_id=exporter_ip,
                is_active=True
            )

            return flow
        except Exception as e:
            logger.warning(f"[NetFlow] Failed to create flow record: {e}")
            return None

    def get_all_flows(self) -> List[Dict[str, Any]]:
        """Get all collected flows"""
        all_flows = []
        for flows in self.flows_by_exporter.values():
            all_flows.extend([f.to_dict() for f in flows])
        return all_flows

    def get_statistics(self) -> Dict[str, Any]:
        """Get collector statistics"""
        return {
            "agent_id": self.agent_id,
            "listen_port": self.listen_port,
            "total_messages_received": self.total_messages_received,
            "total_flows_received": self.total_flows_received,
            "exporters_count": len(self.exporters_seen),
            "exporters": list(self.exporters_seen.keys()),
            "templates_count": len(self.templates),
            "running": self.running
        }

    async def start(self):
        """Start the flow collector"""
        self.running = True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(("0.0.0.0", self.listen_port))
            self.socket.setblocking(False)

            logger.info(f"[NetFlow] Collector listening on port {self.listen_port}")

            loop = asyncio.get_event_loop()

            while self.running:
                try:
                    data, addr = await loop.run_in_executor(None, lambda: self.socket.recvfrom(65535))
                    flows = self.parse_message(data, addr)

                    if flows:
                        exporter_key = f"{addr[0]}:{addr[1]}"
                        self.flows_by_exporter[exporter_key].extend(flows)

                        # Trim old flows per exporter
                        if len(self.flows_by_exporter[exporter_key]) > 10000:
                            self.flows_by_exporter[exporter_key] = self.flows_by_exporter[exporter_key][-5000:]

                except BlockingIOError:
                    await asyncio.sleep(0.1)
                except Exception as e:
                    if self.running:
                        logger.debug(f"[NetFlow] Collector recv: {e}")
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"[NetFlow] Collector error: {e}")
        finally:
            if self.socket:
                self.socket.close()
                self.socket = None

        logger.info(f"[NetFlow] Collector stopped")

    def stop(self):
        """Stop the collector"""
        self.running = False


# Singleton instances per agent
_flow_exporters: Dict[str, FlowExporter] = {}
_flow_collectors: Dict[str, FlowCollector] = {}


def get_flow_exporter(agent_id: str = "local", router_id: str = "0.0.0.0") -> FlowExporter:
    """Get or create flow exporter for an agent"""
    if agent_id not in _flow_exporters:
        _flow_exporters[agent_id] = FlowExporter(agent_id, router_id)
    return _flow_exporters[agent_id]


def get_flow_collector(agent_id: str = "local", listen_port: int = IPFIX_DEFAULT_PORT) -> FlowCollector:
    """Get or create flow collector for an agent"""
    if agent_id not in _flow_collectors:
        _flow_collectors[agent_id] = FlowCollector(agent_id, listen_port)
    return _flow_collectors[agent_id]
