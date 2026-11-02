#!/usr/bin/env python3
"""IT Support Toolkit - a small command-line helper for first-line IT support.

Day 1 commands:
    python toolkit.py hello      -> checks the tool runs
    python toolkit.py diagnose   -> checks whether the internet connection works

Later days add: ticket (log and list support tickets) and kb (how-to articles).
"""

import argparse
import socket

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


def build_parser():
    parser = argparse.ArgumentParser(description="IT Support Toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hello", help="check the toolkit runs").set_defaults(func=cmd_hello)
    sub.add_parser("diagnose", help="check internet connectivity").set_defaults(
        func=cmd_diagnose
    )
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
