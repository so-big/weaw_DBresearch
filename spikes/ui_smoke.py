"""Click through the demo web app (PC + phone, light + dark); save screenshots and JS errors.

Runs in a throwaway Playwright container on the server (nothing installed on the host):

    D=$(mktemp -d ~/dbr-shots.XXXX); mkdir $D/out
    docker run --rm --network host --user $(id -u):$(id -g) -e HOME=/tmp \
      -v ~/dbresearch/spikes/ui_smoke.py:/shoot.py:ro -v $D/out:/out \
      -v ~/dbresearch/secrets/demo-admin-password:/secret/demo-admin-password:ro \
      mcr.microsoft.com/playwright/python:v1.49.0-noble \
      sh -c "pip install -q --target /tmp/pw playwright==1.49.0;
             PYTHONPATH=/tmp/pw python /shoot.py"

Expected noise in the error list: 401 before login, 404 for the deliberately invalid guest link.
It creates one 1-hour share link on the first document and revokes it again.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8120"
OUT = Path("/out")
PASSWORD = Path("/secret/demo-admin-password").read_text().strip()
errors: list[str] = []


def watch(page, tag):
    page.on("console", lambda m: m.type == "error" and errors.append(f"[{tag}] console: {m.text}"))
    page.on("pageerror", lambda e: errors.append(f"[{tag}] pageerror: {e}"))


def shot(page, name):
    page.wait_for_timeout(450)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)


def login(page):
    page.goto(f"{BASE}/documents")
    page.wait_for_selector("#login-user")
    page.fill("#login-user", "admin")
    page.fill("#login-pass", PASSWORD)
    page.click("button.btn.big")
    page.wait_for_url("**/documents**")
    page.wait_for_load_state("networkidle")


def run(p, tag, viewport, mobile, scheme):
    browser = p.chromium.launch()
    ctx = browser.new_context(
        viewport=viewport,
        is_mobile=mobile,
        has_touch=mobile,
        device_scale_factor=2 if mobile else 1,
        color_scheme=scheme,
        locale="th-TH",
    )
    page = ctx.new_page()
    watch(page, tag)
    page.goto(f"{BASE}/login")
    page.wait_for_selector("#login-user")
    shot(page, f"{tag}-01-login")
    login(page)
    shot(page, f"{tag}-02-documents")

    docs = page.evaluate("fetch('/api/documents?page_size=5').then(r => r.json())")
    doc_id = docs["items"][0]["id"] if docs["items"] else None

    if mobile:
        page.click("button.fbtn")
        shot(page, f"{tag}-03-filter-sheet")
        page.mouse.click(viewport["width"] // 2, 40)  # tap the scrim to close
        page.wait_for_timeout(300)
        page.click(".mtop .up")
    else:
        page.click("header.top button.btn")
    shot(page, f"{tag}-04-upload")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    for path, name in [
        ("/review", "05-review-queue"),
        ("/shares", "06-shares"),
        ("/admin", "07-admin"),
        ("/admin/users", "08-admin-users"),
        ("/admin/categories", "09-admin-categories"),
        ("/admin/audit", "10-admin-audit"),
    ]:
        page.goto(f"{BASE}{path}")
        page.wait_for_load_state("networkidle")
        shot(page, f"{tag}-{name}")
    if mobile:
        page.goto(f"{BASE}/account")
        page.wait_for_load_state("networkidle")
        shot(page, f"{tag}-11-account")

    if doc_id:
        page.goto(f"{BASE}/documents/{doc_id}")
        page.wait_for_load_state("networkidle")
        shot(page, f"{tag}-12-detail")
        page.get_by_role("button", name="แชร์ลิงก์").click()
        shot(page, f"{tag}-13-share-dialog")
        page.keyboard.press("Escape")
        page.goto(f"{BASE}/documents/{doc_id}/review")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        shot(page, f"{tag}-14-review-form")
        page.screenshot(path=str(OUT / f"{tag}-14b-review-full.png"), full_page=True)

        # Guest flow: a 1-hour link, opened without a session, then revoked.
        if scheme == "light":
            link = page.evaluate(
                """id => fetch(`/api/documents/${id}/shares`, {
                     method: 'POST',
                     headers: {'Content-Type': 'application/json',
                               'X-Requested-With': 'dbresearch'},
                     body: JSON.stringify({ttl_hours: 1, note: 'ui smoke test'}),
                   }).then(r => r.json())""",
                doc_id,
            )
            guest = browser.new_context(
                viewport=viewport,
                is_mobile=mobile,
                has_touch=mobile,
                device_scale_factor=2 if mobile else 1,
                color_scheme=scheme,
            )
            gp = guest.new_page()
            watch(gp, f"{tag}-guest")
            gp.goto(f"{BASE}{link['path']}")
            gp.wait_for_load_state("networkidle")
            shot(gp, f"{tag}-15-guest")
            gp.goto(f"{BASE}/s/not-a-real-token")
            gp.wait_for_load_state("networkidle")
            shot(gp, f"{tag}-16-guest-invalid")
            guest.close()
            page.evaluate(
                """id => fetch(`/api/shares/${id}`, {method: 'DELETE',
                     headers: {'X-Requested-With': 'dbresearch'}})""",
                link["id"],
            )
    browser.close()


with sync_playwright() as p:
    run(p, "pc", {"width": 1366, "height": 860}, False, "light")
    run(p, "phone", {"width": 390, "height": 844}, True, "light")
    run(p, "pcdark", {"width": 1366, "height": 860}, False, "dark")
    run(p, "phonedark", {"width": 390, "height": 844}, True, "dark")

(OUT / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1))
print(f"{len(errors)} errors")
for e in errors[:30]:
    print(e)
sys.exit(0)
