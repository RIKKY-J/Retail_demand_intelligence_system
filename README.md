# Retail Demand Intelligence & Inventory Management System

A clean, full-stack 7th-semester ML project using real Walmart M5 sales data (`CA_1`, 60 balanced SKUs across `FOODS`, `HOBBIES`, and `HOUSEHOLD`), comparing **4 standard ML forecasting models**, and converting predictions into textbook **Safety Stock & Reorder Point** recommendations.

> **Note:** Since the Kaggle M5 dataset does not include physical stock-on-hand or supplier lead times, inventory levels are simulated in a single-table SQLite database (`data/inventory.db`).

---

## Project Structure

- `backend/preprocess.py` — Filters `data/raw/` M5 CSVs to 60 SKUs × 365 days, drops `NaN` `sell_price` periods, builds 7-day-shifted features, saves `data/m5_subset.csv`.
- `backend/train.py` — Trains & evaluates **7-Day Moving Average**, **Linear Regression**, **Random Forest**, and **LightGBM** on a 28-day chronological test split (`MAE`, `RMSE`, `WMAPE`), saves `models/model.pkl`, `models/metrics.json`, `data/forecasts.csv`, and seeds `data/inventory.db`.
- `backend/inventory.py` — Implements Safety Stock (`1.65 × RMSE × √L`), Reorder Point, Order Quantity, and SQLite helpers.
- `backend/api.py` — Slim FastAPI server exposing `/api/overview`, `/api/forecast`, and `/api/inventory`.
- `frontend/` — 3-page Next.js + Tailwind CSS + Recharts dashboard (`/`, `/forecast`, `/inventory`).
- `notebooks/eda_and_training.ipynb` — Exploratory Data Analysis & 4-model comparison figures for the project report.

---

## Quickstart (4 Steps)

### 1. Preprocess Real M5 Data (`data/raw/` → `data/m5_subset.csv`)

```bash
pip install -r requirements.txt
python -m backend.preprocess
```

### 2. Train & Evaluate 4 Models + Seed SQLite

```bash
python -m backend.train
```

### 3. Start FastAPI Backend (`http://localhost:8000`)

```bash
uvicorn backend.api:app --port 8000
```

### 4. Start Next.js Frontend (`http://localhost:3000`)

```bash
cd frontend
npm install
npm run dev
```
