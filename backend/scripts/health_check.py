"""
Health Check Script for LawAI System
Verifies all components are functioning correctly
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from typing import List, Tuple
from datetime import datetime
import chromadb
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CHROMA_PATH = "./chroma_db"


class HealthChecker:
    """System health checker"""
    
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.start_time = datetime.now()
    
    def check(self, name: str, func) -> bool:
        """Run a health check"""
        try:
            print(f"\n{Fore.CYAN}Checking: {name}...{Style.RESET_ALL}")
            result, message = func()
            
            if result:
                print(f"{Fore.GREEN}✓ PASS: {message}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ FAIL: {message}{Style.RESET_ALL}")
            
            self.results.append((name, result, message))
            return result
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"{Fore.RED}✗ FAIL: {error_msg}{Style.RESET_ALL}")
            self.results.append((name, False, error_msg))
            return False
    
    def check_backend_api(self) -> Tuple[bool, str]:
        """Check if backend API is running"""
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return True, f"Backend API running (status: {data.get('status', 'unknown')})"
            return False, f"Backend returned status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Backend not reachable - is it running?"
        except Exception as e:
            return False, f"Error connecting to backend: {str(e)}"
    
    def check_chromadb(self) -> Tuple[bool, str]:
        """Check ChromaDB collections"""
        try:
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            collections = client.list_collections()
            
            expected_collections = ["bns_sections", "bnss_sections", "bsa_sections", "sc_judgements"]
            found_collections = [c.name for c in collections]
            
            missing = set(expected_collections) - set(found_collections)
            if missing:
                return False, f"Missing collections: {missing}"
            
            # Check collection sizes
            sizes = {}
            for coll_name in expected_collections:
                coll = client.get_collection(coll_name)
                count = coll.count()
                sizes[coll_name] = count
            
            total_docs = sum(sizes.values())
            return True, f"All 4 collections present ({total_docs} total documents): {sizes}"
        except Exception as e:
            return False, f"ChromaDB error: {str(e)}"
    
    def check_llm_service(self) -> Tuple[bool, str]:
        """Check LLM service (AIML API)"""
        try:
            # Test via chat endpoint
            response = requests.post(
                f"{BASE_URL}/api/v1/chat",
                json={"message": "Hello", "session_id": "health_check"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "response" in data and len(data["response"]) > 0:
                    return True, "LLM service responding correctly"
                return False, "LLM returned empty response"
            return False, f"LLM service returned status {response.status_code}"
        except Exception as e:
            return False, f"LLM service error: {str(e)}"
    
    def check_rag_service(self) -> Tuple[bool, str]:
        """Check RAG search service"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/search",
                json={
                    "query": "test query",
                    "collection": "bns_sections",
                    "top_k": 1
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if "results" in data:
                    return True, f"RAG service working ({len(data['results'])} results)"
                return False, "RAG returned invalid response"
            return False, f"RAG service returned status {response.status_code}"
        except Exception as e:
            return False, f"RAG service error: {str(e)}"
    
    def check_agent_service(self) -> Tuple[bool, str]:
        """Check LangGraph agent service"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/agent/query",
                json={
                    "query": "What is BNS Section 1?",
                    "session_id": "health_check_agent"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "response" in data and len(data["response"]) > 0:
                    return True, "Agent service responding correctly"
                return False, "Agent returned empty response"
            return False, f"Agent service returned status {response.status_code}"
        except Exception as e:
            return False, f"Agent service error: {str(e)}"
    
    def check_document_service(self) -> Tuple[bool, str]:
        """Check document generation service"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/documents/draft",
                json={
                    "document_type": "bail_application",
                    "content": {
                        "client_name": "Test Client",
                        "case_details": "Test case",
                        "legal_grounds": "Test grounds"
                    }
                },
                timeout=20
            )
            
            if response.status_code == 200:
                if len(response.content) > 1000:
                    return True, f"Document service working ({len(response.content)} bytes generated)"
                return False, "Document too small"
            return False, f"Document service returned status {response.status_code}"
        except Exception as e:
            return False, f"Document service error: {str(e)}"
    
    def check_streaming_endpoint(self) -> Tuple[bool, str]:
        """Check streaming endpoint"""
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/agent/stream",
                json={
                    "query": "Hello",
                    "session_id": "health_check_stream"
                },
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                # Try to read first chunk
                chunks = 0
                for line in response.iter_lines():
                    if line:
                        chunks += 1
                        if chunks >= 3:  # Read a few chunks
                            break
                
                if chunks > 0:
                    return True, f"Streaming endpoint working ({chunks} chunks received)"
                return False, "No streaming chunks received"
            return False, f"Streaming endpoint returned status {response.status_code}"
        except Exception as e:
            return False, f"Streaming endpoint error: {str(e)}"
    
    def check_all_endpoints(self) -> Tuple[bool, str]:
        """Check all API endpoints are registered"""
        try:
            response = requests.get(f"{BASE_URL}/docs", timeout=5)
            if response.status_code == 200:
                return True, "API documentation accessible"
            return False, f"API docs returned status {response.status_code}"
        except Exception as e:
            return False, f"API docs error: {str(e)}"
    
    def generate_report(self):
        """Generate health check report"""
        print("\n" + "=" * 80)
        print(f"{Fore.CYAN}HEALTH CHECK REPORT{Style.RESET_ALL}")
        print("=" * 80)
        
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        print(f"\nTotal Checks: {total}")
        print(f"{Fore.GREEN}Passed: {passed}{Style.RESET_ALL}")
        print(f"{Fore.RED}Failed: {total - passed}{Style.RESET_ALL}")
        
        print("\nDetailed Results:")
        print("-" * 80)
        
        for name, result, message in self.results:
            status = f"{Fore.GREEN}✓ PASS{Style.RESET_ALL}" if result else f"{Fore.RED}✗ FAIL{Style.RESET_ALL}"
            print(f"{status} | {name}")
            print(f"       {message}")
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"\nTime taken: {elapsed:.2f} seconds")
        
        print("\n" + "=" * 80)
        
        if passed == total:
            print(f"{Fore.GREEN}✓✓✓ ALL CHECKS PASSED - SYSTEM HEALTHY{Style.RESET_ALL}")
            return 0
        else:
            print(f"{Fore.RED}✗✗✗ SOME CHECKS FAILED - SYSTEM UNHEALTHY{Style.RESET_ALL}")
            return 1


def main():
    """Run health checks"""
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}LawAI System Health Check{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend URL: {BASE_URL}")
    
    checker = HealthChecker()
    
    # Run all checks
    checker.check("Backend API", checker.check_backend_api)
    checker.check("ChromaDB Collections", checker.check_chromadb)
    checker.check("LLM Service (AIML API)", checker.check_llm_service)
    checker.check("RAG Search Service", checker.check_rag_service)
    checker.check("Agent Service (LangGraph)", checker.check_agent_service)
    checker.check("Document Generation Service", checker.check_document_service)
    checker.check("Streaming Endpoint", checker.check_streaming_endpoint)
    checker.check("API Documentation", checker.check_all_endpoints)
    
    # Generate report
    exit_code = checker.generate_report()
    
    # Save report to file
    report_file = Path("health_check_report.txt")
    with open(report_file, "w") as f:
        f.write("LawAI Health Check Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 80}\n\n")
        
        for name, result, message in checker.results:
            status = "PASS" if result else "FAIL"
            f.write(f"[{status}] {name}\n")
            f.write(f"  {message}\n\n")
    
    print(f"\nReport saved to: {report_file}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

# Made with Bob
