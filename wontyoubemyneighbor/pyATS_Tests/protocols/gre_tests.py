"""
GRE Tests - Generic Routing Encapsulation tunnel validation

Tests:
- Tunnel interface state
- Tunnel endpoint reachability
- Encapsulation verification
- Keepalive validation
- MTU consistency
"""

from typing import Dict, Any, List, Optional
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.gre")


class GRETunnelStateTest(BaseTest):
    """Test GRE tunnel interface state"""

    test_id = "gre_tunnel_state"
    test_name = "GRE Tunnel State"
    description = "Verify GRE tunnel interfaces are UP"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get GRE tunnel interfaces from agent config
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured on this agent"
                )

            # Check tunnel states via ip tunnel show
            proc = await asyncio.create_subprocess_exec(
                "ip", "tunnel", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            tunnel_output = stdout.decode()

            # Check interface states via ip link show
            proc2 = await asyncio.create_subprocess_exec(
                "ip", "-br", "link", "show", "type", "gre",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout2, stderr2 = await proc2.communicate()
            link_output = stdout2.decode()

            tunnels = []
            down_tunnels = []

            for iface in gre_interfaces:
                iface_name = iface.get("n", iface.get("id"))
                tun_config = iface.get("tun", {})

                tunnel_info = {
                    "name": iface_name,
                    "local": tun_config.get("src", ""),
                    "remote": tun_config.get("dst", ""),
                    "key": tun_config.get("key"),
                    "expected_ip": iface.get("a", []),
                    "state": "unknown"
                }

                # Check if interface is UP in link output
                for line in link_output.split("\n"):
                    if iface_name in line:
                        if "UP" in line:
                            tunnel_info["state"] = "up"
                        elif "DOWN" in line:
                            tunnel_info["state"] = "down"
                            down_tunnels.append(iface_name)

                # Check tunnel exists
                if iface_name in tunnel_output:
                    tunnel_info["exists"] = True
                else:
                    tunnel_info["exists"] = False
                    if tunnel_info["state"] == "unknown":
                        tunnel_info["state"] = "not_found"
                        down_tunnels.append(iface_name)

                tunnels.append(tunnel_info)

            details = {
                "total_tunnels": len(gre_interfaces),
                "tunnels": tunnels,
                "tunnel_output": tunnel_output[:500]
            }

            if down_tunnels:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"GRE tunnels down: {', '.join(down_tunnels)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(tunnels)} GRE tunnels are UP",
                    details=details
                )

        except FileNotFoundError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message="ip command not found - iproute2 may not be installed"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check GRE tunnels: {str(e)}"
            )


class GRETunnelEndpointTest(BaseTest):
    """Test GRE tunnel endpoint reachability"""

    test_id = "gre_endpoint_reachability"
    test_name = "GRE Endpoint Reachability"
    description = "Verify GRE tunnel remote endpoints are reachable"
    severity = TestSeverity.CRITICAL
    timeout = 60.0

    async def execute(self) -> TestResult:
        try:
            # Get GRE tunnel configurations
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured"
                )

            # Test reachability to each remote endpoint (underlay)
            reachability_results = []
            unreachable = []

            for iface in gre_interfaces:
                tun_config = iface.get("tun", {})
                remote_ip = tun_config.get("dst", "")

                if not remote_ip:
                    continue

                # Ping the underlay remote IP
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "3", "-W", "2", remote_ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                result = {
                    "tunnel": iface.get("n", iface.get("id")),
                    "remote_underlay": remote_ip,
                    "reachable": proc.returncode == 0
                }

                # Extract packet loss if available
                output = stdout.decode()
                loss_match = re.search(r"(\d+)% packet loss", output)
                if loss_match:
                    result["packet_loss"] = int(loss_match.group(1))

                reachability_results.append(result)

                if proc.returncode != 0:
                    unreachable.append(f"{result['tunnel']} ({remote_ip})")

            details = {
                "endpoints": reachability_results
            }

            if unreachable:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Unreachable endpoints: {', '.join(unreachable)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(reachability_results)} GRE endpoints reachable",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check endpoint reachability: {str(e)}"
            )


class GRETunnelOverlayTest(BaseTest):
    """Test GRE tunnel overlay connectivity"""

    test_id = "gre_overlay_connectivity"
    test_name = "GRE Overlay Connectivity"
    description = "Verify connectivity through GRE tunnel (overlay)"
    severity = TestSeverity.CRITICAL
    timeout = 60.0

    async def execute(self) -> TestResult:
        try:
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured"
                )

            # Test connectivity through tunnel (ping tunnel IPs)
            overlay_results = []
            failed = []

            for iface in gre_interfaces:
                iface_name = iface.get("n", iface.get("id"))
                addresses = iface.get("a", [])

                if not addresses:
                    continue

                # Get the tunnel IP and calculate peer IP
                tunnel_ip = addresses[0].split("/")[0]
                tun_config = iface.get("tun", {})

                # Try to determine peer tunnel IP (assuming /30 or /31)
                ip_parts = tunnel_ip.split(".")
                last_octet = int(ip_parts[3])

                # For /30 networks, peer is +1 or -1
                if last_octet % 2 == 1:
                    peer_ip = ".".join(ip_parts[:3]) + "." + str(last_octet + 1)
                else:
                    peer_ip = ".".join(ip_parts[:3]) + "." + str(last_octet - 1)

                # Ping through tunnel
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "3", "-W", "2", peer_ip,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                result = {
                    "tunnel": iface_name,
                    "local_ip": tunnel_ip,
                    "peer_ip": peer_ip,
                    "reachable": proc.returncode == 0
                }

                output = stdout.decode()
                loss_match = re.search(r"(\d+)% packet loss", output)
                if loss_match:
                    result["packet_loss"] = int(loss_match.group(1))

                rtt_match = re.search(r"rtt.*= ([\d.]+)/([\d.]+)/([\d.]+)", output)
                if rtt_match:
                    result["rtt_avg_ms"] = float(rtt_match.group(2))

                overlay_results.append(result)

                if proc.returncode != 0:
                    failed.append(f"{iface_name} ({peer_ip})")

            details = {
                "overlay_tests": overlay_results
            }

            if failed:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Overlay connectivity failed: {', '.join(failed)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Overlay connectivity OK for {len(overlay_results)} tunnels",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check overlay connectivity: {str(e)}"
            )


class GRETunnelMTUTest(BaseTest):
    """Test GRE tunnel MTU configuration"""

    test_id = "gre_mtu_validation"
    test_name = "GRE MTU Validation"
    description = "Verify GRE tunnel MTU is correctly configured"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured"
                )

            mtu_results = []
            mtu_issues = []

            for iface in gre_interfaces:
                iface_name = iface.get("n", iface.get("id"))
                expected_mtu = iface.get("mtu", 1400)

                # Get actual MTU from system
                proc = await asyncio.create_subprocess_exec(
                    "ip", "link", "show", iface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                output = stdout.decode()

                actual_mtu = None
                mtu_match = re.search(r"mtu\s+(\d+)", output)
                if mtu_match:
                    actual_mtu = int(mtu_match.group(1))

                result = {
                    "tunnel": iface_name,
                    "expected_mtu": expected_mtu,
                    "actual_mtu": actual_mtu,
                    "match": actual_mtu == expected_mtu if actual_mtu else False
                }
                mtu_results.append(result)

                # GRE overhead is typically 24-28 bytes
                # MTU should be <= underlay MTU - GRE overhead
                if actual_mtu and actual_mtu > 1476:
                    mtu_issues.append(f"{iface_name}: MTU {actual_mtu} may cause fragmentation")
                elif actual_mtu and actual_mtu != expected_mtu:
                    mtu_issues.append(f"{iface_name}: MTU mismatch (expected {expected_mtu}, actual {actual_mtu})")

            details = {
                "mtu_checks": mtu_results
            }

            if mtu_issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="; ".join(mtu_issues),
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"MTU configured correctly for {len(mtu_results)} tunnels",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check MTU: {str(e)}"
            )


class GRETunnelKeyTest(BaseTest):
    """Test GRE tunnel key configuration"""

    test_id = "gre_key_validation"
    test_name = "GRE Key Validation"
    description = "Verify GRE tunnel key configuration matches"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured"
                )

            # Get tunnel details
            proc = await asyncio.create_subprocess_exec(
                "ip", "tunnel", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            tunnel_output = stdout.decode()

            key_results = []
            key_issues = []

            for iface in gre_interfaces:
                iface_name = iface.get("n", iface.get("id"))
                tun_config = iface.get("tun", {})
                expected_key = tun_config.get("key")

                result = {
                    "tunnel": iface_name,
                    "expected_key": expected_key,
                    "actual_key": None,
                    "match": False
                }

                # Parse key from ip tunnel show output
                for line in tunnel_output.split("\n"):
                    if iface_name in line:
                        key_match = re.search(r"key\s+(\d+)", line)
                        if key_match:
                            result["actual_key"] = int(key_match.group(1))
                            result["match"] = (result["actual_key"] == expected_key)
                        elif expected_key is None:
                            result["match"] = True  # No key expected, none found
                        break

                key_results.append(result)

                if expected_key is not None and not result["match"]:
                    key_issues.append(
                        f"{iface_name}: key mismatch (expected {expected_key}, "
                        f"actual {result['actual_key']})"
                    )

            details = {
                "key_checks": key_results
            }

            if key_issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="; ".join(key_issues),
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"GRE keys validated for {len(key_results)} tunnels",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check GRE keys: {str(e)}"
            )


class GRETunnelStatisticsTest(BaseTest):
    """Test GRE tunnel statistics"""

    test_id = "gre_statistics"
    test_name = "GRE Tunnel Statistics"
    description = "Check GRE tunnel packet statistics for errors"
    severity = TestSeverity.MINOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            gre_interfaces = []
            for iface in self.interfaces:
                if iface.get("t") == "gre":
                    gre_interfaces.append(iface)

            if not gre_interfaces:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No GRE interfaces configured"
                )

            stats_results = []
            error_tunnels = []

            for iface in gre_interfaces:
                iface_name = iface.get("n", iface.get("id"))

                # Get interface statistics
                proc = await asyncio.create_subprocess_exec(
                    "ip", "-s", "link", "show", iface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                output = stdout.decode()

                result = {
                    "tunnel": iface_name,
                    "rx_packets": 0,
                    "tx_packets": 0,
                    "rx_errors": 0,
                    "tx_errors": 0,
                    "rx_dropped": 0,
                    "tx_dropped": 0
                }

                # Parse statistics
                lines = output.split("\n")
                for i, line in enumerate(lines):
                    if "RX:" in line and i + 1 < len(lines):
                        rx_line = lines[i + 1].split()
                        if len(rx_line) >= 4:
                            result["rx_packets"] = int(rx_line[1]) if rx_line[1].isdigit() else 0
                            result["rx_errors"] = int(rx_line[2]) if rx_line[2].isdigit() else 0
                            result["rx_dropped"] = int(rx_line[3]) if rx_line[3].isdigit() else 0
                    elif "TX:" in line and i + 1 < len(lines):
                        tx_line = lines[i + 1].split()
                        if len(tx_line) >= 4:
                            result["tx_packets"] = int(tx_line[1]) if tx_line[1].isdigit() else 0
                            result["tx_errors"] = int(tx_line[2]) if tx_line[2].isdigit() else 0
                            result["tx_dropped"] = int(tx_line[3]) if tx_line[3].isdigit() else 0

                stats_results.append(result)

                # Flag high error rates
                total_packets = result["rx_packets"] + result["tx_packets"]
                total_errors = result["rx_errors"] + result["tx_errors"]

                if total_packets > 0:
                    error_rate = (total_errors / total_packets) * 100
                    if error_rate > 1.0:  # More than 1% errors
                        error_tunnels.append(f"{iface_name}: {error_rate:.1f}% errors")

            details = {
                "statistics": stats_results
            }

            if error_tunnels:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"High error rates: {', '.join(error_tunnels)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Statistics OK for {len(stats_results)} tunnels",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to get statistics: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get GRE test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_gre",
        suite_name="GRE Tunnel Tests",
        description="GRE tunnel state, connectivity, and configuration validation",
        protocol="gre"
    )

    suite.tests = [
        GRETunnelStateTest(agent_config),
        GRETunnelEndpointTest(agent_config),
        GRETunnelOverlayTest(agent_config),
        GRETunnelMTUTest(agent_config),
        GRETunnelKeyTest(agent_config),
        GRETunnelStatisticsTest(agent_config)
    ]

    return suite
