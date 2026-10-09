#!/usr/bin/env python3
"""Detect and open captive portals from the Wi-Fi interface only.

Never changes network configuration, routing, DNS or another connection.
"""
import ipaddress
import os
import select
import json
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

CONNECTIVITY_URLS = (
    ("http://connectivitycheck.gstatic.com/generate_204", "204"),
    ("http://detectportal.firefox.com/canonical.html", "success"),
    ("http://captive.apple.com/hotspot-detect.html", "Success"),
)


def run(args, timeout=8):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def output(args, timeout=8):
    result = run(args, timeout)
    if result is None or result.returncode != 0:
        return ""
    return result.stdout.strip()


def wifi_devices():
    listing = output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    devices = []
    for line in listing.splitlines():
        # nmcli escapes literal colons; normal Linux interface names have none.
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "wifi" and parts[2].startswith("connected"):
            devices.append(parts[0])
    return devices


def ipv4_config(device):
    result = output(["ip", "-j", "-4", "addr", "show", "dev", device])
    addresses = []
    try:
        for iface in json.loads(result or "[]"):
            addresses.extend(a.get("local", "") for a in iface.get("addr_info", [])
                             if a.get("family") == "inet")
    except (ValueError, TypeError):
        pass

    gateways = output(["nmcli", "-g", "IP4.GATEWAY", "device", "show", device]).splitlines()
    gateway = next((g.strip() for g in gateways if valid_ipv4(g.strip())), "")
    dns = [d.strip() for d in output(
        ["nmcli", "-g", "IP4.DNS", "device", "show", device]).splitlines()
        if valid_ipv4(d.strip())]
    return addresses, gateway, dns


def valid_ipv4(value):
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def safe_url(url):
    if not url or len(url) > 4096 or any(ord(c) < 32 for c in url):
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return ""
        if parsed.username or parsed.password:
            return ""
        return url
    except ValueError:
        return ""


def probe_url(device, url):
    # Do NOT follow redirects. The first Location is session-specific and
    # following it can hide an authentication failure or cross interfaces.
    result = run(["curl", "--silent", "--show-error", "--noproxy", "*",
                  "--interface", "if!" + device, "--connect-timeout", "2",
                  "--max-time", "4", "--max-filesize", "65536",
                  "-D", "-", url], timeout=6)
    if result is None:
        return {"code": 0, "location": "", "body": "", "error": "curl unavailable"}
    raw = result.stdout[:80000]
    chunks = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    headers, body = (chunks + [""])[:2]
    statuses = re.findall(r"^HTTP/\S+\s+(\d{3})", headers, re.M | re.I)
    code = int(statuses[-1]) if statuses else 0
    locations = re.findall(r"^Location:\s*(.+?)\s*$", headers, re.M | re.I)
    location = safe_url(locations[-1].strip()) if locations else ""
    return {"code": code, "location": location, "body": body[:1024],
            "error": (result.stderr or "").strip()[:250] if result.returncode else ""}


def route_interface(ip):
    line = output(["ip", "-4", "route", "get", ip])
    match = re.search(r"(?:^|\s)dev\s+(\S+)", line)
    return match.group(1) if match else ""


def url_routes_over_wifi(url, device):
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    if valid_ipv4(parsed.hostname):
        return route_interface(parsed.hostname) == device

    # Only use the resolved host address to inspect routing; no DNS settings
    # or network interfaces are modified.
    result = output(["getent", "ahostsv4", parsed.hostname], timeout=3)
    for line in result.splitlines():
        ip = line.split()[0] if line.split() else ""
        if valid_ipv4(ip) and route_interface(ip) == device:
            return True
    return False


def discover(deep=False):
    devices = wifi_devices()
    base = {"state": "none", "device": "", "gateway": "", "dns": [],
            "url": "", "reason": "no-connected-wifi", "probe": []}
    if not devices:
        return base

    device = devices[0]
    addresses, gateway, dns = ipv4_config(device)
    base.update(device=device, gateway=gateway, dns=dns, addresses=addresses)

    if not addresses:
        base.update(state="limited", reason="missing-dhcp-address")
        return base

    redirect = ""
    for url, expected in (CONNECTIVITY_URLS if deep else CONNECTIVITY_URLS[:2]):
        result = probe_url(device, url)
        base["probe"].append({"url": url, "code": result["code"],
                              "location": result["location"],
                              "error": result["error"]})
        if result["location"]:
            redirect = result["location"]
            break
        if (expected == "204" and result["code"] == 204) or (
            expected != "204" and result["code"] == 200 and
            result["body"].strip() == expected):
            base.update(state="full", reason="wifi-reaches-internet")
            return base
        if result["code"] not in (0, 204):
            base.update(state="portal", reason="unexpected-http-response")
            break

    if redirect:
        base.update(state="portal", reason="captive-redirect")

    if gateway:
        gateway_url = "http://" + gateway + "/"
        local_result = probe_url(device, gateway_url)
        base["gatewayProbe"] = {"code": local_result["code"],
                                "location": local_result["location"],
                                "error": local_result["error"]}
        if not redirect and local_result["location"]:
            redirect = local_result["location"]
            base.update(state="portal", reason="gateway-redirect")

    if base["state"] == "none":
        base.update(state="limited", reason=(
            "gateway-unreachable" if gateway and not base.get("gatewayProbe", {}).get("code")
            else "dns-or-hotspot-uplink-unavailable"))

    # With USB or Ethernet active, an external portal URL may route through
    # that other connection. Prefer the directly connected Wi-Fi gateway.
    # Without a gateway, opening the fresh redirected URL is best-effort.
    if redirect and url_routes_over_wifi(redirect, device):
        base["url"] = redirect
    elif gateway:
        base["url"] = "http://" + gateway + "/"
        if redirect:
            base["reason"] += "-external-redirect-on-other-route"
    else:
        base["url"] = redirect or "http://neverssl.com/"
    return base


def launch_isolated(url, device, dns):
    browser_helper = os.path.join(os.path.dirname(__file__), "portal_browser.py")
    try:
        proc = subprocess.Popen(
            [sys.executable, browser_helper, "--interface", device,
             "--url", url, "--dns", ",".join(dns)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        readable, _, _ = select.select([proc.stdout], [], [], 6)
        launched = bool(readable and proc.stdout.readline().strip() == "READY")
        proc.stdout.close()
        if not launched and proc.poll() is None:
            proc.terminate()
        return launched
    except (OSError, ValueError):
        return False


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "browser":
        # Called by the existing Caelestia portal opener. Never launch a
        # privileged process or trust an interface name supplied by an URL.
        url = safe_url(sys.argv[2])
        device = sys.argv[3]
        if not url or device not in wifi_devices():
            return 2
        addresses, _gateway, dns = ipv4_config(device)
        if not addresses:
            return 2
        return 0 if launch_isolated(url, device, dns) else 1

    if len(sys.argv) != 2 or sys.argv[1] not in ("probe", "open", "diagnose"):
        print("Usage: portal_helper.py probe|open|diagnose|browser URL WIFI_DEVICE", file=sys.stderr)
        return 2
    if not shutil.which("nmcli") or not shutil.which("ip"):
        state = {"state": "unknown", "reason": "missing-nmcli-or-ip", "url": ""}
    else:
        state = discover(deep=sys.argv[1] == "diagnose")
    if sys.argv[1] == "probe":
        print(json.dumps({"state": state["state"], "reason": state["reason"]}))
    elif sys.argv[1] == "open":
        launched = (launch_isolated(state["url"], state["device"], state.get("dns", []))
                    if state["url"] and state.get("device") else False)
        print(json.dumps({"state": state["state"], "url": state["url"],
                          "launched": launched, "reason": state["reason"],
                          "device": state.get("device", "")}))
    else:
        print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
