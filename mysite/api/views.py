from rest_framework import viewsets
from rest_framework.response import Response
from core.models import Company, Article, MarketCandle
from .serializers import CompanySerializer, ArticleSerializer, MarketCandleSerializer


class CompanyViewSet(viewsets.ModelViewSet):
    """Companies endpoint.
    Filters:
      - ?company=NVDA or ?ticker=NVDA  -> matches ticker (case-insensitive)
      - list-only: ?limit=N            -> slice the queryset
    """

    queryset = Company.objects.all().order_by("id")
    serializer_class = CompanySerializer
    lookup_field = "ticker"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        qs = super().get_queryset()
        qp = self.request.query_params

        # Accept both ?company and ?ticker
        sym = qp.get("company") or qp.get("ticker")
        if sym:
            qs = qs.filter(ticker__iexact=sym)

        # Optional: list-level limit
        if getattr(self, "action", None) == "list":
            raw = qp.get("limit")
            if raw:
                try:
                    n = int(raw)
                    if n > 0:
                        qs = qs[:n]
                except Exception:
                    pass
        return qs


class ArticleViewSet(viewsets.ModelViewSet):
    """Articles endpoint.
    Filters:
      - ?company=NVDA or ?ticker=NVDA  -> by company ticker
      - ?start=YYYY-MM-DD              -> published__date__gte
      - ?end=YYYY-MM-DD                -> published__date__lte
      - list-only: ?limit=N            -> slice the queryset
    """

    queryset = Article.objects.all().order_by("-id")  # keep your current ordering
    serializer_class = ArticleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        qp = self.request.query_params

        # Filter by company ticker (supports ?company or ?ticker)
        sym = qp.get("company") or qp.get("ticker")
        if sym:
            qs = qs.filter(company__ticker__iexact=sym)

        # Optional date filters
        start = qp.get("start")
        end = qp.get("end")
        if start:
            qs = qs.filter(published__date__gte=start)
        if end:
            qs = qs.filter(published__date__lte=end)

        # Optional list limit
        if getattr(self, "action", None) == "list":
            raw = qp.get("limit")
            if raw:
                try:
                    n = int(raw)
                    if n > 0:
                        qs = qs[:n]
                except Exception:
                    pass
        return qs

    def list(self, request, *args, **kwargs):
        """Opt-in envelope for empty results: `?meta=1` → {"status":"loading",...}
        Default remains a raw list for backward compatibility.
        """
        want_meta = str(request.query_params.get("meta", "")).lower() in {"1", "true", "yes"}
        queryset = self.filter_queryset(self.get_queryset())

        if not want_meta:
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

        # With meta envelope
        if not queryset.exists():
            return Response({"status": "loading", "count": 0, "results": []})

        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        return Response({"status": "ok", "count": len(data), "results": data})


class MarketCandleViewSet(viewsets.ModelViewSet):
    """Market candles endpoint.
    Filters:
      - ?company=NVDA or ?ticker=NVDA  -> by company ticker
      - ?start=YYYY-MM-DD              -> ts__date__gte
      - ?end=YYYY-MM-DD                -> ts__date__lte
      - list-only: ?limit=N            -> slice the queryset
    """

    queryset = MarketCandle.objects.all().order_by("id")  # keep your current ordering
    serializer_class = MarketCandleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        qp = self.request.query_params

        # Filter by company ticker (supports ?company or ?ticker)
        sym = qp.get("company") or qp.get("ticker")
        if sym:
            qs = qs.filter(company__ticker__iexact=sym)

        # Optional date filters
        start = qp.get("start")
        end = qp.get("end")
        if start:
            qs = qs.filter(ts__date__gte=start)
        if end:
            qs = qs.filter(ts__date__lte=end)

        # Optional list limit
        if getattr(self, "action", None) == "list":
            raw = qp.get("limit")
            if raw:
                try:
                    n = int(raw)
                    if n > 0:
                        qs = qs[:n]
                except Exception:
                    pass
        return qs
