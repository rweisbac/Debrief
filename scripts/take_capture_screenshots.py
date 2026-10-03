"""Screenshots of the post-demo capture flow for a deck. Offline: replay mode, sample captures, scratch database.

What is real and what is a sample (the captions in docs/deck/DECK_BRIEF.md say the same):
- the confirm cards use the 2 hand-written sample captures (deal_a, deal_b), scored by the real code
- next steps, recap and stakeholders after confirm come from the recorded run 2 model output (replay)
- Slack screens render the exact Block Kit JSON the app posts, in Slack's style; not a live workspace
- the dashboard holds only the confirms made by this script

Run: python scripts/take_capture_screenshots.py   (writes docs/screenshots/1*.png)
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
PORT = 8611
URL = f"http://127.0.0.1:{PORT}"
CHROMIUM = "/opt/pw-browsers/chromium"


def wait_for_server() -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "/api/deals", timeout=1)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not start")


def shot(page: Page, name: str, full: bool = True) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("wrote", (OUT / f"{name}.png").relative_to(ROOT))


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    env = {**os.environ, "DEBRIEF_MODE": "replay", "DEBRIEF_SAMPLES": "1", "DEBRIEF_DB": str(scratch / "shots.sqlite3")}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.web:app", "--port", str(PORT)], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROMIUM)
            desk = browser.new_page(viewport={"width": 1100, "height": 900}, color_scheme="light")
            phone = browser.new_page(viewport={"width": 400, "height": 860}, color_scheme="light",
                                     device_scale_factor=2)

            desk.goto(f"{URL}/preview/slack/deal_a?kind=capture")
            desk.wait_for_selector(".header")
            shot(desk, "10_slack_confirm_card_halvorsen")

            desk.goto(f"{URL}/preview/slack/deal_b?kind=capture")
            desk.wait_for_selector(".header")
            shot(desk, "11_slack_confirm_card_meridian")

            phone.goto(f"{URL}/capture/deal_b")
            phone.wait_for_selector("#confirm")
            phone.locator('.chip[data-field="champion_status"][data-part="economic_buyer_identified"][data-value="no"]').click()
            shot(phone, "12_phone_confirm_card_meridian_one_edit")

            phone.goto(f"{URL}/capture/deal_a")
            phone.wait_for_selector("#confirm")
            shot(phone, "13_phone_confirm_card_halvorsen")

            mid = browser.new_page(viewport={"width": 760, "height": 900}, color_scheme="light", device_scale_factor=2)
            mid.goto(f"{URL}/capture/deal_a")
            mid.wait_for_selector("#confirm")
            mid.wait_for_timeout(2500)  # a realistic glance before confirming
            mid.click("#confirm")
            mid.wait_for_selector("#payoff .card")
            mid.wait_for_timeout(600)
            for card, name in zip(mid.locator("#payoff .card").all(),
                                  ["17_after_confirm_next_best_steps", "18_after_confirm_recap_draft",
                                   "19_after_confirm_stakeholder_map", "20_after_confirm_written_to_crm"]):
                card.screenshot(path=str(OUT / f"{name}.png"))
                print("wrote", (OUT / f"{name}.png").relative_to(ROOT))

            desk.goto(f"{URL}/preview/slack/deal_a?kind=capture")
            desk.wait_for_selector(".header")
            shot(desk, "14_slack_confirmed_card_halvorsen")

            desk.goto(f"{URL}/preview/slack/deal_a?kind=debrief")
            desk.wait_for_selector(".header")
            shot(desk, "15_slack_debrief_card_halvorsen")

            phone.goto(f"{URL}/capture/deal_b")
            phone.wait_for_selector("#confirm")
            phone.locator('.chip[data-field="champion_status"][data-part="economic_buyer_identified"][data-value="no"]').click()
            phone.wait_for_timeout(1500)
            phone.click("#confirm")
            phone.wait_for_selector("#payoff .card")

            desk.goto(f"{URL}/dashboard")
            desk.wait_for_selector("#tiles .tile")
            shot(desk, "16_capture_dashboard")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
