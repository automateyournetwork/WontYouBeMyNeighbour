"""
ASI Agentic Network Router - Main Entry Point

Usage:
    python -m wontyoubemyneighbor.agentic --help
    python -m wontyoubemyneighbor.agentic cli
    python -m wontyoubemyneighbor.agentic api
    python -m wontyoubemyneighbor.agentic demo
"""

import sys
import argparse


def main():
    """Main entry point for ASI agentic interface"""
    parser = argparse.ArgumentParser(
        description="ASI: Agentic Network Router",
        epilog="For more information, see wontyoubemyneighbor/agentic/README.md"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # CLI command
    cli_parser = subparsers.add_parser("cli", help="Start interactive CLI")
    cli_parser.add_argument("--asi-id", default="asi-cli", help="ASI instance ID")
    cli_parser.add_argument("--openai-key", help="OpenAI API key")
    cli_parser.add_argument("--claude-key", help="Anthropic Claude API key")
    cli_parser.add_argument("--gemini-key", help="Google Gemini API key")
    cli_parser.add_argument("--autonomous", action="store_true", help="Enable autonomous mode")
    cli_parser.add_argument("--batch", nargs="+", help="Run in batch mode")

    # API command
    api_parser = subparsers.add_parser("api", help="Start REST API server")
    api_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    api_parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    api_parser.add_argument("--asi-id", default="asi-api", help="ASI instance ID")
    api_parser.add_argument("--openai-key", help="OpenAI API key")
    api_parser.add_argument("--claude-key", help="Anthropic Claude API key")
    api_parser.add_argument("--gemini-key", help="Google Gemini API key")
    api_parser.add_argument("--autonomous", action="store_true", help="Enable autonomous mode")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run demonstration")

    # Version command
    version_parser = subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "cli":
        # Run CLI
        from .cli.chat import run_cli
        import asyncio
        asyncio.run(run_cli())

    elif args.command == "api":
        # Run API server
        from .api.run_server import main as run_api
        import asyncio
        asyncio.run(run_api())

    elif args.command == "demo":
        # Run demo
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from examples.agentic_demo import main as run_demo
        import asyncio
        asyncio.run(run_demo())

    elif args.command == "version":
        from . import __version__, __author__
        print(f"ASI Agentic Network Router v{__version__}")
        print(f"Author: {__author__}")


if __name__ == "__main__":
    main()
