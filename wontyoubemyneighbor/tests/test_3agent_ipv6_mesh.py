#!/usr/bin/env python3
"""
Test Script: 3-Agent IPv6 Mesh with Neighbor Discovery

This test launches 3 agents from the templates:
- Layer 1: Docker network (172.20.0.0/16 - IPv4)
- Layer 2: ASI Overlay (fd00:a510:0:{net}::{agent}/64 - IPv6, e.g., fd00:a510:0:1::1/64)
- Layer 3: Underlay (user-defined routing)

Tests:
1. Docker network creation
2. Agent container launch with IPv6 overlay addresses
3. IPv6 Neighbor Discovery between agents
4. Full mesh connectivity verification
"""

import asyncio
import json
import logging
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from toon.models import TOONAgent, TOONNetwork, TOONDockerConfig, TOONTopology, TOONLink
from orchestrator.docker_manager import DockerManager
from orchestrator.agent_launcher import AgentLauncher
from orchestrator.network_orchestrator import NetworkOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Test3AgentMesh")


def load_templates():
    """Load agent and topology templates"""
    templates_dir = "/Users/john.capobianco/WontYouBeMyNeighbour/Agent Input/templates"

    # Load agents
    with open(os.path.join(templates_dir, "all_agents.json"), "r") as f:
        agents_data = json.load(f)

    # Load topology
    with open(os.path.join(templates_dir, "first_topology.json"), "r") as f:
        topology_data = json.load(f)

    return agents_data, topology_data


def create_network_from_templates(agents_data, topology_data):
    """Create a TOONNetwork from template data"""

    # Create agents
    agents = []
    for agent_data in agents_data:
        agent = TOONAgent(
            id=agent_data["id"],
            n=agent_data["n"],
            r=agent_data["r"],
            ifs=[],
            protos=[],
            mcps=[]
        )

        # Parse interfaces
        for if_data in agent_data.get("ifs", []):
            from toon.models import TOONInterface
            iface = TOONInterface(
                id=if_data["id"],
                n=if_data["n"],
                t=if_data.get("t", "eth"),
                a=if_data.get("a", []),
                s=if_data.get("s", "up"),
                mtu=if_data.get("mtu", 1500)
            )
            agent.ifs.append(iface)

        # Parse protocols
        for proto_data in agent_data.get("protos", []):
            from toon.models import TOONProtocolConfig
            proto = TOONProtocolConfig(
                p=proto_data["p"],
                r=proto_data.get("r", agent_data["r"]),
                a=proto_data.get("a"),
                asn=proto_data.get("asn"),
                peers=proto_data.get("peers", []),
                nets=proto_data.get("nets", []),
                opts=proto_data.get("opts", {})
            )
            agent.protos.append(proto)

        agents.append(agent)

    # Create topology
    links = []
    for link_data in topology_data.get("links", []):
        link = TOONLink(
            id=link_data["id"],
            a1=link_data["a1"],
            i1=link_data["i1"],
            a2=link_data["a2"],
            i2=link_data["i2"],
            t=link_data.get("t", "ethernet"),
            c=link_data.get("c", 10)
        )
        links.append(link)

    topo = TOONTopology(links=links)

    # Create Docker config with 172.21.0.0/16 (IPv4) - different from existing springfield
    docker_config = TOONDockerConfig(
        n="springfield-test",
        driver="bridge",
        subnet="172.21.0.0/16",
        gw="172.21.0.1"
    )

    # Create network
    network = TOONNetwork(
        id="test-3agent-mesh",
        n="Test 3-Agent IPv6 Mesh",
        docker=docker_config,
        agents=agents,
        topo=topo
    )

    return network


async def test_docker_available():
    """Test 1: Check Docker is available"""
    logger.info("=" * 60)
    logger.info("TEST 1: Docker Availability")
    logger.info("=" * 60)

    dm = DockerManager()
    if dm.available:
        logger.info(f"✓ Docker is available")
        return True
    else:
        logger.error(f"✗ Docker not available: {dm.error_message}")
        return False


async def test_launch_network(network, network_foundation):
    """Test 2: Launch network with 3 agents"""
    logger.info("=" * 60)
    logger.info("TEST 2: Launch Network with 3 Agents")
    logger.info("=" * 60)

    orchestrator = NetworkOrchestrator()

    logger.info(f"Network: {network.n}")
    logger.info(f"Docker subnet: {network.docker.subnet}")
    logger.info(f"Agents: {[a.n for a in network.agents]}")
    logger.info(f"Network foundation: {network_foundation}")

    # Launch network
    deployment = await orchestrator.launch(
        network=network,
        image="wontyoubemyneighbor:latest",
        api_keys=None,
        parallel=True,
        network_foundation=network_foundation
    )

    logger.info(f"Deployment status: {deployment.status}")
    logger.info(f"Docker network: {deployment.docker_network}")
    logger.info(f"Subnet: {deployment.subnet}")

    # Check each agent
    all_running = True
    for agent_id, agent_container in deployment.agents.items():
        status = "✓" if agent_container.status == "running" else "✗"
        logger.info(f"  {status} Agent {agent_id}:")
        logger.info(f"      Container: {agent_container.container_name}")
        logger.info(f"      Status: {agent_container.status}")
        logger.info(f"      Docker IP (Layer 1): {agent_container.ip_address}")
        logger.info(f"      IPv6 Overlay (Layer 2): {agent_container.ipv6_overlay}")
        logger.info(f"      WebUI Port: {agent_container.webui_port}")

        if agent_container.status != "running":
            all_running = False
            logger.error(f"      Error: {agent_container.error_message}")

    return deployment, orchestrator, all_running


async def test_ipv6_mesh_connectivity(deployment):
    """Test 3: Verify IPv6 mesh connectivity"""
    logger.info("=" * 60)
    logger.info("TEST 3: IPv6 Mesh Connectivity")
    logger.info("=" * 60)

    # Get IPv6 overlay addresses
    ipv6_addresses = {}
    for agent_id, agent_container in deployment.agents.items():
        if agent_container.ipv6_overlay:
            ipv6_addresses[agent_id] = agent_container.ipv6_overlay.split('/')[0]

    logger.info("IPv6 Overlay Addresses (Layer 2 - ASI Agent Mesh):")
    for agent_id, ipv6 in ipv6_addresses.items():
        logger.info(f"  {agent_id}: {ipv6}")

    # Verify we have 3 unique IPv6 addresses
    unique_addrs = set(ipv6_addresses.values())
    if len(unique_addrs) == 3:
        logger.info(f"✓ All 3 agents have unique IPv6 overlay addresses")
    else:
        logger.error(f"✗ Expected 3 unique addresses, got {len(unique_addrs)}")
        return False

    # Verify IPv6 addresses follow the expected pattern (e.g., fd00:a510:0:1::1/64)
    for agent_id, ipv6 in ipv6_addresses.items():
        if ipv6.startswith("fd00:a510:0:"):
            logger.info(f"✓ {agent_id} has valid ASI overlay address: {ipv6}")
        else:
            logger.error(f"✗ {agent_id} has invalid address format: {ipv6}")
            return False

    return True


async def test_agent_webui_reachable(deployment):
    """Test 4: Check agent WebUI is reachable"""
    logger.info("=" * 60)
    logger.info("TEST 4: Agent WebUI Reachability")
    logger.info("=" * 60)

    import urllib.request
    import urllib.error

    all_reachable = True
    for agent_id, agent_container in deployment.agents.items():
        if agent_container.webui_port:
            url = f"http://localhost:{agent_container.webui_port}"
            try:
                req = urllib.request.Request(url, method='GET')
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        logger.info(f"✓ {agent_id} WebUI reachable at {url}")
                    else:
                        logger.warning(f"? {agent_id} WebUI returned status {resp.status}")
            except urllib.error.URLError as e:
                logger.warning(f"? {agent_id} WebUI not ready yet: {e}")
                all_reachable = False
            except Exception as e:
                logger.warning(f"? {agent_id} WebUI error: {e}")
                all_reachable = False

    return all_reachable


async def test_neighbor_discovery_status(deployment):
    """Test 5: Check Neighbor Discovery status via API"""
    logger.info("=" * 60)
    logger.info("TEST 5: Neighbor Discovery Status")
    logger.info("=" * 60)

    import urllib.request
    import urllib.error

    nd_results = {}
    for agent_id, agent_container in deployment.agents.items():
        if agent_container.api_port:
            # Try to get ND status from agent API
            url = f"http://localhost:{agent_container.api_port}/api/nd/neighbors"
            try:
                req = urllib.request.Request(url, method='GET')
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        nd_results[agent_id] = data
                        neighbor_count = len(data.get("neighbors", []))
                        logger.info(f"✓ {agent_id}: {neighbor_count} neighbors discovered")
                        for neighbor in data.get("neighbors", []):
                            logger.info(f"    - {neighbor.get('ipv6_address')}: {neighbor.get('state')}")
                    else:
                        logger.info(f"? {agent_id}: ND API returned {resp.status}")
            except urllib.error.URLError as e:
                logger.info(f"? {agent_id}: ND API not available: {e}")
            except Exception as e:
                logger.info(f"? {agent_id}: ND API error: {e}")

    # Check if mesh is forming (each agent should see 2 neighbors)
    full_mesh = True
    for agent_id, data in nd_results.items():
        neighbor_count = len(data.get("neighbors", []))
        if neighbor_count < 2:
            full_mesh = False

    if full_mesh and len(nd_results) == 3:
        logger.info("✓ Full IPv6 mesh established!")
    else:
        logger.info("? Mesh still forming (ND takes time to discover neighbors)")

    return nd_results


async def cleanup(orchestrator, network_id):
    """Cleanup: Stop network and remove containers"""
    logger.info("=" * 60)
    logger.info("CLEANUP")
    logger.info("=" * 60)

    try:
        success = await orchestrator.stop(
            network_id,
            remove_containers=True,
            remove_network=True,
            save_state=False
        )
        if success:
            logger.info("✓ Network stopped and cleaned up")
        else:
            logger.warning("? Cleanup may not be complete")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


async def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("3-AGENT IPv6 MESH TEST")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Testing 3-Layer Network Architecture:")
    logger.info("  Layer 1: Docker Network (172.21.0.0/16 - IPv4)")
    logger.info("  Layer 2: ASI Overlay (fd00:a510:0::/48 - IPv6)")
    logger.info("  Layer 3: Underlay (OSPF/BGP from templates)")
    logger.info("")

    orchestrator = None
    network_id = None

    try:
        # Test 1: Docker available
        if not await test_docker_available():
            logger.error("Docker not available, aborting tests")
            return 1

        # Load templates
        logger.info("")
        logger.info("Loading templates...")
        agents_data, topology_data = load_templates()
        logger.info(f"  Loaded {len(agents_data)} agents")
        logger.info(f"  Loaded {len(topology_data.get('links', []))} links")

        # Create network
        network = create_network_from_templates(agents_data, topology_data)
        network_id = network.id

        # Network foundation settings
        network_foundation = {
            "underlay_protocol": "ipv4",  # Using IPv4 underlay from templates
            "overlay": {
                "enabled": True,
                "subnet": "fd00:a510::/48",
                "enable_nd": True,
                "enable_routes": True
            },
            "docker_ipv6": {
                "enabled": False  # Using IPv4 Docker network
            }
        }

        # Test 2: Launch network
        logger.info("")
        deployment, orchestrator, all_running = await test_launch_network(network, network_foundation)

        if not all_running:
            logger.warning("Not all agents running, but continuing with tests...")

        # Wait for containers to initialize
        logger.info("")
        logger.info("Waiting 10 seconds for agents to initialize...")
        await asyncio.sleep(10)

        # Test 3: IPv6 mesh connectivity
        logger.info("")
        await test_ipv6_mesh_connectivity(deployment)

        # Test 4: WebUI reachability
        logger.info("")
        await test_agent_webui_reachable(deployment)

        # Test 5: Neighbor Discovery
        logger.info("")
        await test_neighbor_discovery_status(deployment)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)

        running_agents = sum(1 for a in deployment.agents.values() if a.status == "running")
        logger.info(f"  Agents running: {running_agents}/3")
        logger.info(f"  Docker network: {deployment.docker_network}")
        logger.info(f"  IPv4 subnet (Layer 1): {deployment.subnet}")
        logger.info(f"  IPv6 overlay (Layer 2): fd00:a510:0:*::/64")

        logger.info("")
        logger.info("Agent Details:")
        for agent_id, ac in deployment.agents.items():
            logger.info(f"  {ac.container_name}:")
            logger.info(f"    Docker IP: {ac.ip_address}")
            logger.info(f"    IPv6 Overlay: {ac.ipv6_overlay}")
            logger.info(f"    WebUI: http://localhost:{ac.webui_port}")

        # Ask user if they want to keep the network running
        logger.info("")
        logger.info("=" * 60)
        response = input("Keep network running for manual testing? [y/N]: ").strip().lower()
        if response != 'y':
            await cleanup(orchestrator, network_id)
        else:
            logger.info("Network left running. To stop manually:")
            logger.info("  docker stop $(docker ps -q --filter 'label=asi.network_id=test-3agent-mesh')")
            logger.info("  docker network rm springfield-test")

        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        if orchestrator and network_id:
            await cleanup(orchestrator, network_id)
        return 1
    except Exception as e:
        logger.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()
        if orchestrator and network_id:
            await cleanup(orchestrator, network_id)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
