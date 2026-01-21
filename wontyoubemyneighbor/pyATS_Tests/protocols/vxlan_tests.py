"""
VXLAN/EVPN Tests - Virtual Extensible LAN and Ethernet VPN validation

Tests:
- VTEP reachability
- VNI configuration
- MAC/IP learning
"""

from typing import Dict, Any
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.vxlan")


class VTEPReachabilityTest(BaseTest):
    """Test VTEP reachability"""

    test_id = "vxlan_vtep_reachability"
    test_name = "VTEP Reachability"
    description = "Verify remote VTEPs are reachable"
    severity = TestSeverity.CRITICAL
    timeout = 45.0

    async def execute(self) -> TestResult:
        try:
            # Get VTEP info from configuration
            remote_vteps = []
            for proto in self.protocols:
                if proto.get("p") in ["vxlan", "evpn"]:
                    vteps = proto.get("remote_vteps", [])
                    remote_vteps.extend(vteps)

            if not remote_vteps:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No remote VTEPs configured"
                )

            results = []
            failed = 0
            for vtep_ip in remote_vteps:
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "2", "-W", "3", vtep_ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                if proc.returncode == 0:
                    results.append({"vtep": vtep_ip, "status": "reachable"})
                else:
                    results.append({"vtep": vtep_ip, "status": "unreachable"})
                    failed += 1

            details = {"vteps": results}

            if failed == 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(remote_vteps)} VTEPs reachable",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{failed} VTEPs unreachable",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check VTEPs: {str(e)}"
            )


class VNIConfigurationTest(BaseTest):
    """Test VNI configuration"""

    test_id = "vxlan_vni_config"
    test_name = "VNI Configuration"
    description = "Verify VNI is properly configured"
    severity = TestSeverity.MAJOR
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Get expected VNIs
            expected_vnis = []
            for proto in self.protocols:
                if proto.get("p") in ["vxlan", "evpn"]:
                    vnis = proto.get("vnis", [])
                    expected_vnis.extend(vnis)

            if not expected_vnis:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No VNIs configured"
                )

            # Check VXLAN interfaces
            proc = await asyncio.create_subprocess_exec(
                "ip", "-d", "link", "show", "type", "vxlan",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            configured_vnis = re.findall(r"vxlan\s+id\s+(\d+)", output)
            configured_vnis = [int(v) for v in configured_vnis]

            missing_vnis = [v for v in expected_vnis if v not in configured_vnis]

            details = {
                "expected_vnis": expected_vnis,
                "configured_vnis": configured_vnis,
                "missing_vnis": missing_vnis
            }

            if missing_vnis:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Missing VNIs: {missing_vnis}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(expected_vnis)} VNIs configured",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check VNIs: {str(e)}"
            )


class EVPNMACLearningTest(BaseTest):
    """Test EVPN MAC/IP learning"""

    test_id = "evpn_mac_learning"
    test_name = "EVPN MAC/IP Learning"
    description = "Verify MAC addresses are learned via EVPN"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show evpn mac vni all",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            # Count learned MACs
            mac_count = len(re.findall(r"[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}", output, re.I))

            details = {"mac_count": mac_count}

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"{mac_count} MAC addresses learned",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check MAC learning: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get VXLAN/EVPN test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_vxlan",
        suite_name="VXLAN/EVPN Tests",
        description="VXLAN tunnel and EVPN validation",
        protocol="vxlan"
    )

    suite.tests = [
        VTEPReachabilityTest(agent_config),
        VNIConfigurationTest(agent_config),
        EVPNMACLearningTest(agent_config)
    ]

    return suite
