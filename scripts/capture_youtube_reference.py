"""Capture public YouTube controls without signing in or subscribing.

Developer utility; Playwright is not a runtime dependency.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://www.youtube.com/watch?v=jfKfPfyJRdk&hl=ru")
    args = parser.parse_args()
    output = ROOT / "assets" / "youtube_subscription"
    fixtures = ROOT / "tests" / "fixtures" / "youtube_subscription"
    output.mkdir(parents=True, exist_ok=True)
    fixtures.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="ru-RU", viewport={"width": 1920, "height": 1080})
        page.set_default_timeout(8000)
        page.goto(args.url, wait_until="domcontentloaded")
        owner = page.locator("ytd-video-owner-renderer")
        try:
            owner.wait_for(timeout=15000)
        except Exception:
            debug_dir = ROOT / "build"
            debug_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(debug_dir / "youtube-reference-error.png"))
            print(page.title().encode("ascii", "backslashreplace").decode())
            print(page.locator("body").inner_text()[:1500].encode("ascii", "backslashreplace").decode())
            raise
        page.wait_for_timeout(2000)
        page.add_style_tag(content=".ytp-chrome-bottom {display:block!important;opacity:1!important;} .ytp-fullscreen-button {display:block!important;} .ytp-chrome-controls {display:block!important;}")
        subscribe = page.locator("ytd-subscribe-button-renderer").filter(has=page.locator("#subscribe-button-shape"))
        print("Renderers:", subscribe.count())
        enter_svg = page.locator(".ytp-fullscreen-button svg").evaluate("e => e.outerHTML")
        icons = browser.new_page(viewport={"width":24,"height":24})
        def capture_icon(svg, destination):
            icons.set_content('<body style="background:black;margin:0">' + svg + '</body>')
            icons.screenshot(path=str(destination))
        capture_icon(enter_svg, output / "enter_player.png")
        page.add_style_tag(content="ytd-subscribe-button-renderer[capture-subscribed] #subscribe-button-shape {display:none!important;} ytd-subscribe-button-renderer[capture-subscribed] #notification-preference-button {visibility:visible!important;opacity:1!important;} ytd-subscribe-button-renderer[capture-subscribed] .ytAnimatedActionContentWithBackground {visibility:visible!important;opacity:1!important;}")
        for theme in ("light", "dark"):
            page.evaluate("dark => { document.documentElement.toggleAttribute('dark', dark); document.querySelector('ytd-subscribe-button-renderer').removeAttribute('capture-subscribed'); }", theme == "dark")
            page.mouse.move(1000, 40)
            page.wait_for_timeout(1000)
            subscribe.locator("#subscribe-button-shape button").screenshot(path=str(output / f"subscribe_{theme}.png"))
            page.screenshot(path=str(fixtures / f"subscribe_{theme}.png"))
            page.evaluate("() => { const e=document.querySelector('ytd-subscribe-button-renderer'); e.setAttribute('capture-subscribed',''); e.querySelector('#notification-preference-button').removeAttribute('invisible'); }")
            page.wait_for_timeout(1000)
            subscribe.locator("#notification-preference-button button").screenshot(path=str(output / f"subscribed_{theme}.png"))
            subscribe.locator("#notification-preference-button .ytSpecButtonShapeNextButtonTextContent").screenshot(path=str(output / f"subscribed_text_{theme}.png"))
            page.screenshot(path=str(fixtures / f"subscribed_{theme}.png"))
        page.mouse.click(1000, 40)  # User activation for the Fullscreen API.
        page.evaluate("() => document.querySelector('#movie_player').requestFullscreen()")
        page.wait_for_timeout(1000)
        exit_svg = page.locator(".ytp-fullscreen-button svg").evaluate("e => e.outerHTML")
        if exit_svg == enter_svg:
            raise RuntimeError("Native fullscreen glyph did not change")
        capture_icon(exit_svg, output / "exit_player.png")
        page.screenshot(path=str(fixtures / "fullscreen.png"))
        (output / "source.json").write_text(json.dumps({"url":args.url, "viewport":[1920,1080], "locale":"ru-RU", "subscribed_state":"Existing native notification renderer made visible with local CSS; no account login or subscription requests", "player_controls":"Native fullscreen SVG rendered against black; unavailable stream hides controls in page fixtures"}, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    main()
