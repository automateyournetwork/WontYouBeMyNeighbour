"""
Network Advisor for Intelligent Suggestions

Analyzes network state and provides AI-powered recommendations
for optimization, security, and best practices.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SuggestionPriority(Enum):
    """Priority levels for suggestions."""
    CRITICAL = "critical"   # Immediate action required
    HIGH = "high"           # Should be addressed soon
    MEDIUM = "medium"       # Good to address
    LOW = "low"             # Nice to have
    INFO = "info"           # Informational only


class SuggestionCategory(Enum):
    """Categories of network suggestions."""
    PERFORMANCE = "performance"     # Performance optimizations
    SECURITY = "security"           # Security improvements
    REDUNDANCY = "redundancy"       # High availability / redundancy
    SCALABILITY = "scalability"     # Scaling improvements
    BEST_PRACTICE = "best_practice" # Best practice compliance
    CONFIGURATION = "configuration" # Config recommendations
    MONITORING = "monitoring"       # Monitoring/observability
    TROUBLESHOOTING = "troubleshooting"  # Issue diagnosis


@dataclass
class Suggestion:
    """A network improvement suggestion."""
    suggestion_id: str
    title: str
    description: str
    category: SuggestionCategory
    priority: SuggestionPriority
    agent_id: Optional[str] = None
    affected_resources: List[str] = field(default_factory=list)
    recommendation: str = ""
    impact: str = ""
    effort: str = "low"  # low, medium, high
    auto_fixable: bool = False
    fix_command: Optional[str] = None
    references: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "suggestion_id": self.suggestion_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "priority": self.priority.value,
            "agent_id": self.agent_id,
            "affected_resources": self.affected_resources,
            "affected_agents": [self.agent_id] if self.agent_id else self.affected_resources,
            "recommendation": self.recommendation,
            "impact": self.impact,
            "effort": self.effort,
            "auto_fixable": self.auto_fixable,
            "auto_applicable": self.auto_fixable,  # Alias for JS compatibility
            "fix_command": self.fix_command,
            "references": self.references,
            "created_at": self.created_at.isoformat(),
        }


class NetworkAdvisor:
    """
    Intelligent network advisor.

    Analyzes network state and generates actionable suggestions
    for improvements, optimizations, and best practices.
    """

    # Singleton instance
    _instance: Optional["NetworkAdvisor"] = None

    def __new__(cls) -> "NetworkAdvisor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._suggestion_counter = 0
        self._suggestions: List[Suggestion] = []
        self._dismissed_suggestions: Set[str] = set()
        self._history: List[Dict[str, Any]] = []
        self._last_analysis: Optional[datetime] = None

        logger.info("NetworkAdvisor initialized")

    def _generate_suggestion_id(self) -> str:
        """Generate unique suggestion ID."""
        self._suggestion_counter += 1
        return f"sug-{self._suggestion_counter:06d}"

    def analyze_network(
        self,
        network_state: Dict[str, Any],
        include_info: bool = True,
    ) -> List[Suggestion]:
        """
        Analyze network state and generate suggestions.

        Args:
            network_state: Current network state dictionary
            include_info: Include informational suggestions

        Returns:
            List of suggestions
        """
        self._suggestions = []
        self._last_analysis = datetime.now()

        # Run all analyzers
        self._analyze_topology(network_state)
        self._analyze_routing(network_state)
        self._analyze_redundancy(network_state)
        self._analyze_security(network_state)
        self._analyze_performance(network_state)
        self._analyze_configuration(network_state)
        self._analyze_monitoring(network_state)

        # Filter out dismissed and optionally info-level
        suggestions = [
            s for s in self._suggestions
            if s.suggestion_id not in self._dismissed_suggestions
        ]

        if not include_info:
            suggestions = [s for s in suggestions if s.priority != SuggestionPriority.INFO]

        logger.info(f"Generated {len(suggestions)} suggestions")
        return suggestions

    def _add_suggestion(
        self,
        title: str,
        description: str,
        category: SuggestionCategory,
        priority: SuggestionPriority,
        **kwargs,
    ):
        """Add a suggestion."""
        suggestion = Suggestion(
            suggestion_id=self._generate_suggestion_id(),
            title=title,
            description=description,
            category=category,
            priority=priority,
            **kwargs,
        )
        self._suggestions.append(suggestion)

    # ==== Topology Analysis ====

    def _analyze_topology(self, state: Dict[str, Any]):
        """Analyze topology for potential issues."""
        topology = state.get("topology", {})
        nodes = topology.get("nodes", [])
        links = topology.get("links", [])

        # Check for single points of failure
        node_connections = {}
        for link in links:
            src = link.get("source")
            tgt = link.get("target")
            node_connections[src] = node_connections.get(src, 0) + 1
            node_connections[tgt] = node_connections.get(tgt, 0) + 1

        for node_id, connections in node_connections.items():
            if connections == 1:
                node = next((n for n in nodes if n.get("id") == node_id), None)
                if node and node.get("type") != "endpoint":
                    self._add_suggestion(
                        title=f"Single point of failure: {node_id}",
                        description=f"Node '{node_id}' has only one connection, making it a single point of failure.",
                        category=SuggestionCategory.REDUNDANCY,
                        priority=SuggestionPriority.HIGH,
                        agent_id=node_id,
                        affected_resources=[node_id],
                        recommendation="Add a redundant link to this node to improve resilience.",
                        impact="If this link fails, the node will be isolated from the network.",
                        effort="medium",
                    )

        # Check for down links
        for link in links:
            if link.get("status") != "up":
                self._add_suggestion(
                    title=f"Link down: {link.get('source')} - {link.get('target')}",
                    description=f"Link between {link.get('source')} and {link.get('target')} is not up.",
                    category=SuggestionCategory.TROUBLESHOOTING,
                    priority=SuggestionPriority.CRITICAL,
                    affected_resources=[link.get("source"), link.get("target")],
                    recommendation="Investigate the link failure. Check physical connectivity, interface status, and configurations.",
                    impact="Traffic between these nodes may be affected or rerouted.",
                    effort="low",
                )

        # Check topology size
        if len(nodes) > 20:
            self._add_suggestion(
                title="Large topology detected",
                description=f"Network has {len(nodes)} nodes. Consider implementing hierarchical design.",
                category=SuggestionCategory.SCALABILITY,
                priority=SuggestionPriority.MEDIUM,
                recommendation="Implement a hierarchical design with core, distribution, and access layers for better scalability.",
                impact="Improved manageability and scalability.",
                effort="high",
            )

    # ==== Routing Analysis ====

    def _analyze_routing(self, state: Dict[str, Any]):
        """Analyze routing for potential issues."""
        routes = state.get("routes", {})
        protocols = state.get("protocols", {})

        total_routes = sum(len(r) for r in routes.values())

        # Check for large routing tables
        for agent_id, agent_routes in routes.items():
            if len(agent_routes) > 100:
                self._add_suggestion(
                    title=f"Large routing table on {agent_id}",
                    description=f"Router '{agent_id}' has {len(agent_routes)} routes.",
                    category=SuggestionCategory.PERFORMANCE,
                    priority=SuggestionPriority.MEDIUM,
                    agent_id=agent_id,
                    recommendation="Consider route summarization to reduce routing table size.",
                    impact="Reduced memory usage and faster route lookups.",
                    effort="medium",
                )

            # Check for multiple routes to same destination
            prefixes = [r.get("prefix") for r in agent_routes]
            duplicates = set([p for p in prefixes if prefixes.count(p) > 1])
            if duplicates:
                self._add_suggestion(
                    title=f"Multiple routes to same prefix on {agent_id}",
                    description=f"Found {len(duplicates)} prefixes with multiple routes.",
                    category=SuggestionCategory.BEST_PRACTICE,
                    priority=SuggestionPriority.LOW,
                    agent_id=agent_id,
                    affected_resources=list(duplicates)[:5],
                    recommendation="Review routing policy to ensure optimal path selection.",
                    impact="May indicate suboptimal routing or redundancy.",
                    effort="low",
                )

        # Check OSPF configuration
        ospf = protocols.get("ospf", {})
        if ospf:
            spf_runs = ospf.get("spf_runs", 0)
            if spf_runs > 10:
                self._add_suggestion(
                    title="High OSPF SPF calculation frequency",
                    description=f"OSPF has run SPF algorithm {spf_runs} times.",
                    category=SuggestionCategory.PERFORMANCE,
                    priority=SuggestionPriority.MEDIUM,
                    recommendation="Check for network instability causing frequent topology changes. Consider SPF throttling.",
                    impact="High SPF frequency can increase CPU usage.",
                    effort="low",
                )

            # Check for OSPF stub areas
            self._add_suggestion(
                title="Consider OSPF stub areas",
                description="Using OSPF stub areas can reduce LSA flooding in larger networks.",
                category=SuggestionCategory.BEST_PRACTICE,
                priority=SuggestionPriority.INFO,
                recommendation="Configure stub or totally stub areas for edge areas that don't need full routing information.",
                impact="Reduced LSDB size and SPF calculations in stub areas.",
                effort="medium",
                references=["RFC 2328 - OSPF Version 2"],
            )

        # Check BGP configuration
        bgp = protocols.get("bgp", {})
        if bgp:
            peers = bgp.get("peers", 0)
            established = bgp.get("established_peers", 0)

            if peers > 0 and established < peers:
                self._add_suggestion(
                    title="BGP peers not fully established",
                    description=f"Only {established} of {peers} BGP peers are established.",
                    category=SuggestionCategory.TROUBLESHOOTING,
                    priority=SuggestionPriority.HIGH,
                    recommendation="Check BGP peer configurations, ACLs, and network connectivity.",
                    impact="Routes may not be properly exchanged with failed peers.",
                    effort="medium",
                )

            if peers >= 5:
                self._add_suggestion(
                    title="Consider BGP route reflector",
                    description=f"Network has {peers} BGP peers. Route reflectors can simplify iBGP design.",
                    category=SuggestionCategory.SCALABILITY,
                    priority=SuggestionPriority.MEDIUM,
                    recommendation="Implement route reflectors for iBGP to reduce full mesh peering requirements.",
                    impact="Simplified BGP configuration and better scalability.",
                    effort="high",
                    references=["RFC 4456 - BGP Route Reflection"],
                )

    # ==== Redundancy Analysis ====

    def _analyze_redundancy(self, state: Dict[str, Any]):
        """Analyze redundancy and high availability."""
        agents = state.get("agents", {})
        topology = state.get("topology", {})

        # Check for VRRP/HSRP
        has_gateway_redundancy = False
        for agent_id, agent_data in agents.items():
            if "vrrp" in str(agent_data).lower() or "hsrp" in str(agent_data).lower():
                has_gateway_redundancy = True
                break

        if len(agents) >= 2 and not has_gateway_redundancy:
            self._add_suggestion(
                title="No gateway redundancy detected",
                description="Consider implementing VRRP or HSRP for default gateway redundancy.",
                category=SuggestionCategory.REDUNDANCY,
                priority=SuggestionPriority.MEDIUM,
                recommendation="Configure VRRP (Virtual Router Redundancy Protocol) for gateway failover.",
                impact="Improved client connectivity during router failures.",
                effort="medium",
                references=["RFC 5798 - VRRP Version 3"],
            )

        # Check for link aggregation opportunities
        links = topology.get("links", [])
        link_pairs = {}
        for link in links:
            pair = tuple(sorted([link.get("source"), link.get("target")]))
            link_pairs[pair] = link_pairs.get(pair, 0) + 1

        for pair, count in link_pairs.items():
            if count == 1:
                # Single link between nodes
                self._add_suggestion(
                    title=f"Consider link aggregation: {pair[0]} - {pair[1]}",
                    description=f"Single link between {pair[0]} and {pair[1]}. LACP can provide redundancy and increased bandwidth.",
                    category=SuggestionCategory.REDUNDANCY,
                    priority=SuggestionPriority.LOW,
                    affected_resources=list(pair),
                    recommendation="Configure LACP (802.3ad) link aggregation for redundancy and bandwidth.",
                    impact="Link failure protection and increased bandwidth.",
                    effort="medium",
                    references=["IEEE 802.3ad"],
                )

    # ==== Security Analysis ====

    def _analyze_security(self, state: Dict[str, Any]):
        """Analyze security posture."""
        agents = state.get("agents", {})

        # Check for ACLs
        has_acls = False
        for agent_id, agent_data in agents.items():
            if "acl" in str(agent_data).lower() or "firewall" in str(agent_data).lower():
                has_acls = True
                break

        if not has_acls:
            self._add_suggestion(
                title="No access control lists detected",
                description="Consider implementing ACLs to control traffic flow and improve security.",
                category=SuggestionCategory.SECURITY,
                priority=SuggestionPriority.HIGH,
                recommendation="Configure ingress filtering ACLs on edge interfaces to block unauthorized traffic.",
                impact="Improved network security and traffic control.",
                effort="medium",
            )

        # Check for control plane protection
        self._add_suggestion(
            title="Implement control plane protection",
            description="Control plane policing (CoPP) protects router CPU from DoS attacks.",
            category=SuggestionCategory.SECURITY,
            priority=SuggestionPriority.MEDIUM,
            recommendation="Configure rate limiting for control plane traffic to protect against attacks.",
            impact="Protected routing protocol operations during attacks.",
            effort="medium",
        )

        # Check for BGP security
        protocols = state.get("protocols", {})
        if protocols.get("bgp"):
            self._add_suggestion(
                title="Enable BGP authentication",
                description="BGP sessions should use MD5 authentication to prevent session hijacking.",
                category=SuggestionCategory.SECURITY,
                priority=SuggestionPriority.HIGH,
                recommendation="Configure TCP MD5 authentication for all BGP peerings.",
                impact="Protected BGP sessions from unauthorized peers.",
                effort="low",
                references=["RFC 2385 - Protection of BGP Sessions via TCP MD5"],
            )

    # ==== Performance Analysis ====

    def _analyze_performance(self, state: Dict[str, Any]):
        """Analyze performance metrics."""
        agents = state.get("agents", {})

        for agent_id, agent_data in agents.items():
            cpu = agent_data.get("cpu_percent", 0)
            memory = agent_data.get("memory_percent", 0)

            if cpu > 80:
                self._add_suggestion(
                    title=f"High CPU usage on {agent_id}",
                    description=f"Router '{agent_id}' has {cpu}% CPU usage.",
                    category=SuggestionCategory.PERFORMANCE,
                    priority=SuggestionPriority.HIGH,
                    agent_id=agent_id,
                    recommendation="Investigate processes consuming CPU. Consider hardware upgrade or load balancing.",
                    impact="High CPU can cause packet drops and protocol timeouts.",
                    effort="medium",
                )
            elif cpu > 60:
                self._add_suggestion(
                    title=f"Elevated CPU usage on {agent_id}",
                    description=f"Router '{agent_id}' has {cpu}% CPU usage.",
                    category=SuggestionCategory.PERFORMANCE,
                    priority=SuggestionPriority.MEDIUM,
                    agent_id=agent_id,
                    recommendation="Monitor CPU trends. Plan for capacity if usage continues to increase.",
                    impact="May indicate approaching capacity limits.",
                    effort="low",
                )

            if memory > 85:
                self._add_suggestion(
                    title=f"High memory usage on {agent_id}",
                    description=f"Router '{agent_id}' has {memory}% memory usage.",
                    category=SuggestionCategory.PERFORMANCE,
                    priority=SuggestionPriority.HIGH,
                    agent_id=agent_id,
                    recommendation="Check for memory leaks or excessive routing tables. Consider memory upgrade.",
                    impact="Low memory can cause instability and process crashes.",
                    effort="medium",
                )

    # ==== Configuration Analysis ====

    def _analyze_configuration(self, state: Dict[str, Any]):
        """Analyze configuration best practices."""
        agents = state.get("agents", {})

        for agent_id, agent_data in agents.items():
            # Check for loopback
            has_loopback = agent_data.get("config", {}).get("has_loopback", False)
            if not has_loopback:
                self._add_suggestion(
                    title=f"No loopback interface on {agent_id}",
                    description="Loopback interfaces provide stable router IDs for routing protocols.",
                    category=SuggestionCategory.CONFIGURATION,
                    priority=SuggestionPriority.MEDIUM,
                    agent_id=agent_id,
                    recommendation="Configure a loopback interface with a /32 address for router ID.",
                    impact="Stable protocol operations even with interface flaps.",
                    effort="low",
                )

        # General config suggestions
        self._add_suggestion(
            title="Enable NTP synchronization",
            description="Synchronized time is critical for logging, troubleshooting, and security.",
            category=SuggestionCategory.CONFIGURATION,
            priority=SuggestionPriority.MEDIUM,
            recommendation="Configure NTP clients on all devices pointing to reliable NTP servers.",
            impact="Accurate timestamps for logs and certificate validation.",
            effort="low",
        )

        self._add_suggestion(
            title="Configure syslog server",
            description="Centralized logging improves visibility and troubleshooting.",
            category=SuggestionCategory.MONITORING,
            priority=SuggestionPriority.MEDIUM,
            recommendation="Configure syslog to send logs to a central logging server.",
            impact="Better visibility into network events and issues.",
            effort="low",
        )

    # ==== Monitoring Analysis ====

    def _analyze_monitoring(self, state: Dict[str, Any]):
        """Analyze monitoring and observability."""
        self._add_suggestion(
            title="Enable SNMP monitoring",
            description="SNMP enables network management systems to monitor device health.",
            category=SuggestionCategory.MONITORING,
            priority=SuggestionPriority.MEDIUM,
            recommendation="Configure SNMPv3 with authentication and encryption for secure monitoring.",
            impact="Proactive monitoring and alerting capabilities.",
            effort="low",
            references=["RFC 3414 - SNMPv3 User-based Security Model"],
        )

        self._add_suggestion(
            title="Implement NetFlow/IPFIX",
            description="Flow data provides visibility into traffic patterns and usage.",
            category=SuggestionCategory.MONITORING,
            priority=SuggestionPriority.LOW,
            recommendation="Enable NetFlow or IPFIX export to analyze traffic patterns.",
            impact="Traffic visibility for capacity planning and security analysis.",
            effort="medium",
            references=["RFC 7011 - IPFIX Protocol"],
        )

    def get_suggestions(
        self,
        category: Optional[SuggestionCategory] = None,
        priority: Optional[SuggestionPriority] = None,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Suggestion]:
        """Get suggestions with optional filtering."""
        suggestions = [
            s for s in self._suggestions
            if s.suggestion_id not in self._dismissed_suggestions
        ]

        if category:
            suggestions = [s for s in suggestions if s.category == category]
        if priority:
            suggestions = [s for s in suggestions if s.priority == priority]
        if agent_id:
            suggestions = [s for s in suggestions if s.agent_id == agent_id]

        # Sort by priority
        priority_order = {
            SuggestionPriority.CRITICAL: 0,
            SuggestionPriority.HIGH: 1,
            SuggestionPriority.MEDIUM: 2,
            SuggestionPriority.LOW: 3,
            SuggestionPriority.INFO: 4,
        }
        suggestions.sort(key=lambda s: priority_order.get(s.priority, 5))

        return suggestions[:limit]

    def dismiss_suggestion(self, suggestion_id: str, reason: Optional[str] = None) -> bool:
        """Dismiss a suggestion (won't appear in future results)."""
        suggestion = next((s for s in self._suggestions if s.suggestion_id == suggestion_id), None)
        if suggestion is None:
            return False

        self._dismissed_suggestions.add(suggestion_id)
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "dismissed",
            "suggestion_id": suggestion_id,
            "suggestion_title": suggestion.title,
            "reason": reason,
        })
        return True

    def apply_suggestion(self, suggestion_id: str) -> Dict[str, Any]:
        """
        Apply a suggestion if it's auto-applicable.

        Returns result dict with 'applied' boolean and details.
        """
        suggestion = next((s for s in self._suggestions if s.suggestion_id == suggestion_id), None)
        if suggestion is None:
            return {"applied": False, "error": "Suggestion not found"}

        if not suggestion.auto_fixable:
            return {"applied": False, "error": "Suggestion is not auto-applicable"}

        # Mark as applied and record in history
        self._dismissed_suggestions.add(suggestion_id)
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "action": "applied",
            "suggestion_id": suggestion_id,
            "suggestion_title": suggestion.title,
            "fix_command": suggestion.fix_command,
        })

        return {
            "applied": True,
            "suggestion_id": suggestion_id,
            "title": suggestion.title,
            "fix_command": suggestion.fix_command,
        }

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get history of dismissed and applied suggestions."""
        return self._history[-limit:][::-1]  # Most recent first

    def clear_cache(self):
        """Clear cached suggestions to force re-analysis."""
        self._suggestions = []
        logger.info("Suggestions cache cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """Get advisor statistics."""
        by_priority = {}
        by_category = {}

        for s in self._suggestions:
            if s.suggestion_id in self._dismissed_suggestions:
                continue
            by_priority[s.priority.value] = by_priority.get(s.priority.value, 0) + 1
            by_category[s.category.value] = by_category.get(s.category.value, 0) + 1

        return {
            "total_suggestions": len(self._suggestions) - len(self._dismissed_suggestions),
            "dismissed_count": len(self._dismissed_suggestions),
            "by_priority": by_priority,
            "by_category": by_category,
            "last_analysis": self._last_analysis.isoformat() if self._last_analysis else None,
        }


# Singleton accessor
def get_network_advisor() -> NetworkAdvisor:
    """Get the network advisor instance."""
    return NetworkAdvisor()


# Convenience functions
def analyze_network(network_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Analyze network and return suggestions as dictionaries."""
    advisor = get_network_advisor()
    suggestions = advisor.analyze_network(network_state)
    return [s.to_dict() for s in suggestions]


def get_suggestions(
    category: Optional[str] = None,
    priority: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get filtered suggestions."""
    advisor = get_network_advisor()

    cat = SuggestionCategory(category) if category else None
    pri = SuggestionPriority(priority) if priority else None

    suggestions = advisor.get_suggestions(category=cat, priority=pri, agent_id=agent_id)
    return [s.to_dict() for s in suggestions]
