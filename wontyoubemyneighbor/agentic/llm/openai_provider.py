"""
OpenAI GPT-4 Provider

Implements OpenAI API integration for wontyoubemyneighbor agentic layer.
"""

from typing import List, Dict, Any, Optional
import os
import asyncio

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .interface import BaseLLMProvider, ConversationMessage


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT-4 provider implementation"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        super().__init__(api_key, model)
        self.model = model or "gpt-4"
        self.client = None

    async def initialize(self) -> bool:
        """Initialize OpenAI client"""
        if not OPENAI_AVAILABLE:
            print("[OpenAI] OpenAI library not installed. Install with: pip install openai")
            return False

        # Get API key from parameter or environment
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[OpenAI] No API key provided. Set OPENAI_API_KEY environment variable.")
            return False

        try:
            self.client = AsyncOpenAI(api_key=api_key)
            # Test with simple completion (with 10 second timeout)
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5
                ),
                timeout=10.0
            )
            self.available = True
            return True
        except asyncio.TimeoutError:
            print(f"[OpenAI] Initialization timed out (API key may be invalid)")
            return False
        except Exception as e:
            print(f"[OpenAI] Initialization failed: {e}")
            return False

    async def generate_response(
        self,
        messages: List[ConversationMessage],
        context: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """Generate response using OpenAI GPT-4"""
        if not self.available or not self.client:
            raise RuntimeError("OpenAI provider not initialized")

        # Convert messages to OpenAI format
        openai_messages = []

        # Add system context
        if "system" in context:
            openai_messages.append({
                "role": "system",
                "content": context["system"]
            })

        # Add conversation history
        for msg in messages:
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        return f"OpenAI ({self.model})"
