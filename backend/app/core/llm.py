"""
llm.py — LLM client factory.

Creates and returns a configured LangChain chat model backed by Azure OpenAI.
API keys and endpoints are read exclusively from the config layer (environment variables).
Never import or use API keys directly in this file.
"""

from functools import lru_cache
from langchain_openai import AzureChatOpenAI

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_chat_model(temperature: float = 0.2) -> AzureChatOpenAI:
    """
    Return a cached AzureChatOpenAI model instance.

    Uses the Azure OpenAI deployment configured in .env:
      - AZURE_OAI_ENDPOINT
      - AZURE_OAI_API_KEY
      - AZURE_OAI_API_VERSION
      - AZURE_finobi4omini_DEPLOYMENT_NAME

    temperature=0.2 is appropriate for structured advisory reasoning.
    Keep low to maintain deterministic-leaning outputs from the orchestrator.
    """
    settings = get_settings()

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_oai_endpoint,
        api_key=settings.azure_oai_api_key,
        api_version=settings.azure_oai_api_version,
        azure_deployment=settings.azure_deployment_name,
        temperature=temperature,
    )


def get_chat_model_fresh(temperature: float = 0.2) -> AzureChatOpenAI:
    """
    Return a non-cached model instance (useful when temperature varies per call).
    """
    settings = get_settings()

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_oai_endpoint,
        api_key=settings.azure_oai_api_key,
        api_version=settings.azure_oai_api_version,
        azure_deployment=settings.azure_deployment_name,
        temperature=temperature,
    )
