# High CPU and Memory Troubleshooting

## Overview
Guide for diagnosing and resolving high CPU/memory utilization on network devices.

## Symptoms
- CPU utilization consistently > 80%
- Memory utilization > 85%
- Connection timeouts during peak hours
- Intermittent packet loss
- Device becoming unresponsive

## Root Causes
1. **Inefficient ACL Processing**: Poorly ordered ACL rules
2. **BGP Route Learning**: Excessive routes from new peer
3. **High Connection Rate**: Overwhelming connection establishment rate
4. **Memory Leak**: Process accumulating memory over time
5. **Insufficient Hardware Capacity**: Device undersized for load

## Diagnostic Commands

### Check CPU Status
```
show processes cpu | include {CPU,process-name}
show processes cpu sorted
show processes cpu top 10
```

### Check Memory Status
```
show processes memory | include memory
show memory statistics
show memory free
```

### Identify Heavy Processes
```
show processes {process-name} | include {CPU,memory}
```

### Monitor Real-Time
```
show system load-average
show monitoring cpu history
```

## Resolution Steps

### For High CPU Due to ACL
1. Review ACL rules: `show access-lists {acl-name}`
2. Reorder rules:
   - Most specific rules first
   - Most frequently matched rules first
   - General DENY rules last
3. Consider consolidating overlapping rules
4. Implement hardware-based ACL processing (offload to ASIC)
5. Monitor CPU post-optimization (should drop 20-40%)

### For High CPU Due to BGP
1. Check BGP learned routes: `show ip bgp summary | include received`
2. Identify peer(s) advertising excessive routes
3. Implement route filtering:
   ```
   route-map FILTER permit 10
   match ip address prefix-list APPROVED
   ```
4. Apply filter: `neighbor {peer} route-map FILTER in`
5. Monitor BGP process CPU usage

### For High Memory
1. Identify memory-heavy process: `show processes memory | sort`
2. Determine if memory leak (increasing over time)
3. If leak: schedule device restart during maintenance window
4. Monitor memory post-restart to confirm fix

### For High Connection Rate
1. Implement connection rate limiting:
   ```
   connection-rate-limit 10000 per-second
   ```
2. Upgrade hardware if persistent (device at capacity)
3. Distribute load across multiple devices

## Validation
- CPU should be < 70% during peak hours
- Memory should be < 75% utilized
- All critical processes responsive
- No connection timeouts

## Capacity Planning
- Target: 50-60% CPU during peak load
- Monitor trends: if consistently > 70%, plan upgrade
- Reserve 25% capacity for traffic spikes

---
