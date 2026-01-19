#!/usr/bin/env python3
"""
Mr. Rogers - Chat Client for Ralph Agentic Network Router

This is a simple chat client that connects to a running Ralph agent via its REST API.
Launch this AFTER you've started wontyoubemyneighbor.py with the --agentic-api flag.

Usage:
    python3 mrrogers.py
    python3 mrrogers.py --host localhost --port 8080
    python3 mrrogers.py --batch "show ospf neighbors" "what is my network status"

Examples:
    # Interactive mode
    python3 mrrogers.py

    # Connect to specific host/port
    python3 mrrogers.py --host 192.168.1.100 --port 8080

    # Batch mode
    python3 mrrogers.py --batch "show ospf neighbors" "explain routing to 10.0.0.0/24"
"""

import sys
import argparse
import asyncio
import aiohttp
from typing import Optional, List


class MrRogers:
    """
    Chat client for Ralph agentic network router
    """

    def __init__(self, host: str = "localhost", port: int = 8080):
        """
        Initialize Mr. Rogers chat client

        Args:
            host: Ralph API host
            port: Ralph API port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def check_health(self) -> bool:
        """
        Check if Ralph API is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            async with self.session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status") == "healthy"
                return False
        except Exception as e:
            print(f"Error checking health: {e}")
            return False

    async def query(self, message: str) -> Optional[dict]:
        """
        Send a query to Ralph

        Args:
            message: Natural language query

        Returns:
            Response dictionary or None on error
        """
        try:
            async with self.session.post(
                f"{self.base_url}/api/query",
                json={"query": message}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    print(f"Error: HTTP {resp.status} - {error_text}")
                    return None
        except Exception as e:
            print(f"Error sending query: {e}")
            return None

    async def get_statistics(self) -> Optional[dict]:
        """
        Get Ralph statistics

        Returns:
            Statistics dictionary or None on error
        """
        try:
            async with self.session.get(f"{self.base_url}/api/statistics") as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return None

    async def interactive_chat(self):
        """
        Run interactive chat session
        """
        print("=" * 70)
        print("Welcome to Mr. Rogers - Ralph Chat Client")
        print("=" * 70)
        print(f"Connected to: {self.base_url}")
        print()
        print("Commands:")
        print("  /help     - Show this help")
        print("  /stats    - Show Ralph statistics")
        print("  /quit     - Exit chat")
        print("  /exit     - Exit chat")
        print()
        print("Just type your questions naturally!")
        print("=" * 70)
        print()

        # Check if Ralph is healthy
        print("Checking connection to Ralph...")
        if not await self.check_health():
            print(f"Error: Cannot connect to Ralph at {self.base_url}")
            print("Make sure wontyoubemyneighbor.py is running with --agentic-api flag")
            return

        print("✓ Connected to Ralph successfully")
        print()

        # Chat loop
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ["/quit", "/exit"]:
                    print("Goodbye!")
                    break

                elif user_input.lower() == "/help":
                    print()
                    print("Commands:")
                    print("  /help     - Show this help")
                    print("  /stats    - Show Ralph statistics")
                    print("  /quit     - Exit chat")
                    print("  /exit     - Exit chat")
                    print()
                    print("Examples:")
                    print("  Show me my OSPF neighbors")
                    print("  What is my network status?")
                    print("  How do I reach 10.0.0.0/24?")
                    print("  Are there any network issues?")
                    print("  Show BGP peers")
                    print()
                    continue

                elif user_input.lower() == "/stats":
                    stats = await self.get_statistics()
                    if stats:
                        print()
                        print("Ralph Statistics:")
                        print(f"  Turn: {stats.get('current_turn', 0)}/{stats.get('max_turns', 75)}")
                        print(f"  Conversation messages: {stats.get('conversation_messages', 0)}")
                        print(f"  Actions executed: {stats.get('actions_executed', 0)}")
                        print(f"  Decisions made: {stats.get('decisions_made', 0)}")
                        print()
                    continue

                # Send query to Ralph
                print("Ralph: ", end="", flush=True)
                response = await self.query(user_input)

                if response:
                    # Extract and print the response
                    answer = response.get("response", "No response")
                    print(answer)
                    print()

                    # Show intent if available
                    if "intent" in response:
                        intent = response["intent"]
                        print(f"  [Intent: {intent.get('intent_type', 'unknown')} "
                              f"(confidence: {intent.get('confidence', 0):.2f})]")
                        print()

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")

    async def batch_mode(self, queries: List[str]):
        """
        Run in batch mode with predefined queries

        Args:
            queries: List of queries to send
        """
        print("=" * 70)
        print("Mr. Rogers - Batch Mode")
        print("=" * 70)
        print(f"Connected to: {self.base_url}")
        print()

        # Check if Ralph is healthy
        if not await self.check_health():
            print(f"Error: Cannot connect to Ralph at {self.base_url}")
            return

        print("✓ Connected to Ralph successfully")
        print()

        # Execute queries
        for i, query in enumerate(queries, 1):
            print(f"Query {i}/{len(queries)}: {query}")
            print("-" * 70)

            response = await self.query(query)

            if response:
                answer = response.get("response", "No response")
                print(f"Ralph: {answer}")
                print()

                # Show intent if available
                if "intent" in response:
                    intent = response["intent"]
                    print(f"  [Intent: {intent.get('intent_type', 'unknown')} "
                          f"(confidence: {intent.get('confidence', 0):.2f})]")
                    print()
            else:
                print("Error: No response from Ralph")
                print()

            # Add spacing between queries
            if i < len(queries):
                print()


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Mr. Rogers - Chat Client for Ralph Agentic Network Router",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Interactive mode
  python3 mrrogers.py

  # Connect to specific host/port
  python3 mrrogers.py --host 192.168.1.100 --port 8080

  # Batch mode
  python3 mrrogers.py --batch "show ospf neighbors" "what is my network status"

Notes:
  - Launch this AFTER starting wontyoubemyneighbor.py with --agentic-api flag
  - Default connection is localhost:8080
        """
    )

    parser.add_argument("--host", default="localhost",
                       help="Ralph API host (default: localhost)")
    parser.add_argument("--port", type=int, default=8080,
                       help="Ralph API port (default: 8080)")
    parser.add_argument("--batch", nargs="+",
                       help="Run in batch mode with queries")

    args = parser.parse_args()

    # Create and run client
    async with MrRogers(host=args.host, port=args.port) as client:
        if args.batch:
            await client.batch_mode(args.batch)
        else:
            await client.interactive_chat()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
