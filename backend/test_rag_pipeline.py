#!/usr/bin/env python3
"""
Test script for RAG pipeline
Tests the complete flow: embedding -> vector search -> LLM generation
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from services.rag_service import get_rag_service
from services.vector_service import VectorService

def test_rag_search():
    """Test RAG search with sample queries"""
    
    print("=" * 70)
    print("Testing LawAI RAG Pipeline")
    print("=" * 70)
    
    # Get RAG service
    rag_service = get_rag_service()
    
    # Test queries
    test_queries = [
        {
            "query": "What are the provisions for anticipatory bail?",
            "collection": VectorService.BNSS_COLLECTION,
            "description": "BNSS - Anticipatory Bail"
        },
        {
            "query": "What is the punishment for murder?",
            "collection": VectorService.BNS_COLLECTION,
            "description": "BNS - Murder Punishment"
        },
        {
            "query": "What are the guidelines for arrest by police?",
            "collection": VectorService.SC_JUDGEMENTS_COLLECTION,
            "description": "SC Judgements - Arrest Guidelines"
        }
    ]
    
    for i, test in enumerate(test_queries, 1):
        print(f"\n{'=' * 70}")
        print(f"Test {i}: {test['description']}")
        print(f"{'=' * 70}")
        print(f"Query: {test['query']}")
        print(f"Collection: {test['collection']}")
        print("-" * 70)
        
        try:
            # Perform RAG search
            result = rag_service.search_and_generate(
                query=test['query'],
                collection=test['collection'],
                top_k=3
            )
            
            # Display results
            print(f"\n✓ Search successful!")
            print(f"  Sources found: {result['num_sources']}")
            
            print(f"\n📚 Sources:")
            for j, source in enumerate(result['sources'], 1):
                meta = source['metadata']
                print(f"\n  [{j}] Relevance: {source['relevance_score']:.2f}")
                if 'section_number' in meta:
                    print(f"      {meta.get('act', 'Unknown')} - Section {meta['section_number']}")
                    print(f"      {meta.get('title', 'No title')}")
                elif 'case_name' in meta:
                    print(f"      {meta.get('case_name', 'Unknown case')}")
                    print(f"      {meta.get('citation', 'No citation')}")
                print(f"      Preview: {source['text'][:150]}...")
            
            print(f"\n💡 AI Answer:")
            print("-" * 70)
            # Print first 500 chars of answer
            answer = result['answer']
            if len(answer) > 500:
                print(answer[:500] + "...\n[Answer truncated for display]")
            else:
                print(answer)
            
            print(f"\n✓ Test {i} passed!")
            
        except Exception as e:
            print(f"\n✗ Test {i} failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Test multi-collection search
    print(f"\n{'=' * 70}")
    print(f"Test 4: Multi-Collection Search")
    print(f"{'=' * 70}")
    print(f"Query: What are bail provisions in Indian law?")
    print(f"Collections: All")
    print("-" * 70)
    
    try:
        result = rag_service.multi_collection_search(
            query="What are bail provisions in Indian law?",
            collections=[
                VectorService.BNS_COLLECTION,
                VectorService.BNSS_COLLECTION,
                VectorService.BSA_COLLECTION,
                VectorService.SC_JUDGEMENTS_COLLECTION
            ],
            top_k_per_collection=2
        )
        
        print(f"\n✓ Multi-collection search successful!")
        print(f"  Total sources: {result['num_sources']}")
        print(f"  Collections searched: {len(result['collections'])}")
        
        print(f"\n📚 Top Sources:")
        for j, source in enumerate(result['sources'][:5], 1):
            meta = source['metadata']
            print(f"\n  [{j}] Relevance: {source['relevance_score']:.2f}")
            if 'section_number' in meta:
                print(f"      {meta.get('act', 'Unknown')} - Section {meta['section_number']}")
            elif 'case_name' in meta:
                print(f"      {meta.get('case_name', 'Unknown case')}")
        
        print(f"\n✓ Test 4 passed!")
        
    except Exception as e:
        print(f"\n✗ Test 4 failed: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'=' * 70}")
    print("RAG Pipeline Testing Complete!")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    test_rag_search()
