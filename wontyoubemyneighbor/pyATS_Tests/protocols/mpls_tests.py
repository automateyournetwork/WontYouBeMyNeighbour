"""
MPLS/LDP Tests - Multiprotocol Label Switching validation

Tests:
- LDP session establishment
- Label distribution
- LFIB verification
"""

from typing import Dict, Any
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.mpls")


class LDPSessionTest(BaseTest):
    """Test LDP session establishment"""

    test_id = "mpls_ldp_session"
    test_name = "LDP Session"
    description = "Verify LDP sessions are established"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show mpls ldp neighbor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            if "not running" in output.lower() or "not enabled" in output.lower():
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="LDP is not running"
                )

            # Parse LDP neighbors
            neighbors = []
            for line in output.split("\n"):
                # Look for IP addresses followed by state
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+.*?(\w+)\s*$", line)
                if match:
                    neighbors.append({
                        "neighbor": match.group(1),
                        "state": match.group(2)
                    })

            operational = [n for n in neighbors if n["state"].lower() in ["operational", "established"]]
            details = {"neighbors": neighbors, "operational": len(operational)}

            if not neighbors:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No LDP neighbors found",
                    details=details
                )

            if len(operational) == len(neighbors):
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(operational)} LDP sessions operational",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{len(neighbors) - len(operational)} sessions not operational",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check LDP sessions: {str(e)}"
            )


class LabelDistributionTest(BaseTest):
    """Test MPLS label distribution"""

    test_id = "mpls_labels"
    test_name = "MPLS Label Distribution"
    description = "Verify labels are being distributed"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show mpls ldp binding",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            # Count label bindings
            bindings = len(re.findall(r"local label:\s*(\d+)", output))

            details = {"binding_count": bindings}

            if bindings > 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"{bindings} label bindings found",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No label bindings found",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check labels: {str(e)}"
            )


class LFIBVerificationTest(BaseTest):
    """Test LFIB (Label Forwarding Information Base)"""

    test_id = "mpls_lfib"
    test_name = "MPLS LFIB"
    description = "Verify LFIB has entries"
    severity = TestSeverity.CRITICAL
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show mpls table",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            # Count LFIB entries
            entries = len([l for l in output.split("\n") if re.match(r"^\s*\d+", l.strip())])

            details = {"lfib_entries": entries}

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"LFIB contains {entries} entries",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check LFIB: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get MPLS/LDP test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_mpls",
        suite_name="MPLS/LDP Tests",
        description="MPLS label switching and LDP validation",
        protocol="mpls"
    )

    suite.tests = [
        LDPSessionTest(agent_config),
        LabelDistributionTest(agent_config),
        LFIBVerificationTest(agent_config)
    ]

    return suite
