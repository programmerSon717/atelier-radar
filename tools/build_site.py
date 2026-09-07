"""정적 사이트를 만든다. HTML/JS 는 site/ 의 템플릿을 그대로 복사하고,
데이터는 data.json 으로 따로 뺀다 (브라우저가 읽어서 필터·정렬을 그때그때 한다).

    ./.venv/bin/python tools/build_site.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = ROOT / "site"

DOCS.mkdir(exist_ok=True)
for name in ("index.html", "app.js"):
    shutil.copyfile(SITE / name, DOCS / name)
(DOCS / ".nojekyll").write_text("", encoding="utf-8")

subprocess.run([sys.executable, str(ROOT / "tools" / "export_data.py")], check=True)
size = (DOCS / "data.json").stat().st_size
print(f"docs/ 생성 — index.html, app.js, data.json ({size:,} bytes)")
