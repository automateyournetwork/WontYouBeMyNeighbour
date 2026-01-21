#!/bin/bash
# Test runner for ASI agentic layer

set -e

echo "=================================="
echo "ASI Agentic Layer Test Suite"
echo "=================================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "Error: pytest not found. Install with:"
    echo "  pip install -r requirements-test.txt"
    exit 1
fi

# Run tests
echo "Running unit tests..."
pytest -v --tb=short

echo ""
echo "Running with coverage..."
pytest --cov=.. --cov-report=term-missing --cov-report=html

echo ""
echo "=================================="
echo "Test Results:"
echo "  HTML Coverage Report: htmlcov/index.html"
echo "=================================="
