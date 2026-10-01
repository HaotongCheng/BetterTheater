"""PROTOTYPE — sample registry. Screenshots stay in the main checkout's untracked docs/ folder; nothing is copied."""
import os, pathlib
ROOT = pathlib.Path(os.environ.get("BT_ASSETS", r"D:\projects\BetterTheater\docs\research\assets"))
SAMPLES = {}
for p in sorted((ROOT / "game screenshots").glob("*.png")):
    SAMPLES["S" + p.name[:2]] = p
for p in sorted((ROOT / "cooperative-run-2026-09-17").glob("*.png")):
    SAMPLES["E1:" + p.stem] = p
