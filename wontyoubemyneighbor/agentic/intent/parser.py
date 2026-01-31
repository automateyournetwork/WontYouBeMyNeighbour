"""
Intent Parser - Natural language to network intent

Parses user intents like:
- "I want high availability between DC1 and DC2"
- "Optimize traffic to prefer the 10G links"
- "Block traffic from AS 65000"
- "Enable redundant paths to the internet"
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("IntentParser")


class IntentType(Enum):
    """Types of network intents"""
    # Availability
    HIGH_AVAILABILITY = "high_availability"
    REDUNDANCY = "redundancy"
    FAILOVER = "failover"

    # Traffic Engineering
    TRAFFIC_OPTIMIZATION = "traffic_optimization"
    LOAD_BALANCING = "load_balancing"
    PATH_PREFERENCE = "path_preference"

    # Security
    TRAFFIC_BLOCK = "traffic_block"
    TRAFFIC_FILTER = "traffic_filter"
    ACCESS_CONTROL = "access_control"

    # Connectivity
    CONNECTIVITY = "connectivity"
    REACHABILITY = "reachability"
    ISOLATION = "isolation"

    # Performance
    LOW_LATENCY = "low_latency"
    HIGH_BANDWIDTH = "high_bandwidth"
    QOS = "qos"

    # Protocol
    PROTOCOL_ENABLE = "protocol_enable"
    PROTOCOL_DISABLE = "protocol_disable"
    PROTOCOL_CONFIGURE = "protocol_configure"

    # Unknown
    UNKNOWN = "unknown"


@dataclass
class IntentParameter:
    """
    Parameter extracted from intent

    Attributes:
        name: Parameter name
        value: Parameter value
        param_type: Parameter type (agent, network, metric, etc.)
        confidence: Extraction confidence (0.0-1.0)
    """
    name: str
    value: Any
    param_type: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "param_type": self.param_type,
            "confidence": self.confidence
        }


@dataclass
class Intent:
    """
    Parsed network intent

    Attributes:
        intent_id: Unique identifier
        intent_type: Type of intent
        raw_text: Original user input
        description: Normalized description
        parameters: Extracted parameters
        target_agents: Agents involved
        protocols: Protocols affected
        confidence: Parsing confidence
        validation_status: Whether intent is valid
    """
    intent_id: str
    intent_type: IntentType
    raw_text: str
    description: str
    parameters: List[IntentParameter] = field(default_factory=list)
    target_agents: List[str] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    confidence: float = 0.0
    validation_status: str = "pending"
    validation_errors: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "intent_type": self.intent_type.value,
            "raw_text": self.raw_text,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "target_agents": self.target_agents,
            "protocols": self.protocols,
            "confidence": self.confidence,
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors,
            "created_at": self.created_at.isoformat()
        }

    def add_parameter(self, name: str, value: Any, param_type: str, confidence: float = 1.0) -> None:
        """Add a parameter to the intent"""
        self.parameters.append(IntentParameter(
            name=name,
            value=value,
            param_type=param_type,
            confidence=confidence
        ))

    def get_parameter(self, name: str) -> Optional[Any]:
        """Get parameter value by name"""
        for param in self.parameters:
            if param.name == name:
                return param.value
        return None


class IntentParser:
    """
    Parses natural language into structured network intents
    """

    def __init__(self):
        """Initialize intent parser with pattern matchers"""
        self._intent_counter = 0

        # Intent patterns (regex -> (intent_type, description_template))
        self._patterns: List[Tuple[re.Pattern, IntentType, str]] = [
            # High Availability
            (re.compile(r'high\s*availability\s+(?:between|from)\s+(\w+)\s+(?:to|and)\s+(\w+)', re.I),
             IntentType.HIGH_AVAILABILITY,
             "Ensure high availability between {0} and {1}"),

            (re.compile(r'redundan(?:t|cy)\s+(?:path|route|link)s?\s+(?:to|for|between)\s+(.+)', re.I),
             IntentType.REDUNDANCY,
             "Configure redundant paths to {0}"),

            (re.compile(r'failover\s+(?:from|to)\s+(\w+)\s+(?:to|from)\s+(\w+)', re.I),
             IntentType.FAILOVER,
             "Set up failover from {0} to {1}"),

            # Traffic Engineering
            (re.compile(r'optimi[sz]e\s+(?:traffic|routing)\s+(?:to\s+)?(?:prefer|use)\s+(.+)', re.I),
             IntentType.TRAFFIC_OPTIMIZATION,
             "Optimize traffic to prefer {0}"),

            (re.compile(r'load\s*balanc(?:e|ing)\s+(?:across|between|to)\s+(.+)', re.I),
             IntentType.LOAD_BALANCING,
             "Enable load balancing across {0}"),

            (re.compile(r'prefer\s+(?:path|route|link)\s+(?:via|through)\s+(\w+)', re.I),
             IntentType.PATH_PREFERENCE,
             "Set path preference via {0}"),

            # Security
            (re.compile(r'block\s+(?:traffic|routes?)\s+(?:from|to)\s+(?:AS\s*)?(\d+|[\w\.]+)', re.I),
             IntentType.TRAFFIC_BLOCK,
             "Block traffic from {0}"),

            (re.compile(r'filter\s+(?:traffic|routes?)\s+(?:from|to)\s+(.+)', re.I),
             IntentType.TRAFFIC_FILTER,
             "Filter traffic from {0}"),

            (re.compile(r'deny\s+(?:access|traffic)\s+(?:from|to)\s+(.+)', re.I),
             IntentType.ACCESS_CONTROL,
             "Deny access from {0}"),

            # Connectivity
            (re.compile(r'connect\s+(\w+)\s+(?:to|with)\s+(\w+)', re.I),
             IntentType.CONNECTIVITY,
             "Establish connectivity between {0} and {1}"),

            (re.compile(r'(?:ensure|verify)\s+reachability\s+(?:to|from|between)\s+(.+)', re.I),
             IntentType.REACHABILITY,
             "Ensure reachability to {0}"),

            (re.compile(r'isolate\s+(\w+)\s+from\s+(.+)', re.I),
             IntentType.ISOLATION,
             "Isolate {0} from {1}"),

            # Performance
            (re.compile(r'low\s*latency\s+(?:path|route)?\s*(?:to|between)\s+(.+)', re.I),
             IntentType.LOW_LATENCY,
             "Configure low latency path to {0}"),

            (re.compile(r'(?:high|maximum)\s+bandwidth\s+(?:to|between)\s+(.+)', re.I),
             IntentType.HIGH_BANDWIDTH,
             "Maximize bandwidth to {0}"),

            (re.compile(r'qos\s+(?:for|on)\s+(.+)', re.I),
             IntentType.QOS,
             "Configure QoS for {0}"),

            # Protocol
            (re.compile(r'enable\s+(ospf|bgp|isis|mpls|vxlan|evpn|gre|bfd)\s+(?:on|for)\s+(.+)', re.I),
             IntentType.PROTOCOL_ENABLE,
             "Enable {0} on {1}"),

            (re.compile(r'disable\s+(ospf|bgp|isis|mpls|vxlan|evpn|gre|bfd)\s+(?:on|for)\s+(.+)', re.I),
             IntentType.PROTOCOL_DISABLE,
             "Disable {0} on {1}"),

            (re.compile(r'configure\s+(ospf|bgp|isis|mpls|vxlan|evpn|gre|bfd)\s+(.+)', re.I),
             IntentType.PROTOCOL_CONFIGURE,
             "Configure {0} {1}"),
        ]

        # Parameter extraction patterns
        self._param_patterns = {
            "agent": re.compile(r'\b(router|switch|spine|leaf|core|edge|border|dc|datacenter)[-_]?\d*\b', re.I),
            "network": re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?)\b'),
            "asn": re.compile(r'\bAS\s*(\d+)\b', re.I),
            "metric": re.compile(r'\b(?:metric|cost)\s*[=:]?\s*(\d+)\b', re.I),
            "bandwidth": re.compile(r'\b(\d+)\s*(?:g|gb|gbps|m|mb|mbps)\b', re.I),
            "interface": re.compile(r'\b(eth\d+|lo\d+|ge-\d+/\d+/\d+)\b', re.I),
            "protocol": re.compile(r'\b(ospf|bgp|isis|mpls|ldp|vxlan|evpn|rip|gre|bfd)\b', re.I),
            "area": re.compile(r'\barea\s*(\d+(?:\.\d+\.\d+\.\d+)?)\b', re.I),
            "vni": re.compile(r'\bvni\s*(\d+)\b', re.I),
        }

    def _generate_intent_id(self) -> str:
        """Generate unique intent ID"""
        self._intent_counter += 1
        return f"intent-{self._intent_counter:04d}"

    def parse(self, text: str) -> Intent:
        """
        Parse natural language text into an Intent

        Args:
            text: Natural language intent description

        Returns:
            Parsed Intent object
        """
        text = text.strip()
        intent_id = self._generate_intent_id()

        # Try to match against known patterns
        intent_type = IntentType.UNKNOWN
        description = text
        confidence = 0.0
        match_groups = []

        for pattern, itype, desc_template in self._patterns:
            match = pattern.search(text)
            if match:
                intent_type = itype
                match_groups = match.groups()
                description = desc_template.format(*match_groups)
                confidence = 0.8  # Pattern match confidence
                break

        # Create intent
        intent = Intent(
            intent_id=intent_id,
            intent_type=intent_type,
            raw_text=text,
            description=description,
            confidence=confidence
        )

        # Extract parameters
        self._extract_parameters(intent, text, match_groups)

        # Extract protocols
        self._extract_protocols(intent, text)

        # Extract target agents
        self._extract_agents(intent, text, match_groups)

        # Adjust confidence based on extractions
        if intent.parameters:
            intent.confidence = min(1.0, intent.confidence + 0.1)
        if intent.protocols:
            intent.confidence = min(1.0, intent.confidence + 0.05)
        if intent.target_agents:
            intent.confidence = min(1.0, intent.confidence + 0.05)

        logger.info(f"Parsed intent: {intent_id} ({intent_type.value}) - confidence: {intent.confidence:.2f}")
        return intent

    def _extract_parameters(self, intent: Intent, text: str, match_groups: List[str]) -> None:
        """Extract parameters from text"""
        for param_type, pattern in self._param_patterns.items():
            matches = pattern.findall(text)
            for i, match in enumerate(matches):
                # Avoid duplicating match groups as parameters
                if match not in match_groups:
                    intent.add_parameter(
                        name=f"{param_type}_{i+1}" if len(matches) > 1 else param_type,
                        value=match,
                        param_type=param_type
                    )

    def _extract_protocols(self, intent: Intent, text: str) -> None:
        """Extract protocols mentioned in intent"""
        protocol_pattern = self._param_patterns["protocol"]
        matches = protocol_pattern.findall(text.lower())
        intent.protocols = list(set(matches))

        # Infer protocols from intent type
        if intent.intent_type in [IntentType.HIGH_AVAILABILITY, IntentType.REDUNDANCY]:
            if "ospf" not in intent.protocols and "bgp" not in intent.protocols:
                # Could be either, leave for executor to decide
                pass

    def _extract_agents(self, intent: Intent, text: str, match_groups: List[str]) -> None:
        """Extract target agents from text"""
        agent_pattern = self._param_patterns["agent"]
        matches = agent_pattern.findall(text)
        intent.target_agents = list(set(matches))

        # Add match groups that look like agent names
        for group in match_groups:
            if group and re.match(r'^[\w-]+$', group) and group not in intent.target_agents:
                if not re.match(r'^\d+$', group):  # Not just a number
                    intent.target_agents.append(group)

    def validate(self, intent: Intent, available_agents: List[str]) -> bool:
        """
        Validate an intent against available resources

        Args:
            intent: Intent to validate
            available_agents: List of available agent IDs

        Returns:
            True if valid
        """
        intent.validation_errors = []

        # Check intent type is recognized
        if intent.intent_type == IntentType.UNKNOWN:
            intent.validation_errors.append("Could not determine intent type from description")

        # Check target agents exist
        for agent in intent.target_agents:
            if agent.lower() not in [a.lower() for a in available_agents]:
                intent.validation_errors.append(f"Unknown agent: {agent}")

        # Check required parameters for specific intents
        if intent.intent_type == IntentType.TRAFFIC_BLOCK:
            if not intent.get_parameter("asn") and not intent.get_parameter("network"):
                intent.validation_errors.append("Block intent requires ASN or network to block")

        if intent.intent_type in [IntentType.HIGH_AVAILABILITY, IntentType.CONNECTIVITY]:
            if len(intent.target_agents) < 2:
                intent.validation_errors.append("Availability/connectivity intents require at least 2 agents")

        # Set validation status
        if intent.validation_errors:
            intent.validation_status = "invalid"
            return False
        else:
            intent.validation_status = "valid"
            return True

    def suggest_intents(self, partial_text: str) -> List[str]:
        """
        Suggest complete intents based on partial input

        Args:
            partial_text: Partial intent text

        Returns:
            List of suggested completions
        """
        suggestions = []
        partial_lower = partial_text.lower()

        suggestion_templates = [
            "high availability between {agent1} and {agent2}",
            "redundant paths to {destination}",
            "failover from {primary} to {backup}",
            "optimize traffic to prefer {path}",
            "load balance across {agents}",
            "block traffic from AS {asn}",
            "connect {agent1} to {agent2}",
            "ensure reachability to {network}",
            "low latency path to {destination}",
            "enable {protocol} on {agents}",
            "configure {protocol} area {area}",
        ]

        for template in suggestion_templates:
            if partial_lower in template.lower() or template.lower().startswith(partial_lower):
                suggestions.append(template)

        return suggestions[:5]  # Return top 5


# Global parser instance
_global_parser: Optional[IntentParser] = None


def get_intent_parser() -> IntentParser:
    """Get or create the global intent parser"""
    global _global_parser
    if _global_parser is None:
        _global_parser = IntentParser()
    return _global_parser
