import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

import requests

logger = logging.getLogger(__name__)

LicStatus = Literal["active", "all"]
SearchBy = Literal["individual", "corporation", "ceref"]


def search_licensee(
    keyword: str,
    licstatus: LicStatus = "active",
    searchby: SearchBy = "individual",
) -> dict:
    """
    Fetch all SFC licensee data with concurrent pagination.

    Args:
        keyword: Search keyword (name for individual/corporation, ceref for ceref search)
        licstatus: "active" or "all"
        searchby: "individual", "corporation", or "ceref"

    Returns:
        {"totalCount": N, "items": [...]}
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    })

    # 1. Initialize session by visiting homepage to get fresh cookies
    index_url = "https://apps.sfc.hk/publicregWeb/searchByName?locale=en"
    try:
        init_res = session.get(index_url, timeout=15)
        if init_res.status_code != 200:
            logger.error(f"Session init failed, status: {init_res.status_code}")
            return {"totalCount": 0, "items": []}
    except Exception as e:
        logger.error(f"Session init error: {e}")
        return {"totalCount": 0, "items": []}

    time.sleep(1)

    # 2. Prepare common parameters
    api_url = "https://apps.sfc.hk/publicregWeb/searchByNameJson"
    page_limit = 20

    api_headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://apps.sfc.hk',
        'Referer': index_url,
        'X-Requested-With': 'XMLHttpRequest'
    }

    # Determine searchbyoption and entityType from searchby
    if searchby == "ceref":
        searchbyoption = "byceref"
        entity_type = None
    elif searchby == "individual":
        searchbyoption = "byname"
        entity_type = "individual"
    else:  # corporation
        searchbyoption = "byname"
        entity_type = "corporation"

    def build_form_data(page_num: int):
        """Build form data for API request"""
        start = (page_num - 1) * page_limit
        data = {
            'licstatus': licstatus,
            'lictype': 'all',
            'searchbyoption': searchbyoption,
            'searchtext': keyword,
            'page': str(page_num),
            'start': str(start),
            'limit': str(page_limit),
            'sort': '[{"property":"ceref","direction":"ASC"}]',
        }
        if entity_type:
            data['entityType'] = entity_type
        if searchbyoption == "byname":
            data['searchlang'] = 'en'
        return data

    # 3. Request page 1 to get totalCount and first page data
    logger.info(f"Fetching page 1 (keyword={keyword}, searchby={searchby}, licstatus={licstatus})...")
    try:
        first_response = session.post(
            api_url,
            params={'_dc': str(int(time.time() * 1000))},
            headers=api_headers,
            data=build_form_data(1),
            timeout=30
        )
        if first_response.status_code != 200:
            logger.error(f"Page 1 request failed, status: {first_response.status_code}")
            return {"totalCount": 0, "items": []}

        first_json = first_response.json()
        total_count = first_json.get("totalCount", 0)
        all_items = first_json.get("items", [])
        logger.info(f"Page 1 returned {len(all_items)} items. API totalCount: {total_count}")

        if total_count == 0 or not all_items:
            return {"totalCount": total_count, "items": all_items}
    except Exception as e:
        logger.error(f"Page 1 request error: {e}")
        return {"totalCount": 0, "items": []}

    # 4. Calculate remaining pages
    total_pages = (total_count + page_limit - 1) // page_limit
    if total_pages <= 1:
        logger.info("All data fetched (only 1 page).")
        return {"totalCount": total_count, "items": all_items}

    remaining_pages = list(range(2, total_pages + 1))
    logger.info(f"Total pages: {total_pages}, fetching remaining {len(remaining_pages)} pages concurrently...")

    # 5. Concurrently fetch remaining pages
    def fetch_page(page_num: int):
        """Fetch a single page concurrently"""
        try:
            local_session = requests.Session()
            local_session.cookies.update(session.cookies)
            local_session.headers.update(session.headers)

            resp = local_session.post(
                api_url,
                params={'_dc': str(int(time.time() * 1000))},
                headers=api_headers,
                data=build_form_data(page_num),
                timeout=30
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                logger.info(f"Page {page_num} returned {len(items)} items.")
                return page_num, items
            else:
                logger.warning(f"Page {page_num} request failed, status: {resp.status_code}")
                return page_num, []
        except Exception as e:
            logger.error(f"Page {page_num} request error: {e}")
            return page_num, []

    pages_results: dict[int, list] = {}
    max_workers = min(len(remaining_pages), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {executor.submit(fetch_page, p): p for p in remaining_pages}
        for future in as_completed(future_to_page):
            page_num, items = future.result()
            pages_results[page_num] = items

    # 6. Merge results in page order
    for page_num in range(2, total_pages + 1):
        if page_num in pages_results:
            all_items.extend(pages_results[page_num])

    logger.info(f"All data fetched. Total: {len(all_items)} items.")
    return {"totalCount": total_count, "items": all_items}


# --- Test ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    test_keyword = "Sze Man"
    results = search_licensee(test_keyword, licstatus="active", searchby="individual")
    print(f"totalCount={results['totalCount']}, actual_items={len(results['items'])}")
    print(json.dumps(results, ensure_ascii=False, indent=2))