"""
Intent Classifier for LawAI Agent

Classifies user queries into appropriate intents for tool routing.
"""

import logging
import re
from typing import ClassVar

from agents.state import IntentType
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Classifies user queries into intents using keyword matching and LLM fallback.
    """

    # Keyword patterns for each intent
    INTENT_PATTERNS: ClassVar[dict] = {
        IntentType.RAG_SEARCH: [
            r'\b(what|explain|tell|describe|define|provisions?|sections?|law|legal|statute|act)\b',
            r'\b(bns|bnss|bsa|ipc|crpc|indian penal code|criminal procedure)\b',
            r'\b(case law|judgement|ruling|precedent|supreme court|sc)\b',
            r'\b(search|find|look up|query)\b',
        ],
        IntentType.DRAFT_DOCUMENT: [
            r'\b(draft|write|create|generate|prepare)\b',
            r'\b(application|petition|affidavit|notice|letter|document)\b',
            r'\b(bail|anticipatory bail|regular bail)\b',
            r'\b(complaint|fir|chargesheet)\b',
        ],
        IntentType.ANALYZE_DOCUMENT: [
            r'\b(analyze|review|check|examine|assess|evaluate)\b',
            r'\b(document|contract|agreement|deed|will)\b',
            r'\b(upload|attached|file|pdf)\b',
            r'\b(risks?|issues?|problems?|clauses?)\b',
        ],
        IntentType.CHAT: [
            r'\b(hello|hi|hey|greetings)\b',
            r'\b(how are you|what can you do|help|assist)\b',
            r'\b(thank|thanks|appreciate)\b',
        ],
        IntentType.LIVE_RESEARCH: [
            r'\b(case ?laws?|judgements?|judgments?|rulings?|precedents?|verdicts?|orders?)\b',
            r'\b(supreme court|high court|sc|hc|bench|tribunal)\b',
            r'\b(held|decided|pronounce[ds]?|observed|delivered)\b',
        ],
    }

    # The corpus is a snapshot, so only questions that actually reach past it
    # justify a live lookup: an explicit recency word, or a year at or after the
    # 2023 codes. Without one of these, settled law is answered from the corpus.
    RECENCY_TRIGGER = re.compile(
        r'\b(recent(ly)?|latest|current(ly)?|new(est)?|this (year|month|week)|'
        r'last (year|month|few years)|nowadays|these days|up ?to ?date|'
        r'as of|since \d{4}|202[3-9]|20[3-9]\d)\b'
    )

    # Producing or inspecting a document is something the user asks for with a
    # verb. The supporting keywords above ("bail", "petition", "contract",
    # "risks") are ordinary legal vocabulary that shows up just as often in
    # questions *about* the law, so without one of these verbs those intents
    # score nothing -- otherwise "Tell me about bail" is answered with a drafted
    # bail application.
    REQUIRED_TRIGGERS: ClassVar[dict] = {
        IntentType.DRAFT_DOCUMENT: re.compile(
            r'\b(draft|write|prepare|create|generate|make|file|send|issue)\b'
        ),
        IntentType.ANALYZE_DOCUMENT: re.compile(
            r'\b(analyse|analyze|review|examine|assess|evaluate|check|summari[sz]e|'
            r'go through|look (?:at|over)|vet)\b'
        ),
        IntentType.LIVE_RESEARCH: RECENCY_TRIGGER,
    }

    # How much a fired trigger contributes. RAG_SEARCH and LIVE_RESEARCH share
    # case-law vocabulary on purpose, and recency is the only thing that tells
    # them apart, so it has to outweigh a single shared keyword -- otherwise
    # "current case law on BNS 111" is answered from the snapshot.
    TRIGGER_WEIGHT: ClassVar[dict] = {IntentType.LIVE_RESEARCH: 2}

    #: Which workspace of the UI a query came from, and what that settles.
    #:
    #: The five workspaces already route by *endpoint* -- Corpus calls
    #: /search, Live research calls /research, Draft calls /documents/draft --
    #: so in practice only "Ask" (`chat`) reaches the agent today, and this
    #: mapping mostly exists to stop the classifier guessing at intents that
    #: cannot legitimately arrive. It becomes load-bearing the moment the UI
    #: offers one input box for everything, which is the direction it is going.
    #:
    #: `chat` is deliberately absent: the Ask workspace is where a user may
    #: reasonably ask anything, so there the keywords still decide.
    WORKSPACE_INTENT: ClassVar[dict] = {
        "search": IntentType.RAG_SEARCH,
        "research": IntentType.LIVE_RESEARCH,
        "draft": IntentType.DRAFT_DOCUMENT,
        "analyze": IntentType.ANALYZE_DOCUMENT,
    }

    # Order used to resolve equal keyword scores; most specific intent first.
    _TIE_BREAK_ORDER = (
        IntentType.CHAT,
        IntentType.LIVE_RESEARCH,
        IntentType.DRAFT_DOCUMENT,
        IntentType.ANALYZE_DOCUMENT,
        IntentType.RAG_SEARCH,
        IntentType.UNKNOWN,
    )

    def __init__(self, llm_service: LLMService | None = None):
        """
        Initialize intent classifier.

        Args:
            llm_service: Optional LLM service for fallback classification
        """
        self.llm_service = llm_service

    def classify(self, query: str, workspace: str | None = None) -> str:
        """
        Classify user query into an intent.

        Args:
            query: User query string
            workspace: Which UI workspace the query was typed in, when the
                caller knows. A user in the Draft workspace is drafting; there
                is nothing to infer, and inferring it from keywords is strictly
                worse than being told. Unknown or absent values fall through to
                the keyword path rather than erroring, so every existing caller
                keeps working unchanged.

        Returns:
            Intent type as string
        """
        settled = self.WORKSPACE_INTENT.get((workspace or "").strip().lower())
        if settled is not None:
            logger.info(f"Intent from workspace {workspace!r}: {settled.value}")
            return settled.value

        query_lower = query.lower()

        # Score each intent based on keyword matches
        scores = dict.fromkeys(IntentType, 0)

        for intent, patterns in self.INTENT_PATTERNS.items():
            trigger = self.REQUIRED_TRIGGERS.get(intent)
            if trigger is not None:
                if not trigger.search(query_lower):
                    continue
                # A trigger is not merely a gate, it is the strongest single
                # signal for these intents, so it scores too.
                scores[intent] += self.TRIGGER_WEIGHT.get(intent, 1)
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    scores[intent] += 1

        # Get intent with highest score
        max_score = max(scores.values())

        if max_score > 0:
            # Break ties by specificity. RAG_SEARCH's patterns are deliberately broad
            # (they include generic question words like "what"), and it is already the
            # fallback below, so it must lose ties to the narrower intents — otherwise
            # "what can you help me with?" would be sent to vector search.
            for intent in self._TIE_BREAK_ORDER:
                if scores[intent] == max_score:
                    logger.info(f"Classified intent: {intent.value} (score: {max_score})")
                    return intent.value

        # Fallback to LLM classification if available
        if self.llm_service:
            try:
                llm_intent = self._classify_with_llm(query)
                if llm_intent:
                    logger.info(f"LLM classified intent: {llm_intent}")
                    return llm_intent
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")

        # Default to RAG search for legal queries
        logger.info(f"Defaulting to RAG_SEARCH for query: {query[:50]}...")
        return IntentType.RAG_SEARCH.value

    def _classify_with_llm(self, query: str) -> str | None:
        """
        Use LLM to classify intent when keyword matching is uncertain.

        Args:
            query: User query

        Returns:
            Intent type or None
        """
        if not self.llm_service:
            return None

        prompt = f"""Classify the following user query into ONE of these intents:
- rag_search: User wants to search legal information, laws, cases, or provisions
- draft_document: User wants to draft a legal document (bail application, petition, etc.)
- analyze_document: User wants to analyze an uploaded document
- chat: General conversation or greeting

Query: "{query}"

Respond with ONLY the intent name (rag_search, draft_document, analyze_document, or chat).
Intent:"""

        try:
            response = self.llm_service.generate(
                prompt=prompt,
                max_tokens=20,
                temperature=0.1
            )

            intent_str = response.strip().lower()

            # Validate response
            for intent in IntentType:
                if intent.value in intent_str:
                    return intent.value

            return None

        except Exception as e:
            logger.error(f"LLM classification error: {e}")
            return None

    def get_intent_description(self, intent: str) -> str:
        """
        Get human-readable description of an intent.

        Args:
            intent: Intent type

        Returns:
            Description string
        """
        descriptions = {
            IntentType.RAG_SEARCH.value: "Search legal information and case law",
            IntentType.DRAFT_DOCUMENT.value: "Draft legal documents",
            IntentType.ANALYZE_DOCUMENT.value: "Analyze uploaded documents",
            IntentType.CHAT.value: "General conversation",
            IntentType.UNKNOWN.value: "Unknown intent"
        }
        return descriptions.get(intent, "Unknown intent")


# Singleton instance
_classifier_instance: IntentClassifier | None = None


def get_intent_classifier(llm_service: LLMService | None = None) -> IntentClassifier:
    """
    Get or create intent classifier singleton.

    Args:
        llm_service: Optional LLM service

    Returns:
        IntentClassifier instance
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier(llm_service)
    return _classifier_instance
