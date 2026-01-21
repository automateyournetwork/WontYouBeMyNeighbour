"""
Intent Parser

Transforms natural language queries into structured network intents.
Uses LLM to understand user intent and map to network operations.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import re
import json


class IntentType(str, Enum):
    """Types of network intents RubberBand can understand"""

    # Query intents
    QUERY_STATUS = "query_status"  # "What is the status of X?"
    QUERY_NEIGHBOR = "query_neighbor"  # "Show me my neighbors"
    QUERY_ROUTE = "query_route"  # "How do I reach 10.0.0.0/24?"
    QUERY_LSA = "query_lsa"  # "Show me LSAs from router X"
    QUERY_BGP_PEER = "query_bgp_peer"  # "What's the state of BGP peer X?"
    QUERY_RIB = "query_rib"  # "Show me the routing table"
    QUERY_ROUTER_ID = "query_router_id"  # "What is my router ID?"
    QUERY_INTERFACE = "query_interface"  # "What interfaces do I have?"
    QUERY_STATISTICS = "query_statistics"  # "Show me statistics"
    QUERY_PROTOCOL_STATUS = "query_protocol_status"  # "Is OSPF/BGP running?"
    QUERY_CAPABILITIES = "query_capabilities"  # "What capabilities did we negotiate?"
    QUERY_FIB = "query_fib"  # "What is my forwarding table?"
    QUERY_CHANGES = "query_changes"  # "Show me recent network changes"
    QUERY_METRICS = "query_metrics"  # "What metrics am I using?"

    # Analysis intents
    ANALYZE_TOPOLOGY = "analyze_topology"  # "Analyze the network topology"
    ANALYZE_PATH = "analyze_path"  # "Why is traffic going through X?"
    DETECT_ANOMALY = "detect_anomaly"  # "Are there any issues?"
    EXPLAIN_DECISION = "explain_decision"  # "Why did you choose this route?"
    ANALYZE_HEALTH = "analyze_health"  # "Is my network healthy?"

    # Action intents (require human approval)
    ACTION_ADJUST_METRIC = "action_adjust_metric"  # "Increase OSPF cost on eth0"
    ACTION_INJECT_ROUTE = "action_inject_route"  # "Advertise 10.0.0.0/24"
    ACTION_MODIFY_PREFERENCE = "action_modify_preference"  # "Prefer routes from AS 65001"
    ACTION_GRACEFUL_SHUTDOWN = "action_graceful_shutdown"  # "Gracefully shut down BGP"

    # Diagnostic intents
    DIAGNOSTIC_PING = "diagnostic_ping"  # "Ping 10.0.0.1"
    DIAGNOSTIC_TRACEROUTE = "diagnostic_traceroute"  # "Traceroute to 10.0.0.1"

    # Multi-agent intents
    COORDINATE_CONSENSUS = "coordinate_consensus"  # "All RubberBands agree on X?"
    GOSSIP_STATE = "gossip_state"  # "Share state with other RubberBands"

    # Unknown
    UNKNOWN = "unknown"


@dataclass
class NetworkIntent:
    """Structured representation of user intent"""

    intent_type: IntentType
    confidence: float  # 0.0 - 1.0
    parameters: Dict[str, Any]
    raw_query: str
    explanation: str  # Why this intent was chosen

    def requires_approval(self) -> bool:
        """Check if this intent requires human approval"""
        action_intents = {
            IntentType.ACTION_ADJUST_METRIC,
            IntentType.ACTION_INJECT_ROUTE,
            IntentType.ACTION_MODIFY_PREFERENCE,
            IntentType.ACTION_GRACEFUL_SHUTDOWN
        }
        return self.intent_type in action_intents

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "raw_query": self.raw_query,
            "explanation": self.explanation,
            "requires_approval": self.requires_approval()
        }


class IntentParser:
    """
    Parse natural language into structured network intents.

    Uses combination of:
    - Pattern matching for common queries
    - LLM-based understanding for complex queries
    - Context from network state
    """

    def __init__(self, llm_interface=None):
        self.llm = llm_interface
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for intent matching"""
        # Order matters! More specific patterns should be checked first
        self.patterns = {
            # Protocol status queries - check first
            IntentType.QUERY_PROTOCOL_STATUS: [
                r"is.*ospf.*running",
                r"is.*bgp.*running",
                r"ospf.*running",
                r"bgp.*running",
                r"protocol.*enabled",
                r"is.*running",
            ],
            # Capabilities queries
            IntentType.QUERY_CAPABILITIES: [
                r"capabilit",
                r"negotiate",
                r"what.*did.*we.*negotiate",
            ],
            # FIB/Forwarding table queries
            IntentType.QUERY_FIB: [
                r"forwarding.*table",
                r"fib\b",
                r"kernel.*route",
            ],
            # Recent changes queries
            IntentType.QUERY_CHANGES: [
                r"recent.*change",
                r"what.*changed",
                r"change.*history",
                r"state.*change",
            ],
            # Metrics queries
            IntentType.QUERY_METRICS: [
                r"what.*metric",
                r"metric.*using",
                r"ospf.*cost",
                r"link.*cost",
                r"med\b",
                r"local.*pref",
            ],
            # Router ID queries - check before general status
            IntentType.QUERY_ROUTER_ID: [
                r"router.?id",
                r"what.*my.*id",
                r"my.*router.*id",
            ],
            # LSA queries - check before general routes
            IntentType.QUERY_LSA: [
                r"lsa",
                r"link.?state.*advert",
                r"link.?state.*database",
                r"lsdb",
                r"show.*database",
            ],
            # Statistics queries
            IntentType.QUERY_STATISTICS: [
                r"statistic",
                r"stats\b",
                r"counter",
                r"how many.*total",
                r"message.*count",
            ],
            # Interface queries
            IntentType.QUERY_INTERFACE: [
                r"interface",
                r"what.*interface",
                r"my.*interface",
            ],
            # Health analysis
            IntentType.ANALYZE_HEALTH: [
                r"health",
                r"healthy",
                r"network.*ok",
                r"everything.*ok",
                r"are.*you.*ok",
                r"how.*are.*you",
            ],
            # Topology analysis
            IntentType.ANALYZE_TOPOLOGY: [
                r"topology",
                r"analyze.*network",
                r"network.*analys",
            ],
            # BGP peer queries - specific BGP patterns (check BEFORE neighbor)
            IntentType.QUERY_BGP_PEER: [
                r"bgp.*peer",
                r"bgp.*session",
                r"bgp.*neighbo[u]?r",
                r"show.*bgp",
                r"bgp.*summary",
                r"bgp.*established",
                r"ebgp|ibgp",
                r"what.*as\b",
                r"local.*as",
                r"peer.*as",
                r"autonomous.*system",
            ],
            # OSPF neighbor queries - specific OSPF patterns
            IntentType.QUERY_NEIGHBOR: [
                r"ospf.*neighbo[u]?r",
                r"show.*ospf",
                r"ospf.*adjacenc",
                r"ospf.*full",
                r"how many.*neighbo[u]?r",
                r"neighbo[u]?r.*state",
                r"neighbo[u]?r.*full",
                r"list.*neighbo[u]?r",
                r"my.*neighbo[u]?r",
                r"neighbo[u]?r.*do i have",
                r"do i have.*neighbo[u]?r",
            ],
            # Specific route lookup (with IP address)
            IntentType.QUERY_ROUTE: [
                r"how.*reach.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"route.*to.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"path.*to.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"next.*hop.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"best.*path.*?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
            ],
            # General routing table queries
            IntentType.QUERY_RIB: [
                r"routing.*table",
                r"show.*route",
                r"what.*route",
                r"my.*route",
                r"list.*route",
                r"all.*route",
                r"how many.*route",
                r"receiving.*route",
                r"bgp.*route",
                r"advertis",
                r"prefix",
                r"rib\b",
                r"fib\b",
            ],
            # Status queries
            IntentType.QUERY_STATUS: [
                r"status",
                r"what.*running",
                r"show.*overview",
                r"protocol.*running",
                r"what.*area",
                r"hello.*interval",
                r"dead.*interval",
                r"hold.*time",
                r"network.*type",
                r"what.*version",
                r"dr\b|bdr\b",
                r"tell.*me.*about.*(?:your|the).*state",
                r"what.*(?:can|do).*you.*tell.*me",
                r"summarize",
                r"summary",
                r"overview",
                r"what.*do.*you.*know",
                r"describe.*(?:your|the).*state",
                r"what.*(?:is|are).*your.*state",
            ],
            # Explain routing decisions
            IntentType.EXPLAIN_DECISION: [
                r"explain.*rout",
                r"why.*route",
                r"why.*path",
                r"routing.*decision",
                r"why.*chose",
                r"why.*select",
            ],
            # Anomaly detection
            IntentType.DETECT_ANOMALY: [
                r"issue",
                r"problem",
                r"wrong",
                r"anomal",
                r"detect",
                r"alert",
                r"flapping",
                r"loop",
            ],
            # Diagnostic intents - Ping (with optional source)
            IntentType.DIAGNOSTIC_PING: [
                # Ping with source: "ping x.x.x.x from y.y.y.y"
                r"ping\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+from\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"ping\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(?:using|with)\s+(?:source\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                # Standard ping (no source)
                r"ping\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"ping\s+to\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"can\s+(?:i|you|we)\s+reach\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"is\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+reachable",
                r"check\s+connectivity\s+to\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"test\s+connectivity\s+to\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
            ],
            # Diagnostic intents - Traceroute
            IntentType.DIAGNOSTIC_TRACEROUTE: [
                r"traceroute\s+(?:to\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"tracert\s+(?:to\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"trace\s+(?:route\s+)?(?:to\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"show\s+path\s+to\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
                r"what\s+(?:is\s+)?(?:the\s+)?path\s+to\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})",
            ],
            # Action intents
            IntentType.ACTION_ADJUST_METRIC: [
                r"increase.*cost",
                r"decrease.*cost",
                r"change.*metric",
                r"adjust.*metric",
            ],
            IntentType.ACTION_INJECT_ROUTE: [
                r"advertise.*route",
                r"inject.*route",
                r"announce.*prefix",
            ],
        }

    async def parse(self, query: str, context: Optional[Dict[str, Any]] = None) -> NetworkIntent:
        """
        Parse natural language query into structured intent.

        Args:
            query: Natural language query from user
            context: Optional network context for better understanding

        Returns:
            NetworkIntent with type, parameters, and confidence
        """
        query_lower = query.lower()

        # Try pattern matching first (fast path)
        pattern_match = self._pattern_match(query_lower)
        if pattern_match and pattern_match["confidence"] > 0.8:
            return NetworkIntent(
                intent_type=pattern_match["intent_type"],
                confidence=pattern_match["confidence"],
                parameters=pattern_match["parameters"],
                raw_query=query,
                explanation=f"Pattern matched: {pattern_match['pattern']}"
            )

        # Fall back to LLM for complex queries
        if self.llm:
            return await self._llm_parse(query, context)

        # Default to unknown if no LLM available
        return NetworkIntent(
            intent_type=IntentType.UNKNOWN,
            confidence=0.0,
            parameters={},
            raw_query=query,
            explanation="No LLM available for complex query parsing"
        )

    def _pattern_match(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Fast pattern matching for common queries.

        Returns dict with intent_type, confidence, parameters, and pattern.
        """
        for intent_type, patterns in self.patterns.items():
            for pattern in patterns:
                match = re.search(pattern, query)
                if match:
                    parameters = {}

                    # Extract parameters from regex groups
                    if match.groups():
                        if intent_type == IntentType.QUERY_ROUTE:
                            parameters["destination"] = match.group(1)
                        elif intent_type == IntentType.DIAGNOSTIC_PING:
                            parameters["target"] = match.group(1)
                            # Check for source IP (second capture group)
                            if len(match.groups()) >= 2 and match.group(2):
                                parameters["source"] = match.group(2)
                        elif intent_type == IntentType.DIAGNOSTIC_TRACEROUTE:
                            parameters["target"] = match.group(1)
                            # Check for source IP (second capture group)
                            if len(match.groups()) >= 2 and match.group(2):
                                parameters["source"] = match.group(2)

                    return {
                        "intent_type": intent_type,
                        "confidence": 0.9,
                        "parameters": parameters,
                        "pattern": pattern
                    }

        return None

    async def _llm_parse(self, query: str, context: Optional[Dict[str, Any]] = None) -> NetworkIntent:
        """
        Use LLM to parse complex queries into intents.

        Sends structured prompt to LLM asking it to classify the intent.
        """
        # Build prompt for LLM
        prompt = self._build_intent_prompt(query, context)

        # Query LLM
        response = await self.llm.query(prompt, temperature=0.3, max_tokens=500)

        # Parse LLM response
        try:
            intent_data = self._parse_llm_response(response)
            return NetworkIntent(
                intent_type=IntentType(intent_data["intent_type"]),
                confidence=intent_data["confidence"],
                parameters=intent_data.get("parameters", {}),
                raw_query=query,
                explanation=intent_data.get("explanation", "LLM-based parsing")
            )
        except Exception as e:
            # Fall back to unknown on parse error
            return NetworkIntent(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                parameters={},
                raw_query=query,
                explanation=f"LLM parsing error: {e}"
            )

    def _build_intent_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build prompt for LLM intent classification"""
        intent_types = [it.value for it in IntentType]

        prompt_parts = [
            "Classify the following network query into one of these intent types:",
            "",
            "Intent Types:",
        ]

        # List all intent types with descriptions
        intent_descriptions = {
            "query_status": "User wants to know the general status/state",
            "query_neighbor": "User wants to see OSPF/BGP neighbors",
            "query_route": "User wants to know the route to a destination",
            "query_lsa": "User wants to see OSPF LSAs",
            "query_bgp_peer": "User wants BGP peer information",
            "query_rib": "User wants to see the routing table",
            "analyze_topology": "User wants topology analysis",
            "analyze_path": "User wants path analysis/explanation",
            "detect_anomaly": "User wants to detect issues/problems",
            "explain_decision": "User wants explanation of routing decision",
            "action_adjust_metric": "User wants to change OSPF cost/metric",
            "action_inject_route": "User wants to advertise a new route",
            "action_modify_preference": "User wants to change route preferences",
            "action_graceful_shutdown": "User wants to gracefully shutdown protocols",
            "coordinate_consensus": "Multi-agent coordination",
            "gossip_state": "Multi-agent state sharing",
            "unknown": "Query doesn't match known patterns"
        }

        for intent, desc in intent_descriptions.items():
            prompt_parts.append(f"- {intent}: {desc}")

        prompt_parts.extend([
            "",
            f"Query: \"{query}\"",
            "",
            "Respond with JSON:",
            "{",
            '  "intent_type": "...",',
            '  "confidence": 0.0-1.0,',
            '  "parameters": {...},',
            '  "explanation": "why you chose this intent"',
            "}"
        ])

        return "\n".join(prompt_parts)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        # Extract JSON from response (might have extra text)
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            raise ValueError("No JSON found in LLM response")

    def get_supported_intents(self) -> List[str]:
        """Get list of all supported intent types"""
        return [intent.value for intent in IntentType]
