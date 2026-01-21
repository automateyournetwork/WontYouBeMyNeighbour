"""
Action Executor

Executes autonomous network actions with safety checks and approval workflows.
Bridges the reasoning engine with actual OSPF/BGP protocol operations.
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .safety import SafetyConstraints, SafetyViolation


class ActionStatus(str, Enum):
    """Status of action execution"""
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ActionResult:
    """Result of action execution"""
    action_id: str
    action_type: str
    status: ActionStatus
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    safety_violation: Optional[SafetyViolation] = None
    timestamp: Optional[datetime] = None
    execution_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status.value,
            "parameters": self.parameters,
            "result": self.result,
            "error": self.error,
            "safety_violation": {
                "type": self.safety_violation.violation_type.value,
                "severity": self.safety_violation.severity,
                "message": self.safety_violation.message
            } if self.safety_violation else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "execution_time_ms": self.execution_time_ms
        }


class ActionExecutor:
    """
    Executes network actions with safety constraints.

    Handles:
    - Safety validation
    - Human approval workflow
    - Action execution
    - Rollback on failure
    - Audit logging
    """

    def __init__(
        self,
        safety_constraints: Optional[SafetyConstraints] = None,
        approval_callback: Optional[Callable] = None
    ):
        self.safety = safety_constraints or SafetyConstraints()
        self.approval_callback = approval_callback
        self.pending_actions: Dict[str, ActionResult] = {}
        self.completed_actions: list[ActionResult] = []
        self._action_counter = 0

        # Protocol handlers (to be injected)
        self.ospf_interface = None
        self.bgp_speaker = None
        self.isis_speaker = None
        self.ospfv3_speaker = None

    def set_protocol_handlers(self, ospf_interface=None, bgp_speaker=None,
                              isis_speaker=None, ospfv3_speaker=None):
        """Inject protocol handlers for actual network operations (preserves existing values)"""
        if ospf_interface is not None:
            self.ospf_interface = ospf_interface
        if bgp_speaker is not None:
            self.bgp_speaker = bgp_speaker
        if isis_speaker is not None:
            self.isis_speaker = isis_speaker
        if ospfv3_speaker is not None:
            self.ospfv3_speaker = ospfv3_speaker

    async def execute_action(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        skip_safety: bool = False
    ) -> ActionResult:
        """
        Execute a network action with safety checks.

        Args:
            action_type: Type of action (metric_adjustment, route_injection, etc.)
            parameters: Action-specific parameters
            skip_safety: Skip safety checks (dangerous, use only for testing)

        Returns:
            ActionResult with status and outcome
        """
        # Generate action ID
        self._action_counter += 1
        action_id = f"action_{self._action_counter:04d}"

        # Create action result
        action_result = ActionResult(
            action_id=action_id,
            action_type=action_type,
            status=ActionStatus.PENDING_APPROVAL,
            parameters=parameters,
            timestamp=datetime.utcnow()
        )

        # Safety validation
        if not skip_safety:
            if not self.safety.is_action_allowed(action_type, parameters):
                # Get specific violation
                violation = self._get_safety_violation(action_type, parameters)
                action_result.safety_violation = violation
                action_result.status = ActionStatus.BLOCKED
                action_result.error = violation.message if violation else "Action requires approval"

                # Request human approval if callback provided
                if self.approval_callback and violation and not violation.action_blocked:
                    self.pending_actions[action_id] = action_result
                    approved = await self.approval_callback(action_result)
                    if approved:
                        action_result.status = ActionStatus.APPROVED
                    else:
                        action_result.status = ActionStatus.REJECTED
                        self.completed_actions.append(action_result)
                        return action_result
                else:
                    self.completed_actions.append(action_result)
                    return action_result

        # Execute action
        action_result.status = ActionStatus.EXECUTING
        start_time = asyncio.get_event_loop().time()

        try:
            if action_type == "metric_adjustment":
                result = await self._execute_metric_adjustment(parameters)
            elif action_type == "route_injection":
                result = await self._execute_route_injection(parameters)
            elif action_type == "graceful_shutdown":
                result = await self._execute_graceful_shutdown(parameters)
            elif action_type == "query_neighbors":
                result = await self._execute_query_neighbors(parameters)
            elif action_type == "query_routes":
                result = await self._execute_query_routes(parameters)
            elif action_type == "diagnostic_ping":
                result = await self._execute_ping(parameters)
            elif action_type == "diagnostic_traceroute":
                result = await self._execute_traceroute(parameters)
            else:
                raise ValueError(f"Unknown action type: {action_type}")

            action_result.status = ActionStatus.COMPLETED
            action_result.result = result

        except Exception as e:
            action_result.status = ActionStatus.FAILED
            action_result.error = str(e)

        # Record execution time
        end_time = asyncio.get_event_loop().time()
        action_result.execution_time_ms = (end_time - start_time) * 1000

        # Record in safety history
        self.safety.record_action({
            "type": action_type,
            "action_id": action_id,
            **parameters
        })

        self.completed_actions.append(action_result)
        return action_result

    def _get_safety_violation(
        self,
        action_type: str,
        parameters: Dict[str, Any]
    ) -> Optional[SafetyViolation]:
        """Get safety violation for action type"""
        if action_type == "metric_adjustment":
            return self.safety.validate_metric_adjustment(
                interface=parameters.get("interface"),
                current_metric=parameters.get("current_metric", 0),
                proposed_metric=parameters.get("proposed_metric", 0)
            )
        elif action_type == "route_injection":
            return self.safety.validate_route_injection(
                network=parameters.get("network"),
                protocol=parameters.get("protocol", "bgp")
            )
        elif action_type == "graceful_shutdown":
            return self.safety.validate_graceful_shutdown(
                protocol=parameters.get("protocol"),
                scope=parameters.get("scope", "all")
            )
        return None

    async def _execute_metric_adjustment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute OSPF metric adjustment"""
        interface = params["interface"]
        new_metric = params["proposed_metric"]

        if not self.ospf_interface:
            raise RuntimeError("OSPF interface not configured")

        # In real implementation, this would update OSPF interface cost
        # For now, return simulated result
        return {
            "interface": interface,
            "old_metric": params.get("current_metric", 0),
            "new_metric": new_metric,
            "message": f"Updated OSPF cost on {interface} to {new_metric}"
        }

    async def _execute_route_injection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute route injection (BGP/OSPF)"""
        network = params["network"]
        protocol = params.get("protocol", "bgp")

        if protocol == "bgp" and not self.bgp_speaker:
            raise RuntimeError("BGP speaker not configured")
        elif protocol == "ospf" and not self.ospf_interface:
            raise RuntimeError("OSPF interface not configured")

        # In real implementation, this would inject route into protocol
        return {
            "network": network,
            "protocol": protocol,
            "message": f"Injected route {network} into {protocol.upper()}"
        }

    async def _execute_graceful_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute graceful protocol shutdown"""
        protocol = params["protocol"]
        scope = params.get("scope", "all")

        # In real implementation, this would initiate graceful shutdown
        return {
            "protocol": protocol,
            "scope": scope,
            "message": f"Initiated graceful shutdown of {protocol} ({scope})"
        }

    async def _execute_query_neighbors(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query OSPF/BGP neighbors"""
        protocol = params.get("protocol", "ospf")

        if protocol == "ospf" and self.ospf_interface:
            # Get OSPF neighbors from interface
            neighbors = []
            for neighbor in self.ospf_interface.neighbors.values():
                neighbors.append({
                    "neighbor_id": neighbor.router_id,
                    "state": neighbor.get_state_name(),
                    "address": neighbor.ip_address
                })
            return {"protocol": "ospf", "neighbors": neighbors}

        elif protocol == "bgp" and self.bgp_speaker:
            # Get BGP peers
            peers = []
            for peer in self.bgp_speaker.agent.sessions.values():
                peers.append({
                    "peer": str(peer.config.peer_ip),
                    "as": peer.config.peer_as,
                    "state": peer.fsm.get_state_name()
                })
            return {"protocol": "bgp", "peers": peers}

        return {"protocol": protocol, "neighbors": []}

    async def _execute_query_routes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query routing table (combined OSPF + BGP)"""
        destination = params.get("destination")

        routes = []

        # Get OSPF routes from SPF calculator
        if self.ospf_interface:
            try:
                # Access SPF calculator's routing table
                if hasattr(self.ospf_interface, 'spf_calc') and self.ospf_interface.spf_calc:
                    ospf_routes = self.ospf_interface.spf_calc.routing_table
                    for prefix, route_entry in ospf_routes.items():
                        # Filter by destination if specified
                        if destination is not None and prefix != destination:
                            continue

                        routes.append({
                            "network": prefix,
                            "next_hop": route_entry.next_hop or "direct",
                            "protocol": "ospf",
                            "cost": route_entry.cost,
                            "path": route_entry.path
                        })
            except (AttributeError, KeyError, TypeError) as e:
                # Log OSPF route retrieval error but continue with other protocols
                self.logger.debug(f"OSPF route retrieval failed: {e}")

        # Get BGP routes from Loc-RIB
        if self.bgp_speaker:
            try:
                from bgp.constants import ATTR_AS_PATH

                all_routes = self.bgp_speaker.agent.loc_rib.get_all_routes()
                for route in all_routes:
                    # Filter by destination if specified
                    if destination is not None and route.prefix != destination:
                        continue

                    # Extract AS path
                    as_path = []
                    if route.has_attribute(ATTR_AS_PATH):
                        as_path_attr = route.get_attribute(ATTR_AS_PATH)
                        if hasattr(as_path_attr, 'as_list'):
                            as_path = as_path_attr.as_list()

                    routes.append({
                        "network": route.prefix,
                        "next_hop": route.next_hop or "",
                        "protocol": "bgp",
                        "as_path": as_path,
                        "source": route.source
                    })
            except (AttributeError, KeyError, TypeError, ImportError) as e:
                # Log BGP route retrieval error but continue with other protocols
                self.logger.debug(f"BGP route retrieval failed: {e}")

        # Get IS-IS routes from SPF calculator
        if self.isis_speaker:
            try:
                if hasattr(self.isis_speaker, 'spf_calculator'):
                    isis_routes = self.isis_speaker.spf_calculator.get_combined_routing_table()
                    for prefix, route in isis_routes.items():
                        # Filter by destination if specified
                        if destination is not None and prefix != destination:
                            continue

                        routes.append({
                            "network": prefix,
                            "next_hop": route.next_hop or "direct",
                            "protocol": "isis",
                            "cost": route.metric,
                            "level": route.level,
                            "route_type": route.route_type
                        })
                elif hasattr(self.isis_speaker, 'get_routes'):
                    for route in self.isis_speaker.get_routes():
                        if destination is not None and route.prefix != destination:
                            continue
                        routes.append({
                            "network": route.prefix,
                            "next_hop": route.next_hop or "direct",
                            "protocol": "isis",
                            "cost": route.metric,
                            "level": route.level
                        })
            except (AttributeError, KeyError, TypeError) as e:
                # Log IS-IS route retrieval error but continue
                self.logger.debug(f"IS-IS route retrieval failed: {e}")

        return {"routes": routes, "count": len(routes)}

    async def _execute_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute ping diagnostic using system ping"""
        import subprocess
        import re
        import ipaddress

        target = params.get("target")
        count = params.get("count", 3)
        source = params.get("source")  # Optional source IP

        if not target:
            return {"success": False, "error": "No target specified"}

        # Validate target IP to prevent command injection
        try:
            ipaddress.ip_address(target)
        except ValueError:
            return {"success": False, "error": f"Invalid IP address: {target}"}

        # Validate source IP if provided
        if source:
            try:
                ipaddress.ip_address(source)
            except ValueError:
                return {"success": False, "error": f"Invalid source IP address: {source}"}

        try:
            # Build ping command
            # -c: count, -W: timeout per packet (seconds), -I: source interface/IP
            cmd = ["ping", "-c", str(count), "-W", "2"]
            if source:
                cmd.extend(["-I", source])
            cmd.append(target)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )

            output = result.stdout + result.stderr

            # Parse ping output
            sent = 0
            received = 0
            rtt_min = None
            rtt_avg = None
            rtt_max = None

            # Parse packet statistics
            # "3 packets transmitted, 3 received, 0% packet loss"
            stats_match = re.search(r'(\d+)\s+packets\s+transmitted,\s+(\d+)\s+(?:packets\s+)?received', output)
            if stats_match:
                sent = int(stats_match.group(1))
                received = int(stats_match.group(2))

            # Parse RTT statistics
            # "rtt min/avg/max/mdev = 0.123/0.456/0.789/0.111 ms"
            rtt_match = re.search(r'rtt\s+min/avg/max/\S+\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)', output)
            if rtt_match:
                rtt_min = float(rtt_match.group(1))
                rtt_avg = float(rtt_match.group(2))
                rtt_max = float(rtt_match.group(3))

            # Calculate packet loss
            packet_loss = 0.0
            if sent > 0:
                packet_loss = ((sent - received) / sent) * 100

            result_dict = {
                "success": True,
                "target": target,
                "sent": sent,
                "received": received,
                "packet_loss": packet_loss,
                "rtt_min": rtt_min,
                "rtt_avg": rtt_avg,
                "rtt_max": rtt_max,
                "raw_output": output
            }
            if source:
                result_dict["source"] = source
            return result_dict

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Ping timed out", "target": target}
        except FileNotFoundError:
            return {"success": False, "error": "ping command not found", "target": target}
        except Exception as e:
            return {"success": False, "error": str(e), "target": target}

    async def _execute_traceroute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute traceroute diagnostic using system traceroute"""
        import subprocess
        import re
        import ipaddress

        target = params.get("target")
        max_hops = params.get("max_hops", 15)

        if not target:
            return {"success": False, "error": "No target specified"}

        # Validate target IP to prevent command injection
        try:
            ipaddress.ip_address(target)
        except ValueError:
            return {"success": False, "error": f"Invalid IP address: {target}"}

        try:
            # Use system traceroute command
            # -m: max TTL (hops), -w: wait time, -q: queries per hop
            result = subprocess.run(
                ["traceroute", "-m", str(max_hops), "-w", "2", "-q", "1", target],
                capture_output=True,
                text=True,
                timeout=60
            )

            output = result.stdout + result.stderr

            # Parse traceroute output
            hops = []
            reached = False

            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Skip the header line
                if line.startswith('traceroute'):
                    continue

                # Parse hop lines: "1  10.0.0.1  0.123 ms"
                # or "2  * * *"
                hop_match = re.match(r'^\s*(\d+)\s+(.+)', line)
                if hop_match:
                    hop_num = int(hop_match.group(1))
                    rest = hop_match.group(2).strip()

                    if rest.startswith('*'):
                        hops.append({"hop": hop_num, "ip": "*", "rtt": None})
                    else:
                        # Parse IP and RTT
                        # Format: "hostname (IP) RTT ms" or "IP RTT ms"
                        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', rest)
                        rtt_match = re.search(r'([\d.]+)\s*ms', rest)

                        ip = ip_match.group(1) if ip_match else "?"
                        rtt = float(rtt_match.group(1)) if rtt_match else None

                        hops.append({"hop": hop_num, "ip": ip, "rtt": rtt})

                        # Check if we reached the target
                        if ip == target:
                            reached = True

            return {
                "success": True,
                "target": target,
                "hops": hops,
                "reached": reached,
                "raw_output": output
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Traceroute timed out", "target": target}
        except FileNotFoundError:
            # Try tracepath as fallback (more commonly available on some systems)
            try:
                result = subprocess.run(
                    ["tracepath", "-m", str(max_hops), target],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                # Simplified parsing for tracepath
                return {
                    "success": True,
                    "target": target,
                    "hops": [],
                    "reached": False,
                    "raw_output": result.stdout + result.stderr
                }
            except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
                self.logger.debug(f"tracepath command failed: {e}")
                return {"success": False, "error": "traceroute/tracepath command not found", "target": target}
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError) as e:
            return {"success": False, "error": str(e), "target": target}

    def get_pending_actions(self) -> list[ActionResult]:
        """Get list of actions pending approval"""
        return list(self.pending_actions.values())

    def approve_action(self, action_id: str) -> bool:
        """Approve a pending action"""
        if action_id in self.pending_actions:
            action = self.pending_actions.pop(action_id)
            action.status = ActionStatus.APPROVED
            # Re-execute with approval
            asyncio.create_task(self.execute_action(
                action.action_type,
                action.parameters,
                skip_safety=True
            ))
            return True
        return False

    def reject_action(self, action_id: str, reason: str = "User rejected") -> bool:
        """Reject a pending action"""
        if action_id in self.pending_actions:
            action = self.pending_actions.pop(action_id)
            action.status = ActionStatus.REJECTED
            action.error = reason
            self.completed_actions.append(action)
            return True
        return False

    def get_action_history(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Get recent action history"""
        recent = self.completed_actions[-limit:]
        return [action.to_dict() for action in recent]
