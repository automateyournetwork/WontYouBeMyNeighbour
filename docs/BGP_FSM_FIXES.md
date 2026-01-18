# BGP OpenConfirm FSM Error - Root Cause and Fixes

## Problem
BGP sessions were reaching OpenConfirm state but then FRR was sending NOTIFICATION with "Finite State Machine Error (code=5, subcode=1)".

## Root Causes Identified

### 1. Duplicate KEEPALIVE Messages (session.py:437-444)
**Problem**: When receiving an OPEN message in OpenSent state, the code was sending TWO KEEPALIVEs:
- First KEEPALIVE: Sent automatically by FSM via `on_send_keepalive()` callback
- Second KEEPALIVE: Explicit send added as attempted fix

**Impact**: FRR likely interpreted the duplicate/rapid KEEPALIVE messages as an FSM protocol violation.

**Fix**: Removed the explicit KEEPALIVE send. The FSM callback is sufficient and correct per RFC 4271.

**File**: `wontyoubemyneighbor/bgp/session.py`
```python
# BEFORE (INCORRECT):
await self.fsm.process_event(BGPEvent.BGPOpen)
keepalive = BGPKeepalive()
await self._send_message(keepalive)  # DUPLICATE!

# AFTER (CORRECT):
await self.fsm.process_event(BGPEvent.BGPOpen)
# FSM automatically sends KEEPALIVE via callback
```

### 2. Hold Timer Stopped in OpenConfirm State (fsm.py:303-307)
**Problem**: When transitioning from OpenSent to OpenConfirm upon receiving OPEN, the code was STOPPING the hold timer instead of RESTARTING it.

**Impact**:
- Per RFC 4271 Section 8.2.2.4, the hold timer MUST continue running in OpenConfirm state
- The hold timer is used to detect if the peer fails to send KEEPALIVEs
- Stopping it meant we weren't properly monitoring peer liveness
- FRR might have detected this violation or timing issues occurred

**Fix**: Changed `_stop_hold_timer()` to `_start_hold_timer()` to restart the hold timer with the negotiated hold time.

**File**: `wontyoubemyneighbor/bgp/fsm.py`
```python
# BEFORE (INCORRECT):
self._stop_hold_timer()  # WRONG! Hold timer should keep running
self._start_keepalive_timer()

# AFTER (CORRECT):
self._start_hold_timer()  # Restart hold timer with negotiated time
self._start_keepalive_timer()
```

## RFC 4271 Compliance

### OpenSent State (Section 8.2.2.3)
When OPEN message is received:
1. Perform collision detection (if applicable)
2. Set negotiated hold time
3. ✅ **Restart hold timer** (fixed!)
4. ✅ Set keepalive timer
5. ✅ Send KEEPALIVE (once!)
6. ✅ Transition to OpenConfirm

### OpenConfirm State (Section 8.2.2.4)
- ✅ Hold timer continues running
- ✅ When KEEPALIVE received: restart hold timer, transition to Established
- ✅ When keepalive timer expires: send KEEPALIVE, restart keepalive timer
- ✅ When hold timer expires: send NOTIFICATION (Hold Timer Expired), go to Idle

## Testing

### Expected Behavior After Fixes
1. Agent sends OPEN → OpenSent state
2. FRR sends OPEN → Agent receives it
3. Agent sends KEEPALIVE (once) → OpenConfirm state
4. Agent hold timer restarts and keeps running
5. FRR sends KEEPALIVE → Agent receives it
6. Agent restarts hold timer → Established state
7. Keepalive timers maintain the session

### Test Commands
```bash
# Start containers (if not running)
# docker start ospf-router bgp-router multi-protocol-agent

# Check BGP status on FRR side
docker exec bgp-router vtysh -c "show ip bgp summary"
docker exec bgp-router vtysh -c "show ip bgp neighbors 172.20.0.4"

# Check agent logs for BGP session establishment
docker logs multi-protocol-agent --tail 100 | grep -E "(BGP|Established|KEEPALIVE|OPEN)"

# Expected log sequence:
# - "Sending OPEN"
# - "Received OPEN: AS=..., ID=..., HoldTime=..."
# - "Negotiated hold time: ..."
# - "FSM state: OpenSent → OpenConfirm"
# - "Sending KEEPALIVE" (only once!)
# - "Received KEEPALIVE"
# - "FSM state: OpenConfirm → Established"
# - "BGP session ESTABLISHED with 172.20.0.2"

# Verify route learning
docker exec bgp-router vtysh -c "show ip bgp"
# Should show routes advertised from agent

# Check kernel routes on agent
docker exec multi-protocol-agent ip route show
# Should show: 20.20.20.1 via 172.20.0.2 dev eth0 proto bgp metric 20
```

## Files Modified
1. `wontyoubemyneighbor/bgp/session.py` - Removed duplicate KEEPALIVE send
2. `wontyoubemyneighbor/bgp/fsm.py` - Fixed hold timer restart in OpenSent→OpenConfirm transition

## Next Steps
1. Restart the agent with fixed code
2. Verify BGP reaches Established state
3. Confirm agent learns 20.20.20.1/32 route from BGP
4. Test bidirectional pings between OSPF and BGP loopbacks
