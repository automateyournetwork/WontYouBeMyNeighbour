"""
Pytest configuration file

Adds the project root to the Python path so tests can import modules.
"""
import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add /app in Docker environment
if '/app' not in sys.path and os.path.exists('/app/bgp'):
    sys.path.insert(0, '/app')
