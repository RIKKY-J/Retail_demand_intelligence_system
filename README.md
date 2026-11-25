# AI-Powered Retail Inventory Management & Demand Prediction System

Full-stack retail inventory management and demand forecasting application using M5-formatted sales data, direct multi-horizon LightGBM (`objective="tweedie"`), forecast-aware safety stock and replenishment optimization, a FastAPI backend, and a Next.js dashboard.

> **Note:** Because the M5 Walmart Forecasting dataset contains sales and price history without physical stock levels, supplier lead times, or purchase orders, inventory state and replenishment policies are maintained as a clearly labeled simulated inventory layer in SQLite.

## Project Structure

- `configs/` — Inventory policy thresholds and forecasting configuration (`inventory_config.yaml`)
- `data/` — Raw M5 CSVs (`raw/`), cleaned Parquet files (`processed/`), and mock forecasts (`mock/`)
- `models/` — Trained LightGBM `.txt` boosters and `model_metrics.json`
- `notebooks/` — Exploration, preprocessing, feature engineering, and training notebooks
- `backend/` — FastAPI application, ML/inventory domain modules, SQLite persistence, and pytest suite
- `frontend/` — Next.js App Router + TypeScript + Tailwind CSS dashboard

## Phase 1 Quickstart (Mock Data & SQLite Seed)

```bash
pip install -r requirements.txt
python -m backend.src.seed_mock_data
```
