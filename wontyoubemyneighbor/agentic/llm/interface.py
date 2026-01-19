"""
Multi-Provider LLM Interface

Provides unified interface to OpenAI GPT-4, Anthropic Claude, and Google Gemini
with automatic fallback, conversation management, and network state context injection.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum
import json
from datetime import datetime


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"


class ConversationMessage:
    """Single message in conversation history"""

    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None):
        self.role = role  # 'user' or 'assistant'
        self.content = content
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for provider APIs"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.available = False

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider and check availability"""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: List[ConversationMessage],
        context: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """Generate response from conversation history and context"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        pass


class LLMInterface:
    """
    Unified interface to multiple LLM providers with automatic fallback.

    Manages:
    - Multi-provider support (OpenAI, Claude, Gemini)
    - 75-turn conversation tracking
    - Network state context injection
    - Automatic provider fallback
    - Conversation history persistence
    """

    def __init__(
        self,
        max_turns: int = 75,
        preferred_provider: LLMProvider = LLMProvider.CLAUDE,
        openai_key: Optional[str] = None,
        claude_key: Optional[str] = None,
        gemini_key: Optional[str] = None
    ):
        self.max_turns = max_turns
        self.current_turn = 0
        self.preferred_provider = preferred_provider

        # Conversation history
        self.messages: List[ConversationMessage] = []

        # Provider instances (lazy loaded)
        self.providers: Dict[LLMProvider, BaseLLMProvider] = {}
        self.api_keys = {
            LLMProvider.OPENAI: openai_key,
            LLMProvider.CLAUDE: claude_key,
            LLMProvider.GEMINI: gemini_key
        }

        # Network state context
        self.network_context: Dict[str, Any] = {}

    async def initialize_providers(self):
        """Initialize all available LLM providers"""
        from .openai_provider import OpenAIProvider
        from .claude_provider import ClaudeProvider
        from .gemini_provider import GeminiProvider

        provider_classes = {
            LLMProvider.OPENAI: OpenAIProvider,
            LLMProvider.CLAUDE: ClaudeProvider,
            LLMProvider.GEMINI: GeminiProvider
        }

        for provider_type, provider_class in provider_classes.items():
            if self.api_keys[provider_type]:
                provider = provider_class(
                    api_key=self.api_keys[provider_type]
                )
                if await provider.initialize():
                    self.providers[provider_type] = provider
                    print(f"[LLM] Initialized {provider.get_provider_name()}")

    def update_network_context(self, context: Dict[str, Any]):
        """
        Update network state context for injection into LLM prompts.

        Context should include:
        - OSPF state (neighbors, LSDB, interfaces)
        - BGP state (peers, RIB, attributes)
        - Routing table
        - Interface statistics
        - Recent events/anomalies
        """
        self.network_context.update(context)

    def _build_system_context(self) -> str:
        """Build system context with network state for LLM"""
        context_parts = [
            "You are Ralph, an agentic network router running wontyoubemyneighbor.",
            "You participate natively in OSPF and BGP protocols.",
            "",
            "Current Network State:",
            "=" * 50,
        ]

        # OSPF state
        if "ospf" in self.network_context:
            ospf = self.network_context["ospf"]
            context_parts.append(f"\nOSPF Status:")
            context_parts.append(f"  Router ID: {ospf.get('router_id', 'unknown')}")
            context_parts.append(f"  Neighbors: {len(ospf.get('neighbors', []))}")
            context_parts.append(f"  LSAs in LSDB: {ospf.get('lsa_count', 0)}")

        # BGP state
        if "bgp" in self.network_context:
            bgp = self.network_context["bgp"]
            context_parts.append(f"\nBGP Status:")
            context_parts.append(f"  AS Number: {bgp.get('local_as', 'unknown')}")
            context_parts.append(f"  Peers: {len(bgp.get('peers', []))}")
            context_parts.append(f"  Routes: {bgp.get('route_count', 0)}")

        # Routing table
        if "routes" in self.network_context:
            routes = self.network_context["routes"]
            context_parts.append(f"\nRouting Table: {len(routes)} routes")

        context_parts.append("\n" + "=" * 50)
        context_parts.append(f"\nTurn {self.current_turn + 1} of {self.max_turns}")

        return "\n".join(context_parts)

    async def query(
        self,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> Optional[str]:
        """
        Send query to LLM and get response.

        Automatically:
        - Injects network state context
        - Manages conversation history
        - Enforces turn limits
        - Falls back between providers
        """
        # Check turn limit
        if self.current_turn >= self.max_turns:
            return f"Turn limit reached ({self.max_turns} turns). Reset conversation to continue."

        # Add user message to history
        user_msg = ConversationMessage("user", user_message)
        self.messages.append(user_msg)

        # Build context
        context = {
            "system": self._build_system_context(),
            "network_state": self.network_context,
            "turn": self.current_turn + 1,
            "max_turns": self.max_turns
        }

        # Try providers in order: preferred first, then fallbacks
        provider_order = [self.preferred_provider]
        for provider in LLMProvider:
            if provider not in provider_order:
                provider_order.append(provider)

        response = None
        for provider_type in provider_order:
            if provider_type in self.providers:
                try:
                    provider = self.providers[provider_type]
                    response = await provider.generate_response(
                        messages=self.messages,
                        context=context,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    if response:
                        print(f"[LLM] Response from {provider.get_provider_name()}")
                        break
                except Exception as e:
                    print(f"[LLM] Error from {provider.get_provider_name()}: {e}")
                    continue

        if response:
            # Add assistant response to history
            assistant_msg = ConversationMessage("assistant", response)
            self.messages.append(assistant_msg)
            self.current_turn += 1

        return response

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get full conversation history"""
        return [msg.to_dict() for msg in self.messages]

    def reset_conversation(self):
        """Reset conversation history and turn counter"""
        self.messages.clear()
        self.current_turn = 0
        print(f"[LLM] Conversation reset. Ready for {self.max_turns} turns.")

    def save_conversation(self, filepath: str):
        """Save conversation history to JSON file"""
        history = {
            "turns": self.current_turn,
            "max_turns": self.max_turns,
            "messages": self.get_conversation_history(),
            "network_context": self.network_context
        }
        with open(filepath, 'w') as f:
            json.dump(history, f, indent=2)

    def load_conversation(self, filepath: str):
        """Load conversation history from JSON file"""
        with open(filepath, 'r') as f:
            history = json.load(f)

        self.current_turn = history["turns"]
        self.max_turns = history.get("max_turns", 75)
        self.network_context = history.get("network_context", {})

        self.messages.clear()
        for msg_dict in history["messages"]:
            msg = ConversationMessage(
                role=msg_dict["role"],
                content=msg_dict["content"],
                timestamp=datetime.fromisoformat(msg_dict["timestamp"])
            )
            self.messages.append(msg)

        print(f"[LLM] Loaded conversation: {self.current_turn}/{self.max_turns} turns")
