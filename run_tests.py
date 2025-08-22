#!/usr/bin/env python3
"""
Enhanced test runner with options for the Orac project.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Run Orac tests",
        epilog="""
Examples:
  python run_tests.py                           # Run all tests
  python run_tests.py tests.test_orac          # Run specific module
  python run_tests.py tests.test_orac test_completion  # Run specific test in module
  python run_tests.py --unit                   # Run only unit tests
  python run_tests.py --external               # Run only external LLM tests (requires API keys)
  python run_tests.py --coverage               # Run with coverage
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--e2e", action="store_true", help="Run only end-to-end tests")
    parser.add_argument("--external", action="store_true", help="Run only external LLM tests (requires API keys)")
    parser.add_argument("--quick", action="store_true", help="Skip slow tests")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--html-coverage", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", "-n", type=int, help="Run tests in parallel (number of workers)")
    parser.add_argument("--pattern", help="Run tests matching pattern")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    parser.add_argument("module", nargs="?", help="Specific test module to run (e.g., tests.test_orac)")
    parser.add_argument("test", nargs="?", help="Specific test function to run (e.g., test_completion)")

    args = parser.parse_args()

    # Build pytest command
    cmd = ["pytest"]

    # Test selection
    if args.unit:
        cmd.extend(["-m", "unit"])
    elif args.integration:
        cmd.extend(["-m", "integration"])
    elif args.e2e:
        cmd.extend(["-m", "e2e"])
    elif args.external:
        cmd.extend(["-m", "external"])

    # Speed options
    if args.quick:
        cmd.extend(["-m", "not slow"])

    # Coverage options
    if args.coverage or args.html_coverage:
        cmd.extend(["--cov=orac", "--cov-report=term-missing"])
        if args.html_coverage:
            cmd.extend(["--cov-report=html:/tmp/orac-htmlcov"])

    # Output options
    if args.verbose:
        cmd.append("-v")

    # Performance options
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])

    # Pattern matching
    if args.pattern:
        cmd.extend(["-k", args.pattern])

    # Failure handling
    if args.fail_fast:
        cmd.append("-x")

    # Handle specific module/test selection
    if args.module:
        if args.test:
            # Run specific test in specific module
            cmd.append(f"{args.module}::{args.test}")
        else:
            # Run entire module
            cmd.append(args.module)
    elif args.test:
        # Run specific test across all modules
        cmd.extend(["-k", args.test])

    # Ensure we're in the right directory
    project_root = Path(__file__).parent
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {project_root}")
    print("-" * 50)
    
    # Run the tests
    result = subprocess.run(cmd, cwd=project_root)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("🎉 All tests passed!")
        if args.coverage or args.html_coverage:
            print("📊 Coverage report generated")
            if args.html_coverage:
                print("📁 HTML coverage report: /tmp/orac-htmlcov/index.html")
    else:
        print("\n" + "=" * 50)
        print("❌ Some tests failed")
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()