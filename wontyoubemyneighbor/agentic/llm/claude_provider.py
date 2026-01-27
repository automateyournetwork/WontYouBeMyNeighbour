"""
Anthropic Claude Provider

Implements Anthropic Claude API integration for wontyoubemyneighbor agentic layer.
"""

from typing import List, Dict, Any, Optional
import os
import asyncio

try:
    from anthropic import AsyncAnthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

from .interface import BaseLLMProvider, ConversationMessage


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        super().__init__(api_key, model)
        # Try multiple valid model versions in order of preference
        # Latest models first: Sonnet 4 (default), Opus 4.5 (most capable), then older fallbacks
        self.model_fallbacks = [
            "claude-sonnet-4-20250514",      # Claude Sonnet 4 - great balance (default)
            "claude-opus-4-5-20251101",       # Claude Opus 4.5 - most capable
            "claude-3-5-sonnet-20241022",     # Claude 3.5 Sonnet (legacy fallback)
            "claude-3-5-haiku-20241022",      # Claude 3.5 Haiku (fast fallback)
        ]
        self.model = model or self.model_fallbacks[0]
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
            # Try each model fallback until one works
            last_error = None
            for model_name in self.model_fallbacks:
                try:
                    response = await asyncio.wait_for(
                        self.client.messages.create(
                            model=model_name,
                            max_tokens=5,
                            messages=[{"role": "user", "content": "test"}]
                        ),
                        timeout=10.0
                    )
                    # Success! Use this model
                    self.model = model_name
                    self.available = True
                    print(f"[Claude] Initialized successfully with model: {model_name}")
                    return True
                except Exception as e:
                    last_error = e
                    continue
            # All models failed
            print(f"[Claude] All model fallbacks failed. Last error: {last_error}")
            return False
        except asyncio.TimeoutError:
            print(f"[Claude] Initialization timed out (API key may be invalid)")
            return False
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
            # Safely access response content
            if not response.content:
                raise RuntimeError("Claude returned empty response")
            return response.content[0].text
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}")
        except (IndexError, AttributeError) as e:
            raise RuntimeError(f"Invalid Claude response format: {e}")

    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        return f"Claude ({self.model})"
