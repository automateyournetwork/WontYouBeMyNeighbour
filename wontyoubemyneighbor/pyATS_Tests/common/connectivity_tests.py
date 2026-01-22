"""
Connectivity Tests - IP reachability and network connectivity validation

Tests:
- Loopback reachability
- Interface IP connectivity
- Gateway reachability
- Peer connectivity (based on protocol config)
"""

from typing import Dict, Any, List, Optional
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
    """Test connectivity to configured protocol peers and discovered neighbors"""

    test_id = "connectivity_peers"
    test_name = "Peer Connectivity"
    description = "Verify connectivity to all configured peers, OSPF neighbors, and BGP peers"
    severity = TestSeverity.CRITICAL
    timeout = 60.0

    def _extract_all_peer_ips(self) -> List[Dict[str, Any]]:
        """
        Dynamically extract all peer IPs from:
        1. Protocol peer configurations
        2. Runtime state (OSPF neighbors, BGP peers)
        3. Interface neighbor hints from topology
        """
        peers_to_test = []
        seen_ips = set()

        # 1. Get peers from protocol configuration
        for proto in self.protocols:
            proto_type = proto.get("p", "unknown")
            peers = proto.get("peers", [])

            for peer in peers:
                peer_ip = peer.get("ip")
                if peer_ip and peer_ip not in seen_ips:
                    seen_ips.add(peer_ip)
                    peers_to_test.append({
                        "ip": peer_ip,
                        "protocol": proto_type,
                        "asn": peer.get("asn"),
                        "source": "config"
                    })

        # 2. Get from runtime state if available (OSPF neighbors)
        runtime_state = self.agent_config.get("state", {})

        # Check OSPF neighbors from runtime state
        ospf_neighbors = runtime_state.get("nbrs", [])
        for nbr in ospf_neighbors:
            nbr_ip = nbr.get("ip") or nbr.get("address")
            if nbr_ip and nbr_ip not in seen_ips:
                seen_ips.add(nbr_ip)
                peers_to_test.append({
                    "ip": nbr_ip,
                    "protocol": "ospf",
                    "router_id": nbr.get("router_id") or nbr.get("r"),
                    "source": "runtime_ospf"
                })

        # Check BGP peers from runtime state
        bgp_peers = runtime_state.get("peers", [])
        for peer in bgp_peers:
            peer_ip = peer.get("ip") or peer.get("address")
            if peer_ip and peer_ip not in seen_ips:
                seen_ips.add(peer_ip)
                peers_to_test.append({
                    "ip": peer_ip,
                    "protocol": "bgp",
                    "asn": peer.get("asn") or peer.get("remote_as"),
                    "source": "runtime_bgp"
                })

        # 3. Extract peer IPs from interface configurations (underlay connectivity)
        # Look for point-to-point links where we can derive the neighbor IP
        for iface in self.interfaces:
            addresses = iface.get("a", [])
            iface_type = iface.get("t", "eth")

            # For point-to-point interfaces, derive neighbor from subnet
            for addr in addresses:
                if "/" in addr:
                    ip, prefix = addr.split("/")
                    prefix_len = int(prefix)

                    # /30 or /31 subnets are point-to-point, we can derive neighbor
                    if prefix_len >= 30:
                        neighbor_ip = self._get_neighbor_ip(ip, prefix_len)
                        if neighbor_ip and neighbor_ip not in seen_ips:
                            seen_ips.add(neighbor_ip)
                            peers_to_test.append({
                                "ip": neighbor_ip,
                                "protocol": "underlay",
                                "interface": iface.get("n", iface.get("id")),
                                "source": "interface_subnet"
                            })

        return peers_to_test

    def _get_neighbor_ip(self, ip: str, prefix_len: int) -> Optional[str]:
        """Calculate neighbor IP for point-to-point links (/30 or /31)"""
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                return None

            ip_int = sum(int(p) << (24 - 8*i) for i, p in enumerate(parts))

            if prefix_len == 31:
                # /31: flip the last bit
                neighbor_int = ip_int ^ 1
            elif prefix_len == 30:
                # /30: network has .0, .1, .2, .3 - we use .1 and .2
                last_octet = ip_int & 3
                if last_octet == 1:
                    neighbor_int = ip_int + 1
                elif last_octet == 2:
                    neighbor_int = ip_int - 1
                else:
                    return None  # .0 or .3 are not usable
            else:
                return None

            # Convert back to IP string
            return ".".join(str((neighbor_int >> (24 - 8*i)) & 255) for i in range(4))
        except Exception:
            return None

    async def execute(self) -> TestResult:
        peers_tested = []
        failed = 0

        # Get all peer IPs dynamically
        peers_to_test = self._extract_all_peer_ips()

        for peer in peers_to_test:
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

                result_entry = {
                    "protocol": peer.get("protocol", "unknown"),
                    "peer_ip": peer_ip,
                    "source": peer.get("source", "unknown")
                }

                # Add optional fields
                if peer.get("asn"):
                    result_entry["peer_asn"] = peer["asn"]
                if peer.get("router_id"):
                    result_entry["router_id"] = peer["router_id"]
                if peer.get("interface"):
                    result_entry["interface"] = peer["interface"]

                if proc.returncode == 0:
                    result_entry["status"] = "reachable"
                    peers_tested.append(result_entry)
                else:
                    result_entry["status"] = "unreachable"
                    peers_tested.append(result_entry)
                    failed += 1

            except Exception as e:
                peers_tested.append({
                    "protocol": peer.get("protocol", "unknown"),
                    "peer_ip": peer_ip,
                    "source": peer.get("source", "unknown"),
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
                message="No peers configured or discovered to test"
            )

        # Build detailed message showing what was tested
        sources = set(p.get("source", "unknown") for p in peers_tested)
        source_summary = ", ".join(sources)

        if failed == 0:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"All {len(peers_tested)} peers reachable (sources: {source_summary})",
                details={"peers": peers_tested, "sources": list(sources)}
            )
        else:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.FAILED,
                severity=self.severity,
                message=f"{failed} of {len(peers_tested)} peers unreachable (sources: {source_summary})",
                details={"peers": peers_tested, "failed_count": failed, "sources": list(sources)}
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
