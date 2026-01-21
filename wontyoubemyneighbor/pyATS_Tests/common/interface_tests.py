"""
Interface Tests - Network interface status and configuration validation

Tests:
- Interface status (up/down)
- IP address configuration
- MTU settings
- Interface counters (errors, drops)
"""

from typing import Dict, Any, List
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.interface")


class InterfaceStatusTest(BaseTest):
    """Test that expected interfaces are up"""

    test_id = "interface_status"
    test_name = "Interface Status"
    description = "Verify all configured interfaces are in expected state"
    severity = TestSeverity.CRITICAL
    timeout = 15.0

    async def execute(self) -> TestResult:
        results = []
        failed = 0

        try:
            # Get actual interface states from system
            proc = await asyncio.create_subprocess_exec(
                "ip", "-o", "link", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse actual interface states
            actual_states = {}
            for line in stdout.decode().split("\n"):
                if not line.strip():
                    continue
                # Format: 1: lo: <LOOPBACK,UP,LOWER_UP> ...
                match = re.match(r"\d+:\s+(\S+):\s+<([^>]+)>", line)
                if match:
                    iface_name = match.group(1).rstrip(":")
                    flags = match.group(2).split(",")
                    actual_states[iface_name] = "up" if "UP" in flags else "down"

            # Check each configured interface
            for iface in self.interfaces:
                iface_name = iface.get("n", "unknown")
                expected_state = iface.get("s", "up")

                # Normalize interface name (remove @xxx suffix)
                base_name = iface_name.split("@")[0]

                if base_name in actual_states:
                    actual_state = actual_states[base_name]
                    if actual_state == expected_state:
                        results.append({
                            "interface": iface_name,
                            "expected": expected_state,
                            "actual": actual_state,
                            "status": "match"
                        })
                    else:
                        results.append({
                            "interface": iface_name,
                            "expected": expected_state,
                            "actual": actual_state,
                            "status": "mismatch"
                        })
                        failed += 1
                else:
                    results.append({
                        "interface": iface_name,
                        "expected": expected_state,
                        "actual": "not_found",
                        "status": "missing"
                    })
                    failed += 1

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check interface status: {str(e)}"
            )

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All {len(results)} interfaces in expected state",
                details={"interfaces": results}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} interfaces not in expected state",
                details={"interfaces": results, "failed_count": failed}
            )


class InterfaceIPConfigurationTest(BaseTest):
    """Test that interfaces have correct IP addresses"""

    test_id = "interface_ip_config"
    test_name = "Interface IP Configuration"
    description = "Verify IP addresses are correctly configured on interfaces"
    severity = TestSeverity.CRITICAL
    timeout = 15.0

    async def execute(self) -> TestResult:
        results = []
        failed = 0

        try:
            # Get actual IP addresses
            proc = await asyncio.create_subprocess_exec(
                "ip", "-o", "addr", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse actual IPs
            actual_ips = {}
            for line in stdout.decode().split("\n"):
                if not line.strip():
                    continue
                # Format: 1: lo    inet 127.0.0.1/8 ...
                match = re.match(r"\d+:\s+(\S+)\s+inet\s+(\S+)", line)
                if match:
                    iface_name = match.group(1)
                    ip_addr = match.group(2)
                    if iface_name not in actual_ips:
                        actual_ips[iface_name] = []
                    actual_ips[iface_name].append(ip_addr)

            # Check each configured interface
            for iface in self.interfaces:
                iface_name = iface.get("n", "unknown")
                expected_ips = iface.get("a", [])

                # Skip interfaces without IPs
                if not expected_ips:
                    results.append({
                        "interface": iface_name,
                        "status": "skipped",
                        "reason": "No IP configured"
                    })
                    continue

                base_name = iface_name.split("@")[0]
                actual = actual_ips.get(base_name, [])

                for expected_ip in expected_ips:
                    if expected_ip in actual:
                        results.append({
                            "interface": iface_name,
                            "expected_ip": expected_ip,
                            "status": "configured"
                        })
                    else:
                        results.append({
                            "interface": iface_name,
                            "expected_ip": expected_ip,
                            "actual_ips": actual,
                            "status": "missing"
                        })
                        failed += 1

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check IP configuration: {str(e)}"
            )

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All IP addresses correctly configured",
                details={"interfaces": results}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} IP addresses missing or misconfigured",
                details={"interfaces": results, "failed_count": failed}
            )


class InterfaceMTUTest(BaseTest):
    """Test interface MTU settings"""

    test_id = "interface_mtu"
    test_name = "Interface MTU"
    description = "Verify MTU settings on interfaces"
    severity = TestSeverity.MINOR
    timeout = 15.0

    async def execute(self) -> TestResult:
        results = []
        failed = 0

        try:
            # Get actual MTU values
            proc = await asyncio.create_subprocess_exec(
                "ip", "-o", "link", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse actual MTUs
            actual_mtus = {}
            for line in stdout.decode().split("\n"):
                if not line.strip():
                    continue
                # Extract interface name and MTU
                match = re.match(r"\d+:\s+(\S+):", line)
                mtu_match = re.search(r"mtu\s+(\d+)", line)
                if match and mtu_match:
                    iface_name = match.group(1).rstrip(":")
                    actual_mtus[iface_name] = int(mtu_match.group(1))

            # Check configured MTUs
            for iface in self.interfaces:
                iface_name = iface.get("n", "unknown")
                expected_mtu = iface.get("mtu", 1500)

                base_name = iface_name.split("@")[0]
                actual_mtu = actual_mtus.get(base_name)

                if actual_mtu is None:
                    results.append({
                        "interface": iface_name,
                        "expected_mtu": expected_mtu,
                        "status": "not_found"
                    })
                    continue

                if actual_mtu == expected_mtu:
                    results.append({
                        "interface": iface_name,
                        "expected_mtu": expected_mtu,
                        "actual_mtu": actual_mtu,
                        "status": "match"
                    })
                else:
                    results.append({
                        "interface": iface_name,
                        "expected_mtu": expected_mtu,
                        "actual_mtu": actual_mtu,
                        "status": "mismatch"
                    })
                    failed += 1

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check MTU: {str(e)}"
            )

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All MTU values match expected",
                details={"interfaces": results}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} interfaces have MTU mismatch",
                details={"interfaces": results, "failed_count": failed}
            )


class InterfaceErrorCountersTest(BaseTest):
    """Test interface error counters"""

    test_id = "interface_errors"
    test_name = "Interface Error Counters"
    description = "Check for interface errors and drops"
    severity = TestSeverity.MINOR
    timeout = 15.0

    async def execute(self) -> TestResult:
        results = []
        interfaces_with_errors = 0

        try:
            # Get interface statistics
            proc = await asyncio.create_subprocess_exec(
                "ip", "-s", "link", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse statistics (simplified)
            current_iface = None
            lines = stdout.decode().split("\n")

            for i, line in enumerate(lines):
                # Interface line
                if re.match(r"^\d+:", line):
                    match = re.match(r"^\d+:\s+(\S+):", line)
                    if match:
                        current_iface = match.group(1)

                # RX stats line
                elif current_iface and "RX:" in line.upper():
                    if i + 1 < len(lines):
                        stats_line = lines[i + 1].strip().split()
                        if len(stats_line) >= 6:
                            rx_errors = int(stats_line[2])
                            rx_dropped = int(stats_line[3])

                            # Check RX errors
                            if rx_errors > 0 or rx_dropped > 0:
                                results.append({
                                    "interface": current_iface,
                                    "rx_errors": rx_errors,
                                    "rx_dropped": rx_dropped,
                                    "status": "errors_present"
                                })
                                interfaces_with_errors += 1
                            else:
                                results.append({
                                    "interface": current_iface,
                                    "rx_errors": 0,
                                    "rx_dropped": 0,
                                    "status": "clean"
                                })

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check interface counters: {str(e)}"
            )

        if interfaces_with_errors == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message="No interface errors detected",
                details={"interfaces": results}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{interfaces_with_errors} interfaces have errors/drops",
                details={"interfaces": results}
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get interface test suite for an agent"""
    suite = TestSuite(
        suite_id="common_interface",
        suite_name="Interface Tests",
        description="Network interface status and configuration validation",
        protocol=None  # Common to all agents
    )

    suite.tests = [
        InterfaceStatusTest(agent_config),
        InterfaceIPConfigurationTest(agent_config),
        InterfaceMTUTest(agent_config),
        InterfaceErrorCountersTest(agent_config)
    ]

    return suite
