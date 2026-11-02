"""
Production Load Testing & Performance Benchmark CLI Tool.

Usage:
  python -m scripts.load_test --scenario mixed --concurrency 25 --requests 500
  python -m scripts.load_test --scenario recommendations --concurrency 50 --requests 1000
  python -m scripts.load_test --scenario events --concurrency 20 --requests 300
"""
import argparse
import asyncio
import datetime
import random
import sys
import time
from typing import List, Tuple

import httpx


class LoadTestRunner:
    def __init__(self, base_url: str, concurrency: int, total_requests: int, scenario: str):
        self.base_url = base_url.rstrip("/")
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.scenario = scenario
        self.latencies: List[float] = []
        self.status_codes: dict[int, int] = {}
        self.errors: int = 0

    async def _make_request(self, client: httpx.AsyncClient, req_index: int) -> Tuple[int, float]:
        user_id = f"USER_{random.randint(10001, 10100)}"
        prod_id = f"PROD_{random.randint(1001, 1050)}"

        # Select request based on scenario
        method = "GET"
        url = f"{self.base_url}/api/v1/health"
        payload = None

        if self.scenario == "recommendations":
            url = f"{self.base_url}/api/v1/recommendations/user/{user_id}"
        elif self.scenario == "events":
            method = "POST"
            url = f"{self.base_url}/api/v1/events"
            payload = {
                "event_type": random.choice(["PRODUCT_VIEW", "ADD_TO_CART", "PURCHASE"]),
                "external_user_id": user_id,
                "product_id": prod_id,
                "session_id": f"sess-{random.randint(100, 999)}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        elif self.scenario == "offers":
            url = f"{self.base_url}/api/v1/offers/user/{user_id}?cart_value={random.randint(500, 5000)}"
        elif self.scenario == "mixed":
            roll = random.random()
            if roll < 0.70:
                url = f"{self.base_url}/api/v1/recommendations/user/{user_id}"
            elif roll < 0.90:
                method = "POST"
                url = f"{self.base_url}/api/v1/events"
                payload = {
                    "event_type": "PRODUCT_VIEW",
                    "external_user_id": user_id,
                    "product_id": prod_id,
                    "session_id": f"sess-{random.randint(100, 999)}",
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            else:
                url = f"{self.base_url}/api/v1/offers/user/{user_id}?cart_value=1500"

        start = time.perf_counter()
        try:
            if method == "POST":
                res = await client.post(url, json=payload, timeout=10.0)
            else:
                res = await client.get(url, timeout=10.0)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return res.status_code, elapsed_ms
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return 0, elapsed_ms

    async def _worker(self, queue: asyncio.Queue, client: httpx.AsyncClient):
        while not queue.empty():
            idx = await queue.get()
            status, duration = await self._make_request(client, idx)
            self.latencies.append(duration)
            if status == 0 or status >= 500:
                self.errors += 1
            self.status_codes[status] = self.status_codes.get(status, 0) + 1
            queue.task_done()

    async def run(self):
        print(f"\n🚀 Starting Load Test against {self.base_url}")
        print(f"   Scenario:    {self.scenario}")
        print(f"   Requests:    {self.total_requests}")
        print(f"   Concurrency: {self.concurrency}\n")

        queue: asyncio.Queue = asyncio.Queue()
        for i in range(self.total_requests):
            queue.put_nowait(i)

        limits = httpx.Limits(max_connections=self.concurrency + 10, max_keepalive_connections=self.concurrency)
        async with httpx.AsyncClient(limits=limits) as client:
            # Warm up
            try:
                await client.get(f"{self.base_url}/api/v1/health")
            except Exception as e:
                print(f"❌ Target unreachable at {self.base_url}: {e}")
                return

            start_time = time.perf_counter()
            workers = [asyncio.create_task(self._worker(queue, client)) for _ in range(self.concurrency)]
            await queue.join()
            for w in workers:
                w.cancel()
            total_duration = time.perf_counter() - start_time

        self._print_results(total_duration)

    def _print_results(self, total_duration: float):
        if not self.latencies:
            print("❌ No requests were completed.")
            return

        sorted_lat = sorted(self.latencies)
        n = len(sorted_lat)
        rps = n / total_duration if total_duration > 0 else 0

        p50 = sorted_lat[int(n * 0.50)]
        p90 = sorted_lat[int(n * 0.90)]
        p95 = sorted_lat[int(n * 0.95)]
        p99 = sorted_lat[int(n * 0.99)]
        avg = sum(sorted_lat) / n

        print("=" * 60)
        print("          LOAD TEST PERFORMANCE BENCHMARK REPORT          ")
        print("=" * 60)
        print(f" Total Duration:      {total_duration:.2f} s")
        print(f" Total Requests:      {n}")
        print(f" Throughput (RPS):    {rps:.2f} req/s")
        print(f" Success Rate:        {((n - self.errors) / n) * 100:.2f}%")
        print(f" Total Errors:        {self.errors}")
        print("-" * 60)
        print(" Latency Percentiles (ms):")
        print(f"   Min:               {sorted_lat[0]:.2f} ms")
        print(f"   Median (p50):      {p50:.2f} ms")
        print(f"   p90:               {p90:.2f} ms")
        print(f"   p95:               {p95:.2f} ms")
        print(f"   p99:               {p99:.2f} ms")
        print(f"   Max:               {sorted_lat[-1]:.2f} ms")
        print(f"   Average:           {avg:.2f} ms")
        print("-" * 60)
        print(" HTTP Status Code Distribution:")
        for code, count in sorted(self.status_codes.items()):
            label = "ERROR/TIMEOUT" if code == 0 else f"HTTP {code}"
            pct = (count / n) * 100
            print(f"   {label:15}: {count:5} ({pct:.1f}%)")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="AI Personalization Engine Load Tester")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the engine")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent workers")
    parser.add_argument("--requests", type=int, default=300, help="Total requests to dispatch")
    parser.add_argument(
        "--scenario",
        choices=["mixed", "recommendations", "events", "offers"],
        default="mixed",
        help="Test scenario",
    )
    args = parser.parse_args()

    runner = LoadTestRunner(
        base_url=args.url,
        concurrency=args.concurrency,
        total_requests=args.requests,
        scenario=args.scenario,
    )
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
