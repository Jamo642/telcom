# Interface Hardware Troubleshooting

## Overview
Comprehensive guide for diagnosing and resolving interface hardware and link layer issues.

## Common Issues
1. **Link Flapping**: Interface repeatedly going up/down
2. **Duplex Mismatch**: Half-duplex on one side, full-duplex on other
3. **CRC Errors**: High Frame Check Sequence (FCS) error rate
4. **MTU Mismatch**: Packets fragmented or dropped due to size mismatch

## Root Causes
- **Faulty fiber/cable**: Dirty connectors, bent fiber, physical damage
- **Auto-negotiation failure**: Speed/duplex mismatch between devices
- **Driver bug**: Outdated or buggy network interface driver
- **Hardware failure**: Degraded or failed transceiver/interface card

## Diagnostic Commands

### Check Interface Status
```
show interfaces gigabitethernet 3/0/1 | include {state,speed,duplex}
show interfaces statistics
```

### Monitor for Flapping
```
show interfaces flap-history
show interfaces {interface} counters
```
Look for increasing error counts over time.

### Verify MTU Configuration
```
show interfaces | include MTU
show interfaces configuration | include mtu
```

## Resolution Steps

### For Link Flapping
1. Disable interface: `shutdown`
2. Inspect physical connection:
   - Clean fiber connector with lint-free cloth
   - Check cable for visible damage
3. Re-enable: `no shutdown`
4. Monitor for 10 minutes using: `show interfaces {interface}`
5. If still flapping: replace SFP/interface card

### For Duplex Mismatch
1. Connect to affected interface
2. Check current duplex: `show interfaces fastethernet 0/1`
3. Verify peer duplex (contact peer team)
4. Force correct duplex: `speed 100 duplex full`
5. Disable auto-negotiation: `no negotiate`
6. Clear counters: `clear counters fastethernet 0/1`
7. Re-enable if resolved

### For High Error Rates
1. If fiber interface:
   - Clean connectors
   - Verify fiber not bent or pinched
   - Replace transceiver if errors persist
2. If copper: replace cable
3. If errors on interface card: replace card

### For MTU Issues
1. Determine maximum MTU needed:
   - Ethernet standard: 1500
   - MPLS/VPN: 1600 (accounts for labels + overhead)
2. Update MTU: `ip mtu 1600`
3. Update peer interface(s) to match
4. Test: `ping {dest} -df -s 1400` (don't-fragment flag)
5. Verify no packet fragmentation

## Validation
- Interface should show "UP/UP" status continuously
- No errors/discards: run `show interfaces` and verify error counters = 0
- Duplex match: verify both sides full-duplex (if possible)
- MTU: test large packets without fragmentation

## Performance Targets
- **Error Rate**: < 0.01%
- **Flap Stability**: no flaps over 24-hour period
- **Link Availability**: > 99.99%

---
