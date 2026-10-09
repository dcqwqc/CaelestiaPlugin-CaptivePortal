#!/usr/bin/env python3
"""Private, short-lived captive sign-in browser via a Wi-Fi-bound localhost proxy.

All outbound browser TCP (and captive DNS) is bound to the specified Wi-Fi
interface. Does not modify OS routes, DNS, VPN, profiles or default browser.
"""
import argparse
import contextlib
import http.server
import ipaddress
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import threading
from urllib.parse import urlsplit

MAX_TTL_SECONDS = 600
SO_BINDTODEVICE = getattr(socket, "SO_BINDTODEVICE", 25)


def bind_device(sock, device):
    if not device or "/" in device or "\x00" in device:
        raise ValueError("Invalid Wi-Fi interface")
    sock.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, device.encode("utf-8") + b"\x00")


def dns_a(host, device, dns_servers):
    if is_ipv4(host):
        return host
    # Query the Wi-Fi DHCP DNS explicitly, not the USB/Ethernet system resolver.
    host_ascii = host.encode("idna").decode("ascii")
    labels = host_ascii.rstrip(".").split(".")
    if not labels or any(len(x) > 63 for x in labels):
        return None
    qname = b"".join(bytes([len(s)]) + s.encode("ascii") for s in labels) + b"\x00"
    for server in dns_servers:
        if not is_ipv4(server):
            continue
        query_id = os.urandom(2)
        request = query_id + struct.pack("!HHHHH", 0x0100, 1, 0, 0, 0) + qname + b"\x00\x01\x00\x01"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                bind_device(s, device)
                s.settimeout(1.5)
                s.sendto(request, (server, 53))
                response, _ = s.recvfrom(4096)
            if len(response) < 12 or response[:2] != query_id or response[3] & 0x0F:
                continue
            nquestions, nanswers = struct.unpack("!HH", response[4:8])
            cursor = 12
            for _ in range(nquestions):
                cursor = skip_name(response, cursor) + 4
            for _ in range(nanswers):
                cursor = skip_name(response, cursor)
                if cursor + 10 > len(response):
                    break
                record_type, record_class, _, size = struct.unpack("!HHIH", response[cursor:cursor + 10])
                cursor += 10
                if cursor + size > len(response):
                    break
                if record_type == 1 and record_class == 1 and size == 4:
                    return socket.inet_ntoa(response[cursor:cursor + 4])
                cursor += size
        except (OSError, UnicodeError, ValueError, IndexError, struct.error):
            continue
    # Public fallback is only used for hostnames the captive DNS cannot resolve;
    # the TCP connection still goes exclusively out of the Wi-Fi interface.
    try:
        return next((item[4][0] for item in socket.getaddrinfo(
            host, None, socket.AF_INET, socket.SOCK_STREAM)), None)
    except (OSError, UnicodeError):
        return None


def skip_name(message, cursor):
    for _ in range(128):
        if cursor >= len(message):
            raise ValueError("DNS packet truncated")
        count = message[cursor]
        if count & 0xC0 == 0xC0:
            if cursor + 1 >= len(message):
                raise ValueError("DNS compression truncated")
            return cursor + 2
        if count == 0:
            return cursor + 1
        if count > 63:
            raise ValueError("Bad DNS label")
        cursor += 1 + count
    raise ValueError("DNS name too long")


def is_ipv4(value):
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def connect_wifi(host, port, device, dns_servers):
    resolved = dns_a(host, device, dns_servers)
    if not resolved:
        raise OSError("Wi-Fi DNS did not resolve " + host)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        bind_device(s, device)
        s.settimeout(9)
        s.connect((resolved, port))
        return s
    except BaseException:
        s.close()
        raise


class PortalProxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    daemon_threads = True
    timeout = 15

    def log_message(self, fmt, *args):
        # Portal URLs may include device and session identifiers: never log them.
        return

    def do_CONNECT(self):
        authority = self.path.strip()
        try:
            host, port = parse_authority(authority, 443)
            with connect_wifi(host, port, self.server.wifi_device, self.server.wifi_dns) as remote:
                self.send_response(200, "Connection established")
                self.end_headers()
                self.connection.settimeout(90)
                remote.settimeout(90)
                relay(self.connection, remote)
        except (OSError, ValueError):
            try:
                self.send_error(502, "Wi-Fi hotspot unavailable")
            except OSError:
                pass
        self.close_connection = True

    def do_GET(self):
        self.forward_http()

    def do_POST(self):
        self.forward_http()

    def do_HEAD(self):
        self.forward_http()

    def do_OPTIONS(self):
        self.forward_http()

    def forward_http(self):
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme != "http" or not parsed.hostname:
                self.send_error(400, "Expected HTTP proxy request")
                return
            host, port = parsed.hostname, parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            if self.headers.get("Transfer-Encoding"):
                self.send_error(501, "Unsupported portal upload encoding")
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 0 or content_length > 2_000_000:
                self.send_error(413, "Request too large")
                return
            with connect_wifi(host, port, self.server.wifi_device, self.server.wifi_dns) as remote:
                method = self.command
                remote.sendall((method + " " + path + " HTTP/1.1\r\n").encode())
                for key, value in self.headers.items():
                    if key.lower() not in ("connection", "proxy-connection", "proxy-authorization"):
                        remote.sendall((key + ": " + value + "\r\n").encode("latin-1"))
                remote.sendall(b"Connection: close\r\n\r\n")
                remaining = content_length
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remote.sendall(chunk)
                    remaining -= len(chunk)
                remote.settimeout(20)
                while True:
                    chunk = remote.recv(65536)
                    if not chunk:
                        break
                    self.connection.sendall(chunk)
            self.close_connection = True
        except (OSError, ValueError, UnicodeError):
            try:
                self.send_error(502, "Wi-Fi hotspot unavailable")
            except OSError:
                pass
            self.close_connection = True


def parse_authority(text, default_port):
    if text.startswith("["):
        raise ValueError("IPv6 captive tunnels unsupported")
    host, sep, port_string = text.rpartition(":")
    if not sep:
        host, port = text, default_port
    else:
        port = int(port_string)
    if not host or not 1 <= port <= 65535:
        raise ValueError("Invalid proxy target")
    return host, port


def relay(client, remote):
    sockets = [client, remote]
    while True:
        readable, _, _ = select.select(sockets, [], [], 60)
        if not readable:
            return
        for source in readable:
            data = source.recv(65536)
            if not data:
                return
            (remote if source is client else client).sendall(data)


def choose_browser(profile, url, port):
    # Never change the user's usual browser proxy or existing tabs.
    preferences = {
        "network.proxy.type": "1",
        "network.proxy.http": '"127.0.0.1"',
        "network.proxy.http_port": str(port),
        "network.proxy.ssl": '"127.0.0.1"',
        "network.proxy.ssl_port": str(port),
        "network.proxy.no_proxies_on": '""',
        "network.trr.mode": "5",
        "network.proxy.allow_hijacking_localhost": "true",
        "browser.shell.checkDefaultBrowser": "false",
        "browser.startup.homepage_override.mstone": '"ignore"',
    }
    with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as f:
        for name, value in preferences.items():
            f.write('user_pref("' + name + '", ' + value + ');\n')

    # Mirai currently has Zen installed as a Flatpak rather than host binary.
    flatpak = shutil.which("flatpak")
    if flatpak:
        info = subprocess.run([flatpak, "info", "app.zen_browser.zen"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=2, check=False)
        if info.returncode == 0:
            return [flatpak, "run", "--filesystem=" + profile,
                    "--command=launch-script.sh", "app.zen_browser.zen",
                    "--no-remote", "--profile", profile, "--new-window", url]

    for browser in ("zen-browser", "zen", "firefox"):
        executable = shutil.which(browser)
        if executable:
            return [executable, "--no-remote", "--profile", profile, "--new-window", url]
    for browser in ("chromium", "chromium-browser", "google-chrome", "brave-browser"):
        executable = shutil.which(browser)
        if executable:
            return [executable, "--user-data-dir=" + profile,
                    "--proxy-server=http://127.0.0.1:" + str(port),
                    "--no-first-run", "--new-window", url]
    return None


def serve(device, url, dns):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        bind_device(probe, device)  # fail closed if interface binding is not possible

    with tempfile.TemporaryDirectory(prefix="caelestia-wifi-login-") as profile:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PortalProxy)
        server.wifi_device = device
        server.wifi_dns = dns
        port = server.server_port
        browser_command = choose_browser(profile, url, port)
        if not browser_command:
            server.server_close()
            return 3

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            browser = subprocess.Popen(browser_command, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            if browser.poll() is not None:
                print("ERROR: browser quit during startup", flush=True)
                return 4
            print("READY", flush=True)
            try:
                browser.wait(timeout=MAX_TTL_SECONDS)
            except subprocess.TimeoutExpired:
                # Do not kill the browser: just stop the short-lived proxy.
                pass
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--dns", default="")
    args = parser.parse_args()
    if args.url.startswith(("http://", "https://")):
        try:
            return serve(args.interface, args.url, args.dns.split(",") if args.dns else [])
        except (OSError, ValueError) as exc:
            print("ERROR: " + str(exc), flush=True)
            return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
