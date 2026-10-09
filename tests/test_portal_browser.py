import http.client
import http.server
import importlib.util
import pathlib
import socket
import socketserver
import tempfile
import threading
import unittest

SPEC = importlib.util.spec_from_file_location("portal_browser",
    pathlib.Path(__file__).resolve().parents[1] / "portal_browser.py")
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class Reply(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data = b"Wi-Fi proxy works"
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.sendall(self.request.recv(4096))


class PortalBrowserTests(unittest.TestCase):
    def setUp(self):
        self.backend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Reply)
        self.frontend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), proxy.PortalProxy)
        self.frontend.wifi_device = "lo"
        self.frontend.wifi_dns = []
        self.threads = []
        for server in (self.backend, self.frontend):
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            self.threads.append(t)

    def tearDown(self):
        for server in (self.frontend, self.backend):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def test_http_proxy_binds_to_specific_interface(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.frontend.server_port, timeout=4)
        try:
            url = "http://127.0.0.1:" + str(self.backend.server_port) + "/login"
            conn.request("GET", url)
            result = conn.getresponse()
            self.assertEqual(result.status, 200)
            self.assertEqual(result.read(), b"Wi-Fi proxy works")
        finally:
            conn.close()

    def test_tls_connect_tunnel_passes_bidirectional_bytes(self):
        echo = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Echo)
        thread = threading.Thread(target=echo.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(("127.0.0.1", self.frontend.server_port), timeout=5) as client:
                client.sendall(("CONNECT 127.0.0.1:" + str(echo.server_address[1])
                                + " HTTP/1.1\r\nHost: test\r\n\r\n").encode())
                response = b""
                while b"\r\n\r\n" not in response:
                    response += client.recv(1024)
                self.assertIn(b"200 Connection established", response)
                client.sendall(b"test tunnel")
                self.assertEqual(client.recv(100), b"test tunnel")
        finally:
            echo.shutdown()
            echo.server_close()
            thread.join(timeout=2)

    def test_isolated_firefox_profile_contains_proxy_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            browser = proxy.choose_browser(directory, "http://192.168.44.1/", 34567)
            self.assertIsNotNone(browser)
            self.assertIn(directory, browser)
            if pathlib.Path(directory, "user.js").exists():
                config = pathlib.Path(directory, "user.js").read_text()
                self.assertIn("network.proxy.ssl_port", config)
                self.assertIn("network.trr.mode", config)
                self.assertIn("34567", config)

    def test_interface_binding_unprivileged(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            proxy.bind_device(s, "lo")
            self.assertIsNotNone(s)


if __name__ == "__main__":
    unittest.main()
