# AI-Powered Retail Inventory Management & Demand Prediction System

Full-stack retail inventory management and demand forecasting application using M5-formatted sales data, direct multi-horizon LightGBM (`objective="tweedie"`), forecast-aware safety stock and replenishment optimization, a FastAPI REST backend, and a Next.js dashboard.

> **Simulated Inventory Disclaimer:** Because the Kaggle M5 Walmart Forecasting dataset contains historical sales and selling prices without physical stock-on-hand, supplier lead times, or purchase orders, inventory levels and replenishment policies are maintained as a clearly labeled simulated inventory layer in SQLite.

---

## Project Structure

- `configs/` — Central policy thresholds, financial cost rates, and forecasting defaults (`inventory_config.yaml`)
- `data/` — Raw M5 CSVs (`raw/`), processed Parquet files (`processed/`), Day-1 mock CSV (`mock/`), and SQLite DB (`retail_inventory.db`)
- `models/` — Native LightGBM `.txt` boosters (`lgbm_h7.txt`, `lgbm_h14.txt`, `lgbm_h28.txt`) and `model_metrics.json`
- `backend/` — FastAPI app (`api/`), ML & inventory domain logic (`src/`), and pytest suite (`tests/`)
- `frontend/` — Next.js App Router + TypeScript + Tailwind CSS + Recharts dashboard

---

## Setup & Installation

### 1. Python Backend Environment

```bash
pip install -r requirements.txt
```

### 2. Next.js Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Data & Model Pipeline

### Option A: Seed Synthetic M5-Formatted Sample Data (Quickstart)

Generates `data/processed/sample_sales.parquet` (50 SKUs × 1 store `CA_1` × 400 days) and seeds SQLite:

```bash
python -m backend.src.seed_mock_data
```

### Option B: Ingest Real Kaggle M5 Dataset (`kagglehub`)

Requires Kaggle credentials (`~/.kaggle/kaggle.json` or `KAGGLE_USERNAME` / `KAGGLE_KEY`) and competition rule acceptance for `m5-forecasting-accuracy`. Downloads raw CSVs into `data/raw/` (if missing), filters to `CA_1` across a balanced 200-SKU subset (`FOODS`, `HOBBIES`, `HOUSEHOLD`) over the last 2.5 years (913 days), drops `sell_price` NaNs prior to feature engineering, saves `data/processed/m5_sales.parquet`, retrains `lgbm_h7/14/28.txt`, runs the 28-day financial policy backtest, and repopulates SQLite:

```bash
python -m backend.src.run_real_m5_pipeline
```

---

## Running the Application

### 1. Start FastAPI Backend (`http://127.0.0.1:8000`)

```bash
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Interactive OpenAPI/Swagger documentation is available at `http://127.0.0.1:8000/docs`.

### 2. Start Next.js Frontend (`http://localhost:3000`)

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000` in your browser to access all 6 routes: `/`, `/inventory`, `/forecasting`, `/analytics`, `/alerts`, and `/evaluation`.

---

## Running Tests & Build Verification

### Backend Unit & API Tests

```bash
pytest backend/tests -v
```

### Frontend TypeScript & Production Build Check

```bash
cd frontend
npx tsc --noEmit
npm run build
```
