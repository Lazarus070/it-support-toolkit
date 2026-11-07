#!/usr/bin/env python3
"""IT Support Network Diagnostic Toolkit (v2).

First-line troubleshooting for "I can't get to X" tickets. The --diagnose mode
tests each network layer in order, so the first failure points at the cause:

    local network -> gateway (router) -> internet -> DNS -> website (HTTP/TLS)

Examples:
    python netdiag.py --diagnose google.com
    python netdiag.py --info
    python netdiag.py --http https://example.com
    python netdiag.py --ping 8.8.8.8
    python netdiag.py --dns google.com
    python netdiag.py --port google.com 80,443

Only test hosts you own or are authorised to test.
Exit codes: 0 = all checks passed, 1 = a check failed, 2 = bad input.
"""
from __future__ import annotations

import argparse
import ipaddress
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import urlparse

__version__ = "2.0.0"

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == "windows"
IS_MAC = SYSTEM == "darwin"
INTERNET_TEST_IPS = ["1.1.1.1", "8.8.8.8"]
CERT_WARN_DAYS = 30

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def validate_host(host: str) -> str:
    """Return host if it is a valid IP or hostname, else raise ValueError.

    Rejecting values like '-f' or '8.8.8.8; rm -rf /' prevents argument
    injection into the underlying ping command.
    """
    host = host.strip()
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if HOSTNAME_RE.match(host):
        return host
    raise ValueError(f"Invalid host: {host!r}")


def normalize_url(target: str) -> str:
    """Accept 'example.com' or a full URL; return a validated http(s) URL."""
    target = target.strip()
    if "://" not in target:
        target = "https://" + target
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid URL: {target!r}")
    validate_host(parsed.hostname)
    return target


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def parse_ports(spec: str) -> list[int]:
    """Parse '80', '80,443' or '20-25' (mixable) into a sorted port list."""
    ports: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                raise ValueError(f"Invalid range: {part!r}")
            ports.update(range(start, end + 1))
        else:
            ports.add(int(part))
    if not ports:
        raise ValueError("No ports given")
    if any(p < 1 or p > 65535 for p in ports):
        raise ValueError("Ports must be between 1 and 65535")
    if len(ports) > 1024:
        raise ValueError("Too many ports (max 1024 per run)")
    return sorted(ports)


# --------------------------------------------------------------------------- #
# Local network information (best effort, OS specific)
# --------------------------------------------------------------------------- #
def _run_cmd(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return its combined output ('' on any failure)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or "") + (result.stderr or "")


def _ip_or_none(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def get_local_ip() -> str | None:
    """Find the IP used for outbound traffic (no packets are actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def get_gateway() -> str | None:
    """Find the default gateway (the router) for this machine."""
    if IS_WINDOWS:
        out = _run_cmd(["route", "print", "-4", "0.0.0.0"])
        match = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
    elif IS_MAC:
        out = _run_cmd(["route", "-n", "get", "default"])
        match = re.search(r"gateway:\s*(\S+)", out)
    else:
        out = _run_cmd(["ip", "route", "show", "default"])
        match = re.search(r"default via (\S+)", out)
        if not match:
            out = _run_cmd(["route", "-n"])
            match = re.search(r"^0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
    return _ip_or_none(match.group(1)) if match else None


def get_dns_servers() -> list[str]:
    """List the DNS servers this machine is configured to use."""
    servers: list[str] = []
    if IS_WINDOWS:
        capture = False
        for line in _run_cmd(["ipconfig", "/all"]).splitlines():
            if "DNS Servers" in line and " : " in line:
                capture = True
                ip = _ip_or_none(line.split(" : ", 1)[1])
                if ip:
                    servers.append(ip)
            elif capture:
                ip = _ip_or_none(line)
                if ip:
                    servers.append(ip)
                else:
                    capture = False
    else:
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "nameserver":
                        ip = _ip_or_none(parts[1])
                        if ip:
                            servers.append(ip)
        except OSError:
            pass
    return list(dict.fromkeys(servers))


def gather_local_info() -> dict:
    return {
        "ip": get_local_ip(),
        "gateway": get_gateway(),
        "dns": get_dns_servers(),
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
    }


def print_local_info(info: dict) -> None:
    print(f"  Hostname : {info['host']}  ({info['os']})")
    print(f"  Local IP : {info['ip'] or 'NOT FOUND'}")
    print(f"  Gateway  : {info['gateway'] or 'NOT FOUND'}")
    if info["dns"]:
        notes = ["  (local stub resolver)" if d in ("127.0.0.53", "127.0.0.1") else "" for d in info["dns"]]
        print("  DNS      : " + ", ".join(f"{d}{n}" for d, n in zip(info["dns"], notes)))
    else:
        print("  DNS      : NOT FOUND")


def show_local_info() -> bool:
    """Print local network configuration. Fails if no local IP is found."""
    print("[*] Local network configuration")
    info = gather_local_info()
    print_local_info(info)
    if not info["ip"]:
        print("[ERROR] No usable network connection (no local IP / no route).")
        return False
    print("[SUCCESS] Network adapter has an IP and a route out.")
    return True


# --------------------------------------------------------------------------- #
# Diagnostics (each returns True on success, False on failure)
# --------------------------------------------------------------------------- #
def ping_host(host: str, count: int = 4, verbose: bool = True) -> bool:
    """Ping a host. verbose=False prints a one-line result instead of raw output."""
    if shutil.which("ping") is None:
        print("[ERROR] 'ping' command not found on this system.")
        return False

    flag = "-n" if IS_WINDOWS else "-c"
    command = ["ping", flag, str(count), host]
    if verbose:
        print(f"[*] Pinging {host} ({count} packets)...")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=count * 5 + 10, check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"[ERROR] Ping to {host} timed out.")
        return False

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    loss_match = re.search(r"(\d+(?:\.\d+)?)%\s*(?:packet\s*)?loss", output, re.I)
    loss = float(loss_match.group(1)) if loss_match else None

    # Windows returns 0 even for "Destination host unreachable", so require TTL=.
    ok = result.returncode == 0 and (loss is None or loss < 100)
    if IS_WINDOWS:
        ok = ok and "TTL=" in output.upper()

    loss_txt = f"{loss:g}% packet loss" if loss is not None else "no loss data"
    if ok:
        print(f"[SUCCESS] {host} is reachable ({loss_txt}).")
    else:
        print(f"[ERROR] Failed to reach {host} ({loss_txt}).")
    if verbose and output:
        print(output)
    return ok


def resolve_dns(domain: str) -> bool:
    """Resolve a domain to its IPv4/IPv6 addresses (plus reverse DNS)."""
    print(f"[*] Resolving DNS for {domain}...")
    try:
        infos = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        print(f"[ERROR] Could not resolve {domain}: {exc.strerror or exc}. "
              "Check the domain name, DNS server settings, or network connection.")
        return False

    addresses: dict[str, str] = {}
    for family, _, _, _, sockaddr in infos:
        label = "IPv6" if family == socket.AF_INET6 else "IPv4"
        addresses.setdefault(sockaddr[0], label)

    for ip, label in addresses.items():
        print(f"[SUCCESS] {domain} -> {ip} ({label})")

    first_ip = next(iter(addresses))
    try:
        print(f"[INFO] Reverse DNS for {first_ip}: {socket.gethostbyaddr(first_ip)[0]}")
    except (socket.herror, socket.gaierror):
        print(f"[INFO] No reverse DNS record for {first_ip}.")
    return True


def check_port(host: str, ports: list[int], timeout: float = 5.0) -> bool:
    """Check whether TCP ports are open on the target host."""
    all_open = True
    for port in ports:
        try:
            service = socket.getservbyport(port, "tcp")
        except OSError:
            service = "unknown"
        print(f"[*] Checking port {port} ({service}) on {host}...")
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                ms = (time.perf_counter() - start) * 1000
                print(f"[SUCCESS] Port {port} is OPEN ({ms:.0f} ms).")
        except (socket.timeout, TimeoutError):
            print(f"[ERROR] Port {port} timed out - likely FILTERED by a firewall.")
            all_open = False
        except ConnectionRefusedError:
            print(f"[ERROR] Port {port} is CLOSED (connection refused).")
            all_open = False
        except socket.gaierror as exc:
            print(f"[ERROR] Could not resolve {host}: {exc.strerror or exc}.")
            return False
        except OSError as exc:
            print(f"[ERROR] Port {port} check failed: {exc.strerror or exc}.")
            all_open = False
    return all_open


def check_tls(host: str, port: int = 443, timeout: float = 5.0) -> bool:
    """Validate the TLS certificate and report days until expiry."""
    print(f"[*] Checking TLS certificate for {host}:{port}...")
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                version = tls.version()
    except ssl.SSLCertVerificationError as exc:
        print(f"[ERROR] Certificate problem: {exc.verify_message} "
              "(expired, self-signed, wrong hostname, or untrusted issuer).")
        return False
    except (ssl.SSLError, OSError) as exc:
        print(f"[ERROR] TLS connection failed: {getattr(exc, 'strerror', None) or exc}.")
        return False

    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), tz=timezone.utc)
    days_left = (expires - datetime.now(timezone.utc)).days
    issuer = dict(item[0] for item in cert.get("issuer", ())).get("organizationName", "unknown")
    print(f"[SUCCESS] Certificate valid ({version}), issued by {issuer}, "
          f"expires {expires:%Y-%m-%d} ({days_left} days left).")
    if days_left < CERT_WARN_DAYS:
        print(f"[WARN] Certificate expires in under {CERT_WARN_DAYS} days - renewal needed soon.")
    return True


def check_http(url: str, timeout: float = 5.0) -> bool:
    """Request a URL; report status, response time, redirects and TLS health."""
    print(f"[*] Requesting {url}...")
    request = urllib.request.Request(url, headers={"User-Agent": f"netdiag/{__version__}"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            status, final_url = resp.status, resp.geturl()
    except urllib.error.HTTPError as exc:  # server answered with 4xx/5xx
        status, final_url = exc.code, exc.geturl()
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            print(f"[ERROR] Certificate problem: {reason.verify_message}.")
        elif isinstance(reason, (socket.timeout, TimeoutError)):
            print(f"[ERROR] Request timed out after {timeout:g}s (server slow or blocked).")
        elif isinstance(reason, socket.gaierror):
            print("[ERROR] DNS lookup failed for this site.")
        elif isinstance(reason, ConnectionRefusedError):
            print("[ERROR] Connection refused (service not running or port closed).")
        else:
            print(f"[ERROR] Request failed: {reason}.")
        return False
    except (socket.timeout, TimeoutError):
        print(f"[ERROR] Request timed out after {timeout:g}s (server slow or blocked).")
        return False
    except OSError as exc:
        print(f"[ERROR] Request failed: {exc.strerror or exc}.")
        return False

    ms = (time.perf_counter() - start) * 1000
    try:
        phrase = HTTPStatus(status).phrase
    except ValueError:
        phrase = ""
    hints = {
        401: "login required", 403: "access denied", 404: "page not found",
        429: "rate limited", 502: "bad gateway", 503: "service unavailable",
    }
    ok = status < 400
    tag = "SUCCESS" if ok else "ERROR"
    extra = f" - {hints[status]}" if status in hints else ""
    print(f"[{tag}] HTTP {status} {phrase} in {ms:.0f} ms{extra}.")
    if final_url.rstrip("/") != url.rstrip("/"):
        print(f"[INFO] Redirected to {final_url}")

    final = urlparse(final_url)
    if final.scheme == "https" and final.hostname:
        return check_tls(final.hostname, final.port or 443, timeout) and ok
    return ok


def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_internet(count: int, timeout: float) -> bool:
    """Test internet reachability by IP (no DNS needed); falls back to TCP if ICMP is blocked."""
    if shutil.which("ping"):
        for ip in INTERNET_TEST_IPS:
            if ping_host(ip, min(count, 2), verbose=False):
                return True
    for ip in INTERNET_TEST_IPS:
        if _tcp_connect(ip, 443, timeout):
            print(f"[INFO] Ping blocked, but TCP to {ip}:443 works - internet is up.")
            return True
    return False


# --------------------------------------------------------------------------- #
# Layered diagnosis
# --------------------------------------------------------------------------- #
def full_diagnosis(target: str, count: int, timeout: float) -> bool:
    """Test each layer in order and say where the fault is."""
    url = normalize_url(target)
    host = urlparse(url).hostname or target
    results: list[tuple[str, str]] = []

    def header(n: int, title: str) -> None:
        print(f"\n[{n}/5] {title}")

    print(f"=== Layered diagnosis for {target} ===")

    # 1. Local network
    header(1, "Local network")
    info = gather_local_info()
    print_local_info(info)
    local_ok = bool(info["ip"])
    print("[SUCCESS] Adapter has an IP and a route out." if local_ok
          else "[ERROR] No usable network connection.")
    results.append(("Local network", "PASS" if local_ok else "FAIL"))

    # 2. Gateway
    header(2, "Gateway (router)")
    gw_ok: bool | None = None
    if not local_ok:
        print("[SKIP] No local network.")
        results.append(("Gateway", "SKIP"))
    elif not info["gateway"]:
        print("[WARN] Could not detect the default gateway; skipping.")
        results.append(("Gateway", "SKIP"))
    else:
        gw_ok = ping_host(info["gateway"], count, verbose=False)
        results.append(("Gateway", "PASS" if gw_ok else "FAIL"))

    # 3. Internet by IP
    header(3, "Internet (by IP, no DNS)")
    internet_ok = False
    if not local_ok:
        print("[SKIP] No local network.")
        results.append(("Internet", "SKIP"))
    else:
        internet_ok = check_internet(count, timeout)
        if not internet_ok:
            print("[ERROR] Cannot reach the internet by IP address.")
        results.append(("Internet", "PASS" if internet_ok else "FAIL"))

    # 4. DNS
    header(4, "DNS resolution")
    dns_ok: bool | None = None
    if not internet_ok:
        print("[SKIP] No internet.")
        results.append(("DNS", "SKIP"))
    elif is_ip(host):
        print("[SKIP] Target is an IP address; no DNS needed.")
        results.append(("DNS", "SKIP"))
    else:
        dns_ok = resolve_dns(host)
        results.append(("DNS", "PASS" if dns_ok else "FAIL"))

    # 5. Website
    header(5, "Website / service (HTTP + TLS)")
    http_ok: bool | None = None
    if not internet_ok or dns_ok is False:
        print("[SKIP] Earlier layer failed.")
        results.append(("Website", "SKIP"))
    else:
        http_ok = check_http(url, timeout)
        results.append(("Website", "PASS" if http_ok else "FAIL"))

    # Summary + plain-English diagnosis
    print("\n=== Summary ===")
    for name, status in results:
        print(f"  {name:<14}{status}")

    if not local_ok:
        verdict = ("No network connection. Check the cable, Wi-Fi, adapter status "
                   "and whether an IP address was assigned (DHCP).")
    elif not internet_ok and gw_ok is False:
        verdict = ("The router is not responding. Check the cable/Wi-Fi link, "
                   "restart the router, and confirm the correct network is joined.")
    elif not internet_ok:
        verdict = ("Router is reachable but there is no internet. Likely an ISP or "
                   "router WAN problem; restart the router or contact the ISP.")
    elif dns_ok is False:
        verdict = ("Internet works but DNS fails. Check the DNS server settings and "
                   "try 8.8.8.8 or 1.1.1.1 as a test.")
    elif http_ok is False:
        verdict = ("Your network and DNS are fine; the problem is the website/service "
                   "itself, or a proxy/firewall blocking it.")
    else:
        verdict = "All layers passed. The connection to the target looks healthy."
        if gw_ok is False:
            verdict += " (Gateway ignores ping, which is common and harmless.)"
    print(f"\nDiagnosis: {verdict}")

    return all(status != "FAIL" for _, status in results)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IT Support Network Diagnostic Toolkit",
        epilog="Example: python netdiag.py --diagnose google.com  "
               "(only test hosts you own or are authorised to test)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--diagnose", metavar="TARGET",
                       help="layered check: local network, gateway, internet, DNS, website")
    group.add_argument("--info", action="store_true",
                       help="show local IP, gateway and DNS servers")
    group.add_argument("--http", metavar="URL",
                       help="check a website: status, speed, redirects, TLS certificate")
    group.add_argument("--ping", metavar="HOST", help="ping a host (e.g. google.com)")
    group.add_argument("--dns", metavar="DOMAIN", help="resolve a domain to IP addresses")
    group.add_argument(
        "--port", nargs=2, metavar=("HOST", "PORTS"),
        help="check TCP ports: single, list or range (e.g. google.com 80,443 or 20-25)",
    )

    parser.add_argument("--count", type=int, default=4, help="ping packets to send (default 4)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="network timeout in seconds (default 5)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not 1 <= args.count <= 20:
        parser.error("--count must be between 1 and 20")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")

    try:
        if args.diagnose:
            ok = full_diagnosis(args.diagnose, args.count, args.timeout)
        elif args.info:
            ok = show_local_info()
        elif args.http:
            ok = check_http(normalize_url(args.http), args.timeout)
        elif args.ping:
            ok = ping_host(validate_host(args.ping), args.count)
        elif args.dns:
            ok = resolve_dns(validate_host(args.dns))
        else:
            ok = check_port(validate_host(args.port[0]), parse_ports(args.port[1]), args.timeout)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n[!] Cancelled by user.")
        return 130

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
