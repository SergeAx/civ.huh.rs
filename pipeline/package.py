"""Build the deploy folder dist/srbciv/: web/ without the dev pages (art gallery, trailer maker), ready for
`wrangler pages deploy dist/srbciv`. The source code lives on GitHub, so the site does not carry a copy.
"""

from __future__ import annotations

import shutil

from .core.paths import ROOT, WEB

NAME = "srbciv"
SITE = ROOT / "dist" / NAME
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SITE_SKIP_DIRS = {"dev"}


def cmd_package() -> None:
    missing = [p for p in ("data/cities.json", "data/world.json", "index.html") if not (WEB / p).exists()]
    if missing:
        raise SystemExit(f"web/ is incomplete ({', '.join(missing)} missing): run `uv run python -m pipeline all` first")
    if SITE.exists():
        shutil.rmtree(SITE)
    n, size = 0, 0
    for f in sorted(WEB.rglob("*")):
        rel = f.relative_to(WEB)
        if not f.is_file() or rel.parts[0] in SITE_SKIP_DIRS or SKIP_NAMES & set(rel.parts):
            continue
        dst = SITE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        n, size = n + 1, size + f.stat().st_size
    print(f"{SITE.relative_to(ROOT).as_posix()}/: {n} files, {size / 1e6:.1f} MB")
