#!/usr/bin/env python3
"""
LawAI Setup Verification Script

This script verifies that the development environment is properly configured.
Run this after completing Phase 1 setup.
"""

import sys
import os
import subprocess
from pathlib import Path
from typing import Tuple, List


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_success(text: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_warning(text: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def check_python_version() -> Tuple[bool, str]:
    """Check if Python version is 3.10 or higher"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor}.{version.micro} (requires 3.10+)"


def check_command_exists(command: str) -> Tuple[bool, str]:
    """Check if a command exists in PATH"""
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            return True, version
        return False, "Command failed"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "Not found"


def check_directory_structure() -> Tuple[bool, List[str]]:
    """Check if required directories exist"""
    required_dirs = [
        "backend",
        "backend/agents",
        "backend/tools",
        "backend/models",
        "backend/services",
        "backend/api/v1",
        "backend/tests",
        "frontend",
        "frontend/components",
        "frontend/pages",
        "frontend/lib",
        "frontend/styles",
        "data/raw",
        "data/processed",
        "scripts",
        "docs"
    ]
    
    missing_dirs = []
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)
    
    return len(missing_dirs) == 0, missing_dirs


def check_required_files() -> Tuple[bool, List[str]]:
    """Check if required files exist"""
    required_files = [
        "backend/requirements.txt",
        "backend/.env.example",
        "backend/main.py",
        "backend/__init__.py",
        "frontend/package.json",
        "frontend/tsconfig.json",
        "frontend/tailwind.config.js",
        "frontend/.env.local.example",
        ".gitignore",
        "README.md",
        "AGENTS.md",
        "RULES.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    return len(missing_files) == 0, missing_files


def check_backend_dependencies() -> Tuple[bool, str]:
    """Check if backend dependencies can be imported"""
    try:
        # Try importing key packages
        import fastapi
        import uvicorn
        import pydantic
        return True, "All key packages available"
    except ImportError as e:
        return False, f"Missing package: {str(e)}"


def check_node_modules() -> Tuple[bool, str]:
    """Check if frontend node_modules exist"""
    node_modules_path = Path("frontend/node_modules")
    if node_modules_path.exists():
        return True, "node_modules directory exists"
    return False, "node_modules not found (run 'npm install' in frontend/)"


def main():
    """Main verification function"""
    print_header("LawAI Setup Verification")
    
    all_checks_passed = True
    
    # Check Python version
    print(f"{Colors.BOLD}1. Checking Python version...{Colors.RESET}")
    success, message = check_python_version()
    if success:
        print_success(message)
    else:
        print_error(message)
        all_checks_passed = False
    
    # Check Node.js
    print(f"\n{Colors.BOLD}2. Checking Node.js...{Colors.RESET}")
    success, message = check_command_exists("node")
    if success:
        print_success(f"Node.js: {message}")
    else:
        print_error(f"Node.js: {message}")
        all_checks_passed = False
    
    # Check npm
    print(f"\n{Colors.BOLD}3. Checking npm...{Colors.RESET}")
    success, message = check_command_exists("npm")
    if success:
        print_success(f"npm: {message}")
    else:
        print_error(f"npm: {message}")
        all_checks_passed = False
    
    # Check directory structure
    print(f"\n{Colors.BOLD}4. Checking directory structure...{Colors.RESET}")
    success, missing = check_directory_structure()
    if success:
        print_success("All required directories exist")
    else:
        print_error(f"Missing directories: {len(missing)}")
        for dir_path in missing:
            print(f"  - {dir_path}")
        all_checks_passed = False
    
    # Check required files
    print(f"\n{Colors.BOLD}5. Checking required files...{Colors.RESET}")
    success, missing = check_required_files()
    if success:
        print_success("All required files exist")
    else:
        print_error(f"Missing files: {len(missing)}")
        for file_path in missing:
            print(f"  - {file_path}")
        all_checks_passed = False
    
    # Check backend dependencies (optional - may not be installed yet)
    print(f"\n{Colors.BOLD}6. Checking backend dependencies...{Colors.RESET}")
    success, message = check_backend_dependencies()
    if success:
        print_success(message)
    else:
        print_warning(f"{message} (run 'pip install -r backend/requirements.txt')")
    
    # Check frontend dependencies (optional - may not be installed yet)
    print(f"\n{Colors.BOLD}7. Checking frontend dependencies...{Colors.RESET}")
    success, message = check_node_modules()
    if success:
        print_success(message)
    else:
        print_warning(message)
    
    # Final summary
    print_header("Verification Summary")
    
    if all_checks_passed:
        print_success("✓ All critical checks passed!")
        print(f"\n{Colors.GREEN}Phase 1 setup is complete!{Colors.RESET}")
        print(f"\n{Colors.BOLD}Next steps:{Colors.RESET}")
        print("1. Install backend dependencies: cd backend && pip install -r requirements.txt")
        print("2. Install frontend dependencies: cd frontend && npm install")
        print("3. Configure environment variables:")
        print("   - Copy backend/.env.example to backend/.env")
        print("   - Copy frontend/.env.local.example to frontend/.env.local")
        print("4. Proceed to Phase 2: Backend Core Infrastructure")
        return 0
    else:
        print_error("✗ Some checks failed")
        print(f"\n{Colors.RED}Please fix the issues above before proceeding.{Colors.RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
