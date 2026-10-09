import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPENER = ROOT / "scripts" / "open-captive-portal"


class OpenerTests(unittest.TestCase):
    def run_mock(self, redirect=False):
        with tempfile.TemporaryDirectory() as directory:
            fake = pathlib.Path(directory)
            for name, source in {
                "nmcli": '''#!/bin/sh
case "$*" in
  "-t -f DEVICE,TYPE,STATE device status") echo "wlan0:wifi:connected";;
  "-g GENERAL.CONNECTION device show wlan0") echo "WIFI@DB";;
  "-t -f ACTIVE,SSID dev wifi") echo "yes:WIFI@DB";;
  "-g IP4.GATEWAY device show wlan0") echo "192.168.44.1";;
esac
''',
                "curl": ('''#!/bin/sh
out=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-D" ]; then shift; out="$1"; fi
    shift
done
if [ -n "$out" ]; then
    printf 'HTTP/1.1 302 Found\\r\\nLocation: https://www.hotsplots.de/auth/login.php?fresh=1\\r\\n\\r\\n' > "$out"
fi
''' if redirect else "#!/bin/sh\nexit 7\n"),
                "ip": "#!/bin/sh\necho '192.168.44.1 dev wlan0 src 192.168.44.102'\n",
                "sleep": "#!/bin/sh\nexit 0\n",
            }.items():
                path = fake / name
                path.write_text(source)
                path.chmod(stat.S_IRWXU)
            env = os.environ.copy()
            env["PATH"] = str(fake) + os.pathsep + env["PATH"]
            env["XDG_STATE_HOME"] = str(fake)
            result = subprocess.run(["bash", str(OPENER), "--print"], env=env,
                                    capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

    def test_no_redirect_uses_connected_wifi_gateway(self):
        self.assertEqual(self.run_mock(), "http://192.168.44.1/")

    def test_fresh_redirect_wins_over_gateway(self):
        self.assertEqual(self.run_mock(redirect=True),
                         "https://www.hotsplots.de/auth/login.php?fresh=1")


if __name__ == "__main__":
    unittest.main()
