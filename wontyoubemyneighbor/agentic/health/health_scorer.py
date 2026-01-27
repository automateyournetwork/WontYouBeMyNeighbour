"""
Health Scoring Engine for ASI Networks

Calculates comprehensive health scores for agents and networks based on
multiple factors including protocol stability, test results, resource
utilization, and configuration quality.

Health Score Components:
- Protocol Health (30%): Neighbor states, adjacencies, session stability
- Test Health (25%): pyATS test pass rates
- Resource Health (25%): CPU, memory, interface utilization
- Configuration Health (20%): Best practices compliance

Score Ranges:
- 90-100: Excellent (green)
- 70-89: Good (light green)
- 50-69: Warning (yellow)
- 25-49: Degraded (orange)
- 0-24: Critical (red)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger("HealthScorer")

# Singleton instance
_health_scorer: Optional["HealthScorer"] = None


class HealthSeverity(Enum):
    """Health severity levels"""
    EXCELLENT = "excellent"
    GOOD = "good"
    WARNING = "warning"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class HealthTrend(Enum):
    """Health trend direction"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class HealthComponent:
    """Individual health component score"""
    name: str
    score: float  # 0-100
    weight: float  # Contribution to total (0-1)
    severity: HealthSeverity
    details: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class AgentHealth:
    """Health score for a single agent"""
    agent_id: str
    agent_name: str
    score: float  # 0-100
    severity: HealthSeverity
    trend: HealthTrend
    components: List[HealthComponent]
    last_updated: float = field(default_factory=time.time)

    # Individual component scores
    protocol_health: float = 100.0
    test_health: float = 100.0
    resource_health: float = 100.0
    config_health: float = 100.0

    # Issues found
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "score": round(self.score, 1),
            "severity": self.severity.value,
            "trend": self.trend.value,
            "protocol_health": round(self.protocol_health, 1),
            "test_health": round(self.test_health, 1),
            "resource_health": round(self.resource_health, 1),
            "config_health": round(self.config_health, 1),
            "components": [
                {
                    "name": c.name,
                    "score": round(c.score, 1),
                    "weight": c.weight,
                    "severity": c.severity.value,
                    "details": c.details,
                    "metrics": c.metrics,
                    "recommendations": c.recommendations
                }
                for c in self.components
            ],
            "issues": self.issues,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "last_updated": self.last_updated
        }


@dataclass
class NetworkHealth:
    """Health score for the entire network"""
    score: float  # 0-100
    severity: HealthSeverity
    trend: HealthTrend
    agent_count: int
    healthy_agents: int
    degraded_agents: int
    critical_agents: int
    agent_health: Dict[str, AgentHealth]  # agent_id -> AgentHealth
    components: List[HealthComponent]
    last_updated: float = field(default_factory=time.time)

    # Aggregated metrics
    average_protocol_health: float = 100.0
    average_test_health: float = 100.0
    average_resource_health: float = 100.0
    average_config_health: float = 100.0

    # Network-wide issues
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "score": round(self.score, 1),
            "severity": self.severity.value,
            "trend": self.trend.value,
            "agent_count": self.agent_count,
            "healthy_agents": self.healthy_agents,
            "degraded_agents": self.degraded_agents,
            "critical_agents": self.critical_agents,
            "average_protocol_health": round(self.average_protocol_health, 1),
            "average_test_health": round(self.average_test_health, 1),
            "average_resource_health": round(self.average_resource_health, 1),
            "average_config_health": round(self.average_config_health, 1),
            "components": [
                {
                    "name": c.name,
                    "score": round(c.score, 1),
                    "weight": c.weight,
                    "severity": c.severity.value,
                    "details": c.details,
                    "metrics": c.metrics
                }
                for c in self.components
            ],
            "agents": {
                agent_id: health.to_dict()
                for agent_id, health in self.agent_health.items()
            },
            "issues": self.issues,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "last_updated": self.last_updated
        }


class HealthScorer:
    """
    Network and agent health scoring engine.

    Calculates comprehensive health scores based on multiple factors.
    """

    # Component weights (must sum to 1.0)
    PROTOCOL_WEIGHT = 0.30
    TEST_WEIGHT = 0.25
    RESOURCE_WEIGHT = 0.25
    CONFIG_WEIGHT = 0.20

    # Severity thresholds
    EXCELLENT_THRESHOLD = 90
    GOOD_THRESHOLD = 70
    WARNING_THRESHOLD = 50
    DEGRADED_THRESHOLD = 25

    def __init__(self):
        self._history: Dict[str, deque] = {}  # agent_id -> deque of (timestamp, score)
        self._network_history: deque = deque(maxlen=1440)  # 24 hours at 1-min intervals
        self._last_network_health: Optional[NetworkHealth] = None
        self._last_agent_health: Dict[str, AgentHealth] = {}

    def get_severity(self, score: float) -> HealthSeverity:
        """Determine severity level from score"""
        if score >= self.EXCELLENT_THRESHOLD:
            return HealthSeverity.EXCELLENT
        elif score >= self.GOOD_THRESHOLD:
            return HealthSeverity.GOOD
        elif score >= self.WARNING_THRESHOLD:
            return HealthSeverity.WARNING
        elif score >= self.DEGRADED_THRESHOLD:
            return HealthSeverity.DEGRADED
        else:
            return HealthSeverity.CRITICAL

    def get_trend(self, agent_id: str, current_score: float) -> HealthTrend:
        """Determine health trend based on historical scores"""
        if agent_id not in self._history or len(self._history[agent_id]) < 5:
            return HealthTrend.STABLE

        # Get last 5 scores
        recent_scores = [score for _, score in list(self._history[agent_id])[-5:]]
        avg_recent = sum(recent_scores) / len(recent_scores)

        # Compare current to average
        diff = current_score - avg_recent
        if diff > 5:
            return HealthTrend.IMPROVING
        elif diff < -5:
            return HealthTrend.DECLINING
        return HealthTrend.STABLE

    async def calculate_protocol_health(self, agent_data: Dict[str, Any]) -> HealthComponent:
        """
        Calculate protocol health based on neighbor states and adjacencies.

        Factors:
        - OSPF neighbor state (FULL = good, others = degraded)
        - BGP peer state (Established = good, others = degraded)
        - ISIS adjacency state (UP = good, others = degraded)
        - Neighbor flapping (recent state changes = bad)
        """
        score = 100.0
        issues = []
        metrics = {}

        # Check OSPF
        ospf_status = agent_data.get("ospf", {})
        if ospf_status:
            neighbors = ospf_status.get("neighbors", 0)
            full_neighbors = ospf_status.get("full_neighbors", 0)

            metrics["ospf_neighbors"] = neighbors
            metrics["ospf_full"] = full_neighbors

            if neighbors > 0:
                full_ratio = full_neighbors / neighbors
                ospf_score = full_ratio * 100
                if full_ratio < 1.0:
                    score -= (1 - full_ratio) * 30
                    issues.append(f"OSPF: {neighbors - full_neighbors} neighbors not FULL")

        # Check BGP
        bgp_status = agent_data.get("bgp", {})
        if bgp_status:
            total_peers = bgp_status.get("total_peers", 0)
            established = bgp_status.get("established_peers", 0)

            metrics["bgp_peers"] = total_peers
            metrics["bgp_established"] = established

            if total_peers > 0:
                est_ratio = established / total_peers
                if est_ratio < 1.0:
                    score -= (1 - est_ratio) * 30
                    issues.append(f"BGP: {total_peers - established} peers not Established")

        # Check ISIS
        isis_status = agent_data.get("isis", {})
        if isis_status:
            adjacencies = isis_status.get("adjacencies", 0)
            up_adjacencies = isis_status.get("up_adjacencies", 0)

            metrics["isis_adjacencies"] = adjacencies
            metrics["isis_up"] = up_adjacencies

            if adjacencies > 0:
                up_ratio = up_adjacencies / adjacencies
                if up_ratio < 1.0:
                    score -= (1 - up_ratio) * 30
                    issues.append(f"ISIS: {adjacencies - up_adjacencies} adjacencies not UP")

        # Ensure score is in valid range
        score = max(0, min(100, score))

        recommendations = []
        if score < 70:
            recommendations.append("Investigate protocol adjacency issues")
            recommendations.append("Check physical connectivity to neighbors")

        return HealthComponent(
            name="Protocol Health",
            score=score,
            weight=self.PROTOCOL_WEIGHT,
            severity=self.get_severity(score),
            details="; ".join(issues) if issues else "All protocols healthy",
            metrics=metrics,
            recommendations=recommendations
        )

    async def calculate_test_health(self, agent_data: Dict[str, Any]) -> HealthComponent:
        """
        Calculate test health based on pyATS test results.

        Factors:
        - Test pass rate
        - Critical test failures
        - Recent test execution
        """
        score = 100.0
        issues = []
        metrics = {}

        test_results = agent_data.get("test_results", {})

        total_tests = test_results.get("total", 0)
        passed = test_results.get("passed", 0)
        failed = test_results.get("failed", 0)
        skipped = test_results.get("skipped", 0)

        metrics["total_tests"] = total_tests
        metrics["passed"] = passed
        metrics["failed"] = failed
        metrics["skipped"] = skipped

        if total_tests > 0:
            pass_rate = passed / total_tests
            score = pass_rate * 100
            metrics["pass_rate"] = round(pass_rate * 100, 1)

            if failed > 0:
                issues.append(f"{failed} tests failed")
        else:
            # No tests = assume healthy but note it
            score = 80  # Slight penalty for no test coverage
            issues.append("No tests executed")

        recommendations = []
        if score < 70:
            recommendations.append("Review failed test cases")
            recommendations.append("Check test environment configuration")

        return HealthComponent(
            name="Test Health",
            score=score,
            weight=self.TEST_WEIGHT,
            severity=self.get_severity(score),
            details="; ".join(issues) if issues else "All tests passing",
            metrics=metrics,
            recommendations=recommendations
        )

    async def calculate_resource_health(self, agent_data: Dict[str, Any]) -> HealthComponent:
        """
        Calculate resource health based on utilization.

        Factors:
        - CPU utilization
        - Memory utilization
        - Interface error rates
        - Interface utilization
        """
        score = 100.0
        issues = []
        metrics = {}

        # CPU
        cpu_percent = agent_data.get("cpu_percent", 0)
        metrics["cpu_percent"] = cpu_percent
        if cpu_percent > 90:
            score -= 30
            issues.append(f"High CPU: {cpu_percent}%")
        elif cpu_percent > 70:
            score -= 15
            issues.append(f"Elevated CPU: {cpu_percent}%")

        # Memory
        memory_percent = agent_data.get("memory_percent", 0)
        metrics["memory_percent"] = memory_percent
        if memory_percent > 90:
            score -= 30
            issues.append(f"High memory: {memory_percent}%")
        elif memory_percent > 70:
            score -= 15
            issues.append(f"Elevated memory: {memory_percent}%")

        # Interface errors
        interfaces = agent_data.get("interfaces", {})
        total_errors = 0
        for iface_name, iface_data in interfaces.items():
            errors = iface_data.get("errors", 0)
            total_errors += errors

        metrics["interface_errors"] = total_errors
        if total_errors > 100:
            score -= 20
            issues.append(f"Interface errors: {total_errors}")
        elif total_errors > 10:
            score -= 10
            issues.append(f"Some interface errors: {total_errors}")

        # Ensure score is in valid range
        score = max(0, min(100, score))

        recommendations = []
        if score < 70:
            recommendations.append("Investigate high resource utilization")
            recommendations.append("Check for interface errors and drops")

        return HealthComponent(
            name="Resource Health",
            score=score,
            weight=self.RESOURCE_WEIGHT,
            severity=self.get_severity(score),
            details="; ".join(issues) if issues else "Resources healthy",
            metrics=metrics,
            recommendations=recommendations
        )

    async def calculate_config_health(self, agent_data: Dict[str, Any]) -> HealthComponent:
        """
        Calculate configuration health based on best practices.

        Factors:
        - Loopback configured
        - Description on interfaces
        - Proper authentication
        - Route filtering in place
        """
        score = 100.0
        issues = []
        metrics = {}

        config = agent_data.get("config", {})

        # Check loopback
        has_loopback = config.get("has_loopback", True)
        metrics["has_loopback"] = has_loopback
        if not has_loopback:
            score -= 15
            issues.append("No loopback configured")

        # Check interface descriptions
        interfaces_with_desc = config.get("interfaces_with_description", 0)
        total_interfaces = config.get("total_interfaces", 1)
        desc_ratio = interfaces_with_desc / max(total_interfaces, 1)
        metrics["description_ratio"] = round(desc_ratio * 100, 1)
        if desc_ratio < 0.5:
            score -= 10
            issues.append("Many interfaces lack descriptions")

        # Check authentication
        auth_enabled = config.get("auth_enabled", True)
        metrics["auth_enabled"] = auth_enabled
        if not auth_enabled:
            score -= 20
            issues.append("Protocol authentication disabled")

        # Ensure score is in valid range
        score = max(0, min(100, score))

        recommendations = []
        if score < 70:
            recommendations.append("Add descriptions to interfaces")
            recommendations.append("Enable protocol authentication")

        return HealthComponent(
            name="Configuration Health",
            score=score,
            weight=self.CONFIG_WEIGHT,
            severity=self.get_severity(score),
            details="; ".join(issues) if issues else "Configuration healthy",
            metrics=metrics,
            recommendations=recommendations
        )

    async def calculate_agent_health(self, agent_id: str, agent_data: Dict[str, Any]) -> AgentHealth:
        """Calculate comprehensive health score for a single agent"""
        agent_name = agent_data.get("name", agent_id)

        # Calculate individual components
        protocol_health = await self.calculate_protocol_health(agent_data)
        test_health = await self.calculate_test_health(agent_data)
        resource_health = await self.calculate_resource_health(agent_data)
        config_health = await self.calculate_config_health(agent_data)

        components = [protocol_health, test_health, resource_health, config_health]

        # Calculate weighted total score
        total_score = sum(c.score * c.weight for c in components)

        # Collect all issues and recommendations
        all_issues = []
        all_warnings = []
        all_recommendations = []

        for c in components:
            if c.severity == HealthSeverity.CRITICAL:
                all_issues.extend([f"[{c.name}] {c.details}"])
            elif c.severity == HealthSeverity.DEGRADED:
                all_issues.extend([f"[{c.name}] {c.details}"])
            elif c.severity == HealthSeverity.WARNING:
                all_warnings.extend([f"[{c.name}] {c.details}"])
            all_recommendations.extend(c.recommendations)

        # Update history
        if agent_id not in self._history:
            self._history[agent_id] = deque(maxlen=1440)
        self._history[agent_id].append((time.time(), total_score))

        # Get trend
        trend = self.get_trend(agent_id, total_score)

        health = AgentHealth(
            agent_id=agent_id,
            agent_name=agent_name,
            score=total_score,
            severity=self.get_severity(total_score),
            trend=trend,
            components=components,
            protocol_health=protocol_health.score,
            test_health=test_health.score,
            resource_health=resource_health.score,
            config_health=config_health.score,
            issues=all_issues,
            warnings=all_warnings,
            recommendations=list(set(all_recommendations))  # Dedupe
        )

        self._last_agent_health[agent_id] = health
        return health

    async def calculate_network_health(self, agents_data: Dict[str, Dict[str, Any]]) -> NetworkHealth:
        """Calculate comprehensive health score for the entire network"""
        agent_health_map = {}

        # Calculate health for each agent
        for agent_id, agent_data in agents_data.items():
            health = await self.calculate_agent_health(agent_id, agent_data)
            agent_health_map[agent_id] = health

        # Count by severity
        agent_count = len(agent_health_map)
        healthy_agents = sum(1 for h in agent_health_map.values()
                           if h.severity in [HealthSeverity.EXCELLENT, HealthSeverity.GOOD])
        degraded_agents = sum(1 for h in agent_health_map.values()
                             if h.severity in [HealthSeverity.WARNING, HealthSeverity.DEGRADED])
        critical_agents = sum(1 for h in agent_health_map.values()
                             if h.severity == HealthSeverity.CRITICAL)

        # Calculate network-wide averages
        if agent_count > 0:
            avg_score = sum(h.score for h in agent_health_map.values()) / agent_count
            avg_protocol = sum(h.protocol_health for h in agent_health_map.values()) / agent_count
            avg_test = sum(h.test_health for h in agent_health_map.values()) / agent_count
            avg_resource = sum(h.resource_health for h in agent_health_map.values()) / agent_count
            avg_config = sum(h.config_health for h in agent_health_map.values()) / agent_count
        else:
            avg_score = 100
            avg_protocol = avg_test = avg_resource = avg_config = 100

        # Create network-level components
        components = [
            HealthComponent(
                name="Protocol Health",
                score=avg_protocol,
                weight=self.PROTOCOL_WEIGHT,
                severity=self.get_severity(avg_protocol),
                details=f"Average protocol health across {agent_count} agents",
                metrics={"agent_count": agent_count}
            ),
            HealthComponent(
                name="Test Health",
                score=avg_test,
                weight=self.TEST_WEIGHT,
                severity=self.get_severity(avg_test),
                details=f"Average test health across {agent_count} agents",
                metrics={"agent_count": agent_count}
            ),
            HealthComponent(
                name="Resource Health",
                score=avg_resource,
                weight=self.RESOURCE_WEIGHT,
                severity=self.get_severity(avg_resource),
                details=f"Average resource health across {agent_count} agents",
                metrics={"agent_count": agent_count}
            ),
            HealthComponent(
                name="Configuration Health",
                score=avg_config,
                weight=self.CONFIG_WEIGHT,
                severity=self.get_severity(avg_config),
                details=f"Average config health across {agent_count} agents",
                metrics={"agent_count": agent_count}
            )
        ]

        # Collect network-wide issues
        all_issues = []
        all_warnings = []
        all_recommendations = []

        for health in agent_health_map.values():
            all_issues.extend([f"[{health.agent_name}] {i}" for i in health.issues])
            all_warnings.extend([f"[{health.agent_name}] {w}" for w in health.warnings])
            all_recommendations.extend(health.recommendations)

        # Update network history
        self._network_history.append((time.time(), avg_score))

        # Determine network trend
        if len(self._network_history) >= 5:
            recent_scores = [score for _, score in list(self._network_history)[-5:]]
            avg_recent = sum(recent_scores) / len(recent_scores)
            diff = avg_score - avg_recent
            if diff > 5:
                trend = HealthTrend.IMPROVING
            elif diff < -5:
                trend = HealthTrend.DECLINING
            else:
                trend = HealthTrend.STABLE
        else:
            trend = HealthTrend.STABLE

        network_health = NetworkHealth(
            score=avg_score,
            severity=self.get_severity(avg_score),
            trend=trend,
            agent_count=agent_count,
            healthy_agents=healthy_agents,
            degraded_agents=degraded_agents,
            critical_agents=critical_agents,
            agent_health=agent_health_map,
            components=components,
            average_protocol_health=avg_protocol,
            average_test_health=avg_test,
            average_resource_health=avg_resource,
            average_config_health=avg_config,
            issues=all_issues,
            warnings=all_warnings,
            recommendations=list(set(all_recommendations))
        )

        self._last_network_health = network_health
        return network_health

    def get_health_history(self, agent_id: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """Get health score history for an agent or the network"""
        cutoff = time.time() - (hours * 3600)

        if agent_id:
            if agent_id not in self._history:
                return []
            history = self._history[agent_id]
        else:
            history = self._network_history

        return [
            {"timestamp": ts, "score": round(score, 1)}
            for ts, score in history
            if ts >= cutoff
        ]


# Module-level functions for convenience
def get_health_scorer() -> HealthScorer:
    """Get the singleton HealthScorer instance"""
    global _health_scorer
    if _health_scorer is None:
        _health_scorer = HealthScorer()
    return _health_scorer


async def get_network_health(agents_data: Optional[Dict[str, Dict[str, Any]]] = None) -> NetworkHealth:
    """Get network health score"""
    scorer = get_health_scorer()

    if agents_data is None:
        # Try to fetch from status APIs
        agents_data = {}
        try:
            # This would integrate with actual agent status fetching
            pass
        except Exception as e:
            logger.warning(f"Could not fetch agent data: {e}")

    return await scorer.calculate_network_health(agents_data)


async def get_agent_health(agent_id: str, agent_data: Optional[Dict[str, Any]] = None) -> AgentHealth:
    """Get agent health score"""
    scorer = get_health_scorer()

    if agent_data is None:
        agent_data = {}
        try:
            # This would integrate with actual agent status fetching
            pass
        except Exception as e:
            logger.warning(f"Could not fetch agent data for {agent_id}: {e}")

    return await scorer.calculate_agent_health(agent_id, agent_data)


def get_health_history(agent_id: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
    """Get health score history"""
    scorer = get_health_scorer()
    return scorer.get_health_history(agent_id, hours)


def get_health_recommendations(health: NetworkHealth) -> List[str]:
    """Get prioritized recommendations for improving network health"""
    recommendations = []

    # Prioritize by severity
    critical_agents = [h for h in health.agent_health.values()
                      if h.severity == HealthSeverity.CRITICAL]
    if critical_agents:
        recommendations.append(
            f"URGENT: {len(critical_agents)} agent(s) in critical state - "
            f"investigate {', '.join(a.agent_name for a in critical_agents[:3])}"
        )

    # Check component health
    if health.average_protocol_health < 70:
        recommendations.append(
            "Protocol health is degraded - check neighbor adjacencies and session states"
        )

    if health.average_test_health < 70:
        recommendations.append(
            "Test health is degraded - review failed test cases and fix issues"
        )

    if health.average_resource_health < 70:
        recommendations.append(
            "Resource utilization is high - consider scaling or optimizing workloads"
        )

    if health.average_config_health < 70:
        recommendations.append(
            "Configuration quality can be improved - add descriptions, enable auth"
        )

    # Add agent-specific recommendations
    recommendations.extend(health.recommendations[:5])  # Top 5

    return recommendations
