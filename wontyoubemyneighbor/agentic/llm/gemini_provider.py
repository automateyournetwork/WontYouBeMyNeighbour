"""
Google Gemini Provider

Implements Google Gemini API integration for wontyoubemyneighbor agentic layer.
Uses the new google.genai package (non-deprecated).
"""

from typing import List, Dict, Any, Optional
import os
import asyncio

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from .interface import BaseLLMProvider, ConversationMessage


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider implementation"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash-exp"):
        super().__init__(api_key, model)
        self.model = model or "gemini-2.0-flash-exp"
        self.client = None

    async def initialize(self) -> bool:
        """Initialize Google Gemini client"""
        if not GEMINI_AVAILABLE:
            print("[Gemini] Google GenAI library not installed. Install with: pip install google-genai")
            return False

        # Get API key from parameter or environment
        api_key = self.api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[Gemini] No API key provided. Set GOOGLE_API_KEY environment variable.")
            return False

        try:
            self.client = genai.Client(api_key=api_key)
            # Test with simple generation (with 10 second timeout)
            # Gemini API is synchronous, so use to_thread
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents="test"
                ),
                timeout=10.0
            )
            self.available = True
            return True
        except asyncio.TimeoutError:
            print(f"[Gemini] Initialization timed out (API key may be invalid)")
            return False
        except Exception as e:
            print(f"[Gemini] Initialization failed: {e}")
            return False

    async def generate_response(
        self,
        messages: List[ConversationMessage],
        context: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> str:
        """Generate response using Google Gemini"""
        if not self.available or not self.client:
            raise RuntimeError("Gemini provider not initialized")

        # Build prompt with system context and conversation history
        prompt_parts = []

        # Add system context
        if "system" in context:
            prompt_parts.append(f"System Context:\n{context['system']}\n")

        # Add conversation history
        prompt_parts.append("Conversation:")
        for msg in messages:
            role_label = "Human" if msg.role == "user" else "Assistant"
            prompt_parts.append(f"{role_label}: {msg.content}")

        full_prompt = "\n".join(prompt_parts)

        try:
            # Configure generation with new API
            generate_content_config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=generate_content_config
            )
            # Safely access response text
            if not hasattr(response, 'text') or response.text is None:
                raise RuntimeError("Gemini returned empty or invalid response")
            return response.text
        except AttributeError as e:
            raise RuntimeError(f"Invalid Gemini response format: {e}")
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        return f"Gemini ({self.model})"
