#!/bin/bash
###############################################################################
# GRE Tunnel Setup Script for External FRR Router
#
# Creates the GRE tunnel interface to connect to Agentic Core Router
###############################################################################

set -e

echo "=== Setting up GRE tunnel to Agentic network ==="

# GRE Tunnel Parameters
LOCAL_IP="192.168.100.20"
REMOTE_IP="192.168.100.10"
TUNNEL_NAME="gre1"
TUNNEL_IP="10.255.0.2/30"
GRE_KEY="100"
TTL="255"

# Create dummy interface for external network simulation
echo "Creating simulated external network interface..."
ip link add ext-net type dummy 2>/dev/null || true
ip addr add 10.100.0.1/24 dev ext-net 2>/dev/null || true
ip link set ext-net up

# Delete existing tunnel if present
ip tunnel del $TUNNEL_NAME 2>/dev/null || true

# Create GRE tunnel
echo "Creating GRE tunnel: $LOCAL_IP -> $REMOTE_IP (key=$GRE_KEY)"
ip tunnel add $TUNNEL_NAME mode gre \
    local $LOCAL_IP \
    remote $REMOTE_IP \
    ttl $TTL \
    key $GRE_KEY

# Assign IP address to tunnel
echo "Assigning IP $TUNNEL_IP to $TUNNEL_NAME"
ip addr add $TUNNEL_IP dev $TUNNEL_NAME

# Bring up tunnel
echo "Bringing up tunnel interface"
ip link set $TUNNEL_NAME up

# Set MTU (account for GRE overhead)
ip link set $TUNNEL_NAME mtu 1400

# Verify
echo ""
echo "=== GRE Tunnel Status ==="
ip tunnel show $TUNNEL_NAME
echo ""
ip addr show $TUNNEL_NAME
echo ""

echo "=== GRE tunnel setup complete ==="
echo "Tunnel: $TUNNEL_NAME"
echo "Local:  $LOCAL_IP"
echo "Remote: $REMOTE_IP"
echo "Tunnel IP: $TUNNEL_IP"
echo "Key: $GRE_KEY"
echo ""
echo "Waiting for Agentic Core Router at $REMOTE_IP..."
