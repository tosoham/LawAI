"""
Request models for LawAI API
"""
from typing import Any, Dict, Optional
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
        description=(
            "Collection to search. Accepts either the short alias "
            "(bns, bnss, bsa, judgements) or the full collection name "
            "(bns_sections, bnss_sections, bsa_sections, sc_judgements). "
            "Omit to search across all collections."
        ),
        pattern="^(bns|bnss|bsa|judgements|bns_sections|bnss_sections|bsa_sections|sc_judgements)$"
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


class DraftDocumentRequest(BaseModel):
    """Request model for document drafting endpoint"""

    document_type: str = Field(
        ...,
        description="Type of document to draft",
        pattern="^(bail_application|petition|notice|agreement)$"
    )

    case_details: Dict[str, Any] = Field(
        ...,
        description="Case details used to populate the document"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_type": "bail_application",
                "case_details": {
                    "accused_name": "John Doe",
                    "fir_number": "CR-123/2024",
                    "sections": "BNS 103",
                    "facts": "First time offender, no criminal history"
                }
            }
        }


class ExportDocxRequest(BaseModel):
    """Request model for rendering document text as a .docx file"""

    content: str = Field(
        ...,
        description="Document text to render",
        min_length=1
    )

    filename: str = Field(
        default="document",
        description="Base filename; the .docx suffix is added if missing",
        max_length=200
    )

    title: Optional[str] = Field(
        None,
        description="Optional heading placed at the top of the document",
        max_length=300
    )

    include_disclaimer: bool = Field(
        default=True,
        description="Append the AI-generated content disclaimer"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "content": "IN THE COURT OF SESSIONS JUDGE\n\nBAIL APPLICATION...",
                "filename": "bail_application_rajesh_kumar",
                "title": "Bail Application"
            }
        }


class AnalyzeDocumentRequest(BaseModel):
    """Request model for document analysis endpoint"""

    document_text: str = Field(
        ...,
        description="Full text of the document to analyse",
        min_length=1
    )

    analysis_type: str = Field(
        default="full",
        description="Type of analysis to perform",
        pattern="^(summary|risks|key_clauses|full)$"
    )

    document_type: str = Field(
        default="other",
        description="Type of document being analysed",
        pattern="^(contract|agreement|notice|petition|other)$"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_text": "This Rental Agreement is made on...",
                "analysis_type": "risks",
                "document_type": "agreement"
            }
        }

