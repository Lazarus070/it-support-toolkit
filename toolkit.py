#!/usr/bin/env python3
"""IT Support Toolkit - a small command-line helper for first-line IT support.

Commands:
    python toolkit.py hello          -> checks the tool runs
    python toolkit.py diagnose       -> checks whether the internet connection works
    python toolkit.py ping HOST      -> pings a host (Day 2)
    python toolkit.py lookup NAME    -> DNS lookup (Day 2)

Later days add: ticket (log and list support tickets) and kb (how-to articles).
"""

import argparse
import platform
import socket
import subprocess

# Public DNS servers we can try to reach. 1.1.1.1 is Cloudflare, 8.8.8.8 is Google.
# Port 53 is the port DNS uses.
DNS_SERVERS = [("1.1.1.1", 53), ("8.8.8.8", 53)]


def can_connect(host, port, timeout=3):
    """Try to open a connection. Returns True if it worked, False if not."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def can_resolve(name):
    """Try to turn a website name into an IP address (this is what DNS does)."""
    try:
        socket.gethostbyname(name)
        return True
    except OSError:
        return False


def ping(host, count=3):
    """Ping a host using the operating system's ping command.

    Windows uses -n for the number of pings, Linux and Mac use -c.
    Returns True if the host replied.
    """
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        result = subprocess.run(
            ["ping", flag, str(count), host],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def print_result(ok, label, fix):
    """Print PASS or FAIL, plus a plain-English fix when something fails."""
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"       Try this: {fix}")


def cmd_hello(args):
    print("IT Support Toolkit is working. Next try: python toolkit.py diagnose")


def cmd_diagnose(args):
    print("Running internet checks...\n")

    reached = any(can_connect(host, port) for host, port in DNS_SERVERS)
    print_result(
        reached,
        "Can reach the internet by IP address (1.1.1.1 / 8.8.8.8)",
        "Check the Wi-Fi or cable is connected, restart the router, "
        "then check whether other devices can get online.",
    )

    resolved = can_resolve("google.com")
    print_result(
        resolved,
        "Can look up website names (DNS)",
        "Restart the router, or try switching the DNS server to 1.1.1.1.",
    )

    print()
    if reached and resolved:
        print("Result: Connection looks healthy.")
    elif reached and not resolved:
        print("Result: Internet works but names do not resolve - likely a DNS problem.")
    else:
        print("Result: No connection - likely a network or router problem.")


def cmd_ping(args):
    print(f"Pinging {args.host}...\n")
    ok = ping(args.host)
    print_result(
        ok,
        f"{args.host} replied to ping",
        "If other sites work, the host may block ping. If nothing works, "
        "run 'python toolkit.py diagnose' to find where the problem is.",
    )


def cmd_lookup(args):
    print(f"Looking up {args.name}...\n")
    try:
        ip = socket.gethostbyname(args.name)
    except OSError:
        print_result(False, f"Could not resolve {args.name}",
                     "Check the spelling, then try switching DNS to 1.1.1.1.")
        return
    print_result(True, f"{args.name} resolves to {ip}", "")


def build_parser():
    parser = argparse.ArgumentParser(description="IT Support Toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hello", help="check the toolkit runs").set_defaults(func=cmd_hello)
    sub.add_parser("diagnose", help="check internet connectivity").set_defaults(
        func=cmd_diagnose
    )
    p = sub.add_parser("ping", help="ping a host")
    p.add_argument("host", help="e.g. 1.1.1.1 or google.com")
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("lookup", help="turn a website name into an IP address")
    p.add_argument("name", help="e.g. google.com")
    p.set_defaults(func=cmd_lookup)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
