"""
ASI API Server Runner

Starts the ASI REST API server.
"""

import asyncio
import argparse

try:
    import uvicorn
    UVICORN_AVAILABLE = True
except ImportError:
    UVICORN_AVAILABLE = False


async def main():
    """Run ASI API server"""
    parser = argparse.ArgumentParser(description="ASI Network Agent API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--asi-id", default="asi-1", help="ASI instance ID")
    parser.add_argument("--openai-key", help="OpenAI API key")
    parser.add_argument("--claude-key", help="Anthropic Claude API key")
    parser.add_argument("--gemini-key", help="Google Gemini API key")
    parser.add_argument("--autonomous", action="store_true", help="Enable autonomous mode")

    args = parser.parse_args()

    if not UVICORN_AVAILABLE:
        print("Error: uvicorn not installed. Install with: pip install uvicorn")
        return

    # Import here to avoid circular dependency
    from ..integration.bridge import AgenticBridge
    from .server import create_api_server

    print(f"Starting ASI API Server...")
    print(f"  ASI ID: {args.asi_id}")
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print(f"  Autonomous Mode: {args.autonomous}")

    # Create agentic bridge
    bridge = AgenticBridge(
        asi_id=args.asi_id,
        openai_key=args.openai_key,
        claude_key=args.claude_key,
        gemini_key=args.gemini_key,
        autonomous_mode=args.autonomous
    )

    # Initialize
    await bridge.initialize()

    # Start bridge
    await bridge.start()

    # Create API server
    api, server_config = create_api_server(
        bridge,
        host=args.host,
        port=args.port
    )

    print(f"\n✓ ASI API Server ready!")
    print(f"\nAPI Endpoints:")
    print(f"  Health:      http://{args.host}:{args.port}/health")
    print(f"  Query:       http://{args.host}:{args.port}/api/query")
    print(f"  State:       http://{args.host}:{args.port}/api/state")
    print(f"  Statistics:  http://{args.host}:{args.port}/api/statistics")
    print(f"  Docs:        http://{args.host}:{args.port}/docs")
    print()

    # Run server
    config = uvicorn.Config(**server_config)
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        # Cleanup
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
