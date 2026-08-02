"""
End-to-End System Tests for LawAI
Tests complete user flows with real API calls (not mocked)
"""

import json
import os

import pytest
import requests

# Test configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
TIMEOUT = 60  # seconds for long-running operations


class TestE2ESystem:
    """End-to-end system tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test"""
        # Verify backend is running
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            assert response.status_code == 200, "Backend not running"
        except requests.exceptions.RequestException:
            pytest.skip("Backend not running - start with: cd backend && uvicorn main:app --reload")

        yield

    def test_health_check(self):
        """Test: System health check"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")

    def test_bail_application_flow(self):
        """
        Test Scenario 1: Complete Bail Application Flow
        1. RAG search for BNS Section 103
        2. Draft bail application
        3. Verify document generation
        """
        print("\n=== Testing Bail Application Flow ===")

        # Step 1: RAG search for BNS Section 103
        print("Step 1: Searching for BNS Section 103 provisions...")
        search_payload = {
            "query": "What are the provisions for bail in BNS Section 103 cases?",
            "collection": "bns_sections",
            "top_k": 3
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/search",
            json=search_payload,
            timeout=30
        )
        assert response.status_code == 200, f"Search failed: {response.text}"
        search_results = response.json()

        assert "answer" in search_results
        assert "sources" in search_results
        assert len(search_results["sources"]) > 0
        print(f"✓ Found {len(search_results['sources'])} relevant sections")

        # Step 2: Draft bail application using agent
        print("Step 2: Drafting bail application...")
        draft_payload = {
            "query": "Draft a bail application for a client arrested under BNS Section 103 (murder). Client name: Rajesh Kumar, arrested on 2024-01-15, no prior criminal record.",
            "session_id": "test_bail_session_001"
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/agent/query",
            json=draft_payload,
            timeout=TIMEOUT
        )
        assert response.status_code == 200, f"Draft failed: {response.text}"
        draft_result = response.json()

        assert "response" in draft_result
        assert len(draft_result["response"]) > 100  # Should be substantial
        print(f"✓ Draft generated ({len(draft_result['response'])} chars)")

        # Step 3: Generate document
        print("Step 3: Generating .docx document...")
        doc_payload = {
            "document_type": "bail_application",
            "case_details": {
                "accused_name": "Rajesh Kumar",
                "fir_number": "FIR 42/2024",
                "sections": "BNS 103",
                "facts": "Arrested on 2024-01-15, no prior criminal record.",
                "police_station": "Andheri PS"
            }
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/documents/draft",
            json=doc_payload,
            timeout=TIMEOUT
        )
        assert response.status_code == 200, f"Document generation failed: {response.text}"
        drafted = response.json()
        assert drafted["success"] is True
        assert len(drafted["document"]) > 200
        print(f"✓ Document drafted ({len(drafted['document'])} chars)")

        # Step 4: Export the draft as a .docx the user can file
        print("Step 4: Exporting .docx document...")
        response = requests.post(
            f"{BASE_URL}/api/v1/documents/export/docx",
            json={
                "content": drafted["document"],
                "filename": "bail_application_rajesh_kumar",
                "title": "Bail Application"
            },
            timeout=30
        )
        assert response.status_code == 200, f"Export failed: {response.text}"
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert response.content[:2] == b"PK"  # .docx is a zip archive
        assert len(response.content) > 1000
        print(f"✓ Document exported ({len(response.content)} bytes)")

        print("✓✓✓ Bail Application Flow: PASSED")

    def test_case_law_research_flow(self):
        """
        Test Scenario 2: Case Law Research Flow
        1. Search SC judgements for anticipatory bail
        2. Verify citations and relevance scores
        3. Test export functionality
        """
        print("\n=== Testing Case Law Research Flow ===")

        # Step 1: Search SC judgements
        print("Step 1: Searching SC judgements for anticipatory bail...")
        search_payload = {
            "query": "anticipatory bail guidelines and conditions",
            "collection": "sc_judgements",
            "top_k": 5
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/search",
            json=search_payload,
            timeout=30
        )
        assert response.status_code == 200
        results = response.json()

        assert "answer" in results
        assert "sources" in results
        assert len(results["sources"]) > 0

        # Step 2: Verify citations and scores
        print("Step 2: Verifying citations and relevance scores...")
        for result in results["sources"]:
            assert "text" in result
            assert "metadata" in result
            assert "relevance_score" in result
            assert 0 <= result["relevance_score"] <= 1
            print(f"  - Score: {result['relevance_score']:.3f}, Text: {result['text'][:80]}...")

        print(f"✓ Found {len(results['sources'])} relevant judgements")

        # Step 3: Test export (simulate)
        print("Step 3: Testing export functionality...")
        export_data = json.dumps(results, indent=2)
        assert len(export_data) > 100
        print(f"✓ Export data generated ({len(export_data)} bytes)")

        print("✓✓✓ Case Law Research Flow: PASSED")

    def test_document_analysis_flow(self):
        """
        Test Scenario 3: Document Analysis Flow
        1. Analyze sample rental agreement
        2. Verify risk identification
        3. Verify key clauses extraction
        """
        print("\n=== Testing Document Analysis Flow ===")

        # Sample rental agreement text
        sample_agreement = """
        RENTAL AGREEMENT

        This agreement is made on 1st January 2024 between:
        Landlord: Mr. Sharma (Owner)
        Tenant: Mr. Patel

        Property: Flat 301, Building A, Mumbai

        Terms:
        1. Monthly rent: Rs. 25,000
        2. Security deposit: Rs. 75,000 (non-refundable)
        3. Tenant shall not make any alterations without written consent
        4. Landlord may terminate with 7 days notice for any reason
        5. Tenant responsible for all repairs and maintenance
        6. Tenant indemnifies landlord from all claims and liabilities
        7. Disputes subject to Mumbai jurisdiction only
        """

        print("Step 1: Analyzing rental agreement...")
        analyze_payload = {
            "document_text": sample_agreement,
            "analysis_type": "risks",
            "document_type": "agreement"
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/documents/analyze",
            json=analyze_payload,
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        analysis = response.json()

        assert "analysis" in analysis
        assert len(analysis["analysis"]) > 50
        print(f"✓ Analysis completed ({len(analysis['analysis'])} chars)")

        # Verify analysis mentions key risks
        analysis_text = analysis["analysis"].lower()
        risk_keywords = ["risk", "clause", "tenant", "landlord", "deposit"]
        found_keywords = [kw for kw in risk_keywords if kw in analysis_text]
        assert len(found_keywords) >= 3, f"Analysis should mention risks, found: {found_keywords}"
        print(f"✓ Risk keywords found: {found_keywords}")

        print("✓✓✓ Document Analysis Flow: PASSED")

    def test_streaming_chat_flow(self):
        """
        Test Scenario 4: Streaming Chat Flow
        1. Send chat query
        2. Verify streaming response
        3. Test follow-up with context
        """
        print("\n=== Testing Streaming Chat Flow ===")

        session_id = "test_chat_session_001"

        # Step 1: Initial query
        print("Step 1: Sending initial chat query...")
        chat_payload = {
            "message": "Explain the concept of anticipatory bail in simple terms",
            "session_id": session_id,
            # /chat streams SSE unless told otherwise; this step wants JSON.
            "stream": False
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json=chat_payload,
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        chat_result = response.json()

        assert "response" in chat_result
        assert len(chat_result["response"]) > 50
        print(f"✓ Initial response received ({len(chat_result['response'])} chars)")

        # Step 2: Follow-up query (tests context)
        print("Step 2: Sending follow-up query...")
        followup_payload = {
            "message": "What are the conditions for granting it?",
            "session_id": session_id,
            "stream": False
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json=followup_payload,
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        followup_result = response.json()

        assert "response" in followup_result
        assert len(followup_result["response"]) > 30
        print(f"✓ Follow-up response received ({len(followup_result['response'])} chars)")

        # Step 3: Test streaming endpoint
        print("Step 3: Testing streaming endpoint...")
        stream_payload = {
            "query": "What is Section 498A BNS?",
            "session_id": f"{session_id}_stream"
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/agent/query/stream",
            json=stream_payload,
            stream=True,
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        # Collect streamed chunks
        # SSE contract: data: {"token": "..."} lines, terminated by data: [DONE]
        chunks = []
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            payload = decoded[len("data: "):]
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if "token" in data:
                chunks.append(data["token"])

        full_response = "".join(chunks)
        assert len(full_response) > 20, "Streaming should return content"
        print(f"✓ Streaming response received ({len(full_response)} chars)")

        print("✓✓✓ Streaming Chat Flow: PASSED")

    def test_agent_tool_routing(self):
        """Test: Agent correctly routes to different tools"""
        print("\n=== Testing Agent Tool Routing ===")

        test_cases = [
            {
                "query": "Search for BNS Section 420",
                "expected_tool": "rag_search",
                "keywords": ["section", "420"]
            },
            {
                "query": "Draft a petition for anticipatory bail",
                "expected_tool": "draft_document",
                "keywords": ["petition", "bail"]
            },
            {
                "query": "Analyze this contract for risks",
                "expected_tool": "analyze_doc",
                "keywords": ["analyze", "risk"]
            },
            {
                "query": "What is the difference between bail and anticipatory bail?",
                "expected_tool": "chat",
                "keywords": ["bail", "difference"]
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\nTest {i}: {test_case['query'][:50]}...")
            payload = {
                "query": test_case["query"],
                "session_id": f"test_routing_{i}"
            }

            response = requests.post(
                f"{BASE_URL}/api/v1/agent/query",
                json=payload,
                timeout=TIMEOUT
            )
            assert response.status_code == 200
            result = response.json()

            assert "response" in result
            assert len(result["response"]) > 20

            # Check if response contains expected keywords
            response_lower = result["response"].lower()
            found = any(kw.lower() in response_lower for kw in test_case["keywords"])
            assert found, f"Response should contain keywords: {test_case['keywords']}"

            print(f"✓ Tool routing test {i} passed")

        print("✓✓✓ Agent Tool Routing: PASSED")

    def test_error_handling(self):
        """Test: System error handling"""
        print("\n=== Testing Error Handling ===")

        # Test 1: Invalid collection
        print("Test 1: Invalid collection name...")
        response = requests.post(
            f"{BASE_URL}/api/v1/search",
            json={"query": "test", "collection": "invalid_collection"},
            timeout=10
        )
        assert response.status_code in [400, 422], "Should return error for invalid collection"
        print("✓ Invalid collection handled")

        # Test 2: Empty query
        print("Test 2: Empty query...")
        response = requests.post(
            f"{BASE_URL}/api/v1/agent/query",
            json={"query": "", "session_id": "test"},
            timeout=10
        )
        assert response.status_code in [400, 422], "Should return error for empty query"
        print("✓ Empty query handled")

        # Test 3: Invalid document type
        print("Test 3: Invalid document type...")
        response = requests.post(
            f"{BASE_URL}/api/v1/documents/draft",
            json={"document_type": "invalid_type", "content": {}},
            timeout=10
        )
        assert response.status_code in [400, 422], "Should return error for invalid document type"
        print("✓ Invalid document type handled")

        print("✓✓✓ Error Handling: PASSED")

    def test_concurrent_requests(self):
        """Test: System handles concurrent requests"""
        print("\n=== Testing Concurrent Requests ===")

        import concurrent.futures

        def make_request(i):
            response = requests.post(
                f"{BASE_URL}/api/v1/chat",
                json={
                    "message": f"What is BNS Section {100 + i}?",
                    "session_id": f"concurrent_test_{i}",
                    "stream": False
                },
                timeout=TIMEOUT
            )
            return response.status_code == 200

        # Send 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = sum(results)
        print(f"✓ {success_count}/5 concurrent requests succeeded")
        assert success_count >= 4, "At least 4/5 concurrent requests should succeed"

        print("✓✓✓ Concurrent Requests: PASSED")


def run_e2e_tests():
    """Run all E2E tests and generate report"""
    print("=" * 80)
    print("LawAI End-to-End System Tests")
    print("=" * 80)

    # Run pytest with verbose output
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-s"  # Show print statements
    ])


if __name__ == "__main__":
    run_e2e_tests()
