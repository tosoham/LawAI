"""
Chat Tool

General legal Q&A without RAG search - direct LLM interaction.
"""

from typing import Dict, List, Optional
from .base_tool import BaseTool, ToolParameter, ToolResult
from services.llm_service import LLMService


class ChatTool(BaseTool):
    """
    Tool for general legal Q&A using LLM directly.
    
    Provides conversational legal assistance without RAG retrieval.
    Useful for general legal concepts, explanations, and discussions.
    """
    
    def __init__(self, llm_service: LLMService):
        """
        Initialize chat tool.
        
        Args:
            llm_service: LLM service instance
        """
        super().__init__()
        self.llm_service = llm_service
        self.examples = [
            "Explain the concept of mens rea in criminal law",
            "What is the difference between cognizable and non-cognizable offenses?",
            "Explain the doctrine of res judicata",
            "What are the essential elements of a valid contract?"
        ]
    
    @property
    def name(self) -> str:
        return "chat"
    
    @property
    def description(self) -> str:
        return "General legal Q&A and explanations without document retrieval"
    
    @property
    def parameters(self) -> Dict[str, ToolParameter]:
        return {
            "message": ToolParameter(
                name="message",
                type="string",
                description="User's question or message",
                required=True
            ),
            "context": ToolParameter(
                name="context",
                type="list",
                description="Optional conversation context (previous messages)",
                required=False,
                default=[]
            )
        }
    
    def _create_prompt(self, message: str, context: Optional[List[Dict]] = None) -> str:
        """
        Create prompt for LLM with message and optional context.
        
        Args:
            message: User's message
            context: Optional conversation history
            
        Returns:
            Formatted prompt
        """
        prompt_parts = [
            "You are a legal AI assistant specializing in Indian law.",
            "Provide clear, accurate legal information and explanations.",
            "Use proper legal terminology and cite relevant laws when applicable.",
            ""
        ]
        
        # Add conversation context if provided
        if context:
            prompt_parts.append("CONVERSATION HISTORY:")
            for msg in context[-5:]:  # Last 5 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role.upper()}: {content}")
            prompt_parts.append("")
        
        # Add current message
        prompt_parts.extend([
            "USER QUESTION:",
            message,
            "",
            "INSTRUCTIONS:",
            "1. Provide a clear, accurate answer based on Indian law",
            "2. Use proper legal terminology and citation format",
            "3. If you're unsure, acknowledge limitations",
            "4. Include a disclaimer that this is AI-generated legal information",
            "",
            "ANSWER:"
        ])
        
        return "\n".join(prompt_parts)
    
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute chat interaction.
        
        Args:
            message: User's message
            context: Optional conversation context
            
        Returns:
            ToolResult with AI response
        """
        try:
            message = kwargs.get("message")
            context = kwargs.get("context", [])
            
            if not message:
                return ToolResult(
                    success=False,
                    error="Message is required"
                )
            
            self.logger.info(f"Chat: message='{message[:50]}...', context_length={len(context)}")
            
            # Create prompt
            prompt = self._create_prompt(message, context)
            
            # Generate response
            response = self.llm_service.generate(prompt=prompt)
            
            # Add disclaimer
            answer = response + "\n\n**DISCLAIMER**: This is AI-generated legal information for educational purposes only. Please consult a qualified lawyer for legal advice specific to your situation."
            
            return ToolResult(
                success=True,
                data={
                    "answer": answer,
                    "message": message,
                    "has_context": len(context) > 0
                },
                metadata={
                    "tool": self.name,
                    "context_length": len(context)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Chat failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Chat failed: {str(e)}"
            )

# Made with Bob
