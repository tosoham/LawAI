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
                "model": "ibm/granite-13b-chat-v2",
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


class DocumentAnalysisResponse(BaseModel):
    """Response model for document analysis endpoint"""
    
    file_name: str = Field(..., description="Analyzed file name")
    analysis_type: str = Field(..., description="Type of analysis performed")
    summary: str = Field(..., description="Analysis summary")
    key_points: List[str] = Field(..., description="Key points identified")
    risks: Optional[List[str]] = Field(None, description="Identified risks")
    recommendations: Optional[List[str]] = Field(None, description="Recommendations")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_name": "rental_agreement.pdf",
                "analysis_type": "risk",
                "summary": "Standard rental agreement with some concerning clauses",
                "key_points": [
                    "11-month lease term",
                    "Security deposit: 3 months rent"
                ],
                "risks": [
                    "Broad indemnity clause in favor of landlord",
                    "Unilateral termination rights"
                ],
                "recommendations": [
                    "Negotiate indemnity clause",
                    "Add notice period for termination"
                ]
            }
        }


class DraftDocumentResponse(BaseModel):
    """Response model for document drafting endpoint"""
    
    document_type: str = Field(..., description="Type of document drafted")
    file_path: str = Field(..., description="Path to generated document")
    format: str = Field(..., description="Document format")
    preview: Optional[str] = Field(None, description="Text preview of document")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "bail_application",
                "file_path": "/tmp/bail_application_123.docx",
                "format": "docx",
                "preview": "IN THE COURT OF...\n\nBail Application under Section 479 BNSS..."
            }
        }


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
                "model": "ibm/granite-13b-chat-v2",
                "timestamp": "2024-01-01T12:00:00"
            }
        }

# Made with Bob
