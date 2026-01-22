"""
Agentic Bridge

Main integration point between the agentic layer and protocol implementations.
Orchestrates LLM queries, decision-making, and autonomous actions.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

from ..llm.interface import LLMInterface, LLMProvider
from ..reasoning.intent_parser import IntentParser, IntentType
from ..reasoning.decision_engine import DecisionEngine
from ..actions.executor import ActionExecutor
from ..actions.safety import SafetyConstraints
from ..knowledge.state_manager import NetworkStateManager
from ..knowledge.analytics import NetworkAnalytics
from ..multi_agent.gossip import GossipProtocol
from ..multi_agent.consensus import ConsensusEngine
from ..mcp.gait_mcp import GAITClient, GAITEventType, GAITActor, get_gait_client


class AgenticBridge:
    """
    Main bridge connecting agentic intelligence to network protocols.

    This is the primary interface for natural language network management.
    """

    def __init__(
        self,
        asi_id: str,
        openai_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        autonomous_mode: bool = False
    ):
        self.asi_id = asi_id

        # Initialize LLM interface
        self.llm = LLMInterface(
            max_turns=75,
            preferred_provider=LLMProvider.CLAUDE,
            openai_key=openai_key,
            claude_key=claude_key,
            gemini_key=gemini_key
        )

        # Initialize reasoning layer
        self.intent_parser = IntentParser(llm_interface=self.llm)
        self.decision_engine = DecisionEngine(llm_interface=self.llm)

        # Initialize action layer
        self.safety = SafetyConstraints()
        self.safety.set_autonomous_mode(autonomous_mode)
        self.executor = ActionExecutor(safety_constraints=self.safety)

        # Initialize knowledge layer
        self.state_manager = NetworkStateManager(snapshot_retention=100)
        self.analytics = NetworkAnalytics(self.state_manager)

        # Initialize multi-agent layer
        self.gossip = GossipProtocol(asi_id=asi_id)
        self.consensus = ConsensusEngine(asi_id=asi_id, gossip_protocol=self.gossip)

        # Protocol connectors (set via dependency injection)
        self.ospf_connector = None
        self.bgp_connector = None

        # Full agent configuration (interfaces, protocols, etc.)
        self.agent_config: Optional[Dict[str, Any]] = None
        self.interfaces: List[Dict[str, Any]] = []

        # GAIT: Conversation and action history tracking
        self.conversation_history: List[Dict[str, Any]] = []
        self.action_history: List[Dict[str, Any]] = []
        self._max_history_length = 1000  # Maximum items to retain

        # GAIT MCP Client for persistent audit trail
        self.gait_client: GAITClient = get_gait_client(asi_id)
        self._gait_initialized = False

        # State update task
        self._state_update_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self):
        """Initialize all agentic components"""
        print(f"[AgenticBridge] Initializing ASI {self.asi_id}...")

        # Initialize LLM providers
        await self.llm.initialize_providers()

        # Initialize GAIT for conversation tracking
        if not self._gait_initialized:
            gait_result = await self.gait_client.init()
            if gait_result.get("success"):
                self._gait_initialized = True
                print(f"[AgenticBridge] GAIT initialized for {self.asi_id}")
            else:
                print(f"[AgenticBridge] GAIT init failed: {gait_result.get('error')}")

        # Register gossip handlers
        self._register_gossip_handlers()

        print(f"[AgenticBridge] Initialization complete")

    def set_ospf_connector(self, connector):
        """Inject OSPF connector"""
        self.ospf_connector = connector
        self.state_manager.set_protocol_handlers(ospf_interface=connector.interface)
        self.executor.set_protocol_handlers(ospf_interface=connector.interface)

    def set_bgp_connector(self, connector):
        """Inject BGP connector"""
        self.bgp_connector = connector
        self.state_manager.set_protocol_handlers(bgp_speaker=connector.speaker)
        self.executor.set_protocol_handlers(bgp_speaker=connector.speaker)

    def set_agent_config(self, config: Dict[str, Any]):
        """
        Set full agent configuration for LLM visibility.

        This gives the LLM access to all interfaces, protocols, and config.
        """
        self.agent_config = config

        # Extract interfaces (support both 'ifs' and 'interfaces' keys)
        raw_ifs = config.get('ifs') or config.get('interfaces', [])
        self.interfaces = []
        for iface in raw_ifs:
            self.interfaces.append({
                'id': iface.get('id') or iface.get('n'),
                'name': iface.get('n') or iface.get('name'),
                'type': iface.get('t') or iface.get('type', 'eth'),
                'addresses': iface.get('a') or iface.get('addresses', []),
                'status': iface.get('s') or iface.get('status', 'up'),
                'mtu': iface.get('mtu', 1500),
                'description': iface.get('description', '')
            })

        # Pass interfaces to state manager
        self.state_manager.set_interfaces(self.interfaces)

        print(f"[AgenticBridge] Loaded agent config with {len(self.interfaces)} interfaces")

    async def process_message(self, user_message: str) -> str:
        """
        Process natural language message (alias for query).

        This is the WebUI entry point for chat messages.
        """
        return await self.query(user_message)

    async def query(self, user_message: str) -> str:
        """
        Process natural language query.

        This is the main entry point for human interaction.
        """
        # Record user message in conversation history (GAIT)
        self._record_conversation('user', user_message)

        # Update network state
        await self.state_manager.update_state()
        context = self.state_manager.get_llm_context()
        self.llm.update_network_context(context)

        # Parse intent
        intent = await self.intent_parser.parse(user_message, context)

        print(f"[AgenticBridge] Parsed intent: {intent.intent_type.value} (confidence: {intent.confidence:.2f})")

        # Handle based on intent type - response will be recorded centrally
        response = None

        if intent.intent_type == IntentType.QUERY_NEIGHBOR:
            response = await self._handle_query_neighbors(intent)

        elif intent.intent_type == IntentType.QUERY_ROUTE:
            response = await self._handle_query_route(intent)

        elif intent.intent_type == IntentType.QUERY_STATUS:
            response = await self._handle_query_status(intent)

        elif intent.intent_type == IntentType.QUERY_BGP_PEER:
            response = await self._handle_query_bgp_peers(intent)

        elif intent.intent_type == IntentType.QUERY_RIB:
            response = await self._handle_query_rib(intent)

        elif intent.intent_type == IntentType.DETECT_ANOMALY:
            response = await self._handle_detect_anomaly(intent)

        elif intent.intent_type == IntentType.ANALYZE_TOPOLOGY:
            response = await self._handle_analyze_topology(intent)

        elif intent.intent_type == IntentType.EXPLAIN_DECISION:
            response = await self._handle_explain_decision(intent)

        elif intent.intent_type == IntentType.ACTION_ADJUST_METRIC:
            response = await self._handle_action_adjust_metric(intent)

        elif intent.intent_type == IntentType.ACTION_INJECT_ROUTE:
            response = await self._handle_action_inject_route(intent)

        elif intent.intent_type == IntentType.QUERY_ROUTER_ID:
            response = await self._handle_query_router_id(intent)

        elif intent.intent_type == IntentType.QUERY_LSA:
            response = await self._handle_query_lsa(intent)

        elif intent.intent_type == IntentType.QUERY_STATISTICS:
            response = await self._handle_query_statistics(intent)

        elif intent.intent_type == IntentType.QUERY_INTERFACE:
            response = await self._handle_query_interface(intent)

        elif intent.intent_type == IntentType.ANALYZE_HEALTH:
            response = await self._handle_analyze_health(intent)

        elif intent.intent_type == IntentType.QUERY_PROTOCOL_STATUS:
            response = await self._handle_query_protocol_status(intent)

        elif intent.intent_type == IntentType.QUERY_CAPABILITIES:
            response = await self._handle_query_capabilities(intent)

        elif intent.intent_type == IntentType.QUERY_FIB:
            response = await self._handle_query_fib(intent)

        elif intent.intent_type == IntentType.QUERY_CHANGES:
            response = await self._handle_query_changes(intent)

        elif intent.intent_type == IntentType.QUERY_METRICS:
            response = await self._handle_query_metrics(intent)

        elif intent.intent_type == IntentType.DIAGNOSTIC_PING:
            response = await self._handle_ping(intent)

        elif intent.intent_type == IntentType.DIAGNOSTIC_TRACEROUTE:
            response = await self._handle_traceroute(intent)

        else:
            # Use LLM for complex queries
            response = await self.llm.query(user_message)
            response = response or "I'm not sure how to help with that."

        # Record assistant response centrally for ALL handlers (GAIT tracking)
        # Use async version to ensure GAIT recording completes before returning
        if response:
            await self._record_conversation_async('assistant', response)

        return response

    def _record_conversation(self, role: str, content: str) -> None:
        """
        Record a conversation message for GAIT tracking (fire-and-forget).

        Args:
            role: 'user' or 'assistant'
            content: Message content
        """
        self.conversation_history.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })

        # Trim history if too long
        if len(self.conversation_history) > self._max_history_length:
            self.conversation_history = self.conversation_history[-self._max_history_length:]

        # Also record to GAIT for persistent audit trail (fire-and-forget)
        if self._gait_initialized:
            asyncio.create_task(self._record_to_gait(role, content))

    async def _record_conversation_async(self, role: str, content: str) -> None:
        """
        Record a conversation message for GAIT tracking (await-able version).

        Use this for assistant responses to ensure GAIT recording completes
        before returning to the client.

        Args:
            role: 'user' or 'assistant'
            content: Message content
        """
        self.conversation_history.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })

        # Trim history if too long
        if len(self.conversation_history) > self._max_history_length:
            self.conversation_history = self.conversation_history[-self._max_history_length:]

        # Also record to GAIT for persistent audit trail (await for completion)
        if self._gait_initialized:
            await self._record_to_gait(role, content)

    async def _record_to_gait(self, role: str, content: str) -> None:
        """Record conversation turn to GAIT asynchronously"""
        try:
            if role == 'user':
                await self.gait_client.record_turn(
                    user_text=content,
                    assistant_text="",
                    event_type=GAITEventType.USER_PROMPT,
                    actor=GAITActor.USER,
                    note="Chat message from user"
                )
            else:
                await self.gait_client.record_turn(
                    user_text="",
                    assistant_text=content,
                    event_type=GAITEventType.AGENT_RESPONSE,
                    actor=GAITActor.AGENT,
                    note="Chat response from agent"
                )
        except Exception as e:
            print(f"[AgenticBridge] Failed to record to GAIT: {e}")

    def _record_action(self, action: str, result: Any, success: bool = True) -> None:
        """
        Record an action execution for GAIT tracking.

        Args:
            action: Action name/type
            result: Action result or error message
            success: Whether the action succeeded
        """
        self.action_history.append({
            'action': action,
            'result': str(result) if result else '',
            'success': success,
            'timestamp': datetime.now().isoformat()
        })

        # Trim history if too long
        if len(self.action_history) > self._max_history_length:
            self.action_history = self.action_history[-self._max_history_length:]

        # Also record to GAIT
        if self._gait_initialized:
            asyncio.create_task(self._record_action_to_gait(action, result, success))

    async def _record_action_to_gait(self, action: str, result: Any, success: bool) -> None:
        """Record action to GAIT asynchronously"""
        try:
            await self.gait_client.record_turn(
                user_text=f"Action: {action}",
                assistant_text=str(result)[:500] if result else "",
                event_type=GAITEventType.MCP_CALL if action.startswith("mcp_") else GAITEventType.SYSTEM,
                actor=GAITActor.AGENT,
                note=f"Action {'succeeded' if success else 'failed'}: {action}",
                artifacts=[{
                    "type": "action_result",
                    "action": action,
                    "success": success,
                    "result_preview": str(result)[:200] if result else ""
                }]
            )
        except Exception as e:
            print(f"[AgenticBridge] Failed to record action to GAIT: {e}")

    async def get_gait_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get GAIT conversation history for UI display.

        Returns:
            List of history items formatted for the GAIT timeline
        """
        if not self._gait_initialized:
            # Return local history if GAIT not initialized
            history = []
            for item in self.conversation_history[-limit:]:
                history.append({
                    "type": "user" if item["role"] == "user" else "agent",
                    "sender": "User" if item["role"] == "user" else "Agent",
                    "message": item["content"],
                    "timestamp": item["timestamp"]
                })
            return history

        # Get from GAIT client
        try:
            commits = await self.gait_client.get_history(limit=limit)
            history = []
            for commit in reversed(commits):  # Oldest first
                item_type = "user" if commit.event_type == GAITEventType.USER_PROMPT else \
                           "agent" if commit.event_type == GAITEventType.AGENT_RESPONSE else \
                           "action" if commit.event_type in [GAITEventType.MCP_CALL, GAITEventType.CONFIG_CHANGE] else "system"

                sender = "User" if commit.actor == GAITActor.USER else \
                        "Agent" if commit.actor == GAITActor.AGENT else \
                        "System"

                # Extract message content
                details = commit.details
                message = details.get("user_text") or details.get("assistant_text") or commit.message

                history.append({
                    "type": item_type,
                    "sender": sender,
                    "message": message,
                    "timestamp": commit.timestamp,
                    "commit_id": commit.commit_id
                })
            return history
        except Exception as e:
            print(f"[AgenticBridge] Failed to get GAIT history: {e}")
            return []

    def get_gait_status(self) -> Dict[str, Any]:
        """Get GAIT status for UI display"""
        if not self._gait_initialized:
            return {
                "total_turns": len(self.conversation_history),
                "user_messages": len([c for c in self.conversation_history if c["role"] == "user"]),
                "agent_messages": len([c for c in self.conversation_history if c["role"] == "assistant"]),
                "actions_taken": len(self.action_history),
                "gait_initialized": False
            }

        status = self.gait_client.get_status()
        return {
            "total_turns": status.get("total_commits", 0),
            "user_messages": len([c for c in self.conversation_history if c["role"] == "user"]),
            "agent_messages": len([c for c in self.conversation_history if c["role"] == "assistant"]),
            "actions_taken": len(self.action_history),
            "gait_initialized": True,
            "gait_dir": status.get("gait_dir"),
            "head_commit": status.get("head_commit"),
            "pinned_memory": status.get("pinned_memory", 0)
        }

    async def _handle_query_neighbors(self, intent) -> str:
        """Handle OSPF neighbor query"""
        result = await self.executor.execute_action(
            "query_neighbors",
            {"protocol": "ospf"}
        )

        if result.result:
            neighbors = result.result.get("neighbors", [])
            if not neighbors:
                response = "No OSPF neighbors found."
            else:
                lines = ["OSPF Neighbors:", ""]
                for neighbor in neighbors:
                    lines.append(f"  • Neighbor {neighbor['neighbor_id']}")
                    lines.append(f"    State: {neighbor['state']}")
                    lines.append(f"    Address: {neighbor['address']}")
                    lines.append("")
                response = "\n".join(lines)
        else:
            response = f"Error querying neighbors: {result.error}"

        self._record_action('query_neighbors', result.result if result.result else result.error, bool(result.result))
        return response

    async def _handle_query_route(self, intent) -> str:
        """Handle route query"""
        destination = intent.parameters.get("destination")

        result = await self.executor.execute_action(
            "query_routes",
            {"destination": destination}
        )

        if result.result:
            routes = result.result.get("routes", [])
            if not routes:
                return f"No route found to {destination}"

            lines = [f"Routes to {destination}:", ""]
            for route in routes:
                lines.append(f"  • Network: {route['network']}")
                lines.append(f"    Next Hop: {route['next_hop']}")
                lines.append(f"    Protocol: {route['protocol']}")
                if "as_path" in route:
                    lines.append(f"    AS Path: {' '.join(map(str, route['as_path']))}")
                lines.append("")

            return "\n".join(lines)
        else:
            return f"Error querying routes: {result.error}"

    async def _handle_query_status(self, intent) -> str:
        """Handle general status query"""
        return self.state_manager.get_state_summary()

    async def _handle_query_bgp_peers(self, intent) -> str:
        """Handle BGP peer query"""
        result = await self.executor.execute_action(
            "query_neighbors",
            {"protocol": "bgp"}
        )

        if result.result:
            peers = result.result.get("peers", [])
            if not peers:
                return "No BGP peers found."

            lines = ["BGP Peers:", ""]
            for peer in peers:
                lines.append(f"  • Peer {peer['peer']}")
                lines.append(f"    AS: {peer['as']}")
                lines.append(f"    State: {peer['state']}")
                lines.append("")

            return "\n".join(lines)
        else:
            return f"Error querying BGP peers: {result.error}"

    async def _handle_query_rib(self, intent) -> str:
        """Handle RIB query"""
        result = await self.executor.execute_action(
            "query_routes",
            {}
        )

        if result.result:
            routes = result.result.get("routes", [])
            count = result.result.get("count", len(routes))

            lines = [f"Routing Table ({count} routes):", ""]
            for route in routes[:10]:  # Show first 10
                lines.append(f"  • {route['network']} via {route['next_hop']} ({route['protocol']})")

            if count > 10:
                lines.append(f"\n  ... and {count - 10} more routes")

            return "\n".join(lines)
        else:
            return f"Error querying routing table: {result.error}"

    async def _handle_detect_anomaly(self, intent) -> str:
        """Handle anomaly detection"""
        network_state = self.state_manager.get_llm_context()
        anomalies = await self.decision_engine.detect_anomalies(network_state)

        if not anomalies:
            return "No anomalies detected. Network appears healthy."

        lines = [f"Detected {len(anomalies)} anomalies:", ""]
        for i, anomaly in enumerate(anomalies, 1):
            lines.append(f"{i}. [{anomaly['severity'].upper()}] {anomaly['type']}")
            lines.append(f"   {anomaly['description']}")
            lines.append(f"   Recommendation: {anomaly['recommendation']}")
            lines.append("")

        return "\n".join(lines)

    async def _handle_analyze_topology(self, intent) -> str:
        """Handle topology analysis"""
        # Generate analytics report
        report = self.analytics.generate_report()
        return report

    async def _handle_explain_decision(self, intent) -> str:
        """Explain routing decisions"""
        lines = ["Routing Decision Explanation:", ""]

        # First check decision engine history
        explanation = self.decision_engine.explain_last_decision()
        if explanation and explanation != "No decisions made yet.":
            lines.append("Recent Agentic Decision:")
            lines.append(f"  {explanation}")
            lines.append("")

        # Also explain BGP path selection for installed routes
        if self.bgp_connector and self.bgp_connector.speaker:
            routes = self.bgp_connector.speaker.agent.loc_rib.get_all_routes()
            if routes:
                lines.append("BGP Path Selection:")
                lines.append("  Decision process follows these steps:")
                lines.append("    1. Highest LOCAL_PREF (prefer routes with higher local preference)")
                lines.append("    2. Shortest AS_PATH (prefer routes with fewer AS hops)")
                lines.append("    3. Lowest ORIGIN (IGP < EGP < Incomplete)")
                lines.append("    4. Lowest MED (Multi-Exit Discriminator)")
                lines.append("    5. eBGP over iBGP (prefer external routes)")
                lines.append("    6. Lowest IGP metric to next-hop")
                lines.append("    7. Lowest Router ID (tiebreaker)")
                lines.append("")

                # Show a sample decision
                if routes:
                    route = routes[0]
                    lines.append(f"  Example: Route {route.prefix}")
                    lines.append(f"    Learned from: {route.peer_id}")

                    # AS Path
                    as_path = route.path_attributes.get(2)
                    if as_path and hasattr(as_path, 'get_as_list'):
                        path_list = as_path.get_as_list()
                        lines.append(f"    AS Path: {' '.join(map(str, path_list)) or '(local)'}")
                        lines.append(f"    AS Path Length: {len(path_list)}")

                    # Local Pref
                    local_pref = route.path_attributes.get(5)
                    if local_pref:
                        val = local_pref.value
                        if isinstance(val, (int, float)):
                            lines.append(f"    Local Pref: {val}")

                    # Origin
                    origin = route.path_attributes.get(1)
                    if origin:
                        val = origin.value
                        if isinstance(val, int):
                            origin_names = {0: "IGP", 1: "EGP", 2: "Incomplete"}
                            lines.append(f"    Origin: {origin_names.get(val, 'Unknown')}")

        # OSPF path selection
        if self.ospf_connector and self.ospf_connector.interface:
            lines.append("")
            lines.append("OSPF Path Selection:")
            lines.append("  Routes are selected based on:")
            lines.append("    1. Intra-area routes preferred over inter-area")
            lines.append("    2. Inter-area routes preferred over external")
            lines.append("    3. Lowest cumulative cost (SPF algorithm)")

            ospf_state = self.state_manager.get_ospf_state()
            if ospf_state:
                lsdb = ospf_state.get('lsdb', {})
                lines.append(f"  Current LSDB has {lsdb.get('total_lsas', 0)} LSAs for SPF computation")

        if len(lines) == 2:
            return "No routing decisions to explain - no protocols running."

        return "\n".join(lines)

    async def _handle_action_adjust_metric(self, intent) -> str:
        """Handle metric adjustment action"""
        interface = intent.parameters.get("interface", "eth0")
        current_metric = intent.parameters.get("current_metric", 10)
        proposed_metric = intent.parameters.get("proposed_metric", 20)

        # Execute action (will trigger safety checks)
        result = await self.executor.execute_action(
            "metric_adjustment",
            {
                "interface": interface,
                "current_metric": current_metric,
                "proposed_metric": proposed_metric
            }
        )

        if result.status.value == "completed":
            response = f"✓ Successfully adjusted OSPF cost on {interface} to {proposed_metric}"
            success = True
        elif result.status.value == "blocked":
            response = f"✗ Action blocked: {result.error}"
            success = False
        elif result.status.value == "pending_approval":
            response = f"⚠ Action requires approval: {result.error}"
            success = False
        else:
            response = f"✗ Action failed: {result.error}"
            success = False

        self._record_action('metric_adjustment', {'interface': interface, 'metric': proposed_metric, 'status': result.status.value}, success)
        return response

    async def _handle_action_inject_route(self, intent) -> str:
        """Handle route injection action"""
        network = intent.parameters.get("network")
        protocol = intent.parameters.get("protocol", "bgp")

        result = await self.executor.execute_action(
            "route_injection",
            {"network": network, "protocol": protocol}
        )

        if result.status.value == "completed":
            response = f"✓ Successfully injected route {network} into {protocol.upper()}"
            success = True
        elif result.status.value == "blocked":
            response = f"✗ Action blocked: {result.error}"
            success = False
        elif result.status.value == "pending_approval":
            response = f"⚠ Action requires approval: {result.error}"
            success = False
        else:
            response = f"✗ Action failed: {result.error}"
            success = False

        self._record_action('route_injection', {'network': network, 'protocol': protocol, 'status': result.status.value}, success)
        return response

    async def _handle_query_router_id(self, intent) -> str:
        """Handle router ID query"""
        await self.state_manager.update_state()

        lines = ["Router ID Information:", ""]

        # OSPF Router ID
        ospf_state = self.state_manager.get_ospf_state()
        if ospf_state:
            lines.append(f"  OSPF Router ID: {ospf_state.get('router_id', 'N/A')}")
            lines.append(f"  OSPF Area: {ospf_state.get('area_id', 'N/A')}")

        # BGP Router ID
        bgp_state = self.state_manager.get_bgp_state()
        if bgp_state:
            lines.append(f"  BGP Router ID: {bgp_state.get('router_id', 'N/A')}")
            lines.append(f"  BGP Local AS: {bgp_state.get('local_as', 'N/A')}")

        if len(lines) == 2:
            return "No router ID information available."

        return "\n".join(lines)

    async def _handle_query_lsa(self, intent) -> str:
        """Handle LSA/LSDB query"""
        await self.state_manager.update_state()

        ospf_state = self.state_manager.get_ospf_state()
        if not ospf_state:
            return "No OSPF state available."

        lsdb = ospf_state.get("lsdb", {})
        lines = ["OSPF Link State Database:", ""]
        lines.append(f"  Router LSAs: {lsdb.get('router_lsas', 0)}")
        lines.append(f"  Network LSAs: {lsdb.get('network_lsas', 0)}")
        lines.append(f"  Summary LSAs: {lsdb.get('summary_lsas', 0)}")
        lines.append(f"  External LSAs: {lsdb.get('external_lsas', 0)}")
        lines.append(f"  Total LSAs: {lsdb.get('total_lsas', 0)}")

        return "\n".join(lines)

    async def _handle_query_statistics(self, intent) -> str:
        """Handle statistics query"""
        stats = self.get_statistics()
        await self.state_manager.update_state()

        lines = ["Network Statistics:", ""]

        # OSPF stats
        ospf_state = self.state_manager.get_ospf_state()
        if ospf_state:
            lines.append("OSPF:")
            lines.append(f"  Neighbors: {ospf_state.get('neighbor_count', 0)}")
            lines.append(f"  Full Adjacencies: {ospf_state.get('full_neighbors', 0)}")
            lines.append(f"  Total LSAs: {ospf_state.get('lsdb', {}).get('total_lsas', 0)}")
            lines.append("")

        # BGP stats
        bgp_state = self.state_manager.get_bgp_state()
        if bgp_state:
            lines.append("BGP:")
            lines.append(f"  Total Peers: {bgp_state.get('peer_count', 0)}")
            lines.append(f"  Established Peers: {bgp_state.get('established_peers', 0)}")
            lines.append(f"  Total Routes: {bgp_state.get('route_count', 0)}")
            lines.append("")

        # LLM stats
        lines.append("Agentic Layer:")
        lines.append(f"  LLM Turns: {stats['llm']['turns']}/{stats['llm']['max_turns']}")
        lines.append(f"  Actions Completed: {stats['actions']['completed']}")
        lines.append(f"  State Snapshots: {stats['state']['snapshots']}")

        return "\n".join(lines)

    async def _handle_query_interface(self, intent) -> str:
        """Handle interface query"""
        await self.state_manager.update_state()

        lines = ["Interface Information:", ""]

        # Show ALL configured interfaces
        if self.interfaces:
            lines.append(f"Configured Interfaces ({len(self.interfaces)} total):")
            lines.append("")
            for iface in self.interfaces:
                name = iface.get('name', iface.get('id', 'unknown'))
                iface_type = iface.get('type', 'eth')
                addrs = iface.get('addresses', [])
                status = iface.get('status', 'up')
                mtu = iface.get('mtu', 1500)

                type_names = {
                    'eth': 'Ethernet',
                    'lo': 'Loopback',
                    'vlan': 'VLAN',
                    'tun': 'Tunnel',
                    'sub': 'Sub-Interface'
                }
                type_display = type_names.get(iface_type, iface_type)

                lines.append(f"  • {name} ({type_display})")
                if addrs:
                    lines.append(f"      IP: {', '.join(addrs)}")
                else:
                    lines.append(f"      IP: Not configured")
                lines.append(f"      Status: {status}, MTU: {mtu}")
                lines.append("")
        else:
            lines.append("  No interfaces configured in agent config.")
            lines.append("")

        # Also show protocol-specific interface info
        ospf_state = self.state_manager.get_ospf_state()
        if ospf_state:
            lines.append("Protocol Interface Bindings:")
            lines.append(f"  OSPF bound to: {ospf_state.get('interface_name', 'N/A')}")
            lines.append(f"  OSPF Router ID: {ospf_state.get('router_id', 'N/A')}")
            lines.append(f"  OSPF Area: {ospf_state.get('area_id', 'N/A')}")

        if len(lines) == 2:
            return "No interface information available."

        return "\n".join(lines)

    async def _handle_analyze_health(self, intent) -> str:
        """Handle network health analysis"""
        await self.state_manager.update_state()

        issues = []

        # Check OSPF health
        ospf_state = self.state_manager.get_ospf_state()
        if ospf_state:
            neighbor_count = ospf_state.get('neighbor_count', 0)
            full_neighbors = ospf_state.get('full_neighbors', 0)
            if neighbor_count > 0 and full_neighbors < neighbor_count:
                issues.append(f"OSPF: Only {full_neighbors}/{neighbor_count} neighbors in Full state")

        # Check BGP health
        bgp_state = self.state_manager.get_bgp_state()
        if bgp_state:
            peer_count = bgp_state.get('peer_count', 0)
            established = bgp_state.get('established_peers', 0)
            if peer_count > 0 and established < peer_count:
                issues.append(f"BGP: Only {established}/{peer_count} peers Established")

        if not issues:
            lines = ["Network Health: ✓ HEALTHY", ""]
            if ospf_state:
                lines.append(f"  OSPF: {ospf_state.get('full_neighbors', 0)} Full neighbors")
            if bgp_state:
                lines.append(f"  BGP: {bgp_state.get('established_peers', 0)} Established peers, {bgp_state.get('route_count', 0)} routes")
            return "\n".join(lines)
        else:
            lines = ["Network Health: ⚠ ISSUES DETECTED", ""]
            for issue in issues:
                lines.append(f"  • {issue}")
            return "\n".join(lines)

    async def _handle_query_protocol_status(self, intent) -> str:
        """Handle protocol status query (is OSPF/BGP running?)"""
        await self.state_manager.update_state()

        lines = ["Protocol Status:", ""]

        # Check OSPF
        ospf_running = False
        if self.ospf_connector and self.ospf_connector.interface:
            ospf_running = True
            ospf_state = self.state_manager.get_ospf_state()
            neighbor_count = ospf_state.get('neighbor_count', 0) if ospf_state else 0
            full_neighbors = ospf_state.get('full_neighbors', 0) if ospf_state else 0
            lines.append(f"  OSPF: ✓ Running")
            lines.append(f"    Router ID: {ospf_state.get('router_id', 'N/A') if ospf_state else 'N/A'}")
            lines.append(f"    Area: {ospf_state.get('area_id', 'N/A') if ospf_state else 'N/A'}")
            lines.append(f"    Neighbors: {full_neighbors}/{neighbor_count} Full")
        else:
            lines.append(f"  OSPF: ✗ Not running")

        lines.append("")

        # Check BGP
        bgp_running = False
        if self.bgp_connector and self.bgp_connector.speaker:
            bgp_running = self.bgp_connector.speaker.agent.running
            bgp_state = self.state_manager.get_bgp_state()
            if bgp_running:
                peer_count = bgp_state.get('peer_count', 0) if bgp_state else 0
                established = bgp_state.get('established_peers', 0) if bgp_state else 0
                lines.append(f"  BGP: ✓ Running")
                lines.append(f"    Local AS: {bgp_state.get('local_as', 'N/A') if bgp_state else 'N/A'}")
                lines.append(f"    Router ID: {bgp_state.get('router_id', 'N/A') if bgp_state else 'N/A'}")
                lines.append(f"    Peers: {established}/{peer_count} Established")
            else:
                lines.append(f"  BGP: ✗ Not running")
        else:
            lines.append(f"  BGP: ✗ Not configured")

        return "\n".join(lines)

    async def _handle_query_capabilities(self, intent) -> str:
        """Handle BGP capabilities query"""
        await self.state_manager.update_state()

        if not self.bgp_connector or not self.bgp_connector.speaker:
            return "BGP is not configured."

        lines = ["BGP Negotiated Capabilities:", ""]

        # Get capabilities from each BGP session
        for peer_ip, session in self.bgp_connector.speaker.agent.sessions.items():
            lines.append(f"  Peer {peer_ip} (AS {session.config.peer_as}):")

            caps = session.capabilities
            cap_stats = caps.get_statistics()

            # List negotiated capabilities
            cap_list = []
            if cap_stats.get('ipv4_unicast'):
                cap_list.append("IPv4 Unicast")
            if cap_stats.get('ipv6_unicast'):
                cap_list.append("IPv6 Unicast")
            if cap_stats.get('route_refresh'):
                cap_list.append("Route Refresh")
            if cap_stats.get('four_octet_as'):
                cap_list.append("4-Byte AS")
            if cap_stats.get('graceful_restart'):
                cap_list.append("Graceful Restart")
            if cap_stats.get('add_path'):
                cap_list.append("ADD-PATH")

            if cap_list:
                lines.append(f"    Negotiated: {', '.join(cap_list)}")
            else:
                lines.append(f"    Negotiated: Basic BGP only")

            # Show local vs peer capability counts
            lines.append(f"    Local capabilities: {cap_stats.get('local_capabilities', 0)}")
            lines.append(f"    Peer capabilities: {cap_stats.get('peer_capabilities', 0)}")
            lines.append("")

        if len(lines) == 2:
            return "No BGP sessions configured."

        return "\n".join(lines)

    async def _handle_query_fib(self, intent) -> str:
        """Handle FIB/forwarding table query"""
        lines = ["Forwarding Information Base (FIB):", ""]

        # Get kernel routes if kernel route manager is available
        kernel_routes = []
        if self.bgp_connector and self.bgp_connector.speaker:
            kernel_mgr = self.bgp_connector.speaker.agent.kernel_route_manager
            if kernel_mgr:
                kernel_routes = kernel_mgr.get_installed_routes()
                lines.append(f"  Kernel Routes Installed: {len(kernel_routes)}")
                lines.append("")

                if kernel_routes:
                    for prefix in kernel_routes[:15]:  # Show first 15
                        next_hop = kernel_mgr.installed_routes.get(prefix, "unknown")
                        lines.append(f"    • {prefix} via {next_hop}")

                    if len(kernel_routes) > 15:
                        lines.append(f"\n    ... and {len(kernel_routes) - 15} more routes")
                else:
                    lines.append("    No routes installed in kernel.")
            else:
                lines.append("  Kernel route manager not configured.")
        else:
            lines.append("  BGP not configured (no kernel routes from BGP).")

        # Also show OSPF-derived routes if available
        if self.ospf_connector and self.ospf_connector.interface:
            lines.append("")
            lines.append("  OSPF Routes:")
            ospf_state = self.state_manager.get_ospf_state()
            if ospf_state:
                lsdb = ospf_state.get('lsdb', {})
                lines.append(f"    Router LSAs: {lsdb.get('router_lsas', 0)}")
                lines.append(f"    Total LSAs: {lsdb.get('total_lsas', 0)}")
            else:
                lines.append("    No OSPF routes computed.")

        return "\n".join(lines)

    async def _handle_query_changes(self, intent) -> str:
        """Handle recent network changes query"""
        # Get state changes from snapshots
        changes = self.state_manager.detect_state_changes()

        lines = ["Recent Network Changes:", ""]

        if changes:
            for change in changes:
                lines.append(f"  • {change}")
        else:
            lines.append("  No recent changes detected.")

        # Show snapshot count
        lines.append("")
        lines.append(f"  Snapshots tracked: {len(self.state_manager.snapshots)}")

        # Show recent snapshots with timestamps if available
        if self.state_manager.snapshots:
            recent = self.state_manager.snapshots[-3:]  # Last 3 snapshots
            lines.append("")
            lines.append("  Recent Snapshots:")
            for snapshot in reversed(recent):
                ts = snapshot.timestamp.strftime("%H:%M:%S")
                health = snapshot.metrics.get('health_score', 0)
                lines.append(f"    • {ts} - Health: {health:.0f}/100")

        return "\n".join(lines)

    async def _handle_query_metrics(self, intent) -> str:
        """Handle metrics query (OSPF costs, BGP attributes)"""
        await self.state_manager.update_state()

        lines = ["Network Metrics:", ""]

        # OSPF metrics
        if self.ospf_connector and self.ospf_connector.interface:
            lines.append("  OSPF Metrics:")
            ospf_iface = self.ospf_connector.interface

            # Interface cost
            cost = getattr(ospf_iface, 'cost', 10)
            lines.append(f"    Interface Cost: {cost}")

            # Hello/Dead intervals
            hello = getattr(ospf_iface, 'hello_interval', 10)
            dead = getattr(ospf_iface, 'dead_interval', 40)
            lines.append(f"    Hello Interval: {hello}s")
            lines.append(f"    Dead Interval: {dead}s")

            # Router priority
            priority = getattr(ospf_iface, 'priority', 1)
            lines.append(f"    Router Priority: {priority}")
            lines.append("")

        # BGP metrics
        if self.bgp_connector and self.bgp_connector.speaker:
            lines.append("  BGP Metrics:")

            # Show route attributes for routes in Loc-RIB
            routes = self.bgp_connector.speaker.agent.loc_rib.get_all_routes()
            if routes:
                lines.append(f"    Routes in Loc-RIB: {len(routes)}")
                lines.append("")

                # Show sample route attributes
                for route in routes[:5]:  # Show first 5 routes
                    lines.append(f"    Route: {route.prefix}")

                    # Local preference
                    local_pref = route.path_attributes.get(5)  # ATTR_LOCAL_PREF
                    if local_pref:
                        val = local_pref.value
                        if isinstance(val, (int, float)):
                            lines.append(f"      Local Pref: {val}")
                        elif val and val != b'':
                            lines.append(f"      Local Pref: {val}")

                    # MED
                    med = route.path_attributes.get(4)  # ATTR_MED
                    if med:
                        val = med.value
                        if isinstance(val, (int, float)):
                            lines.append(f"      MED: {val}")
                        elif val and val != b'':
                            lines.append(f"      MED: {val}")

                    # AS Path
                    as_path = route.path_attributes.get(2)  # ATTR_AS_PATH
                    if as_path and hasattr(as_path, 'get_as_list'):
                        path_list = as_path.get_as_list()
                        lines.append(f"      AS Path: {' '.join(map(str, path_list)) or '(local)'}")
                        lines.append(f"      AS Path Length: {len(path_list)}")

                    # Next-hop
                    next_hop = route.path_attributes.get(3)  # ATTR_NEXT_HOP
                    if next_hop and hasattr(next_hop, 'next_hop'):
                        lines.append(f"      Next-Hop: {next_hop.next_hop}")

                    lines.append("")

                if len(routes) > 5:
                    lines.append(f"    ... and {len(routes) - 5} more routes")
            else:
                lines.append("    No routes in Loc-RIB.")

        if len(lines) == 2:
            return "No metrics available - no protocols configured."

        return "\n".join(lines)

    async def _handle_ping(self, intent) -> str:
        """Handle ping diagnostic"""
        target = intent.parameters.get("target")
        source = intent.parameters.get("source")

        if not target:
            return "Please specify an IP address to ping. Example: 'ping 10.0.0.1' or 'ping 10.0.0.1 from 192.168.1.1'"

        params = {"target": target, "count": 3}
        if source:
            params["source"] = source

        result = await self.executor.execute_action(
            "diagnostic_ping",
            params
        )

        if result.result:
            ping_result = result.result
            if ping_result.get("success"):
                # Build header with source info if specified
                if source:
                    header = f"Ping to {target} from {source}:"
                else:
                    header = f"Ping to {target}:"

                lines = [header, ""]
                lines.append(f"  Packets: {ping_result.get('sent', 0)} sent, {ping_result.get('received', 0)} received")
                loss = ping_result.get('packet_loss', 0)
                lines.append(f"  Packet loss: {loss:.1f}%")

                if ping_result.get('rtt_avg') is not None:
                    lines.append(f"  Round-trip time:")
                    lines.append(f"    Min: {ping_result.get('rtt_min', 0):.2f}ms")
                    lines.append(f"    Avg: {ping_result.get('rtt_avg', 0):.2f}ms")
                    lines.append(f"    Max: {ping_result.get('rtt_max', 0):.2f}ms")

                status = "✓ Host is reachable" if ping_result.get('received', 0) > 0 else "✗ Host unreachable"
                lines.append("")
                lines.append(status)

                return "\n".join(lines)
            else:
                return f"✗ Ping to {target} failed: {ping_result.get('error', 'Host unreachable')}"
        else:
            return f"Error executing ping: {result.error}"

    async def _handle_traceroute(self, intent) -> str:
        """Handle traceroute diagnostic"""
        target = intent.parameters.get("target")

        if not target:
            return "Please specify an IP address to traceroute. Example: 'traceroute 10.0.0.1'"

        result = await self.executor.execute_action(
            "diagnostic_traceroute",
            {"target": target, "max_hops": 15}
        )

        if result.result:
            trace_result = result.result
            if trace_result.get("success"):
                lines = [f"Traceroute to {target}:", ""]

                hops = trace_result.get("hops", [])
                for hop in hops:
                    hop_num = hop.get("hop", "?")
                    ip = hop.get("ip", "*")
                    rtt = hop.get("rtt")

                    if ip == "*":
                        lines.append(f"  {hop_num:2d}  * * * (no response)")
                    elif rtt is not None:
                        lines.append(f"  {hop_num:2d}  {ip}  {rtt:.2f}ms")
                    else:
                        lines.append(f"  {hop_num:2d}  {ip}")

                # Check if we reached the target
                if hops and hops[-1].get("ip") == target:
                    lines.append("")
                    lines.append(f"✓ Reached destination in {len(hops)} hops")
                elif trace_result.get("reached"):
                    lines.append("")
                    lines.append(f"✓ Reached destination")
                else:
                    lines.append("")
                    lines.append(f"✗ Did not reach destination (max hops exceeded)")

                return "\n".join(lines)
            else:
                return f"✗ Traceroute to {target} failed: {trace_result.get('error', 'Unknown error')}"
        else:
            return f"Error executing traceroute: {result.error}"

    def _register_gossip_handlers(self):
        """Register handlers for gossip messages"""
        from ..multi_agent.gossip import MessageType

        async def handle_consensus_request(message):
            # Receive consensus proposal
            self.consensus.receive_proposal(message.payload)

        async def handle_consensus_vote(message):
            # Receive vote
            self.consensus.receive_vote(
                message.payload["proposal_id"],
                message.payload["voter_id"],
                message.payload["vote"]
            )

        async def handle_anomaly_alert(message):
            print(f"[AgenticBridge] Anomaly alert from {message.sender_id}: {message.payload}")

        self.gossip.register_handler(MessageType.CONSENSUS_REQUEST, handle_consensus_request)
        self.gossip.register_handler(MessageType.CONSENSUS_VOTE, handle_consensus_vote)
        self.gossip.register_handler(MessageType.ANOMALY_ALERT, handle_anomaly_alert)

    async def start(self):
        """Start agentic bridge"""
        if self._running:
            return

        self._running = True

        # Start gossip protocol
        await self.gossip.start()

        # Start state update loop
        self._state_update_task = asyncio.create_task(self._state_update_loop())

        print(f"[AgenticBridge] ASI {self.asi_id} started")

    async def stop(self):
        """Stop agentic bridge"""
        self._running = False

        # Stop gossip
        await self.gossip.stop()

        # Stop state updates
        if self._state_update_task:
            self._state_update_task.cancel()
            try:
                await self._state_update_task
            except asyncio.CancelledError:
                pass

        print(f"[AgenticBridge] ASI {self.asi_id} stopped")

    async def _state_update_loop(self):
        """Periodically update network state"""
        while self._running:
            try:
                await self.state_manager.update_state()
                self.state_manager.create_snapshot()

                # Run analytics
                # Detect changes
                changes = self.state_manager.detect_state_changes()
                if changes:
                    print(f"[AgenticBridge] State changes detected: {len(changes)}")

                await asyncio.sleep(10)  # Update every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AgenticBridge] Error in state update: {e}")
                await asyncio.sleep(1)

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            "asi_id": self.asi_id,
            "llm": {
                "turns": self.llm.current_turn,
                "max_turns": self.llm.max_turns,
                "providers": len(self.llm.providers)
            },
            "state": {
                "snapshots": len(self.state_manager.snapshots),
                "metrics": self.state_manager._compute_metrics()
            },
            "actions": {
                "completed": len(self.executor.completed_actions),
                "pending": len(self.executor.pending_actions)
            },
            "gossip": self.gossip.get_statistics(),
            "consensus": self.consensus.get_statistics()
        }
