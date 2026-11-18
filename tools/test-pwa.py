#!/usr/bin/env python3
"""Exercise the real agent PWA using an isolated config and a test-only TLS authority."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-PhoneBox-Panel": "1"}


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def certificates(work):
    def openssl(*args):
        subprocess.run(["openssl", *args], cwd=work, check=True, capture_output=True)

    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "2",
            "-subj", "/CN=PhoneBox integration test CA", "-keyout", "ca.key", "-out", "ca.pem")
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost",
            "-keyout", "leaf.key", "-out", "leaf.csr")
    (work / "ext").write_text("subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n")
    openssl("x509", "-req", "-in", "leaf.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", "leaf.pem", "-days", "1", "-sha256", "-extfile", "ext")
    openssl("pkcs12", "-export", "-inkey", "leaf.key", "-in", "leaf.pem", "-out", "test.pfx",
            "-passout", "pass:integration-test-only")


class Fixture:
    def __init__(self, work, executable):
        self.work = work
        self.local, self.remote = port(), port()
        while self.local == self.remote:
            self.remote = port()
        self.origin = f"https://localhost:{self.remote}"
        self.config = work / "config.json"
        self.config.write_text(json.dumps({
            "deviceSerial": "__test_no_device__", "updates": {"auto": False}, "lan": {"enabled": False},
            "claude": {"phoneApprovals": False}, "night": {"enabled": False}, "rules": [], "shortcuts": [],
            "pages": [{"id": "home", "template": "home"}],
            "pwa": {"enabled": True, "host": "localhost", "bindAddress": "127.0.0.1",
                    "port": self.remote, "certificatePath": "test.pfx"},
        }))
        self.command = [str(executable), "--config", str(self.config), "--port", str(self.local), "--restart"]
        self.tls = ssl.create_default_context(cafile=str(work / "ca.pem"))
        self.log = (work / "agent.log").open("w+")
        self.process = None

    def start(self):
        self.process = subprocess.Popen(self.command, stdout=self.log, stderr=self.log,
                                        env={**os.environ, "PHONEBOX_PWA_PFX_PASSWORD": "integration-test-only"})
        until = time.monotonic() + 30
        while time.monotonic() < until and self.process.poll() is None:
            try:
                if self.request("/pwa/manage", local=True)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.15)
        raise AssertionError("Agent never became ready")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def connection(self, local=False):
        if local:
            return http.client.HTTPConnection("127.0.0.1", self.local, timeout=6)
        return http.client.HTTPSConnection("localhost", self.remote, timeout=6, context=self.tls)

    def request(self, path, method="GET", headers=None, body=None, local=False):
        conn = self.connection(local)
        try:
            conn.request(method, path, body, headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def code(self):
        status, _, data = self.request("/pwa/manage/pair", "POST", HEADERS, local=True)
        assert status == 200
        return json.loads(data)

    def claim(self, code, name, cookie=None, origin=None):
        headers = {**HEADERS, "Origin": origin or self.origin, "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        return self.request("/pwa/session", "POST", headers, json.dumps({"code": code, "name": name}))

    def tests(self):
        state, panel = "/agent/api/state", "/panel/"
        with closing(http.client.HTTPSConnection("localhost", self.remote, timeout=6, context=ssl.create_default_context())) as untrusted:
            try:
                untrusted.request("GET", panel)
            except ssl.SSLCertVerificationError:
                pass
            else:
                raise AssertionError("The TLS client accepted the test CA without explicit trust")
        assert self.request(panel)[0] == 200
        assert self.request(panel, headers={"Host": f"other.local:{self.remote}"})[0] == 403
        status, fields, body = self.request(panel + "manifest.webmanifest")
        assert status == 200 and fields["Content-Type"] == "application/manifest+json"
        assert json.loads(body)["display"] == "standalone"
        assert self.request(panel + "widgets/pc.js")[0] == 200
        assert self.request(panel + "%2e%2e/pwa/manage")[0] == 404
        assert self.request(state, headers=HEADERS)[0] == 401
        assert self.request("/agent/api/stream", headers={"Accept": "text/event-stream"})[0] == 401
        assert self.request(state, headers={**HEADERS, "Cookie": "__Host-phonebox=" + "a" * 64})[0] == 401
        assert self.request("/api/settings")[0] == 404
        assert self.request("/pwa/setup")[0] == 404
        assert self.request("/pwa/setup", local=True)[0] == 200
        assert self.request("/pwa/manage/pair", "POST", local=True)[0] == 403
        assert self.request("/pwa/manage/pair", "POST", {**HEADERS, "Origin": "https://other.local"}, local=True)[0] == 403
        assert self.claim("bad", "unpaired")[0] == 403
        code = self.code()
        assert code["link"] == self.origin + "/panel/#pair=" + code["code"]
        assert self.claim(code["code"], "unpaired", origin="https://other.local")[0] == 403
        status, fields, _ = self.claim(code["code"], "iPhone test")
        assert status == 204
        full_cookie = fields["Set-Cookie"]
        assert all(key.lower() in full_cookie.lower() for key in ("; secure", "; httponly", "samesite=strict", "path=/"))
        cookie = full_cookie.split(";")[0]
        assert self.claim(code["code"], "reused")[0] == 403
        headers = {**HEADERS, "Cookie": cookie}
        assert self.request(state, headers={"Cookie": cookie})[0] == 403
        status, fields, data = self.request(state, headers=headers)
        assert status == 200 and "pc" in json.loads(data) and fields["Cache-Control"] == "no-store"
        status, _, public = self.request("/agent/api/config", headers=headers)
        assert status == 200 and "config" in json.loads(public)
        assert "webhookToken" not in public.decode() and "certificatePath" not in public.decode()
        assert self.request("/agent/api/controls/state", headers=headers)[0] == 200
        assert self.request("/agent/api/settings", headers=headers)[0] == 404
        assert self.request("/agent/api/shortcuts/test", "POST", {**headers, "Origin": self.origin})[0] == 404
        assert self.request("/agent/api/notify", "POST", {**headers, "Origin": self.origin})[0] == 404
        assert self.request("/agent/api/volume?op=mute", "POST", headers)[0] == 403
        assert self.request("/agent/api/run/missing", "POST", {**headers, "Origin": self.origin})[0] == 500
        assert self.request(state, headers={**headers, "Sec-Fetch-Site": "same-site"})[0] == 403
        assert self.request(state, "OPTIONS", {**headers, "Origin": "https://other.local"})[0] == 403

        status, fields, _ = self.claim(self.code()["code"], "iPad test", cookie)
        assert status == 204
        assert self.request(state, headers=headers)[0] == 401
        headers["Cookie"] = fields["Set-Cookie"].split(";")[0]
        status, fields, _ = self.claim(self.code()["code"], "Second iPad")
        assert status == 204
        second = {**HEADERS, "Cookie": fields["Set-Cookie"].split(";")[0]}
        assert self.request(state, headers=second)[0] == 200

        status, _, raw = self.request("/pwa/manage", local=True)
        devices = json.loads(raw)["devices"]
        assert status == 200 and len(devices) == 2
        assert all("digest" not in d and "token" not in d for d in devices)
        target = next(d for d in devices if d["name"] == "iPad test")

        with closing(self.connection()) as stream:
            stream.request("GET", "/agent/api/stream",
                           headers={"Cookie": headers["Cookie"], "Accept": "text/event-stream"})
            events = stream.getresponse()
            assert events.status == 200 and events.getheader("content-type") == "text/event-stream"
            assert events.readline().strip() == b"event: state"
            assert b'"pc":' in events.readline()
            assert self.request("/api/notify", "POST", HEADERS, "integration event", local=True)[0] == 200
            while not (line := events.readline()).startswith(b"event: event"):
                assert line
            assert b"integration event" in events.readline()
            assert self.request("/pwa/manage/" + target["id"], "DELETE", HEADERS, local=True)[0] == 204
            assert not events.read().strip()
        assert self.request(state, headers=headers)[0] == 401
        assert self.request(state, headers=second)[0] == 200
        self.stop()
        self.start()
        assert self.request(state, headers=headers)[0] == 401
        assert self.request(state, headers=second)[0] == 200
        print("PASS: real HTTPS, authentication, pairing, session rotation, API permissions, SSE, revocation and restart")


    def soak(self, seconds):
        cookies = []
        for name in ("soak iPhone", "soak iPad"):
            status, headers, _ = self.claim(self.code()["code"], name)
            assert status == 204
            cookies.append(headers["Set-Cookie"].split(";")[0])

        until = time.monotonic() + 10
        while time.monotonic() < until:
            status, _, payload = self.request("/agent/api/state", headers={**HEADERS, "Cookie": cookies[0]})
            if status == 200 and (json.loads(payload)["pc"] or {}).get("ramTotalGb", 0) > 0:
                break
            time.sleep(.15)
        else:
            raise AssertionError("The agent did not sample PC state before the soak")

        def sample(cookie):
            frames = 0
            with closing(self.connection()) as conn:
                conn.request("GET", "/agent/api/stream", headers={"Cookie": cookie, "Accept": "text/event-stream"})
                events = conn.getresponse()
                assert events.status == 200
                until = time.monotonic() + seconds
                previous = 0
                while time.monotonic() < until:
                    line = events.readline()
                    assert line, "Stream ended during soak"
                    if line.rstrip() == b"event: state":
                        state = json.loads(events.readline().removeprefix(b"data: "))
                        assert state["pc"]["ramTotalGb"] > 0
                        assert state["ts"] >= previous
                        previous = state["ts"]
                        frames += 1
            return frames

        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(sample, cookies))
        assert all(count >= seconds * .8 for count in counts), counts
        print(f"PASS: {seconds}s simultaneous TLS/SSE soak, {counts} valid state frames")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", type=lambda x: Path(x).resolve())
    parser.add_argument("--browser", action="store_true", help="run Playwright with a trusted test CA and Chromium")
    parser.add_argument("--soak-seconds", type=int, default=0, help="sample two concurrent TLS streams for this duration")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="phonebox-pwa-") as tmp:
        work = Path(tmp)
        certificates(work)
        fixture = Fixture(work, args.agent)
        try:
            fixture.start()
            fixture.tests()
            if args.soak_seconds > 0:
                fixture.soak(args.soak_seconds)
            if args.browser:
                run_browser(fixture)
        except BaseException:
            fixture.log.seek(0)
            print(fixture.log.read())
            raise
        finally:
            fixture.stop()
            fixture.log.close()


def run_browser(fixture):
    # Chromium 146+ uses the XDG NSS database when the legacy database is absent.
    xdg = fixture.work / "xdg"
    nss = xdg / "pki" / "nssdb"
    nss.mkdir(parents=True)
    db = f"sql:{nss}"
    subprocess.run(["certutil", "-N", "-d", db, "--empty-password"], check=True)
    subprocess.run(["certutil", "-A", "-d", db, "-n", "PhoneBox integration test CA", "-t", "C,,",
                    "-i", str(fixture.work / "ca.pem")], check=True)
    chromium = os.environ.get("PHONEBOX_TEST_CHROMIUM", "/usr/bin/chromium")
    legacy = Path.home() / ".pki" / "nssdb"
    if legacy.is_dir():
        # Chromium prioritizes an existing legacy NSS database. Mount the test DB only inside
        # the browser's namespace, keeping the regular user and system certificate stores intact.
        wrapper = fixture.work / "chromium-test"
        command = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc",
                   "--bind", tempfile.gettempdir(), tempfile.gettempdir(), "--bind", str(nss), str(legacy), chromium]
        wrapper.write_text("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n')
        wrapper.chmod(0o700)
        chromium = str(wrapper)
    cwd = ROOT / "tools" / "ui-tests"
    subprocess.run([str(cwd / "node_modules" / ".bin" / "playwright"), "test", "--config", "playwright.pwa.config.cjs"],
                   cwd=cwd, env={**os.environ, "XDG_DATA_HOME": str(xdg), "PHONEBOX_TEST_CHROMIUM": chromium,
                                 "PHONEBOX_PWA_TEST_URL": fixture.origin,
                                 "PHONEBOX_PWA_TEST_LOCAL": f"http://127.0.0.1:{fixture.local}"}, check=True)


if __name__ == "__main__":
    main()
