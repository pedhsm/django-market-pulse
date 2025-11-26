import os
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Dict, Optional
import finnhub
from django.db import transaction
from dotenv import load_dotenv
from .sentiments import news_analysis
import json
from pathlib import Path

load_dotenv()

from core.models import Company, Article, MarketCandle

logger = logging.getLogger(__name__)


def run_candles_from_json_pipeline(
    data_path: str,                # folder with JSON files (e.g., "data_1h_7d_json")
    from_companies: bool = True,   # use active companies from DB
    tickers=None,                  # optional: manual tickers list
    throttle_seconds: float = 0.0, # sleep between tickers (seconds)
):
    """
    Read candles from JSON files with items like:
      { "time": "2025-09-05T14:00:00+00:00", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ... }
    and save into MarketCandle. Accepted filename pattern: "<TICKER>_1h_7d.json" (e.g., AAPL_1h_7d.json).
    """
    # ---- resolve tickers ----
    if from_companies:
        symbols = list(Company.objects.filter(is_active=True).values_list("ticker", flat=True))
    else:
        if not tickers:
            raise ValueError("Provide tickers or use from_companies=True.")
        symbols = list(tickers)

    base = Path(data_path)
    if not base.is_dir():
        raise FileNotFoundError(f"Invalid folder: {data_path}")

    results = []

    for sym in symbols:
        # expected file: <TICKER>_1h_7d.json
        f = base / f"{sym}_1h_7d.json"
        if not f or not f.exists():
            results.append({"ticker": sym, "inserted": 0})
            continue

        inserted = 0
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("JSON must be a list of objects.")

            to_create = []
            for it in data:
                ts = it.get("time")
                if not ts:
                    continue
                s = str(ts).strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"  # normalize Z to +00:00
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                to_create.append(
                    MarketCandle(
                        company=Company.objects.get(ticker__iexact=sym),
                        ts=dt,
                        open=it.get("open"),
                        high=it.get("high"),
                        low=it.get("low"),
                        close=it.get("close"),
                        volume=it.get("volume"),
                    )
                )

            with transaction.atomic():
                created = MarketCandle.objects.bulk_create(
                    to_create, ignore_conflicts=True, batch_size=1000
                )
            inserted = len(created)

        except Exception:
            inserted = 0  # keep going; per-ticker isolation

        results.append({"ticker": sym, "inserted": inserted})

        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    return results


def _get_finnhub():
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise RuntimeError("Define an API Key for Finnhub on .env!")
    return finnhub.Client(api_key=api_key)

# Finnhub returns a Unix timestamp (seconds)
def _utc_from_epoch(seconds=None):
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(int(seconds), tz=timezone.utc)
    except Exception:
        return None


def _resolve_tickers(tickers=(), from_companies=False):
    if from_companies:
        return list(Company.objects.filter(is_active=True).values_list("ticker", flat=True))
    if not tickers:
        raise ValueError("Provide tickers or use from_companies=True.")
    return list(tickers)


def run_news_pipeline(
    days: int = 7,
    tickers: Iterable[str] = None,
    from_companies: bool = False,
    throttle_seconds: float = 0.0,
    max_per_company: Optional[int] = None,  # NEW: hard cap per ticker (applied after sorting by recency)
) -> List[Dict[str, int]]:
    """
    Fetch company news for the given symbols within the last `days` and persist.
    - Synchronous (batch) pipeline; meant to be run outside request cycle.
    - Applies an optional hard limit per company *after* sorting by recency.
    - Idempotent via bulk_create(ignore_conflicts=True) at DB layer.
    """
    client = _get_finnhub()
    symbols = _resolve_tickers(tickers, from_companies)

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=days)
    date_from = from_dt.strftime("%Y-%m-%d")
    date_to = to_dt.strftime("%Y-%m-%d")

    results = []

    for symbol in symbols:
        inserted = skipped = errors = 0
        try:
            company = Company.objects.filter(ticker__iexact=symbol).first()
            if not company:
                raise ValueError(f"Company with ticker '{symbol}' not found")

            # 1) fetch raw items from provider
            raw_items = client.company_news(symbol, _from=date_from, to=date_to) or []

            # 2) sort by recency (descending). finnhub 'datetime' is epoch seconds.
            def _key(it):
                v = it.get("datetime") or it.get("published") or 0
                try:
                    return int(v)
                except Exception:
                    return 0
            raw_items.sort(key=_key, reverse=True)

            # 3) apply per-company hard limit (if any)
            if isinstance(max_per_company, int) and max_per_company > 0:
                raw_items = raw_items[:max_per_company]

            # 4) map + analyze sentiment (brief, defensive)
            to_create = []
            for item in raw_items:
                try:
                    url = item.get("url")
                    if not url:
                        skipped += 1  # ignore items without external URL
                        continue

                    published_dt = _utc_from_epoch(item.get("datetime"))
                    headline = (item.get("headline") or "").strip()

                    # Keep labels within {'Positive','Neutral','Negative'}
                    sentiment_label = "Neutral"
                    try:
                        tmp = news_analysis(headline)
                        if isinstance(tmp, str) and tmp.strip():
                            sentiment_label = tmp.strip()
                    except Exception as e:
                        logger.warning("sentiment error for %s: %s", symbol, str(e))

                    to_create.append(
                        Article(
                            company=company,
                            title=(headline or "(no title)")[:512],
                            url=url,
                            source=item.get("source") or "finnhub",
                            published=published_dt,
                            sentiment_label=sentiment_label,
                        )
                    )
                except Exception:
                    errors += 1  # skip malformed items but continue for the ticker

            # 5) persist in one transaction; ignore duplicates by DB constraint
            with transaction.atomic():
                created = Article.objects.bulk_create(
                    to_create, ignore_conflicts=True, batch_size=500
                )
                inserted = len(created)

            results.append(
                {
                    "ticker": symbol,
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                }
            )

        except Exception as e:
            logger.warning("news pipeline error for %s: %s", symbol, str(e))
            results.append({"ticker": symbol, "inserted": 0, "skipped": 0, "errors": 1})

        if throttle_seconds > 0:
            time.sleep(throttle_seconds)

    return results