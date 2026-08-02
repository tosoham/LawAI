"""
Demo Script for LangGraph Agent

Demonstrates agent capabilities with realistic legal queries.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from backend.agents.agent_service import get_agent_service, reset_agent_service
from backend.services.llm_service import LLMService
from backend.services.rag_service import RAGService
from backend.tools.registry import initialize_tools
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_separator():
    """Print a visual separator"""
    print("\n" + "="*80 + "\n")


def print_result(query: str, result: dict):
    """Print query result in a formatted way"""
    print(f"Query: {query}")
    print(f"Intent: {result['intent']}")
    print(f"\nResponse:\n{result['response']}")
    if result.get('error'):
        print(f"\nError: {result['error']}")
    print_separator()


async def demo_streaming(agent_service, query: str):
    """Demonstrate streaming response"""
    print(f"Query (Streaming): {query}")
    print("\nStreaming Response:")
    
    async for chunk in agent_service.process_query_stream(query):
        print(chunk, end='', flush=True)
    
    print()
    print_separator()


def main():
    """Run agent demo"""
    print_separator()
    print("LawAI Agent Demo - LangGraph Orchestration")
    print_separator()
    
    # Initialize services
    logger.info("Initializing services...")
    reset_agent_service()
    
    try:
        llm_service = LLMService()
        rag_service = RAGService()
        initialize_tools(llm_service, rag_service)
        agent_service = get_agent_service()
        
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        print("\nError: Could not initialize services. Please check your .env configuration.")
        print(f"Details: {e}")
        return
    
    # Demo 1: RAG Search - Bail Provisions
    print("Demo 1: RAG Search - Legal Provisions")
    print_separator()
    
    queries_rag = [
        "What are the provisions for anticipatory bail in BNSS?",
        "Explain BNS Section 103 on murder",
        "What are the arrest procedures under BNSS?"
    ]
    
    for query in queries_rag:
        try:
            result = agent_service.process_query(query)
            print_result(query, result)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"Error: {e}")
            print_separator()
    
    # Demo 2: Draft Document
    print("Demo 2: Draft Legal Document")
    print_separator()
    
    queries_draft = [
        "Draft a bail application for a client arrested under BNS Section 103",
        "Generate an anticipatory bail petition under BNSS Section 482"
    ]
    
    for query in queries_draft:
        try:
            result = agent_service.process_query(query)
            print_result(query, result)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"Error: {e}")
            print_separator()
    
    # Demo 3: Document Analysis
    print("Demo 3: Document Analysis")
    print_separator()
    
    queries_analyze = [
        "Analyze this rental agreement for potential risks",
        "Review the uploaded contract and identify problematic clauses"
    ]
    
    for query in queries_analyze:
        try:
            result = agent_service.process_query(query)
            print_result(query, result)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"Error: {e}")
            print_separator()
    
    # Demo 4: Chat
    print("Demo 4: General Chat")
    print_separator()
    
    queries_chat = [
        "Hello, what can you help me with?",
        "Explain the concept of mens rea in criminal law"
    ]
    
    for query in queries_chat:
        try:
            result = agent_service.process_query(query)
            print_result(query, result)
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"Error: {e}")
            print_separator()
    
    # Demo 5: Streaming Response
    print("Demo 5: Streaming Response")
    print_separator()
    
    try:
        asyncio.run(demo_streaming(
            agent_service,
            "What are the key differences between IPC and BNS?"
        ))
    except Exception as e:
        logger.error(f"Error in streaming demo: {e}")
        print(f"Error: {e}")
        print_separator()
    
    # Demo 6: Complex Multi-Step Flow
    print("Demo 6: Complete Bail Application Flow")
    print_separator()
    
    print("Step 1: Search for relevant legal provisions")
    try:
        result1 = agent_service.process_query(
            "What are the provisions for bail under BNSS Section 479?"
        )
        print_result("Search Query", result1)
    except Exception as e:
        logger.error(f"Error in step 1: {e}")
        print(f"Error: {e}")
        print_separator()
    
    print("Step 2: Draft bail application based on provisions")
    try:
        result2 = agent_service.process_query(
            "Draft a bail application under BNSS Section 479 for theft charges"
        )
        print_result("Draft Query", result2)
    except Exception as e:
        logger.error(f"Error in step 2: {e}")
        print(f"Error: {e}")
        print_separator()
    
    # Agent Info
    print("Agent Information")
    print_separator()
    
    try:
        info = agent_service.get_agent_info()
        print(f"Status: {info['status']}")
        print(f"LLM Model: {info['llm_model']}")
        print(f"Version: {info['version']}")
        print("\nAvailable Tools:")
        for tool in info['available_tools']:
            print(f"  - {tool}")
        print("\nSupported Intents:")
        for intent in info['supported_intents']:
            print(f"  - {intent}")
        print_separator()
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        print(f"Error: {e}")
        print_separator()
    
    # Health Check
    print("Health Check")
    print_separator()
    
    try:
        health = agent_service.health_check()
        print(f"Overall Status: {health['status']}")
        print(f"Tools Count: {health['tools_count']}")
        print("\nComponent Health:")
        for component, status in health.get('components', {}).items():
            print(f"  - {component}: {status}")
        print_separator()
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        print(f"Error: {e}")
        print_separator()
    
    print("Demo completed successfully!")
    print_separator()


if __name__ == "__main__":
    main()
