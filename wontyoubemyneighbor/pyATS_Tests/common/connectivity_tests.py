"""
Connectivity Tests - IP reachability and network connectivity validation

Tests:
- Loopback reachability
- Interface IP connectivity
- Gateway reachability
- Peer connectivity (based on protocol config)
"""

from typing import Dict, Any, List
import asyncio
import subprocess
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.connectivity")


class LoopbackReachabilityTest(BaseTest):
    """Test that the loopback interface is reachable"""

    test_id = "connectivity_loopback"
    test_name = "Loopback Reachability"
    description = "Verify loopback IP is configured and responding"
    severity = TestSeverity.CRITICAL
    timeout = 10.0

    async def execute(self) -> TestResult:
        # Find loopback interface
        loopback_ip = None
        for iface in self.interfaces:
            if iface.get("t") == "lo":
                addresses = iface.get("a", [])
                if addresses:
                    # Extract IP without prefix
                    loopback_ip = addresses[0].split("/")[0]
                    break

        if not loopback_ip:
            # Use router ID as fallback
            loopback_ip = self.router_id

        try:
            # Ping loopback
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "2", loopback_ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Loopback {loopback_ip} is reachable",
                    details={"loopback_ip": loopback_ip, "ping_output": stdout.decode()[:200]}
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Loopback {loopback_ip} is not reachable",
                    details={"loopback_ip": loopback_ip, "error": stderr.decode()}
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Ping test failed: {str(e)}"
            )


class InterfaceIPConnectivityTest(BaseTest):
    """Test that interface IPs are reachable from the agent"""

    test_id = "connectivity_interface_ips"
    test_name = "Interface IP Connectivity"
    description = "Verify all configured interface IPs are reachable"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        results = []
        failed = 0

        for iface in self.interfaces:
            iface_name = iface.get("n", "unknown")
            iface_state = iface.get("s", "unknown")
            addresses = iface.get("a", [])

            # Skip down interfaces
            if iface_state != "up":
                results.append({
                    "interface": iface_name,
                    "status": "skipped",
                    "reason": f"Interface is {iface_state}"
                })
                continue

            for addr in addresses:
                ip = addr.split("/")[0]

                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ping", "-c", "1", "-W", "2", ip,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()

                    if proc.returncode == 0:
                        results.append({
                            "interface": iface_name,
                            "ip": ip,
                            "status": "reachable"
                        })
                    else:
                        results.append({
                            "interface": iface_name,
                            "ip": ip,
                            "status": "unreachable"
                        })
                        failed += 1

                except Exception as e:
                    results.append({
                        "interface": iface_name,
                        "ip": ip,
                        "status": "error",
                        "error": str(e)
                    })
                    failed += 1

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All {len(results)} interface IPs are reachable",
                details={"interfaces": results}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} interface IPs are not reachable",
                details={"interfaces": results, "failed_count": failed}
            )


class PeerConnectivityTest(BaseTest):
    """Test connectivity to configured protocol peers"""

    test_id = "connectivity_peers"
    test_name = "Peer Connectivity"
    description = "Verify connectivity to all configured protocol peers"
    severity = TestSeverity.CRITICAL
    timeout = 60.0

    async def execute(self) -> TestResult:
        peers_tested = []
        failed = 0

        for proto in self.protocols:
            proto_type = proto.get("p", "unknown")
            peers = proto.get("peers", [])

            for peer in peers:
                peer_ip = peer.get("ip")
                if not peer_ip:
                    continue

                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ping", "-c", "2", "-W", "3", peer_ip,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await proc.communicate()

                    if proc.returncode == 0:
                        peers_tested.append({
                            "protocol": proto_type,
                            "peer_ip": peer_ip,
                            "peer_asn": peer.get("asn"),
                            "status": "reachable"
                        })
                    else:
                        peers_tested.append({
                            "protocol": proto_type,
                            "peer_ip": peer_ip,
                            "peer_asn": peer.get("asn"),
                            "status": "unreachable"
                        })
                        failed += 1

                except Exception as e:
                    peers_tested.append({
                        "protocol": proto_type,
                        "peer_ip": peer_ip,
                        "status": "error",
                        "error": str(e)
                    })
                    failed += 1

        if not peers_tested:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="No peers configured to test"
            )

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All {len(peers_tested)} peers are reachable",
                details={"peers": peers_tested}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} of {len(peers_tested)} peers are unreachable",
                details={"peers": peers_tested, "failed_count": failed}
            )


class DefaultRouteTest(BaseTest):
    """Test that a default route exists"""

    test_id = "connectivity_default_route"
    test_name = "Default Route Check"
    description = "Verify a default route exists in the routing table"
    severity = TestSeverity.MINOR
    timeout = 10.0

    async def execute(self) -> TestResult:
        try:
            # Check for default route using ip route
            proc = await asyncio.create_subprocess_exec(
                "ip", "route", "show", "default",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode().strip()
            if output and "default via" in output:
                # Extract gateway
                parts = output.split()
                gateway = parts[2] if len(parts) > 2 else "unknown"

                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Default route via {gateway}",
                    details={"route": output, "gateway": gateway}
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No default route configured",
                    details={"routing_table": output}
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check routing table: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get connectivity test suite for an agent"""
    suite = TestSuite(
        suite_id="common_connectivity",
        suite_name="Connectivity Tests",
        description="IP reachability and network connectivity validation",
        protocol=None  # Common to all agents
    )

    suite.tests = [
        LoopbackReachabilityTest(agent_config),
        InterfaceIPConnectivityTest(agent_config),
        PeerConnectivityTest(agent_config),
        DefaultRouteTest(agent_config)
    ]

    return suite
