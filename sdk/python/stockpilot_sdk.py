# Developer toolkit: creates, validates, packages and submits declarative add-ons.
# stockpilot_validation.py mirrors the server manifest contract; parity tests compare both.
# Client uses a token and organization header to call the same reviewed marketplace/lifecycle APIs.
"""Create, validate, package and submit reviewed StockPilot add-ons."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from stockpilot_validation import checksum, validate


def scaffold(slug, hook="inventory.low_stock"):
    return validate({"id": slug, "name": slug.replace("-", " ").title(), "version": "1.0.0",
                     "api": 1, "core_min": "0.14.0", "core_max": "0.15.0", "hook": hook,
                     "requires": {}, "settings": {"threshold": 5} if hook == "inventory.low_stock" else {"message": "Hello StockPilot"}})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward credentials to a redirect target.
        return None


class Client:
    def __init__(self, base_url, token, organization):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an API base URL without credentials, query or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("HTTPS is required outside localhost")
        self.base_url, self.token, self.organization = base_url.rstrip("/"), token, organization

    def request(self, path, data=None):
        request = Request(self.base_url + path, data=None if data is None else json.dumps(data).encode(), headers={
            "Authorization": "Bearer " + self.token, "X-Organization-ID": self.organization,
            "Content-Type": "application/json"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"API {exc.code}: {exc.read(4096).decode(errors='replace')}") from exc

    def catalog(self):
        return self.request("/plugins/marketplace/")

    def submit(self, manifest, summary):
        return self.request("/plugins/submissions/", {"manifest": validate(manifest), "summary": summary})

    def command(self, slug, operation, expected_revision, idempotency_key=None, **options):
        # Retain the same key when retrying an unchanged write after a timeout.
        return self.request("/plugins/commands/", {"slug": slug, "operation": operation,
                            "expected_revision": expected_revision, "idempotency_key": str(idempotency_key or uuid4()), **options})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("id")
    init.add_argument("--hook", choices=["inventory.low_stock", "dashboard.notice"], default="inventory.low_stock")
    init.add_argument("--output", default="manifest.json")
    check = commands.add_parser("validate")
    check.add_argument("manifest")
    build = commands.add_parser("build")
    build.add_argument("manifest")
    build.add_argument("--summary", required=True)
    build.add_argument("--output", default="plugin.json")
    submit = commands.add_parser("submit")
    submit.add_argument("manifest")
    submit.add_argument("--summary", required=True)
    submit.add_argument("--base-url", required=True)
    submit.add_argument("--organization", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = scaffold(args.id, args.hook)
        else:
            manifest = validate(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
            if args.command == "validate":
                print("Valid · SHA-256 " + checksum(manifest))
                return
            if not 1 <= len(args.summary.strip()) <= 240:
                raise ValueError("Summary must have 1 to 240 characters")
            if args.command == "submit":
                token = os.environ.get("STOCKPILOT_TOKEN")
                if not token:
                    raise ValueError("Set STOCKPILOT_TOKEN to your access token")
                print(json.dumps(Client(args.base_url, token, args.organization).submit(manifest, args.summary)))
                return
            result = {"manifest": manifest, "summary": args.summary}
        # Exclusive creation prevents accidental overwriting of developer work.
        with open(args.output, "x", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2)
        print(args.output)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
