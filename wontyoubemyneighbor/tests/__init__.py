"""
Tests Package

Provides test infrastructure for the Won't You Be My Neighbor platform.
"""
import sys
import os

# Ensure the project root is in the path for all tests
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
