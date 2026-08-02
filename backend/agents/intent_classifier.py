"""
Intent Classifier for LawAI Agent

Classifies user queries into appropriate intents for tool routing.
"""

import re
from typing import Optional
import logging

from agents.state import IntentType
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Classifies user queries into intents using keyword matching and LLM fallback.
    """
    
    # Keyword patterns for each intent
    INTENT_PATTERNS = {
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
    }
    
    # Order used to resolve equal keyword scores; most specific intent first.
    _TIE_BREAK_ORDER = (
        IntentType.CHAT,
        IntentType.DRAFT_DOCUMENT,
        IntentType.ANALYZE_DOCUMENT,
        IntentType.RAG_SEARCH,
        IntentType.UNKNOWN,
    )

    def __init__(self, llm_service: Optional[LLMService] = None):
        """
        Initialize intent classifier.
        
        Args:
            llm_service: Optional LLM service for fallback classification
        """
        self.llm_service = llm_service
    
    def classify(self, query: str) -> str:
        """
        Classify user query into an intent.
        
        Args:
            query: User query string
            
        Returns:
            Intent type as string
        """
        query_lower = query.lower()
        
        # Score each intent based on keyword matches
        scores = {intent: 0 for intent in IntentType}
        
        for intent, patterns in self.INTENT_PATTERNS.items():
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
    
    def _classify_with_llm(self, query: str) -> Optional[str]:
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
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier(llm_service: Optional[LLMService] = None) -> IntentClassifier:
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
