"""
Unit tests for LLM Service
Tests IBM watsonx.ai integration and streaming functionality
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import os
from backend.services.llm_service import LLMService, llm_service


class TestLLMService:
    """Test suite for LLM Service"""
    
    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Mock environment variables for testing"""
        monkeypatch.setenv("IBM_WATSONX_API_KEY", "test_api_key")
        monkeypatch.setenv("IBM_WATSONX_PROJECT_ID", "test_project_id")
        monkeypatch.setenv("IBM_WATSONX_URL", "https://test.ibm.com")
        monkeypatch.setenv("IBM_WATSONX_MODEL", "ibm/granite-13b-chat-v2")
        monkeypatch.setenv("IBM_WATSONX_MAX_TOKENS", "2048")
        monkeypatch.setenv("IBM_WATSONX_TEMPERATURE", "0.7")
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_llm_service_initialization(self, mock_watsonx, mock_env_vars):
        """Test LLM service initializes correctly with credentials"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        # Create service
        service = LLMService()
        
        # Verify WatsonxLLM was called with correct parameters
        mock_watsonx.assert_called_once()
        call_kwargs = mock_watsonx.call_args[1]
        
        assert call_kwargs['model_id'] == "ibm/granite-13b-chat-v2"
        assert call_kwargs['url'] == "https://test.ibm.com"
        assert call_kwargs['apikey'] == "test_api_key"
        assert call_kwargs['project_id'] == "test_project_id"
        assert 'params' in call_kwargs
        assert call_kwargs['params']['max_new_tokens'] == 2048
        assert call_kwargs['params']['temperature'] == 0.7
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_llm_service_singleton(self, mock_watsonx, mock_env_vars):
        """Test that LLM service follows singleton pattern"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        service1 = LLMService()
        service2 = LLMService()
        
        # Should be the same instance
        assert service1 is service2
        
        # WatsonxLLM should only be initialized once
        assert mock_watsonx.call_count == 1
    
    def test_llm_service_missing_credentials(self, monkeypatch):
        """Test that service raises error when credentials are missing"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        # Clear environment variables
        monkeypatch.delenv("IBM_WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("IBM_WATSONX_PROJECT_ID", raising=False)
        monkeypatch.delenv("IBM_WATSONX_URL", raising=False)
        
        with pytest.raises(ValueError, match="Missing required IBM watsonx.ai credentials"):
            LLMService()
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_generate_basic(self, mock_watsonx, mock_env_vars):
        """Test basic text generation"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        # Mock LLM response
        mock_llm_instance = Mock()
        mock_llm_instance.invoke.return_value = "This is a test response"
        mock_watsonx.return_value = mock_llm_instance
        
        service = LLMService()
        response = service.generate("Test prompt")
        
        assert response == "This is a test response"
        mock_llm_instance.invoke.assert_called_once_with("Test prompt")
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_generate_with_kwargs(self, mock_watsonx, mock_env_vars):
        """Test generation with additional parameters"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        mock_llm_instance = Mock()
        mock_llm_instance.invoke.return_value = "Response with custom params"
        mock_watsonx.return_value = mock_llm_instance
        
        service = LLMService()
        response = service.generate("Test prompt", max_new_tokens=100, temperature=0.5)
        
        assert response == "Response with custom params"
        mock_llm_instance.invoke.assert_called_once_with(
            "Test prompt",
            max_new_tokens=100,
            temperature=0.5
        )
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_generate_error_handling(self, mock_watsonx, mock_env_vars):
        """Test error handling in generation"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        mock_llm_instance = Mock()
        mock_llm_instance.invoke.side_effect = Exception("API Error")
        mock_watsonx.return_value = mock_llm_instance
        
        service = LLMService()
        
        with pytest.raises(Exception, match="LLM generation error"):
            service.generate("Test prompt")
    
    @pytest.mark.asyncio
    @patch('backend.services.llm_service.WatsonxLLM')
    async def test_generate_stream(self, mock_watsonx, mock_env_vars):
        """Test streaming generation"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        # Mock streaming response
        mock_llm_instance = Mock()
        mock_llm_instance.stream.return_value = iter(["Hello", " ", "world", "!"])
        mock_watsonx.return_value = mock_llm_instance
        
        service = LLMService()
        
        # Collect streamed tokens
        tokens = []
        async for token in service.generate_stream("Test prompt"):
            tokens.append(token)
        
        assert tokens == ["Hello", " ", "world", "!"]
        mock_llm_instance.stream.assert_called_once_with("Test prompt")
    
    @pytest.mark.asyncio
    @patch('backend.services.llm_service.WatsonxLLM')
    async def test_generate_stream_error_handling(self, mock_watsonx, mock_env_vars):
        """Test error handling in streaming"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        mock_llm_instance = Mock()
        mock_llm_instance.stream.side_effect = Exception("Streaming error")
        mock_watsonx.return_value = mock_llm_instance
        
        service = LLMService()
        
        with pytest.raises(Exception, match="LLM streaming error"):
            async for _ in service.generate_stream("Test prompt"):
                pass
    
    @patch('backend.services.llm_service.WatsonxLLM')
    def test_get_model_info(self, mock_watsonx, mock_env_vars):
        """Test getting model information"""
        # Reset singleton
        LLMService._instance = None
        LLMService._llm = None
        
        service = LLMService()
        info = service.get_model_info()
        
        assert info['model_id'] == "ibm/granite-13b-chat-v2"
        assert info['max_tokens'] == 2048
        assert info['temperature'] == 0.7
        assert info['url'] == "https://test.ibm.com"


class TestGlobalLLMService:
    """Test the global llm_service instance"""
    
    def test_global_instance_exists(self):
        """Test that global llm_service instance is created"""
        from backend.services.llm_service import llm_service
        assert llm_service is not None
        assert isinstance(llm_service, LLMService)

# Made with Bob
