"""
Response models for LawAI API
"""
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    """Source citation model"""

    title: str = Field(..., description="Source title")
    content: str = Field(..., description="Relevant content excerpt")
    section: str | None = Field(None, description="Section/article number")
    score: float | None = Field(None, description="Relevance score")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""

    response: str = Field(..., description="Generated response text")
    sources: list[Source] | None = Field(
        None,
        description="Sources used for response"
    )
    model: str = Field(..., description="Model used for generation")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_schema_extra={
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
        })


class RAGSearchResponse(BaseModel):
    """Response model for RAG search endpoint"""

    query: str = Field(..., description="Original search query")
    results: list[Source] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total number of results")
    collection: str | None = Field(None, description="Collection searched")

    model_config = ConfigDict(json_schema_extra={
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
        })


class DraftDocumentResponse(BaseModel):
    """Response model for document drafting endpoint"""

    success: bool = Field(..., description="Whether drafting succeeded")
    document: str | None = Field(None, description="The drafted document text")
    document_type: str | None = Field(None, description="Type of document drafted")
    case_details: dict[str, Any] | None = Field(None, description="Case details used")
    disclaimer: str | None = Field(None, description="AI-generated content disclaimer")
    error: str | None = Field(None, description="Error message if drafting failed")


class AnalyzeDocumentResponse(BaseModel):
    """Response model for document analysis endpoint"""

    success: bool = Field(..., description="Whether analysis succeeded")
    analysis: str | None = Field(None, description="Analysis output")
    analysis_type: str | None = Field(None, description="Type of analysis performed")
    document_type: str | None = Field(None, description="Type of document analysed")
    document_length: int | None = Field(None, description="Length of analysed text")
    disclaimer: str | None = Field(None, description="AI-generated content disclaimer")
    error: str | None = Field(None, description="Error message if analysis failed")


class DocumentTemplate(BaseModel):
    """A single document template offered by the drafting tool"""

    type: str = Field(..., description="Template identifier used in draft requests")
    name: str = Field(..., description="Human-readable template name")
    description: str = Field(..., description="What the template is for")
    required_fields: list[str] = Field(
        default_factory=list,
        description="Case-detail keys the template expects"
    )


class DocumentTemplatesResponse(BaseModel):
    """Response model listing the available document templates"""

    templates: list[DocumentTemplate] = Field(..., description="Available templates")


class ErrorResponse(BaseModel):
    """Error response model"""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: str | None = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "error": "ValidationError",
                "message": "Invalid request parameters",
                "details": "Field 'message' is required",
                "timestamp": "2024-01-01T12:00:00"
            }
        })


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    model: str = Field(..., description="LLM model in use")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "model": "gpt-4o-mini",
                "timestamp": "2024-01-01T12:00:00"
            }
        })


class ClaimSourceResponse(BaseModel):
    """One citation on a claim, with what it points at."""

    ref: str = Field(..., description="Section key, judgement id, doctrine id or URL")
    kind: str = Field(..., description="section | judgement | doctrine | live | unknown")


class PositionResponse(BaseModel):
    """One side of a contested question."""

    summary: str = Field(..., description="What this line of authority holds")
    authority: list[str] = Field(default_factory=list, description="Cases supporting it")


class ClaimResponse(BaseModel):
    """
    One assertion, with the kind of assertion it is.

    The epistemic class is the point of this shape. A client that renders every
    claim identically has thrown away the only thing distinguishing enacted
    text from the model's reasoning, which is the difference this system exists
    to preserve.
    """

    text: str = Field(..., description="The claim as it will be read")
    epistemic_class: str = Field(
        ...,
        description=(
            "statute | classification | holding | interpretation | contested | "
            "inference. Never 'unsupported': those are removed before the answer "
            "is returned."
        ),
    )
    sources: list[ClaimSourceResponse] = Field(default_factory=list)
    verbatim_span: str | None = Field(
        None, description="For a statute claim, the exact words taken from the section"
    )
    positions: list[PositionResponse] = Field(
        default_factory=list, description="For a contested claim, the competing readings"
    )


class ClaimVerdictResponse(BaseModel):
    """What the verifier found for one claim synthesis emitted."""

    index: int
    verified: bool
    original_class: str = Field(..., description="The class synthesis asserted")
    reason: str = Field("", description="Why it failed, if it did")


class AnswerMetricsResponse(BaseModel):
    """Grounding measured, rather than asserted."""

    claims: int
    by_class: dict[str, int]
    grounding_rate: float
    verbatim_fidelity: float
    quoted_statute_claims: int
    unsupported: int = Field(..., description="Claims the verifier rejected and removed")
    unattributed_interpretation: int
    inference_share: float
    source_mix: dict[str, int]
    abstained: bool
    clean: bool = Field(..., description="Nothing had to be removed from this answer")


class GroundedAnswerResponse(BaseModel):
    """
    A verified answer and the chain that makes it defensible afterwards.

    ``sources`` and ``graph_context`` stay separate for the same reason
    ``sources`` and ``live_sources`` do elsewhere: one was retrieved by
    relevance and the other reached by an edge, and a client that merges them
    is asserting something the API did not.
    """

    query: str
    answer: str = Field(..., description="Prose rendered from the verified claims")
    abstained: bool = Field(
        ..., description="True when nothing could be supported and no answer is given"
    )
    claims: list[ClaimResponse] = Field(default_factory=list)
    verdicts: list[ClaimVerdictResponse] = Field(default_factory=list)
    metrics: AnswerMetricsResponse
    sources: list[dict[str, Any]] = Field(default_factory=list)
    graph_context: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Retrieved ids, graph edges traversed, generation attempts and per-claim "
            "verdicts. Not a debugging aid: it is what makes an answer defensible "
            "after the fact."
        ),
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
