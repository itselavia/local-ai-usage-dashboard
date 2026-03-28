from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from .app import STATIC_DIR, create_app


def run(args) -> int:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(args.db)
    client = TestClient(app)
    query = "?anonymize=1" if args.anonymize_workspaces else ""

    pages = {
        "index.html": f"/overview{query}",
        "overview.html": f"/overview{query}",
        "workspaces.html": f"/workspaces{query}",
        "methodology.html": f"/methodology{query}",
    }

    for filename, path in pages.items():
        response = client.get(path)
        response.raise_for_status()
        (output_dir / filename).write_text(response.text, encoding="utf-8")

    static_dir = output_dir / "static"
    if static_dir.exists():
        shutil.rmtree(static_dir)
    shutil.copytree(STATIC_DIR, static_dir)

    print(f"generated static snapshot at {output_dir}")
    return 0
