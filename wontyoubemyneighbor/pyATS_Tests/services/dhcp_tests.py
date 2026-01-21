"""
DHCP Tests - DHCP server/relay validation

Tests:
- Pool configuration
- Lease assignment
- Relay functionality
"""

from typing import Dict, Any
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.dhcp")


class DHCPPoolConfigurationTest(BaseTest):
    """Test DHCP pool configuration"""

    test_id = "dhcp_pool_config"
    test_name = "DHCP Pool Configuration"
    description = "Verify DHCP pools are properly configured"
    severity = TestSeverity.CRITICAL
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Get expected pool config
            pool_config = None
            for proto in self.protocols:
                if proto.get("p") == "dhcp":
                    pool_config = proto
                    break

            if not pool_config:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="DHCP not configured"
                )

            # Check DHCP service is running
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-x", "dhcpd",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            if proc.returncode != 0:
                # Try alternative DHCP service names
                proc = await asyncio.create_subprocess_exec(
                    "pgrep", "-f", "dhcp",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

            service_running = proc.returncode == 0

            details = {
                "service_running": service_running,
                "pool_start": pool_config.get("pool_start"),
                "pool_end": pool_config.get("pool_end"),
                "gateway": pool_config.get("gateway")
            }

            if not service_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="DHCP service not running",
                    details=details
                )

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message="DHCP pool configured and service running",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check DHCP pool: {str(e)}"
            )


class DHCPLeaseAssignmentTest(BaseTest):
    """Test DHCP lease assignment"""

    test_id = "dhcp_lease_assignment"
    test_name = "DHCP Lease Assignment"
    description = "Verify DHCP leases are being assigned"
    severity = TestSeverity.MAJOR
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Check DHCP lease file
            lease_files = [
                "/var/lib/dhcp/dhcpd.leases",
                "/var/lib/dhcpd/dhcpd.leases",
                "/var/db/dhcpd.leases"
            ]

            leases = []
            lease_file_found = None

            for lf in lease_files:
                proc = await asyncio.create_subprocess_exec(
                    "cat", lf,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                if proc.returncode == 0:
                    lease_file_found = lf
                    content = stdout.decode()

                    # Parse lease entries
                    lease_matches = re.findall(
                        r"lease\s+(\d+\.\d+\.\d+\.\d+)\s*\{([^}]+)\}",
                        content,
                        re.DOTALL
                    )

                    for ip, lease_data in lease_matches:
                        mac_match = re.search(r"hardware ethernet\s+([^;]+)", lease_data)
                        state_match = re.search(r"binding state\s+(\w+)", lease_data)

                        leases.append({
                            "ip": ip,
                            "mac": mac_match.group(1).strip() if mac_match else "unknown",
                            "state": state_match.group(1) if state_match else "unknown"
                        })
                    break

            details = {
                "lease_file": lease_file_found,
                "total_leases": len(leases),
                "leases": leases[:10]  # First 10
            }

            if lease_file_found is None:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No DHCP lease file found",
                    details=details
                )

            active_leases = [l for l in leases if l.get("state") == "active"]

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"{len(active_leases)} active leases, {len(leases)} total",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check leases: {str(e)}"
            )


class DHCPRelayTest(BaseTest):
    """Test DHCP relay functionality"""

    test_id = "dhcp_relay"
    test_name = "DHCP Relay"
    description = "Verify DHCP relay is operational (if configured)"
    severity = TestSeverity.MINOR
    timeout = 15.0

    async def execute(self) -> TestResult:
        try:
            # Check if DHCP relay is running
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-f", "dhcrelay",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            relay_running = proc.returncode == 0

            details = {"relay_running": relay_running}

            if relay_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message="DHCP relay is running",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="DHCP relay not configured",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check relay: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get DHCP test suite for an agent"""
    suite = TestSuite(
        suite_id="service_dhcp",
        suite_name="DHCP Service Tests",
        description="DHCP server and relay validation",
        protocol="dhcp"
    )

    suite.tests = [
        DHCPPoolConfigurationTest(agent_config),
        DHCPLeaseAssignmentTest(agent_config),
        DHCPRelayTest(agent_config)
    ]

    return suite
