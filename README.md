# NetDiag: IT Support Network Diagnostic Toolkit

A command-line tool for first-line network troubleshooting. Instead of running `ping`, `nslookup` and `ipconfig` by hand, it tests each network layer in order and tells you **where** the fault is.

Built with Python 3 and **no external dependencies** (standard library only). Works on Windows, Linux and macOS.

## Why it exists

Most "I can't get online" tickets are solved by checking, in order:

1. Does the device have a network connection and an IP?
2. Can it reach the router (gateway)?
3. Can it reach the internet by IP address?
4. Does DNS work?
5. Is the website or service itself up?

The first step that fails points to the cause: device, router, ISP, DNS or the site. `--diagnose` automates this and prints a plain-English verdict.

## Features

| Command | What it does |
|---|---|
| `--diagnose TARGET` | Layered check: local network, gateway, internet, DNS, website (HTTP + TLS), then a diagnosis |
| `--info` | Shows local IP, default gateway and DNS servers |
| `--http URL` | Status code, response time, redirects and TLS certificate expiry |
| `--ping HOST` | Ping with packet-loss reporting |
| `--dns DOMAIN` | Resolves IPv4/IPv6 addresses plus reverse DNS |
| `--port HOST PORTS` | Checks TCP ports (`80`, `80,443` or `20-25`) and tells **closed** apart from **filtered** (firewall) |

Other options: `--count N` (ping packets, default 4), `--timeout S` (seconds, default 5), `--version`.

## Requirements

- Python 3.9 or newer
- The `ping` command available on the system (standard on Windows, macOS and most Linux distributions)

## Usage

```bash
# Full layered diagnosis (start here)
python netdiag.py --diagnose google.com

# Show this machine's network configuration
python netdiag.py --info

# Check a website, including its TLS certificate
python netdiag.py --http https://example.com

# Individual tools
python netdiag.py --ping 8.8.8.8
python netdiag.py --dns google.com
python netdiag.py --port google.com 80,443
python netdiag.py --port 192.168.1.1 20-25
```

## Example output

> Illustrative output showing the format; your results will differ.

```text
=== Layered diagnosis sample ===

[1/5] Local network
  Hostname : LAPTOP-1825EV94  (Windows 11)
  Local IP : 192.168.101.106
  Gateway  : 192.168.101.1
  DNS      : 192.168.101.1
[SUCCESS] Adapter has an IP and a route out.

[2/5] Gateway (router)
[SUCCESS] 192.168.101.1 is reachable (0% packet loss).

[3/5] Internet (by IP, no DNS)
[SUCCESS] 1.1.1.1 is reachable (0% packet loss).

[4/5] DNS resolution
[*] Resolving DNS for google.com...
[SUCCESS] google.com -> 142.251.216.142 (IPv4)
[INFO] Reverse DNS for 142.251.216.142: lcjnbi-ag-in-f14.1e100.net

[5/5] Website / service (HTTP + TLS)
[*] Requesting https://google.com...
[SUCCESS] HTTP 200 OK in 1675 ms.
[INFO] Redirected to https://www.google.com/
[*] Checking TLS certificate for www.google.com:443...
[SUCCESS] Certificate valid (TLSv1.3), issued by Google Trust Services, expires 2026-12-30 (53 days left).

=== Summary ===
  Local network PASS
  Gateway       PASS
  Internet      PASS
  DNS           PASS
  Website       PASS

Diagnosis: All layers passed. The connection to the target looks healthy.
```

### How to read a failure

| First failing layer | Likely cause |
|---|---|
| Local network | Cable or Wi-Fi problem, adapter disabled, no DHCP address |
| Gateway | Router down, wrong network, weak Wi-Fi link |
| Internet | ISP outage or router WAN fault |
| DNS | Wrong or unreachable DNS server |
| Website | The site or service is down, or blocked by a firewall or proxy |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All checks passed |
| 1 | At least one check failed |
| 2 | Invalid input |

These make the tool usable in scripts and scheduled checks.

## Design notes

- **Input validation:** hosts and URLs are validated before use, which prevents argument injection into the `ping` subprocess.
- **No shell:** commands run with `subprocess.run([...])` and a timeout, never `shell=True`.
- **Cross-platform:** ping flags and gateway/DNS discovery adapt to Windows, Linux and macOS. On Windows, ping success is confirmed by a reply (`TTL=`) because Windows returns exit code 0 even for "host unreachable".
- **ICMP fallback:** some networks block ping, so the internet check falls back to a TCP connection.
- **Closed vs filtered ports:** a refused connection means the port is closed; a timeout usually means a firewall is dropping packets.

## Limitations

- Gateway detection is best effort; on some systems it may not be found and that step is skipped.
- Some routers ignore ping, which can show a gateway FAIL even though the network works.
- Test only hosts and networks you own or are authorised to test.

## Roadmap

- Traceroute support
- Compare DNS answers from the system resolver and public resolvers (8.8.8.8, 1.1.1.1)
- Save results as a Markdown or JSON report for tickets
- Unit tests and CI

## License

MIT (add a `LICENSE` file if you want to apply this).
