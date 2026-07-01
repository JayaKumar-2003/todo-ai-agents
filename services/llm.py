import os
# pyrefly: ignore [missing-import]
from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "openrouter/free"

class LLMService:
    """
    Service to handle LLM calls using LangChain's ChatOpenAI wrapper,
    configured for OpenRouter API.
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
    def get_llm(cls, model: str = DEFAULT_MODEL, temperature: float = 0.0) -> ChatOpenAI:
        """
        Creates and returns a LangChain ChatOpenAI instance configured for OpenRouter.
        
        Args:
            model: The OpenRouter model name to use. Defaults to "openrouter/free".
            temperature: Sampling temperature.
            
        Returns:
            An initialized ChatOpenAI instance.
        """
        api_key = cls.get_api_key()
        return ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
            default_headers={
                "HTTP-Referer": "https://github.com/todo-ai-agents",
                "X-Title": "TODO AI Agent"
            }
        )
