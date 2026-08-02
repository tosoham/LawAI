"""
Demo Script for MCP Tools

Demonstrates all MCP tools with realistic examples:
- RAG Search
- Chat
- Draft Document (Bail Application)
- Analyze Document
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from services.llm_service import llm_service
from services.rag_service import RAGService
from tools.registry import initialize_tools
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_result(result):
    """Print tool result in a formatted way"""
    if result.success:
        print("✓ SUCCESS")
        print("\nData:")
        if isinstance(result.data, dict):
            for key, value in result.data.items():
                if isinstance(value, str) and len(value) > 200:
                    print(f"  {key}: {value[:200]}...")
                else:
                    print(f"  {key}: {value}")
        else:
            print(f"  {result.data}")
        
        if result.metadata:
            print("\nMetadata:")
            for key, value in result.metadata.items():
                print(f"  {key}: {value}")
    else:
        print("✗ FAILED")
        print(f"Error: {result.error}")


async def demo_rag_search(registry):
    """Demo RAG search tool"""
    print_section("DEMO 1: RAG Search Tool")
    
    tool = registry.get_tool("rag_search")
    if not tool:
        print("❌ RAG search tool not available")
        return
    
    print("Query: 'Find provisions for anticipatory bail in BNSS'")
    print("Collection: bnss_sections")
    print("Top K: 3\n")
    
    result = await tool.safe_execute(
        query="Find provisions for anticipatory bail in BNSS",
        collection="bnss_sections",
        top_k=3
    )
    
    print_result(result)


async def demo_chat(registry):
    """Demo chat tool"""
    print_section("DEMO 2: Chat Tool")
    
    tool = registry.get_tool("chat")
    if not tool:
        print("❌ Chat tool not available")
        return
    
    print("Message: 'Explain the concept of mens rea in criminal law'\n")
    
    result = await tool.safe_execute(
        message="Explain the concept of mens rea in criminal law"
    )
    
    print_result(result)
    
    # Demo with context
    print("\n" + "-" * 80)
    print("Follow-up with context:\n")
    
    context = [
        {"role": "user", "content": "Explain mens rea"},
        {"role": "assistant", "content": "Mens rea refers to the mental state..."}
    ]
    
    print("Message: 'Give me an example from Indian law'")
    print(f"Context: {len(context)} previous messages\n")
    
    result = await tool.safe_execute(
        message="Give me an example from Indian law",
        context=context
    )
    
    print_result(result)


async def demo_draft_document(registry):
    """Demo draft document tool"""
    print_section("DEMO 3: Draft Document Tool - Bail Application")
    
    tool = registry.get_tool("draft_document")
    if not tool:
        print("❌ Draft document tool not available")
        return
    
    case_details = {
        "accused_name": "Rajesh Kumar",
        "fir_number": "456/2024",
        "sections": ["BNS 103 (Murder)", "BNS 34 (Common Intention)"],
        "facts": "The accused has been falsely implicated in a murder case. The incident occurred on 15th January 2024. The accused was not present at the scene and has alibi witnesses. The FIR was registered based on false testimony.",
        "police_station": "Koramangala Police Station, Bangalore",
        "court_name": "Sessions Court, Bangalore",
        "additional_grounds": "The accused is a first-time offender with no criminal history. He is the sole breadwinner of his family and has strong community ties."
    }
    
    print("Document Type: bail_application")
    print("\nCase Details:")
    for key, value in case_details.items():
        print(f"  {key}: {value}")
    print()
    
    result = await tool.safe_execute(
        document_type="bail_application",
        case_details=case_details
    )
    
    print_result(result)


async def demo_analyze_document(registry):
    """Demo analyze document tool"""
    print_section("DEMO 4: Analyze Document Tool - Rental Agreement")
    
    tool = registry.get_tool("analyze_document")
    if not tool:
        print("❌ Analyze document tool not available")
        return
    
    # Sample rental agreement
    document_text = """
RENTAL AGREEMENT

This Rental Agreement is made on 1st January 2024 between:

LANDLORD: Mr. Suresh Sharma, residing at 123 MG Road, Bangalore
TENANT: Ms. Priya Patel, residing at 456 Brigade Road, Bangalore

PROPERTY: Flat No. 301, Green Valley Apartments, Whitefield, Bangalore

TERMS AND CONDITIONS:

1. RENT: The monthly rent is Rs. 25,000/- payable on or before 5th of each month.

2. SECURITY DEPOSIT: The tenant shall pay Rs. 1,00,000/- as security deposit, refundable at the end of tenancy subject to deductions for damages.

3. DURATION: This agreement is for 11 months starting from 1st January 2024.

4. TERMINATION: Either party may terminate with 2 months notice. Landlord reserves right to terminate immediately for non-payment of rent for 2 consecutive months.

5. MAINTENANCE: Tenant responsible for minor repairs. Major structural repairs by landlord.

6. SUBLETTING: Tenant shall not sublet without written permission of landlord.

7. PETS: No pets allowed without prior written consent.

8. LATE PAYMENT: Late payment of rent will attract penalty of Rs. 500/- per day.

9. DISPUTES: Any disputes shall be subject to Bangalore jurisdiction only.

10. INDEMNITY: Tenant shall indemnify landlord against all claims, damages arising from tenant's use of property.

Signed:
Landlord: ________________
Tenant: ________________
"""
    
    print("Document Type: agreement (rental)")
    print(f"Document Length: {len(document_text)} characters")
    print("Analysis Type: risks\n")
    
    result = await tool.safe_execute(
        document_text=document_text,
        analysis_type="risks",
        document_type="agreement"
    )
    
    print_result(result)
    
    # Demo summary analysis
    print("\n" + "-" * 80)
    print("Summary Analysis:\n")
    
    result = await tool.safe_execute(
        document_text=document_text,
        analysis_type="summary",
        document_type="agreement"
    )
    
    print_result(result)


async def demo_tool_registry(registry):
    """Demo tool registry functionality"""
    print_section("DEMO 5: Tool Registry")
    
    print("Registered Tools:")
    tools = registry.list_tools()
    for tool_name in tools:
        metadata = registry.get_tool_metadata(tool_name)
        print(f"\n  • {tool_name}")
        print(f"    Description: {metadata.description}")
        print(f"    Parameters: {', '.join(metadata.parameters.keys())}")
        if metadata.examples:
            print(f"    Example: {metadata.examples[0]}")
    
    print(f"\n\nTotal Tools: {len(registry)}")


async def main():
    """Run all demos"""
    print("\n" + "=" * 80)
    print("  LawAI MCP Tools Demo")
    print("  Demonstrating all 4 tools with realistic examples")
    print("=" * 80)
    
    try:
        # Initialize services and tools
        print("\n⏳ Initializing services and tools...")
        rag_service = RAGService()
        registry = initialize_tools(llm_service, rag_service)
        print(f"✓ Initialized {len(registry)} tools\n")
        
        # Run demos
        await demo_rag_search(registry)
        await demo_chat(registry)
        await demo_draft_document(registry)
        await demo_analyze_document(registry)
        await demo_tool_registry(registry)
        
        print_section("Demo Complete!")
        print("All tools demonstrated successfully.")
        print("\nKey Features:")
        print("  ✓ RAG Search - Query legal corpus with citations")
        print("  ✓ Chat - General legal Q&A with context")
        print("  ✓ Draft Document - Generate professional legal documents")
        print("  ✓ Analyze Document - Risk analysis and summaries")
        print("\nNext Steps:")
        print("  • Integrate with LangGraph for agent orchestration")
        print("  • Add streaming support for real-time responses")
        print("  • Deploy to production with FastAPI")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"\n❌ Demo failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

# Made with Bob
