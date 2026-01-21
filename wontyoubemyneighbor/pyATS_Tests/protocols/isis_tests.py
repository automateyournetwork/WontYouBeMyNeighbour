"""
IS-IS Tests - Intermediate System to Intermediate System protocol validation

Tests:
- Adjacency establishment
- LSP propagation
- Route calculation
"""

from typing import Dict, Any
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.isis")


class ISISAdjacencyTest(BaseTest):
    """Test IS-IS adjacency establishment"""

    test_id = "isis_adjacency"
    test_name = "IS-IS Adjacency"
    description = "Verify IS-IS adjacencies reach Up state"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show isis neighbor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode()

            if "IS-IS" not in output and "not running" in output.lower():
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="IS-IS is not running"
                )

            # Parse neighbors
            neighbors = []
            for line in output.split("\n"):
                if "Up" in line or "Init" in line or "Down" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        neighbors.append({
                            "system_id": parts[0],
                            "state": "Up" if "Up" in line else "Down",
                            "interface": parts[-1] if len(parts) > 3 else "unknown"
                        })

            up_neighbors = [n for n in neighbors if n["state"] == "Up"]
            details = {"neighbors": neighbors, "up_count": len(up_neighbors)}

            if not neighbors:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No IS-IS neighbors found",
                    details=details
                )

            if len(up_neighbors) == len(neighbors):
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(up_neighbors)} IS-IS adjacencies Up",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{len(neighbors) - len(up_neighbors)} adjacencies not Up",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check adjacencies: {str(e)}"
            )


class ISISLSPPropagationTest(BaseTest):
    """Test IS-IS LSP propagation"""

    test_id = "isis_lsp"
    test_name = "IS-IS LSP Database"
    description = "Verify LSP database has entries"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show isis database",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode()

            # Count LSPs
            lsp_count = len(re.findall(r"[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}", output, re.I))

            details = {"lsp_count": lsp_count}

            if lsp_count > 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"IS-IS database contains {lsp_count} LSPs",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No LSPs in IS-IS database",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check LSP database: {str(e)}"
            )


class ISISRouteCalculationTest(BaseTest):
    """Test IS-IS route calculation"""

    test_id = "isis_routes"
    test_name = "IS-IS Routes"
    description = "Verify IS-IS routes are installed"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip route isis",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode()

            isis_routes = len([l for l in output.split("\n") if l.strip().startswith("i")])

            details = {"route_count": isis_routes}

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"{isis_routes} IS-IS routes installed",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check routes: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get IS-IS test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_isis",
        suite_name="IS-IS Protocol Tests",
        description="IS-IS adjacency and route validation",
        protocol="isis"
    )

    suite.tests = [
        ISISAdjacencyTest(agent_config),
        ISISLSPPropagationTest(agent_config),
        ISISRouteCalculationTest(agent_config)
    ]

    return suite
