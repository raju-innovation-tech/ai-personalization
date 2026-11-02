"""
Observability & Prometheus metrics collection for production monitoring.
"""
from collections import defaultdict
import threading
import time
from typing import Dict, Tuple

from fastapi import APIRouter, Response

from app.core.config import settings

metrics_router = APIRouter(tags=["Metrics"])


class PrometheusCollector:
    """Lightweight, thread-safe Prometheus metrics collector with zero external dependencies."""

    def __init__(self):
        self._lock = threading.Lock()
        # counters: (name, label_tuple) -> float
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        # gauges: (name, label_tuple) -> float
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        # histograms: (name, label_tuple) -> {"count": int, "sum": float}
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, float]] = defaultdict(
            lambda: {"count": 0.0, "sum": 0.0}
        )
        self._descriptions: Dict[str, str] = {
            "http_requests_total": "Total count of HTTP requests processed",
            "http_request_duration_seconds": "Duration of HTTP requests in seconds",
            "events_ingested_total": "Total number of e-commerce events ingested",
            "recommendations_served_total": "Total recommendations served by algorithm",
            "offers_evaluated_total": "Total offer evaluation operations",
            "app_info": "Application build and environment information",
        }
        self._types: Dict[str, str] = {
            "http_requests_total": "counter",
            "http_request_duration_seconds": "summary",
            "events_ingested_total": "counter",
            "recommendations_served_total": "counter",
            "offers_evaluated_total": "counter",
            "app_info": "gauge",
        }

        # Initialize base app info
        self.set_gauge("app_info", 1.0, {"version": "0.8.0", "env": settings.APP_ENV})

    def _labels_key(self, labels: dict | None) -> Tuple[Tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def inc_counter(self, name: str, value: float = 1.0, labels: dict | None = None) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            self._gauges[key] = value

    def observe_duration(self, name: str, duration_seconds: float, labels: dict | None = None) -> None:
        key = (name, self._labels_key(labels))
        with self._lock:
            entry = self._histograms[key]
            entry["count"] += 1.0
            entry["sum"] += duration_seconds

    def export(self) -> str:
        """Render metrics in standard Prometheus text format 0.0.4."""
        lines = []

        with self._lock:
            # Combine all metric names
            metric_names = set(
                [k[0] for k in self._counters.keys()]
                + [k[0] for k in self._gauges.keys()]
                + [k[0] for k in self._histograms.keys()]
            )

            for name in sorted(metric_names):
                desc = self._descriptions.get(name, f"Metric {name}")
                mtype = self._types.get(name, "untyped")
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} {mtype}")

                # Counters
                for (mname, labels), val in self._counters.items():
                    if mname == name:
                        lbl_str = ""
                        if labels:
                            lbl_str = "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}"
                        lines.append(f"{name}{lbl_str} {val}")

                # Gauges
                for (mname, labels), val in self._gauges.items():
                    if mname == name:
                        lbl_str = ""
                        if labels:
                            lbl_str = "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}"
                        lines.append(f"{name}{lbl_str} {val}")

                # Histograms / Summaries
                for (mname, labels), val in self._histograms.items():
                    if mname == name:
                        base_lbls = dict(labels) if labels else {}
                        lbl_count = dict(base_lbls)
                        lbl_sum = dict(base_lbls)

                        count_str = (
                            "{" + ",".join(f'{k}="{v}"' for k, v in sorted(lbl_count.items())) + "}"
                            if lbl_count
                            else ""
                        )
                        sum_str = (
                            "{" + ",".join(f'{k}="{v}"' for k, v in sorted(lbl_sum.items())) + "}"
                            if lbl_sum
                            else ""
                        )

                        lines.append(f"{name}_count{count_str} {int(val['count'])}")
                        lines.append(f"{name}_sum{sum_str} {val['sum']:.4f}")

        return "\n".join(lines) + "\n"


metrics_collector = PrometheusCollector()


@metrics_router.get("/metrics", response_class=Response)
async def get_metrics():
    """Prometheus scrape endpoint."""
    content = metrics_collector.export()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
