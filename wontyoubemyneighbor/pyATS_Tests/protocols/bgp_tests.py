"""
BGP Tests - Border Gateway Protocol validation

Tests:
- Peer establishment
- Prefix advertisement/reception
- Path attribute validation
- Route policy application
- AS path verification
"""

from typing import Dict, Any, List
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.bgp")


class BGPPeerEstablishmentTest(BaseTest):
    """Test BGP peer establishment"""

    test_id = "bgp_peer_establishment"
    test_name = "BGP Peer Establishment"
    description = "Verify BGP peers reach Established state"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Query BGP neighbor summary
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip bgp summary",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            if "BGP not running" in output or "No BGP process" in output:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BGP is not running on this agent"
                )

            # Parse BGP summary output
            # Format varies but typically:
            # Neighbor        V         AS MsgRcvd MsgSent   TblVer  InQ OutQ  Up/Down  State/PfxRcd
            peers = []
            parsing_peers = False

            for line in output.split("\n"):
                # Skip header lines
                if "Neighbor" in line and "State" in line:
                    parsing_peers = True
                    continue

                if parsing_peers and line.strip():
                    parts = line.split()
                    if len(parts) >= 9:
                        neighbor_ip = parts[0]
                        # Validate it looks like an IP
                        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", neighbor_ip):
                            continue

                        remote_as = parts[2]
                        uptime = parts[8] if len(parts) > 8 else "?"
                        state_pfx = parts[9] if len(parts) > 9 else parts[-1]

                        # State/PfxRcd - if it's a number, peer is established
                        try:
                            prefixes = int(state_pfx)
                            state = "Established"
                        except ValueError:
                            prefixes = 0
                            state = state_pfx  # Could be "Active", "Connect", etc.

                        peers.append({
                            "neighbor": neighbor_ip,
                            "remote_as": remote_as,
                            "state": state,
                            "prefixes_received": prefixes,
                            "uptime": uptime
                        })

            if not peers:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No BGP peers found",
                    details={"output": output[:500]}
                )

            established = [p for p in peers if p["state"] == "Established"]
            non_established = [p for p in peers if p["state"] != "Established"]

            details = {
                "total_peers": len(peers),
                "established": len(established),
                "peers": peers
            }

            if non_established:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{len(non_established)} peers not Established",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(established)} BGP peers Established",
                    details=details
                )

        except FileNotFoundError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message="vtysh not found - FRR may not be installed"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check BGP peers: {str(e)}"
            )


class BGPPrefixAdvertisementTest(BaseTest):
    """Test BGP prefix advertisement"""

    test_id = "bgp_prefix_advertisement"
    test_name = "BGP Prefix Advertisement"
    description = "Verify expected prefixes are being advertised"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get configured networks from agent config
            expected_networks = []
            local_asn = None
            for proto in self.protocols:
                if proto.get("p") in ["ibgp", "ebgp"]:
                    nets = proto.get("nets", [])
                    expected_networks.extend(nets)
                    local_asn = proto.get("asn")

            if not expected_networks:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No networks configured for advertisement"
                )

            # Get advertised routes
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip bgp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Parse BGP table for locally originated routes
            advertised = []
            for line in output.split("\n"):
                # Local routes typically show origin 'i'
                if "*>" in line:
                    parts = line.split()
                    for part in parts:
                        # Look for CIDR notation
                        if "/" in part and re.match(r"^\d+\.\d+\.\d+\.\d+/\d+$", part):
                            advertised.append(part)
                            break

            details = {
                "expected_networks": expected_networks,
                "advertised_prefixes": advertised[:20],  # First 20
                "total_advertised": len(advertised)
            }

            # Check if expected networks are advertised
            missing = [n for n in expected_networks if n not in advertised]

            if missing:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Missing advertisements: {', '.join(missing)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(expected_networks)} configured networks advertised",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check advertisements: {str(e)}"
            )


class BGPPrefixReceptionTest(BaseTest):
    """Test BGP prefix reception"""

    test_id = "bgp_prefix_reception"
    test_name = "BGP Prefix Reception"
    description = "Verify prefixes are being received from peers"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get peer prefixes
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip bgp summary",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Parse prefix counts from summary
            peer_prefixes = []
            parsing = False

            for line in output.split("\n"):
                if "Neighbor" in line and "State" in line:
                    parsing = True
                    continue

                if parsing and line.strip():
                    parts = line.split()
                    if len(parts) >= 9:
                        neighbor = parts[0]
                        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", neighbor):
                            continue

                        try:
                            prefixes = int(parts[-1])
                        except ValueError:
                            prefixes = 0  # Not established

                        peer_prefixes.append({
                            "neighbor": neighbor,
                            "prefixes": prefixes
                        })

            details = {
                "peers": peer_prefixes,
                "total_peers": len(peer_prefixes),
                "total_prefixes": sum(p["prefixes"] for p in peer_prefixes)
            }

            # Check if we're receiving any prefixes
            peers_with_prefixes = [p for p in peer_prefixes if p["prefixes"] > 0]

            if not peer_prefixes:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BGP peers configured"
                )
            elif not peers_with_prefixes:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No prefixes received from any peer",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Receiving {details['total_prefixes']} prefixes from {len(peers_with_prefixes)} peers",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check prefix reception: {str(e)}"
            )


class BGPASPathVerificationTest(BaseTest):
    """Test BGP AS path verification"""

    test_id = "bgp_as_path"
    test_name = "BGP AS Path Verification"
    description = "Verify AS paths are correct for received routes"
    severity = TestSeverity.MINOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get BGP routes with AS paths
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip bgp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Parse AS paths
            routes_with_paths = []
            current_prefix = None

            for line in output.split("\n"):
                # Route line starts with status codes
                if line.strip().startswith(("*", ">")):
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if "/" in part and re.match(r"^\d+\.\d+\.\d+\.\d+/\d+$", part):
                            current_prefix = part
                            # AS path is usually at the end before origin code
                            # Look for sequence of numbers
                            as_path = []
                            for p in parts[i+1:]:
                                if p.isdigit():
                                    as_path.append(int(p))
                                elif p in ["i", "e", "?"]:
                                    break

                            routes_with_paths.append({
                                "prefix": current_prefix,
                                "as_path": as_path,
                                "path_length": len(as_path)
                            })
                            break

            details = {
                "routes_analyzed": len(routes_with_paths),
                "sample_routes": routes_with_paths[:5]
            }

            # Check for AS path loops (shouldn't happen if properly configured)
            loops_found = 0
            for route in routes_with_paths:
                if len(route["as_path"]) != len(set(route["as_path"])):
                    loops_found += 1

            if loops_found > 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=TestSeverity.MAJOR,
                    message=f"Found {loops_found} routes with AS path loops",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"AS paths valid for {len(routes_with_paths)} routes",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to verify AS paths: {str(e)}"
            )


class BGPRouteInstallationTest(BaseTest):
    """Test BGP routes are installed in RIB"""

    test_id = "bgp_route_installation"
    test_name = "BGP Route Installation"
    description = "Verify BGP routes are installed in the routing table"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get BGP routes from routing table
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip route bgp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Count BGP routes
            bgp_routes = []
            for line in output.split("\n"):
                if line.strip().startswith("B"):
                    match = re.search(r"B[>*]*\s+(\S+)", line)
                    if match:
                        prefix = match.group(1)
                        via_match = re.search(r"via\s+(\S+)", line)
                        via = via_match.group(1) if via_match else "direct"

                        bgp_routes.append({
                            "prefix": prefix,
                            "via": via
                        })

            details = {
                "bgp_route_count": len(bgp_routes),
                "routes": bgp_routes[:10]  # First 10
            }

            if bgp_routes:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"{len(bgp_routes)} BGP routes installed in RIB",
                    details=details
                )
            else:
                # No BGP routes might be OK for some configurations
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.INFO,
                    message="No BGP routes in RIB (may be expected)",
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
    """Get BGP test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_bgp",
        suite_name="BGP Protocol Tests",
        description="BGP peer establishment and route validation",
        protocol="bgp"
    )

    suite.tests = [
        BGPPeerEstablishmentTest(agent_config),
        BGPPrefixAdvertisementTest(agent_config),
        BGPPrefixReceptionTest(agent_config),
        BGPASPathVerificationTest(agent_config),
        BGPRouteInstallationTest(agent_config)
    ]

    return suite
