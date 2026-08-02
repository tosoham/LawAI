"""
Performance Testing Script for LawAI System
Measures response times, throughput, and resource usage
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import json
import time
from typing import Dict, List
from datetime import datetime
import statistics
import concurrent.futures
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
NUM_REQUESTS = 10
CONCURRENT_REQUESTS = 5


class PerformanceTester:
    """Performance testing suite"""
    
    def __init__(self):
        self.results: Dict[str, List[float]] = {}
        self.start_time = datetime.now()
    
    def measure_endpoint(self, name: str, method: str, url: str, payload: Dict = None, 
                        num_requests: int = NUM_REQUESTS) -> Dict:
        """Measure endpoint performance"""
        print(f"\n{Fore.CYAN}Testing: {name}{Style.RESET_ALL}")
        print(f"Endpoint: {method} {url}")
        print(f"Requests: {num_requests}")
        
        times = []
        errors = 0
        
        for i in range(num_requests):
            try:
                start = time.time()
                
                if method == "GET":
                    response = requests.get(url, timeout=60)
                elif method == "POST":
                    response = requests.post(url, json=payload, timeout=60)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                elapsed = time.time() - start
                
                if response.status_code == 200:
                    times.append(elapsed)
                    print(f"  Request {i+1}/{num_requests}: {elapsed:.3f}s ✓")
                else:
                    errors += 1
                    print(f"  Request {i+1}/{num_requests}: Error {response.status_code} ✗")
            
            except Exception as e:
                errors += 1
                print(f"  Request {i+1}/{num_requests}: Exception {str(e)[:50]} ✗")
        
        if not times:
            return {
                "name": name,
                "error": "All requests failed",
                "success_rate": 0
            }
        
        # Calculate statistics
        stats = {
            "name": name,
            "endpoint": f"{method} {url}",
            "num_requests": num_requests,
            "successful": len(times),
            "failed": errors,
            "success_rate": len(times) / num_requests * 100,
            "min_time": min(times),
            "max_time": max(times),
            "avg_time": statistics.mean(times),
            "median_time": statistics.median(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "total_time": sum(times)
        }
        
        # Print summary
        print(f"\n{Fore.GREEN}Results:{Style.RESET_ALL}")
        print(f"  Success Rate: {stats['success_rate']:.1f}%")
        print(f"  Min: {stats['min_time']:.3f}s")
        print(f"  Max: {stats['max_time']:.3f}s")
        print(f"  Avg: {stats['avg_time']:.3f}s")
        print(f"  Median: {stats['median_time']:.3f}s")
        
        self.results[name] = times
        return stats
    
    def test_concurrent_requests(self, name: str, method: str, url: str, 
                                 payload: Dict = None, num_workers: int = CONCURRENT_REQUESTS) -> Dict:
        """Test concurrent request handling"""
        print(f"\n{Fore.CYAN}Testing Concurrent: {name}{Style.RESET_ALL}")
        print(f"Concurrent Workers: {num_workers}")
        
        def make_request(i):
            try:
                start = time.time()
                
                if method == "GET":
                    response = requests.get(url, timeout=60)
                elif method == "POST":
                    # Add unique session ID for each request
                    req_payload = payload.copy()
                    if "session_id" in req_payload:
                        req_payload["session_id"] = f"{req_payload['session_id']}_{i}"
                    response = requests.post(url, json=req_payload, timeout=60)
                
                elapsed = time.time() - start
                return (response.status_code == 200, elapsed)
            except Exception as e:
                return (False, 0)
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_workers)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        total_time = time.time() - start_time
        
        successful = [r for r in results if r[0]]
        times = [r[1] for r in successful]
        
        stats = {
            "name": f"{name} (Concurrent)",
            "num_workers": num_workers,
            "successful": len(successful),
            "failed": num_workers - len(successful),
            "success_rate": len(successful) / num_workers * 100,
            "total_time": total_time,
            "throughput": num_workers / total_time if total_time > 0 else 0,
            "avg_response_time": statistics.mean(times) if times else 0
        }
        
        print(f"\n{Fore.GREEN}Concurrent Results:{Style.RESET_ALL}")
        print(f"  Success Rate: {stats['success_rate']:.1f}%")
        print(f"  Total Time: {stats['total_time']:.3f}s")
        print(f"  Throughput: {stats['throughput']:.2f} req/s")
        print(f"  Avg Response: {stats['avg_response_time']:.3f}s")
        
        return stats
    
    def generate_report(self, all_stats: List[Dict]):
        """Generate performance report"""
        print("\n" + "=" * 80)
        print(f"{Fore.CYAN}PERFORMANCE TEST REPORT{Style.RESET_ALL}")
        print("=" * 80)
        
        print("\nEndpoint Performance Summary:")
        print("-" * 80)
        
        for stats in all_stats:
            if "error" in stats:
                print(f"\n{Fore.RED}✗ {stats['name']}: {stats['error']}{Style.RESET_ALL}")
                continue
            
            print(f"\n{Fore.CYAN}{stats['name']}{Style.RESET_ALL}")
            
            if "num_workers" in stats:  # Concurrent test
                print(f"  Workers: {stats['num_workers']}")
                print(f"  Success Rate: {stats['success_rate']:.1f}%")
                print(f"  Throughput: {stats['throughput']:.2f} req/s")
                print(f"  Avg Response: {stats['avg_response_time']:.3f}s")
            else:  # Sequential test
                print(f"  Requests: {stats['num_requests']}")
                print(f"  Success Rate: {stats['success_rate']:.1f}%")
                print(f"  Min/Max/Avg: {stats['min_time']:.3f}s / {stats['max_time']:.3f}s / {stats['avg_time']:.3f}s")
                print(f"  Median: {stats['median_time']:.3f}s")
        
        # Performance targets check
        print("\n" + "=" * 80)
        print(f"{Fore.CYAN}Performance Targets Check:{Style.RESET_ALL}")
        print("-" * 80)
        
        targets = {
            "Agent Query": 10.0,
            "RAG Search": 5.0,
            "Document Draft": 20.0,
            "Document Analysis": 10.0,
            "Chat": 5.0
        }
        
        for stats in all_stats:
            name = stats["name"]
            if name in targets and "avg_time" in stats:
                target = targets[name]
                actual = stats["avg_time"]
                
                if actual <= target:
                    print(f"{Fore.GREEN}✓ {name}: {actual:.2f}s (target: {target}s){Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⚠ {name}: {actual:.2f}s (target: {target}s) - SLOW{Style.RESET_ALL}")
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"\nTotal test time: {elapsed:.2f} seconds")
        print("=" * 80)


def main():
    """Run performance tests"""
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}LawAI Performance Testing{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend URL: {BASE_URL}")
    
    tester = PerformanceTester()
    all_stats = []
    
    # Test 1: Health Check (baseline)
    stats = tester.measure_endpoint(
        "Health Check",
        "GET",
        f"{BASE_URL}/health",
        num_requests=20
    )
    all_stats.append(stats)
    
    # Test 2: RAG Search
    stats = tester.measure_endpoint(
        "RAG Search",
        "POST",
        f"{BASE_URL}/api/v1/search",
        payload={
            "query": "What is BNS Section 103?",
            "collection": "bns_sections",
            "top_k": 5
        },
        num_requests=10
    )
    all_stats.append(stats)
    
    # Test 3: Chat
    stats = tester.measure_endpoint(
        "Chat",
        "POST",
        f"{BASE_URL}/api/v1/chat",
        payload={
            "message": "Explain anticipatory bail",
            "session_id": "perf_test_chat"
        },
        num_requests=5
    )
    all_stats.append(stats)
    
    # Test 4: Agent Query
    stats = tester.measure_endpoint(
        "Agent Query",
        "POST",
        f"{BASE_URL}/api/v1/agent/query",
        payload={
            "query": "What are the provisions for bail in BNS Section 103?",
            "session_id": "perf_test_agent"
        },
        num_requests=5
    )
    all_stats.append(stats)
    
    # Test 5: Document Analysis
    stats = tester.measure_endpoint(
        "Document Analysis",
        "POST",
        f"{BASE_URL}/api/v1/documents/analyze",
        payload={
            "text": "Sample rental agreement with standard clauses for analysis",
            "analysis_type": "risk_analysis"
        },
        num_requests=5
    )
    all_stats.append(stats)
    
    # Test 6: Document Draft
    stats = tester.measure_endpoint(
        "Document Draft",
        "POST",
        f"{BASE_URL}/api/v1/documents/draft",
        payload={
            "document_type": "bail_application",
            "content": {
                "client_name": "Test Client",
                "case_details": "Test case details",
                "legal_grounds": "Test legal grounds"
            }
        },
        num_requests=3
    )
    all_stats.append(stats)
    
    # Test 7: Concurrent Requests
    stats = tester.test_concurrent_requests(
        "Concurrent Chat",
        "POST",
        f"{BASE_URL}/api/v1/chat",
        payload={
            "message": "What is BNS?",
            "session_id": "perf_test_concurrent"
        },
        num_workers=5
    )
    all_stats.append(stats)
    
    # Generate report
    tester.generate_report(all_stats)
    
    # Save report to file
    report_file = Path("performance_test_report.json")
    with open(report_file, "w") as f:
        json.dump(all_stats, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")


if __name__ == "__main__":
    main()
