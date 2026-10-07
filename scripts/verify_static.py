"""Validate source without requiring the deliberately omitted PDFs and diagrams."""
import ast
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IGNORE = {".venv", "node_modules", "__pycache__", ".git", "dist", "tmp", "target"}


def main():
    # Parse files without executing application code or touching its database.
    for path in ROOT.rglob("*"):
        if not path.is_file() or IGNORE.intersection(path.parts):
            continue
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
        elif path.suffix == ".json":
            json.loads(path.read_text())
        elif path.suffix in (".yml", ".yaml"):
            yaml.safe_load(path.read_text())
        elif path.suffix in (".ts", ".tsx"):
            for target in re.findall(r'from\s+["\'](\.[^"\']+)["\']', path.read_text()):
                base = path.parent / target
                assert any(p.is_file() for p in (
                    base,
                    base.with_suffix(".ts"), base.with_suffix(".tsx"),
                    base / "index.ts", base / "index.tsx",
                )), f"Unresolved import in {path}: {target}"
    for name in [
        "services/erp-core/apps/sales/models.py",
        "services/erp-core/apps/sales/migrations/0001_initial.py",
        "services/erp-core/tests/test_sales_week5.py",
        "apps/web/src/features/sales/SalesPage.tsx",
        "services/erp-core/apps/billing/migrations/0001_initial.py",
        "services/erp-core/apps/intelligence/migrations/0001_initial.py",
        "services/ai-service/app/main.py",
        "services/ai-service/uv.lock",
        "apps/web/src/features/finance/FinancePage.tsx",
        "apps/web/src/features/intelligence/IntelligencePage.tsx",
        "services/api-gateway/src/server.js",
        "services/api-gateway/package-lock.json",
        "services/identity/pom.xml",
        "services/erp-core/apps/tenancy/oidc.py",
        "services/erp-core/tests/test_security_week11.py",
        "services/erp-core/apps/extensions/services.py",
        "services/erp-core/apps/extensions/migrations/0001_initial.py",
        "services/erp-core/tests/test_plugins_week14.py",
        "apps/web/src/features/plugins/PluginsPage.tsx",
    ]:
        assert (ROOT / name).is_file(), f"Missing source file: {name}"
    print("Source syntax, configuration and relative imports passed.")


if __name__ == "__main__":
    main()
