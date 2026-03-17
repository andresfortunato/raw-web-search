"""Async URL fetching and content extraction via trafilatura.

Supports optional Playwright fallback for JS-rendered pages.
Install with: pip install open-search-mcp[browser]
"""

import asyncio
import logging

import httpx
import trafilatura

from .chunker import select_chunks

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0
MAX_CONCURRENT = 5
MAX_CONTENT_LENGTH = 20_000
TARGET_CHUNK_CHARS = 500

# Playwright is optional — detected at import time
_playwright_available = False
try:
    from playwright.async_api import async_playwright
    _playwright_available = True
except ImportError:
    pass


async def fetch_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str | None]:
    """Fetch a single URL, returning (url, html_or_none)."""
    async with semaphore:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return (url, resp.text)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return (url, None)


async def fetch_many(
    client: httpx.AsyncClient,
    urls: list[str],
    max_concurrent: int = MAX_CONCURRENT,
) -> dict[str, str | None]:
    """Fetch multiple URLs concurrently. Returns {url: html_or_none}."""
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [fetch_url(client, url, semaphore) for url in urls]
    results = await asyncio.gather(*tasks)
    return dict(results)


def extract_content(
    html: str,
    url: str,
    max_length: int = MAX_CONTENT_LENGTH,
) -> dict | None:
    """Extract clean markdown content from HTML using trafilatura.

    Returns {"title": str, "content": str} or None on failure.
    """
    try:
        content = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_formatting=True,
        )
        if not content or len(content.strip()) < 50:
            return None

        title = None
        metadata = trafilatura.extract_metadata(html, default_url=url)
        if metadata:
            title = metadata.title

        # Truncate at paragraph boundary if too long
        if len(content) > max_length:
            cut = content[:max_length].rfind("\n\n")
            if cut > max_length // 2:
                content = content[:cut]
            else:
                content = content[:max_length]

        return {"title": title or "", "content": content.strip()}
    except Exception as e:
        logger.warning("Extraction failed for %s: %s", url, e)
        return None


async def extract_content_async(
    html: str,
    url: str,
    max_length: int = MAX_CONTENT_LENGTH,
) -> dict | None:
    """Async wrapper — runs trafilatura in a thread pool."""
    return await asyncio.to_thread(extract_content, html, url, max_length)


async def fetch_with_playwright(
    urls: list[str],
    timeout_ms: int = 8000,
) -> dict[str, str | None]:
    """Fetch URLs using a headless browser. Handles JS-rendered pages.

    Returns {url: html_or_none}. Only called for URLs that failed with httpx.
    """
    if not _playwright_available:
        return {url: None for url in urls}

    results: dict[str, str | None] = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            for url in urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    # Brief wait for JS rendering
                    await page.wait_for_timeout(1000)
                    html = await page.content()
                    results[url] = html
                except Exception as e:
                    logger.warning("Playwright failed for %s: %s", url, e)
                    results[url] = None
            await browser.close()
    except Exception as e:
        logger.warning("Playwright browser launch failed: %s", e)
        return {url: None for url in urls}
    return results


async def fetch_and_extract(
    client: httpx.AsyncClient,
    urls: list[str],
    query: str | None = None,
    max_concurrent: int = MAX_CONCURRENT,
    max_length: int = MAX_CONTENT_LENGTH,
    target_chars: int = TARGET_CHUNK_CHARS,
) -> list[dict]:
    """Fetch URLs and extract content concurrently.

    Returns list of {"url": str, "title": str, "content": str}.
    Failed URLs are silently skipped. When query is provided, content is
    reduced to the most query-relevant chunks via embeddings.
    """
    html_map = await fetch_many(client, urls, max_concurrent)

    # Extract content concurrently via thread pool
    extract_tasks = []
    for url, html in html_map.items():
        if html is not None:
            extract_tasks.append((url, extract_content_async(html, url, max_length)))

    results = []
    failed_urls = []
    for url, task in extract_tasks:
        extracted = await task
        if extracted:
            results.append({"url": url, **extracted})
        else:
            failed_urls.append(url)

    # Also collect URLs that httpx couldn't fetch at all
    for url in urls:
        if url not in html_map or html_map[url] is None:
            if url not in failed_urls:
                failed_urls.append(url)

    # Playwright fallback for failed URLs (JS-rendered pages, 403s)
    if failed_urls and _playwright_available:
        logger.info("Retrying %d URLs with Playwright...", len(failed_urls))
        pw_html = await fetch_with_playwright(failed_urls)
        for url, html in pw_html.items():
            if html:
                extracted = await extract_content_async(html, url, max_length)
                if extracted:
                    results.append({"url": url, **extracted})

    # Apply chunk selection to all results
    final = []
    for r in results:
        content = r["content"]
        if query and len(content) > target_chars:
            content = await asyncio.to_thread(
                select_chunks, query, content, target_chars
            )
        final.append({
            "url": r["url"],
            "title": r["title"],
            "content": content,
        })

    return final
