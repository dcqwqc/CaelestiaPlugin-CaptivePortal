#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("portal_helper",
    pathlib.Path(__file__).resolve().parents[1] / "portal_helper.py")
portal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(portal)


class PortalTests(unittest.TestCase):
    def configured(self):
        return patch.multiple(portal,
            wifi_devices=lambda: ["wlan0"],
            ipv4_config=lambda dev: (["192.168.44.102"], "192.168.44.1", ["192.168.44.1"]))

    def test_no_wifi_does_not_open_portal(self):
        with patch.object(portal, "wifi_devices", return_value=[]):
            result = portal.discover()
        self.assertEqual(result["state"], "none")
        self.assertEqual(result["url"], "")

    def test_wifi_full_even_with_other_default_route(self):
        with self.configured(), patch.object(portal, "probe_url", return_value={
                "code": 204, "location": "", "body": "", "error": ""}):
            result = portal.discover()
        self.assertEqual(result["state"], "full")
        self.assertEqual(result["url"], "")

    def test_captive_redirect_when_wifi_routes_to_it(self):
        redir = "https://www.hotsplots.de/auth/login.php?challenge=123"
        def response(_dev, target):
            if "connectivitycheck" in target:
                return {"code": 302, "location": redir, "body": "", "error": ""}
            return {"code": 302, "location": redir, "body": "", "error": ""}
        with self.configured(), patch.object(portal, "probe_url", side_effect=response), \
                patch.object(portal, "url_routes_over_wifi", return_value=True):
            result = portal.discover()
        self.assertEqual(result["state"], "portal")
        self.assertEqual(result["url"], redir)

    def test_external_redirect_with_usb_uses_local_gateway(self):
        redir = "https://www.hotsplots.de/auth/login.php?challenge=123"
        def response(_dev, target):
            return {"code": 302, "location": redir, "body": "", "error": ""}
        with self.configured(), patch.object(portal, "probe_url", side_effect=response), \
                patch.object(portal, "url_routes_over_wifi", return_value=False):
            result = portal.discover()
        self.assertEqual(result["state"], "portal")
        self.assertEqual(result["url"], "http://192.168.44.1/")
        self.assertIn("other-route", result["reason"])

    def test_missing_dhcp_is_limited(self):
        with patch.object(portal, "wifi_devices", return_value=["wlan0"]), \
                patch.object(portal, "ipv4_config", return_value=([], "", [])):
            result = portal.discover()
        self.assertEqual(result["reason"], "missing-dhcp-address")
        self.assertEqual(result["state"], "limited")

    def test_broken_hotspot_reports_limited_without_overclaiming_portal(self):
        empty = {"code": 0, "location": "", "body": "", "error": "Timeout"}
        with self.configured(), patch.object(portal, "probe_url", return_value=empty):
            result = portal.discover()
        self.assertEqual(result["state"], "limited")
        self.assertEqual(result["reason"], "gateway-unreachable")
        self.assertEqual(result["url"], "http://192.168.44.1/")

    def test_gateway_redirect_detected_when_public_probe_is_blocked(self):
        redir = "https://www.hotsplots.de/auth/login.php?token=fresh"
        def response(_dev, target):
            if target.startswith("http://192.168.44.1/"):
                return {"code": 302, "location": redir, "body": "", "error": ""}
            return {"code": 0, "location": "", "body": "", "error": "DNS failed"}
        with self.configured(), patch.object(portal, "probe_url", side_effect=response), \
                patch.object(portal, "url_routes_over_wifi", return_value=True):
            result = portal.discover()
        self.assertEqual(result["state"], "portal")
        self.assertEqual(result["url"], redir)

    def test_unsafe_redirects_are_ignored(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd",
                    "http://user:pass@example.org/", "https://example.org/\r\nOther: bad"):
            self.assertEqual(portal.safe_url(url), "")

    def test_probe_always_binds_wifi_and_does_not_follow_redirects(self):
        calls = []
        class Output:
            stdout = "HTTP/1.1 302 Found\r\nLocation: https://www.hotsplots.de/login\r\n\r\n"
            stderr = ""
            returncode = 0
        def fake_run(args, timeout=8):
            calls.append(args)
            return Output()
        with patch.object(portal, "run", side_effect=fake_run):
            result = portal.probe_url("wlan0", "http://detectportal.firefox.com/canonical.html")
        self.assertEqual(result["code"], 302)
        self.assertEqual(result["location"], "https://www.hotsplots.de/login")
        self.assertIn("--interface", calls[0])
        self.assertEqual(calls[0][calls[0].index("--interface") + 1], "if!wlan0")
        self.assertNotIn("--location", calls[0])
        self.assertNotIn("-L", calls[0])

if __name__ == "__main__":
    unittest.main()
