"""API integration tests using FastAPI TestClient against SQLite and Parquet."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_overview_endpoint() -> None:
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["kpis"]["monitored_skus"] > 0
    assert data["kpis"]["is_simulated_inventory"] is True
    assert len(data["sales_trend"]) > 0
    assert len(data["status_breakdown"]) == 4


def test_inventory_get_and_patch_persistence() -> None:
    overview_skus = client.get("/api/overview").json()["kpis"]["monitored_skus"]
    res = client.get("/api/inventory")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == overview_skus
    assert len(items) > 0

    target = items[0]
    store_id = target["store_id"]
    item_id = target["item_id"]
    orig_on_hand = target["on_hand"]
    orig_lead = target["lead_time_days"]

    try:
        patch_res = client.patch(
            f"/api/inventory/{store_id}/{item_id}",
            json={"on_hand": orig_on_hand + 10, "lead_time_days": orig_lead + 1, "notes": "API test patch"},
        )
        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["on_hand"] == orig_on_hand + 10
        assert updated["lead_time_days"] == orig_lead + 1
    finally:
        # Restore original values so seeded state remains clean
        client.patch(
            f"/api/inventory/{store_id}/{item_id}",
            json={"on_hand": orig_on_hand, "lead_time_days": orig_lead, "notes": "API test restore"},
        )


def test_forecasts_analytics_alerts_evaluation_endpoints() -> None:
    fc = client.get("/api/forecasts?store_id=CA_1&horizon=14")
    assert fc.status_code == 200
    fc_data = fc.json()
    assert len(fc_data["forecasts"]) == 14
    assert len(fc_data["holdout_comparison"]) == 28

    an = client.get("/api/analytics?granularity=weekly")
    assert an.status_code == 200
    assert len(an.json()["top_products"]) == 10

    al = client.get("/api/alerts?alert_type=all")
    assert al.status_code == 200
    assert al.json()["counts"]["all"] > 0

    ev = client.get("/api/evaluation")
    assert ev.status_code == 200
    ev_data = ev.json()
    assert len(ev_data["horizon_metrics"]) == 3
    bt = ev_data["policy_backtest_28d"]
    overview_skus = client.get("/api/overview").json()["kpis"]["monitored_skus"]
    assert bt["lightgbm"]["skus_evaluated"] == overview_skus
    assert bt["lightgbm"]["skus_evaluated"] > 0
    assert "total_policy_cost" in bt["lightgbm"]
    assert "holding_cost" in bt["lightgbm"]
    assert "stockout_cost" in bt["lightgbm"]
    assert "total_policy_cost_savings" in bt["comparison"]
