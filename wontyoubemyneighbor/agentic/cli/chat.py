"""
Ralph CLI Chat Interface

Interactive command-line interface for natural language network management.
"""

import asyncio
import argparse
import sys
from typing import Optional
from datetime import datetime

try:
    import readline  # For command history
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False


class RalphCLI:
    """
    Interactive CLI for chatting with Ralph.

    Features:
    - Natural language queries
    - Command history (if readline available)
    - Multi-line input support
    - Special commands (/help, /stats, /quit)
    - Color output (if supported)
    """

    def __init__(self, agentic_bridge):
        self.bridge = agentic_bridge
        self.running = False

        # Command history
        self.history = []

        # Special commands
        self.commands = {
            "/help": self._cmd_help,
            "/stats": self._cmd_stats,
            "/state": self._cmd_state,
            "/anomalies": self._cmd_anomalies,
            "/history": self._cmd_history,
            "/reset": self._cmd_reset,
            "/quit": self._cmd_quit,
            "/exit": self._cmd_quit,
        }

    def _print_banner(self):
        """Print welcome banner"""
        print()
        print("=" * 60)
        print("       Ralph - Your Agentic Network Router")
        print("=" * 60)
        print(f"  Ralph ID: {self.bridge.ralph_id}")
        print(f"  LLM Providers: {len(self.bridge.llm.providers)}")
        print(f"  Turn Limit: {self.bridge.llm.max_turns}")
        print()
        print("  Type your question in natural language")
        print("  Use /help for special commands")
        print("  Use /quit to exit")
        print("=" * 60)
        print()

    def _print_prompt(self):
        """Print input prompt"""
        turn_info = f"[{self.bridge.llm.current_turn}/{self.bridge.llm.max_turns}]"
        sys.stdout.write(f"\n{turn_info} You: ")
        sys.stdout.flush()

    async def _cmd_help(self, args):
        """Show help"""
        print("\nRalph CLI Commands:")
        print()
        print("  /help       - Show this help")
        print("  /stats      - Show statistics")
        print("  /state      - Show network state")
        print("  /anomalies  - Detect anomalies")
        print("  /history    - Show conversation history")
        print("  /reset      - Reset conversation")
        print("  /quit       - Exit CLI")
        print()
        print("Example queries:")
        print("  • Show me my OSPF neighbors")
        print("  • What's the status of BGP peer 192.168.1.2?")
        print("  • Are there any network issues?")
        print("  • How do I reach 10.0.0.1?")
        print("  • Increase OSPF cost on eth0 to 20")

    async def _cmd_stats(self, args):
        """Show statistics"""
        stats = self.bridge.get_statistics()

        print("\nRalph Statistics:")
        print()
        print(f"LLM:")
        print(f"  Turns: {stats['llm']['turns']}/{stats['llm']['max_turns']}")
        print(f"  Providers: {stats['llm']['providers']}")
        print()
        print(f"State:")
        print(f"  Snapshots: {stats['state']['snapshots']}")
        print(f"  Health: {stats['state']['metrics'].get('health_score', 0):.1f}/100")
        print()
        print(f"Actions:")
        print(f"  Completed: {stats['actions']['completed']}")
        print(f"  Pending: {stats['actions']['pending']}")
        print()
        print(f"Gossip:")
        print(f"  Peers: {stats['gossip']['peers']}")
        print(f"  Messages Seen: {stats['gossip']['messages_seen']}")

    async def _cmd_state(self, args):
        """Show network state"""
        await self.bridge.state_manager.update_state()
        summary = self.bridge.state_manager.get_state_summary()
        print()
        print(summary)

    async def _cmd_anomalies(self, args):
        """Detect anomalies"""
        network_state = self.bridge.state_manager.get_llm_context()
        anomalies = await self.bridge.decision_engine.detect_anomalies(network_state)

        if not anomalies:
            print("\n✓ No anomalies detected. Network appears healthy.")
        else:
            print(f"\n⚠ Detected {len(anomalies)} anomalies:\n")
            for i, anomaly in enumerate(anomalies, 1):
                print(f"{i}. [{anomaly['severity'].upper()}] {anomaly['type']}")
                print(f"   {anomaly['description']}")
                print(f"   → {anomaly['recommendation']}")
                print()

    async def _cmd_history(self, args):
        """Show conversation history"""
        history = self.bridge.llm.get_conversation_history()

        if not history:
            print("\nNo conversation history yet.")
            return

        print(f"\nConversation History ({len(history)} messages):\n")
        for i, msg in enumerate(history[-10:], 1):  # Show last 10
            role = msg['role'].capitalize()
            content = msg['content'][:100]  # Truncate long messages
            timestamp = msg.get('timestamp', '')[:19]  # Just date and time

            print(f"{i}. [{timestamp}] {role}:")
            print(f"   {content}...")
            print()

    async def _cmd_reset(self, args):
        """Reset conversation"""
        self.bridge.llm.reset_conversation()
        print(f"\n✓ Conversation reset. Ready for {self.bridge.llm.max_turns} turns.")

    async def _cmd_quit(self, args):
        """Quit CLI"""
        self.running = False
        print("\nGoodbye! 👋")

    async def _process_input(self, user_input: str):
        """Process user input"""
        user_input = user_input.strip()

        if not user_input:
            return

        # Check for special command
        parts = user_input.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command in self.commands:
            await self.commands[command](args)
            return

        # Regular query
        try:
            print()
            print("Ralph: ", end="", flush=True)

            response = await self.bridge.query(user_input)

            if response:
                print(response)
            else:
                print("[No response]")

            # Add to history
            self.history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "query": user_input,
                "response": response
            })

        except Exception as e:
            print(f"Error: {e}")

    async def run(self):
        """Run interactive CLI"""
        self._print_banner()

        self.running = True

        while self.running:
            try:
                self._print_prompt()

                # Read input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, input
                )

                await self._process_input(user_input)

            except (KeyboardInterrupt, EOFError):
                print()
                self.running = False
                print("\nGoodbye! 👋")
                break

            except Exception as e:
                print(f"\nError: {e}")

    async def run_batch(self, queries: list):
        """
        Run in batch mode with predefined queries.

        Useful for demos or testing.
        """
        self._print_banner()

        print("Running in batch mode...\n")

        for i, query in enumerate(queries, 1):
            print(f"[{i}/{len(queries)}] You: {query}")

            response = await self.bridge.query(query)

            print(f"Ralph: {response}\n")

            await asyncio.sleep(0.5)  # Small delay between queries

        print("Batch mode complete!")


async def run_cli():
    """
    Run Ralph CLI from command line.

    Usage:
        python -m wontyoubemyneighbor.agentic.cli.chat
    """
    parser = argparse.ArgumentParser(description="Ralph Network Agent CLI")
    parser.add_argument("--ralph-id", default="ralph-cli", help="Ralph instance ID")
    parser.add_argument("--openai-key", help="OpenAI API key")
    parser.add_argument("--claude-key", help="Anthropic Claude API key")
    parser.add_argument("--gemini-key", help="Google Gemini API key")
    parser.add_argument("--autonomous", action="store_true", help="Enable autonomous mode")
    parser.add_argument("--batch", nargs="+", help="Run in batch mode with queries")

    args = parser.parse_args()

    # Import here to avoid circular dependency
    from ..integration.bridge import AgenticBridge

    # Create agentic bridge
    bridge = AgenticBridge(
        ralph_id=args.ralph_id,
        openai_key=args.openai_key,
        claude_key=args.claude_key,
        gemini_key=args.gemini_key,
        autonomous_mode=args.autonomous
    )

    # Initialize
    print("Initializing Ralph...")
    await bridge.initialize()

    # Start bridge
    await bridge.start()

    # Create CLI
    cli = RalphCLI(bridge)

    try:
        if args.batch:
            # Run in batch mode
            await cli.run_batch(args.batch)
        else:
            # Run interactive mode
            await cli.run()
    finally:
        # Cleanup
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(run_cli())
