"""
Google Gemini Provider

Implements Google Gemini API integration for wontyoubemyneighbor agentic layer.
"""

from typing import List, Dict, Any, Optional
import os

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from .interface import BaseLLMProvider, ConversationMessage


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider implementation"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-pro"):
        super().__init__(api_key, model)
        self.model = model or "gemini-pro"
        self.client = None

    async def initialize(self) -> bool:
        """Initialize Google Gemini client"""
        if not GEMINI_AVAILABLE:
            print("[Gemini] Google GenerativeAI library not installed. Install with: pip install google-generativeai")
            return False

        # Get API key from parameter or environment
        api_key = self.api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[Gemini] No API key provided. Set GOOGLE_API_KEY environment variable.")
            return False

        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(self.model)
            # Test with simple generation
            response = self.client.generate_content("test")
            self.available = True
            return True
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
            # Configure generation
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            response = self.client.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

    def get_provider_name(self) -> str:
        """Get provider name for logging"""
        return f"Gemini ({self.model})"
