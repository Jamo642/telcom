# DNS Resolution Troubleshooting

## Overview
Guide for diagnosing and resolving DNS query timeouts and resolution failures.

## Symptoms
- DNS queries timing out (response > 5 seconds)
- "Resolution timeout" errors in client logs
- DNS cache hit rate dropped significantly
- 40%+ of queries returning SERVFAIL

## Root Causes
1. **Cache Memory Exhaustion**: Cache at 100% capacity, evicting entries
2. **Upstream DNS Unreachable**: Forwarders offline or unreachable
3. **Query Storms**: Excessive query volume overwhelming cache
4. **Configuration Error**: Cache size too small for domain volume

## Diagnostic Steps

### Check DNS Cache Status
```
show dns-cache statistics
show dns-cache memory
show dns-cache hit-rate
```
Key metrics:
- Cache hit rate (target: >80%)
- Memory utilization (should be <80%)
- Query response time (target: <100ms)

### Monitor Active Queries
```
show dns-cache active-queries
show dns-cache top-domains
```

### Verify Upstream Connectivity
```
nslookup google.com 8.8.8.8
dig @8.8.8.8 google.com +stats
```

## Resolution Steps

### For Cache Memory Issues
1. Increase cache size: `max_cache_size=1073741824` (1GB)
2. Adjust cache entry timeout: `cache_timeout=300` (5 minutes)
3. Enable query rate limiting: `max_queries_per_sec=1000`
4. Clear cache: `clear dns-cache` (one-time)
5. Monitor response times (should improve to <50ms)

### For Upstream Issues
1. Add DNS failover server:
   ```
   nameserver 8.8.8.8
   nameserver 8.8.4.4
   ```
2. Verify connectivity: `ping {nameserver-ip}`
3. Test specific query: `dig @{nameserver} {domain}`

### For Query Storms
1. Implement rate limiting per source IP
2. Enable query caching for higher TTLs
3. Monitor query patterns: identify botnet or malware

## Validation
- Response time: < 50ms (p95)
- Cache hit rate: > 80%
- Query success rate: > 99%
- No SERVFAIL responses

## Performance Targets
- **Average Response Time**: 10-50ms
- **Cache Hit Rate**: 80-95%
- **Failover Time**: < 500ms if primary down

---
