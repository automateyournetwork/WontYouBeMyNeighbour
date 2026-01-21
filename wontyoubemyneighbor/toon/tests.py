"""
TOON Format Tests

Unit tests for Token Oriented Object Notation serialization and validation.
"""

import json
import unittest
from datetime import datetime

from .models import (
    TOONAgent, TOONNetwork, TOONInterface, TOONProtocolConfig,
    TOONMCPConfig, TOONRuntimeState, TOONLink, TOONTopology, TOONDockerConfig
)
from .format import (
    serialize, deserialize, compress, decompress,
    validate, save_to_file, load_from_file, get_token_count
)
from .schemas import validate_agent, validate_network


class TestTOONModels(unittest.TestCase):
    """Test TOON model classes"""

    def test_interface_creation(self):
        """Test interface model creation and serialization"""
        iface = TOONInterface(
            id="eth0",
            n="eth0",
            t="eth",
            a=["192.168.1.1/24"],
            m="00:11:22:33:44:55",
            s="up"
        )

        data = iface.to_dict()
        self.assertEqual(data["id"], "eth0")
        self.assertEqual(data["a"], ["192.168.1.1/24"])

        # Test round-trip
        iface2 = TOONInterface.from_dict(data)
        self.assertEqual(iface.id, iface2.id)
        self.assertEqual(iface.a, iface2.a)

    def test_protocol_config_creation(self):
        """Test protocol config creation"""
        proto = TOONProtocolConfig(
            p="ospf",
            r="10.0.0.1",
            a="0.0.0.0",
            peers=[{"ip": "10.0.0.2", "priority": 1}],
            nets=["10.0.0.0/24"]
        )

        data = proto.to_dict()
        self.assertEqual(data["p"], "ospf")
        self.assertEqual(data["r"], "10.0.0.1")

    def test_mcp_config_creation(self):
        """Test MCP config creation"""
        mcp = TOONMCPConfig(
            id="gait-1",
            t="gait",
            url="https://github.com/automateyournetwork/gait_mcp",
            c={"tracking": True},
            e=True
        )

        data = mcp.to_dict()
        self.assertEqual(data["t"], "gait")
        self.assertTrue(data["e"])

    def test_agent_creation(self):
        """Test full agent creation with nested objects"""
        agent = TOONAgent(
            id="router-1",
            n="Core Router 1",
            r="10.0.0.1",
            ifs=[
                TOONInterface(id="eth0", n="eth0", a=["10.0.0.1/24"]),
                TOONInterface(id="lo0", n="lo0", t="lo", a=["127.0.0.1/8"])
            ],
            protos=[
                TOONProtocolConfig(p="ospf", r="10.0.0.1", a="0.0.0.0")
            ],
            mcps=[
                TOONMCPConfig(id="gait", t="gait", url="https://github.com/automateyournetwork/gait_mcp")
            ]
        )

        data = agent.to_dict()
        self.assertEqual(len(data["ifs"]), 2)
        self.assertEqual(len(data["protos"]), 1)
        self.assertEqual(len(data["mcps"]), 1)

        # Test round-trip
        agent2 = TOONAgent.from_dict(data)
        self.assertEqual(agent.id, agent2.id)
        self.assertEqual(len(agent.ifs), len(agent2.ifs))

    def test_network_creation(self):
        """Test network creation with agents"""
        network = TOONNetwork(
            id="test-network",
            n="Test Network",
            docker=TOONDockerConfig(n="test-net", subnet="172.20.0.0/16"),
            agents=[
                TOONAgent(id="r1", n="Router 1", r="10.0.0.1"),
                TOONAgent(id="r2", n="Router 2", r="10.0.0.2")
            ],
            topo=TOONTopology(
                links=[TOONLink(id="link1", a1="r1", i1="eth0", a2="r2", i2="eth0")]
            )
        )

        data = network.to_dict()
        self.assertEqual(len(data["agents"]), 2)
        self.assertIsNotNone(data["topo"])

        # Test round-trip
        network2 = TOONNetwork.from_dict(data)
        self.assertEqual(network.id, network2.id)
        self.assertEqual(len(network.agents), len(network2.agents))


class TestTOONFormat(unittest.TestCase):
    """Test TOON format serialization"""

    def test_serialize_deserialize(self):
        """Test basic serialization round-trip"""
        data = {"id": "test", "n": "Test", "v": "1.0"}

        serialized = serialize(data)
        deserialized = deserialize(serialized)

        self.assertEqual(data, deserialized)

    def test_compact_serialization(self):
        """Test compact serialization produces smaller output"""
        data = {"id": "test", "name": "TestAgent", "value": 123}

        normal = serialize(data, indent=2)  # Use indented for comparison
        compact = serialize(data, compact=True)

        self.assertLess(len(compact), len(normal))
        # Compact should not have newlines or indentation
        self.assertNotIn('\n', compact)

    def test_compress_decompress(self):
        """Test compression round-trip"""
        original = serialize({"id": "test", "data": "x" * 1000})

        compressed = compress(original)
        decompressed = decompress(compressed)

        self.assertEqual(original, decompressed)
        # Compression should reduce size for repetitive data
        self.assertLess(len(compressed), len(original))

    def test_typed_deserialization(self):
        """Test deserialization to specific type"""
        agent_data = {
            "id": "r1",
            "n": "Router 1",
            "r": "10.0.0.1",
            "ifs": [],
            "protos": [],
            "mcps": []
        }

        serialized = serialize(agent_data)
        agent = deserialize(serialized, TOONAgent)

        self.assertIsInstance(agent, TOONAgent)
        self.assertEqual(agent.id, "r1")

    def test_token_count(self):
        """Test token count estimation"""
        data = {"short": "a", "long": "x" * 100}

        count = get_token_count(data)
        self.assertGreater(count, 0)


class TestTOONValidation(unittest.TestCase):
    """Test TOON schema validation"""

    def test_valid_agent(self):
        """Test validation of valid agent"""
        agent_data = {
            "id": "router-1",
            "n": "Core Router",
            "r": "10.0.0.1",
            "ifs": [],
            "protos": [],
            "mcps": []
        }

        result = validate_agent(agent_data)
        self.assertTrue(result["valid"])

    def test_invalid_agent_missing_id(self):
        """Test validation catches missing required field"""
        agent_data = {
            "n": "Core Router",
            "r": "10.0.0.1"
        }

        result = validate_agent(agent_data)
        self.assertFalse(result["valid"])
        self.assertIn("id", str(result["errors"]))

    def test_valid_network(self):
        """Test validation of valid network"""
        network_data = {
            "id": "net-1",
            "n": "Test Network",
            "agents": []
        }

        result = validate_network(network_data)
        self.assertTrue(result["valid"])

    def test_format_validate(self):
        """Test format.validate function"""
        valid_json = '{"id": "test", "n": "Test"}'
        invalid_json = '{invalid json}'

        result1 = validate(valid_json, "agent")
        # Missing required fields but JSON is valid
        self.assertIsNotNone(result1)

        result2 = validate(invalid_json)
        self.assertFalse(result2["valid"])


class TestTOONRuntimeState(unittest.TestCase):
    """Test runtime state capture and serialization"""

    def test_runtime_state_capture(self):
        """Test capturing current runtime state"""
        state = TOONRuntimeState.capture_now()

        self.assertIsNotNone(state.ts)
        # Timestamp should be valid ISO format
        datetime.fromisoformat(state.ts)

    def test_runtime_state_with_data(self):
        """Test runtime state with RIB and LSDB data"""
        state = TOONRuntimeState(
            ts=datetime.now().isoformat(),
            rib=[
                {"prefix": "10.0.0.0/24", "nexthop": "192.168.1.1", "metric": 10}
            ],
            lsdb=[
                {"type": "router", "id": "10.0.0.1", "age": 100}
            ],
            nbrs=[
                {"id": "10.0.0.2", "state": "FULL", "ip": "192.168.1.2"}
            ],
            metrics={"cpu": 25.5, "memory": 60.0}
        )

        data = state.to_dict()
        self.assertEqual(len(data["rib"]), 1)
        self.assertEqual(len(data["lsdb"]), 1)
        self.assertEqual(data["metrics"]["cpu"], 25.5)


def run_tests():
    """Run all TOON tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestTOONModels))
    suite.addTests(loader.loadTestsFromTestCase(TestTOONFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestTOONValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestTOONRuntimeState))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    run_tests()
