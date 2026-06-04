"""
This module implements Bloomberg Query via Excel as a workaround if you don't
have access to BQL from API
"""

import math
import asyncio
import xlwings as xw
from pathlib import Path


async def excel_bql(query: str) -> list[str, any]:
    wb = xw.Book(Path(__file__).parent / "bql.xlsx")
    ws = wb.sheets[0]
    ws.clear_contents()
    ws.range("A1").formula = f'=BQL.Query("{query}")'

    # Loop to check if data arrived
    timeout_seconds, retry_interval = 20, 0.2
    max_retries = int(math.ceil(timeout_seconds/retry_interval))
    
    for i in range(max_retries):
        await asyncio.sleep(retry_interval)
        
        a1_val = ws.range("A1").value
        if a1_val is None: continue
            
        a1_str = str(a1_val).strip()
        if "Requesting" in a1_str or a1_str == "nan" or a1_str == "#N/A": continue
        
        break

    # Parse result
    if "Requesting" in a1_str: raise TimeoutError("BQL.Query timeout.")
    elif "ERR" in a1_str or "Review" in a1_str: raise ValueError("BQL.Query error.")

    current_table = ws.range("A1").expand()
    table_value = current_table.value

    if not isinstance(table_value, list):
        # Only one cell (single underlying and single field)
        formatted_json = [{"value": table_value}]
    elif not isinstance(table_value[0], list):
        if len(table_value) == 1:
            # Safety check, if still only one cell
            formatted_json = [{"value": table_value[0]}]
        else:
            # Only one column of data
            header = str(table_value[0])
            formatted_json = [{header: row} for row in table_value[1:]]
    else:
        # Clear all-empty rows
        clean_table = [row for row in table_value if any(cell is not None for cell in row)]
        if len(clean_table) == 1:
            # Only one row
            formatted_json = [{"value": cell} for cell in clean_table[0]]
        else:
            # Standard 2-dimensional table
            headers = [str(h) if h is not None else f"col_{idx}" for idx, h in enumerate(clean_table[0])]
            rows = clean_table[1:]
            formatted_json = [dict(zip(headers, row)) for row in rows]

    return formatted_json
