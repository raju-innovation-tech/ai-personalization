"""
Orchestrates a Welfog -> engine sync.

    python -m scripts.welfog_sync --dry-run                  # read + map only, nothing is sent
    python -m scripts.welfog_sync                            # every source, resumes from the saved state
    python -m scripts.welfog_sync --sources orders,carts     # only some sources
    python -m scripts.welfog_sync --full                     # ignore saved state, start from the beginning

``run_source`` is free of I/O (the page reader, the mapper, the sender and the state saver are passed in),
so the paging / resume logic is unit-tested without a database or an HTTP server.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from dotenv import load_dotenv

from app.integrations.welfog import mapping, readers

ALL_SOURCES = ("products", "orders", "carts", "wishlists", "reviews", "user_events")
MAX_BATCH = 500  # engine limit for /events/batch and /products/bulk


@dataclass
class SourceReport:
    name: str
    rows_read: int = 0
    produced: int = 0
    skipped: Counter = field(default_factory=Counter)
    sent: tuple[int, int, int] = (0, 0, 0)  # (accepted|created, duplicates|updated, rejected)

    def line(self) -> str:
        skipped = ", ".join(f"{k}={v}" for k, v in sorted(self.skipped.items())) or "none"
        return (f"{self.name:12} rows={self.rows_read:<7} produced={self.produced:<7} "
                f"sent(a/b/rejected)={self.sent[0]}/{self.sent[1]}/{self.sent[2]}  skipped: {skipped}")


# ------------------------------------------------------------------------------ state
class StateStore:
    """Tiny JSON file holding one watermark per source; written atomically."""

    def __init__(self, path: str | None):
        self.path = path
        self.data: dict = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.data = json.load(fh)

    def get(self, name: str) -> dict:
        return dict(self.data.get(name) or {})

    def set(self, name: str, watermark: dict) -> None:
        self.data[name] = watermark
        if not self.path:
            return
        directory = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)


def _encode_ts(value) -> str | None:
    return value.isoformat(sep=" ") if isinstance(value, datetime) else (str(value) if value is not None else None)


def _decode_ts(value):
    return datetime.fromisoformat(value) if value else None


# ------------------------------------------------------------------------------- core
def run_source(
    *,
    spec: readers.SourceSpec,
    fetch: Callable[[object, int | None, int], list[dict]],  # (after_ts, after_id, limit) -> rows
    mapper: Callable[[dict], object],  # row -> MapResult | ProductResult
    send: Callable[[list[dict]], tuple[int, int, int]] | None,  # None = dry run
    watermark: dict,
    save: Callable[[dict], None],
    page_size: int = 500,
    max_rows: int | None = None,
) -> SourceReport:
    report = SourceReport(spec.name)
    after_ts, after_id = _decode_ts(watermark.get("ts")), watermark.get("id")
    page_size = max(1, min(page_size, MAX_BATCH))

    while max_rows is None or report.rows_read < max_rows:
        limit = page_size if max_rows is None else min(page_size, max_rows - report.rows_read)
        rows = fetch(after_ts, after_id, limit)
        if not rows:
            break
        items: list[dict] = []
        for row in rows:
            result = mapper(row)
            if isinstance(result, mapping.ProductResult):
                produced = [result.product] if result.product else []
            else:
                produced = result.events
            items.extend(produced)
            if not produced:
                report.skipped[result.skipped or "skipped"] += 1
        report.rows_read += len(rows)
        report.produced += len(items)

        if send is not None:
            for start in range(0, len(items), MAX_BATCH):
                a, b, c = send(items[start:start + MAX_BATCH])
                report.sent = (report.sent[0] + a, report.sent[1] + b, report.sent[2] + c)

        last = rows[-1]
        after_ts, after_id = readers.row_timestamp(spec, last), last[spec.id_col]
        if send is not None:  # only a successful send moves the saved watermark
            save({"ts": _encode_ts(after_ts), "id": int(after_id)})
        if len(rows) < limit:
            break
    return report


# ------------------------------------------------------------------------------- CLI
def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def build_options() -> mapping.MapOptions:
    start = _env("WELFOG_EVENTS_TABLE_START")
    return mapping.MapOptions(
        source_tz=_env("WELFOG_SOURCE_TZ", "UTC"),
        image_base_url=_env("WELFOG_IMAGE_BASE_URL"),
        events_table_start=datetime.fromisoformat(start) if start else None,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Sync Welfog data into the AI personalization engine")
    parser.add_argument("--sources", default=",".join(ALL_SOURCES), help=f"comma list of: {', '.join(ALL_SOURCES)}")
    parser.add_argument("--dry-run", action="store_true", help="read and map only; send nothing, save no state")
    parser.add_argument("--full", action="store_true", help="ignore the saved state and start from the beginning")
    parser.add_argument("--limit", type=int, default=None, help="max rows to read per source")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH)
    args = parser.parse_args(argv)

    names = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [n for n in names if n not in ALL_SOURCES]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")

    opts = build_options()
    state = StateStore(_env("WELFOG_SYNC_STATE", "welfog_sync_state.json"))
    engines: dict[str, object] = {}
    urls = {"mysql": _env("WELFOG_MYSQL_URL"), "postgres": _env("WELFOG_PG_URL")}

    client = None
    if not args.dry_run:
        from app.integrations.welfog.client import EngineClient

        client = EngineClient(
            _env("AI_ENGINE_URL", "http://localhost:8000/api/v1"), _env("AI_ENGINE_EMAIL"), _env("AI_ENGINE_PASSWORD")
        )

    mappers = {
        "products": lambda r: mapping.map_product(r, opts), "orders": lambda r: mapping.map_order(r, opts),
        "carts": lambda r: mapping.map_cart(r, opts), "wishlists": lambda r: mapping.map_wishlist(r, opts),
        "reviews": lambda r: mapping.map_review(r, opts), "user_events": lambda r: mapping.map_user_event(r, opts),
    }
    exit_code = 0
    try:
        for name in names:
            spec = readers.SOURCES[name]
            url = urls[spec.db]
            if not url:
                print(f"{name}: skipped - set {'WELFOG_MYSQL_URL' if spec.db == 'mysql' else 'WELFOG_PG_URL'}", file=sys.stderr)
                exit_code = 1
                continue
            engine = engines.setdefault(spec.db, readers.make_engine(url))
            try:
                columns = readers.pick_columns(spec, readers.available_columns(engine, spec))
            except Exception as exc:  # e.g. user_events table not created yet
                print(f"{name}: skipped - {exc}", file=sys.stderr)
                exit_code = 1
                continue
            send = None
            if client is not None:
                send = client.upsert_products if name == "products" else client.post_events
            report = run_source(
                spec=spec,
                fetch=lambda ts, rid, limit, _e=engine, _s=spec, _c=columns: readers.read_page(_e, _s, _c, ts, rid, limit),
                mapper=mappers[name],
                send=send,
                watermark={} if args.full else state.get(name),
                save=lambda wm, _n=name: state.set(_n, wm),
                page_size=args.batch_size,
                max_rows=args.limit,
            )
            print(report.line())
            if report.sent[2]:
                print(f"  WARNING: {report.sent[2]} item(s) were rejected by the engine", file=sys.stderr)
                exit_code = 1
    finally:
        if client is not None:
            client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
