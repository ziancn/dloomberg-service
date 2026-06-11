"""
Leveraged ETF analysis service.
Computes tracking error, decay, and cumulative returns against the underlying.
Returns JSON-serializable chart data suitable for frontend rendering.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.config import settings


def analyze_leveraged_etf(
    letf_ticker: str,
    underlying_ticker: str,
    leverage: float = 2.0,
    start_date: str | None = None,
    end_date: str | None = None,
    ref_currency: str = "local",
) -> dict:
    """
    Analyze a leveraged ETF's tracking performance against its underlying.

    Parameters
    ----------
    letf_ticker : str
        Leveraged ETF ticker (e.g., '7709.HK').
    underlying_ticker : str
        Underlying index/stock ticker (e.g., '000660.KS').
    leverage : float
        Leverage multiplier of the LETF (default 2.0).
    start_date : str or None
        Start date in 'YYYY-MM-DD' format. Defaults to 1 year ago.
    end_date : str or None
        End date in 'YYYY-MM-DD' format. Defaults to today.
    ref_currency : str
        Reference currency for price comparison (e.g., 'HKD', 'USD').
        Defaults to 'local' (no currency adjustment).

    Returns
    -------
    dict
        {
            "meta": { ... },
            "dates": ["YYYY-MM-DD", ...],
            "charts": {
                "cumulative_returns": {
                    "series": [
                        {"name": "LETF", "data": [...]},
                        {"name": "Theoretical Nx", "data": [...]},
                        {"name": "Underlying xN (Simple)", "data": [...]},
                    ]
                },
                "decay": {
                    "series": [
                        {"name": "Decay", "data": [...]},
                    ]
                },
                "tracking_error": {
                    "series": [
                        {"name": "Daily Tracking Error", "data": [...]},
                    ]
                }
            }
        }
    """
    # Apply proxy if configured
    if settings.PROXY_URL:
        yf.set_config(proxy=settings.PROXY_URL)

    # ------------------------------------------------------------------
    # 1. Resolve date range
    # ------------------------------------------------------------------
    if end_date is None:
        end_dt = datetime.now()
        end = end_dt.strftime("%Y-%m-%d")
    else:
        end_dt = pd.Timestamp(end_date)
        end = end_date

    if start_date is None:
        start_dt = end_dt - timedelta(days=365)
        start = start_dt.strftime("%Y-%m-%d")
    else:
        start = start_date

    # ------------------------------------------------------------------
    # 2. Detect currencies and determine FX pairs
    # ------------------------------------------------------------------
    letf_fast = yf.Ticker(letf_ticker).fast_info
    undl_fast = yf.Ticker(underlying_ticker).fast_info

    letf_currency = letf_fast.currency
    undl_currency = undl_fast.currency

    if not letf_currency or not undl_currency:
        raise ValueError(
            f"Cannot determine currencies. LETF={letf_currency}, Underlying={undl_currency}"
        )

    # Build direct cross-rate FX pairs
    fx_pairs = set()
    need_letf_fx = ref_currency != "local" and letf_currency.upper() != ref_currency.upper()
    need_undl_fx = ref_currency != "local" and undl_currency.upper() != ref_currency.upper()

    if need_letf_fx:
        fx_pairs.add(f"{letf_currency.upper()}{ref_currency.upper()}=X")
    if need_undl_fx:
        fx_pairs.add(f"{undl_currency.upper()}{ref_currency.upper()}=X")

    fx_pairs = sorted(fx_pairs)

    # ------------------------------------------------------------------
    # 3. Download all price data
    # ------------------------------------------------------------------
    letf_df = yf.download(letf_ticker, start=start, end=end, auto_adjust=False)
    undl_df = yf.download(underlying_ticker, start=start, end=end, auto_adjust=False)

    def _extract_close(df, preferred_col="Adj Close"):
        """Extract close price from yfinance download DataFrame."""
        if isinstance(df.columns, pd.MultiIndex):
            if preferred_col in df.columns.get_level_values(0):
                col = df.xs(preferred_col, axis=1, level=0)
                if isinstance(col, pd.DataFrame):
                    return col.iloc[:, 0]
                return col
            elif "Close" in df.columns.get_level_values(0):
                col = df.xs("Close", axis=1, level=0)
                if isinstance(col, pd.DataFrame):
                    return col.iloc[:, 0]
                return col
            else:
                return df.iloc[:, 0]
        else:
            if preferred_col in df.columns:
                return df[preferred_col]
            elif "Close" in df.columns:
                return df["Close"]
            else:
                return df.iloc[:, 0]

    letf_price = _extract_close(letf_df).rename("LETF_Price")
    undl_price = _extract_close(undl_df).rename("Undl_Price")

    fx_data = {}
    for pair in fx_pairs:
        fx_df = yf.download(pair, start=start, end=end, auto_adjust=False)
        fx_data[pair] = _extract_close(fx_df).rename(pair)

    # ------------------------------------------------------------------
    # 4. Merge all data on date and drop NaN rows
    # ------------------------------------------------------------------
    merged = pd.concat(
        [letf_price, undl_price] + list(fx_data.values()), axis=1, sort=True
    )
    merged = merged.dropna()

    if merged.empty:
        raise ValueError("No overlapping data after merging. Check tickers and date range.")

    # ------------------------------------------------------------------
    # 5. Currency adjustment
    # ------------------------------------------------------------------
    if ref_currency != "local":
        if letf_currency.upper() != ref_currency.upper():
            letf_fx_col = f"{letf_currency.upper()}{ref_currency.upper()}=X"
            merged["LETF_FX_Mult"] = merged[letf_fx_col]
        else:
            merged["LETF_FX_Mult"] = 1.0

        if undl_currency.upper() != ref_currency.upper():
            undl_fx_col = f"{undl_currency.upper()}{ref_currency.upper()}=X"
            merged["Undl_FX_Mult"] = merged[undl_fx_col]
        else:
            merged["Undl_FX_Mult"] = 1.0

        merged["LETF_Price_FX"] = merged["LETF_Price"] * merged["LETF_FX_Mult"]
        merged["Undl_Price_FX"] = merged["Undl_Price"] * merged["Undl_FX_Mult"]
    else:
        merged["LETF_Price_FX"] = merged["LETF_Price"]
        merged["Undl_Price_FX"] = merged["Undl_Price"]

    # ------------------------------------------------------------------
    # 6. Compute daily returns
    # ------------------------------------------------------------------
    merged["LETF_Return"] = merged["LETF_Price_FX"].pct_change()
    merged["Undl_Return"] = merged["Undl_Price_FX"].pct_change()

    merged = merged.iloc[1:]  # drop first row (NaN pct_change)

    merged["Undl_Return_Nx"] = merged["Undl_Return"] * leverage

    # ------------------------------------------------------------------
    # 7. Tracking error (daily)
    # ------------------------------------------------------------------
    merged["Tracking_Error"] = merged["LETF_Return"] - merged["Undl_Return_Nx"]

    # ------------------------------------------------------------------
    # 8. Theoretical compounded N×
    # ------------------------------------------------------------------
    merged["Theoretical_Nx_Cum"] = (1 + merged["Undl_Return_Nx"]).cumprod()

    # ------------------------------------------------------------------
    # 9. Actual LETF cumulative
    # ------------------------------------------------------------------
    merged["LETF_Norm"] = (1 + merged["LETF_Return"]).cumprod()

    # ------------------------------------------------------------------
    # 10. Simple N× underlying
    # ------------------------------------------------------------------
    merged["Undl_Norm"] = (1 + merged["Undl_Return"]).cumprod()
    merged["Undl_Nx_Simple"] = (merged["Undl_Norm"] - 1) * leverage + 1

    # ------------------------------------------------------------------
    # 11. Decay
    # ------------------------------------------------------------------
    merged["Decay"] = merged["LETF_Norm"] - merged["Theoretical_Nx_Cum"]

    # ------------------------------------------------------------------
    # 12. Build JSON-serializable response
    # ------------------------------------------------------------------
    dates = merged.index.strftime("%Y-%m-%d").tolist()

    response = {
        "meta": {
            "letf_ticker": letf_ticker,
            "underlying_ticker": underlying_ticker,
            "leverage": leverage,
            "start_date": dates[0],
            "end_date": dates[-1],
            "data_points": len(dates),
            "letf_currency": letf_currency,
            "underlying_currency": undl_currency,
            "ref_currency": ref_currency if ref_currency != "local" else "local (no adjustment)",
            "fx_pairs_used": fx_pairs,
        },
        "dates": dates,
        "charts": {
            "cumulative_returns": {
                "title": "Cumulative Normalized Returns",
                "x_label": "Date",
                "y_label": "Normalized Price",
                "series": [
                    {
                        "name": f"{letf_ticker} (LETF)",
                        "data": [round(v, 6) for v in merged["LETF_Norm"].tolist()],
                    },
                    {
                        "name": f"Theoretical {leverage}x {underlying_ticker} (Compounded)",
                        "data": [round(v, 6) for v in merged["Theoretical_Nx_Cum"].tolist()],
                    },
                    {
                        "name": f"{underlying_ticker} x{leverage} (Simple)",
                        "data": [round(v, 6) for v in merged["Undl_Nx_Simple"].tolist()],
                    },
                ],
            },
            "decay": {
                "title": "Decay (LETF - Theoretical Nx Compounded)",
                "x_label": "Date",
                "y_label": "Decay",
                "series": [
                    {
                        "name": "Decay",
                        "data": [round(v, 6) for v in merged["Decay"].tolist()],
                    },
                ],
            },
            "tracking_error": {
                "title": "Daily Tracking Error",
                "x_label": "Date",
                "y_label": "Tracking Error",
                "series": [
                    {
                        "name": "Daily Tracking Error",
                        "data": [round(v, 6) for v in merged["Tracking_Error"].tolist()],
                    },
                ],
            },
        },
    }

    return response



if __name__ == "__main__":
    analyze_leveraged_etf(
        letf_ticker="7709.HK",
        underlying_ticker="000660.KS",
        leverage=2.0,
        ref_currency="local",
    )