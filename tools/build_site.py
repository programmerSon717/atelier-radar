
"""정적 사이트를 만든다. HTML/JS 는 site/ 의 템플릿을 그대로 복사하고,
데이터는 data.json 으로 따로 뺀다 (브라우저가 읽어서 필터·정렬을 그때그때 한다).

    ./.venv/bin/python tools/build_site.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# export_data.py 가 이름·학교를 가리려면 그 값을 알아야 한다. 모르면 메일 초안이 통째로 빠진다.
load_dotenv(ROOT / ".env")
DOCS = ROOT / "docs"
SITE = ROOT / "site"

DOCS.mkdir(exist_ok=True)
for name in ("index.html", "app.js", "ui.js"):
    shutil.copyfile(SITE / name, DOCS / name)
(DOCS / ".nojekyll").write_text("", encoding="utf-8")

subprocess.run([sys.executable, str(ROOT / "tools" / "export_data.py")], check=True)
size = (DOCS / "data.json").stat().st_size
print(f"docs/ 생성 — index.html, app.js, data.json ({size:,} bytes)")
