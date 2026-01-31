"""
Quality of Service (QoS) Protocol Implementation

Based on RFC 4594 - Configuration Guidelines for DiffServ Service Classes

This module implements DiffServ QoS with:
- Service class definitions per RFC 4594
- DSCP marking and classification
- Traffic shaping and policing
- Per-interface QoS policy application
"""

import logging
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger("QoS")


class DSCP(Enum):
    """
    DSCP (Differentiated Services Code Point) values per RFC 4594.

    Format: 6-bit value (0-63)
    """
    # Class Selector (CS) - RFC 2474
    CS0 = 0    # Best Effort / Default (000000)
    CS1 = 8    # Low Priority (001000)
    CS2 = 16   # OAM (010000)
    CS3 = 24   # Broadcast Video (011000)
    CS4 = 32   # Real-Time Interactive (100000)
    CS5 = 40   # Signaling (101000)
    CS6 = 48   # Network Control (110000)
    CS7 = 56   # Reserved (111000)

    # Expedited Forwarding (EF) - RFC 3246
    EF = 46    # Telephony/Voice (101110)

    # Assured Forwarding (AF) - RFC 2597
    # AFxy where x=class (1-4), y=drop precedence (1-3)
    AF11 = 10  # High-Throughput Data - Low Drop (001010)
    AF12 = 12  # High-Throughput Data - Med Drop (001100)
    AF13 = 14  # High-Throughput Data - High Drop (001110)

    AF21 = 18  # Low-Latency Data - Low Drop (010010)
    AF22 = 20  # Low-Latency Data - Med Drop (010100)
    AF23 = 22  # Low-Latency Data - High Drop (010110)

    AF31 = 26  # Multimedia Streaming - Low Drop (011010)
    AF32 = 28  # Multimedia Streaming - Med Drop (011100)
    AF33 = 30  # Multimedia Streaming - High Drop (011110)

    AF41 = 34  # Multimedia Conferencing - Low Drop (100010)
    AF42 = 36  # Multimedia Conferencing - Med Drop (100100)
    AF43 = 38  # Multimedia Conferencing - High Drop (100110)

    # Voice Admit - RFC 5865
    VOICE_ADMIT = 44  # (101100)

    @property
    def binary(self) -> str:
        """Return 6-bit binary representation"""
        return format(self.value, '06b')

    @property
    def tos_byte(self) -> int:
        """Return full ToS byte (DSCP << 2)"""
        return self.value << 2


class ServiceClass(Enum):
    """
    RFC 4594 Service Classes with recommended DSCP mappings.
    """
    NETWORK_CONTROL = "network_control"
    TELEPHONY = "telephony"
    SIGNALING = "signaling"
    MULTIMEDIA_CONFERENCING = "multimedia_conferencing"
    REALTIME_INTERACTIVE = "realtime_interactive"
    MULTIMEDIA_STREAMING = "multimedia_streaming"
    BROADCAST_VIDEO = "broadcast_video"
    LOW_LATENCY_DATA = "low_latency_data"
    OAM = "oam"
    HIGH_THROUGHPUT_DATA = "high_throughput_data"
    STANDARD = "standard"
    LOW_PRIORITY = "low_priority"


@dataclass
class ServiceClassConfig:
    """Configuration for a DiffServ service class"""
    name: str
    service_class: ServiceClass
    dscp: DSCP
    description: str

    # Traffic characteristics
    traffic_type: str  # "real-time", "elastic", "best-effort"
    tolerance_loss: str  # "very low", "low", "medium", "high"
    tolerance_delay: str  # "very low", "low", "medium", "high"
    tolerance_jitter: str  # "very low", "low", "medium", "high"

    # PHB (Per-Hop Behavior)
    phb: str  # "EF", "AF", "CS", "BE"
    rfc_reference: str

    # Queue parameters
    priority: int  # 0-7, higher = more priority
    weight: int = 10  # For weighted fair queuing
    min_bandwidth_percent: int = 0  # Minimum guaranteed bandwidth
    max_bandwidth_percent: int = 100  # Maximum allowed bandwidth

    # Colors for visualization
    color: str = "#808080"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "service_class": self.service_class.value,
            "dscp": self.dscp.name,
            "dscp_value": self.dscp.value,
            "dscp_binary": self.dscp.binary,
            "description": self.description,
            "traffic_type": self.traffic_type,
            "tolerance": {
                "loss": self.tolerance_loss,
                "delay": self.tolerance_delay,
                "jitter": self.tolerance_jitter
            },
            "phb": self.phb,
            "rfc_reference": self.rfc_reference,
            "priority": self.priority,
            "weight": self.weight,
            "bandwidth": {
                "min_percent": self.min_bandwidth_percent,
                "max_percent": self.max_bandwidth_percent
            },
            "color": self.color
        }


# RFC 4594 Standard Service Class Definitions
RFC4594_SERVICE_CLASSES: Dict[ServiceClass, ServiceClassConfig] = {
    ServiceClass.NETWORK_CONTROL: ServiceClassConfig(
        name="Network Control",
        service_class=ServiceClass.NETWORK_CONTROL,
        dscp=DSCP.CS6,
        description="Routing protocols, network management (OSPF, BGP, SNMP)",
        traffic_type="control",
        tolerance_loss="very low",
        tolerance_delay="low",
        tolerance_jitter="high",
        phb="CS",
        rfc_reference="RFC 2474",
        priority=7,
        weight=5,
        min_bandwidth_percent=2,
        max_bandwidth_percent=5,
        color="#ef4444"  # Red - critical
    ),

    ServiceClass.TELEPHONY: ServiceClassConfig(
        name="Telephony (Voice)",
        service_class=ServiceClass.TELEPHONY,
        dscp=DSCP.EF,
        description="VoIP bearer traffic (RTP voice streams)",
        traffic_type="real-time",
        tolerance_loss="very low",
        tolerance_delay="very low",
        tolerance_jitter="very low",
        phb="EF",
        rfc_reference="RFC 3246",
        priority=6,
        weight=10,
        min_bandwidth_percent=10,
        max_bandwidth_percent=30,
        color="#22c55e"  # Green - voice
    ),

    ServiceClass.SIGNALING: ServiceClassConfig(
        name="Signaling",
        service_class=ServiceClass.SIGNALING,
        dscp=DSCP.CS5,
        description="Call setup, SIP, H.323 signaling",
        traffic_type="control",
        tolerance_loss="low",
        tolerance_delay="low",
        tolerance_jitter="medium",
        phb="CS",
        rfc_reference="RFC 2474",
        priority=5,
        weight=5,
        min_bandwidth_percent=2,
        max_bandwidth_percent=5,
        color="#eab308"  # Yellow - signaling
    ),

    ServiceClass.MULTIMEDIA_CONFERENCING: ServiceClassConfig(
        name="Multimedia Conferencing",
        service_class=ServiceClass.MULTIMEDIA_CONFERENCING,
        dscp=DSCP.AF41,
        description="Video conferencing (variable rate, real-time)",
        traffic_type="real-time",
        tolerance_loss="low",
        tolerance_delay="very low",
        tolerance_jitter="low",
        phb="AF",
        rfc_reference="RFC 2597",
        priority=4,
        weight=15,
        min_bandwidth_percent=10,
        max_bandwidth_percent=40,
        color="#8b5cf6"  # Purple - video
    ),

    ServiceClass.REALTIME_INTERACTIVE: ServiceClassConfig(
        name="Real-Time Interactive",
        service_class=ServiceClass.REALTIME_INTERACTIVE,
        dscp=DSCP.CS4,
        description="Interactive video, gaming",
        traffic_type="real-time",
        tolerance_loss="low",
        tolerance_delay="very low",
        tolerance_jitter="low",
        phb="CS",
        rfc_reference="RFC 2474",
        priority=4,
        weight=10,
        min_bandwidth_percent=5,
        max_bandwidth_percent=25,
        color="#ec4899"  # Pink - interactive
    ),

    ServiceClass.MULTIMEDIA_STREAMING: ServiceClassConfig(
        name="Multimedia Streaming",
        service_class=ServiceClass.MULTIMEDIA_STREAMING,
        dscp=DSCP.AF31,
        description="Video/audio streaming (buffered)",
        traffic_type="elastic",
        tolerance_loss="low",
        tolerance_delay="medium",
        tolerance_jitter="high",
        phb="AF",
        rfc_reference="RFC 2597",
        priority=3,
        weight=15,
        min_bandwidth_percent=10,
        max_bandwidth_percent=50,
        color="#06b6d4"  # Cyan - streaming
    ),

    ServiceClass.BROADCAST_VIDEO: ServiceClassConfig(
        name="Broadcast Video",
        service_class=ServiceClass.BROADCAST_VIDEO,
        dscp=DSCP.CS3,
        description="IPTV, broadcast video",
        traffic_type="real-time",
        tolerance_loss="very low",
        tolerance_delay="medium",
        tolerance_jitter="low",
        phb="CS",
        rfc_reference="RFC 2474",
        priority=3,
        weight=20,
        min_bandwidth_percent=15,
        max_bandwidth_percent=50,
        color="#3b82f6"  # Blue - broadcast
    ),

    ServiceClass.LOW_LATENCY_DATA: ServiceClassConfig(
        name="Low-Latency Data",
        service_class=ServiceClass.LOW_LATENCY_DATA,
        dscp=DSCP.AF21,
        description="Interactive applications, transactions, web",
        traffic_type="elastic",
        tolerance_loss="low",
        tolerance_delay="low",
        tolerance_jitter="high",
        phb="AF",
        rfc_reference="RFC 2597",
        priority=2,
        weight=20,
        min_bandwidth_percent=10,
        max_bandwidth_percent=60,
        color="#f97316"  # Orange - interactive data
    ),

    ServiceClass.OAM: ServiceClassConfig(
        name="OAM (Operations & Management)",
        service_class=ServiceClass.OAM,
        dscp=DSCP.CS2,
        description="Network monitoring, SNMP, syslog, NTP",
        traffic_type="control",
        tolerance_loss="low",
        tolerance_delay="medium",
        tolerance_jitter="high",
        phb="CS",
        rfc_reference="RFC 2474",
        priority=2,
        weight=5,
        min_bandwidth_percent=1,
        max_bandwidth_percent=5,
        color="#64748b"  # Slate - OAM
    ),

    ServiceClass.HIGH_THROUGHPUT_DATA: ServiceClassConfig(
        name="High-Throughput Data",
        service_class=ServiceClass.HIGH_THROUGHPUT_DATA,
        dscp=DSCP.AF11,
        description="Bulk transfers, backups, email",
        traffic_type="elastic",
        tolerance_loss="low",
        tolerance_delay="high",
        tolerance_jitter="high",
        phb="AF",
        rfc_reference="RFC 2597",
        priority=1,
        weight=15,
        min_bandwidth_percent=5,
        max_bandwidth_percent=80,
        color="#14b8a6"  # Teal - bulk
    ),

    ServiceClass.STANDARD: ServiceClassConfig(
        name="Standard (Best Effort)",
        service_class=ServiceClass.STANDARD,
        dscp=DSCP.CS0,
        description="Default traffic, web browsing, general data",
        traffic_type="best-effort",
        tolerance_loss="medium",
        tolerance_delay="high",
        tolerance_jitter="high",
        phb="BE",
        rfc_reference="RFC 2474",
        priority=0,
        weight=10,
        min_bandwidth_percent=0,
        max_bandwidth_percent=100,
        color="#6b7280"  # Gray - default
    ),

    ServiceClass.LOW_PRIORITY: ServiceClassConfig(
        name="Low Priority (Scavenger)",
        service_class=ServiceClass.LOW_PRIORITY,
        dscp=DSCP.CS1,
        description="Background tasks, P2P, non-critical bulk",
        traffic_type="best-effort",
        tolerance_loss="high",
        tolerance_delay="high",
        tolerance_jitter="high",
        phb="CS",
        rfc_reference="RFC 3662",
        priority=0,
        weight=1,
        min_bandwidth_percent=0,
        max_bandwidth_percent=25,
        color="#9ca3af"  # Light gray - scavenger
    ),
}


@dataclass
class ClassificationRule:
    """Rule for classifying traffic into service classes"""
    id: str
    name: str
    service_class: ServiceClass
    dscp: DSCP

    # Match criteria (all optional, combined with AND)
    src_ip: Optional[str] = None  # CIDR or IP
    dst_ip: Optional[str] = None
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    protocol: Optional[str] = None  # tcp, udp, icmp
    application: Optional[str] = None  # app name

    # Match on existing DSCP (for trust)
    match_dscp: Optional[DSCP] = None

    # Action
    action: str = "mark"  # mark, police, shape
    police_rate: Optional[int] = None  # kbps
    police_burst: Optional[int] = None  # bytes

    enabled: bool = True
    hit_count: int = 0

    def matches(self, packet: Dict[str, Any]) -> bool:
        """Check if packet matches this rule"""
        if not self.enabled:
            return False

        if self.src_ip and packet.get('src_ip') != self.src_ip:
            return False
        if self.dst_ip and packet.get('dst_ip') != self.dst_ip:
            return False
        if self.src_port and packet.get('src_port') != self.src_port:
            return False
        if self.dst_port and packet.get('dst_port') != self.dst_port:
            return False
        if self.protocol and packet.get('protocol') != self.protocol:
            return False
        if self.match_dscp and packet.get('dscp') != self.match_dscp.value:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "service_class": self.service_class.value,
            "dscp": self.dscp.name,
            "dscp_value": self.dscp.value,
            "match": {
                "src_ip": self.src_ip,
                "dst_ip": self.dst_ip,
                "src_port": self.src_port,
                "dst_port": self.dst_port,
                "protocol": self.protocol,
                "application": self.application,
                "dscp": self.match_dscp.name if self.match_dscp else None
            },
            "action": self.action,
            "police": {
                "rate_kbps": self.police_rate,
                "burst_bytes": self.police_burst
            } if self.police_rate else None,
            "enabled": self.enabled,
            "hit_count": self.hit_count
        }


@dataclass
class QueueStatistics:
    """Statistics for a QoS queue"""
    service_class: ServiceClass
    packets_in: int = 0
    packets_out: int = 0
    packets_dropped: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    bytes_dropped: int = 0
    current_depth: int = 0
    max_depth: int = 0
    avg_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_class": self.service_class.value,
            "packets": {
                "in": self.packets_in,
                "out": self.packets_out,
                "dropped": self.packets_dropped
            },
            "bytes": {
                "in": self.bytes_in,
                "out": self.bytes_out,
                "dropped": self.bytes_dropped
            },
            "queue": {
                "current_depth": self.current_depth,
                "max_depth": self.max_depth
            },
            "latency_ms": self.avg_latency_ms
        }


@dataclass
class InterfaceQoSPolicy:
    """QoS policy applied to an interface"""
    interface: str
    direction: str  # "ingress", "egress", "both"
    policy_name: str
    enabled: bool = True
    trust_dscp: bool = True  # Trust incoming DSCP markings
    default_class: ServiceClass = ServiceClass.STANDARD

    # Per-class statistics
    class_stats: Dict[ServiceClass, QueueStatistics] = field(default_factory=dict)

    # Classification rules (ordered by priority)
    rules: List[ClassificationRule] = field(default_factory=list)

    # Timestamps
    applied_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface": self.interface,
            "direction": self.direction,
            "policy_name": self.policy_name,
            "enabled": self.enabled,
            "trust_dscp": self.trust_dscp,
            "default_class": self.default_class.value,
            "rules": [r.to_dict() for r in self.rules],
            "statistics": {sc.value: stats.to_dict() for sc, stats in self.class_stats.items()},
            "applied_at": self.applied_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }


class QoSManager:
    """
    Manages QoS policies across all agent interfaces.

    Implements RFC 4594 DiffServ service classes with:
    - Traffic classification
    - DSCP marking (egress)
    - DSCP trust (ingress)
    - Queue management
    - Statistics collection

    End-to-End QoS:
    - Egress: Mark outgoing packets with appropriate DSCP based on classification
    - Ingress: Trust incoming DSCP markings from other agents
    - Each agent marks at source, all agents respect markings hop-by-hop
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.enabled = True  # Always enabled by default

        # Service class configurations (RFC 4594)
        self.service_classes = RFC4594_SERVICE_CLASSES.copy()

        # Per-interface policies
        self.interface_policies: Dict[str, InterfaceQoSPolicy] = {}

        # Global classification rules
        self.global_rules: List[ClassificationRule] = []

        # Default rules based on well-known ports
        self._init_default_rules()

        # Statistics
        self.total_classified = 0
        self.total_marked = 0
        self.total_trusted = 0  # Packets where we trusted incoming DSCP

        # Egress marking state - tracks what DSCP we're marking on each interface
        self.egress_marking: Dict[str, Dict[str, int]] = {}  # interface -> {service_class -> packet_count}

        # Ingress trust state - tracks what DSCP we've received and trusted
        self.ingress_trusted: Dict[str, Dict[int, int]] = {}  # interface -> {dscp_value -> packet_count}

        logger.info(f"[QoS] Manager initialized for agent {agent_id} (always enabled, marking egress, trusting ingress)")

    def _init_default_rules(self):
        """Initialize default classification rules based on RFC 4594 recommendations"""

        # Network Control - OSPF, BGP
        self.global_rules.append(ClassificationRule(
            id="nc-ospf",
            name="OSPF Routing",
            service_class=ServiceClass.NETWORK_CONTROL,
            dscp=DSCP.CS6,
            protocol="ospf"
        ))
        self.global_rules.append(ClassificationRule(
            id="nc-bgp",
            name="BGP Routing",
            service_class=ServiceClass.NETWORK_CONTROL,
            dscp=DSCP.CS6,
            protocol="tcp",
            dst_port=179
        ))

        # Telephony - RTP voice
        self.global_rules.append(ClassificationRule(
            id="voice-rtp",
            name="VoIP RTP",
            service_class=ServiceClass.TELEPHONY,
            dscp=DSCP.EF,
            protocol="udp",
            dst_port=5004  # RTP
        ))

        # Signaling - SIP
        self.global_rules.append(ClassificationRule(
            id="sig-sip",
            name="SIP Signaling",
            service_class=ServiceClass.SIGNALING,
            dscp=DSCP.CS5,
            protocol="udp",
            dst_port=5060
        ))
        self.global_rules.append(ClassificationRule(
            id="sig-sip-tls",
            name="SIP-TLS Signaling",
            service_class=ServiceClass.SIGNALING,
            dscp=DSCP.CS5,
            protocol="tcp",
            dst_port=5061
        ))

        # Multimedia Conferencing
        self.global_rules.append(ClassificationRule(
            id="conf-webrtc",
            name="WebRTC Conferencing",
            service_class=ServiceClass.MULTIMEDIA_CONFERENCING,
            dscp=DSCP.AF41,
            protocol="udp",
            dst_port=3478  # STUN/TURN
        ))

        # Streaming
        self.global_rules.append(ClassificationRule(
            id="stream-rtsp",
            name="RTSP Streaming",
            service_class=ServiceClass.MULTIMEDIA_STREAMING,
            dscp=DSCP.AF31,
            protocol="tcp",
            dst_port=554
        ))

        # Low-Latency Data - Interactive
        self.global_rules.append(ClassificationRule(
            id="lld-ssh",
            name="SSH Interactive",
            service_class=ServiceClass.LOW_LATENCY_DATA,
            dscp=DSCP.AF21,
            protocol="tcp",
            dst_port=22
        ))
        self.global_rules.append(ClassificationRule(
            id="lld-dns",
            name="DNS Queries",
            service_class=ServiceClass.LOW_LATENCY_DATA,
            dscp=DSCP.AF21,
            protocol="udp",
            dst_port=53
        ))

        # OAM
        self.global_rules.append(ClassificationRule(
            id="oam-snmp",
            name="SNMP Monitoring",
            service_class=ServiceClass.OAM,
            dscp=DSCP.CS2,
            protocol="udp",
            dst_port=161
        ))
        self.global_rules.append(ClassificationRule(
            id="oam-ntp",
            name="NTP Time Sync",
            service_class=ServiceClass.OAM,
            dscp=DSCP.CS2,
            protocol="udp",
            dst_port=123
        ))
        self.global_rules.append(ClassificationRule(
            id="oam-syslog",
            name="Syslog",
            service_class=ServiceClass.OAM,
            dscp=DSCP.CS2,
            protocol="udp",
            dst_port=514
        ))

        # High-Throughput - FTP, backups
        self.global_rules.append(ClassificationRule(
            id="htd-ftp",
            name="FTP Bulk Transfer",
            service_class=ServiceClass.HIGH_THROUGHPUT_DATA,
            dscp=DSCP.AF11,
            protocol="tcp",
            dst_port=21
        ))

        # Low Priority - P2P
        self.global_rules.append(ClassificationRule(
            id="lp-bittorrent",
            name="BitTorrent",
            service_class=ServiceClass.LOW_PRIORITY,
            dscp=DSCP.CS1,
            protocol="tcp",
            dst_port=6881
        ))

        logger.info(f"[QoS] Initialized {len(self.global_rules)} default classification rules")

    def enable(self):
        """Enable QoS processing"""
        self.enabled = True
        logger.info(f"[QoS] Enabled for agent {self.agent_id}")

    def disable(self):
        """Disable QoS processing"""
        self.enabled = False
        logger.info(f"[QoS] Disabled for agent {self.agent_id}")

    def apply_policy_to_interface(
        self,
        interface: str,
        policy_name: str = "rfc4594-default",
        direction: str = "both",
        trust_dscp: bool = True
    ) -> InterfaceQoSPolicy:
        """
        Apply QoS policy to an interface.

        Args:
            interface: Interface name (e.g., "eth0")
            policy_name: Policy name for reference
            direction: "ingress", "egress", or "both"
            trust_dscp: Whether to trust incoming DSCP markings

        Returns:
            Applied policy configuration
        """
        policy = InterfaceQoSPolicy(
            interface=interface,
            direction=direction,
            policy_name=policy_name,
            trust_dscp=trust_dscp,
            rules=self.global_rules.copy()
        )

        # Initialize per-class statistics
        for sc in self.service_classes:
            policy.class_stats[sc] = QueueStatistics(service_class=sc)

        self.interface_policies[interface] = policy
        logger.info(f"[QoS] Applied policy '{policy_name}' to {interface} ({direction})")

        return policy

    def apply_to_all_interfaces(self, interfaces: List[str]) -> Dict[str, InterfaceQoSPolicy]:
        """Apply RFC 4594 QoS policy to all interfaces"""
        results = {}
        for iface in interfaces:
            results[iface] = self.apply_policy_to_interface(iface)

        self.enable()
        logger.info(f"[QoS] Applied policy to {len(interfaces)} interfaces")
        return results

    def classify_packet(self, packet: Dict[str, Any], interface: str) -> Tuple[ServiceClass, DSCP]:
        """
        Classify a packet and determine its service class and DSCP marking.

        Args:
            packet: Packet metadata (src_ip, dst_ip, ports, protocol, etc.)
            interface: Interface the packet arrived on

        Returns:
            Tuple of (ServiceClass, DSCP marking)
        """
        if not self.enabled:
            return ServiceClass.STANDARD, DSCP.CS0

        policy = self.interface_policies.get(interface)
        if not policy or not policy.enabled:
            return ServiceClass.STANDARD, DSCP.CS0

        # If trust DSCP is enabled and packet has DSCP, use it
        if policy.trust_dscp and 'dscp' in packet:
            dscp_val = packet['dscp']
            for sc, config in self.service_classes.items():
                if config.dscp.value == dscp_val:
                    self.total_classified += 1
                    return sc, config.dscp

        # Apply classification rules
        for rule in policy.rules:
            if rule.matches(packet):
                rule.hit_count += 1
                self.total_classified += 1
                self.total_marked += 1

                # Update statistics
                if rule.service_class in policy.class_stats:
                    policy.class_stats[rule.service_class].packets_in += 1
                    policy.class_stats[rule.service_class].bytes_in += packet.get('length', 0)

                return rule.service_class, rule.dscp

        # Default classification
        return policy.default_class, self.service_classes[policy.default_class].dscp

    # =========================================================================
    # EGRESS MARKING - Mark outgoing packets with DSCP at the source
    # =========================================================================

    def mark_egress(self, service_class: ServiceClass, interface: str = "eth0") -> int:
        """
        Mark an egress packet with the appropriate DSCP value.
        Called when sending a packet to get the DSCP/TOS value to set.

        Args:
            service_class: The service class for this packet
            interface: Outgoing interface

        Returns:
            TOS byte value to set on the IP header (DSCP << 2)
        """
        if not self.enabled:
            return 0

        config = self.service_classes.get(service_class)
        if not config:
            return 0

        dscp = config.dscp
        tos_byte = dscp.tos_byte

        # Track egress marking stats
        if interface not in self.egress_marking:
            self.egress_marking[interface] = {}
        sc_name = service_class.value
        self.egress_marking[interface][sc_name] = self.egress_marking[interface].get(sc_name, 0) + 1

        self.total_marked += 1

        logger.debug(f"[QoS] Marking egress on {interface}: {service_class.value} -> DSCP {dscp.name} (TOS={tos_byte})")

        return tos_byte

    def get_dscp_for_protocol(self, protocol: str) -> Tuple[DSCP, int]:
        """
        Get the DSCP value and TOS byte for a protocol.
        Use this when sending protocol messages to mark them appropriately.

        Args:
            protocol: Protocol name (ospf, bgp, isis, ldp, lldp, bfd, etc.)

        Returns:
            Tuple of (DSCP enum, TOS byte value)
        """
        # Map protocols to service classes per RFC 4594
        protocol_map = {
            # Network Control - CS6 (DSCP 48)
            'ospf': ServiceClass.NETWORK_CONTROL,
            'ospfv3': ServiceClass.NETWORK_CONTROL,
            'bgp': ServiceClass.NETWORK_CONTROL,
            'isis': ServiceClass.NETWORK_CONTROL,
            'ldp': ServiceClass.NETWORK_CONTROL,
            'rsvp': ServiceClass.NETWORK_CONTROL,
            'bfd': ServiceClass.NETWORK_CONTROL,
            'pim': ServiceClass.NETWORK_CONTROL,
            'vrrp': ServiceClass.NETWORK_CONTROL,
            'hsrp': ServiceClass.NETWORK_CONTROL,

            # Signaling - CS5 (DSCP 40)
            'sip': ServiceClass.SIGNALING,
            'h323': ServiceClass.SIGNALING,

            # OAM - CS2 (DSCP 16)
            'lldp': ServiceClass.OAM,
            'snmp': ServiceClass.OAM,
            'ntp': ServiceClass.OAM,
            'syslog': ServiceClass.OAM,
            'icmp': ServiceClass.OAM,

            # Low-Latency Data - AF21 (DSCP 18)
            'ssh': ServiceClass.LOW_LATENCY_DATA,
            'dns': ServiceClass.LOW_LATENCY_DATA,
            'http': ServiceClass.LOW_LATENCY_DATA,
            'https': ServiceClass.LOW_LATENCY_DATA,
        }

        service_class = protocol_map.get(protocol.lower(), ServiceClass.STANDARD)
        config = self.service_classes[service_class]

        return config.dscp, config.dscp.tos_byte

    # =========================================================================
    # INGRESS TRUST - Respect DSCP markings from other agents
    # =========================================================================

    def trust_ingress(self, dscp_value: int, interface: str = "eth0") -> Tuple[ServiceClass, bool]:
        """
        Process an ingress packet and trust its DSCP marking.
        Called when receiving a packet to determine how to handle it.

        Args:
            dscp_value: DSCP value from the incoming packet's IP header
            interface: Incoming interface

        Returns:
            Tuple of (ServiceClass, whether DSCP was trusted)
        """
        if not self.enabled:
            return ServiceClass.STANDARD, False

        # Auto-create interface policy if it doesn't exist (always trust DSCP by default)
        policy = self.interface_policies.get(interface)
        if not policy:
            # Create default policy that trusts DSCP
            policy = self.apply_to_interface(interface)
            logger.info(f"[QoS] Auto-created policy for interface {interface} with DSCP trust enabled")

        if not policy.trust_dscp:
            return ServiceClass.STANDARD, False

        # Track ingress trust stats
        if interface not in self.ingress_trusted:
            self.ingress_trusted[interface] = {}
        self.ingress_trusted[interface][dscp_value] = self.ingress_trusted[interface].get(dscp_value, 0) + 1

        # Find matching service class
        for sc, config in self.service_classes.items():
            if config.dscp.value == dscp_value:
                self.total_trusted += 1
                self.total_classified += 1

                # Update per-class stats
                if policy and sc in policy.class_stats:
                    policy.class_stats[sc].packets_in += 1

                logger.debug(f"[QoS] Trusting ingress on {interface}: DSCP {dscp_value} -> {sc.value}")
                return sc, True

        # Unknown DSCP, treat as best effort
        return ServiceClass.STANDARD, False

    def trust_ingress_protocol(self, protocol: str, interface: str = "eth0", packet_count: int = 1) -> Tuple[ServiceClass, bool]:
        """
        Trust ingress traffic for a known protocol (TCP-based protocols like BGP).
        Use this when DSCP value cannot be extracted from the wire (e.g., TCP streams).

        This assumes the peer is using proper DSCP marking and we trust based on protocol.

        Args:
            protocol: Protocol name (bgp, ospf, etc.)
            interface: Incoming interface
            packet_count: Number of packets to record

        Returns:
            Tuple of (ServiceClass, whether trusted)
        """
        if not self.enabled:
            return ServiceClass.STANDARD, False

        # Get expected DSCP for this protocol
        dscp, tos_byte = self.get_dscp_for_protocol(protocol)

        # Trust as if we received the expected DSCP
        for _ in range(packet_count):
            self.trust_ingress(dscp.value, interface)

        # Find service class and increment the matching rule's hit_count
        matched_sc = ServiceClass.STANDARD
        for sc, config in self.service_classes.items():
            if config.dscp == dscp:
                matched_sc = sc
                break

        # Also increment the matching classification rule's hit_count
        # This ensures the dashboard shows correct counts for protocol-based traffic
        protocol_lower = protocol.lower()
        for rule in self.global_rules:
            # Match by protocol name (ospf, bgp) or by service class
            rule_proto = (rule.protocol or "").lower()
            rule_name = (rule.name or "").lower()
            if (protocol_lower in rule_name or
                protocol_lower == rule_proto or
                (protocol_lower == "bgp" and rule.dst_port == 179)):
                rule.hit_count += packet_count
                logger.debug(f"[QoS] Incremented rule '{rule.name}' hit_count by {packet_count} for {protocol}")
                break

        return matched_sc, matched_sc != ServiceClass.STANDARD

    def get_tos_from_ip_header(self, ip_header: bytes) -> int:
        """
        Extract DSCP value from IP header TOS byte.

        Args:
            ip_header: Raw IP header bytes (at least 1 byte for IPv4 TOS)

        Returns:
            DSCP value (0-63)
        """
        if len(ip_header) < 2:
            return 0

        # IPv4: TOS is byte 1, DSCP is top 6 bits
        tos_byte = ip_header[1]
        dscp = tos_byte >> 2

        return dscp

    def set_socket_tos(self, sock, protocol: str) -> bool:
        """
        Set the TOS/DSCP on a socket for a given protocol.
        Call this before sending to ensure packets are marked.

        Args:
            sock: Socket object
            protocol: Protocol name (ospf, bgp, etc.)

        Returns:
            True if TOS was set successfully
        """
        import socket

        dscp, tos_byte = self.get_dscp_for_protocol(protocol)

        try:
            # Set IP_TOS for IPv4
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos_byte)
            logger.debug(f"[QoS] Set socket TOS={tos_byte} (DSCP {dscp.name}) for {protocol}")
            return True
        except Exception as e:
            logger.warning(f"[QoS] Failed to set socket TOS for {protocol}: {e}")

        try:
            # Try IPv6 traffic class
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_TCLASS, tos_byte)
            logger.debug(f"[QoS] Set socket TCLASS={tos_byte} (DSCP {dscp.name}) for {protocol}")
            return True
        except:
            pass

        return False

    def get_marking_stats(self) -> Dict[str, Any]:
        """Get egress marking and ingress trust statistics."""
        return {
            "egress_marking": self.egress_marking,
            "ingress_trusted": self.ingress_trusted,
            "total_marked": self.total_marked,
            "total_trusted": self.total_trusted
        }

    def get_service_class_info(self, service_class: ServiceClass) -> Optional[ServiceClassConfig]:
        """Get configuration for a service class"""
        return self.service_classes.get(service_class)

    def get_all_service_classes(self) -> List[Dict[str, Any]]:
        """Get all service class configurations"""
        return [config.to_dict() for config in self.service_classes.values()]

    def get_interface_policy(self, interface: str) -> Optional[Dict[str, Any]]:
        """Get QoS policy for an interface"""
        policy = self.interface_policies.get(interface)
        return policy.to_dict() if policy else None

    def get_all_policies(self) -> Dict[str, Dict[str, Any]]:
        """Get all interface policies"""
        return {iface: policy.to_dict() for iface, policy in self.interface_policies.items()}

    def get_classification_rules(self) -> List[Dict[str, Any]]:
        """Get all classification rules"""
        return [rule.to_dict() for rule in self.global_rules]

    def add_classification_rule(self, rule: ClassificationRule):
        """Add a new classification rule"""
        self.global_rules.append(rule)
        # Add to all interface policies
        for policy in self.interface_policies.values():
            policy.rules.append(rule)
        logger.info(f"[QoS] Added rule: {rule.name}")

    def record_packet(self, service_class: ServiceClass, direction: str = "out",
                       bytes_count: int = 64, interface: str = "eth0"):
        """
        Record a packet for QoS statistics.

        For EGRESS (direction="out"):
        - Packet is classified and MARKED with appropriate DSCP
        - This agent is the source, marking for end-to-end QoS

        For INGRESS (direction="in"):
        - Packet's existing DSCP is TRUSTED
        - The marking was done by the source agent

        Args:
            service_class: The service class for this packet
            direction: "in" (trust ingress) or "out" (mark egress)
            bytes_count: Packet size in bytes
            interface: Interface name
        """
        if not self.enabled:
            return

        self.total_classified += 1

        # Get DSCP for this service class
        config = self.service_classes.get(service_class)
        dscp = config.dscp if config else DSCP.CS0

        if direction == "out":
            # EGRESS: We are marking this packet
            self.total_marked += 1

            # Track egress marking per interface
            if interface not in self.egress_marking:
                self.egress_marking[interface] = {}
            sc_name = service_class.value
            self.egress_marking[interface][sc_name] = self.egress_marking[interface].get(sc_name, 0) + 1

        else:
            # INGRESS: We are trusting this packet's marking
            self.total_trusted += 1

            # Track ingress trust per interface
            if interface not in self.ingress_trusted:
                self.ingress_trusted[interface] = {}
            dscp_val = dscp.value
            self.ingress_trusted[interface][dscp_val] = self.ingress_trusted[interface].get(dscp_val, 0) + 1

        # Update rule hit counts
        for rule in self.global_rules:
            if rule.service_class == service_class:
                rule.hit_count += 1
                break

        # Update per-interface stats
        policy = self.interface_policies.get(interface)
        if policy and service_class in policy.class_stats:
            stats = policy.class_stats[service_class]
            if direction == "in":
                stats.packets_in += 1
                stats.bytes_in += bytes_count
            else:
                stats.packets_out += 1
                stats.bytes_out += bytes_count

    def record_ospf_packet(self, packet_type: str, bytes_count: int = 64, interface: str = "eth0"):
        """Record OSPF packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_bgp_packet(self, packet_type: str, bytes_count: int = 64, interface: str = "eth0"):
        """Record BGP packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_dns_packet(self, bytes_count: int = 64, interface: str = "eth0"):
        """Record DNS packet (Low-Latency Data - AF21)"""
        self.record_packet(ServiceClass.LOW_LATENCY_DATA, "out", bytes_count, interface)

    def record_ssh_packet(self, bytes_count: int = 64, interface: str = "eth0"):
        """Record SSH packet (Low-Latency Data - AF21)"""
        self.record_packet(ServiceClass.LOW_LATENCY_DATA, "out", bytes_count, interface)

    def record_snmp_packet(self, bytes_count: int = 64, interface: str = "eth0"):
        """Record SNMP/OAM packet (OAM - CS2)"""
        self.record_packet(ServiceClass.OAM, "out", bytes_count, interface)

    def record_default_packet(self, bytes_count: int = 64, interface: str = "eth0"):
        """Record default/best-effort packet (Standard - CS0)"""
        self.record_packet(ServiceClass.STANDARD, "out", bytes_count, interface)

    def record_http_packet(self, bytes_count: int = 500, interface: str = "eth0"):
        """Record HTTP/Web packet (Low-Latency Data - AF21)"""
        self.record_packet(ServiceClass.LOW_LATENCY_DATA, "out", bytes_count, interface)

    def record_bulk_packet(self, bytes_count: int = 1500, interface: str = "eth0"):
        """Record bulk transfer packet (High-Throughput - AF11)"""
        self.record_packet(ServiceClass.HIGH_THROUGHPUT_DATA, "out", bytes_count, interface)

    def record_voice_packet(self, bytes_count: int = 160, interface: str = "eth0"):
        """Record VoIP/voice packet (Telephony - EF)"""
        self.record_packet(ServiceClass.TELEPHONY, "out", bytes_count, interface)

    def record_video_packet(self, bytes_count: int = 1200, interface: str = "eth0"):
        """Record video conferencing packet (Multimedia Conferencing - AF41)"""
        self.record_packet(ServiceClass.MULTIMEDIA_CONFERENCING, "out", bytes_count, interface)

    def record_streaming_packet(self, bytes_count: int = 1400, interface: str = "eth0"):
        """Record media streaming packet (Multimedia Streaming - AF31)"""
        self.record_packet(ServiceClass.MULTIMEDIA_STREAMING, "out", bytes_count, interface)

    # =========================================================================
    # ALL PROTOCOL SUPPORT - Network Control (CS6)
    # =========================================================================

    def record_isis_packet(self, packet_type: str = "hello", bytes_count: int = 64, interface: str = "eth0"):
        """Record IS-IS packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_ospfv3_packet(self, packet_type: str = "hello", bytes_count: int = 64, interface: str = "eth0"):
        """Record OSPFv3 packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_ldp_packet(self, packet_type: str = "hello", bytes_count: int = 64, interface: str = "eth0"):
        """Record LDP packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_rsvp_packet(self, packet_type: str = "path", bytes_count: int = 64, interface: str = "eth0"):
        """Record RSVP-TE packet (Network Control - CS6)"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_bfd_packet(self, bytes_count: int = 24, interface: str = "eth0"):
        """Record BFD packet (Network Control - CS6) - small keepalive packets"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_lldp_packet(self, bytes_count: int = 128, interface: str = "eth0"):
        """Record LLDP packet (OAM - CS2) - discovery protocol"""
        self.record_packet(ServiceClass.OAM, "out", bytes_count, interface)

    def record_pim_packet(self, packet_type: str = "hello", bytes_count: int = 64, interface: str = "eth0"):
        """Record PIM packet (Network Control - CS6) - multicast routing"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    def record_vrrp_packet(self, bytes_count: int = 40, interface: str = "eth0"):
        """Record VRRP packet (Network Control - CS6) - FHRP"""
        self.record_packet(ServiceClass.NETWORK_CONTROL, "out", bytes_count, interface)

    # =========================================================================
    # Protocol Stats Collection - Collects from ALL protocol sources
    # =========================================================================

    def collect_all_protocol_stats(self, asi_app) -> Dict[str, int]:
        """
        Collect statistics from ALL protocols in the stack.
        This should be called periodically by the metrics collector.

        Args:
            asi_app: WontYouBeMyNeighbor instance with protocol references

        Returns:
            Dictionary with total packets per protocol
        """
        stats = {
            'ospf': 0,
            'ospfv3': 0,
            'bgp': 0,
            'isis': 0,
            'ldp': 0,
            'lldp': 0,
            'bfd': 0
        }

        # OSPF stats
        if hasattr(asi_app, 'ospf_interface') and asi_app.ospf_interface:
            ospf = asi_app.ospf_interface
            if hasattr(ospf, 'stats'):
                ospf_stats = ospf.stats
                stats['ospf'] = sum([
                    ospf_stats.get('hello_sent', 0), ospf_stats.get('hello_recv', 0),
                    ospf_stats.get('dbd_sent', 0), ospf_stats.get('dbd_recv', 0),
                    ospf_stats.get('lsu_sent', 0), ospf_stats.get('lsu_recv', 0),
                    ospf_stats.get('lsr_sent', 0), ospf_stats.get('lsr_recv', 0),
                    ospf_stats.get('lsack_sent', 0), ospf_stats.get('lsack_recv', 0)
                ])

        # OSPFv3 stats
        if hasattr(asi_app, 'ospfv3_speaker') and asi_app.ospfv3_speaker:
            ospfv3 = asi_app.ospfv3_speaker
            if hasattr(ospfv3, 'stats'):
                ospfv3_stats = ospfv3.stats
                stats['ospfv3'] = sum([
                    ospfv3_stats.get('hello_sent', 0), ospfv3_stats.get('hello_recv', 0),
                    ospfv3_stats.get('dd_sent', 0), ospfv3_stats.get('dd_recv', 0),
                    ospfv3_stats.get('lsu_sent', 0), ospfv3_stats.get('lsu_recv', 0)
                ])
            # Also check interfaces
            elif hasattr(ospfv3, 'interfaces'):
                for iface in ospfv3.interfaces.values():
                    if hasattr(iface, 'stats'):
                        stats['ospfv3'] += iface.stats.get('hello_sent', 0)
                        stats['ospfv3'] += iface.stats.get('hello_received', 0)

        # BGP stats
        if hasattr(asi_app, 'bgp_speaker') and asi_app.bgp_speaker:
            bgp = asi_app.bgp_speaker
            if hasattr(bgp, 'stats'):
                bgp_stats = bgp.stats
                stats['bgp'] = sum([
                    bgp_stats.get('open_sent', 0), bgp_stats.get('open_recv', 0),
                    bgp_stats.get('update_sent', 0), bgp_stats.get('update_recv', 0),
                    bgp_stats.get('keepalive_sent', 0), bgp_stats.get('keepalive_recv', 0),
                    bgp_stats.get('notification_sent', 0), bgp_stats.get('notification_recv', 0)
                ])

        # IS-IS stats (if available)
        if hasattr(asi_app, 'isis_speaker') and asi_app.isis_speaker:
            isis = asi_app.isis_speaker
            if hasattr(isis, 'stats'):
                isis_stats = isis.stats
                stats['isis'] = sum([
                    isis_stats.get('iih_sent', 0), isis_stats.get('iih_recv', 0),
                    isis_stats.get('lsp_sent', 0), isis_stats.get('lsp_recv', 0),
                    isis_stats.get('csnp_sent', 0), isis_stats.get('csnp_recv', 0),
                    isis_stats.get('psnp_sent', 0), isis_stats.get('psnp_recv', 0)
                ])

        # LDP stats (if available)
        if hasattr(asi_app, 'ldp_speaker') and asi_app.ldp_speaker:
            ldp = asi_app.ldp_speaker
            if hasattr(ldp, 'stats'):
                ldp_stats = ldp.stats
                stats['ldp'] = sum([
                    ldp_stats.get('hello_sent', 0), ldp_stats.get('hello_recv', 0),
                    ldp_stats.get('init_sent', 0), ldp_stats.get('init_recv', 0),
                    ldp_stats.get('label_sent', 0), ldp_stats.get('label_recv', 0)
                ])

        # LLDP stats (from agentic layer)
        if hasattr(asi_app, 'agentic_bridge') and asi_app.agentic_bridge:
            try:
                from agentic.discovery.lldp import get_lldp_daemon
                lldp = get_lldp_daemon()
                if lldp and hasattr(lldp, 'stats'):
                    lldp_stats = lldp.stats
                    stats['lldp'] = lldp_stats.get('frames_sent', 0) + lldp_stats.get('frames_recv', 0)
            except:
                pass

        return stats

    def update_from_protocol_stats(self, asi_app, interface: str = "eth0"):
        """
        Update QoS counters from ALL protocol statistics.
        Call this periodically to keep QoS in sync with actual protocol activity.

        Args:
            asi_app: WontYouBeMyNeighbor instance
            interface: Default interface for stats
        """
        if not self.enabled:
            return

        # Initialize tracking if needed
        if not hasattr(self, '_last_protocol_stats'):
            self._last_protocol_stats = {
                'ospf': 0, 'ospfv3': 0, 'bgp': 0, 'isis': 0, 'ldp': 0, 'lldp': 0, 'bfd': 0, 'gre': 0
            }

        # Get current stats
        current = self.collect_all_protocol_stats(asi_app)

        # Calculate deltas and record packets
        for protocol, total in current.items():
            last = self._last_protocol_stats.get(protocol, 0)
            delta = total - last

            if delta > 0:
                # Record packets based on protocol type
                for _ in range(int(delta)):
                    if protocol == 'ospf':
                        self.record_ospf_packet("hello", 64, interface)
                    elif protocol == 'ospfv3':
                        self.record_ospfv3_packet("hello", 64, interface)
                    elif protocol == 'bgp':
                        self.record_bgp_packet("keepalive", 64, interface)
                    elif protocol == 'isis':
                        self.record_isis_packet("hello", 64, interface)
                    elif protocol == 'ldp':
                        self.record_ldp_packet("hello", 64, interface)
                    elif protocol == 'lldp':
                        self.record_lldp_packet(128, interface)
                    elif protocol == 'bfd':
                        self.record_bfd_packet(24, interface)
                    elif protocol == 'gre':
                        self.record_generic_packet("gre", 100, interface, dscp=48)

                logger.debug(f"[QoS] Recorded {delta} {protocol.upper()} packets")

            self._last_protocol_stats[protocol] = total

    def get_statistics(self) -> Dict[str, Any]:
        """Get QoS statistics including egress marking and ingress trust"""
        per_class_totals = {}
        for sc in self.service_classes:
            per_class_totals[sc.value] = {
                "packets_in": 0,
                "packets_out": 0,
                "packets_dropped": 0,
                "bytes_in": 0,
                "bytes_out": 0
            }

        for policy in self.interface_policies.values():
            for sc, stats in policy.class_stats.items():
                per_class_totals[sc.value]["packets_in"] += stats.packets_in
                per_class_totals[sc.value]["packets_out"] += stats.packets_out
                per_class_totals[sc.value]["packets_dropped"] += stats.packets_dropped
                per_class_totals[sc.value]["bytes_in"] += stats.bytes_in
                per_class_totals[sc.value]["bytes_out"] += stats.bytes_out

        return {
            "enabled": self.enabled,
            "total_classified": self.total_classified,
            "total_marked": self.total_marked,
            "total_trusted": self.total_trusted,
            "interfaces_with_qos": len(self.interface_policies),
            "classification_rules": len(self.global_rules),
            "per_class": per_class_totals,
            "egress_marking": self.egress_marking,
            "ingress_trusted": self.ingress_trusted
        }

    def get_swim_lanes(self) -> List[Dict[str, Any]]:
        """
        Get swim lane visualization data for QoS classes.

        Returns ordered list of swim lanes from highest to lowest priority.
        """
        lanes = []

        # Sort by priority (descending)
        sorted_classes = sorted(
            self.service_classes.items(),
            key=lambda x: x[1].priority,
            reverse=True
        )

        for sc, config in sorted_classes:
            lanes.append({
                "id": sc.value,
                "name": config.name,
                "dscp": config.dscp.name,
                "dscp_value": config.dscp.value,
                "dscp_binary": config.dscp.binary,
                "priority": config.priority,
                "color": config.color,
                "traffic_type": config.traffic_type,
                "phb": config.phb,
                "bandwidth": {
                    "min": config.min_bandwidth_percent,
                    "max": config.max_bandwidth_percent
                },
                "tolerance": {
                    "loss": config.tolerance_loss,
                    "delay": config.tolerance_delay,
                    "jitter": config.tolerance_jitter
                }
            })

        return lanes


# Singleton manager instances per agent
_qos_managers: Dict[str, QoSManager] = {}


def get_qos_manager(agent_id: str = "local") -> QoSManager:
    """Get or create QoS manager for an agent"""
    if agent_id not in _qos_managers:
        _qos_managers[agent_id] = QoSManager(agent_id)
    return _qos_managers[agent_id]
