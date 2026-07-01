import os
# pyrefly: ignore [missing-import]
import httpx
from typing import List, Dict, Any

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"

class LLMService:
    """
    Service to handle LLM calls via OpenRouter API, managing authentication and request execution.
    """
    
    @staticmethod
    def get_api_key() -> str:
        """
        Retrieves the OpenRouter API key from the environment variables.
        Raises ValueError if the API key is not configured.
        """
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise ValueError("API_KEY not found in environment variables.")
        return api_key

    @classmethod
    async def chat_completion(
        cls,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Sends a chat completion request to the OpenRouter API.
        
        Args:
            messages: A list of message dictionaries, e.g., [{"role": "user", "content": "Hello"}]
            model: The OpenRouter model name to use. Defaults to "openrouter/free".
            timeout: Request timeout in seconds.
            
        Returns:
            The JSON response dictionary from OpenRouter.
        """
        api_key = cls.get_api_key()
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": messages
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=data, timeout=timeout)
            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    message=f"OpenRouter API returned status code {response.status_code}: {response.text}",
                    request=response.request,
                    response=response
                )
            return response.json()

    @classmethod
    async def complete_prompt(
        cls,
        prompt: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Convenience method to complete a single user prompt string.
        
        Args:
            prompt: The string prompt to send.
            model: The OpenRouter model name to use.
            timeout: Request timeout in seconds.
            
        Returns:
            The JSON response dictionary from OpenRouter.
        """
        messages = [{"role": "user", "content": prompt}]
        return await cls.chat_completion(messages, model=model, timeout=timeout)
