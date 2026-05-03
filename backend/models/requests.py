"""
Request models for LawAI API
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    
    message: str = Field(
        ...,
        description="User message/query",
        min_length=1,
        max_length=5000
    )
    
    context: Optional[str] = Field(
        None,
        description="Optional context for the conversation",
        max_length=10000
    )
    
    stream: bool = Field(
        default=True,
        description="Whether to stream the response"
    )
    
    max_tokens: Optional[int] = Field(
        None,
        description="Maximum tokens to generate",
        ge=1,
        le=4096
    )
    
    temperature: Optional[float] = Field(
        None,
        description="Sampling temperature",
        ge=0.0,
        le=2.0
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "What are the provisions for bail under BNSS?",
                "context": "Client arrested under BNS Section 103",
                "stream": True
            }
        }


class RAGSearchRequest(BaseModel):
    """Request model for RAG search endpoint"""
    
    query: str = Field(
        ...,
        description="Search query",
        min_length=1,
        max_length=1000
    )
    
    collection: Optional[str] = Field(
        None,
        description="Specific collection to search (bns, bnss, bsa, judgements)",
        pattern="^(bns|bnss|bsa|judgements)$"
    )
    
    top_k: int = Field(
        default=5,
        description="Number of results to return",
        ge=1,
        le=20
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "anticipatory bail provisions",
                "collection": "bnss",
                "top_k": 5
            }
        }


class DocumentAnalysisRequest(BaseModel):
    """Request model for document analysis endpoint"""
    
    file_path: str = Field(
        ...,
        description="Path to uploaded document"
    )
    
    analysis_type: str = Field(
        default="general",
        description="Type of analysis to perform",
        pattern="^(general|risk|summary|clauses)$"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "/tmp/rental_agreement.pdf",
                "analysis_type": "risk"
            }
        }


class DraftDocumentRequest(BaseModel):
    """Request model for document drafting endpoint"""
    
    document_type: str = Field(
        ...,
        description="Type of document to draft",
        pattern="^(bail_application|petition|notice|agreement)$"
    )
    
    details: dict = Field(
        ...,
        description="Details required for drafting"
    )
    
    format: str = Field(
        default="docx",
        description="Output format",
        pattern="^(docx|pdf|txt)$"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "bail_application",
                "details": {
                    "accused_name": "John Doe",
                    "case_number": "CR-123/2024",
                    "sections": ["BNS 103"],
                    "grounds": "First time offender, no criminal history"
                },
                "format": "docx"
            }
        }

# Made with Bob
