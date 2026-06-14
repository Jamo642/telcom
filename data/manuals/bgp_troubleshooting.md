# BGP Troubleshooting Guide

## Overview
This guide covers diagnosing and resolving BGP (Border Gateway Protocol) issues.

## Common BGP Issues
1. **Adjacency Down**: BGP neighbor connection failed
2. **Slow Convergence**: Routes taking too long to propagate after topology change
3. **Prefix Leak**: Incorrect prefixes being advertised
4. **Route Flapping**: Routes repeatedly going up/down

## Root Causes
- Misconfigured BGP timers (too aggressive)
- Incorrect AS number configuration
- Firewall blocking BGP port 179
- BFD (Bidirectional Forwarding Detection) not enabled
- Authentication failure (MD5 mismatch)

## Diagnostic Commands

### Verify BGP Status
```
show ip bgp summary
show ip bgp neighbors 10.200.1.1
show ip bgp neighbors 10.200.1.1 received-routes
show ip bgp neighbors 10.200.1.1 advertised-routes
```

### Check BGP Timers
```
show ip bgp neighbors | include {Keepalives,Holdtime}
show ip bgp neighbors 10.200.1.1 detail
```

### Examine Route Information
```
show ip bgp {prefix}
show ip bgp flap-statistics
```

## Resolution Steps

### For Slow Convergence (> 60 seconds)
1. Reduce hold-time from 180s to 30s: `neighbor 10.200.1.1 timers 10 30`
2. Reduce keepalive from 60s to 10s
3. Enable BFD for sub-second detection: `neighbor 10.200.1.1 fall-over bfd`
4. Force hard reset: `clear ip bgp *` (causes brief disruption)
5. Or soft reset: `clear ip bgp 10.200.1.1 soft out/in` (no disruption)

### For Adjacency Issues
1. Verify connectivity: `ping 10.200.1.1` (must succeed)
2. Check BGP authentication: `show ip bgp neighbors 10.200.1.1 |include auth`
3. Verify firewall allows port 179: `telnet 10.200.1.1 179`
4. Correct MD5 password if mismatched: `neighbor 10.200.1.1 password {correct-password}`

### For Prefix Leaks
1. Review advertised routes: `show ip bgp neighbors 10.200.1.1 advertised-routes`
2. Compare against approved prefix-list
3. Apply route-map filter on export:
   ```
   route-map EXPORT permit 10
   match ip address prefix-list APPROVED
   ```
4. Force re-advertisement: `clear ip bgp 10.200.1.1 soft out`

## Validation
- BGP adjacency: should show "Established" status
- Convergence time: verify < 60 seconds after topology change
- Route count: verify expected number of routes learned
- No route flapping: verify flap-statistics shows stable count

## Performance Metrics
- **Target Convergence Time**: < 30 seconds (with BFD)
- **Keepalive Interval**: 10 seconds (recommended)
- **Hold Time**: 30-40 seconds (4x keepalive minimum)

---
