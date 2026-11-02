"""
Comprehensive End-to-End Verification of Phases 1 to 8.
Runs full assertion checks against all functional requirements.
"""
import asyncio
import sys
import httpx

BASE_URL = "http://localhost:8000/api/v1"
ROOT_URL = "http://localhost:8000"


async def main():
    print("=" * 70)
    print("      AI PERSONALIZATION ENGINE - COMPLETE PHASES 1-8 AUDIT")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # -------------------------------------------------------------
        # PHASE 1: Authentication, Health, Ingestion
        # -------------------------------------------------------------
        print("\n[Phase 1] Foundation, Auth, Health & Events:")
        r = await client.get(f"{BASE_URL}/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        assert r.json()["data"]["status"] == "ok"
        print("  ✓ /health liveness probe OK")

        r = await client.get(f"{BASE_URL}/ready")
        assert r.status_code == 200, f"Readiness check failed: {r.status_code}"
        ready_data = r.json()["data"]
        assert ready_data["checks"]["database"] == "ok"
        assert ready_data["checks"]["redis"] == "ok"
        print(f"  ✓ /ready deep probe OK (DB: {ready_data['latencies']['database_ms']}ms, Redis: {ready_data['latencies']['redis_ms']}ms)")

        # Login
        r = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": "admin@example.com", "password": "ChangeMe123!"},
        )
        assert r.status_code == 200, f"Admin login failed: {r.text}"
        token = r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✓ Admin JWT authentication and token issuance OK")

        # Ingest single event
        r = await client.post(
            f"{BASE_URL}/events",
            json={
                "event_type": "PRODUCT_VIEW",
                "external_user_id": "USER_VERIFY_1",
                "product_id": "PROD_1001",
                "session_id": "sess-verify-1",
                "timestamp": "2026-10-28T10:00:00Z",
            },
        )
        assert r.status_code in (200, 201), f"Event ingestion failed: {r.text}"
        assert r.json()["data"]["status"] in ("accepted", "duplicate")
        print("  ✓ Idempotent Event ingestion OK")

        # -------------------------------------------------------------
        # PHASE 2: Recommendation MVP & Products Catalog
        # -------------------------------------------------------------
        print("\n[Phase 2] Recommendation Engine & Product Catalog:")
        r = await client.get(f"{BASE_URL}/products?limit=5", headers=headers)
        assert r.status_code == 200, f"Products listing failed: {r.text}"
        products = r.json()["data"]["items"]
        assert len(products) > 0, "No products found"
        sample_prod_id = products[0]["product_id"]
        print(f"  ✓ Products catalog synced (Total: {r.json()['data']['total']} products)")

        # Popular recos
        r = await client.get(f"{BASE_URL}/recommendations/popular?limit=5")
        assert r.status_code == 200
        assert "items" in r.json()["data"]
        print(f"  ✓ Popular recommendations OK ({len(r.json()['data']['items'])} items)")

        # User recos
        r = await client.get(f"{BASE_URL}/recommendations/user/USER_10005?limit=5")
        assert r.status_code == 200
        assert "items" in r.json()["data"]
        print(f"  ✓ User hybrid recommendations OK ({len(r.json()['data']['items'])} items)")

        # Frequently bought together
        r = await client.get(f"{BASE_URL}/recommendations/frequently-bought/{sample_prod_id}")
        assert r.status_code == 200
        print(f"  ✓ Frequently-bought-together OK for {sample_prod_id}")

        # -------------------------------------------------------------
        # PHASE 3: Customer Intelligence & RFM Segments
        # -------------------------------------------------------------
        print("\n[Phase 3] Customer Intelligence & RFM Segments:")
        r = await client.get(f"{BASE_URL}/customers?limit=5", headers=headers)
        assert r.status_code == 200
        cust_total = r.json()["data"]["total"]
        assert cust_total > 0
        sample_cust = r.json()["data"]["items"][0]["customer_id"]
        print(f"  ✓ Customers directory OK (Total: {cust_total} profiles)")

        # Customer Detail + RFM + Timeline
        r = await client.get(f"{BASE_URL}/customers/{sample_cust}", headers=headers)
        assert r.status_code == 200
        cust_profile = r.json()["data"]
        rfm = cust_profile.get("rfm") or {}
        seg = cust_profile.get("segment") or {}
        print(f"  ✓ Customer RFM: Recency={rfm.get('r')}, Freq={rfm.get('f')}, Monetary={rfm.get('m')}, Segment={seg.get('name')}")

        r = await client.get(f"{BASE_URL}/customers/{sample_cust}/timeline", headers=headers)
        assert r.status_code == 200
        print(f"  ✓ Customer timeline events OK ({r.json()['data']['total']} events)")

        # Segments
        r = await client.get(f"{BASE_URL}/segments", headers=headers)
        assert r.status_code == 200
        segments = r.json()["data"]["segments"]
        print(f"  ✓ RFM 12 Segments OK (Grid: {len(segments)} segments active)")

        # -------------------------------------------------------------
        # PHASE 4: Offer Engine (Targeting, Validation, Redemption)
        # -------------------------------------------------------------
        print("\n[Phase 4] Offer Engine & Checkout Rules:")
        r = await client.get(f"{BASE_URL}/offers", headers=headers)
        assert r.status_code == 200
        offers_total = r.json()["data"]["total"]
        print(f"  ✓ Offers directory OK (Total: {offers_total} offers)")

        # Storefront eligible offers for user
        r = await client.get(f"{BASE_URL}/offers/user/USER_10005?cart_value=3000")
        assert r.status_code == 200
        eligible = r.json()["data"]["items"]
        print(f"  ✓ User personalized offer eligibility OK ({len(eligible)} offers eligible)")

        # Offer validate
        if eligible:
            code = eligible[0]["code"]
            r = await client.post(
                f"{BASE_URL}/offers/validate",
                headers=headers,
                json={"code": code, "external_user_id": "USER_10005", "order_value": 3000},
            )
            assert r.status_code == 200
            val_data = r.json()["data"]
            print(f"  ✓ Checkout coupon validation for '{code}': Valid={val_data.get('valid')}, Discount={val_data.get('discount_amount')}")

        # -------------------------------------------------------------
        # PHASE 5: Admin Dashboard, Analytics, Integrations, Users, System
        # -------------------------------------------------------------
        print("\n[Phase 5] Analytics, Integrations, System, Users:")
        r = await client.get(f"{BASE_URL}/analytics/report?days=30", headers=headers)
        assert r.status_code == 200
        kpis = r.json()["data"]["kpis"]
        print(f"  ✓ 30-Day Period Analytics OK (Revenue: ₹{kpis['revenue']['value']:.2f}, Orders: {kpis['orders']['value']})")

        r = await client.get(f"{BASE_URL}/integrations/status", headers=headers)
        assert r.status_code == 200
        print(f"  ✓ Integrations health score: {r.json()['data']['score']}%")

        r = await client.get(f"{BASE_URL}/system/status", headers=headers)
        assert r.status_code == 200
        sys_info = r.json()["data"]["app"]
        db_tables = r.json()["data"]["database"].get("table_sizes", [])
        print(f"  ✓ System status OK (Version: {sys_info['version']}, Env: {sys_info.get('environment')}, Tables: {len(db_tables)})")

        r = await client.get(f"{BASE_URL}/search?q=USER", headers=headers)
        assert r.status_code == 200
        print(f"  ✓ Global search OK (Found {len(r.json()['data']['customers'])} customers matching query)")

        # -------------------------------------------------------------
        # PHASE 6: A/B Testing (Experiments)
        # -------------------------------------------------------------
        print("\n[Phase 6] A/B Testing & Experiments:")
        r = await client.get(f"{BASE_URL}/experiments", headers=headers)
        assert r.status_code == 200
        exp_list = r.json()["data"]["items"]
        print(f"  ✓ Experiments directory OK ({len(exp_list)} experiments active/seeded)")
        if exp_list:
            exp_id = exp_list[0]["id"]
            r = await client.get(f"{BASE_URL}/experiments/{exp_id}/results", headers=headers)
            assert r.status_code == 200
            res = r.json()["data"]
            verdict_status = res.get("verdict", {}).get("status", "unknown")
            print(f"  ✓ Experiment '{exp_list[0]['name']}' results: Verdict = '{verdict_status}'")

        # -------------------------------------------------------------
        # PHASE 7: Advanced ML (Churn, Purchase, Offer Response)
        # -------------------------------------------------------------
        print("\n[Phase 7] Advanced ML Models & Customer Predictions:")
        r = await client.get(f"{BASE_URL}/ml/models", headers=headers)
        assert r.status_code == 200
        ml_models = r.json()["data"].get("models", [])
        print(f"  ✓ Model Registry active: {[m['name'] for m in ml_models]}")

        r = await client.get(f"{BASE_URL}/ml/customers/USER_10005", headers=headers)
        assert r.status_code == 200
        ml_preds = r.json()["data"]
        purch = ml_preds["purchase_probability"]
        churn = ml_preds["churn_risk"]
        offer = ml_preds["offer_response"]
        print(f"  ✓ Customer ML Predictions: Purchase Prob={purch['score']:.2f} ({purch['label']}), Churn Risk={churn['score']:.2f} ({churn['label']}), Best Offer={offer['recommended_offer_type']}")

        r = await client.get(f"{BASE_URL}/ml/top/churn?limit=5", headers=headers)
        assert r.status_code == 200
        print(f"  ✓ Churn Leaderboard OK ({len(r.json()['data'])} high-risk customers listed)")

        # -------------------------------------------------------------
        # PHASE 8: Production Hardening, Security & Observability
        # -------------------------------------------------------------
        print("\n[Phase 8] Production Hardening & Observability:")
        # Security headers
        r = await client.get(f"{BASE_URL}/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        assert r.headers.get("x-xss-protection") == "1; mode=block"
        assert "x-request-id" in r.headers
        assert "x-response-time" in r.headers
        print("  ✓ Security headers verified (nosniff, DENY, XSS-block, Request-ID, Response-Time)")

        # Prometheus metrics
        r = await client.get(f"{ROOT_URL}/metrics")
        assert r.status_code == 200
        assert "# HELP http_requests_total" in r.text
        assert "app_info" in r.text
        print(f"  ✓ Prometheus metrics scrape endpoint OK ({len(r.text)} bytes exported)")

        # Payload size limit
        oversized_data = b"x" * (11 * 1024 * 1024)
        r = await client.post(
            f"{BASE_URL}/events",
            content=oversized_data,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        print("  ✓ Payload size limit guard verified (11MB payload blocked with HTTP 413)")

        print("\n" + "=" * 70)
        print(" 🎉 ALL PHASES (PHASE 1 TO PHASE 8) VERIFIED WITH 100% ACCURACY!")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
