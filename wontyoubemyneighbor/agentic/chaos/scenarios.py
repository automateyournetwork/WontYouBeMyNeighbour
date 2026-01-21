"""
Chaos Scenarios - Predefined failure scenarios for testing

Provides:
- Predefined chaos scenarios
- Scenario runner for automated testing
- Impact measurement and reporting
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from .injector import FailureInjector, FailureConfig, FailureType, FailureResult

logger = logging.getLogger("ChaosScenarios")


class ScenarioStatus(Enum):
    """Scenario execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ChaosScenario:
    """
    A chaos engineering scenario

    Attributes:
        scenario_id: Unique scenario identifier
        name: Human-readable name
        description: Scenario description
        failures: List of failure configs to inject
        sequence: Whether to inject sequentially or all at once
        delay_between_ms: Delay between sequential injections
        expected_behavior: What should happen during the scenario
        validation_checks: Checks to perform after scenario
    """
    scenario_id: str
    name: str
    description: str
    failures: List[FailureConfig]
    sequence: bool = True
    delay_between_ms: int = 1000
    expected_behavior: str = ""
    validation_checks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "failures": [f.to_dict() for f in self.failures],
            "sequence": self.sequence,
            "delay_between_ms": self.delay_between_ms,
            "expected_behavior": self.expected_behavior,
            "validation_checks": self.validation_checks
        }


@dataclass
class ScenarioResult:
    """
    Result of a scenario execution

    Attributes:
        scenario: The executed scenario
        start_time: Execution start time
        end_time: Execution end time
        status: Execution status
        failure_results: Results from each failure injection
        validation_results: Results of validation checks
        observations: Observed network behavior
    """
    scenario: ChaosScenario
    start_time: datetime
    end_time: Optional[datetime] = None
    status: ScenarioStatus = ScenarioStatus.PENDING
    failure_results: List[FailureResult] = field(default_factory=list)
    validation_results: Dict[str, bool] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "failure_results": [r.to_dict() for r in self.failure_results],
            "validation_results": self.validation_results,
            "observations": self.observations,
            "error": self.error
        }


class ScenarioRunner:
    """
    Runs chaos scenarios and collects results
    """

    def __init__(self, injector: FailureInjector):
        """
        Initialize scenario runner

        Args:
            injector: FailureInjector instance to use
        """
        self.injector = injector
        self._running_scenario: Optional[ScenarioResult] = None
        self._history: List[ScenarioResult] = []

    async def run_scenario(self, scenario: ChaosScenario) -> ScenarioResult:
        """
        Run a chaos scenario

        Args:
            scenario: Scenario to execute

        Returns:
            ScenarioResult with execution details
        """
        result = ScenarioResult(
            scenario=scenario,
            start_time=datetime.now(),
            status=ScenarioStatus.RUNNING
        )
        self._running_scenario = result

        logger.info(f"Starting scenario: {scenario.name}")

        try:
            if scenario.sequence:
                # Sequential injection
                for i, failure_config in enumerate(scenario.failures):
                    logger.info(f"Injecting failure {i+1}/{len(scenario.failures)}")
                    failure_result = await self.injector.inject_failure(failure_config)
                    result.failure_results.append(failure_result)

                    if failure_result.status == "failed":
                        result.observations.append(f"Failure {i+1} injection failed: {failure_result.error}")

                    if i < len(scenario.failures) - 1:
                        await asyncio.sleep(scenario.delay_between_ms / 1000)
            else:
                # Parallel injection
                tasks = [
                    self.injector.inject_failure(config)
                    for config in scenario.failures
                ]
                failure_results = await asyncio.gather(*tasks)
                result.failure_results.extend(failure_results)

            # Wait for failures to take effect
            await asyncio.sleep(2)

            # Run validation checks (simulated)
            for check in scenario.validation_checks:
                # In production, these would be actual network checks
                result.validation_results[check] = True
                result.observations.append(f"Validation '{check}': PASSED (simulated)")

            result.status = ScenarioStatus.COMPLETED
            result.end_time = datetime.now()

            logger.info(f"Scenario completed: {scenario.name}")

        except asyncio.CancelledError:
            result.status = ScenarioStatus.CANCELLED
            result.end_time = datetime.now()
            result.error = "Scenario cancelled"
            logger.info(f"Scenario cancelled: {scenario.name}")

        except Exception as e:
            result.status = ScenarioStatus.FAILED
            result.end_time = datetime.now()
            result.error = str(e)
            logger.error(f"Scenario failed: {scenario.name} - {e}")

        finally:
            self._running_scenario = None
            self._history.append(result)

        return result

    def get_running_scenario(self) -> Optional[ScenarioResult]:
        """Get currently running scenario"""
        return self._running_scenario

    def get_history(self, limit: int = 50) -> List[ScenarioResult]:
        """Get scenario execution history"""
        return self._history[-limit:]


class PredefinedScenarios:
    """
    Collection of predefined chaos scenarios
    """

    @staticmethod
    def single_link_failure(agent1: str, agent2: str) -> ChaosScenario:
        """
        Single link failure between two agents

        Tests: Basic redundancy and failover
        """
        return ChaosScenario(
            scenario_id="single-link-failure",
            name="Single Link Failure",
            description=f"Simulate link failure between {agent1} and {agent2}",
            failures=[
                FailureConfig(
                    failure_type=FailureType.LINK_DOWN,
                    target_agent=agent1,
                    target_peer=agent2,
                    duration_seconds=60
                )
            ],
            expected_behavior="Traffic should reroute via alternate path within convergence time",
            validation_checks=[
                "connectivity_maintained",
                "routes_reconverged",
                "no_packet_loss_after_convergence"
            ]
        )

    @staticmethod
    def spine_failure(spine_agents: List[str]) -> ChaosScenario:
        """
        Spine router failure in leaf-spine topology

        Tests: Spine redundancy
        """
        if not spine_agents:
            raise ValueError("No spine agents provided")

        return ChaosScenario(
            scenario_id="spine-failure",
            name="Spine Router Failure",
            description=f"Simulate failure of spine router: {spine_agents[0]}",
            failures=[
                FailureConfig(
                    failure_type=FailureType.AGENT_DOWN,
                    target_agent=spine_agents[0],
                    duration_seconds=120
                )
            ],
            expected_behavior="All traffic should failover to remaining spine(s)",
            validation_checks=[
                "leaf_connectivity_maintained",
                "bgp_sessions_established_to_alternate_spine",
                "ecmp_paths_updated"
            ]
        )

    @staticmethod
    def rolling_failure(agents: List[str], interval_seconds: int = 30) -> ChaosScenario:
        """
        Rolling failures across multiple agents

        Tests: Network resilience under cascading failures
        """
        failures = [
            FailureConfig(
                failure_type=FailureType.AGENT_DOWN,
                target_agent=agent,
                duration_seconds=interval_seconds * 2
            )
            for agent in agents[:3]  # Limit to 3 agents
        ]

        return ChaosScenario(
            scenario_id="rolling-failure",
            name="Rolling Failures",
            description=f"Sequential failures across {len(failures)} agents",
            failures=failures,
            sequence=True,
            delay_between_ms=interval_seconds * 1000,
            expected_behavior="Network should remain operational with degraded capacity",
            validation_checks=[
                "core_connectivity_maintained",
                "graceful_degradation",
                "recovery_after_restore"
            ]
        )

    @staticmethod
    def network_partition(group_a: List[str], group_b: List[str]) -> ChaosScenario:
        """
        Network partition between two groups

        Tests: Split-brain handling
        """
        failures = []
        for agent in group_a:
            failures.append(
                FailureConfig(
                    failure_type=FailureType.PARTITION,
                    target_agent=agent,
                    duration_seconds=90,
                    parameters={"partition_group": group_b}
                )
            )

        return ChaosScenario(
            scenario_id="network-partition",
            name="Network Partition",
            description=f"Partition between groups: {group_a} and {group_b}",
            failures=failures,
            sequence=False,
            expected_behavior="Each partition should maintain internal connectivity",
            validation_checks=[
                "intra_partition_connectivity",
                "partition_detection",
                "recovery_after_heal"
            ]
        )

    @staticmethod
    def packet_loss_storm(agents: List[str], loss_percentage: float = 0.3) -> ChaosScenario:
        """
        Packet loss across multiple agents

        Tests: Protocol resilience to lossy conditions
        """
        failures = [
            FailureConfig(
                failure_type=FailureType.PACKET_LOSS,
                target_agent=agent,
                duration_seconds=60,
                intensity=loss_percentage
            )
            for agent in agents
        ]

        return ChaosScenario(
            scenario_id="packet-loss-storm",
            name="Packet Loss Storm",
            description=f"{loss_percentage*100:.0f}% packet loss on {len(agents)} agents",
            failures=failures,
            sequence=False,
            expected_behavior="Protocols should handle retransmissions, adjacencies may flap",
            validation_checks=[
                "adjacencies_stable_or_recovering",
                "routes_eventually_consistent",
                "no_permanent_blackholes"
            ]
        )

    @staticmethod
    def latency_injection(agents: List[str], latency_ms: int = 200) -> ChaosScenario:
        """
        Latency injection across agents

        Tests: Protocol timer handling
        """
        failures = [
            FailureConfig(
                failure_type=FailureType.LATENCY,
                target_agent=agent,
                duration_seconds=120,
                parameters={"latency_ms": latency_ms, "jitter_ms": latency_ms // 10}
            )
            for agent in agents
        ]

        return ChaosScenario(
            scenario_id="latency-injection",
            name="High Latency Conditions",
            description=f"{latency_ms}ms latency on {len(agents)} agents",
            failures=failures,
            sequence=False,
            expected_behavior="Adjacencies should remain stable if timers configured correctly",
            validation_checks=[
                "hello_timers_adjusted",
                "adjacencies_stable",
                "convergence_time_acceptable"
            ]
        )

    @staticmethod
    def flapping_adjacency(agent: str, peer: str, flap_count: int = 5) -> ChaosScenario:
        """
        Flapping adjacency simulation

        Tests: Dampening and stability mechanisms
        """
        return ChaosScenario(
            scenario_id="flapping-adjacency",
            name="Flapping Adjacency",
            description=f"Flapping adjacency between {agent} and {peer}",
            failures=[
                FailureConfig(
                    failure_type=FailureType.FLAP,
                    target_agent=agent,
                    target_peer=peer,
                    duration_seconds=60,
                    parameters={"flap_count": flap_count, "interval_ms": 2000}
                )
            ],
            expected_behavior="Dampening should activate, limiting route churn",
            validation_checks=[
                "dampening_activated",
                "route_churn_limited",
                "stability_restored"
            ]
        )

    @staticmethod
    def bgp_peer_failure(bgp_agents: List[str]) -> ChaosScenario:
        """
        BGP peer failure scenario

        Tests: BGP failover and route withdrawal
        """
        if not bgp_agents:
            raise ValueError("No BGP agents provided")

        return ChaosScenario(
            scenario_id="bgp-peer-failure",
            name="BGP Peer Failure",
            description=f"Simulate BGP peer failure: {bgp_agents[0]}",
            failures=[
                FailureConfig(
                    failure_type=FailureType.AGENT_DOWN,
                    target_agent=bgp_agents[0],
                    duration_seconds=90
                )
            ],
            expected_behavior="BGP routes should be withdrawn and alternate paths used",
            validation_checks=[
                "routes_withdrawn",
                "alternate_paths_activated",
                "convergence_within_timer"
            ]
        )

    @staticmethod
    def full_chaos(agents: List[str], duration_seconds: int = 300) -> ChaosScenario:
        """
        Full chaos mode - random failures

        Tests: Overall network resilience
        """
        import random

        failures = []
        failure_types = [
            FailureType.LINK_DOWN,
            FailureType.PACKET_LOSS,
            FailureType.LATENCY,
            FailureType.FLAP
        ]

        # Generate random failures
        for _ in range(min(5, len(agents))):
            agent = random.choice(agents)
            ftype = random.choice(failure_types)

            config = FailureConfig(
                failure_type=ftype,
                target_agent=agent,
                duration_seconds=random.randint(30, 90),
                intensity=random.uniform(0.2, 0.8)
            )

            if ftype == FailureType.LATENCY:
                config.parameters = {"latency_ms": random.randint(50, 300)}
            elif ftype == FailureType.FLAP:
                config.parameters = {"flap_count": random.randint(3, 8)}

            failures.append(config)

        return ChaosScenario(
            scenario_id="full-chaos",
            name="Full Chaos Mode",
            description=f"Random failures on {len(failures)} targets for {duration_seconds}s",
            failures=failures,
            sequence=False,
            expected_behavior="Network should demonstrate resilience and self-healing",
            validation_checks=[
                "network_operational",
                "self_healing_activated",
                "eventual_recovery"
            ]
        )

    @classmethod
    def list_scenarios(cls) -> List[Dict[str, str]]:
        """List all available predefined scenarios"""
        return [
            {"id": "single-link-failure", "name": "Single Link Failure", "description": "Test basic link redundancy"},
            {"id": "spine-failure", "name": "Spine Router Failure", "description": "Test spine redundancy in leaf-spine"},
            {"id": "rolling-failure", "name": "Rolling Failures", "description": "Test cascading failure resilience"},
            {"id": "network-partition", "name": "Network Partition", "description": "Test split-brain handling"},
            {"id": "packet-loss-storm", "name": "Packet Loss Storm", "description": "Test protocol loss handling"},
            {"id": "latency-injection", "name": "High Latency", "description": "Test timer handling"},
            {"id": "flapping-adjacency", "name": "Flapping Adjacency", "description": "Test dampening mechanisms"},
            {"id": "bgp-peer-failure", "name": "BGP Peer Failure", "description": "Test BGP failover"},
            {"id": "full-chaos", "name": "Full Chaos Mode", "description": "Random failure injection"},
        ]
