# Dloomberg Terminal

Extending Bloomberg Terminal with custom functionality not natively supported.

## Setup

```bash
# Install dependencies
uv sync

# Configure settings in app/config.py

# Run the service
uv run uvicorn app.main:app
```

## Implemented

- Hong Kong exchange daily short sell turnover market data scraped from HKEX website.
- Bloomberg API: refdata, mktdata, bql

## Status

🚧 Work in progress. Features are being added incrementally.