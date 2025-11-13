"""
AI Factory - Centralized AI API Routing

Single source of truth for all AI API calls.
Uses Azure OpenAI with proper configuration.
"""

import logging
from typing import Optional, Union
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from config import get_settings

logger = logging.getLogger(__name__)


class AIFactory:
    """
    Factory for creating AI model instances.
    Centralizes all AI API configuration and routing.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._validate_config()
    
    def _validate_config(self):
        """Validate that AI configuration is present"""
        if not self.settings.azure_openai_key and not self.settings.openai_api_key:
            raise ValueError(
                "No AI API key configured. "
                "Please set AZURE_OPENAI_KEY or OPENAI_API_KEY in environment."
            )
    
    def get_smart_llm(
        self,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Union[AzureChatOpenAI, ChatOpenAI]:
        """
        Get GPT-4o (smart model) for complex reasoning tasks.
        
        Use for:
        - Content extraction
        - Complex analysis
        - Strategic decisions
        
        Args:
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            **kwargs: Additional arguments
            
        Returns:
            Configured LLM instance (Azure or OpenAI)
        """
        return self._create_llm(
            model_type="gpt-4o",
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def get_fast_llm(
        self,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Union[AzureChatOpenAI, ChatOpenAI]:
        """
        Get GPT-4o-mini (fast model) for simple tasks.
        
        Use for:
        - Simple classification
        - Quick filtering
        - Basic extraction
        
        Args:
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            **kwargs: Additional arguments
            
        Returns:
            Configured LLM instance (Azure or OpenAI)
        """
        return self._create_llm(
            model_type="gpt-4o-mini",
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def _create_llm(
        self,
        model_type: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Union[AzureChatOpenAI, ChatOpenAI]:
        """
        Create LLM instance with Azure OpenAI (preferred) or OpenAI fallback.
        
        Args:
            model_type: "gpt-4o" or "gpt-4o-mini"
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional arguments
            
        Returns:
            Configured LLM instance
        """
        # Try Azure OpenAI first
        if self.settings.azure_openai_key:
            try:
                deployment_map = {
                    "gpt-4o": self.settings.azure_deployment_gpt4o,
                    "gpt-4o-mini": self.settings.azure_deployment_gpt4o_mini,
                }
                
                deployment_name = deployment_map.get(
                    model_type,
                    self.settings.azure_deployment_gpt4o
                )
                
                llm_config = {
                    "azure_deployment": deployment_name,
                    "api_key": self.settings.azure_openai_key,
                    "azure_endpoint": self.settings.azure_openai_endpoint,
                    "api_version": self.settings.azure_openai_api_version,
                    "temperature": temperature,
                    **kwargs
                }
                
                if max_tokens is not None:
                    llm_config["max_tokens"] = max_tokens
                
                logger.debug(
                    f"Using Azure OpenAI: {deployment_name} "
                    f"(endpoint: {self.settings.azure_openai_endpoint})"
                )
                
                return AzureChatOpenAI(**llm_config)
                
            except Exception as e:
                logger.warning(f"Azure OpenAI failed: {e}, falling back to OpenAI")
        
        # Fallback to standard OpenAI
        if not self.settings.openai_api_key:
            raise ValueError(
                "Neither Azure OpenAI nor OpenAI API key configured. "
                "Please set AZURE_OPENAI_KEY or OPENAI_API_KEY."
            )
        
        model_map = {
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
        }
        
        model_name = model_map.get(model_type, "gpt-4o")
        
        llm_config = {
            "model": model_name,
            "api_key": self.settings.openai_api_key,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens is not None:
            llm_config["max_tokens"] = max_tokens
        
        logger.debug(f"Using OpenAI: {model_name}")
        
        return ChatOpenAI(**llm_config)


# Global factory instance (singleton)
_factory: Optional[AIFactory] = None


def get_ai_factory() -> AIFactory:
    """Get or create the global AI factory instance"""
    global _factory
    if _factory is None:
        _factory = AIFactory()
    return _factory

