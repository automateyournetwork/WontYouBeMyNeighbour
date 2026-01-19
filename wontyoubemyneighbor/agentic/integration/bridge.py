"""
Agentic Bridge

Main integration point between the agentic layer and protocol implementations.
Orchestrates LLM queries, decision-making, and autonomous actions.
"""

from typing import Dict, Any, Optional
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


class AgenticBridge:
    """
    Main bridge connecting agentic intelligence to network protocols.

    This is the primary interface for natural language network management.
    """

    def __init__(
        self,
        ralph_id: str,
        openai_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None,
        autonomous_mode: bool = False
    ):
        self.ralph_id = ralph_id

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
        self.gossip = GossipProtocol(ralph_id=ralph_id)
        self.consensus = ConsensusEngine(ralph_id=ralph_id, gossip_protocol=self.gossip)

        # Protocol connectors (set via dependency injection)
        self.ospf_connector = None
        self.bgp_connector = None

        # State update task
        self._state_update_task: Optional[asyncio.Task] = None
        self._running = False

    async def initialize(self):
        """Initialize all agentic components"""
        print(f"[AgenticBridge] Initializing Ralph {self.ralph_id}...")

        # Initialize LLM providers
        await self.llm.initialize_providers()

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

    async def query(self, user_message: str) -> str:
        """
        Process natural language query.

        This is the main entry point for human interaction.
        """
        # Update network state
        await self.state_manager.update_state()
        context = self.state_manager.get_llm_context()
        self.llm.update_network_context(context)

        # Parse intent
        intent = await self.intent_parser.parse(user_message, context)

        print(f"[AgenticBridge] Parsed intent: {intent.intent_type.value} (confidence: {intent.confidence:.2f})")

        # Handle based on intent type
        if intent.intent_type == IntentType.QUERY_NEIGHBOR:
            return await self._handle_query_neighbors(intent)

        elif intent.intent_type == IntentType.QUERY_ROUTE:
            return await self._handle_query_route(intent)

        elif intent.intent_type == IntentType.QUERY_STATUS:
            return await self._handle_query_status(intent)

        elif intent.intent_type == IntentType.QUERY_BGP_PEER:
            return await self._handle_query_bgp_peers(intent)

        elif intent.intent_type == IntentType.QUERY_RIB:
            return await self._handle_query_rib(intent)

        elif intent.intent_type == IntentType.DETECT_ANOMALY:
            return await self._handle_detect_anomaly(intent)

        elif intent.intent_type == IntentType.ANALYZE_TOPOLOGY:
            return await self._handle_analyze_topology(intent)

        elif intent.intent_type == IntentType.EXPLAIN_DECISION:
            return await self._handle_explain_decision(intent)

        elif intent.intent_type == IntentType.ACTION_ADJUST_METRIC:
            return await self._handle_action_adjust_metric(intent)

        elif intent.intent_type == IntentType.ACTION_INJECT_ROUTE:
            return await self._handle_action_inject_route(intent)

        else:
            # Use LLM for complex queries
            response = await self.llm.query(user_message)
            return response or "I'm not sure how to help with that."

    async def _handle_query_neighbors(self, intent) -> str:
        """Handle OSPF neighbor query"""
        result = await self.executor.execute_action(
            "query_neighbors",
            {"protocol": "ospf"}
        )

        if result.result:
            neighbors = result.result.get("neighbors", [])
            if not neighbors:
                return "No OSPF neighbors found."

            lines = ["OSPF Neighbors:", ""]
            for neighbor in neighbors:
                lines.append(f"  • Neighbor {neighbor['neighbor_id']}")
                lines.append(f"    State: {neighbor['state']}")
                lines.append(f"    Address: {neighbor['address']}")
                lines.append("")

            return "\n".join(lines)
        else:
            return f"Error querying neighbors: {result.error}"

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
        """Explain last routing decision"""
        explanation = self.decision_engine.explain_last_decision()
        return explanation or "No recent decisions to explain."

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
            return f"✓ Successfully adjusted OSPF cost on {interface} to {proposed_metric}"
        elif result.status.value == "blocked":
            return f"✗ Action blocked: {result.error}"
        elif result.status.value == "pending_approval":
            return f"⚠ Action requires approval: {result.error}"
        else:
            return f"✗ Action failed: {result.error}"

    async def _handle_action_inject_route(self, intent) -> str:
        """Handle route injection action"""
        network = intent.parameters.get("network")
        protocol = intent.parameters.get("protocol", "bgp")

        result = await self.executor.execute_action(
            "route_injection",
            {"network": network, "protocol": protocol}
        )

        if result.status.value == "completed":
            return f"✓ Successfully injected route {network} into {protocol.upper()}"
        elif result.status.value == "blocked":
            return f"✗ Action blocked: {result.error}"
        elif result.status.value == "pending_approval":
            return f"⚠ Action requires approval: {result.error}"
        else:
            return f"✗ Action failed: {result.error}"

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

        print(f"[AgenticBridge] Ralph {self.ralph_id} started")

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

        print(f"[AgenticBridge] Ralph {self.ralph_id} stopped")

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
            "ralph_id": self.ralph_id,
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
