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
    """Types of network intents ASI can understand"""

    # Query intents
    QUERY_STATUS = "query_status"
    QUERY_NEIGHBOR = "query_neighbor"
    QUERY_ROUTE = "query_route"
    QUERY_LSA = "query_lsa"
    QUERY_BGP_PEER = "query_bgp_peer"
    QUERY_RIB = "query_rib"
    QUERY_ROUTER_ID = "query_router_id"
    QUERY_INTERFACE = "query_interface"
    QUERY_STATISTICS = "query_statistics"
    QUERY_PROTOCOL_STATUS = "query_protocol_status"
    QUERY_CAPABILITIES = "query_capabilities"
    QUERY_FIB = "query_fib"
    QUERY_CHANGES = "query_changes"
    QUERY_METRICS = "query_metrics"

    # Analysis intents
    ANALYZE_TOPOLOGY = "analyze_topology"
    ANALYZE_PATH = "analyze_path"
    DETECT_ANOMALY = "detect_anomaly"
    EXPLAIN_DECISION = "explain_decision"
    ANALYZE_HEALTH = "analyze_health"

    # Action intents (require human approval)
    ACTION_ADJUST_METRIC = "action_adjust_metric"
    ACTION_INJECT_ROUTE = "action_inject_route"
    ACTION_MODIFY_PREFERENCE = "action_modify_preference"
    ACTION_GRACEFUL_SHUTDOWN = "action_graceful_shutdown"

    # Diagnostic intents
    DIAGNOSTIC_PING = "diagnostic_ping"
    DIAGNOSTIC_TRACEROUTE = "diagnostic_traceroute"

    # Notification intents
    SEND_EMAIL = "send_email"

    # Subnet/IP calculation intents
    CALCULATE_SUBNET = "calculate_subnet"
    ANALYZE_IP = "analyze_ip"

    # Multi-agent intents
    COORDINATE_CONSENSUS = "coordinate_consensus"
    GOSSIP_STATE = "gossip_state"

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

    Uses LLM for natural language understanding - no hardcoded patterns.
    The LLM interprets user queries and maps them to intent types.
    """

    def __init__(self, llm_interface=None):
        self.llm = llm_interface

    async def parse(self, query: str, context: Optional[Dict[str, Any]] = None) -> NetworkIntent:
        """
        Parse natural language query into structured intent using LLM.

        Args:
            query: Natural language query from user
            context: Optional network context for better understanding

        Returns:
            NetworkIntent with type, parameters, and confidence
        """
        # Use LLM for all intent parsing
        if self.llm:
            return await self._llm_parse(query, context)

        # Fallback if no LLM available
        return NetworkIntent(
            intent_type=IntentType.UNKNOWN,
            confidence=0.0,
            parameters={},
            raw_query=query,
            explanation="No LLM available for query parsing"
        )

    async def _llm_parse(self, query: str, context: Optional[Dict[str, Any]] = None) -> NetworkIntent:
        """
        Use LLM to parse queries into intents.
        """
        prompt = self._build_intent_prompt(query, context)

        try:
            response = await self.llm.query(prompt, temperature=0.3, max_tokens=500)
            intent_data = self._parse_llm_response(response)

            # Extract any IP addresses or other parameters from the query
            parameters = intent_data.get("parameters", {})
            parameters = self._extract_parameters(query, intent_data.get("intent_type", "unknown"), parameters)

            return NetworkIntent(
                intent_type=IntentType(intent_data["intent_type"]),
                confidence=intent_data.get("confidence", 0.9),
                parameters=parameters,
                raw_query=query,
                explanation=intent_data.get("explanation", "LLM interpretation")
            )
        except Exception as e:
            return NetworkIntent(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                parameters={},
                raw_query=query,
                explanation=f"LLM parsing error: {e}"
            )

    def _extract_parameters(self, query: str, intent_type: str, existing_params: Dict) -> Dict[str, Any]:
        """
        Extract structured parameters (like IP addresses) from the query.
        This is post-processing after LLM classification, not intent detection.
        """
        params = existing_params.copy()

        # Extract CIDR notation for subnet queries (IPv4 and IPv6)
        cidr_v4_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})'
        cidr_v6_pattern = r'([0-9a-fA-F:]+::[0-9a-fA-F:]*(?:/\d{1,3})?|[0-9a-fA-F:]+/\d{1,3})'

        if intent_type in ['calculate_subnet', 'analyze_ip']:
            # Try IPv4 CIDR first
            cidrs_v4 = re.findall(cidr_v4_pattern, query)
            if cidrs_v4 and 'cidr' not in params:
                params['cidr'] = cidrs_v4[0]
            else:
                # Try IPv6 CIDR
                cidrs_v6 = re.findall(cidr_v6_pattern, query)
                if cidrs_v6 and 'cidr' not in params:
                    params['cidr'] = cidrs_v6[0]
                else:
                    # Try plain IPv4
                    ip_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
                    ips = re.findall(ip_pattern, query)
                    if ips and 'cidr' not in params:
                        params['cidr'] = ips[0]

        # Extract IP addresses for relevant intents
        ip_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        ips = re.findall(ip_pattern, query)

        if ips:
            if intent_type in ['diagnostic_ping', 'diagnostic_traceroute', 'query_route']:
                if 'target' not in params:
                    params['target'] = ips[0]
                if len(ips) > 1 and 'source' not in params:
                    params['source'] = ips[1]
            elif intent_type == 'query_route':
                if 'destination' not in params:
                    params['destination'] = ips[0]

        # Extract email addresses for email intent
        if intent_type == 'send_email':
            email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
            emails = re.findall(email_pattern, query)
            if emails and 'recipient' not in params:
                params['recipient'] = emails[0]

        return params

    def _build_intent_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build prompt for LLM intent classification"""

        # All supported intent types with descriptions
        intent_descriptions = {
            "query_status": "General status inquiry about the agent or network",
            "query_neighbor": "Questions about OSPF neighbors or adjacencies",
            "query_route": "Questions about how to reach a specific destination",
            "query_lsa": "Questions about OSPF LSAs or link-state database",
            "query_bgp_peer": "Questions about BGP peers, sessions, or AS numbers",
            "query_rib": "Questions about the routing table, routes, or prefixes",
            "query_router_id": "Questions about the router ID",
            "query_interface": "Questions about interfaces or ports",
            "query_statistics": "Questions about counters, statistics, or message counts",
            "query_protocol_status": "Questions about whether protocols are running",
            "query_capabilities": "Questions about negotiated capabilities",
            "query_fib": "Questions about the forwarding table",
            "query_changes": "Questions about recent network changes",
            "query_metrics": "Questions about OSPF costs, BGP metrics, etc.",
            "analyze_topology": "Requests to analyze or describe the network topology",
            "analyze_path": "Requests to explain traffic paths or routing decisions",
            "detect_anomaly": "Requests to find issues, problems, or anomalies",
            "explain_decision": "Requests to explain why a route was chosen",
            "analyze_health": "Questions about network or agent health",
            "action_adjust_metric": "Requests to change OSPF cost or routing metrics",
            "action_inject_route": "Requests to advertise or inject routes",
            "action_modify_preference": "Requests to change route preferences",
            "action_graceful_shutdown": "Requests to shut down protocols gracefully",
            "diagnostic_ping": "Requests to ping an IP address",
            "diagnostic_traceroute": "Requests to traceroute to an IP address",
            "send_email": "Requests to send email, reports, or notifications",
            "calculate_subnet": "Requests to calculate subnet information for an IPv4 or IPv6 CIDR (e.g., '192.168.1.0/24', 'what subnet is 10.0.0.0/8')",
            "analyze_ip": "Questions about IP addresses, their classification, or properties (e.g., 'what type of IP is 10.0.0.1', 'is this IP private')",
            "coordinate_consensus": "Multi-agent coordination requests",
            "gossip_state": "Multi-agent state sharing requests",
            "unknown": "Query that doesn't fit any category"
        }

        prompt = f"""You are a network agent assistant. Classify the user's query into the most appropriate intent type.

USER QUERY: "{query}"

AVAILABLE INTENT TYPES:
"""
        for intent, desc in intent_descriptions.items():
            prompt += f"- {intent}: {desc}\n"

        prompt += """
Analyze the user's query and respond with JSON:
{
  "intent_type": "<one of the intent types above>",
  "confidence": <0.0 to 1.0>,
  "parameters": {<any relevant parameters extracted from the query>},
  "explanation": "<brief explanation of why you chose this intent>"
}

Important:
- Choose the most specific intent that matches
- For email/report requests, use "send_email"
- For general questions about state or status, use "query_status"
- Extract any IP addresses, email addresses, or other parameters
- Respond ONLY with valid JSON, no other text
"""
        return prompt

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
