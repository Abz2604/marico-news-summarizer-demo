import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List
from urllib.parse import urlparse, quote
import json

from playwright.async_api import async_playwright


log = logging.getLogger(__name__)


PROFILE_DIR = Path(__file__).resolve().parent.parent / "benv" / "playwright-profile"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "benv" / "crawl-outputs"


async def _ensure_dirs() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def crawl_url_to_disk(
    url: str,
    headless: bool = True,
    use_chrome: bool = False,
    proxy: Optional[str] = None,
    locale: str = "en-IN",
    timezone_id: str = "Asia/Kolkata",
    prewarm: bool = True,
    cookies_json: Optional[str] = None,
    user_data_dir_override: Optional[str] = None,
    use_mobile: bool = False,
    device_name: Optional[str] = None,
    via_search: bool = False,
    search_engine: str = "google",
    referer: Optional[str] = None,
    selectors_json: Optional[str] = None,
    wait_selector: Optional[str] = None,
) -> Dict[str, Any]:
    await _ensure_dirs()

    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    safe_name = (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace("?", "_")
        .replace("%", "_")
    )
    out_html_path = OUTPUT_DIR / f"{timestamp}_{safe_name}.html"

    # Conservative defaults for headless environments
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]

    if use_mobile:
        # Pixel 7-like UA
        user_agent = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Mobile Safari/537.36"
        )
    else:
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )

    result: Dict[str, Any] = {
        "url": url,
        "started_at": started_at.isoformat(),
        "out_html_path": str(out_html_path),
    }

    try:
        async with async_playwright() as p:
            # Prefer real Chrome channel if requested; otherwise Playwright Chromium
            browser_type = p.chromium
            launch_kwargs: Dict[str, Any] = {
                "user_data_dir": str(Path(user_data_dir_override) if user_data_dir_override else PROFILE_DIR),
                "headless": headless,
                "args": launch_args,
                "locale": locale,
                "timezone_id": timezone_id,
                "user_agent": user_agent,
                "viewport": {"width": 390, "height": 844} if use_mobile else {"width": 1366, "height": 850},
                "ignore_default_args": ["--enable-automation"],
                "extra_http_headers": {
                    "Accept-Language": f"{locale},{locale.split('-')[0]};q=0.9,en-US;q=0.8,en;q=0.7",
                    "Upgrade-Insecure-Requests": "1",
                    "DNT": "1",
                    # Some client hints (best-effort; servers may ignore if not negotiated)
                    "Sec-CH-UA": '"Not A(Brand)";v="99", "Chromium";v="128", "Google Chrome";v="128"',
                    "Sec-CH-UA-Mobile": "?1" if use_mobile else "?0",
                    "Sec-CH-UA-Platform": "\"Android\"" if use_mobile else "\"Linux\"",
                },
            }

            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}

            context = None
            if use_chrome:
                try:
                    context = await browser_type.launch_persistent_context(
                        channel="chrome",  # requires Chrome installed
                        **launch_kwargs,
                    )
                except Exception as _:
                    # Fallback to bundled Chromium
                    context = await browser_type.launch_persistent_context(
                        **launch_kwargs,
                    )
            else:
                context = await browser_type.launch_persistent_context(
                    **launch_kwargs,
                )
            try:
                page = await context.new_page()

                # Basic anti-automation hardening
                _locale_base = locale.split('-')[0] if '-' in locale else locale
                stealth_script = (
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"  # noqa: E501
                    + f"Object.defineProperty(navigator, 'languages', {{ get: () => ['{locale}', '{_locale_base}'] }});"  # noqa: E501
                    + "Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });"
                    + "window.chrome = { runtime: {} };"
                    + "Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });"
                    + "const _gp = WebGLRenderingContext.prototype.getParameter;"
                    + "WebGLRenderingContext.prototype.getParameter = function(parameter) {"
                    + " if (parameter === 37445) { return 'Google Inc. (Intel)'; }"
                    + " if (parameter === 37446) { return 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 620, OpenGL 4.6)'; }"
                    + " return _gp.call(this, parameter);"
                    + "};"
                )
                await page.add_init_script(stealth_script)

                # Mobile device emulation flags
                if use_mobile:
                    try:
                        await context.set_default_navigation_timeout(60000)
                        await page.emulate_media(media="screen")
                    except Exception:
                        pass

                # Optional cookie injection
                if cookies_json:
                    try:
                        cookies: List[Dict[str, Any]] = json.loads(cookies_json)
                        await context.add_cookies(cookies)
                    except Exception:
                        pass

                # Optional prewarm visit to establish cookies/session
                if prewarm and not via_search:
                    try:
                        parsed = urlparse(url)
                        base_origin = f"{parsed.scheme}://{parsed.netloc}/"
                        await page.goto(base_origin, wait_until="domcontentloaded", timeout=30000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass

                if via_search:
                    # Navigate via search engine to get a search referer
                    try:
                        parsed = urlparse(url)
                        domain = parsed.netloc
                        if search_engine.lower() == "bing":
                            search_url = f"https://www.bing.com/search?q={quote(url)}"
                        else:
                            search_url = f"https://www.google.com/search?q={quote(url)}"
                        await page.goto(search_url, wait_until="domcontentloaded", timeout=35000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(600)

                        link_selector = f'a[href*="{domain}"]'

                        # Try top-level first
                        try:
                            top_count = await page.locator(link_selector).count()
                        except Exception:
                            top_count = 0

                        if top_count and top_count > 0:
                            href = await page.locator(link_selector).first.get_attribute("href")
                            if href:
                                await page.evaluate("url => location.href = url", href)
                        else:
                            # Try common Bing Copilot iframe that hosts classic SERP
                            found = False
                            try:
                                for fr in page.frames:
                                    fr_url = (fr.url or "").lower()
                                    if "bing.com/search" in fr_url or "cplt_frame" in fr_url:
                                        try:
                                            fl = fr.locator(link_selector).first
                                            # Wait briefly for result to attach
                                            await fl.wait_for(state="attached", timeout=6000)
                                            await fl.click()
                                            found = True
                                            break
                                        except Exception:
                                            continue
                            except Exception:
                                pass

                            if not found:
                                # Fallback: direct goto with referer from search
                                await page.goto(url, referer=search_url, wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        # Fallback to direct
                        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                else:
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=45000,
                        referer=referer if referer else None,
                    )
                # Allow JS-driven content and requests to settle
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass

                # Small human-like behavior
                await page.mouse.move(100, 100)
                await page.wait_for_timeout(300)
                await page.mouse.move(300, 250)
                await page.wait_for_timeout(300)
                try:
                    await page.evaluate("""
                        try {
                          const h = (document && document.body) ? document.body.scrollHeight : 0;
                          window.scrollTo(0, Math.min(1200, h));
                        } catch (e) { /* ignore */ }
                    """)
                except Exception:
                    # Non-fatal; proceed to save HTML anyway
                    pass
                await page.wait_for_timeout(800)

                # Optionally wait for a selector (e.g., price span) before snapshot/extract
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=15000)
                    except Exception:
                        pass

                html = await page.content()
                out_html_path.write_text(html, encoding="utf-8")
                # Save a screenshot alongside
                try:
                    out_png_path = out_html_path.with_suffix('.png')
                    await page.screenshot(path=str(out_png_path), full_page=True)
                    result["out_screenshot_path"] = str(out_png_path)
                except Exception:
                    pass

                # Try to capture the title and final URL
                title = await page.title()
                final_url = page.url

                result.update(
                    {
                        "status": "success",
                        "title": title,
                        "final_url": final_url,
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # Optional field extraction
                if selectors_json:
                    try:
                        mapping: Dict[str, Dict[str, Optional[str]]] = json.loads(selectors_json)
                        extracted: Dict[str, Any] = {}
                        for key, conf in mapping.items():
                            sel = conf.get("selector") if isinstance(conf, dict) else None
                            attr = conf.get("attr") if isinstance(conf, dict) else None
                            if not sel:
                                continue
                            try:
                                loc = page.locator(sel).first
                                await loc.wait_for(state="attached", timeout=2000)
                                if attr:
                                    val = await loc.get_attribute(attr)
                                else:
                                    val = await loc.text_content()
                                if val is not None:
                                    extracted[key] = val.strip()
                            except Exception:
                                continue
                        if extracted:
                            result["extracted"] = extracted
                    except Exception:
                        pass
            finally:
                await context.close()
    except Exception as exc:
        log.exception("Crawl failed: %s", exc)
        result.update(
            {
                "status": "error",
                "error": str(exc),
                "ended_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return result


