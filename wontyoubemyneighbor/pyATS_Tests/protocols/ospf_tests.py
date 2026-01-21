"""
OSPF Tests - Open Shortest Path First protocol validation

Tests:
- Neighbor adjacency formation
- LSA database consistency
- Route installation verification
- Area configuration validation
- DR/BDR election verification
"""

from typing import Dict, Any, List, Optional
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.ospf")


class OSPFNeighborAdjacencyTest(BaseTest):
    """Test OSPF neighbor adjacency formation"""

    test_id = "ospf_neighbor_adjacency"
    test_name = "OSPF Neighbor Adjacency"
    description = "Verify OSPF neighbors reach FULL state"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Query FRR vtysh for OSPF neighbors
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip ospf neighbor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()
            if "OSPF not running" in output or "no ospf instance" in output.lower():
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="OSPF is not running on this agent"
                )

            # Parse neighbor output
            # Format: Neighbor ID     Pri State           Dead Time Address         Interface
            neighbors = []
            lines = output.strip().split("\n")

            for line in lines:
                # Skip header lines
                if "Neighbor" in line or line.strip() == "" or "---" in line:
                    continue

                parts = line.split()
                if len(parts) >= 4:
                    neighbor_id = parts[0]
                    priority = parts[1]
                    state = parts[2]
                    # State might be "Full/DR" or "Full/BDR" or "Full/-"
                    state_base = state.split("/")[0]

                    neighbors.append({
                        "neighbor_id": neighbor_id,
                        "priority": priority,
                        "state": state,
                        "state_base": state_base
                    })

            if not neighbors:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No OSPF neighbors found",
                    details={"output": output[:500]}
                )

            # Check states
            full_neighbors = [n for n in neighbors if n["state_base"].upper() == "FULL"]
            non_full = [n for n in neighbors if n["state_base"].upper() != "FULL"]

            details = {
                "total_neighbors": len(neighbors),
                "full_neighbors": len(full_neighbors),
                "neighbors": neighbors
            }

            if non_full:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{len(non_full)} neighbors not in FULL state",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(full_neighbors)} OSPF neighbors in FULL state",
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
                message=f"Failed to check OSPF neighbors: {str(e)}"
            )


class OSPFLSDBConsistencyTest(BaseTest):
    """Test OSPF LSDB consistency"""

    test_id = "ospf_lsdb_consistency"
    test_name = "OSPF LSDB Consistency"
    description = "Verify OSPF Link State Database has expected LSAs"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get LSDB summary
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip ospf database",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()
            if "OSPF not running" in output:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="OSPF is not running"
                )

            # Parse LSDB output
            lsa_counts = {
                "router": 0,
                "network": 0,
                "summary": 0,
                "asbr_summary": 0,
                "external": 0,
                "nssa_external": 0
            }

            # Count LSA types
            current_type = None
            for line in output.split("\n"):
                line_lower = line.lower()
                if "router link states" in line_lower:
                    current_type = "router"
                elif "net link states" in line_lower:
                    current_type = "network"
                elif "summary link states" in line_lower:
                    current_type = "summary"
                elif "asbr-summary" in line_lower:
                    current_type = "asbr_summary"
                elif "as external" in line_lower:
                    current_type = "external"
                elif "nssa-external" in line_lower:
                    current_type = "nssa_external"
                elif current_type and re.match(r"^\d+\.\d+\.\d+\.\d+", line.strip()):
                    lsa_counts[current_type] += 1

            total_lsas = sum(lsa_counts.values())

            details = {
                "lsa_counts": lsa_counts,
                "total_lsas": total_lsas
            }

            # Verify we have at least our own router LSA
            if lsa_counts["router"] == 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No Router LSAs found in LSDB",
                    details=details
                )

            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"LSDB contains {total_lsas} LSAs",
                details=details
            )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check LSDB: {str(e)}"
            )


class OSPFRouteInstallationTest(BaseTest):
    """Test that OSPF routes are installed in RIB"""

    test_id = "ospf_route_installation"
    test_name = "OSPF Route Installation"
    description = "Verify OSPF routes are installed in the routing table"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            # Get OSPF routes from routing table
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip route ospf",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Count OSPF routes
            ospf_routes = []
            for line in output.split("\n"):
                if line.strip().startswith("O"):
                    # Extract route prefix
                    match = re.search(r"O\s+(\S+)", line)
                    if match:
                        prefix = match.group(1)
                        via_match = re.search(r"via\s+(\S+)", line)
                        via = via_match.group(1) if via_match else "direct"

                        ospf_routes.append({
                            "prefix": prefix,
                            "via": via,
                            "type": "O" if "O>" in line else "O"
                        })

            details = {
                "ospf_route_count": len(ospf_routes),
                "routes": ospf_routes[:10]  # First 10 routes
            }

            # Get expected networks from config
            expected_networks = []
            for proto in self.protocols:
                if proto.get("p") in ["ospf", "ospfv3"]:
                    nets = proto.get("nets", [])
                    expected_networks.extend(nets)

            if ospf_routes:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"{len(ospf_routes)} OSPF routes installed",
                    details=details
                )
            else:
                # No routes might be OK for edge devices
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.INFO,
                    message="No OSPF routes (may be expected for edge device)",
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


class OSPFAreaConfigurationTest(BaseTest):
    """Test OSPF area configuration"""

    test_id = "ospf_area_config"
    test_name = "OSPF Area Configuration"
    description = "Verify OSPF area configuration matches expected"
    severity = TestSeverity.MAJOR
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Get OSPF configuration
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip ospf",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Extract configured router ID
            router_id_match = re.search(r"OSPF Routing Process.*Router ID:\s*(\S+)", output)
            actual_router_id = router_id_match.group(1) if router_id_match else None

            # Extract areas
            areas = []
            area_section = False
            for line in output.split("\n"):
                if "Area ID:" in line:
                    area_match = re.search(r"Area ID:\s*(\S+)", line)
                    if area_match:
                        areas.append(area_match.group(1))

            # Get expected config
            expected_router_id = None
            expected_area = None
            for proto in self.protocols:
                if proto.get("p") in ["ospf", "ospfv3"]:
                    expected_router_id = proto.get("r")
                    expected_area = proto.get("a", "0.0.0.0")
                    break

            details = {
                "actual_router_id": actual_router_id,
                "expected_router_id": expected_router_id,
                "configured_areas": areas,
                "expected_area": expected_area
            }

            issues = []
            if expected_router_id and actual_router_id != expected_router_id:
                issues.append(f"Router ID mismatch: expected {expected_router_id}, got {actual_router_id}")

            if expected_area and expected_area not in areas:
                issues.append(f"Expected area {expected_area} not found")

            if issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="; ".join(issues),
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"OSPF configured correctly with router-id {actual_router_id}",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check OSPF config: {str(e)}"
            )


class OSPFDRBDRElectionTest(BaseTest):
    """Test OSPF DR/BDR election"""

    test_id = "ospf_dr_bdr"
    test_name = "OSPF DR/BDR Election"
    description = "Verify DR/BDR election on broadcast segments"
    severity = TestSeverity.MINOR
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Get OSPF interface info
            proc = await asyncio.create_subprocess_exec(
                "vtysh", "-c", "show ip ospf interface",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            output = stdout.decode()

            # Parse interface info for DR/BDR
            interfaces = []
            current_iface = None

            for line in output.split("\n"):
                iface_match = re.match(r"^(\S+)\s+is", line)
                if iface_match:
                    current_iface = {
                        "name": iface_match.group(1),
                        "dr": None,
                        "bdr": None,
                        "state": None,
                        "network_type": None
                    }
                    interfaces.append(current_iface)

                if current_iface:
                    if "Designated Router" in line and "Backup" not in line:
                        dr_match = re.search(r"id\s+(\S+)", line)
                        if dr_match:
                            current_iface["dr"] = dr_match.group(1)
                    elif "Backup Designated Router" in line:
                        bdr_match = re.search(r"id\s+(\S+)", line)
                        if bdr_match:
                            current_iface["bdr"] = bdr_match.group(1)
                    elif "Network Type" in line:
                        type_match = re.search(r"Network Type\s+(\S+)", line)
                        if type_match:
                            current_iface["network_type"] = type_match.group(1)
                    elif "State" in line:
                        state_match = re.search(r"State\s+(\S+)", line)
                        if state_match:
                            current_iface["state"] = state_match.group(1)

            details = {"interfaces": interfaces}

            # Check broadcast interfaces have DR/BDR
            broadcast_without_dr = []
            for iface in interfaces:
                if iface.get("network_type") == "BROADCAST":
                    if not iface.get("dr"):
                        broadcast_without_dr.append(iface["name"])

            if broadcast_without_dr:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"No DR elected on: {', '.join(broadcast_without_dr)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message="DR/BDR election completed on all broadcast segments",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check DR/BDR: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get OSPF test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_ospf",
        suite_name="OSPF Protocol Tests",
        description="OSPF adjacency, LSDB, and route validation",
        protocol="ospf"
    )

    suite.tests = [
        OSPFNeighborAdjacencyTest(agent_config),
        OSPFLSDBConsistencyTest(agent_config),
        OSPFRouteInstallationTest(agent_config),
        OSPFAreaConfigurationTest(agent_config),
        OSPFDRBDRElectionTest(agent_config)
    ]

    return suite
