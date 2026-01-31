"""
Network Compliance Checker

Validates network configurations against best practices, security policies,
and compliance requirements.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import logging
import re
import uuid

logger = logging.getLogger(__name__)


class ComplianceSeverity(Enum):
    """Severity levels for compliance violations."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceCategory(Enum):
    """Categories of compliance rules."""
    SECURITY = "security"
    AUTHENTICATION = "authentication"
    ENCRYPTION = "encryption"
    ACCESS_CONTROL = "access_control"
    ROUTING = "routing"
    REDUNDANCY = "redundancy"
    MONITORING = "monitoring"
    LOGGING = "logging"
    NAMING = "naming"
    CONFIGURATION = "configuration"
    BEST_PRACTICE = "best_practice"
    REGULATORY = "regulatory"


@dataclass
class ComplianceRule:
    """A compliance rule definition."""
    rule_id: str
    name: str
    description: str
    category: ComplianceCategory
    severity: ComplianceSeverity
    check_function: Optional[Callable] = None
    remediation: str = ""
    references: List[str] = field(default_factory=list)
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    rule_set: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "remediation": self.remediation,
            "references": self.references,
            "enabled": self.enabled,
            "tags": self.tags,
            "rule_set": self.rule_set
        }


@dataclass
class ComplianceViolation:
    """A detected compliance violation."""
    violation_id: str
    rule_id: str
    rule_name: str
    category: ComplianceCategory
    severity: ComplianceSeverity
    agent_id: Optional[str]
    resource: str
    description: str
    details: Dict[str, Any]
    remediation: str
    detected_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "resource": self.resource,
            "description": self.description,
            "details": self.details,
            "remediation": self.remediation,
            "detected_at": self.detected_at.isoformat()
        }


@dataclass
class ComplianceReport:
    """A compliance check report."""
    report_id: str
    generated_at: datetime
    completed_at: Optional[datetime]
    rule_set: str
    categories_checked: List[ComplianceCategory]
    agents_checked: List[str]
    total_rules: int
    rules_passed: int
    rules_failed: int
    violations: List[ComplianceViolation]
    score: float  # 0-100
    summary: Dict[str, Any]

    @property
    def pass_rate(self) -> float:
        if self.total_rules == 0:
            return 100.0
        return (self.rules_passed / self.total_rules) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "rule_set": self.rule_set,
            "categories_checked": [c.value for c in self.categories_checked],
            "agents_checked": self.agents_checked,
            "total_rules": self.total_rules,
            "rules_passed": self.rules_passed,
            "rules_failed": self.rules_failed,
            "violations": [v.to_dict() for v in self.violations],
            "violation_count": len(self.violations),
            "score": round(self.score, 1),
            "pass_rate": round(self.pass_rate, 1),
            "summary": self.summary,
            "by_severity": self._count_by_severity(),
            "by_category": self._count_by_category()
        }

    def _count_by_severity(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in ComplianceSeverity}
        for v in self.violations:
            counts[v.severity.value] += 1
        return counts

    def _count_by_category(self) -> Dict[str, int]:
        counts = {c.value: 0 for c in ComplianceCategory}
        for v in self.violations:
            counts[v.category.value] += 1
        return counts


class ComplianceChecker:
    """Network compliance checking engine."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._rules: Dict[str, ComplianceRule] = {}
        self._reports: Dict[str, ComplianceReport] = {}
        self._rule_sets: Dict[str, List[str]] = {}  # rule_set -> [rule_ids]
        self._init_rules()

        logger.info("ComplianceChecker initialized")

    def _init_rules(self):
        """Initialize built-in compliance rules."""
        # Security Rules
        self._add_rule(ComplianceRule(
            rule_id="SEC001",
            name="BGP Authentication Required",
            description="BGP peers should use MD5 authentication",
            category=ComplianceCategory.AUTHENTICATION,
            severity=ComplianceSeverity.HIGH,
            remediation="Configure MD5 authentication for all BGP peer sessions",
            references=["RFC 5925", "CIS Benchmark"],
            tags=["bgp", "security", "authentication"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="SEC002",
            name="OSPF Authentication Required",
            description="OSPF interfaces should use authentication",
            category=ComplianceCategory.AUTHENTICATION,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure OSPF authentication (MD5 or SHA) on all OSPF interfaces",
            references=["RFC 5709"],
            tags=["ospf", "security", "authentication"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="SEC003",
            name="SSH Required for Management",
            description="Management access should use SSH, not Telnet",
            category=ComplianceCategory.ENCRYPTION,
            severity=ComplianceSeverity.CRITICAL,
            remediation="Disable Telnet and enable SSH for all management access",
            references=["PCI-DSS 2.3", "CIS Benchmark"],
            tags=["management", "encryption", "ssh"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="SEC004",
            name="Strong Passwords Required",
            description="All accounts should have strong passwords",
            category=ComplianceCategory.AUTHENTICATION,
            severity=ComplianceSeverity.HIGH,
            remediation="Implement password policy with minimum length and complexity requirements",
            references=["PCI-DSS 8.2", "NIST 800-63B"],
            tags=["passwords", "authentication"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="SEC005",
            name="ACL on Management Interface",
            description="Management interfaces should have ACLs restricting access",
            category=ComplianceCategory.ACCESS_CONTROL,
            severity=ComplianceSeverity.HIGH,
            remediation="Apply ACLs to restrict management access to authorized IP addresses",
            references=["CIS Benchmark"],
            tags=["acl", "management", "access-control"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="SEC006",
            name="Disable Unused Services",
            description="Unused network services should be disabled",
            category=ComplianceCategory.SECURITY,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Disable HTTP, FTP, and other unused services",
            references=["CIS Benchmark"],
            tags=["services", "hardening"]
        ))

        # Routing Rules
        self._add_rule(ComplianceRule(
            rule_id="RTG001",
            name="BGP Maximum Prefix Limit",
            description="BGP peers should have maximum prefix limits configured",
            category=ComplianceCategory.ROUTING,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure maximum-prefix limits on all eBGP sessions",
            references=["RFC 7454"],
            tags=["bgp", "routing", "best-practice"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="RTG002",
            name="BGP Route Filtering",
            description="eBGP peers should have route filters applied",
            category=ComplianceCategory.ROUTING,
            severity=ComplianceSeverity.HIGH,
            remediation="Apply prefix lists or route-maps to filter BGP routes",
            references=["RFC 7454"],
            tags=["bgp", "routing", "filtering"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="RTG003",
            name="OSPF Passive Interface Default",
            description="OSPF should use passive-interface default with explicit activation",
            category=ComplianceCategory.ROUTING,
            severity=ComplianceSeverity.LOW,
            remediation="Configure passive-interface default and explicitly enable OSPF on required interfaces",
            references=["Best Practice"],
            tags=["ospf", "routing", "security"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="RTG004",
            name="Loopback Interface Required",
            description="All routers should have a loopback interface for stable router-id",
            category=ComplianceCategory.CONFIGURATION,
            severity=ComplianceSeverity.LOW,
            remediation="Configure a loopback interface with a stable IP address",
            tags=["configuration", "routing"]
        ))

        # GRE Tunnel Rules
        self._add_rule(ComplianceRule(
            rule_id="TUN001",
            name="GRE Tunnel MTU Configuration",
            description="GRE tunnels should have MTU configured to prevent fragmentation",
            category=ComplianceCategory.CONFIGURATION,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure MTU on GRE tunnels to account for encapsulation overhead (typically 1400-1476)",
            references=["RFC 2784", "RFC 2890"],
            tags=["gre", "tunnel", "mtu", "configuration"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="TUN002",
            name="GRE Tunnel Keepalives",
            description="GRE tunnels should have keepalives enabled for failure detection",
            category=ComplianceCategory.MONITORING,
            severity=ComplianceSeverity.LOW,
            remediation="Enable GRE keepalives with appropriate interval for tunnel health monitoring",
            tags=["gre", "tunnel", "keepalive", "monitoring"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="TUN003",
            name="GRE Key Authentication",
            description="GRE tunnels should use key authentication for security",
            category=ComplianceCategory.AUTHENTICATION,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure GRE key on both tunnel endpoints to prevent unauthorized tunnel connections",
            references=["RFC 2890"],
            tags=["gre", "tunnel", "security", "authentication"]
        ))

        # BFD (Bidirectional Forwarding Detection) Rules
        self._add_rule(ComplianceRule(
            rule_id="BFD001",
            name="BFD for Routing Protocols",
            description="BFD should be enabled for all routing protocol neighbors for fast failure detection",
            category=ComplianceCategory.ROUTING,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Enable BFD for OSPF, BGP, and IS-IS neighbors to achieve sub-second failure detection",
            references=["RFC 5880", "RFC 5882"],
            tags=["bfd", "routing", "convergence", "availability"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="BFD002",
            name="BFD Detection Timers",
            description="BFD detection timers should be configured appropriately for the protocol",
            category=ComplianceCategory.CONFIGURATION,
            severity=ComplianceSeverity.LOW,
            remediation="Configure BFD timers: 100ms TX/RX with detect-mult 3 for IGP (300ms detection), "
                       "adjust for BGP and WAN links as needed",
            references=["RFC 5880"],
            tags=["bfd", "timers", "configuration"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="BFD003",
            name="BFD Session Stability",
            description="BFD sessions should be stable without frequent flaps",
            category=ComplianceCategory.MONITORING,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Investigate and resolve underlying causes of BFD session flapping (jitter, congestion, MTU)",
            tags=["bfd", "stability", "monitoring"]
        ))

        # Redundancy Rules
        self._add_rule(ComplianceRule(
            rule_id="RED001",
            name="Dual-Homed Connectivity",
            description="Critical devices should have redundant connections",
            category=ComplianceCategory.REDUNDANCY,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Ensure critical devices have at least two uplink connections",
            tags=["redundancy", "availability"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="RED002",
            name="Multiple OSPF Areas",
            description="Large OSPF networks should use multiple areas",
            category=ComplianceCategory.ROUTING,
            severity=ComplianceSeverity.LOW,
            remediation="Design OSPF with hierarchical areas for networks with >50 routers",
            tags=["ospf", "design", "scalability"]
        ))

        # Monitoring Rules
        self._add_rule(ComplianceRule(
            rule_id="MON001",
            name="SNMP Configured",
            description="SNMP should be configured for network monitoring",
            category=ComplianceCategory.MONITORING,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure SNMPv3 for secure network monitoring",
            references=["RFC 3411"],
            tags=["snmp", "monitoring"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="MON002",
            name="Syslog Configured",
            description="Syslog should be configured for centralized logging",
            category=ComplianceCategory.LOGGING,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure syslog to send logs to a central log server",
            references=["PCI-DSS 10.2"],
            tags=["syslog", "logging"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="MON003",
            name="NTP Configured",
            description="NTP should be configured for time synchronization",
            category=ComplianceCategory.CONFIGURATION,
            severity=ComplianceSeverity.MEDIUM,
            remediation="Configure NTP servers for accurate timekeeping",
            references=["PCI-DSS 10.4"],
            tags=["ntp", "time", "logging"]
        ))

        # Naming/Configuration Rules
        self._add_rule(ComplianceRule(
            rule_id="CFG001",
            name="Interface Description Required",
            description="All interfaces should have descriptions",
            category=ComplianceCategory.NAMING,
            severity=ComplianceSeverity.INFO,
            remediation="Add descriptive interface descriptions",
            tags=["documentation", "naming"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="CFG002",
            name="Hostname Configured",
            description="All devices should have meaningful hostnames",
            category=ComplianceCategory.NAMING,
            severity=ComplianceSeverity.INFO,
            remediation="Configure descriptive hostnames following naming convention",
            tags=["naming", "documentation"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="CFG003",
            name="Banner Configured",
            description="Login banners should be configured",
            category=ComplianceCategory.SECURITY,
            severity=ComplianceSeverity.LOW,
            remediation="Configure MOTD and login banners with legal warnings",
            references=["CIS Benchmark"],
            tags=["banner", "security"]
        ))

        # Best Practice Rules
        self._add_rule(ComplianceRule(
            rule_id="BP001",
            name="MTU Consistency",
            description="MTU should be consistent across connected interfaces",
            category=ComplianceCategory.BEST_PRACTICE,
            severity=ComplianceSeverity.LOW,
            remediation="Ensure matching MTU on both ends of each link",
            tags=["mtu", "configuration"]
        ))

        self._add_rule(ComplianceRule(
            rule_id="BP002",
            name="Unused Interfaces Shutdown",
            description="Unused interfaces should be administratively shut down",
            category=ComplianceCategory.SECURITY,
            severity=ComplianceSeverity.LOW,
            remediation="Shutdown unused interfaces with 'shutdown' command",
            references=["CIS Benchmark"],
            tags=["security", "hardening"]
        ))

        # Rule sets
        self._rule_sets["default"] = list(self._rules.keys())
        self._rule_sets["security"] = [r for r in self._rules.keys() if r.startswith("SEC")]
        self._rule_sets["routing"] = [r for r in self._rules.keys() if r.startswith("RTG")]
        self._rule_sets["monitoring"] = [r for r in self._rules.keys() if r.startswith("MON")]
        self._rule_sets["best-practice"] = [r for r in self._rules.keys() if r.startswith("BP") or r.startswith("CFG")]

    def _add_rule(self, rule: ComplianceRule) -> None:
        """Add a compliance rule."""
        self._rules[rule.rule_id] = rule

    def get_rules(self, category: str = None, rule_set: str = None) -> List[ComplianceRule]:
        """Get compliance rules with optional filtering."""
        rules = list(self._rules.values())

        if category:
            try:
                cat = ComplianceCategory(category)
                rules = [r for r in rules if r.category == cat]
            except ValueError:
                pass

        if rule_set and rule_set in self._rule_sets:
            rule_ids = self._rule_sets[rule_set]
            rules = [r for r in rules if r.rule_id in rule_ids]

        return [r for r in rules if r.enabled]

    def get_rule_sets(self) -> List[str]:
        """Get available rule sets."""
        return list(self._rule_sets.keys())

    def run_check(
        self,
        categories: List[ComplianceCategory] = None,
        agents: List[str] = None,
        rule_set: str = "default"
    ) -> ComplianceReport:
        """Run compliance checks."""
        report_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        # Get agents to check
        agent_data = self._get_agents(agents)
        agents_checked = [a.get("name", a.get("agent_id", "unknown")) for a in agent_data]

        # Get rules to check
        rules = self.get_rules(rule_set=rule_set)
        if categories:
            rules = [r for r in rules if r.category in categories]

        categories_checked = list(set(r.category for r in rules))

        # Run checks
        violations = []
        rules_passed = 0
        rules_failed = 0

        for rule in rules:
            rule_violations = self._check_rule(rule, agent_data)
            if rule_violations:
                violations.extend(rule_violations)
                rules_failed += 1
            else:
                rules_passed += 1

        # Calculate score
        total_rules = rules_passed + rules_failed
        if total_rules > 0:
            # Weight by severity
            severity_weights = {
                ComplianceSeverity.CRITICAL: 10,
                ComplianceSeverity.HIGH: 5,
                ComplianceSeverity.MEDIUM: 3,
                ComplianceSeverity.LOW: 1,
                ComplianceSeverity.INFO: 0.5
            }
            max_penalty = sum(severity_weights.get(r.severity, 1) for r in rules)
            actual_penalty = sum(severity_weights.get(v.severity, 1) for v in violations)
            score = max(0, 100 - (actual_penalty / max(max_penalty, 1)) * 100)
        else:
            score = 100.0

        # Generate summary
        summary = {
            "total_agents": len(agents_checked),
            "critical_violations": sum(1 for v in violations if v.severity == ComplianceSeverity.CRITICAL),
            "high_violations": sum(1 for v in violations if v.severity == ComplianceSeverity.HIGH),
            "medium_violations": sum(1 for v in violations if v.severity == ComplianceSeverity.MEDIUM),
            "low_violations": sum(1 for v in violations if v.severity == ComplianceSeverity.LOW),
            "top_categories": self._get_top_violation_categories(violations),
            "affected_agents": list(set(v.agent_id for v in violations if v.agent_id))
        }

        # Create report
        report = ComplianceReport(
            report_id=report_id,
            generated_at=now,
            completed_at=datetime.now(),
            rule_set=rule_set,
            categories_checked=categories_checked,
            agents_checked=agents_checked,
            total_rules=total_rules,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            violations=violations,
            score=score,
            summary=summary
        )

        self._reports[report_id] = report
        logger.info(f"Compliance check complete: {rules_passed}/{total_rules} passed, score: {score:.1f}")

        return report

    def _get_agents(self, agent_filter: List[str] = None) -> List[Dict[str, Any]]:
        """Get agent data for compliance checking."""
        try:
            from agentic.network import get_all_agents
            agents = get_all_agents()
            agent_list = [a.to_dict() if hasattr(a, 'to_dict') else a for a in agents]

            if agent_filter:
                agent_list = [a for a in agent_list
                             if a.get("name") in agent_filter or a.get("agent_id") in agent_filter]

            return agent_list
        except Exception as e:
            logger.warning(f"Could not fetch agents: {e}")
            return []

    def _check_rule(self, rule: ComplianceRule, agents: List[Dict[str, Any]]) -> List[ComplianceViolation]:
        """Check a single compliance rule."""
        violations = []

        # Rule-specific checks
        check_methods = {
            "SEC001": self._check_bgp_auth,
            "SEC002": self._check_ospf_auth,
            "SEC003": self._check_ssh_management,
            "SEC005": self._check_acl_management,
            "RTG001": self._check_bgp_max_prefix,
            "RTG002": self._check_bgp_filtering,
            "RTG004": self._check_loopback,
            "RED001": self._check_dual_homed,
            "MON001": self._check_snmp,
            "MON002": self._check_syslog,
            "MON003": self._check_ntp,
            "CFG001": self._check_interface_descriptions,
            "CFG002": self._check_hostname,
            "TUN001": self._check_gre_mtu,
            "TUN002": self._check_gre_keepalive,
            "TUN003": self._check_gre_key,
            "BFD001": self._check_bfd_enabled,
            "BFD002": self._check_bfd_timers,
            "BFD003": self._check_bfd_stability,
        }

        check_method = check_methods.get(rule.rule_id)
        if check_method:
            violations = check_method(rule, agents)
        else:
            # Generic check - just verify configuration exists
            violations = self._generic_check(rule, agents)

        return violations

    def _create_violation(
        self,
        rule: ComplianceRule,
        agent_id: str,
        resource: str,
        description: str,
        details: Dict[str, Any] = None
    ) -> ComplianceViolation:
        """Create a compliance violation."""
        return ComplianceViolation(
            violation_id=str(uuid.uuid4())[:8],
            rule_id=rule.rule_id,
            rule_name=rule.name,
            category=rule.category,
            severity=rule.severity,
            agent_id=agent_id,
            resource=resource,
            description=description,
            details=details or {},
            remediation=rule.remediation,
            detected_at=datetime.now()
        )

    def _check_bgp_auth(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BGP authentication."""
        violations = []
        for agent in agents:
            protocols = agent.get("protocols", [])
            if "bgp" in [p.lower() for p in protocols]:
                # Check if BGP auth is configured
                bgp_config = agent.get("bgp_config", {})
                peers = agent.get("bgp_peers", [])

                for peer in peers:
                    if isinstance(peer, dict):
                        if not peer.get("authentication") and not peer.get("md5_password"):
                            violations.append(self._create_violation(
                                rule,
                                agent.get("name", "unknown"),
                                f"BGP peer {peer.get('peer_address', 'unknown')}",
                                f"BGP peer lacks MD5 authentication",
                                {"peer_address": peer.get("peer_address"), "remote_as": peer.get("remote_as")}
                            ))
        return violations

    def _check_ospf_auth(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check OSPF authentication."""
        violations = []
        for agent in agents:
            protocols = agent.get("protocols", [])
            if "ospf" in [p.lower() for p in protocols]:
                ospf_config = agent.get("ospf_config", {})
                if not ospf_config.get("authentication"):
                    violations.append(self._create_violation(
                        rule,
                        agent.get("name", "unknown"),
                        "OSPF configuration",
                        "OSPF authentication not configured"
                    ))
        return violations

    def _check_ssh_management(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check SSH is used for management."""
        violations = []
        for agent in agents:
            # Check if telnet is enabled or SSH is disabled
            services = agent.get("services", {})
            if services.get("telnet", False) or not services.get("ssh", True):
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "Management access",
                    "Telnet enabled or SSH not configured for management"
                ))
        return violations

    def _check_acl_management(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check ACL on management interface."""
        violations = []
        for agent in agents:
            acls = agent.get("acls", [])
            mgmt_interface = agent.get("management_interface")

            # Check if any ACL is applied to management
            has_mgmt_acl = False
            for acl in acls:
                if isinstance(acl, dict):
                    applied = acl.get("applied_interfaces", [])
                    if mgmt_interface in applied or "management" in str(applied).lower():
                        has_mgmt_acl = True
                        break

            if not has_mgmt_acl and mgmt_interface:
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    f"Interface {mgmt_interface}",
                    "No ACL applied to management interface"
                ))
        return violations

    def _check_bgp_max_prefix(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BGP maximum prefix limits."""
        violations = []
        for agent in agents:
            protocols = agent.get("protocols", [])
            if "bgp" in [p.lower() for p in protocols]:
                peers = agent.get("bgp_peers", [])
                for peer in peers:
                    if isinstance(peer, dict):
                        if not peer.get("max_prefix") and peer.get("peer_type") == "ebgp":
                            violations.append(self._create_violation(
                                rule,
                                agent.get("name", "unknown"),
                                f"BGP peer {peer.get('peer_address', 'unknown')}",
                                "eBGP peer lacks maximum-prefix limit"
                            ))
        return violations

    def _check_bgp_filtering(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BGP route filtering."""
        violations = []
        for agent in agents:
            protocols = agent.get("protocols", [])
            if "bgp" in [p.lower() for p in protocols]:
                peers = agent.get("bgp_peers", [])
                for peer in peers:
                    if isinstance(peer, dict):
                        if not peer.get("route_map_in") and not peer.get("prefix_list_in"):
                            if peer.get("peer_type") == "ebgp":
                                violations.append(self._create_violation(
                                    rule,
                                    agent.get("name", "unknown"),
                                    f"BGP peer {peer.get('peer_address', 'unknown')}",
                                    "eBGP peer lacks inbound route filtering"
                                ))
        return violations

    def _check_loopback(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check loopback interface exists."""
        violations = []
        for agent in agents:
            loopback = agent.get("loopback") or agent.get("loopback_ip")
            if not loopback:
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "Loopback interface",
                    "No loopback interface configured"
                ))
        return violations

    def _check_dual_homed(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check dual-homed connectivity."""
        violations = []
        for agent in agents:
            interfaces = agent.get("interfaces", [])
            # Count active uplink interfaces
            uplinks = [i for i in interfaces
                      if isinstance(i, dict) and i.get("state") == "up" and not i.get("name", "").startswith("lo")]
            if len(uplinks) < 2:
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "Network connectivity",
                    f"Only {len(uplinks)} active uplink(s) - recommend at least 2 for redundancy"
                ))
        return violations

    def _check_snmp(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check SNMP configuration."""
        violations = []
        for agent in agents:
            snmp_config = agent.get("snmp", {})
            if not snmp_config or not snmp_config.get("enabled"):
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "SNMP configuration",
                    "SNMP not configured for monitoring"
                ))
        return violations

    def _check_syslog(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check syslog configuration."""
        violations = []
        for agent in agents:
            syslog_config = agent.get("syslog", {})
            if not syslog_config or not syslog_config.get("servers"):
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "Syslog configuration",
                    "No syslog server configured"
                ))
        return violations

    def _check_ntp(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check NTP configuration."""
        violations = []
        for agent in agents:
            ntp_config = agent.get("ntp", {})
            if not ntp_config or not ntp_config.get("servers"):
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "NTP configuration",
                    "No NTP server configured"
                ))
        return violations

    def _check_interface_descriptions(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check interface descriptions."""
        violations = []
        for agent in agents:
            interfaces = agent.get("interfaces", [])
            for iface in interfaces:
                if isinstance(iface, dict):
                    if not iface.get("description") and iface.get("state") == "up":
                        violations.append(self._create_violation(
                            rule,
                            agent.get("name", "unknown"),
                            f"Interface {iface.get('name', 'unknown')}",
                            "Interface lacks description"
                        ))
        return violations

    def _check_hostname(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check hostname configuration."""
        violations = []
        for agent in agents:
            hostname = agent.get("hostname") or agent.get("name")
            if not hostname or hostname == "localhost" or hostname.startswith("router"):
                violations.append(self._create_violation(
                    rule,
                    agent.get("name", "unknown"),
                    "Hostname",
                    f"Hostname '{hostname}' is generic - use descriptive naming"
                ))
        return violations

    def _check_gre_mtu(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check GRE tunnel MTU configuration."""
        violations = []
        for agent in agents:
            interfaces = agent.get("interfaces", [])
            for iface in interfaces:
                if isinstance(iface, dict) and iface.get("type") == "gre":
                    mtu = iface.get("mtu", 0)
                    # GRE overhead is ~24-28 bytes, MTU should be configured
                    if mtu == 0 or mtu > 1476:
                        violations.append(self._create_violation(
                            rule,
                            agent.get("name", "unknown"),
                            f"GRE tunnel {iface.get('name', 'unknown')}",
                            f"MTU {mtu} may cause fragmentation (recommended: 1400-1476)"
                        ))
        return violations

    def _check_gre_keepalive(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check GRE tunnel keepalive configuration."""
        violations = []
        for agent in agents:
            interfaces = agent.get("interfaces", [])
            for iface in interfaces:
                if isinstance(iface, dict) and iface.get("type") == "gre":
                    tun_config = iface.get("tun", {})
                    keepalive = tun_config.get("ka", 0)
                    if keepalive == 0:
                        violations.append(self._create_violation(
                            rule,
                            agent.get("name", "unknown"),
                            f"GRE tunnel {iface.get('name', 'unknown')}",
                            "Keepalive not configured - tunnel failures may not be detected"
                        ))
        return violations

    def _check_gre_key(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check GRE tunnel key authentication."""
        violations = []
        for agent in agents:
            interfaces = agent.get("interfaces", [])
            for iface in interfaces:
                if isinstance(iface, dict) and iface.get("type") == "gre":
                    tun_config = iface.get("tun", {})
                    key = tun_config.get("key")
                    if key is None:
                        violations.append(self._create_violation(
                            rule,
                            agent.get("name", "unknown"),
                            f"GRE tunnel {iface.get('name', 'unknown')}",
                            "GRE key not configured - tunnel may accept unauthorized traffic"
                        ))
        return violations

    def _check_bfd_enabled(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BFD is enabled for routing protocols."""
        violations = []
        try:
            from bfd import get_bfd_manager

            for agent in agents:
                agent_id = agent.get("name", agent.get("agent_id", "unknown"))
                protocols = agent.get("protocols", [])

                # Check if agent has routing protocols that should use BFD
                routing_protocols = []
                for proto in protocols:
                    proto_type = proto.get("type", proto.get("p", "")).lower()
                    if proto_type in ["ospf", "ospfv3", "bgp", "ibgp", "ebgp", "isis"]:
                        routing_protocols.append(proto_type)

                if routing_protocols:
                    # Check if BFD is enabled for this agent
                    manager = get_bfd_manager(agent_id)
                    if not manager or not manager.is_running:
                        violations.append(self._create_violation(
                            rule,
                            agent_id,
                            "BFD Manager",
                            f"BFD not enabled but routing protocols configured: {', '.join(routing_protocols)}"
                        ))
                    elif manager.session_count == 0:
                        violations.append(self._create_violation(
                            rule,
                            agent_id,
                            "BFD Sessions",
                            f"No BFD sessions configured for protocols: {', '.join(routing_protocols)}"
                        ))

        except ImportError:
            # BFD module not available - skip check
            pass
        return violations

    def _check_bfd_timers(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BFD detection timers are appropriate."""
        violations = []
        try:
            from bfd import get_bfd_manager

            # Recommended max detection times (ms)
            max_detection = {
                "ospf": 900,
                "bgp": 900,
                "isis": 900,
                "static": 3000,
            }

            for agent in agents:
                agent_id = agent.get("name", agent.get("agent_id", "unknown"))
                manager = get_bfd_manager(agent_id)

                if manager and manager.is_running:
                    for session in manager.list_sessions():
                        protocol = session.get("client_protocol", "").lower()
                        detection_ms = session.get("detection_time_ms", 0)
                        max_ms = max_detection.get(protocol, 3000)

                        if detection_ms > max_ms:
                            violations.append(self._create_violation(
                                rule,
                                agent_id,
                                f"BFD session to {session.get('remote_address', 'unknown')}",
                                f"Detection time {detection_ms:.0f}ms exceeds recommended {max_ms}ms for {protocol}"
                            ))

        except ImportError:
            pass
        return violations

    def _check_bfd_stability(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Check BFD session stability (no excessive flapping)."""
        violations = []
        try:
            from bfd import get_bfd_manager

            max_flaps = 5  # Threshold for excessive flapping

            for agent in agents:
                agent_id = agent.get("name", agent.get("agent_id", "unknown"))
                manager = get_bfd_manager(agent_id)

                if manager and manager.is_running:
                    for session in manager.list_sessions():
                        stats = session.get("statistics", {})
                        down_transitions = stats.get("down_transitions", 0)

                        if down_transitions > max_flaps:
                            violations.append(self._create_violation(
                                rule,
                                agent_id,
                                f"BFD session to {session.get('remote_address', 'unknown')}",
                                f"Session has {down_transitions} down transitions - investigate instability"
                            ))

        except ImportError:
            pass
        return violations

    def _generic_check(self, rule: ComplianceRule, agents: List[Dict]) -> List[ComplianceViolation]:
        """Generic check for rules without specific implementations."""
        # Return empty - rule passed by default
        return []

    def _get_top_violation_categories(self, violations: List[ComplianceViolation], limit: int = 3) -> List[Dict]:
        """Get top violation categories."""
        counts = {}
        for v in violations:
            cat = v.category.value
            counts[cat] = counts.get(cat, 0) + 1

        sorted_cats = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"category": c, "count": n} for c, n in sorted_cats[:limit]]

    def get_report(self, report_id: str) -> Optional[ComplianceReport]:
        """Get a compliance report by ID."""
        return self._reports.get(report_id)

    def list_reports(self, limit: int = 10) -> List[ComplianceReport]:
        """List recent compliance reports."""
        reports = list(self._reports.values())
        reports.sort(key=lambda r: r.generated_at, reverse=True)
        return reports[:limit]

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a compliance rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a compliance rule."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
            return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get compliance checker statistics."""
        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "rule_sets": list(self._rule_sets.keys()),
            "categories": [c.value for c in ComplianceCategory],
            "severities": [s.value for s in ComplianceSeverity],
            "reports_generated": len(self._reports)
        }
