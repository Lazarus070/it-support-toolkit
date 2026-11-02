# How to fix "I have no internet"

**Applies to:** Windows laptop or desktop, home or office network
**Priority guide:** One user = Low/Medium. Whole office = High.

## Steps

1. Check Wi-Fi is on, or that the cable is plugged in.
2. Check whether other devices on the same network can get online.
   - If none can, the problem is the router or the ISP (go to step 6).
3. Open Command Prompt and run `ping 1.1.1.1`.
   - Replies: the connection works, so the problem is probably DNS.
   - No replies: the device is not reaching the network.
4. Run `ping google.com`.
   - Works with 1.1.1.1 but fails here: DNS problem. Run `ipconfig /flushdns`.
5. Run `ipconfig /release` then `ipconfig /renew` to get a fresh IP address.
6. Restart the router (off for 30 seconds, then on).
7. Still down? Escalate to Tier 2 with: what you tried, the ping results, and the affected users.

## Notes
- Use `python toolkit.py diagnose` to run the first checks automatically.
