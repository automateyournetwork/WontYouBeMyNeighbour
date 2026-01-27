#!/bin/bash
# Docker entrypoint script for ASI Agent containers
# Starts LLDP daemon for Layer 2 neighbor discovery, then runs the agent

# Start LLDP daemon in the background
# -d: daemonize, -c: configure mode, -e: enable receiving
if command -v lldpd &> /dev/null; then
    echo "Starting LLDP daemon..."
    # Start lldpd with agent name as system name
    SYSTEM_NAME="${AGENT_NAME:-asi-agent}"
    SYSTEM_DESC="ASI Agent - Won't You Be My Neighbor"

    # Start lldpd daemon
    lldpd -c -e

    # Configure system info via lldpcli
    sleep 1
    lldpcli configure system hostname "$SYSTEM_NAME" 2>/dev/null || true
    lldpcli configure system description "$SYSTEM_DESC" 2>/dev/null || true

    echo "LLDP daemon started"
else
    echo "Warning: lldpd not installed, LLDP discovery disabled"
fi

# Execute the main command (passed as arguments)
exec "$@"
