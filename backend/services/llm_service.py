"""
IBM watsonx.ai LLM Service
Singleton service for IBM Granite model integration via langchain-ibm
"""
import os
import logging
from typing import Optional, AsyncIterator
from langchain_ibm import WatsonxLLM
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class LLMService:
    """Singleton service for IBM watsonx.ai LLM operations"""
    
    _instance: Optional['LLMService'] = None
    _llm: Optional[WatsonxLLM] = None
    
    def __new__(cls):
        """Ensure singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize LLM service with IBM watsonx.ai credentials"""
        if self._llm is None:
            try:
                # Get credentials from environment
                api_key = os.getenv("IBM_WATSONX_API_KEY")
                project_id = os.getenv("IBM_WATSONX_PROJECT_ID")
                url = os.getenv("IBM_WATSONX_URL")
                model_id = os.getenv("IBM_WATSONX_MODEL", "ibm/granite-13b-chat-v2")
                max_tokens = int(os.getenv("IBM_WATSONX_MAX_TOKENS", "2048"))
                temperature = float(os.getenv("IBM_WATSONX_TEMPERATURE", "0.7"))
                
                # Validate required credentials
                if not all([api_key, project_id, url]):
                    raise ValueError(
                        "Missing required IBM watsonx.ai credentials. "
                        "Check IBM_WATSONX_API_KEY, IBM_WATSONX_PROJECT_ID, and IBM_WATSONX_URL in .env"
                    )
                
                # Initialize WatsonxLLM
                self._llm = WatsonxLLM(
                    model_id=model_id,
                    url=url,
                    apikey=api_key,
                    project_id=project_id,
                    params={
                        "max_new_tokens": max_tokens,
                        "temperature": temperature,
                        "decoding_method": "greedy",
                        "repetition_penalty": 1.0,
                    }
                )
                
                logger.info(f"LLM Service initialized with model: {model_id}")
                
            except Exception as e:
                logger.error(f"Failed to initialize LLM service: {str(e)}")
                raise
    
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate completion for a prompt
        
        Args:
            prompt: Input prompt text
            **kwargs: Additional parameters for generation
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If generation fails
        """
        try:
            logger.debug(f"Generating completion for prompt: {prompt[:100]}...")
            response = self._llm.invoke(prompt, **kwargs)
            logger.debug(f"Generated response: {response[:100]}...")
            return response
            
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise Exception(f"LLM generation error: {str(e)}")
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """
        Generate streaming completion for a prompt
        
        Args:
            prompt: Input prompt text
            **kwargs: Additional parameters for generation
            
        Yields:
            Token strings as they are generated
            
        Raises:
            Exception: If streaming fails
        """
        try:
            logger.debug(f"Starting streaming generation for prompt: {prompt[:100]}...")
            
            # Use stream method from langchain-ibm
            for chunk in self._llm.stream(prompt, **kwargs):
                if chunk:
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Streaming generation failed: {str(e)}")
            raise Exception(f"LLM streaming error: {str(e)}")
    
    def get_model_info(self) -> dict:
        """
        Get information about the current model
        
        Returns:
            Dictionary with model configuration
        """
        return {
            "model_id": os.getenv("IBM_WATSONX_MODEL", "ibm/granite-13b-chat-v2"),
            "max_tokens": int(os.getenv("IBM_WATSONX_MAX_TOKENS", "2048")),
            "temperature": float(os.getenv("IBM_WATSONX_TEMPERATURE", "0.7")),
            "url": os.getenv("IBM_WATSONX_URL"),
        }


# Global singleton instance
llm_service = LLMService()

# Made with Bob
