"""
Live Case Law Tools

Reach authentic judiciary sources at query time. The ChromaDB corpus holds the
complete 2023 codes and a curated set of landmark judgements, but it is a
snapshot: anything decided after ingestion is invisible to it. These tools
cover that gap.

Results are *retrieved*, not curated. Everything returned carries the court,
date and source URL so the answer can be attributed, and callers should present
live material as such rather than blending it into the verified corpus.
"""

import asyncio
from typing import Any

from services.judiciary_service import COURTS, JudiciaryService, get_judiciary_service

from .base_tool import BaseTool, ToolParameter, ToolResult


class LiveCaseLawSearchTool(BaseTool):
    """Search current Indian case law, including judgements newer than the corpus."""

    def __init__(self, judiciary_service: JudiciaryService | None = None):
        super().__init__()
        self.judiciary_service = judiciary_service or get_judiciary_service()
        self.examples = [
            "Recent Supreme Court judgments on anticipatory bail in 2026",
            "Latest rulings interpreting the Bharatiya Nyaya Sanhita",
            "High Court decisions on default bail this year",
        ]

    @property
    def name(self) -> str:
        return "live_case_law_search"

    @property
    def description(self) -> str:
        return (
            "Search authentic Indian judiciary sources for current case law. Use this "
            "for recent or very specific judgements that the local legal corpus (the "
            "2023 codes plus landmark judgements) will not contain."
        )

    @property
    def parameters(self) -> dict[str, ToolParameter]:
        return {
            "query": ToolParameter(
                name="query",
                type="string",
                description="Search terms, e.g. 'anticipatory bail economic offences'",
                required=True,
            ),
            "court": ToolParameter(
                name="court",
                type="string",
                description=f"Which courts to search: {', '.join(sorted(COURTS))}",
                required=False,
                default="supremecourt",
            ),
            "from_date": ToolParameter(
                name="from_date",
                type="string",
                description="Earliest judgement date, as YYYY-MM-DD or a year",
                required=False,
            ),
            "to_date": ToolParameter(
                name="to_date",
                type="string",
                description="Latest judgement date, as YYYY-MM-DD or a year",
                required=False,
            ),
            "limit": ToolParameter(
                name="limit",
                type="integer",
                description="Maximum results to return (1-20)",
                required=False,
                default=5,
            ),
        }

    async def execute(self, **kwargs) -> ToolResult:
        """Search live case law without blocking the event loop."""
        try:
            query = kwargs.get("query")
            if not query:
                return ToolResult(success=False, error="query is required")

            result = await asyncio.to_thread(
                self.judiciary_service.search_case_law,
                query=query,
                court=kwargs.get("court") or "supremecourt",
                from_date=kwargs.get("from_date"),
                to_date=kwargs.get("to_date"),
                limit=int(kwargs.get("limit") or 5),
            )

            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error", "search failed"))

            return ToolResult(
                success=True,
                data=result,
                metadata={
                    "tool": self.name,
                    "num_results": result.get("num_results", 0),
                    "live": True,
                },
            )

        except Exception as e:
            self.logger.error(f"Live case law search failed: {e}", exc_info=True)
            return ToolResult(success=False, error=f"Live case law search failed: {e!s}")


class FetchJudgmentTool(BaseTool):
    """Retrieve the text of one judgement located by a live search."""

    def __init__(self, judiciary_service: JudiciaryService | None = None):
        super().__init__()
        self.judiciary_service = judiciary_service or get_judiciary_service()
        self.examples = ["Fetch the full text of judgement 60022179"]

    @property
    def name(self) -> str:
        return "fetch_judgment"

    @property
    def description(self) -> str:
        return (
            "Retrieve the text of a specific judgement using the doc_id returned by "
            "live_case_law_search. Use this after searching, to read what a judgement "
            "actually held before relying on it."
        )

    @property
    def parameters(self) -> dict[str, ToolParameter]:
        return {
            "doc_id": ToolParameter(
                name="doc_id",
                type="string",
                description="Document id from live_case_law_search results",
                required=True,
            ),
            "max_chars": ToolParameter(
                name="max_chars",
                type="integer",
                description="Maximum characters of judgement text to return",
                required=False,
                default=8000,
            ),
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            doc_id = kwargs.get("doc_id")
            if not doc_id:
                return ToolResult(success=False, error="doc_id is required")

            result = await asyncio.to_thread(
                self.judiciary_service.fetch_judgment,
                doc_id=str(doc_id),
                max_chars=int(kwargs.get("max_chars") or 8000),
            )

            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error", "fetch failed"))

            return ToolResult(
                success=True,
                data=result,
                metadata={"tool": self.name, "doc_id": str(doc_id), "live": True},
            )

        except Exception as e:
            self.logger.error(f"Fetching judgement failed: {e}", exc_info=True)
            return ToolResult(success=False, error=f"Fetching judgement failed: {e!s}")


def build_openai_tool_schemas() -> list[dict[str, Any]]:
    """
    Describe the live tools in the format the chat-completions API expects.

    Kept next to the tools so the schema and the implementation stay in step.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "live_case_law_search",
                "description": (
                    "Search authentic Indian judiciary sources for current case law. "
                    "Use when the question concerns recent, latest or dated judgements "
                    "that the local corpus of 2023 codes and landmark cases will not have."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search terms describing the legal issue",
                        },
                        "court": {
                            "type": "string",
                            "enum": sorted(COURTS),
                            "description": "Which courts to search",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Earliest date, YYYY-MM-DD or a year such as 2025",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "Latest date, YYYY-MM-DD or a year",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results (1-20)",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_judgment",
                "description": (
                    "Retrieve the text of a specific judgement by the doc_id returned "
                    "from live_case_law_search, to check what it actually held."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {
                            "type": "string",
                            "description": "Document id from live_case_law_search",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters of text to return",
                        },
                    },
                    "required": ["doc_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_local_corpus",
                "description": (
                    "Search the verified local corpus: the full text of the Bharatiya "
                    "Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya "
                    "Sakshya Adhiniyam (2023), plus landmark Supreme Court judgements. "
                    "Prefer this for settled law and statutory provisions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to look for in the codes or landmark cases",
                        },
                        "collection": {
                            "type": "string",
                            "enum": ["bns_sections", "bnss_sections",
                                     "bsa_sections", "sc_judgements"],
                            "description": "Which collection to search; omit to search all",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]
