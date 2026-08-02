"""
Analyze Document Tool

Analyze uploaded legal documents (PDF/text) for summaries, risks, and key clauses.
"""

import asyncio
from typing import Dict
from .base_tool import BaseTool, ToolParameter, ToolResult
from services.llm_service import LLMService


class AnalyzeDocumentTool(BaseTool):
    """
    Tool for analyzing legal documents.
    
    Provides document summaries, risk analysis, and key clause extraction.
    Supports various document types including contracts, agreements, and legal notices.
    """
    
    def __init__(self, llm_service: LLMService):
        """
        Initialize analyze document tool.
        
        Args:
            llm_service: LLM service instance
        """
        super().__init__()
        self.llm_service = llm_service
        self.examples = [
            "Analyze rental agreement for risks",
            "Summarize employment contract",
            "Extract key clauses from partnership deed",
            "Identify termination clauses in service agreement"
        ]
    
    @property
    def name(self) -> str:
        return "analyze_document"
    
    @property
    def description(self) -> str:
        return "Analyze legal documents for summaries, risks, and key clauses"
    
    @property
    def parameters(self) -> Dict[str, ToolParameter]:
        return {
            "document_text": ToolParameter(
                name="document_text",
                type="string",
                description="Full text of the document to analyze",
                required=True
            ),
            "analysis_type": ToolParameter(
                name="analysis_type",
                type="string",
                description="Type of analysis (summary|risks|key_clauses|full)",
                required=False,
                default="full"
            ),
            "document_type": ToolParameter(
                name="document_type",
                type="string",
                description="Type of document (contract|agreement|notice|petition|other)",
                required=False,
                default="other"
            )
        }
    
    def _create_summary_prompt(self, document_text: str, document_type: str) -> str:
        """Create prompt for document summary"""
        return f"""You are a legal document analyst. Provide a comprehensive summary of the following {document_type}.

DOCUMENT:
{document_text}

INSTRUCTIONS:
1. Provide a clear, concise summary (200-300 words)
2. Identify the parties involved
3. State the main purpose and subject matter
4. Highlight key obligations and rights
5. Note any important dates or deadlines
6. Use professional legal language

SUMMARY:"""
    
    def _create_risk_analysis_prompt(self, document_text: str, document_type: str) -> str:
        """Create prompt for risk analysis"""
        return f"""You are a legal risk analyst. Analyze the following {document_type} for potential risks and concerns.

DOCUMENT:
{document_text}

INSTRUCTIONS:
1. Identify all potential legal risks and liabilities
2. Highlight unfavorable clauses or terms
3. Point out missing protections or safeguards
4. Note any ambiguous or unclear provisions
5. Flag unusual or one-sided terms
6. Assess termination and penalty clauses
7. Rate each risk as HIGH, MEDIUM, or LOW
8. Provide specific recommendations

RISK ANALYSIS:"""
    
    def _create_key_clauses_prompt(self, document_text: str, document_type: str) -> str:
        """Create prompt for key clause extraction"""
        return f"""You are a legal document analyst. Extract and explain the key clauses from the following {document_type}.

DOCUMENT:
{document_text}

INSTRUCTIONS:
1. Identify all critical clauses and provisions
2. Extract exact text of each key clause
3. Explain the legal significance of each clause
4. Categorize clauses (e.g., payment, termination, liability, confidentiality)
5. Highlight any unusual or noteworthy provisions
6. Note interdependencies between clauses

KEY CLAUSES:"""
    
    def _create_full_analysis_prompt(self, document_text: str, document_type: str) -> str:
        """Create prompt for full document analysis"""
        return f"""You are an expert legal document analyst. Provide a comprehensive analysis of the following {document_type}.

DOCUMENT:
{document_text}

INSTRUCTIONS:
Provide a complete analysis with the following sections:

1. EXECUTIVE SUMMARY
   - Brief overview of the document
   - Parties involved
   - Main purpose and subject matter

2. KEY CLAUSES
   - Extract and explain critical provisions
   - Categorize by type (payment, termination, liability, etc.)
   - Note any unusual or significant terms

3. RISK ANALYSIS
   - Identify potential legal risks (HIGH/MEDIUM/LOW)
   - Highlight unfavorable or one-sided terms
   - Point out missing protections
   - Flag ambiguous provisions

4. OBLIGATIONS & RIGHTS
   - List obligations of each party
   - Outline rights and entitlements
   - Note conditions and contingencies

5. TERMINATION & REMEDIES
   - Termination conditions and procedures
   - Penalty clauses and consequences
   - Dispute resolution mechanisms

6. RECOMMENDATIONS
   - Suggested modifications or additions
   - Areas requiring clarification
   - Protective measures to consider

Use clear headings and bullet points. Be specific and cite relevant clauses.

COMPREHENSIVE ANALYSIS:"""
    
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute document analysis.
        
        Args:
            document_text: Text of document to analyze
            analysis_type: Type of analysis to perform
            document_type: Type of document
            
        Returns:
            ToolResult with analysis
        """
        try:
            document_text = kwargs.get("document_text")
            analysis_type = kwargs.get("analysis_type", "full")
            document_type = kwargs.get("document_type", "other")
            
            if not document_text:
                return ToolResult(
                    success=False,
                    error="document_text is required"
                )
            
            # Validate document length
            if len(document_text) < 100:
                return ToolResult(
                    success=False,
                    error="Document text is too short for meaningful analysis (minimum 100 characters)"
                )
            
            if len(document_text) > 50000:
                self.logger.warning(f"Document is very long ({len(document_text)} chars), truncating to 50000")
                document_text = document_text[:50000] + "\n\n[Document truncated for analysis]"
            
            self.logger.info(f"Analyzing {document_type} document: type={analysis_type}, length={len(document_text)}")
            
            # Create appropriate prompt based on analysis type
            if analysis_type == "summary":
                prompt = self._create_summary_prompt(document_text, document_type)
            elif analysis_type == "risks":
                prompt = self._create_risk_analysis_prompt(document_text, document_type)
            elif analysis_type == "key_clauses":
                prompt = self._create_key_clauses_prompt(document_text, document_type)
            else:  # full analysis
                prompt = self._create_full_analysis_prompt(document_text, document_type)
            
            # Generate analysis
            analysis = await asyncio.to_thread(self.llm_service.generate, prompt=prompt)
            
            # Format result
            result_data = {
                "analysis": analysis,
                "analysis_type": analysis_type,
                "document_type": document_type,
                "document_length": len(document_text),
                "disclaimer": "This is an AI-generated analysis for informational purposes only. Please consult a qualified lawyer for legal advice."
            }
            
            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "tool": self.name,
                    "analysis_type": analysis_type,
                    "document_type": document_type,
                    "analysis_length": len(analysis)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Document analysis failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Document analysis failed: {str(e)}"
            )

# Made with Bob
