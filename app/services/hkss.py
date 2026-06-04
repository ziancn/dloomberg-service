"""
HKEX Short Sell Turnover Data Scraper
"""

import asyncio
import aiohttp
import html
import re
import json

from app.config import settings


async def fetch(session: aiohttp.ClientSession, url):
   async with session.get(url, proxy=settings.PROXY_URL) as resp:
       resp.raise_for_status()
       return await resp.text()


def is_ready(text):
   return re.search(r'will be available', text, re.I) is None


def preformatted_text_to_rows(text: str) -> list[dict]:
   pattern = re.compile(
       r'^\s*(?P<prefix>%?)\s*(?P<code>\d+)\s+'
       r'(?P<name>.*?)\s+'
       r'(?P<shares>[\d,]+)\s+'
       r'(?P<value>[\d,]+)\s*$'
   )

   rows = []

   for line in text.splitlines():
       # Stop parsing when we reach the summary section
       if line.startswith("Total No. of all Securities"): break

       m = pattern.match(line.rstrip())
       if m:
           rows.append({
               "code": m.group("code"),
               "name": html.unescape(m.group("name").strip()),
               "shares": int(m.group("shares").replace(",", "")),
               "value": int(m.group("value").replace(",", "")),
               "non_hkd": m.group("prefix") == "%"
           })

   return rows


def parse_summary(text):
   mkt_turnover_pattern = re.compile(r'Total market turnover\s*:\s*(?P<currency>[A-Z]{3})\s*(?P<value>[\d,]+)')
   non_etp_pct_pattern = re.compile(r'Short Selling of Designated Securities \(excluding ETP\) as % total turnover\s*:\s*(?P<pct>\d+)%')
   etp_pct_pattern = re.compile(r'Short Selling of Designated Securities \(ETP only\) as % total turnover\s*:\s*(?P<pct>\d+)%')
   all_pct_pattern = re.compile(r'Short Selling of all Designated Securities as % total turnover\s*:\s*(?P<pct>\d+)%')


   market_match = mkt_turnover_pattern.search(text)
   non_etp_match = non_etp_pct_pattern.search(text)
   etp_match = etp_pct_pattern.search(text)
   all_designated_match = all_pct_pattern.search(text)


   return {
       "total_market_turnover": {
           "currency": market_match.group("currency") if market_match else None,
           "value": int(market_match.group("value").replace(",", "")) if market_match else None,
       },
       "short_selling_pct": {
           "non_etp": int(non_etp_match.group("pct")) if non_etp_match else None,
           "etp_only": int(etp_match.group("pct")) if etp_match else None,
           "all_designated": int(all_designated_match.group("pct")) if all_designated_match else None,
       }
   }


def parse_page(text) -> dict:
   return {
       "ready": is_ready(text),
       "rows": preformatted_text_to_rows(text),
       "summary": parse_summary(text),
   }


async def fetch_and_parse(session, url) -> dict:
   text = await fetch(session, url)
   return {
       "url": url,
       "parsed": parse_page(text)
   }


async def main(urls) -> list[dict]:
   async with aiohttp.ClientSession() as session:
       tasks = [fetch_and_parse(session, url) for url in urls]
       return await asyncio.gather(*tasks)



urls = [
   "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/mshtmain.htm",  # Mainboard by AM
   "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/mshtgem.htm",   # GEM by AM
   "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ashtmain.htm",  # Mainboard by PM
   "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ashtgem.htm",   # GEM by PM
]


async def get_hkss_data():
   result = await main(urls)
   return result