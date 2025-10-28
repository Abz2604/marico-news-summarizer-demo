from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query

from services.crawler import crawl_url_to_disk


router = APIRouter(prefix="/crawl", tags=["crawl-poc"])


@router.post("")
async def crawl(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Target URL to crawl with headless browser"),
    headless: bool = Query(True, description="Run in headless mode"),
    use_chrome: bool = Query(False, description="Prefer system Chrome channel if available"),
    proxy: Optional[str] = Query(None, description="Proxy server, e.g. http://user:pass@host:port"),
    locale: str = Query("en-IN", description="Browser locale, e.g. en-IN"),
    timezone_id: str = Query("Asia/Kolkata", description="Timezone ID, e.g. Asia/Kolkata"),
    prewarm: bool = Query(True, description="Visit site root first to establish session"),
    cookies_json: Optional[str] = Query(None, description="JSON array of Playwright cookies"),
    user_data_dir_override: Optional[str] = Query(None, description="Custom user-data dir path to reuse profile"),
    use_mobile: bool = Query(False, description="Emulate a mobile device"),
    device_name: Optional[str] = Query(None, description="Reserved for named device profiles"),
    via_search: bool = Query(False, description="Navigate via search engine first"),
    search_engine: str = Query("google", description="google or bing"),
    referer: Optional[str] = Query(None, description="Send a custom Referer header for direct nav"),
    selectors_json: Optional[str] = Query(None, description="JSON map of key -> {selector, attr?}"),
    wait_selector: Optional[str] = Query(None, description="Wait for this selector before snapshot"),
):
    # Queue crawl in background and return immediately
    background_tasks.add_task(
        crawl_url_to_disk,
        url,
        headless,
        use_chrome,
        proxy,
        locale,
        timezone_id,
        prewarm,
        cookies_json,
        user_data_dir_override,
        use_mobile,
        device_name,
        via_search,
        search_engine,
        referer,
        selectors_json,
        wait_selector,
    )
    return {
        "status": "scheduled",
        "url": url,
        "headless": headless,
        "use_chrome": use_chrome,
        "proxy": bool(proxy),
        "locale": locale,
        "timezone": timezone_id,
        "prewarm": prewarm,
        "cookies": bool(cookies_json),
        "user_data_dir_override": bool(user_data_dir_override),
        "use_mobile": use_mobile,
        "via_search": via_search,
        "search_engine": search_engine,
        "referer": bool(referer),
    }


@router.get("/run")
async def crawl_sync(
    url: str = Query(...),
    headless: bool = Query(True),
    use_chrome: bool = Query(False),
    proxy: Optional[str] = Query(None),
    locale: str = Query("en-IN"),
    timezone_id: str = Query("Asia/Kolkata"),
    prewarm: bool = Query(True),
    cookies_json: Optional[str] = Query(None),
    user_data_dir_override: Optional[str] = Query(None),
    use_mobile: bool = Query(False),
    device_name: Optional[str] = Query(None),
    via_search: bool = Query(False),
    search_engine: str = Query("google"),
    referer: Optional[str] = Query(None),
    selectors_json: Optional[str] = Query(None),
    wait_selector: Optional[str] = Query(None),
):
    # Optional: allow foreground run for diagnostics
    return await crawl_url_to_disk(
        url,
        headless,
        use_chrome,
        proxy,
        locale,
        timezone_id,
        prewarm,
        cookies_json,
        user_data_dir_override,
        use_mobile,
        device_name,
        via_search,
        search_engine,
        referer,
        selectors_json,
        wait_selector,
    )


