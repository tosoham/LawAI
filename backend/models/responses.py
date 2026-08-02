"""
Response models for LawAI API
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class Source(BaseModel):
    """Source citation model"""
    
    title: str = Field(..., description="Source title")
    content: str = Field(..., description="Relevant content excerpt")
    section: Optional[str] = Field(None, description="Section/article number")
    score: Optional[float] = Field(None, description="Relevance score")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    
    response: str = Field(..., description="Generated response text")
    sources: Optional[List[Source]] = Field(
        None,
        description="Sources used for response"
    )
    model: str = Field(..., description="Model used for generation")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "Under BNSS Section 479, anticipatory bail can be granted...",
                "sources": [
                    {
                        "title": "BNSS Section 479",
                        "content": "When any person has reason to believe...",
                        "section": "479",
                        "score": 0.95
                    }
                ],
                "model": "gpt-4o-mini",
                "timestamp": "2024-01-01T12:00:00"
            }
        }


class RAGSearchResponse(BaseModel):
    """Response model for RAG search endpoint"""
    
    query: str = Field(..., description="Original search query")
    results: List[Source] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total number of results")
    collection: Optional[str] = Field(None, description="Collection searched")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "anticipatory bail provisions",
                "results": [
                    {
                        "title": "BNSS Section 479",
                        "content": "Anticipatory bail provisions...",
                        "section": "479",
                        "score": 0.95
                    }
                ],
                "total_results": 5,
                "collection": "bnss"
            }
        }


class DraftDocumentResponse(BaseModel):
    """Response model for document drafting endpoint"""

    success: bool = Field(..., description="Whether drafting succeeded")
    document: Optional[str] = Field(None, description="The drafted document text")
    document_type: Optional[str] = Field(None, description="Type of document drafted")
    case_details: Optional[Dict[str, Any]] = Field(None, description="Case details used")
    disclaimer: Optional[str] = Field(None, description="AI-generated content disclaimer")
    error: Optional[str] = Field(None, description="Error message if drafting failed")


class AnalyzeDocumentResponse(BaseModel):
    """Response model for document analysis endpoint"""

    success: bool = Field(..., description="Whether analysis succeeded")
    analysis: Optional[str] = Field(None, description="Analysis output")
    analysis_type: Optional[str] = Field(None, description="Type of analysis performed")
    document_type: Optional[str] = Field(None, description="Type of document analysed")
    document_length: Optional[int] = Field(None, description="Length of analysed text")
    disclaimer: Optional[str] = Field(None, description="AI-generated content disclaimer")
    error: Optional[str] = Field(None, description="Error message if analysis failed")


class DocumentTemplate(BaseModel):
    """A single document template offered by the drafting tool"""

    type: str = Field(..., description="Template identifier used in draft requests")
    name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="What the template is for")
    required_fields: List[str] = Field(
        default_factory=list,
        description="Case-detail keys the template expects"
    )


class DocumentTemplatesResponse(BaseModel):
    """Response model listing the available document templates"""

    templates: List[DocumentTemplate] = Field(..., description="Available templates")


class ErrorResponse(BaseModel):
    """Error response model"""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid request parameters",
                "details": "Field 'message' is required",
                "timestamp": "2024-01-01T12:00:00"
            }
        }


class HealthResponse(BaseModel):
    """Health check response model"""
    
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    model: str = Field(..., description="LLM model in use")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "model": "gpt-4o-mini",
                "timestamp": "2024-01-01T12:00:00"
            }
        }
