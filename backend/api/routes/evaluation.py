"""Model evaluation and 28-day policy backtest endpoint (`GET /api/evaluation`)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.schemas import EvaluationResponse
from backend.src.analytics import load_model_metrics

router = APIRouter(prefix="/api", tags=["evaluation"])


@router.get("/evaluation", response_model=EvaluationResponse)
def get_evaluation() -> EvaluationResponse:
    """Return Baseline vs. LightGBM error metrics and 28-day policy backtest KPIs."""
    metrics_doc = load_model_metrics()
    if not metrics_doc or "policy_backtest_28d" not in metrics_doc:
        raise HTTPException(
            status_code=404,
            detail="Model evaluation metrics not found. Run Phase 2 training/backtest first.",
        )

    horizon_rows = [
        metrics_doc["horizon_metrics"][k]
        for k in sorted(
            metrics_doc["horizon_metrics"].keys(),
            key=lambda x: metrics_doc["horizon_metrics"][x]["horizon_days"],
        )
    ]

    category_rows = [
        {
            "cat_id": cat_id,
            "lightgbm": vals["lightgbm"],
            "seasonal_naive": vals["seasonal_naive"],
        }
        for cat_id, vals in sorted(metrics_doc["category_metrics_h28"].items())
    ]

    return EvaluationResponse(
        generated_at=metrics_doc["generated_at"],
        split=metrics_doc["split"],
        horizon_metrics=horizon_rows,
        category_metrics_h28=category_rows,
        policy_backtest_28d=metrics_doc["policy_backtest_28d"],
    )
