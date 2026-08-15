# Runbook: VPN drops on new laptops

**Applies to:** Corp VPN (GlobalProtect) on freshly imaged laptops.

## Symptom
VPN connects, then drops after 30–60 seconds. Most common on laptops imaged after the 2026 fleet refresh.

## Root cause
The new image ships GlobalProtect 6.2, which defaults to IPv6. The corp gateway only advertises IPv4 routes, so the tunnel collapses when IPv6 traffic is attempted.

## Fix
1. Open GlobalProtect → Settings → Network.
2. Set **IP Protocol** to `IPv4 Only`.
3. Disconnect and reconnect the VPN.
4. If it still drops, flush DNS: `sudo dscacheutil -flushcache` (macOS) or `ipconfig /flushdns` (Windows).

## Escalation
If the tunnel still drops after the IPv4-only change, open a ticket with the **Network** team and attach the GlobalProtect logs from `~/Library/Logs/PaloAltoNetworks/`. Do not share your VPN credentials in the ticket.
