"""
RFC MCP Client

Provides integration with the RFC MCP server for IETF RFC standards lookup.
Enables agents to query protocol specifications, understand standard behaviors,
and reference relevant RFCs for network protocols.

Common RFC lookups for network protocols:
- OSPF: RFC 2328 (OSPFv2), RFC 5340 (OSPFv3)
- BGP: RFC 4271 (BGP-4), RFC 4360 (BGP Extended Communities)
- IS-IS: RFC 1195 (IP over IS-IS)
- MPLS: RFC 3031 (Architecture), RFC 3032 (Label Stack)
- LDP: RFC 5036 (LDP Specification)
- VXLAN: RFC 7348 (VXLAN)
- EVPN: RFC 7432 (BGP MPLS-Based EVPN)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime

logger = logging.getLogger("RFC_MCP")


class RFCStatus(Enum):
    """RFC document status"""
    PROPOSED_STANDARD = "proposed_standard"
    DRAFT_STANDARD = "draft_standard"
    INTERNET_STANDARD = "internet_standard"
    BEST_CURRENT_PRACTICE = "bcp"
    INFORMATIONAL = "informational"
    EXPERIMENTAL = "experimental"
    HISTORIC = "historic"
    UNKNOWN = "unknown"


@dataclass
class RFCDocument:
    """
    RFC document metadata and content reference

    Attributes:
        number: RFC number (e.g., 2328)
        title: Document title
        authors: List of authors
        date: Publication date
        status: Document status
        abstract: Document abstract
        keywords: Keywords/topics
        obsoletes: List of RFC numbers this obsoletes
        obsoleted_by: List of RFC numbers that obsolete this
        updates: List of RFC numbers this updates
        updated_by: List of RFC numbers that update this
    """
    number: int
    title: str
    authors: List[str] = field(default_factory=list)
    date: Optional[str] = None
    status: RFCStatus = RFCStatus.UNKNOWN
    abstract: str = ""
    keywords: List[str] = field(default_factory=list)
    obsoletes: List[int] = field(default_factory=list)
    obsoleted_by: List[int] = field(default_factory=list)
    updates: List[int] = field(default_factory=list)
    updated_by: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "authors": self.authors,
            "date": self.date,
            "status": self.status.value,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "obsoletes": self.obsoletes,
            "obsoleted_by": self.obsoleted_by,
            "updates": self.updates,
            "updated_by": self.updated_by,
        }

    @property
    def url(self) -> str:
        """Get the RFC URL"""
        return f"https://www.rfc-editor.org/rfc/rfc{self.number}"

    @property
    def is_current(self) -> bool:
        """Check if RFC is still current (not obsoleted)"""
        return len(self.obsoleted_by) == 0


# Protocol to RFC mapping - primary specifications
PROTOCOL_RFC_MAP: Dict[str, List[int]] = {
    # OSPF
    "ospf": [2328, 5340, 2740, 5838],  # OSPFv2, OSPFv3, OSPF-TE, OSPFv3 AF
    "ospfv2": [2328, 2740],
    "ospfv3": [5340, 5838],

    # BGP
    "bgp": [4271, 4360, 4456, 7911],  # BGP-4, Communities, RR, Add-Path
    "ibgp": [4271, 4456],  # BGP-4, Route Reflection
    "ebgp": [4271, 4360],
    "bgp-evpn": [7432, 8365],  # EVPN, VxLAN-EVPN

    # IS-IS
    "isis": [1195, 5302, 5305, 5308],  # IP/IS-IS, IS-IS Extensions
    "is-is": [1195, 5302, 5305, 5308],

    # MPLS
    "mpls": [3031, 3032, 3270],  # Architecture, Label Stack, DSCP
    "ldp": [5036, 5561, 6388],  # LDP, Cap Extensions, mLDP

    # VXLAN/EVPN
    "vxlan": [7348, 8365],  # VXLAN, VxLAN-EVPN
    "evpn": [7432, 8365, 9136],  # EVPN, VxLAN-EVPN, IP Prefix

    # IP/Routing
    "ipv4": [791, 1918, 4632],  # IPv4, Private Addresses, CIDR
    "ipv6": [8200, 4291],  # IPv6, IPv6 Addressing
    "routing": [1812, 4632],  # Router Requirements, CIDR

    # Services
    "dhcp": [2131, 3315, 8415],  # DHCPv4, DHCPv6, DHCPv6 Failover
    "dns": [1035, 2181, 8499],  # DNS, DNS Clarifications, Terminology

    # BFD (Bidirectional Forwarding Detection)
    "bfd": [5880, 5881, 5882, 5883],  # BFD Base, Single-Hop, Generic App, Multi-Hop
    "bfd-single-hop": [5880, 5881],
    "bfd-multi-hop": [5880, 5883],

    # GRE (Generic Routing Encapsulation)
    "gre": [2784, 2890],  # GRE, Key/Sequence Extensions

    # General
    "snmp": [3411, 3412, 3414],  # SNMP Architecture
    "syslog": [5424, 5426],  # Syslog Protocol
}

# Key RFC summaries (embedded knowledge)
RFC_SUMMARIES: Dict[int, Dict[str, str]] = {
    2328: {
        "title": "OSPF Version 2",
        "summary": "Defines the OSPF Version 2 routing protocol for IPv4 networks. "
                   "OSPF is a link-state routing protocol using Dijkstra's SPF algorithm. "
                   "Key concepts: Areas, LSAs, DR/BDR election, adjacency states, flooding.",
        "key_sections": [
            "Section 4: OSPF Data Structures (areas, interfaces, neighbors, LSDB)",
            "Section 7: LSA Types (Router-LSA, Network-LSA, Summary-LSA, AS-External-LSA)",
            "Section 10: Neighbor State Machine (Down, Init, 2-Way, ExStart, Exchange, Loading, Full)",
            "Section 12: LSA Flooding (sequence numbers, aging, acknowledged flooding)",
            "Section 16: SPF Calculation (Dijkstra algorithm, intra-area routing)",
        ]
    },
    5340: {
        "title": "OSPF for IPv6",
        "summary": "Defines OSPFv3 for IPv6 routing. Major changes from OSPFv2: "
                   "per-link protocol processing, new LSA types, removal of authentication "
                   "(handled by IPsec), interface-based addressing.",
        "key_sections": [
            "Section 2.4: New LSA Types (Link-LSA, Intra-Area-Prefix-LSA)",
            "Section 2.6: Per-link processing vs per-subnet",
            "Section 4: Protocol changes from OSPFv2",
        ]
    },
    4271: {
        "title": "A Border Gateway Protocol 4 (BGP-4)",
        "summary": "Defines BGP-4, the inter-domain routing protocol of the Internet. "
                   "BGP is a path vector protocol using TCP connections between peers. "
                   "Key concepts: AS path, attributes, route selection, policy application.",
        "key_sections": [
            "Section 3: BGP Messages (OPEN, UPDATE, NOTIFICATION, KEEPALIVE)",
            "Section 5: Path Attributes (ORIGIN, AS_PATH, NEXT_HOP, MED, LOCAL_PREF)",
            "Section 8: BGP FSM (Idle, Connect, Active, OpenSent, OpenConfirm, Established)",
            "Section 9.1: Decision Process (route selection algorithm)",
        ]
    },
    4456: {
        "title": "BGP Route Reflection",
        "summary": "Defines route reflection as a method to eliminate the need for "
                   "full mesh iBGP connectivity. Route reflectors advertise routes "
                   "to route reflector clients.",
        "key_sections": [
            "Section 7: Route Reflector Operation",
            "Section 8: Avoiding Routing Information Loops (ORIGINATOR_ID, CLUSTER_LIST)",
        ]
    },
    3031: {
        "title": "Multiprotocol Label Switching Architecture",
        "summary": "Defines the MPLS architecture. MPLS provides a mechanism for "
                   "forwarding packets based on labels rather than IP addresses. "
                   "Key concepts: LSP, FEC, LIB, LFIB.",
        "key_sections": [
            "Section 2.1: Labels and Label Stacks",
            "Section 2.3: Label Switched Paths (LSP)",
            "Section 3: MPLS Operation",
        ]
    },
    5036: {
        "title": "LDP Specification",
        "summary": "Defines the Label Distribution Protocol for distributing MPLS labels. "
                   "LDP establishes LSPs using hello packets and TCP sessions.",
        "key_sections": [
            "Section 2.5: LDP Sessions",
            "Section 2.6: LDP Messages",
            "Section 2.8: Label Distribution and Management",
        ]
    },
    7348: {
        "title": "Virtual eXtensible Local Area Network (VXLAN)",
        "summary": "Defines VXLAN, an overlay network scheme for encapsulating L2 frames "
                   "in UDP packets for transport across L3 networks. Uses 24-bit VNI.",
        "key_sections": [
            "Section 3: VXLAN Frame Format",
            "Section 4: VXLAN Deployment Scenarios",
            "Section 5: VXLAN Segment and VXLAN Gateway",
        ]
    },
    7432: {
        "title": "BGP MPLS-Based Ethernet VPN",
        "summary": "Defines EVPN, a BGP-based control plane for Ethernet VPN services. "
                   "EVPN provides multi-homing, fast convergence, and optimal forwarding.",
        "key_sections": [
            "Section 7: Route Types (Type-1 through Type-5)",
            "Section 8: Multi-homing",
            "Section 9: Designated Forwarder Election",
        ]
    },
    1195: {
        "title": "Use of OSI IS-IS for Routing in TCP/IP and Dual Environments",
        "summary": "Defines integrated IS-IS for routing IP in addition to OSI protocols. "
                   "IS-IS is a link-state protocol like OSPF but uses different PDU formats.",
        "key_sections": [
            "Section 3: IP Reachability TLV",
            "Section 4: Routing with Integrated IS-IS",
        ]
    },
    5880: {
        "title": "Bidirectional Forwarding Detection (BFD)",
        "summary": "Defines BFD, a protocol for rapid detection of connectivity failures between "
                   "adjacent forwarding engines. BFD provides sub-second failure detection independent "
                   "of media, protocol, or routing protocol timers.",
        "key_sections": [
            "Section 4: BFD Control Packet Format",
            "Section 6.8: State Machine (AdminDown, Down, Init, Up)",
            "Section 6.8.6: Packet Reception",
            "Section 6.8.7: Transmitting BFD Control Packets",
        ]
    },
    5881: {
        "title": "Bidirectional Forwarding Detection (BFD) for IPv4 and IPv6 (Single Hop)",
        "summary": "Defines BFD procedures for single IP hop connections. Specifies use of "
                   "UDP port 3784 for control packets. Requires TTL/hop limit of 255 for security.",
        "key_sections": [
            "Section 4: BFD Control Packets",
            "Section 5: TTL/Hop Limit Issues",
        ]
    },
    5882: {
        "title": "Generic Application of Bidirectional Forwarding Detection (BFD)",
        "summary": "Describes how to use BFD with various routing protocols including OSPF, "
                   "IS-IS, BGP, and static routes. Provides guidance on integrating BFD.",
        "key_sections": [
            "Section 4.1: BFD for OSPF",
            "Section 4.2: BFD for IS-IS",
            "Section 4.3: BFD for BGP",
            "Section 4.4: BFD for Static Routes",
        ]
    },
    5883: {
        "title": "Bidirectional Forwarding Detection (BFD) for Multihop Paths",
        "summary": "Extends BFD for paths spanning multiple IP hops, such as EBGP multi-hop "
                   "or MPLS LSP verification. Uses UDP port 4784.",
        "key_sections": [
            "Section 3: Use of the TTL/Hop Limit Field",
            "Section 4: Demultiplexing",
            "Section 5: Encapsulation",
        ]
    },
    2784: {
        "title": "Generic Routing Encapsulation (GRE)",
        "summary": "Defines GRE, a protocol for encapsulating packets of one protocol inside "
                   "packets of another protocol. IP protocol 47. Creates point-to-point tunnels.",
        "key_sections": [
            "Section 2: Structure of a GRE Encapsulated Packet",
            "Section 2.1: GRE Header",
            "Section 3: Protocol Type Field",
        ]
    },
    2890: {
        "title": "Key and Sequence Number Extensions to GRE",
        "summary": "Extends GRE with optional key and sequence number fields. Key provides "
                   "tunnel demultiplexing; sequence numbers enable ordered delivery detection.",
        "key_sections": [
            "Section 2: Extensions to GRE Header",
            "Section 2.1: Key Field",
            "Section 2.2: Sequence Number",
        ]
    },
}


@dataclass
class RFCLookup:
    """Result of an RFC lookup"""
    success: bool
    rfc: Optional[RFCDocument] = None
    error: Optional[str] = None
    summary: Optional[str] = None
    key_sections: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"success": self.success}
        if self.rfc:
            result["rfc"] = self.rfc.to_dict()
        if self.error:
            result["error"] = self.error
        if self.summary:
            result["summary"] = self.summary
        if self.key_sections:
            result["key_sections"] = self.key_sections
        return result


@dataclass
class RFCSearch:
    """Result of an RFC search"""
    success: bool
    query: str
    results: List[RFCDocument] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
        }
        if self.error:
            result["error"] = self.error
        return result


class RFCClient:
    """
    RFC MCP Client

    Provides methods to query and lookup IETF RFCs.
    This client provides both embedded RFC knowledge (for offline use)
    and can be extended to query the RFC MCP server for live data.
    """

    def __init__(self, mcp_url: Optional[str] = None):
        """
        Initialize RFC client

        Args:
            mcp_url: Optional URL to RFC MCP server
        """
        self.mcp_url = mcp_url
        self._cache: Dict[int, RFCDocument] = {}
        self._init_embedded_rfcs()

    def _init_embedded_rfcs(self) -> None:
        """Initialize embedded RFC documents for common protocols"""
        embedded_rfcs = [
            RFCDocument(
                number=2328,
                title="OSPF Version 2",
                authors=["J. Moy"],
                date="April 1998",
                status=RFCStatus.INTERNET_STANDARD,
                abstract="This memo documents version 2 of the OSPF protocol. "
                         "OSPF is a link-state routing protocol.",
                keywords=["ospf", "routing", "link-state", "igp"],
                obsoletes=[2178],
                updated_by=[5709, 6549, 6845, 6860, 7503, 8042],
            ),
            RFCDocument(
                number=5340,
                title="OSPF for IPv6",
                authors=["R. Coltun", "D. Ferguson", "J. Moy", "A. Lindem"],
                date="July 2008",
                status=RFCStatus.PROPOSED_STANDARD,
                abstract="This document describes the modifications to OSPF "
                         "to support version 6 of the Internet Protocol (IPv6).",
                keywords=["ospfv3", "ipv6", "routing"],
                obsoletes=[2740],
                updated_by=[6845, 6860, 7503, 8042],
            ),
            RFCDocument(
                number=4271,
                title="A Border Gateway Protocol 4 (BGP-4)",
                authors=["Y. Rekhter", "T. Li", "S. Hares"],
                date="January 2006",
                status=RFCStatus.DRAFT_STANDARD,
                abstract="This document discusses the Border Gateway Protocol (BGP), "
                         "an inter-Autonomous System routing protocol.",
                keywords=["bgp", "routing", "inter-domain", "egp"],
                obsoletes=[1771],
                updated_by=[6286, 6608, 6793, 7606, 7607, 7705, 8212, 9072],
            ),
            RFCDocument(
                number=4456,
                title="BGP Route Reflection: An Alternative to Full Mesh Internal BGP (IBGP)",
                authors=["T. Bates", "E. Chen", "R. Chandra"],
                date="April 2006",
                status=RFCStatus.DRAFT_STANDARD,
                abstract="This document describes a modification to the BGP route "
                         "advertisement rules that allows BGP speakers to be "
                         "route reflectors.",
                keywords=["bgp", "ibgp", "route-reflection"],
                obsoletes=[2796, 1966],
                updated_by=[9234],
            ),
            RFCDocument(
                number=3031,
                title="Multiprotocol Label Switching Architecture",
                authors=["E. Rosen", "A. Viswanathan", "R. Callon"],
                date="January 2001",
                status=RFCStatus.PROPOSED_STANDARD,
                abstract="This document specifies the architecture for "
                         "Multiprotocol Label Switching (MPLS).",
                keywords=["mpls", "label-switching", "forwarding"],
            ),
            RFCDocument(
                number=5036,
                title="LDP Specification",
                authors=["L. Andersson", "I. Minei", "B. Thomas"],
                date="October 2007",
                status=RFCStatus.DRAFT_STANDARD,
                abstract="This document specifies the Label Distribution Protocol (LDP) "
                         "for distributing labels in MPLS networks.",
                keywords=["ldp", "mpls", "label-distribution"],
                obsoletes=[3036],
                updated_by=[7358, 7552],
            ),
            RFCDocument(
                number=7348,
                title="Virtual eXtensible Local Area Network (VXLAN)",
                authors=["M. Mahalingam", "D. Dutt", "K. Duda", "P. Agarwal",
                        "L. Kreeger", "T. Sridhar", "M. Bursell", "C. Wright"],
                date="August 2014",
                status=RFCStatus.INFORMATIONAL,
                abstract="This document describes VXLAN, a framework for overlaying "
                         "virtualized layer 2 networks over layer 3 networks.",
                keywords=["vxlan", "overlay", "virtualization", "datacenter"],
            ),
            RFCDocument(
                number=7432,
                title="BGP MPLS-Based Ethernet VPN",
                authors=["A. Sajassi", "R. Aggarwal", "N. Bitar", "A. Isaac",
                        "J. Uttaro", "J. Drake", "W. Henderickx"],
                date="February 2015",
                status=RFCStatus.PROPOSED_STANDARD,
                abstract="This document describes procedures for BGP MPLS-based "
                         "Ethernet VPNs (EVPN).",
                keywords=["evpn", "bgp", "mpls", "ethernet-vpn"],
                updated_by=[8584, 9251],
            ),
            RFCDocument(
                number=1195,
                title="Use of OSI IS-IS for Routing in TCP/IP and Dual Environments",
                authors=["R. Callon"],
                date="December 1990",
                status=RFCStatus.PROPOSED_STANDARD,
                abstract="This RFC specifies an integrated IS-IS routing protocol "
                         "for TCP/IP and OSI environments.",
                keywords=["isis", "is-is", "routing", "link-state"],
            ),
            RFCDocument(
                number=2131,
                title="Dynamic Host Configuration Protocol",
                authors=["R. Droms"],
                date="March 1997",
                status=RFCStatus.DRAFT_STANDARD,
                abstract="This document specifies the DHCP protocol for providing "
                         "configuration parameters to hosts.",
                keywords=["dhcp", "ip-config", "host-configuration"],
                obsoletes=[1541],
                updated_by=[3396, 4361, 5494, 6842],
            ),
            RFCDocument(
                number=1035,
                title="Domain Names - Implementation and Specification",
                authors=["P. Mockapetris"],
                date="November 1987",
                status=RFCStatus.INTERNET_STANDARD,
                abstract="This RFC is the specification of the DNS protocol.",
                keywords=["dns", "domain-names", "resolution"],
                updated_by=[1101, 1183, 1348, 1876, 1982, 1995, 1996, 2065,
                           2136, 2181, 2137, 2308, 2535, 2673, 2845, 3425,
                           3658, 4033, 4034, 4035, 4343, 5936, 5966, 6604,
                           7766, 8482, 8490, 8767, 9210],
            ),
        ]

        for rfc in embedded_rfcs:
            self._cache[rfc.number] = rfc

    def lookup(self, rfc_number: int) -> RFCLookup:
        """
        Look up an RFC by number

        Args:
            rfc_number: RFC number to look up

        Returns:
            RFCLookup result
        """
        # Check cache first
        if rfc_number in self._cache:
            rfc = self._cache[rfc_number]
            summary_data = RFC_SUMMARIES.get(rfc_number, {})
            return RFCLookup(
                success=True,
                rfc=rfc,
                summary=summary_data.get("summary"),
                key_sections=summary_data.get("key_sections"),
            )

        # For numbers we don't have cached, return basic info
        return RFCLookup(
            success=True,
            rfc=RFCDocument(
                number=rfc_number,
                title=f"RFC {rfc_number}",
                abstract=f"Document available at https://www.rfc-editor.org/rfc/rfc{rfc_number}",
            ),
            summary=f"Full content available at https://www.rfc-editor.org/rfc/rfc{rfc_number}",
        )

    def search_by_protocol(self, protocol: str) -> RFCSearch:
        """
        Search for RFCs related to a protocol

        Args:
            protocol: Protocol name (e.g., "ospf", "bgp", "mpls")

        Returns:
            RFCSearch result with matching RFCs
        """
        protocol_lower = protocol.lower().replace("-", "").replace("_", "")

        # Find matching RFC numbers
        rfc_numbers = PROTOCOL_RFC_MAP.get(protocol_lower, [])

        # Also search in keywords
        for rfc in self._cache.values():
            if protocol_lower in [k.lower() for k in rfc.keywords]:
                if rfc.number not in rfc_numbers:
                    rfc_numbers.append(rfc.number)

        # Build results
        results = []
        for num in rfc_numbers:
            lookup = self.lookup(num)
            if lookup.success and lookup.rfc:
                results.append(lookup.rfc)

        return RFCSearch(
            success=len(results) > 0,
            query=protocol,
            results=results,
            error=f"No RFCs found for protocol: {protocol}" if not results else None,
        )

    def search_by_keyword(self, keyword: str) -> RFCSearch:
        """
        Search for RFCs by keyword

        Args:
            keyword: Keyword to search for

        Returns:
            RFCSearch result
        """
        keyword_lower = keyword.lower()
        results = []

        for rfc in self._cache.values():
            # Search in title, abstract, and keywords
            if (keyword_lower in rfc.title.lower() or
                keyword_lower in rfc.abstract.lower() or
                keyword_lower in [k.lower() for k in rfc.keywords]):
                results.append(rfc)

        return RFCSearch(
            success=len(results) > 0,
            query=keyword,
            results=results,
        )

    def get_protocol_summary(self, protocol: str) -> Dict[str, Any]:
        """
        Get a summary of protocol standards

        Args:
            protocol: Protocol name

        Returns:
            Dictionary with protocol RFC summary
        """
        search_result = self.search_by_protocol(protocol)

        if not search_result.success:
            return {
                "protocol": protocol,
                "error": f"No RFCs found for {protocol}",
            }

        summaries = []
        for rfc in search_result.results:
            summary_data = RFC_SUMMARIES.get(rfc.number, {})
            summaries.append({
                "rfc_number": rfc.number,
                "title": rfc.title,
                "status": rfc.status.value,
                "is_current": rfc.is_current,
                "url": rfc.url,
                "summary": summary_data.get("summary", rfc.abstract),
                "key_sections": summary_data.get("key_sections", []),
            })

        return {
            "protocol": protocol,
            "rfc_count": len(summaries),
            "rfcs": summaries,
        }

    def get_rfc_for_intent(self, intent: str) -> Dict[str, Any]:
        """
        Get relevant RFCs based on an agent's intent

        This helps agents find relevant standards when making decisions.

        Args:
            intent: Intent description (e.g., "configure ospf neighbor",
                   "advertise bgp routes", "create vxlan tunnel")

        Returns:
            Dictionary with relevant RFC information
        """
        intent_lower = intent.lower()

        # Map common intents to protocols
        protocol_patterns = {
            "ospf": ["ospf", "lsa", "spf", "dijkstra", "area", "dr election", "lsdb"],
            "bgp": ["bgp", "as path", "route advertisement", "peer", "neighbor",
                   "local pref", "med", "community"],
            "isis": ["isis", "is-is", "clns", "tlv"],
            "mpls": ["mpls", "label", "lsp", "fec"],
            "ldp": ["ldp", "label distribution"],
            "vxlan": ["vxlan", "vni", "vtep", "tunnel", "overlay"],
            "evpn": ["evpn", "mac route", "type-2", "type-5"],
        }

        matched_protocols = []
        for protocol, patterns in protocol_patterns.items():
            for pattern in patterns:
                if pattern in intent_lower:
                    if protocol not in matched_protocols:
                        matched_protocols.append(protocol)
                    break

        if not matched_protocols:
            return {
                "intent": intent,
                "error": "No matching protocols found for intent",
                "suggestion": "Try including protocol names in your query",
            }

        results = []
        for protocol in matched_protocols:
            summary = self.get_protocol_summary(protocol)
            if "error" not in summary:
                results.append(summary)

        return {
            "intent": intent,
            "matched_protocols": matched_protocols,
            "protocol_summaries": results,
        }


# Global RFC client instance
_rfc_client: Optional[RFCClient] = None


def get_rfc_client() -> RFCClient:
    """Get or create the global RFC client instance"""
    global _rfc_client
    if _rfc_client is None:
        _rfc_client = RFCClient()
    return _rfc_client
