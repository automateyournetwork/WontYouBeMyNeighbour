"""
Agentic Bridge

Main integration point between the agentic layer and protocol implementations.
Orchestrates LLM queries, decision-making, and autonomous actions.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
import json

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
from ..mcp.pyats_mcp import PyATSMCPClient, get_pyats_client, init_pyats_for_agent
from ..tests.dynamic_test_generator import (
    DynamicTestGenerator,
    SelfTestingAgent,
    TestCategory,
    TestTrigger,
    TestExecutionResult,
)


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

        # Self-Testing Network: pyATS MCP client and dynamic test generator
        self.pyats_client: Optional[PyATSMCPClient] = None
        self.self_tester: Optional[SelfTestingAgent] = None
        self._self_test_enabled = False

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

        # Initialize self-testing if pyATS client is available
        if self.pyats_client and self._self_test_enabled:
            self.self_tester = SelfTestingAgent(
                agent_config=config,
                pyats_client=self.pyats_client,
            )
            # Register callback to update health scores on test completion
            self.self_tester.register_callback(self._on_test_completed)
            print(f"[AgenticBridge] Self-testing agent initialized")

    async def enable_self_testing(
        self,
        pyats_server_path: Optional[str] = None,
        testbed_path: Optional[str] = None,
        docker_mode: bool = False,
    ) -> bool:
        """
        Enable self-testing capability for this agent.

        This connects to the pyATS MCP server and enables the agent
        to autonomously generate and execute network tests.

        Args:
            pyats_server_path: Path to pyats_mcp_server.py
            testbed_path: Path to pyATS testbed.yaml
            docker_mode: Use Docker container for pyATS MCP

        Returns:
            True if self-testing was enabled successfully
        """
        try:
            self.pyats_client = await init_pyats_for_agent(
                server_path=pyats_server_path,
                testbed_path=testbed_path,
                docker_mode=docker_mode,
            )
            self._self_test_enabled = True

            # If agent config is already set, initialize self-tester
            if self.agent_config:
                self.self_tester = SelfTestingAgent(
                    agent_config=self.agent_config,
                    pyats_client=self.pyats_client,
                )
                self.self_tester.register_callback(self._on_test_completed)

            print(f"[AgenticBridge] Self-testing enabled for {self.asi_id}")
            return True

        except Exception as e:
            print(f"[AgenticBridge] Failed to enable self-testing: {e}")
            return False

    def _on_test_completed(self, result: TestExecutionResult) -> None:
        """
        Callback when a self-test completes.

        Updates health scores and records result in GAIT.
        """
        # Record in action history (GAIT)
        self._record_action(
            action_type='self_test',
            description=f"Self-test {result.test_id}",
            result={
                'success': result.success,
                'passed': result.passed,
                'failed': result.failed,
                'errored': result.errored,
                'recommendations': result.recommendations,
            }
        )

        # Log result
        if result.success:
            print(f"[SelfTest] PASSED - {result.test_id}: {result.passed} tests passed")
        else:
            print(f"[SelfTest] FAILED - {result.test_id}: {result.failed} failed, {result.errored} errors")
            for rec in result.recommendations:
                print(f"  Recommendation: {rec}")

    async def run_self_assessment(self) -> Optional[TestExecutionResult]:
        """
        Run comprehensive self-assessment.

        The agent tests its own connectivity, protocol states,
        interface health, and routing table.

        Returns:
            TestExecutionResult or None if self-testing not enabled
        """
        if not self.self_tester:
            print("[AgenticBridge] Self-testing not enabled. Call enable_self_testing() first.")
            return None

        print(f"[AgenticBridge] Running self-assessment for {self.asi_id}...")
        return await self.self_tester.run_self_assessment()

    async def test_connectivity(self, targets: List[str]) -> Optional[TestExecutionResult]:
        """
        Test connectivity to specific targets.

        Args:
            targets: List of IP addresses to test connectivity to

        Returns:
            TestExecutionResult or None if self-testing not enabled
        """
        if not self.self_tester:
            return None

        return await self.self_tester.test_connectivity_to(
            targets=targets,
            trigger=TestTrigger.HUMAN_REQUEST,
        )

    async def test_protocol_state(self, protocol: str) -> Optional[TestExecutionResult]:
        """
        Test a specific protocol's state.

        Args:
            protocol: Protocol to test ('ospf', 'bgp', 'interfaces')

        Returns:
            TestExecutionResult or None if self-testing not enabled
        """
        if not self.self_tester:
            return None

        if protocol.lower() == 'ospf':
            return await self.self_tester.test_ospf_neighbors(
                trigger=TestTrigger.HUMAN_REQUEST
            )
        elif protocol.lower() == 'bgp':
            return await self.self_tester.test_bgp_peers(
                trigger=TestTrigger.HUMAN_REQUEST
            )
        elif protocol.lower() in ('interface', 'interfaces'):
            return await self.self_tester.test_interfaces(
                trigger=TestTrigger.HUMAN_REQUEST
            )
        else:
            print(f"[AgenticBridge] Unknown protocol: {protocol}")
            return None

    async def test_on_state_change(self, change_type: str, details: Dict[str, Any]) -> Optional[TestExecutionResult]:
        """
        Run appropriate tests when a state change is detected.

        This is the autonomous testing trigger - when the agent
        detects something changed, it tests to validate.

        Args:
            change_type: Type of change ('neighbor_down', 'route_withdrawn', etc.)
            details: Details about the change

        Returns:
            TestExecutionResult or None
        """
        if not self.self_tester:
            return None

        print(f"[AgenticBridge] State change detected: {change_type}")

        if change_type in ('neighbor_down', 'neighbor_up', 'ospf_adjacency_change'):
            return await self.self_tester.test_ospf_neighbors(
                trigger=TestTrigger.STATE_CHANGE
            )
        elif change_type in ('peer_down', 'peer_up', 'bgp_session_change'):
            return await self.self_tester.test_bgp_peers(
                trigger=TestTrigger.STATE_CHANGE
            )
        elif change_type in ('interface_down', 'interface_up', 'link_flap'):
            return await self.self_tester.test_interfaces(
                trigger=TestTrigger.STATE_CHANGE
            )
        elif change_type in ('route_withdrawn', 'route_added'):
            # Test that expected routes are still present
            if 'routes' in details:
                return await self.self_tester.test_route_presence(
                    routes=details['routes'],
                    trigger=TestTrigger.STATE_CHANGE,
                )
        else:
            # Unknown change type - run full self-assessment
            return await self.self_tester.run_self_assessment()

    def get_test_pass_rate(self) -> float:
        """Get the overall test pass rate from self-testing history"""
        if not self.self_tester:
            return 0.0
        return self.self_tester.get_pass_rate()

    def get_test_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent test execution history"""
        if not self.self_tester:
            return []
        return [r.to_dict() for r in self.self_tester.get_test_history(limit)]

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

        elif intent.intent_type == IntentType.SEND_EMAIL:
            response = await self._handle_send_email(intent)

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

    async def _llm_respond(self, user_query: str, additional_context: str = "") -> str:
        """
        Generate an LLM response based on the user's query and full agent state.

        This is the core RAG-like method - the LLM has access to all agent state
        and generates natural language responses based on it.

        Args:
            user_query: The user's original question/request
            additional_context: Any extra context specific to this query

        Returns:
            Natural language response from the LLM
        """
        prompt = f"""Based on the current network state (which you have full access to in your context),
please answer the user's question naturally and conversationally.

USER'S QUESTION: {user_query}
"""
        if additional_context:
            prompt += f"\nADDITIONAL CONTEXT:\n{additional_context}\n"

        prompt += """
Provide a helpful, accurate response based on the actual network state data you have.
Be specific - reference actual values, IPs, states, and metrics from the data.
If something is not available in the data, say so rather than guessing.
"""
        response = await self.llm.query(prompt)
        return response or "I couldn't generate a response. Please try again."

    async def _handle_query_neighbors(self, intent) -> str:
        """Handle neighbor query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_route(self, intent) -> str:
        """Handle route query - LLM responds based on full state"""
        destination = intent.parameters.get("destination", "")
        extra = f"User is asking about route to: {destination}" if destination else ""
        return await self._llm_respond(intent.raw_query, extra)

    async def _handle_query_status(self, intent) -> str:
        """Handle general status query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_bgp_peers(self, intent) -> str:
        """Handle BGP peer query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_rib(self, intent) -> str:
        """Handle RIB query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_detect_anomaly(self, intent) -> str:
        """Handle anomaly detection - LLM analyzes state for issues"""
        return await self._llm_respond(
            intent.raw_query,
            "Analyze the network state for any anomalies, issues, or problems. "
            "Look for things like down neighbors, missing routes, protocol issues, etc."
        )

    async def _handle_analyze_topology(self, intent) -> str:
        """Handle topology analysis - LLM describes the network topology"""
        return await self._llm_respond(
            intent.raw_query,
            "Describe the network topology including all agents, their connections, "
            "protocols in use, and how traffic flows between them."
        )

    async def _handle_explain_decision(self, intent) -> str:
        """Explain routing decisions - LLM explains based on full state"""
        return await self._llm_respond(
            intent.raw_query,
            "Explain how routing decisions are made. Include BGP path selection criteria "
            "(LOCAL_PREF, AS_PATH, ORIGIN, MED, etc.) and OSPF SPF algorithm if relevant. "
            "Reference actual routes and their attributes from the current state."
        )

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

    async def _handle_query_router_id(self, intent) -> str:
        """Handle router ID query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_lsa(self, intent) -> str:
        """Handle LSA/LSDB query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_statistics(self, intent) -> str:
        """Handle statistics query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_interface(self, intent) -> str:
        """Handle interface query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_analyze_health(self, intent) -> str:
        """Handle network health analysis - LLM analyzes state"""
        return await self._llm_respond(
            intent.raw_query,
            "Analyze the overall health of the network. Check for issues like "
            "neighbors not in Full state, BGP peers not Established, missing routes, etc. "
            "Provide a health assessment with specific details from the current state."
        )

    async def _handle_query_protocol_status(self, intent) -> str:
        """Handle protocol status query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_capabilities(self, intent) -> str:
        """Handle BGP capabilities query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_fib(self, intent) -> str:
        """Handle FIB/forwarding table query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_changes(self, intent) -> str:
        """Handle recent network changes query - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

    async def _handle_query_metrics(self, intent) -> str:
        """Handle metrics query (OSPF costs, BGP attributes) - LLM responds based on full state"""
        return await self._llm_respond(intent.raw_query)

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

    async def _handle_send_email(self, intent) -> str:
        """Handle send email request with LLM-generated reports"""
        import re
        import os
        import json

        # Extract email addresses from both intent parameters and raw query
        raw_query = intent.raw_query if hasattr(intent, 'raw_query') else str(intent.parameters)

        # First check if LLM parsed recipients in parameters
        recipients = []
        if hasattr(intent, 'parameters') and intent.parameters:
            param_recipients = intent.parameters.get('recipients', [])
            if isinstance(param_recipients, list):
                recipients.extend(param_recipients)
            elif isinstance(param_recipients, str):
                recipients.append(param_recipients)
            # Also check for 'recipient' (singular)
            single_recipient = intent.parameters.get('recipient')
            if single_recipient and single_recipient not in recipients:
                recipients.append(single_recipient)

        # Also extract any emails from raw query using regex (as fallback)
        email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', raw_query)
        for email in email_matches:
            if email not in recipients:
                recipients.append(email)

        if not recipients:
            return "Please specify email address(es). Example: 'email the report to user@example.com'"

        # Get subject from parameters if provided
        custom_subject = None
        if hasattr(intent, 'parameters') and intent.parameters:
            custom_subject = intent.parameters.get('subject')

        try:
            from ..mcp.smtp_mcp import (
                get_smtp_client, Email, SMTPConfig, configure_smtp_from_mcp
            )

            # Load SMTP configuration from environment variables (set by wizard)
            smtp_server = os.environ.get("SMTP_SERVER", "")
            smtp_username = os.environ.get("SMTP_USERNAME", "")
            smtp_password = os.environ.get("SMTP_PASSWORD", "")

            if not smtp_server or not smtp_username:
                return (
                    "SMTP is not configured. Please configure SMTP in the wizard:\n"
                    "1. Go to the Agent Wizard\n"
                    "2. Enable 'SMTP Email' in Optional MCPs\n"
                    "3. Click 'Configure' and enter your SMTP settings\n"
                    "4. Re-deploy the agent\n\n"
                    "For Gmail: Use smtp.gmail.com, port 587, and an App Password."
                )

            # Build SMTP config from environment
            config_dict = {
                "smtp_server": smtp_server,
                "smtp_port": os.environ.get("SMTP_PORT", "587"),
                "smtp_username": smtp_username,
                "smtp_password": smtp_password,
                "smtp_from": os.environ.get("SMTP_FROM", smtp_username),
                "smtp_use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
            }
            smtp_config = configure_smtp_from_mcp(config_dict)

            # Get SMTP client and configure it
            smtp_client = get_smtp_client(self.asi_id)
            smtp_client.configure(smtp_config)

            # Get FULL agent state - let the LLM decide what's relevant
            context = self.state_manager.get_llm_context()

            # Gather ALL available data - the LLM will determine what to include
            full_state = {
                'agent_id': self.asi_id,
                'timestamp': datetime.now().isoformat(),
                'routes': context.get('routes', []),
                'interfaces': context.get('interfaces', []),
                'neighbors': context.get('neighbors', {}),
                'ospf': {
                    'neighbors': context.get('neighbors', {}).get('ospf', []),
                    'areas': context.get('ospf_areas', [])
                },
                'bgp': {
                    'peers': context.get('neighbors', {}).get('bgp', []),
                    'local_as': context.get('local_as')
                },
                'health': {
                    'uptime': context.get('uptime'),
                    'cpu': context.get('cpu_usage'),
                    'memory': context.get('memory_usage'),
                    'protocol_status': context.get('protocol_status', {})
                },
                'metrics': context.get('metrics', {}),
                'topology': {
                    'connected_agents': context.get('connected_agents', []),
                    'network_role': context.get('network_role', 'unknown')
                }
            }

            # Let the LLM interpret the user's request and generate the report
            report_prompt = f"""You are a network agent assistant. The user has requested an email report.

USER'S REQUEST: "{raw_query}"

Based on their request, generate an appropriate email report. You have access to the complete agent state below.
Interpret what the user wants and include the relevant information. If they ask for "full state", "everything",
"complete report", etc., include all sections. If they ask for something specific like "routing table" or
"BGP peers", focus on that.

AGENT: {self.asi_id}
TIMESTAMP: {datetime.now().isoformat()}

COMPLETE AGENT STATE:
{json.dumps(full_state, indent=2, default=str)}

Generate a professional, well-formatted email report. Include:
1. An appropriate subject line based on what they asked for
2. Executive summary
3. Relevant data sections based on their request
4. Any observations or recommendations

Format your response EXACTLY as:
SUBJECT: <subject line here>
BODY:
<email body here>
"""

            # Let the LLM generate the report
            llm_response = await self.llm.query(report_prompt)

            # Parse LLM response
            subject, body = self._parse_llm_email_response(llm_response, "Agent Report")

            # Use custom subject from intent if provided, otherwise use LLM-generated subject
            final_subject = custom_subject if custom_subject else subject

            # Create and send email to all recipients
            email = Email(
                to=recipients,
                subject=f"[{self.asi_id}] {final_subject}",
                body=body
            )

            success = await smtp_client.send_immediate(email)

            recipient_list = ', '.join(recipients)
            if success:
                return f"Email report sent successfully to {len(recipients)} recipient(s): {recipient_list}"
            else:
                return f"Failed to send email to {recipient_list}. Please check SMTP configuration (server: {smtp_server})."

        except ImportError:
            return "SMTP module not available. Email functionality requires SMTP MCP."
        except Exception as e:
            return f"Error sending email: {str(e)}"

    def _parse_llm_email_response(self, response: str, default_type: str) -> tuple:
        """Parse LLM response to extract subject and body"""
        if not response:
            return f"{default_type} Report", f"Report generated at {datetime.now().isoformat()}\n\nNo data available."

        # Try to parse structured response
        lines = response.strip().split('\n')
        subject = f"{default_type} Report"
        body_lines = []
        in_body = False

        for line in lines:
            if line.upper().startswith('SUBJECT:'):
                subject = line[8:].strip()
            elif line.upper().startswith('BODY:'):
                in_body = True
            elif in_body:
                body_lines.append(line)

        if body_lines:
            body = '\n'.join(body_lines).strip()
        else:
            # If parsing failed, use entire response as body
            body = response.strip()

        # Add footer
        body += f"\n\n---\nGenerated by Network Agent: {self.asi_id}\nTimestamp: {datetime.now().isoformat()}"

        return subject, body

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
