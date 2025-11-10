"""
LLM Factory for Azure OpenAI Integration with OpenAI Fallback

Centralizes all LLM instantiation to use Azure OpenAI with automatic fallback to standard OpenAI.
"""

import logging
from typing import Optional, Union
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


def get_llm(
    model_type: str = "gpt4o",
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    **kwargs
) -> Union[AzureChatOpenAI, ChatOpenAI]:
    """
    Create an LLM instance with Azure OpenAI (primary) and OpenAI fallback.
    
    Strategy:
    - Try Azure OpenAI first (if configured)
    - Fall back to standard OpenAI if Azure fails or not configured
    
    Args:
        model_type: "gpt4o" (for complex reasoning) or "gpt4o-mini" (for simple tasks)
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
        max_tokens: Maximum tokens in response (None = model default)
        **kwargs: Additional arguments
        
    Returns:
        Configured LLM instance (Azure or OpenAI)
    """
    settings = get_settings()
    
    # Try Azure OpenAI first
    if settings.azure_openai_key:
        try:
            # Map model type to deployment name
            deployment_map = {
                "gpt4o": settings.azure_deployment_gpt4o,
                "gpt4o-mini": settings.azure_deployment_gpt4o_mini,
                "gpt-4o": settings.azure_deployment_gpt4o,
                "gpt-4o-mini": settings.azure_deployment_gpt4o_mini,
            }
            
            deployment_name = deployment_map.get(model_type, settings.azure_deployment_gpt4o)
            
            llm_config = {
                "azure_deployment": deployment_name,
                "api_key": settings.azure_openai_key,
                "azure_endpoint": settings.azure_openai_endpoint,
                "api_version": settings.azure_openai_api_version,
                "temperature": temperature,
                **kwargs
            }
            
            if max_tokens is not None:
                llm_config["max_tokens"] = max_tokens
            
            logger.info(
                f"✅ Using Azure OpenAI: deployment={deployment_name}, "
                f"endpoint={settings.azure_openai_endpoint}"
            )
            
            return AzureChatOpenAI(**llm_config)
            
        except Exception as e:
            logger.warning(f"⚠️ Azure OpenAI failed: {e}, falling back to standard OpenAI")
    
    # Fall back to standard OpenAI
    if not settings.openai_api_key:
        raise ValueError(
            "Neither Azure OpenAI nor OpenAI API key configured. "
            "Please set AZURE_OPENAI_KEY or OPENAI_API_KEY environment variable."
        )
    
    # Map model type to OpenAI model name
    openai_model_map = {
        "gpt4o": "gpt-4o",
        "gpt4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
    }
    
    model_name = openai_model_map.get(model_type, "gpt-4o")
    
    llm_config = {
        "model": model_name,
        "api_key": settings.openai_api_key,
        "temperature": temperature,
        **kwargs
    }
    
    if max_tokens is not None:
        llm_config["max_tokens"] = max_tokens
    
    logger.info(f"✅ Using OpenAI fallback: model={model_name}")
    
    return ChatOpenAI(**llm_config)


def get_smart_llm(temperature: float = 0.0, **kwargs) -> Union[AzureChatOpenAI, ChatOpenAI]:
    """
    Get GPT-4o (full model) for complex reasoning tasks.
    
    Use for:
    - Strategic planning
    - Complex page analysis
    - Content extraction with nuance
    - Intent interpretation
    
    Args:
        temperature: Sampling temperature
        **kwargs: Additional arguments
        
    Returns:
        GPT-4o LLM instance (Azure or OpenAI)
    """
    return get_llm(model_type="gpt4o", temperature=temperature, **kwargs)


def get_fast_llm(temperature: float = 0.0, **kwargs) -> Union[AzureChatOpenAI, ChatOpenAI]:
    """
    Get GPT-4o-mini for simple, fast tasks.
    
    Use for:
    - Simple text extraction
    - Straightforward classification
    - Quick validations
    
    Args:
        temperature: Sampling temperature
        **kwargs: Additional arguments
        
    Returns:
        GPT-4o-mini LLM instance (Azure or OpenAI)
    """
    return get_llm(model_type="gpt4o-mini", temperature=temperature, **kwargs)


# Backward compatibility: expose common model names
def get_gpt4o(**kwargs) -> Union[AzureChatOpenAI, ChatOpenAI]:
    """Get GPT-4o (smart) model."""
    return get_smart_llm(**kwargs)


def get_gpt4o_mini(**kwargs) -> Union[AzureChatOpenAI, ChatOpenAI]:
    """Get GPT-4o-mini (fast) model."""
    return get_fast_llm(**kwargs)

