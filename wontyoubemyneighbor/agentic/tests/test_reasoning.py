"""
Tests for Reasoning Engine
"""

import pytest
import asyncio

from ..reasoning.intent_parser import IntentParser, IntentType, NetworkIntent
from ..reasoning.decision_engine import DecisionEngine, Decision


class TestIntentParser:
    """Test IntentParser"""

    @pytest.mark.asyncio
    async def test_pattern_match_neighbors(self):
        parser = IntentParser()

        intent = await parser.parse("show me my neighbors")

        assert intent.intent_type == IntentType.QUERY_NEIGHBOR
        assert intent.confidence > 0.8

    @pytest.mark.asyncio
    async def test_pattern_match_route(self):
        parser = IntentParser()

        intent = await parser.parse("how do I reach 10.0.0.1")

        assert intent.intent_type == IntentType.QUERY_ROUTE
        assert "destination" in intent.parameters
        assert intent.parameters["destination"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_pattern_match_status(self):
        parser = IntentParser()

        intent = await parser.parse("what's the status")

        assert intent.intent_type == IntentType.QUERY_STATUS

    @pytest.mark.asyncio
    async def test_pattern_match_anomaly(self):
        parser = IntentParser()

        intent = await parser.parse("are there any issues")

        assert intent.intent_type == IntentType.DETECT_ANOMALY

    def test_requires_approval(self):
        # Query intent doesn't require approval
        intent = NetworkIntent(
            intent_type=IntentType.QUERY_NEIGHBOR,
            confidence=0.9,
            parameters={},
            raw_query="show neighbors",
            explanation="test"
        )
        assert not intent.requires_approval()

        # Action intent requires approval
        intent = NetworkIntent(
            intent_type=IntentType.ACTION_ADJUST_METRIC,
            confidence=0.9,
            parameters={},
            raw_query="adjust metric",
            explanation="test"
        )
        assert intent.requires_approval()


class TestDecisionEngine:
    """Test DecisionEngine"""

    @pytest.mark.asyncio
    async def test_route_selection(self):
        engine = DecisionEngine()

        candidates = [
            {
                "next_hop": "192.168.1.2",
                "as_path": [65001, 65002, 65003],
                "med": 100,
                "local_pref": 100,
                "ibgp": False,
                "metric": 20
            },
            {
                "next_hop": "192.168.1.3",
                "as_path": [65001, 65002],  # Shorter
                "med": 50,  # Better MED
                "local_pref": 100,
                "ibgp": False,
                "metric": 10  # Better metric
            }
        ]

        best_route, decision = await engine.select_best_route(
            destination="10.0.0.0/24",
            candidates=candidates
        )

        # Should prefer route with shorter AS path, better MED, and better metric
        assert best_route["next_hop"] == "192.168.1.3"
        assert isinstance(decision, Decision)
        assert decision.decision_type == "route_selection"

    @pytest.mark.asyncio
    async def test_anomaly_detection_neighbor_flapping(self):
        engine = DecisionEngine()

        network_state = {
            "ospf": {
                "neighbors": [
                    {
                        "neighbor_id": "2.2.2.2",
                        "state": "Full",
                        "state_changes": 12  # Flapping!
                    }
                ]
            },
            "bgp": {"peers": []}
        }

        anomalies = await engine.detect_anomalies(network_state)

        assert len(anomalies) > 0
        assert any(a["type"] == "neighbor_flapping" for a in anomalies)

    @pytest.mark.asyncio
    async def test_anomaly_detection_peer_down(self):
        engine = DecisionEngine()

        network_state = {
            "ospf": {"neighbors": []},
            "bgp": {
                "peers": [
                    {
                        "peer": "192.168.1.2",
                        "state": "Idle"  # Down!
                    }
                ]
            }
        }

        anomalies = await engine.detect_anomalies(network_state)

        assert len(anomalies) > 0
        assert any(a["type"] == "peer_down" for a in anomalies)

    @pytest.mark.asyncio
    async def test_metric_adjustment_suggestion(self):
        engine = DecisionEngine()

        # High utilization
        decision = await engine.suggest_metric_adjustment(
            interface="eth0",
            current_metric=10,
            utilization=0.92,
            network_state={}
        )

        assert decision.decision_type == "metric_adjustment"
        assert decision.parameters["suggested_metric"] > 10  # Should increase

    def test_decision_history(self):
        engine = DecisionEngine()

        # Add decision manually
        decision = Decision(
            decision_type="test",
            action="Test action",
            rationale="Test rationale",
            confidence=0.9,
            alternatives=[],
            timestamp=pytest.importorskip('datetime').datetime.utcnow(),
            parameters={}
        )
        engine.decision_history.append(decision)

        history = engine.get_decision_history(limit=10)
        assert len(history) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
