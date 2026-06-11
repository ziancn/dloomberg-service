import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Literal

import requests

from app.config import settings

logger = logging.getLogger(__name__)

LicStatus = Literal["active", "all"]
SearchBy = Literal["individual", "corporation", "ceref"]

# All 10 SFC licence types with descriptions
ALL_LICENCE_TYPES: list[dict] = [
    {"actType": 1, "actDesc": "Dealing in Securities", "cactDesc": "證券交易"},
    {"actType": 2, "actDesc": "Dealing in Futures Contracts", "cactDesc": "期貨合約交易"},
    {"actType": 3, "actDesc": "Leveraged Foreign Exchange Trading", "cactDesc": "槓桿式外匯交易"},
    {"actType": 4, "actDesc": "Advising on Securities", "cactDesc": "就證券提供意見"},
    {"actType": 5, "actDesc": "Advising on Futures Contracts", "cactDesc": "就期貨合約提供意見"},
    {"actType": 6, "actDesc": "Advising on Corporate Finance", "cactDesc": "就機構融資提供意見"},
    {"actType": 7, "actDesc": "Providing Automated Trading Services", "cactDesc": "提供自動化交易服務"},
    {"actType": 8, "actDesc": "Securities Margin Financing", "cactDesc": "證券保證金融資"},
    {"actType": 9, "actDesc": "Asset Management", "cactDesc": "資產管理"},
    {"actType": 10, "actDesc": "Providing Credit Rating Services", "cactDesc": "提供信貸評級服務"},
]

# ---------------------------------------------------------------------------
# Shared HTTP helpers
# ---------------------------------------------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if settings.PROXY_URL is not None:
        session.proxies = {"http": settings.PROXY_URL, "https": settings.PROXY_URL}
    return session


# ---------------------------------------------------------------------------
# HTML scraping helpers
# ---------------------------------------------------------------------------

# Pattern:  var varname = [{...}];
_JS_VAR_RE = re.compile(
    r"""var\s+(?P<varname>[A-Za-z_]\w*)\s*=\s*(?P<json>\[[\s\S]*?\])\s*;""",
)

# Pattern: "Mar 27, 2025 12:00:00 AM" (Java/ExtJS date format used by SFC)
_SFC_DATE_RE = re.compile(
    r"""^(?P<m>[A-Z][a-z]{2})\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M$"""
)
_SFC_DATE_FMT = "%b %d, %Y %I:%M:%S %p"


def _normalize_dates(obj: Any) -> Any:
    """Recursively walk a JSON-like structure and convert SFC date strings
    (e.g. ``"Mar 27, 2025 12:00:00 AM"``) to ``"YYYY-MM-DD"``.
    """
    if isinstance(obj, dict):
        return {k: _normalize_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_dates(v) for v in obj]
    if isinstance(obj, str) and _SFC_DATE_RE.match(obj):
        try:
            return datetime.strptime(obj, _SFC_DATE_FMT).strftime("%Y-%m-%d")
        except ValueError:
            return obj
    return obj


def _extract_js_vars(html: str) -> dict[str, list[dict]]:
    """Extract all *top-level-array* JavaScript var assignments from HTML.

    Returns a dict mapping variable name → parsed JSON list.
    """
    result: dict[str, list[dict]] = {}
    for m in _JS_VAR_RE.finditer(html):
        name = m.group("varname")
        raw = m.group("json")
        try:
            result[name] = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON for JS var %r", name)
    return result


# ---------------------------------------------------------------------------
# Page-specific parsers
# ---------------------------------------------------------------------------

def _parse_details_page(html: str) -> dict[str, Any]:
    """Parse the /indi/{ceref}/details HTML."""
    all_vars = _extract_js_vars(html)
    return {
        "sfoLicences": all_vars.get("indData", []),
        "amloLicences": all_vars.get("amloindData", []),
    }


def _parse_licence_record_page(html: str) -> dict[str, Any]:
    """Parse the /indi/{ceref}/licenceRecord HTML."""
    all_vars = _extract_js_vars(html)
    return {
        "sfoRecords": all_vars.get("licRecordData", []),
        "amloRecords": all_vars.get("amlolicRecordData", []),
    }


# ---------------------------------------------------------------------------
# High-level: fetch + parse multiple pages concurrently
# ---------------------------------------------------------------------------

# Page definitions – add new pages here as needed.
# Key = logical name, value = URL path segment after ceref.
_INDIVIDUAL_PAGES: dict[str, str] = {
    "details": "details",
    "licenceRecord": "licenceRecord",
    # future: "addresses": "addresses",
    # future: "conditions": "conditions",
    # future: "disciplinaryAction": "disciplinaryAction",
}


def _fetch_page(
    session: requests.Session,
    ceref: str,
    page_path: str,
    *,
    timeout: int = 30,
) -> str | None:
    """Fetch a single HTML page; return *html* or *None* on failure."""
    url = f"https://apps.sfc.hk/publicregWeb/indi/{ceref}/{page_path}"
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
        logger.warning("Non-200 (%d) for %s", resp.status_code, url)
        return None
    except Exception:
        logger.exception("Request failed for %s", url)
        return None


def search_indi_details(ceref: str) -> dict[str, Any]:
    """Fetch all individual details sub-pages and return parsed table data.

    Currently fetches:
        - /indi/{ceref}/details       → sfoLicences, amloLicences
        - /indi/{ceref}/licenceRecord → sfoRecords, amloRecords

    Returns a dict keyed by logical page name + parsed fields.
    """
    session = _make_session()

    # Fetch all pages concurrently
    html_results: dict[str, str | None] = {}
    max_workers = min(len(_INDIVIDUAL_PAGES), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_page, session, ceref, path): name
            for name, path in _INDIVIDUAL_PAGES.items()
        }
        for future in as_completed(future_map):
            name = future_map[future]
            html_results[name] = future.result()

    # Parse
    result: dict[str, Any] = {"ceref": ceref}

    details_html = html_results.get("details")
    if details_html:
        result.update(_parse_details_page(details_html))

    lr_html = html_results.get("licenceRecord")
    if lr_html:
        result.update(_parse_licence_record_page(lr_html))

    # Normalize all date strings to YYYY-MM-DD
    return _normalize_dates(result)


# ---------------------------------------------------------------------------
# search_licensee (existing API-based search)
# ---------------------------------------------------------------------------

def _normalize_licences(items: list[dict]) -> list[dict]:
    """Expand raDetails so every item shows all 10 licence types with hasLicence bool."""
    for item in items:
        existing_types: set[int] = {
            detail["actType"] for detail in item.get("raDetails", [])
        }
        item["raDetails"] = [
            {**licence_def, "hasLicence": licence_def["actType"] in existing_types}
            for licence_def in ALL_LICENCE_TYPES
        ]
    return items


def search_licensee(
    keyword: str,
    licstatus: LicStatus = "active",
    searchby: SearchBy = "individual",
) -> dict:
    """Fetch SFC licensee list via the JSON API with concurrent pagination."""
    session = _make_session()

    # 1. Warm up session cookies
    index_url = "https://apps.sfc.hk/publicregWeb/searchByName?locale=en"
    try:
        init_res = session.get(index_url, timeout=15)
        if init_res.status_code != 200:
            logger.error("Session init failed, status: %s", init_res.status_code)
            return {"totalCount": 0, "items": []}
    except Exception:
        logger.exception("Session init error")
        return {"totalCount": 0, "items": []}

    time.sleep(1)

    api_url = "https://apps.sfc.hk/publicregWeb/searchByNameJson"
    page_limit = 20

    api_headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://apps.sfc.hk",
        "Referer": index_url,
        "X-Requested-With": "XMLHttpRequest",
    }

    # Determine searchbyoption / entityType
    if searchby == "ceref":
        searchbyoption = "byceref"
        entity_type = None
    elif searchby == "individual":
        searchbyoption = "byname"
        entity_type = "individual"
    else:  # corporation
        searchbyoption = "byname"
        entity_type = "corporation"

    def _build_form(page_num: int) -> dict:
        start = (page_num - 1) * page_limit
        data = {
            "licstatus": licstatus,
            "lictype": "all",
            "searchbyoption": searchbyoption,
            "searchtext": keyword,
            "page": str(page_num),
            "start": str(start),
            "limit": str(page_limit),
            "sort": '[{"property":"ceref","direction":"ASC"}]',
        }
        if entity_type:
            data["entityType"] = entity_type
        if searchbyoption == "byname":
            data["searchlang"] = "en"
        return data

    # 2. Page 1
    logger.info(
        "Fetching page 1 (keyword=%r, searchby=%s, licstatus=%s)...",
        keyword,
        searchby,
        licstatus,
    )
    try:
        first_resp = session.post(
            api_url,
            params={"_dc": str(int(time.time() * 1000))},
            headers=api_headers,
            data=_build_form(1),
            timeout=30,
        )
        if first_resp.status_code != 200:
            logger.error("Page 1 request failed, status: %s", first_resp.status_code)
            return {"totalCount": 0, "items": []}

        first_json = first_resp.json()
        total_count = first_json.get("totalCount", 0)
        all_items: list[dict] = first_json.get("items", [])
        logger.info("Page 1 returned %d items. API totalCount: %d", len(all_items), total_count)

        if total_count == 0 or not all_items:
            return {"totalCount": total_count, "items": _normalize_licences(all_items)}
    except Exception:
        logger.exception("Page 1 request error")
        return {"totalCount": 0, "items": []}

    # 3. Remaining pages
    total_pages = (total_count + page_limit - 1) // page_limit
    if total_pages <= 1:
        return {"totalCount": total_count, "items": _normalize_licences(all_items)}

    remaining = list(range(2, total_pages + 1))
    logger.info("Total pages: %d, fetching %d more concurrently...", total_pages, len(remaining))

    def _fetch_one(page_num: int):
        try:
            s = requests.Session()
            s.cookies.update(session.cookies)
            s.headers.update(session.headers)
            if settings.PROXY_URL is not None:
                s.proxies = {"http": settings.PROXY_URL, "https": settings.PROXY_URL}
            r = s.post(
                api_url,
                params={"_dc": str(int(time.time() * 1000))},
                headers=api_headers,
                data=_build_form(page_num),
                timeout=30,
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                logger.info("Page %d returned %d items.", page_num, len(items))
                return page_num, items
            logger.warning("Page %d request failed, status: %d", page_num, r.status_code)
            return page_num, []
        except Exception:
            logger.exception("Page %d request error", page_num)
            return page_num, []

    pages_map: dict[int, list[dict]] = {}
    max_w = min(len(remaining), 5)
    with ThreadPoolExecutor(max_workers=max_w) as executor:
        f2p = {executor.submit(_fetch_one, p): p for p in remaining}
        for future in as_completed(f2p):
            pn, items = future.result()
            pages_map[pn] = items

    for pn in range(2, total_pages + 1):
        if pn in pages_map:
            all_items.extend(pages_map[pn])

    logger.info("All data fetched. Total: %d items.", len(all_items))
    return {"totalCount": total_count, "items": _normalize_licences(all_items)}


# ---------------------------------------------------------------------------
# search_corp_details (placeholder)
# ---------------------------------------------------------------------------

def search_corp_details():
    ...


# ---------------------------------------------------------------------------
# Quick manual test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # --- Test 1: search_licensee (existing) ---
    # print("=" * 60)
    # print("Test: search_licensee")
    # results = search_licensee("chen zian", licstatus="active", searchby="individual")
    # print(f"  totalCount={results['totalCount']}, actual_items={len(results['items'])}")
    # if results["items"]:
    #     first = results["items"][0]
    #     print(f"  First result: {first.get('cename')} ({first.get('ceref')})")

    # --- Test 2: search_indi_details (new) ---
    print("=" * 60)
    print("Test: search_indi_details")
    test_ceref = "BTB840"
    details = search_indi_details(test_ceref)
    print(f"  ceref: {details['ceref']}")
    print(f"  sfoLicences count: {len(details.get('sfoLicences', []))}")
    print(f"  amloLicences count: {len(details.get('amloLicences', []))}")
    print(f"  sfoRecords count:   {len(details.get('sfoRecords', []))}")
    print(f"  amloRecords count:  {len(details.get('amloRecords', []))}")

    # Pretty-print a sample from each
    if details.get("sfoLicences"):
        print("\n  Sample sfoLicences:")
        print(json.dumps(details["sfoLicences"], indent=4, ensure_ascii=False))
    if details.get("sfoRecords"):
        print("\n  Sample sfoRecords:")
        print(json.dumps(details["sfoRecords"], indent=4, ensure_ascii=False))