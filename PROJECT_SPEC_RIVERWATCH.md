# RiverWatch: River Health Intelligence & Multi-Indicator Pollution Analysis

**Type:** Final-year project | **Domain:** Environment & Climate | **Level:** Intermediate
**Stack:** Python 3.11, Pandas, NumPy, SciPy, statsmodels, scikit-learn, FastAPI, SQLite, HTML/JS + Plotly.js + Leaflet. **No Streamlit.**

> **Instructions for Claude Code:** Read this whole document first. Build the project phase by phase (Section 11). After each phase, run the tests and confirm the acceptance criteria before moving on. Do not skip phases. Ask me only if something is truly blocking; otherwise use the defaults stated here. Do NOT use Streamlit anywhere; the web layer is FastAPI + static HTML/JavaScript frontend. Python owns all data processing, calculation and modelling logic; the frontend only displays results.

---

## 1. Problem Statement

River water quality is recorded across spreadsheets, manual lab sheets and separate monitoring systems. Parameters such as pH, dissolved oxygen (DO), BOD, nitrate and faecal coliform are measured at different stations and dates with missing, duplicate or invalid entries. This makes it hard to compare stations, see long-term trends, or know **which pollutants drive the decline in quality** and **which stations need more sampling first**.

RiverWatch is a Python application that lets a user **upload monitoring data, validates and cleans it, computes a Water Quality Index (WQI) and CPCB class, analyses trends, identifies the variables most associated with changes in quality (correlation + PCA), ranks stations for further sampling, and exports results and reports.**

## 2. Objectives

1. Build a working web application: upload, validate, process, analyse, visualize, export.
2. Provide a reliable input process with **clear validation messages** and handling of missing, duplicate and invalid values.
3. Implement the analysis as **reusable Python modules**: weighted-arithmetic WQI, CPCB class compliance, Mann-Kendall + Sen's slope trends, correlation analysis, PCA, and a sampling-priority score.
4. Present results through charts, summary cards, tables and a station map with plain-language explanations.
5. Allow users to **review and correct records** (with an audit trail) and **export** cleaned data, results and a PDF report.
6. Identify which water-quality variables are most associated with quality change, and recommend where to sample next.

## 3. Scope

**In scope:** CSV/Excel upload, validation, cleaning, WQI, standards compliance, trends, correlation, PCA, driver ranking, priority ranking, dashboard, correction workflow, export, report, tests.
**Out of scope:** hydrodynamic or water-quality simulation models (QUAL2K, MIKE), real-time IoT sensor ingestion, satellite remote sensing, multi-tenant authentication (listed as future work). Basic single-role use only.

## 4. Data Sources

| Data | Source | Format | Notes |
|---|---|---|---|
| River water quality | CPCB National Water Quality Monitoring Programme (NWMP) / India-WRIS water quality data; state pollution control board reports; public Kaggle river water-quality datasets | CSV / Excel | Typical parameters: pH, DO, BOD, COD, nitrate, ammonia, conductivity, turbidity, TDS, temperature, total and faecal coliform, hardness |
| Station metadata | Same source or hand-built | CSV | Station id, river, lat, lon, order along the river (upstream to downstream) |
| Standards | CPCB "designated best use" water-quality criteria (classes A to E) and BIS limits | YAML in `config` | Stored as configuration, **verify values against the official CPCB document before final results** |

**Fallback (mandatory):** Build `src/data/synthetic.py` generating a river with ~8 stations from upstream (clean) to downstream (polluted), 8 years of monthly samples, monsoon dilution seasonality, a worsening trend downstream, realistic correlations (e.g. high BOD with low DO, high coliform in dry season), and **deliberately injected errors** (duplicates, negative values, pH of 15, text in numeric columns, missing dates, mixed units, blank cells) so the validation module can be demonstrated and tested. The whole project must run end to end on synthetic data. Real data plugs in through the same schema.

### Standard input schema (CSV/Excel)

Wide format, one row per sample:
`station_id, station_name, river, lat, lon, sample_date, ph, do_mgl, bod_mgl, cod_mgl, nitrate_mgl, ammonia_mgl, conductivity_uscm, turbidity_ntu, tds_mgl, temp_c, total_coliform_mpn, faecal_coliform_mpn`

Only `station_id` and `sample_date` plus at least 3 parameters are mandatory; the rest are optional. A downloadable **template file** is provided by the app, and column names are mapped through an alias table (e.g. `DO`, `Dissolved Oxygen`, `do_mg/l` all map to `do_mgl`).

## 5. System Flow

```
User uploads CSV/Excel (or loads sample/synthetic data)
        |
        v
[1] Input management: file type/size check, column mapping via aliases, template check
        |
        v
[2] Validation: schema, dtypes, date parsing, range checks, duplicates, missingness -> issue report (row, column, problem, suggested fix)
        |
        v
[3] User reviews issues: accept auto-fix, edit a value, or exclude the row (audit trail saved)
        |
        v
[4] Pre-processing: unit normalization, duplicate resolution, outlier flagging, imputation of short gaps (flagged), censored values (e.g. "<0.5") handled
        |
        v
[5] Commit to SQLite (stations, samples, measurements)
        |
        v
[6] Analysis engine (Python modules):
        |--> WQI (weighted arithmetic) + CPCB class + standards violations
        |--> Trend analysis: Mann-Kendall + Sen's slope per station/parameter (seasonal MK optional)
        |--> Correlation: Spearman matrix, parameter vs WQI
        |--> PCA: loadings, explained variance, station/date scores
        |--> Driver ranking: variables most associated with change in quality
        |--> Sampling priority score per station
        |
        v
[7] Results stored in SQLite + cached
        |
        v
[8] FastAPI REST layer  -->  [9] Web dashboard (charts, map, tables, correction UI)
        |
        v
[10] Export: CSV/Excel of cleaned data and results, PDF report, chart images
```

## 6. Methods (precise definitions)

### 6.1 Validation rules (each produces a message with row number, column, value, reason and suggestion)

| Check | Rule | Severity |
|---|---|---|
| Missing mandatory column | `station_id` or `sample_date` absent | Error (blocks upload) |
| Unparseable date | Cannot parse, or in the future | Error (row) |
| Non-numeric value in numeric column | e.g. "N/A", "ND", text | Warning, converted to NaN (values like `<0.5` handled as censored) |
| Physically impossible value | pH outside 0-14, DO < 0 or > 20 mg/L, BOD/COD < 0, temperature outside 0-45 C, negative concentrations | Error (row/cell flagged) |
| Suspicious outlier | Beyond median +/- 5 MAD per station and parameter | Warning (kept, flagged) |
| Duplicate | Same `(station_id, sample_date)` | Warning; options: keep first, keep last, average |
| Missingness | Parameter missing for more than 40% of a station's rows | Warning, parameter excluded from that station's WQI |
| Unit consistency | Configurable expected ranges catch likely unit errors (e.g. conductivity in mS/cm vs uS/cm) | Warning |
| Coordinates | lat/lon within India bounding box if provided | Warning |

All issues are stored in `validation_issues`; the UI shows a filterable table and a summary (e.g. "412 rows, 9 errors, 37 warnings").

### 6.2 Water Quality Index (weighted arithmetic, Brown et al.)

For each sample and each available parameter `i`:
- `S_i` = standard (permissible) value, `V_ideal` = 0 for all parameters except pH (7.0) and DO (14.6 mg/L at 20 C, or 0 deviation convention as in config).
- Unit weight `W_i = K / S_i`, where `K = 1 / sum(1/S_i)` over available parameters.
- Quality rating `q_i = 100 * (V_i - V_ideal) / (S_i - V_ideal)`; for DO use the inverse form (lower DO is worse).
- `WQI = sum(q_i * W_i) / sum(W_i)`.
- Classes (configurable): 0-25 Excellent, 26-50 Good, 51-75 Poor, 76-100 Very Poor, above 100 Unsuitable.
- Renormalize weights when parameters are missing; require at least 4 parameters including DO or BOD, otherwise WQI = NaN.
- Provide a sensitivity check: recompute WQI with equal weights and compare rank correlation.

### 6.3 CPCB class compliance

For each sample, compare DO, pH, BOD and total coliform against CPCB classes A to E (store thresholds in config). Report the best class the sample satisfies, the percentage of samples meeting class A/B/C per station, and the **violating parameters** (which parameter breaks the class).

### 6.4 Trend analysis

- For each station and parameter (and WQI): aggregate to monthly means, then use `pymannkendall` (`original_test`, or `hamed_rao_modification_test` when autocorrelation is significant; `seasonal_test` with period 12 when seasonality is present).
- Report trend direction, p-value, Kendall tau, **Sen's slope** (units per year) with confidence interval, and percentage change per year.
- Interpret direction relative to the parameter: rising BOD = worsening, rising DO = improving (config table `worse_if: increasing|decreasing`).

### 6.5 Correlation and association with quality

- Spearman correlation matrix between parameters (robust to skew); heatmap with significance masks (Benjamini-Hochberg correction).
- Spearman correlation of each parameter with WQI **computed from independent subsets** to avoid circularity (WQI is built from the same parameters; therefore also report correlation with a held-out indicator such as faecal coliform or CPCB class, and state this limitation in the app).
- **Change analysis:** split each station's record into early and late periods; Mann-Whitney U per parameter; effect size (rank-biserial); rank parameters by their contribution to the change in WQI (difference in `q_i * W_i`).

### 6.6 PCA

- Standardize (z-score, log-transform skewed variables such as coliform and turbidity first); impute remaining gaps with median per station.
- Run `sklearn.decomposition.PCA`; report explained variance (scree plot), loadings table, and a biplot of station-date scores.
- Interpret components in plain language (e.g. PC1 = organic/sewage pollution: BOD, COD, ammonia, coliform; PC2 = natural mineralization: conductivity, TDS, hardness) using the loadings.
- Check suitability with KMO and Bartlett's test (`factor_analyzer` optional, or implement with numpy/scipy); keep components until ~80% variance or eigenvalue above 1.

### 6.7 Driver ranking (variables most associated with changes in quality)

Combine three signals into one transparent rank score per parameter (weights in config, default equal):
1. Absolute PCA loading on the leading components (weighted by explained variance).
2. Absolute Spearman correlation with WQI change.
3. Contribution to WQI change between early and late periods.

Optional (clearly labelled as supporting evidence only): Random Forest regressor predicting WQI category from parameters with **permutation importance** using time-based split.

### 6.8 Sampling priority score (prioritization of further sampling)

Per station, min-max normalize each component and combine (weights in config):
`priority = 0.30*norm(mean WQI of last 12 months) + 0.25*norm(worsening trend: Sen slope of WQI) + 0.20*norm(violation rate) + 0.15*norm(days since last sample) + 0.10*norm(data gaps / variability)`
Output a ranked list with a short reason text for each station (e.g. "High WQI, worsening trend, no sample in 140 days"). Weights adjustable in the UI with live recompute.

## 7. Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11 | Core data, calculation and modelling logic |
| Data | pandas, numpy | Tabular data, dates, grouping, missing values |
| Statistics | SciPy, statsmodels, pymannkendall | Correlation, tests, trend, Sen's slope |
| ML (optional/supporting) | scikit-learn | PCA, optional Random Forest and clustering |
| File handling | openpyxl, python-multipart | Excel read/write, file uploads |
| Backend | **FastAPI** + Uvicorn, Pydantic v2 | REST API, validated schemas, auto docs at `/docs` |
| Frontend | **HTML + CSS + JavaScript (no framework), Plotly.js, Leaflet.js, simple table library** | Interactive charts and station map, no Streamlit |
| Database | SQLite via SQLAlchemy 2.0 (+ Alembic optional) | Zero-setup, enough for single-user app; PostgreSQL-ready |
| Reports | Jinja2 + matplotlib images + weasyprint (PDF) | Downloadable report |
| Config | PyYAML | Standards, aliases, weights, thresholds |
| Testing | pytest, httpx TestClient | Unit and API tests |
| Quality / tooling | ruff, black, Git, pre-commit | Code quality |
| Deployment | Docker (optional), Uvicorn, GitHub | Reproducible demo |

Keep the library set minimal: no deep learning, no extra database.

## 8. Database Design (SQLite)

```sql
CREATE TABLE rivers (
  river_id INTEGER PRIMARY KEY AUTOINCREMENT,
  river_name TEXT UNIQUE NOT NULL
);

CREATE TABLE stations (
  station_id TEXT PRIMARY KEY,
  station_name TEXT,
  river_id INTEGER REFERENCES rivers(river_id),
  lat REAL, lon REAL,
  river_order INTEGER            -- position upstream (1) to downstream (n)
);

CREATE TABLE parameters (
  param_code TEXT PRIMARY KEY,   -- 'ph','do_mgl','bod_mgl',...
  display_name TEXT,
  unit TEXT,
  standard_value REAL,           -- S_i for WQI
  ideal_value REAL,              -- V_ideal
  worse_if TEXT,                 -- 'increasing' | 'decreasing' | 'both'
  valid_min REAL, valid_max REAL
);

CREATE TABLE uploads (
  upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT,
  uploaded_at DATETIME,
  status TEXT,                   -- 'validated','committed','rejected'
  n_rows INTEGER, n_errors INTEGER, n_warnings INTEGER
);

CREATE TABLE samples (
  sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
  upload_id INTEGER REFERENCES uploads(upload_id),
  station_id TEXT REFERENCES stations(station_id),
  sample_date DATE NOT NULL,
  is_excluded INTEGER DEFAULT 0,
  UNIQUE(station_id, sample_date)
);

CREATE TABLE measurements (
  sample_id INTEGER REFERENCES samples(sample_id),
  param_code TEXT REFERENCES parameters(param_code),
  value REAL,
  raw_value TEXT,                -- original text, e.g. '<0.5'
  is_censored INTEGER DEFAULT 0,
  is_imputed INTEGER DEFAULT 0,
  is_outlier INTEGER DEFAULT 0,
  PRIMARY KEY (sample_id, param_code)
);

CREATE TABLE validation_issues (
  issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
  upload_id INTEGER REFERENCES uploads(upload_id),
  row_number INTEGER,
  column_name TEXT,
  value TEXT,
  severity TEXT,                 -- 'error' | 'warning'
  rule TEXT,
  message TEXT,
  suggestion TEXT,
  status TEXT DEFAULT 'open'     -- 'open' | 'fixed' | 'ignored' | 'excluded'
);

CREATE TABLE corrections_audit (
  audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  sample_id INTEGER, param_code TEXT,
  old_value REAL, new_value REAL,
  reason TEXT, changed_at DATETIME
);

CREATE TABLE wqi_results (
  sample_id INTEGER PRIMARY KEY REFERENCES samples(sample_id),
  wqi REAL, wqi_class TEXT, wqi_equal_weights REAL,
  cpcb_class TEXT, violating_params TEXT, n_params_used INTEGER
);

CREATE TABLE trend_results (
  station_id TEXT REFERENCES stations(station_id),
  param_code TEXT,               -- includes 'wqi'
  test_used TEXT, trend TEXT, interpretation TEXT,   -- 'worsening'|'improving'|'no trend'
  p_value REAL, tau REAL,
  sen_slope_per_year REAL, ci_low REAL, ci_high REAL, pct_change_per_year REAL,
  PRIMARY KEY (station_id, param_code)
);

CREATE TABLE correlation_results (
  param_a TEXT, param_b TEXT,
  spearman_rho REAL, p_value REAL, p_adjusted REAL, n INTEGER,
  PRIMARY KEY (param_a, param_b)
);

CREATE TABLE pca_results (
  component TEXT, param_code TEXT, loading REAL,
  explained_variance_ratio REAL,
  PRIMARY KEY (component, param_code)
);

CREATE TABLE pca_scores (
  sample_id INTEGER REFERENCES samples(sample_id),
  pc1 REAL, pc2 REAL, pc3 REAL,
  PRIMARY KEY (sample_id)
);

CREATE TABLE driver_ranking (
  param_code TEXT PRIMARY KEY,
  pca_score REAL, corr_score REAL, change_contribution REAL,
  combined_score REAL, rank INTEGER, explanation TEXT
);

CREATE TABLE station_priority (
  station_id TEXT PRIMARY KEY REFERENCES stations(station_id),
  mean_wqi_12m REAL, wqi_slope REAL, violation_rate REAL,
  days_since_last_sample INTEGER, gap_score REAL,
  priority_score REAL, priority_rank INTEGER, reason TEXT
);

CREATE TABLE reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at DATETIME, file_path TEXT, scope_json TEXT
);
```

Indexes: `samples(station_id, sample_date)`, `measurements(param_code)`, `validation_issues(upload_id, status)`.

## 9. Backend API and Frontend

### REST endpoints (FastAPI, all JSON validated by Pydantic)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/template` | Download CSV template |
| POST | `/api/uploads` | Upload CSV/Excel, returns upload id and validation summary |
| GET | `/api/uploads/{id}/issues?severity=&status=` | List validation issues |
| PATCH | `/api/uploads/{id}/issues/{issue_id}` | Fix value / ignore / exclude row (writes audit entry) |
| POST | `/api/uploads/{id}/commit` | Pre-process and commit to database |
| POST | `/api/datasets/sample` | Load built-in synthetic sample dataset |
| POST | `/api/analysis/run` | Run full analysis (WQI, trends, correlation, PCA, drivers, priority) |
| GET | `/api/stations` | Stations with latest WQI and class |
| GET | `/api/stations/{id}/series?param=&start=&end=` | Time series for a station |
| GET | `/api/wqi?station_id=&start=&end=` | WQI results |
| GET | `/api/compliance?station_id=` | CPCB class compliance |
| GET | `/api/trends?station_id=&param=` | Trend results |
| GET | `/api/correlation` | Correlation matrix |
| GET | `/api/pca` | Loadings, variance, scores |
| GET | `/api/drivers` | Ranked drivers with explanations |
| GET | `/api/priority` and `POST /api/priority/recompute` | Station ranking, with custom weights |
| GET | `/api/export/data.csv` and `/api/export/results.xlsx` | Cleaned data and result tables |
| POST | `/api/report` and GET `/api/report/{id}` | Generate and download PDF report |
| GET | `/health` | Health check |

### Frontend pages (static HTML + JS, served by FastAPI from `/`)

1. **Upload and Validate:** drag-drop upload, template download, validation summary cards, filterable issues table with inline fix / ignore / exclude buttons, "Commit data" button.
2. **Dashboard:** summary cards (stations, samples, date range, % samples meeting class B), **Leaflet map** with stations coloured by latest WQI class, WQI over time chart, upstream-to-downstream profile chart.
3. **Station Explorer:** pick station and parameters, time series with standard limit line, seasonal box plots, compliance table.
4. **Trends:** table and bar chart of Sen's slope with colours for worsening/improving, filter by parameter and significance.
5. **Drivers and Relationships:** correlation heatmap, PCA scree, loadings heatmap, biplot, ranked driver list with plain-language explanation.
6. **Sampling Priority:** ranked station table with reasons, weight sliders with live recompute, map view.
7. **Records and Corrections:** browse processed records, edit values (audit trail shown).
8. **Export and Reports:** download CSV/Excel, generate PDF report, list previous reports.

## 10. Project Structure

```
riverwatch/
|-- PROJECT_SPEC_RIVERWATCH.md
|-- README.md
|-- requirements.txt
|-- config/
|   |-- parameters.yaml        # standards, ideal values, worse_if, valid ranges
|   |-- aliases.yaml           # column name aliases
|   `-- analysis.yaml          # WQI classes, CPCB classes, weights, thresholds
|-- data/
|   |-- sample/                # synthetic + template files
|   |-- uploads/
|   `-- riverwatch.db
|-- src/
|   |-- data/
|   |   |-- synthetic.py
|   |   |-- ingest.py          # file reading, alias mapping
|   |   |-- validate.py        # rules in 6.1, returns issue list
|   |   |-- preprocess.py      # units, duplicates, censored, imputation
|   |   `-- db.py              # SQLAlchemy models + repositories
|   |-- analysis/
|   |   |-- wqi.py
|   |   |-- compliance.py
|   |   |-- trend.py
|   |   |-- correlation.py
|   |   |-- pca.py
|   |   |-- drivers.py
|   |   `-- priority.py
|   |-- report/
|   |   |-- generate.py
|   |   `-- template.html.j2
|   `-- pipeline.py            # CLI: run everything on a file or synthetic data
|-- backend/
|   |-- main.py
|   |-- routers/               # uploads, analysis, stations, export
|   |-- schemas.py             # Pydantic models
|   `-- deps.py
|-- frontend/
|   |-- index.html, upload.html, stations.html, trends.html, drivers.html, priority.html, records.html, export.html
|   |-- css/style.css
|   `-- js/
|-- tests/
|-- notebooks/                 # EDA
`-- outputs/
```

Commands: `python -m src.pipeline --source synthetic|file --path data.csv`, then `uvicorn backend.main:app --reload` and open `http://localhost:8000`.

## 11. Development Plan (12 weeks)

| Phase | Weeks | Deliverables | Acceptance criteria |
|---|---|---|---|
| 1. Setup and study | 1 | Repo, venv, requirements, config YAMLs, notes on WQI, CPCB classes, Mann-Kendall, PCA | `pip install -r requirements.txt` works, `pytest` runs |
| 2. Data layer and synthetic data | 2 | `synthetic.py` (with injected errors), `ingest.py`, `db.py`, schema in Section 8 | Synthetic dataset created with known errors; alias mapping works; tables created |
| 3. Validation and preprocessing | 3-4 | `validate.py`, `preprocess.py` | **Every injected error type is detected** with correct row/column and message; duplicates and censored values handled; tests pass |
| 4. WQI and compliance | 5 | `wqi.py`, `compliance.py` | WQI matches 3+ hand-calculated examples; missing-parameter renormalization tested; class thresholds from config |
| 5. Trends | 6 | `trend.py` | Built-in synthetic downstream worsening trend is detected with correct sign; Sen's slope within 20% of truth |
| 6. Correlation, PCA, drivers | 7-8 | `correlation.py`, `pca.py`, `drivers.py` | PCA loadings reproduce synthetic structure (organic pollution component); driver ranking puts BOD/coliform/DO near top on synthetic data |
| 7. Priority scoring and pipeline | 9 | `priority.py`, `pipeline.py` | End-to-end CLI run produces all result tables; ranking reproducible |
| 8. Backend API | 10 | FastAPI app, schemas, upload/validate/commit flow, exports | API tests pass; `/docs` lists all endpoints; upload of bad file returns clear messages |
| 9. Frontend | 11 | HTML pages with Plotly.js charts, Leaflet map, correction UI | All pages load without console errors; user can upload, fix, commit, analyse and export entirely in browser |
| 10. Report, tests, real data | 12 | PDF report, README, coverage over 70%, real NWMP data run, demo script | Pipeline and app work unchanged on real CSV; report downloads correctly |

## 12. Testing Plan

- **Validation tests:** one test per rule in 6.1 using a tiny DataFrame; the synthetic error file must produce the exact expected issue counts.
- **Calculation tests:** WQI against hand-computed values; CPCB class assignment at threshold edges; unit conversion tests.
- **Statistical tests:** perfectly monotone series gives p below 0.05 and expected Sen's slope; random noise gives no trend; PCA on constructed correlated data recovers expected loadings.
- **Priority tests:** station with highest WQI, worst trend and oldest sample ranks first.
- **API tests:** upload, issues, patch, commit, analysis, export endpoints return correct status codes and schemas; malformed requests return 422 with helpful details; oversized or wrong-type files rejected.
- **Audit test:** every correction creates an `corrections_audit` row.
- **Smoke test:** full pipeline on synthetic data, and the app starts and serves the home page.

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Inconsistent column names and units in real files | Alias table, unit-range checks, clear mapping messages, downloadable template |
| Sparse or irregular sampling (e.g. monthly with gaps) | Aggregate to monthly, require minimum records (e.g. 24 months) for trend tests, show "insufficient data" instead of a misleading result |
| WQI circularity when correlating with parameters | Use held-out indicators and PCA/change-contribution evidence; explain limitation in UI and report |
| Standards differ by use (drinking vs bathing vs ecology) | Make standards configurable; default to CPCB designated best use; document choice |
| Correlation is not causation | Phrase outputs as "associated with", not "caused by" |
| Censored values ("<0.5") bias statistics | Substitute half the detection limit, flag them, and test sensitivity |
| Large upload files slow the app | File-size limit, chunked reading, background task for analysis |
| Real data licensing or access | Keep synthetic dataset for demo; document data sources in the report |

## 14. Final Deliverables Checklist

- [ ] Working code in repo with README and setup steps
- [ ] SQLite database with all tables and the audit trail
- [ ] Validation module with clear messages and correction workflow
- [ ] Analysis modules: WQI, compliance, trends, correlation, PCA, drivers, priority
- [ ] FastAPI backend with Swagger docs
- [ ] Web dashboard (HTML + Plotly.js + Leaflet), no Streamlit
- [ ] Export to CSV/Excel and PDF report
- [ ] Final project report (Introduction, Literature Review, Data and Methodology, Implementation, Results and Discussion, Conclusion and Future Work, References)
- [ ] Presentation slides and demo script
- [ ] Future work: user authentication and roles, PostgreSQL, real-time sensor feeds, forecasting of WQI, remote-sensing indicators, mobile data entry app

## 15. Claude Code Starter Prompts

Use in order:

1. `Read PROJECT_SPEC_RIVERWATCH.md. Set up the repo structure from Section 10, requirements.txt, the three YAML config files and a README. Do Phase 1 only. Do not use Streamlit.`
2. `Implement Phase 2: synthetic data generator with the injected errors listed in Section 4, ingestion with alias mapping, and the SQLAlchemy schema from Section 8, with pytest tests.`
3. `Implement Phase 3: validate.py and preprocess.py following the rule table in Section 6.1. Tests must confirm every injected error is caught with the right row, column and message.`
4. `Implement Phase 4: weighted-arithmetic WQI and CPCB compliance exactly as in 6.2 and 6.3, config-driven, with hand-calculated tests.`
5. `Implement Phase 5: trend analysis with Mann-Kendall and Sen's slope per 6.4, including interpretation of worsening/improving using the worse_if table.`
6. `Implement Phase 6: correlation, PCA and driver ranking per 6.5 to 6.7 with tests on constructed data.`
7. `Implement Phase 7: sampling priority score per 6.8 and the end-to-end pipeline CLI.`
8. `Implement Phase 8: the FastAPI backend with all endpoints in Section 9, Pydantic schemas, audit-trail corrections, exports and API tests.`
9. `Implement Phase 9: static HTML + JavaScript frontend pages with Plotly.js charts and a Leaflet station map, including the upload, validation and correction workflow. No Streamlit.`
10. `Generate the PDF report, finish README, raise test coverage to 70%+, add an optional Dockerfile.`
11. `Add support for real CPCB/NWMP data files: document the column mapping, extend aliases, and test with a sample real-format CSV.`

## 16. References (starting points)

- Brown, R.M. et al. (1970): A water quality index, do we dare?
- CPCB: Water Quality Criteria (designated best use classes A to E) and NWMP guidelines
- BIS 10500: drinking water specification
- Mann (1945), Kendall (1975), Sen (1968): trend test and slope estimator
- Hamed & Rao (1998): modified Mann-Kendall test
- Jolliffe, I.T.: Principal Component Analysis; Helsel, D.R.: Nondetects and Data Analysis (censored data)
- Documentation: FastAPI, Pydantic, pandas, SciPy, statsmodels, scikit-learn, pymannkendall, Plotly.js, Leaflet
