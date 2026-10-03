"""Capture screenshots of the demo app for a walkthrough. Offline: replay mode, sample cards, scratch database.

Run: python scripts/take_screenshots.py   (writes docs/screenshots/*.png)
Sample cards by default. After make record, run DEBRIEF_SAMPLES=0 python scripts/take_screenshots.py to capture real debriefs from the replay cache.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
PORT = 8599
URL = f"http://127.0.0.1:{PORT}"
CHROMIUM = "/opt/pw-browsers/chromium"


def wait_for_server() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "/_stcore/health", timeout=1)
            return
        except Exception:
            time.sleep(1)
    raise SystemExit("Streamlit did not start")


def settle(page: Page, ms: int = 1200) -> None:
    page.wait_for_timeout(ms)
    page.wait_for_selector("[data-testid=stStatusWidget]", state="detached", timeout=30000)


def pick_role(page: Page, role: str) -> None:
    page.get_by_text(role, exact=True).first.click()
    settle(page)


def shot(page: Page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("wrote", (OUT / f"{name}.png").relative_to(ROOT))


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    env = {**os.environ, "DEBRIEF_MODE": "replay", "DEBRIEF_SAMPLES": os.environ.get("DEBRIEF_SAMPLES", "1"), "DEBRIEF_DB": str(scratch / "shots.sqlite3")}
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
                               "--server.port", str(PORT), "--browser.gatherUsageStats", "false"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROMIUM)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(URL)
            settle(page, 2500)

            shot(page, "01_ae_close_the_demo_checklist")
            page.get_by_role("button", name="End demo and build the card").click()
            settle(page, 2000)
            shot(page, "02_ae_card_next_steps")

            page.get_by_text("Why this step").first.click()
            settle(page)
            shot(page, "03_ae_why_this_step_with_transcript_quote")

            page.get_by_role("tab", name="Recap email").click()
            settle(page)
            shot(page, "04_ae_recap_draft_for_approval")

            pick_role(page, "SC")
            shot(page, "05_sc_commitments_and_record")

            pick_role(page, "Sales manager")
            shot(page, "06_manager_coaching_prompts")

            pick_role(page, "Measurement")
            shot(page, "07_measurement")
            browser.close()
    finally:
        server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
