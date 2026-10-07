"""Week 11: real Spring -> gateway -> Django OIDC integration in a disposable database.

Prerequisites: mvn verify in services/identity, npm ci in services/api-gateway, uv sync.
Run with: uv --project services/erp-core run python scripts/test_identity_integration.py
This test creates its own demo records, keys and SQLite database, never uses your ERP data.
It exercises HTTP protocol behavior, not a visual browser session or PostgreSQL locking.
"""

import base64
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix="stockpilot-oidc-test-") as directory:
        private = Path(directory)
        log = (private / "services.log").open("w+")
        identity_port, erp_port, gateway_port = port(), port(), port()
        issuer = f"http://127.0.0.1:{identity_port}"
        backend = f"http://127.0.0.1:{erp_port}"
        gateway = f"http://127.0.0.1:{gateway_port}"
        web = "http://127.0.0.1:5173"
        env = os.environ | {
            "DATABASE_URL": f"sqlite:///{private / 'erp.sqlite3'}",
            "AUTH_MODE": "oidc",
            "OIDC_ISSUER": issuer,
            "OIDC_JWKS_URL": issuer + "/oauth2/jwks",
            "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "DJANGO_DEBUG": "true",
            "STOCKPILOT_PRODUCTION": "false",
            "DJANGO_SECRET_KEY": "isolated-test-only",
            "IDENTITY_ACCOUNTS": str(private / "accounts.json"),
            "IDENTITY_SIGNING_KEY": str(private / "signing.jwk"),
            "WEB_ORIGIN": web,
            "SERVER_PORT": str(identity_port),
            "ERP_URL": backend,
            "PORT": str(gateway_port),
        }
        erp = ROOT / "services/erp-core"

        def manage(*args):
            subprocess.run(
                [sys.executable, "manage.py", *args],
                cwd=erp,
                env=env,
                check=True,
                stdout=log,
                stderr=log,
            )

        def start(command, cwd):
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log))

        opener = build_opener(
            ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect()
        )

        def request(url, data=None, headers=None):
            payload = urlencode(data).encode() if data is not None else None
            try:
                response = opener.open(
                    Request(url, data=payload, headers=headers or {}), timeout=10
                )
            except HTTPError as response:
                return response.code, response.headers, response.read()
            with response:
                return response.status, response.headers, response.read()

        try:
            manage("migrate", "--noinput")
            # Rehearse the Week 8 -> 11 schema boundary with real seeded ERP records.
            manage("migrate", "audit", "0001", "--noinput")
            manage("seed_week8")

            def snapshot():
                with sqlite3.connect(private / "erp.sqlite3") as database:
                    tables = database.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    return {
                        name: sorted(
                            map(
                                repr,
                                database.execute(
                                    'SELECT * FROM "' + name.replace('"', '""') + '"'
                                ).fetchall(),
                            )
                        )
                        for (name,) in tables
                        if name not in {"django_migrations", "sqlite_sequence"}
                    }

            before_upgrade = snapshot()
            manage("migrate", "--noinput")
            assert snapshot() == before_upgrade, "Upgrade changed existing ERP rows"
            manage("export_identity", str(private / "accounts.json"))
            exported = json.loads((private / "accounts.json").read_text())
            account = next(a for a in exported if a["email"] == "admin@stockpilot.local")
            start(["java", "-jar", "target/identity-0.11.0.jar"], ROOT / "services/identity")
            start(
                [sys.executable, "manage.py", "runserver", f"127.0.0.1:{erp_port}", "--noreload"],
                erp,
            )
            start(["node", "src/server.js"], ROOT / "services/api-gateway")
            for url in [
                issuer + "/.well-known/openid-configuration",
                backend + "/api/v1/health/",
                gateway + "/healthz",
            ]:
                deadline = time.monotonic() + 45
                while True:
                    try:
                        if request(url)[0] == 200:
                            break
                    except (URLError, OSError):
                        pass
                    if time.monotonic() > deadline:
                        raise AssertionError("Service did not become ready: " + url)
                    time.sleep(0.2)
            verifier = "stockpilot-integration-pkce-" + uuid4().hex
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            params = {
                "client_id": "stockpilot-web",
                "response_type": "code",
                "scope": "openid profile erp",
                "redirect_uri": web + "/callback",
                "state": uuid4().hex,
                "nonce": uuid4().hex,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            authorize = issuer + "/oauth2/authorize?" + urlencode(params)
            status, headers, _ = request(authorize, headers={"Accept": "text/html"})
            assert status == 302, ("authorize", status)
            status, _, html = request(urljoin(issuer, headers["Location"]))
            assert status == 200
            csrf = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html.decode()).group(1)
            # Missing CSRF cannot submit a login form.
            assert (
                request(
                    issuer + "/login",
                    {"username": "admin@stockpilot.local", "password": "Admin123!"},
                )[0]
                == 403
            )
            status, headers, _ = request(
                issuer + "/login",
                {
                    "username": "admin@stockpilot.local",
                    "password": "Admin123!",
                    "_csrf": csrf,
                },
            )
            assert status == 302, ("login", status)
            status, headers, _ = request(
                urljoin(issuer, headers["Location"]), headers={"Accept": "text/html"}
            )
            assert status == 302, ("code redirect", status)
            callback = parse_qs(urlparse(headers["Location"]).query)
            assert callback["state"] == [params["state"]]
            token_data = {
                "grant_type": "authorization_code",
                "client_id": "stockpilot-web",
                "code": callback["code"][0],
                "redirect_uri": web + "/callback",
                "code_verifier": verifier,
            }
            status, headers, body = request(issuer + "/oauth2/token", token_data, {"Origin": web})
            assert status == 200, ("token exchange", status, body[:200])
            assert headers["Access-Control-Allow-Origin"] == web
            token = json.loads(body)["access_token"]
            assert request(issuer + "/oauth2/token", token_data)[0] == 400, (
                "Authorization code replay accepted"
            )
            auth = {"Authorization": "Bearer " + token, "Origin": web}
            # Authorization-code reuse invalidates the original token in the AS store,
            # but offline JWT verifiers cannot detect that until its five-minute expiry.
            status, _, body = request(gateway + "/api/v1/auth/me/", headers=auth)
            assert status == 200, ("gateway identity", status, body[:200])
            me = json.loads(body)
            assert me["id"] == account["id"] and me["memberships"]
            organization = me["memberships"][0]["organization"]["id"]
            auth["X-Organization-ID"] = organization
            assert request(gateway + "/api/v1/catalog/products/", headers=auth)[0] == 200
            status, _, body = request(
                gateway + "/api/v1/catalog/categories/",
                {"code": "GATEWAY-TEST", "name": "Gateway test"},
                auth,
            )
            assert status == 201, ("proxied write", status, body[:200])
            assert request(gateway + "/api/v1/notifications/revision/", headers=auth)[0] == 200
            assert request(gateway + "/api/v1/auth/token/", headers=auth)[0] == 404
            auth["X-Organization-ID"] = str(uuid4())
            assert request(gateway + "/api/v1/catalog/products/", headers=auth)[0] == 403
            print("PASS: Spring discovery, CSRF, PKCE, code replay rejection, UUID migration,")
            print(
                "gateway writes, JWT checks, tenant denial, notifications and legacy login closure."
            )
            print("PASS: Week 8 -> 11 schema upgrade preserved all existing ERP rows.")
        except Exception:
            log.flush()
            # Logs contain no credential/token dumps; show diagnostics for failed startup only.
            log.seek(0)
            print(log.read()[-12000:])
            raise
        finally:
            for process in reversed(processes):
                process.terminate()
            for process in reversed(processes):
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            log.close()


if __name__ == "__main__":
    main()
