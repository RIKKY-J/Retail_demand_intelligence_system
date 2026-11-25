# AI-Powered Retail Inventory Management & Demand Prediction System

## 1. Project Overview

**Project title:** AI-Powered Retail Inventory Management and Demand Prediction System

### Objective

Build a full-stack retail inventory management web application that uses historical sales data to forecast product demand, monitor simulated stock levels, recommend replenishment quantities, and provide sales and inventory analytics.

The system will use the **M5 Walmart Forecasting dataset** for historical demand. Since the M5 dataset does not contain actual on-hand inventory, purchase orders, or supplier lead times, the project will add a clearly documented **simulated inventory layer**.

### Core capabilities

1. Forecast product demand for the next 7, 14, and 28 days.

2. Track inventory levels for selected products and stores.

3. Calculate forecast-aware safety stock and reorder points.

4. Recommend replenishment quantities.

5. Identify low-stock, potential stockout, and excess-stock situations.

6. Analyze sales trends, seasonality, and product/store performance.

7. Evaluate both forecasting accuracy and simulated business impact (stockouts avoided vs. inventory held).

## 2. Project Scope

### Included in the initial version

| Module | Main capabilities | Priority | 
| ----- | ----- | ----- | 
| Overview dashboard | Sales KPIs, inventory KPIs, alerts | High | 
| Inventory management | Stock records, stock status, reorder levels, live stock mutations | High | 
| Demand forecasting | 7-, 14-, and 28-day direct predictions | High | 
| Inventory optimization | Forecast-aware safety stock, reorder point, reorder quantity | High | 
| Sales analytics | Product, store, and seasonal trends | Medium | 
| Model evaluation | Actual vs. predicted demand, error metrics, and 28-day policy backtest | High | 

### Out of scope for the initial version

* Live integration with Walmart or supplier systems.

* Real purchase-order placement.

* Native mobile application (the Next.js web app will be responsive).

* Complex microservices or Kubernetes orchestration.

* LLM chatbot or generative-AI assistant.

* Deep-learning models such as LSTM unless added later as an optional experiment.

Keep the first implementation focused on a clean, reliable forecasting-to-replenishment workflow powered by a decoupled Python ML backend and a Next.js frontend.

## 3. Dataset: M5 Walmart Forecasting

**Dataset:** [M5 Forecasting -- Accuracy (Kaggle)](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data)

The M5 dataset contains daily unit sales for Walmart products across stores, along with calendar events and selling prices.

### Main files

| File | Purpose | 
| ----- | ----- | 
| `sales_train_validation.csv` | Historical daily sales by product and store | 
| `calendar.csv` | Dates, weekdays, events, and SNAP information | 
| `sell_prices.csv` | Product prices by store and week | 
| `sales_train_evaluation.csv` | Extended sales history for evaluation | 

### Dataset fields to understand

* `id`: product-store identifier.

* `item_id`: product identifier.

* `dept_id`: department.

* `cat_id`: product category.

* `store_id`: store identifier.

* `state_id`: state identifier.

* `d_1`, `d_2`, etc.: daily unit sales columns.

* Calendar fields: date, weekday, event and SNAP indicators.

* Price fields: store, item, week and selling price.

### Recommended initial data subset

Do not start by training on all 30,490 product-store series.

Start with:

* One store (e.g., `CA_1`).

* One product category or department.

* Approximately 100–300 product-store time series, depending on availability.

* A chronological historical period (e.g., the most recent 2.5–3 years) suitable for training and validation.

After the pipeline works, increase the number of stores and products.

### Important dataset limitation

M5 contains sales history, not actual stock-on-hand, supplier lead time, backorders, or purchase orders.

Therefore:

* Historical sales and prices are dataset-derived.

* Opening inventory, supplier lead time, on-order quantity, and backorders must be simulated or entered as application data.

* Clearly label simulated values in the UI and project report.

* Do not claim that the system has learned actual stockout events from M5.

## 4. Technology Stack

| Layer | Recommended technology | Use | 
| ----- | ----- | ----- | 
| ML & Backend Language | Python 3.10+ | Data processing, ML training, optimization, and REST API | 
| Data processing | Pandas / Polars, NumPy | Cleaning and feature engineering | 
| Historical data storage | Parquet (`.parquet`) | Fast local storage for processed M5 sales | 
| Forecasting baseline | Seasonal naive / moving average | Baseline comparison | 
| Main ML model | LightGBM (`objective="tweedie"`) | Demand forecasting for count data | 
| Optional comparison | XGBoost or LightGBM Quantile | Compare a second model or upper-bound quantiles | 
| Application database | SQLite | Store inventory records, transactions, and forecast results | 
| Backend API | FastAPI + Pydantic | REST API serving forecasts, inventory math, and analytics to Next.js | 
| Frontend Framework | Next.js (App Router, TypeScript) | Web dashboard and interactive user interface | 
| Styling & UI Components | Tailwind CSS + shadcn/ui | Clean, responsive enterprise dashboard UI | 
| Visualization | Recharts (or Tremor / Plotly.js) | Interactive forecast, inventory, and analytics charts | 
| Model persistence | LightGBM native format (`save_model` / `Booster`) | Cross-environment safe saving/loading (Colab to local laptop) | 
| Development | VS Code / Antigravity, Jupyter, Google Colab | Coding and experiments | 

### Why Next.js + FastAPI?

Decoupling the frontend in **Next.js (TypeScript)** from a **FastAPI** backend keeps all Python ML/inventory logic clean and testable while delivering a responsive, production-grade web dashboard. Using LightGBM's native `model.booster_.save_model("lgbm_h7.txt")` instead of `Joblib` pickles prevents version-mismatch crashes when training on Google Colab and serving locally via FastAPI.

Start with LightGBM (`tweedie`) as the primary model. Add XGBoost or Quantile Regression only after the core end-to-end API and Next.js pipeline is working.

## 5. System Architecture

```
                 M5 DATASET
     (Sales, Calendar, Selling Prices)
                    |
                    v
             DATA INGESTION
                    |
                    v
       DATA CLEANING, PRICE FILTERING,
         & PARQUET STORAGE (.parquet)
                    |
                    v
        HORIZON-ALIGNED FEATURE ENGINEERING
       (Lags, Rolling Means, Calendar,
             Price, Product IDs)
                    |
                    v
           DIRECT DEMAND FORECASTING
      (Baseline + Direct LightGBM h=7,14,28)
                    |
                    v
          FORECASTED PRODUCT DEMAND
        (Stored in SQLite forecast_results)
                    |
                    v
       INVENTORY MANAGEMENT & BACKTEST ENGINE
    (On-hand, On-order, Lead Time, Forecast-Aware
      Safety Stock, Reorder Point, Quantity)
                    |
                    v
            FASTAPI REST BACKEND
   (/api/overview, /api/inventory, /api/forecasts,
        /api/analytics, /api/evaluation)
                    |
                    v
         NEXT.JS WEB APPLICATION (UI)
   (Overview, Inventory, Forecasts, Analytics,
       Alerts, Model & Backtest Metrics)
```

### Main system components

1. **Data pipeline:** Loads, filters unstocked periods, transforms M5 data, and writes processed `.parquet` files.

2. **Forecasting component:** Trains direct horizon-specific LightGBM models and runs demand predictions.

3. **Inventory & backtest component:** Maintains simulated inventory, calculates forecast-aware replenishment recommendations, and runs a 28-day policy backtest.

4. **Database:** SQLite stores application-managed inventory records, transactions, and forecast outputs (while historical sales remain in Parquet for speed).

5. **Backend API (FastAPI):** Exposes typed JSON endpoints (`http://localhost:8000/api/...`) with OpenAPI/Swagger documentation (`/docs`) for the frontend.

6. **Frontend Web App (Next.js):** Consumes the FastAPI endpoints to render interactive charts, inventory forms, stock alerts, and backtest evaluations (`http://localhost:3000`).

## 6. Data Processing and Feature Engineering

The original M5 sales file is in wide format, with one column per day. Convert it to long format before analysis and model training.

### Processing steps

1. Load the sales, calendar, and price CSV files.

2. Select the required stores, products, and date range.

3. Convert daily sales columns (`d_1`, `d_2`, etc.) into rows.

4. Map each day identifier to its calendar date and join `calendar.csv`.

5. Join `sell_prices.csv` using `store_id`, `item_id`, and `wm_yr_wk`.

6. **Critical M5 Filtering Rule:** Drop all rows where `sell_price` is `NaN` **before** calculating any lag or rolling features. In M5, a missing `sell_price` indicates the product was not yet launched or stocked in that store during that week—leaving these rows in as `sales = 0` introduces fake zero-demand periods that bias rolling averages and downward-skew LightGBM.

7. Downcast numeric types (`float64` to `float32`, integer IDs to categoricals) to keep memory usage low on laptop hardware.

8. Save the processed dataset as a `.parquet` file.

### Suggested feature set (Horizon-Aligned)

To support direct multi-horizon forecasting without leakage, shift lag and rolling features by at least the target horizon $h \in \{7, 14, 28\}$:

| Feature | Description | 
| ----- | ----- | 
| `item_id`, `store_id` | Product and store identifiers (categorical) | 
| `date` | Sales date | 
| `sales` | Target variable: units sold | 
| `sell_price` | Selling price (plus optional price change vs. 4-week rolling mean) | 
| `day_of_week`, `month`, `week_of_year` | Calendar seasonality indicators | 
| `event_name_1` | Calendar holiday/event indicator | 
| `snap_CA`, `snap_TX`, `snap_WI` | SNAP benefit indicators where applicable | 
| `lag_h`, `lag_h_plus_7`, `lag_h_plus_21` | Sales shifted by $h$, $h+7$, and $h+21$ days (e.g., for $h=7$: `lag_7`, `lag_14`, `lag_28`) | 
| `rolling_mean_7_shift_h` | 7-day rolling mean of sales, shifted by $h$ days | 
| `rolling_mean_28_shift_h` | 28-day rolling mean of sales, shifted by $h$ days | 
| `rolling_std_28_shift_h` | 28-day rolling standard deviation of sales, shifted by $h$ days | 

### Preventing data leakage

* Always shift sales by at least the forecast horizon $h$ before computing lag and rolling features.

* A prediction for date $t$ made from cutoff date $t - h$ must use only information available on or before $t - h$.

* Split training, validation, and 28-day test holdout sets strictly chronologically—never randomly.

* Fit any encoders or scalers on training data only.

## 7. Demand Forecasting Module

### Models

**Model 1: Baseline (Seasonal Naive)**

Use a weekly seasonal naive forecast where the predicted demand for a future day equals the actual sales from the same weekday in the most recent available week (or a 4-week same-weekday moving average).

**Model 2: Direct Multi-Horizon LightGBM (Tweedie Objective)**

Instead of recursive daily forecasting (which compounds errors across 28 steps and slows down live inference), train **3 direct LightGBM models**—one for each horizon ($h = 7$, $h = 14$, and $h = 28$ days). On 100–300 SKUs, training all 3 models takes under a minute and eliminates recursive drift.

* **Loss Function:** Use `objective="tweedie"` (with `tweedie_variance_power` tuned around `1.1` to `1.3`) or `objective="poisson"`. Daily retail sales in M5 are zero-inflated, right-skewed count data; standard MSE (`regression`) assumes Gaussian errors, overreacts to promo spikes, and can output negative predictions.

* **Optional Upgrade (Quantile Upper Bound):** Train a companion LightGBM model with `objective="quantile"` and `alpha=0.95` to directly predict the 95th-percentile upper demand bound for dynamic safety stock.

### Forecast horizons

The application supports:

* 7-day forecast (`lgbm_h7.txt`)

* 14-day forecast (`lgbm_h14.txt`)

* 28-day forecast (`lgbm_h28.txt`)

### Evaluation metrics

| Metric | Meaning | 
| ----- | ----- | 
| **MAE** | Average absolute difference between actual and predicted sales | 
| **RMSE** | Penalizes larger prediction errors (also used for forecast-error safety stock) | 
| **WMAPE** | $\frac{\sum \lvert y_i - \hat{y}_i \rvert}{\sum y_i}$; handles zero-sales days without division-by-zero | 
| **Forecast Bias** | $\frac{\sum (\hat{y}_i - y_i)}{\sum y_i}$; detects systematic over- or under-forecasting | 

Use a chronological 28-day holdout period (and rolling-origin validation if time permits). Report metrics separately by horizon (7, 14, 28 days) and product category.

### Forecast outputs

For each selected product and store, store and return via API:

* `forecast_date`

* `prediction` (clipped at $\ge 0$)

* `prediction_p95` (optional, if quantile model is enabled)

* `store_id` and `item_id`

* `horizon`

* `model_version` / training timestamp

Label point forecasts clearly in the Next.js UI as expected demand estimates rather than guaranteed outcomes.

## 8. Inventory Management Module

Because M5 does not include real inventory records, maintain a simulated inventory table in SQLite.

### Suggested inventory fields

| Field | Description | 
| ----- | ----- | 
| `item_id` | Product identifier | 
| `store_id` | Store identifier | 
| `on_hand` | Current simulated stock | 
| `on_order` | Units already ordered | 
| `backorders` | Unfulfilled demand | 
| `lead_time_days` | Supplier lead time ($L$) | 
| `review_period_days` | Time between stock reviews ($R$) | 
| `unit_cost` | Optional simulated unit cost | 
| `updated_at` | Last inventory update | 

### Inventory position

Calculate inventory position ($IP$) as:

$$
IP = \text{On-hand} + \text{On-order} - \text{Backorders}
$$

Always use inventory position—not on-hand stock alone—when deciding whether to reorder.

### Forecast-Aware Safety Stock

Avoid using raw historical demand standard deviation, which over-orders safety stock for predictable seasonality that the ML model already captures. Instead, base safety stock on the **validation forecast error** ($\text{RMSE}_{\text{val}}$) of the LightGBM model:

$$
SS = Z \times \text{RMSE}_{\text{val}} \times \sqrt{L}
$$

Where:

* $Z$ is the service-level factor (e.g., $Z = 1.645$ for a $95\%$ cycle service level).

* $\text{RMSE}_{\text{val}}$ is the per-SKU (or department-level) daily validation RMSE of the forecasting model.

* $L$ is the supplier lead time in days.

*Optional Quantile Upgrade:* If using a 95th-percentile LightGBM quantile model ($\hat{y}_{P95}$), compute safety stock directly without Gaussian assumptions:

$$
SS = \sum_{d=1}^{L} \left(\hat{y}_{P95, d} - \hat{y}_{P50, d}\right)
$$

### Reorder point

Sum the ML-forecasted daily demand over the supplier lead time $L$ and add safety stock:

$$
\text{ROP} = \left(\sum_{d=1}^{L} \hat{y}_{d}\right) + SS
$$

### Replenishment quantity

For a periodic review policy with review period $R$:

$$
\text{Target Stock} = \left(\sum_{d=1}^{L + R} \hat{y}_{d}\right) + SS
$$

$$
\text{Recommended Order Quantity} = \max\left(0,\; \lceil \text{Target Stock} - IP \rceil\right)
$$

Apply pack-size or minimum-order-quantity (MOQ) constraints explicitly if configured.

### Inventory status rules

Define all thresholds in a central configuration file (`configs/inventory_config.yaml`):

| Condition | Suggested status | 
| ----- | ----- | 
| $IP \le \text{ROP}$ | Reorder required | 
| $\text{On-hand} < \sum_{d=1}^{L} \hat{y}_{d}$ | Potential stockout | 
| $\text{On-hand} > 1.5 \times \text{Target Stock}$ | Possible overstock | 
| Otherwise | Healthy | 

### 28-Day Policy Backtest Simulator

To prove business value beyond ML error metrics, replay the 28-day chronological holdout period day-by-day under two identical starting stock states—once driven by the **Baseline forecast** and once driven by **LightGBM**:

$$
\text{Closing Stock}_{t} = \max\left(0,\; \text{Opening Stock}_{t} + \text{Receipts}_{t} - \text{Actual Sales}_{t}\right)
$$

$$
\text{Lost Sales}_{t} = \max\left(0,\; \text{Actual Sales}_{t} - \left(\text{Opening Stock}_{t} + \text{Receipts}_{t}\right)\right)
$$

Track and compare across both policies:

* **Total Stockout Units (Lost Sales)**

* **Fill Rate / Service Level (%)**

* **Average Daily On-Hand Inventory** (proxy for holding cost)

State explicitly in the UI and report whether unmet demand is modeled as lost sales (standard for retail shelves) or backorders.

## 9. Sales and Inventory Analytics Module

Provide filters for store, product, category, and date range via API query parameters.

### Recommended analytics

 1. Daily, weekly, and monthly sales trends.

 2. Top-selling products.

 3. Low-demand products.

 4. Store-wise sales comparison.

 5. Category-wise demand comparison.

 6. Price and demand trends.

 7. Weekday and seasonal patterns.

 8. Actual sales versus forecast.

 9. Products below reorder point.

10. Products with potential excess stock.

Render interactive line charts, bar charts, and sortable data tables in Next.js using Recharts (or Tremor) and Tailwind CSS.

## 10. Backend API & Next.js Web Application Pages

### FastAPI Endpoints (`backend/api/`)

* `GET /api/overview` — Returns KPI summary cards, sales trend series, and stock status breakdown.

* `GET /api/inventory` & `PATCH /api/inventory/{store_id}/{item_id}` — Fetches inventory metrics and updates simulated on-hand, on-order, backorders, or lead time in SQLite.

* `GET /api/forecasts` — Returns historical actuals + 7-, 14-, or 28-day predictions for a selected SKU.

* `GET /api/analytics` — Returns aggregated category, weekday, price-vs-demand, and top/bottom product metrics.

* `GET /api/alerts` — Returns filtered lists of reorder-required, potential stockout, and overstock items.

* `GET /api/evaluation` — Returns Baseline vs. LightGBM error metrics and 28-day policy backtest results.

### Next.js App Router Pages (`frontend/src/app/`)

Build the web application in **Next.js (App Router + TypeScript + Tailwind CSS + shadcn/ui)** with a persistent sidebar navigation layout and the following routes:

#### 1. Overview Dashboard (`/`)

* KPI summary cards: Total units sold, monitored SKUs, reorder alerts, potential stockouts, and possible overstock counts.

* Interactive sales trend chart and inventory status distribution chart.

#### 2. Inventory Management (`/inventory`)

* Searchable/filterable product and store selector.

* Live metrics panel: On-hand, on-order, backorders, lead time, review period, safety stock, reorder point, recommended order quantity, and status badge.

* Interactive form allowing users to update simulated stock and lead-time values (persisted in SQLite via `PATCH` request with instant UI revalidation).

#### 3. Demand Forecasting (`/forecasting`)

* Product and store selector + horizon toggle (`7d`, `14d`, `28d`).

* Interactive historical + predicted demand chart and actual-versus-predicted holdout comparison.

* Paginated forecast values table (with explicit disclaimer that values are statistical estimates).

#### 4. Sales Analytics (`/analytics`)

* Product, store, and category performance charts.

* Seasonal, weekday, and price-vs-sales trend visualizations.

#### 5. Stock Alerts (`/alerts`)

* Tabbed/filtered data tables for products requiring reorder, potential stockout, and possible overstock.

* Suggested replenishment quantities, reason badges for each alert, and one-click CSV export.

#### 6. Model Performance & Policy Backtest (`/evaluation`)

* Metric comparison cards and charts (MAE, RMSE, WMAPE, Forecast Bias) comparing Baseline vs. LightGBM across 7-, 14-, and 28-day horizons.

* **28-Day Business Impact Backtest panel:** Side-by-side comparison of **Lost Sales (Stockout Units)**, **Fill Rate (%)**, and **Average On-Hand Inventory** for Baseline vs. LightGBM replenishment policies.

## 11. Database Design

Keep historical M5 sales data in local `.parquet` files (queried via Pandas/DuckDB in FastAPI) so API responses remain fast and lightweight. Use **SQLite** strictly for application-managed state, inventory records, and generated forecasts.

### SQLite tables

**`inventory`** — Stores current simulated stock state:

```
inventory_id, item_id, store_id, on_hand, on_order, backorders,
lead_time_days, review_period_days, unit_cost, updated_at
```

**`inventory_transactions`** — Stores audit log of stock changes (`opening_stock`, `simulated_sale`, `receipt`, `manual_adjustment`):

```
transaction_id, item_id, store_id, transaction_type,
quantity, transaction_date, notes
```

**`forecast_results`** — Stores generated predictions:

```
forecast_id, item_id, store_id, forecast_date,
prediction, prediction_p95, horizon, model_version, created_at
```

**`product_metadata`** — Stores product and store descriptions derived from M5:

```
item_id, store_id, dept_id, cat_id, state_id
```

## 12. Recommended Project Folder Structure

```
retail-demand-intelligence/
│
├── configs/
│   └── inventory_config.yaml        # Service level Z, overstock thresholds, defaults
│
├── data/
│   ├── raw/                         # Unmodified M5 CSVs (gitignored)
│   ├── processed/                   # Cleaned Parquet files (post sell_price filter)
│   └── mock/                        # Day-1 mock forecast_results.csv for parallel dev
│
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_data_preprocessing.ipynb
│   ├── 03_feature_engineering.ipynb
│   └── 04_model_training.ipynb
│
├── models/
│   ├── lgbm_h7.txt                  # Native LightGBM model (7-day horizon)
│   ├── lgbm_h14.txt                 # Native LightGBM model (14-day horizon)
│   ├── lgbm_h28.txt                 # Native LightGBM model (28-day horizon)
│   └── model_metrics.json           # Validation MAE, RMSE, WMAPE, Bias, Backtest KPIs
│
├── backend/
│   ├── api/
│   │   ├── main.py                  # FastAPI app, CORS config, router registration
│   │   ├── schemas.py               # Pydantic request/response models
│   │   └── routes/
│   │       ├── overview.py
│   │       ├── inventory.py
│   │       ├── forecasts.py
│   │       ├── analytics.py
│   │       ├── alerts.py
│   │       └── evaluation.py
│   ├── src/
│   │   ├── data_processing.py
│   │   ├── forecasting.py
│   │   ├── inventory.py
│   │   ├── backtest.py              # 28-day inventory policy simulator
│   │   ├── analytics.py
│   │   └── database.py
│   └── tests/
│       ├── test_forecasting.py      # Includes leakage & horizon-shift assertions
│       └── test_inventory.py        # Includes ROP, SS, and backtest math tests
│
├── frontend/                        # Next.js (App Router + TypeScript + Tailwind)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # Persistent sidebar & header shell
│   │   │   ├── page.tsx             # Overview Dashboard (/)
│   │   │   ├── inventory/page.tsx   # Inventory Management (/inventory)
│   │   │   ├── forecasting/page.tsx # Demand Forecasting (/forecasting)
│   │   │   ├── analytics/page.tsx   # Sales Analytics (/analytics)
│   │   │   ├── alerts/page.tsx      # Stock Alerts (/alerts)
│   │   │   └── evaluation/page.tsx  # Model & Backtest Metrics (/evaluation)
│   │   ├── components/
│   │   │   ├── charts/              # Recharts wrappers (ForecastChart, BacktestBarChart)
│   │   │   ├── inventory/           # StockUpdateForm, StatusBadge, KpiCard
│   │   │   └── ui/                  # shadcn/ui primitives
│   │   └── lib/
│   │       ├── api.ts               # Typed fetch wrapper for FastAPI endpoints
│   │       └── types.ts             # TypeScript interfaces matching Pydantic schemas
│   ├── package.json
│   └── tsconfig.json
│
├── requirements.txt
└── README.md
```

## 13. Suggested Development Implementation

Implement the project in dependency order:

1. **Dataset exploration & API/schema contract:** Download M5, inspect relationships, pick the 100–300 SKU subset, and freeze both the `forecast_results` mock CSV and the FastAPI JSON/TypeScript schemas so frontend and ML development can start immediately in parallel.

2. **Data preprocessing:** Melt wide to long, join calendar and `sell_prices.csv`, **drop `sell_price` NaNs**, downcast dtypes, and save to `.parquet`.

3. **Horizon-aligned feature engineering:** Build shifted lags and rolling stats for $h \in \{7, 14, 28\}$, calendar/SNAP features, and strict chronological train/val/test splits.

4. **Forecasting module:** Implement Seasonal Naive baseline and train direct LightGBM (`objective="tweedie"`) models for 7, 14, and 28 days. Save native `.txt` models and compute validation RMSE, MAE, WMAPE, and bias.

5. **Inventory & backtest engine:** Implement simulated inventory records, inventory position, forecast-error-based safety stock, ROP, replenishment quantity, and the 28-day Baseline-vs-LightGBM policy backtest.

6. **Analytics & FastAPI backend:** Build sales trend, seasonality, price-demand, and top/bottom SKU aggregations over the `.parquet` dataset and expose all 6 route groups via FastAPI with CORS enabled for `localhost:3000`.

7. **Next.js web application:** Scaffold Next.js with TypeScript, Tailwind CSS, and shadcn/ui; build the persistent sidebar layout and connect all 6 routes to the FastAPI backend.

8. **Testing & evaluation:** Run leakage tests, inventory math unit tests, FastAPI endpoint tests, and end-to-end Next.js form persistence checks.

## 14. Work Distribution for a Two-Member Team

**Day-1 Joint Contract (Prevents Blocking):** Both members agree on the `forecast_results` schema (generating a 10-SKU mock forecast file in `data/mock/`) and the FastAPI OpenAPI/TypeScript response interfaces. This allows Member 2 to build the FastAPI routes and Next.js pages immediately without waiting for Member 1 to finish LightGBM training.

| Member 1 -- Data & ML | Member 2 -- Full-Stack App & Inventory | 
| ----- | ----- | 
| M5 dataset exploration & Parquet pipeline | SQLite database & `inventory_config.yaml` | 
| `sell_price` filtering & feature engineering | Inventory data model, SS, ROP & order logic | 
| Seasonal Naive baseline | FastAPI REST endpoints & Pydantic schemas | 
| Direct LightGBM (`h=7, 14, 28`, Tweedie) | Next.js web app (6 routes, Tailwind, Recharts) | 
| Forecast evaluation & validation RMSE export | Stock alerts, interactive stock forms & CORS wiring | 
| 28-day policy backtest integration | Unit testing & end-to-end API/UI testing | 

**Joint responsibilities:** Finalize inventory assumptions, swap mock forecasts for real LightGBM outputs, validate backtest results, and prepare the final report and presentation.

## 15. Testing and Evaluation Criteria

### Forecasting evaluation

* Compare Direct LightGBM (Tweedie) against Seasonal Naive on a chronological 28-day holdout.

* Report MAE, RMSE, WMAPE, and Forecast Bias separately for 7-, 14-, and 28-day horizons and across product groups.

### Business-impact backtest evaluation

* Replay the 28-day holdout period using Baseline vs. LightGBM forecasts to drive replenishment.

* Quantify reduction in **Stockout Units (Lost Sales)**, improvement in **Fill Rate (%)**, and impact on **Average On-Hand Inventory**.

### Inventory & system evaluation

Test scenarios:

1. Stock above reorder point (Healthy).

2. Stock falls below reorder point (Reorder required).

3. Supplier lead time increases (ROP and Safety Stock rise dynamically).

4. Demand forecast spikes (ROP and Recommended Order Quantity rise).

5. Replenishment receipt arrives (On-hand increases, On-order decreases).

6. Outstanding orders prevent duplicate reorders (via Inventory Position).

7. Demand exceeds available stock (Lost sales / backorder recorded accurately).

8. Leakage check verifies lag features never access future dates relative to horizon $h$.

9. Next.js inventory mutations (`PATCH`) persist in SQLite and reflect immediately across Overview, Inventory, and Alerts pages.

## 16. Expected Final Deliverables

 1. Cleaned and `sell_price`-filtered M5 Parquet subset.

 2. Exploratory data analysis notebook.

 3. Horizon-aligned feature engineering pipeline.

 4. Seasonal Naive baseline implementation.

 5. Trained direct LightGBM models (`h=7, 14, 28`) saved in native `.txt` format.

 6. Forecast accuracy metrics and 28-day policy backtest comparison.

 7. Forecast-aware inventory management and replenishment engine.

 8. SQLite database with transaction logging.

 9. FastAPI REST backend with OpenAPI docs.

10. 6-page Next.js web application (TypeScript, Tailwind CSS, Recharts).

11. Automated unit tests for leakage and inventory math.

12. Source code, README, project report, and viva presentation.

## 17. Final Recommended Implementation

Keep the first release centered on this end-to-end workflow:

```
M5 Historical Sales (sell_price filtered -> Parquet)
        |
        v
Horizon-Aligned Feature Engineering
        |
        v
Direct LightGBM (Tweedie, h=7/14/28)
        |
        v
Future Product Demand + Validation RMSE
        |
        v
Inventory Position + Forecast-Aware Safety Stock & ROP
        |
        v
Recommended Replenishment + 28-Day Policy Backtest
        |
        v
FastAPI REST API  --->  Next.js Web Dashboard
```

### Final scope recommendation

For a manageable B.Tech major project, prioritize:

* One M5 store and 100–300 SKUs initially.

* One baseline method (Seasonal Naive).

* Direct LightGBM (`objective="tweedie"`) for 7-, 14-, and 28-day horizons.

* A clearly labeled simulated inventory layer persisted in SQLite.

* Forecast-error-aware safety stock and reorder recommendations.

* A 28-day policy backtest proving measurable business impact over the baseline.

* A clean, responsive 6-page Next.js web dashboard backed by FastAPI.

**The central contribution is not just predicting sales. It is converting demand predictions into explainable, backtest-verified inventory replenishment recommendations.**