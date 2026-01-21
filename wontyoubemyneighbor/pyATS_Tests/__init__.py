"""
pyATS Test Library for Agent-Defined Networks

This library provides AETest-based test suites for validating network agents.
Each agent can run tests based on its configured protocols.

Test Categories:
- common/: Tests applicable to all agents (connectivity, interfaces, resources)
- protocols/: Protocol-specific tests (OSPF, BGP, IS-IS, VXLAN, EVPN, MPLS)
- services/: Service-specific tests (DHCP, DNS)
- templates/: Test templates for creating custom tests

Usage:
    from pyATS_Tests import get_tests_for_agent

    tests = get_tests_for_agent(agent_config)
    results = await run_tests(tests)
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger("pyATS_Tests")


class TestStatus(Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestSeverity(Enum):
    """Test failure severity"""
    CRITICAL = "critical"  # Affects service availability
    MAJOR = "major"        # Significant degradation
    MINOR = "minor"        # Non-critical issue
    INFO = "info"          # Informational check


@dataclass
class TestResult:
    """Result of a single test execution"""
    test_id: str
    test_name: str
    status: TestStatus
    severity: TestSeverity
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp
        }


@dataclass
class TestSuite:
    """Collection of related tests"""
    suite_id: str
    suite_name: str
    description: str
    protocol: Optional[str] = None  # None for common tests
    tests: List["BaseTest"] = field(default_factory=list)
    results: List[TestResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "description": self.description,
            "protocol": self.protocol,
            "test_count": len(self.tests),
            "results": [r.to_dict() for r in self.results]
        }

    @property
    def passed(self) -> int:
        return len([r for r in self.results if r.status == TestStatus.PASSED])

    @property
    def failed(self) -> int:
        return len([r for r in self.results if r.status == TestStatus.FAILED])

    @property
    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": len([r for r in self.results if r.status == TestStatus.SKIPPED]),
            "error": len([r for r in self.results if r.status == TestStatus.ERROR])
        }


class BaseTest:
    """Base class for all tests"""

    test_id: str = "base_test"
    test_name: str = "Base Test"
    description: str = "Base test class"
    severity: TestSeverity = TestSeverity.MINOR
    timeout: float = 30.0  # seconds

    def __init__(self, agent_config: Dict[str, Any]):
        """
        Initialize test with agent configuration

        Args:
            agent_config: Agent TOON configuration dict
        """
        self.agent_config = agent_config
        self.agent_id = agent_config.get("id", "unknown")
        self.router_id = agent_config.get("r", "0.0.0.0")
        self.interfaces = agent_config.get("ifs", [])
        self.protocols = agent_config.get("protos", [])

    async def setup(self) -> None:
        """Pre-test setup (override in subclass)"""
        pass

    async def execute(self) -> TestResult:
        """Execute the test (must override in subclass)"""
        raise NotImplementedError("Subclass must implement execute()")

    async def cleanup(self) -> None:
        """Post-test cleanup (override in subclass)"""
        pass

    async def run(self) -> TestResult:
        """Run the complete test lifecycle"""
        start_time = datetime.now()

        try:
            await self.setup()
            result = await asyncio.wait_for(
                self.execute(),
                timeout=self.timeout
            )
            result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            return result

        except asyncio.TimeoutError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Test timed out after {self.timeout}s",
                duration_ms=self.timeout * 1000
            )
        except Exception as e:
            logger.exception(f"Test {self.test_id} failed with exception")
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Test error: {str(e)}",
                duration_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
        finally:
            try:
                await self.cleanup()
            except Exception as e:
                logger.warning(f"Cleanup failed for {self.test_id}: {e}")


def get_protocol_from_config(agent_config: Dict[str, Any]) -> List[str]:
    """Extract enabled protocols from agent configuration"""
    protocols = []
    for proto in agent_config.get("protos", []):
        proto_type = proto.get("p", "")
        if proto_type:
            protocols.append(proto_type.lower())
    return protocols


def get_tests_for_agent(agent_config: Dict[str, Any]) -> List[TestSuite]:
    """
    Get all applicable test suites for an agent based on its configuration

    Args:
        agent_config: Agent TOON configuration dict

    Returns:
        List of TestSuite objects applicable to this agent
    """
    from .common import connectivity_tests, interface_tests, resource_tests
    from .protocols import ospf_tests, bgp_tests, isis_tests, vxlan_tests, mpls_tests
    from .services import dhcp_tests, dns_tests

    suites = []

    # Always include common tests
    suites.append(connectivity_tests.get_suite(agent_config))
    suites.append(interface_tests.get_suite(agent_config))
    suites.append(resource_tests.get_suite(agent_config))

    # Add protocol-specific tests based on configuration
    protocols = get_protocol_from_config(agent_config)

    if "ospf" in protocols or "ospfv3" in protocols:
        suites.append(ospf_tests.get_suite(agent_config))

    if "ibgp" in protocols or "ebgp" in protocols:
        suites.append(bgp_tests.get_suite(agent_config))

    if "isis" in protocols:
        suites.append(isis_tests.get_suite(agent_config))

    if "vxlan" in protocols or "evpn" in protocols:
        suites.append(vxlan_tests.get_suite(agent_config))

    if "mpls" in protocols or "ldp" in protocols:
        suites.append(mpls_tests.get_suite(agent_config))

    if "dhcp" in protocols:
        suites.append(dhcp_tests.get_suite(agent_config))

    if "dns" in protocols:
        suites.append(dns_tests.get_suite(agent_config))

    return suites


async def run_test_suite(suite: TestSuite) -> TestSuite:
    """
    Run all tests in a test suite

    Args:
        suite: TestSuite to run

    Returns:
        TestSuite with results populated
    """
    suite.results = []

    for test in suite.tests:
        result = await test.run()
        suite.results.append(result)
        logger.info(f"Test {test.test_id}: {result.status.value}")

    return suite


async def run_all_tests(
    agent_config: Dict[str, Any],
    suite_filter: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Run all applicable tests for an agent

    Args:
        agent_config: Agent TOON configuration dict
        suite_filter: Optional list of suite IDs to run (runs all if None)

    Returns:
        Complete test results with summary
    """
    start_time = datetime.now()
    suites = get_tests_for_agent(agent_config)

    # Filter suites if specified
    if suite_filter:
        suites = [s for s in suites if s.suite_id in suite_filter]

    # Run all suites
    results = []
    for suite in suites:
        completed_suite = await run_test_suite(suite)
        results.append(completed_suite.to_dict())

    # Calculate summary
    total_passed = sum(s.passed for s in suites)
    total_failed = sum(s.failed for s in suites)
    total_tests = sum(len(s.results) for s in suites)

    return {
        "agent_id": agent_config.get("id", "unknown"),
        "timestamp": start_time.isoformat(),
        "duration_ms": (datetime.now() - start_time).total_seconds() * 1000,
        "summary": {
            "total_suites": len(suites),
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "pass_rate": round(total_passed / total_tests * 100, 1) if total_tests > 0 else 0
        },
        "suites": results
    }
