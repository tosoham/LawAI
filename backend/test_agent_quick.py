"""
Quick test script for agent functionality
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from agents.intent_classifier import IntentClassifier
from agents.state import IntentType, create_initial_state


def test_intent_classifier():
    """Test intent classifier"""
    print("Testing Intent Classifier...")

    classifier = IntentClassifier()

    test_cases = [
        ("What are bail provisions in BNSS?", IntentType.RAG_SEARCH.value),
        ("Draft a bail application", IntentType.DRAFT_DOCUMENT.value),
        ("Analyze this contract", IntentType.ANALYZE_DOCUMENT.value),
        ("Hello, how are you?", IntentType.CHAT.value),
    ]

    for query, expected_intent in test_cases:
        intent = classifier.classify(query)
        status = "✓" if intent == expected_intent else "✗"
        print(f"{status} Query: '{query[:50]}...'")
        print(f"  Expected: {expected_intent}, Got: {intent}")

    print("\nIntent Classifier Test Complete!\n")


def test_agent_state():
    """Test agent state management"""
    print("Testing Agent State...")

    query = "Test query"
    state = create_initial_state(query)

    assert state["user_query"] == query
    assert state["intent"] == IntentType.UNKNOWN.value
    assert len(state["messages"]) == 1

    print("✓ Initial state created successfully")
    print(f"  Query: {state['user_query']}")
    print(f"  Intent: {state['intent']}")
    print(f"  Messages: {len(state['messages'])}")

    print("\nAgent State Test Complete!\n")


def test_imports():
    """Test that all modules can be imported"""
    print("Testing Module Imports...")

    try:
        print("✓ agents.state imported")

        print("✓ agents.intent_classifier imported")

        print("✓ agents.legal_agent imported")

        print("✓ agents.agent_service imported")

        print("✓ api.v1.agent imported")

        print("\nAll Module Imports Successful!\n")
        return True

    except Exception as e:
        print(f"\n✗ Import failed: {e}\n")
        return False


def main():
    """Run quick tests"""
    print("="*60)
    print("LawAI Agent - Quick Test")
    print("="*60 + "\n")

    # Test imports first
    if not test_imports():
        print("Import test failed. Please check dependencies.")
        return

    # Test intent classifier
    try:
        test_intent_classifier()
    except Exception as e:
        print(f"Intent classifier test failed: {e}\n")

    # Test agent state
    try:
        test_agent_state()
    except Exception as e:
        print(f"Agent state test failed: {e}\n")

    print("="*60)
    print("Quick Test Complete!")
    print("="*60)
    print("\nTo run full demo: python backend/scripts/demo_agent.py")
    print("To run unit tests: cd backend && pytest tests/unit/test_agent.py -v")
    print("To run integration tests: cd backend && pytest tests/integration/test_agent_flow.py -v")


if __name__ == "__main__":
    main()
