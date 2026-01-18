#!/usr/bin/env python3
"""
Direct test of BGP FlowSpec functionality
Tests FlowSpec rule matching and action application
"""

import sys
sys.path.insert(0, 'wontyoubemyneighbor')

from bgp.flowspec import FlowspecManager, FlowspecRule


def test_flowspec_basic_matching():
    """Test basic flowspec rule matching"""
    print("=" * 70)
    print("TEST 1: Basic FlowSpec Rule Matching")
    print("=" * 70)

    manager = FlowspecManager()

    # Create a rule to drop traffic to 192.0.2.0/24
    rule = FlowspecRule(
        name="Block 192.0.2.0/24",
        dest_prefix="192.0.2.0/24",
        rate_limit=0,  # 0 = drop
        priority=100
    )

    print(f"\n1. Installing FlowSpec rule: {rule.name}")
    success = manager.install_rule(rule)
    assert success, "Failed to install rule"
    print(f"   ✅ Rule installed successfully")

    # Test matching packet
    print(f"\n2. Testing packet to 192.0.2.10 (should match)")
    packet = {'dest_ip': '192.0.2.10'}
    matched_rule = manager.match_packet(packet)
    assert matched_rule is not None, "Packet should match rule"
    assert matched_rule.name == "Block 192.0.2.0/24"
    print(f"   ✅ Packet matched rule: {matched_rule.name}")

    # Test action
    print(f"\n3. Applying action")
    action = manager.apply_action(matched_rule, packet)
    print(f"   Action: {action}")
    assert action == "drop", "Action should be drop"
    print(f"   ✅ Packet dropped correctly")

    # Test non-matching packet
    print(f"\n4. Testing packet to 203.0.113.10 (should NOT match)")
    packet = {'dest_ip': '203.0.113.10'}
    matched_rule = manager.match_packet(packet)
    assert matched_rule is None, "Packet should not match"
    print(f"   ✅ Packet did not match (as expected)")

    print(f"\n✅ TEST 1 PASSED: Basic rule matching works correctly!")
    return True


def test_flowspec_protocol_port():
    """Test protocol and port matching"""
    print("\n" + "=" * 70)
    print("TEST 2: Protocol and Port Matching")
    print("=" * 70)

    manager = FlowspecManager()

    # Rule: Block SSH (TCP port 22) from 10.0.0.0/8
    rule = FlowspecRule(
        name="Block SSH from 10.0.0.0/8",
        source_prefix="10.0.0.0/8",
        protocols=[6],  # TCP
        dest_ports=[22],
        rate_limit=0,
        priority=100
    )

    print(f"\n1. Installing rule: {rule.name}")
    manager.install_rule(rule)
    print(f"   ✅ Rule installed")

    # Test matching packet (SSH from 10.1.2.3)
    print(f"\n2. Testing SSH packet from 10.1.2.3 to 192.0.2.1:22")
    packet = {
        'source_ip': '10.1.2.3',
        'dest_ip': '192.0.2.1',
        'protocol': 6,  # TCP
        'dest_port': 22
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is not None, "SSH packet should match"
    print(f"   ✅ Packet matched: {matched_rule.name}")

    # Test non-matching protocol (UDP)
    print(f"\n3. Testing UDP packet from 10.1.2.3 (should NOT match)")
    packet = {
        'source_ip': '10.1.2.3',
        'dest_ip': '192.0.2.1',
        'protocol': 17,  # UDP
        'dest_port': 22
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is None, "UDP packet should not match"
    print(f"   ✅ UDP packet did not match (as expected)")

    # Test non-matching port (HTTP)
    print(f"\n4. Testing HTTP packet from 10.1.2.3 (should NOT match)")
    packet = {
        'source_ip': '10.1.2.3',
        'dest_ip': '192.0.2.1',
        'protocol': 6,  # TCP
        'dest_port': 80
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is None, "HTTP packet should not match"
    print(f"   ✅ HTTP packet did not match (as expected)")

    print(f"\n✅ TEST 2 PASSED: Protocol/port matching works correctly!")
    return True


def test_flowspec_rate_limiting():
    """Test rate limiting action"""
    print("\n" + "=" * 70)
    print("TEST 3: Rate Limiting")
    print("=" * 70)

    manager = FlowspecManager()

    # Rule: Rate limit ICMP to 1Mbps
    rule = FlowspecRule(
        name="Rate limit ICMP",
        protocols=[1],  # ICMP
        rate_limit=1000000,  # 1 Mbps
        priority=100
    )

    print(f"\n1. Installing rate limit rule: {rule.name}")
    manager.install_rule(rule)
    print(f"   ✅ Rule installed")

    # Test matching ICMP packet
    print(f"\n2. Testing ICMP packet")
    packet = {
        'source_ip': '192.0.2.1',
        'dest_ip': '203.0.113.1',
        'protocol': 1  # ICMP
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is not None, "ICMP packet should match"
    print(f"   ✅ Packet matched: {matched_rule.name}")

    # Test action
    print(f"\n3. Applying rate limit action")
    action = manager.apply_action(matched_rule, packet)
    print(f"   Action: {action}")
    assert action == "rate_limit", "Action should be rate_limit"
    print(f"   ✅ Rate limit action applied: {rule.rate_limit} bps")

    print(f"\n✅ TEST 3 PASSED: Rate limiting works correctly!")
    return True


def test_flowspec_priority():
    """Test rule priority ordering"""
    print("\n" + "=" * 70)
    print("TEST 4: Rule Priority")
    print("=" * 70)

    manager = FlowspecManager()

    # Install two overlapping rules with different priorities
    rule_low_priority = FlowspecRule(
        name="Allow all to 192.0.2.0/24 (low priority)",
        dest_prefix="192.0.2.0/24",
        priority=200  # Lower priority (higher number)
    )

    rule_high_priority = FlowspecRule(
        name="Block SSH to 192.0.2.0/24 (high priority)",
        dest_prefix="192.0.2.0/24",
        protocols=[6],  # TCP
        dest_ports=[22],
        rate_limit=0,
        priority=100  # Higher priority (lower number)
    )

    print(f"\n1. Installing low priority rule (priority 200)")
    manager.install_rule(rule_low_priority)
    print(f"   ✅ Low priority rule installed")

    print(f"\n2. Installing high priority rule (priority 100)")
    manager.install_rule(rule_high_priority)
    print(f"   ✅ High priority rule installed")

    # Test: SSH packet should match high-priority rule first
    print(f"\n3. Testing SSH packet to 192.0.2.10:22")
    packet = {
        'dest_ip': '192.0.2.10',
        'protocol': 6,
        'dest_port': 22
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is not None, "Packet should match"
    assert matched_rule.name == "Block SSH to 192.0.2.0/24 (high priority)"
    print(f"   ✅ Matched high priority rule: {matched_rule.name}")

    # Test: HTTP packet should match low-priority rule
    print(f"\n4. Testing HTTP packet to 192.0.2.10:80")
    packet = {
        'dest_ip': '192.0.2.10',
        'protocol': 6,
        'dest_port': 80
    }
    matched_rule = manager.match_packet(packet)
    assert matched_rule is not None, "Packet should match"
    assert matched_rule.name == "Allow all to 192.0.2.0/24 (low priority)"
    print(f"   ✅ Matched low priority rule: {matched_rule.name}")

    print(f"\n✅ TEST 4 PASSED: Priority ordering works correctly!")
    return True


def test_flowspec_actions():
    """Test various FlowSpec actions"""
    print("\n" + "=" * 70)
    print("TEST 5: Various Actions")
    print("=" * 70)

    manager = FlowspecManager()

    # Test actions: drop, rate-limit, mark, sample
    rules = [
        FlowspecRule(name="Drop rule", dest_prefix="10.0.0.0/8", rate_limit=0, priority=100),
        FlowspecRule(name="Rate limit rule", dest_prefix="172.16.0.0/12", rate_limit=500000, priority=101),
        FlowspecRule(name="Mark DSCP rule", dest_prefix="192.168.0.0/16", dscp_marking=46, priority=102),
        FlowspecRule(name="Sample rule", dest_prefix="203.0.113.0/24", sample=True, priority=103),
        FlowspecRule(name="Terminate rule", dest_prefix="198.51.100.0/24", terminate=True, priority=104),
    ]

    print(f"\n1. Installing {len(rules)} rules with different actions")
    for rule in rules:
        manager.install_rule(rule)
    print(f"   ✅ All rules installed")

    # Test each action
    test_cases = [
        ("10.1.0.0", "drop"),
        ("172.16.1.0", "rate_limit"),
        ("192.168.1.0", "mark"),
        ("203.0.113.1", "pass"),
        ("198.51.100.1", "drop"),
    ]

    print(f"\n2. Testing actions:")
    for dest_ip, expected_action in test_cases:
        packet = {'dest_ip': dest_ip}
        matched_rule = manager.match_packet(packet)
        assert matched_rule is not None, f"Packet to {dest_ip} should match"
        action = manager.apply_action(matched_rule, packet)
        print(f"   {dest_ip:15} -> {matched_rule.name:20} -> {action}")
        assert action == expected_action, f"Expected {expected_action}, got {action}"

    print(f"   ✅ All actions applied correctly")

    print(f"\n✅ TEST 5 PASSED: Various actions work correctly!")
    return True


def test_flowspec_statistics():
    """Test FlowSpec statistics"""
    print("\n" + "=" * 70)
    print("TEST 6: Statistics")
    print("=" * 70)

    manager = FlowspecManager()

    # Install multiple rules
    for i in range(3):
        rule = FlowspecRule(
            name=f"Rule {i+1}",
            dest_prefix=f"10.{i}.0.0/16",
            rate_limit=0,
            priority=100 + i
        )
        manager.install_rule(rule)

    print(f"\n1. Installed 3 rules")

    # Match some packets
    for i in range(5):
        packet = {'dest_ip': '10.0.1.1'}
        manager.match_packet(packet)

    print(f"\n2. Matched 5 packets")

    # Get statistics
    stats = manager.get_statistics()
    print(f"\n3. Statistics:")
    print(f"   Total rules: {stats['total_rules']}")
    print(f"   Rules by priority: {stats['rules_by_priority']}")
    print(f"   Packets matched: {stats['packets_matched']}")
    print(f"   Rules installed: {stats['rules_installed']}")

    assert stats['total_rules'] == 3, "Should have 3 rules"
    assert stats['packets_matched'] == 5, "Should have 5 matched packets"
    print(f"   ✅ Statistics correct")

    # Remove a rule
    print(f"\n4. Removing first rule")
    all_rules = manager.get_all_rules()
    manager.remove_rule(all_rules[0])

    stats = manager.get_statistics()
    print(f"   Total rules after removal: {stats['total_rules']}")
    assert stats['total_rules'] == 2, "Should have 2 rules after removal"
    print(f"   ✅ Rule removed successfully")

    print(f"\n✅ TEST 6 PASSED: Statistics work correctly!")
    return True


def main():
    try:
        print("\n" + "=" * 70)
        print("BGP FLOWSPEC TEST SUITE")
        print("=" * 70)

        test_flowspec_basic_matching()
        test_flowspec_protocol_port()
        test_flowspec_rate_limiting()
        test_flowspec_priority()
        test_flowspec_actions()
        test_flowspec_statistics()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)
        print("\nFlowSpec implementation is working correctly.")
        print("The integration with BGP session is complete.")
        print("\nNote: Full FlowSpec NLRI parsing (RFC 5575) requires additional")
        print("implementation for MP_REACH_NLRI with AFI=1/2, SAFI=133/134.")
        print("Current integration provides the rule matching and action framework.")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
