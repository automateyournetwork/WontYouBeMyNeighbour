"""
Anthropic Claude Provider

Implements Anthropic Claude API integration for wontyoubemyneighbor agentic layer.
"""

from typing import List, Dict, Any, Optional
import os

try:
    from anthropic import AsyncAnthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

from .interface import BaseLLMProvider, ConversationMessage


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        super().__init__(api_key, model)
        self.model = model or "claude-3-5-sonnet-20241022"
        self.client = None

    async def initialize(self) -> bool:
        """Initialize Anthropic client"""
        if not CLAUDE_AVAILABLE:
            print("[Claude] Anthropic library not installed. Install with: pip install anthropic")
            return False

        # Get API key from parameter or environment
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("[Claude] No API key provided. Set ANTHROPIC_API_KEY environment variable.")
            return False

        try:
            self.client = AsyncAnthropic(api_key=api_key)
            # Test with simple completion
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "test"}]
            )
            self.available = True
            return True
        except Exception as e:
            print(f"[Claude] Initialization failed: {e}")
            return False

    async def generate_response(
        self,
        messages: List[ConversationMessage],
        context: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """Generate response using Anthropic Claude"""
        if not self.available or not self.client:
            raise RuntimeError("Claude provider not initialized")

        # Convert messages to Claude format
        claude_messages = []
        for msg in messages:
            claude_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Build system prompt with context
        system_prompt = context.get("system", "You are a helpful AI assistant.")

        try:
            response = await self.client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=claude_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}")

    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        return f"Claude ({self.model})"
