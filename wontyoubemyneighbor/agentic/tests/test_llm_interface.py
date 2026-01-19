"""
Tests for LLM Interface Layer
"""

import pytest
import asyncio
from datetime import datetime

from ..llm.interface import (
    LLMInterface,
    LLMProvider,
    ConversationMessage,
    BaseLLMProvider
)


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for testing"""

    def __init__(self, api_key=None, model=None):
        super().__init__(api_key, model)
        self.call_count = 0
        self.last_messages = None

    async def initialize(self) -> bool:
        self.available = True
        return True

    async def generate_response(self, messages, context, temperature=0.7, max_tokens=4000) -> str:
        self.call_count += 1
        self.last_messages = messages
        return f"Mock response {self.call_count}"

    def get_provider_name(self) -> str:
        return "Mock Provider"


class TestConversationMessage:
    """Test ConversationMessage"""

    def test_create_message(self):
        msg = ConversationMessage("user", "Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert isinstance(msg.timestamp, datetime)

    def test_to_dict(self):
        msg = ConversationMessage("assistant", "Hi there")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
        assert "timestamp" in d


class TestLLMInterface:
    """Test LLMInterface"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        llm = LLMInterface(max_turns=10)
        assert llm.max_turns == 10
        assert llm.current_turn == 0
        assert len(llm.messages) == 0

    @pytest.mark.asyncio
    async def test_context_building(self):
        llm = LLMInterface()

        # Update context
        llm.update_network_context({
            "ospf": {"router_id": "1.1.1.1", "neighbors": []},
            "bgp": {"local_as": 65001, "peers": []}
        })

        context = llm._build_system_context()
        assert "1.1.1.1" in context
        assert "65001" in context

    @pytest.mark.asyncio
    async def test_query_with_mock_provider(self):
        llm = LLMInterface(max_turns=5)

        # Add mock provider
        mock_provider = MockLLMProvider()
        await mock_provider.initialize()
        llm.providers[LLMProvider.CLAUDE] = mock_provider

        # Query
        response = await llm.query("Test query")

        assert response == "Mock response 1"
        assert llm.current_turn == 1
        assert len(llm.messages) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_turn_limit(self):
        llm = LLMInterface(max_turns=2)

        mock_provider = MockLLMProvider()
        await mock_provider.initialize()
        llm.providers[LLMProvider.CLAUDE] = mock_provider

        # First query
        await llm.query("Query 1")
        assert llm.current_turn == 1

        # Second query
        await llm.query("Query 2")
        assert llm.current_turn == 2

        # Third query should fail
        response = await llm.query("Query 3")
        assert "Turn limit reached" in response

    @pytest.mark.asyncio
    async def test_conversation_reset(self):
        llm = LLMInterface()

        mock_provider = MockLLMProvider()
        await mock_provider.initialize()
        llm.providers[LLMProvider.CLAUDE] = mock_provider

        await llm.query("Test")
        assert llm.current_turn == 1
        assert len(llm.messages) == 2

        llm.reset_conversation()
        assert llm.current_turn == 0
        assert len(llm.messages) == 0

    def test_conversation_history(self):
        llm = LLMInterface()

        llm.messages.append(ConversationMessage("user", "Hello"))
        llm.messages.append(ConversationMessage("assistant", "Hi"))

        history = llm.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
