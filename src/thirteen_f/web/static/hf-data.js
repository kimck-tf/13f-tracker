// 13F Terminal — data layer (Phase 5: hydrated by bootstrapFromJson)
// Mock data removed; bootstrap fetches /data/*.json (produced by `thirteen-f export`).
// See _claude_docs/FRONTEND_PARITY.md for which fields are exporter-owned vs derived.

let QUARTERS = [];      // ["2024Q2", ...] — exporter quarters.json[i].key
let Q_LABELS = [];      // ["Q2'24", ...] — exporter quarters.json[i].label
let STOCKS = [];        // [{t, n, s, i?, mc?, px:[N], yld?}] — exporter stocks.json
let STOCK_MAP = {};     // {ticker: stock}
let MANAGERS = [];      // [{id, name, firm, style, color, avatar, note}]
let MGR_MAP = {};       // {id: manager}
let HOLDINGS = {};      // {mgrId: {ticker: [shares_M_per_quarter]}}
let HOLDINGS_UNMAPPED = {}; // {mgrId: {cusip: {name_of_issuer, shares:[...]}}}
let BACKTESTS = [];     // [{run_id, name, equity, dd, qrets, holdingsLog, metrics}]
let LLM_SUMMARY = {};   // {[period]: {headline, top_signals}}
let META = {};          // {generated_at, latest_period, data_version, ...}

const SECTOR_COLORS = {
  Tech: "#1d6dc8",
  Technology: "#1d6dc8",
  Financials: "#6d28d9",
  "Financial Services": "#6d28d9",
  Energy: "#b45309",
  Consumer: "#0e8a3b",
  "Consumer Cyclical": "#0e8a3b",
  "Consumer Defensive": "#0e8a3b",
  Healthcare: "#0e7490",
  Other: "#475569",
};

// Daily-ish price series for charting (12 quarters, 65 weekly samples)
function buildWeeklyPrices(quarterly, drift = 0) {
  // interpolate between quarter-end prices with mild noise; result length = (q-1)*8 + 1
  const out = [];
  let s = 1;
  for (let i = 0; i < quarterly.length - 1; i++) {
    const a = quarterly[i], b = quarterly[i + 1];
    for (let j = 0; j < 8; j++) {
      const f = j / 8;
      const interp = a + (b - a) * f;
      const noise = Math.sin(s * 1.7 + i * 1.3) * (a + b) * 0.008;
      out.push(+(interp + noise).toFixed(2));
      s++;
    }
  }
  out.push(quarterly[quarterly.length - 1]);
  return out;
}
// pxWeekly is rebuilt inside bootstrapFromJson once STOCKS is hydrated.

// ─── Derived helpers ────────────────────────────────────────────────────────
// classify action between two quarters
function classifyAction(prev, curr) {
  if (prev === 0 && curr === 0) return null;
  if (prev === 0 && curr > 0) return "NEW";
  if (prev > 0 && curr === 0) return "EXIT";
  const ratio = curr / prev;
  if (ratio >= 1.05) return "ADD";
  if (ratio <= 0.95) return "CUT";
  return "HOLD";
}

// position-level: dollar value, weight
function positionValue(shares, ticker, qIdx) {
  const s = STOCK_MAP[ticker];
  if (!s) return 0;
  return shares * s.px[qIdx]; // shares in millions * price -> $M
}

// manager total at a quarter (sum of held position values)
function managerTotal(mgrId, qIdx) {
  const h = HOLDINGS[mgrId] || {};
  let total = 0;
  for (const tk in h) {
    total += positionValue(h[tk][qIdx], tk, qIdx);
  }
  return total;
}

// portfolio at quarter: array of { ticker, shares, prevShares, value, weight, action, deltaWeight }
function managerPortfolio(mgrId, qIdx) {
  const h = HOLDINGS[mgrId] || {};
  const total = managerTotal(mgrId, qIdx);
  const totalPrev = qIdx > 0 ? managerTotal(mgrId, qIdx - 1) : total;
  const rows = [];
  for (const tk in h) {
    if (!STOCK_MAP[tk]) continue; // skip unknown tickers
    const shares = h[tk][qIdx];
    const prev = qIdx > 0 ? h[tk][qIdx - 1] : 0;
    if (shares === 0 && prev === 0) continue;
    const value = positionValue(shares, tk, qIdx);
    const valuePrev = qIdx > 0 ? positionValue(prev, tk, qIdx - 1) : 0;
    const weight = total > 0 ? value / total : 0;
    const weightPrev = totalPrev > 0 ? valuePrev / totalPrev : 0;
    const action = classifyAction(prev, shares);
    rows.push({
      ticker: tk,
      stock: STOCK_MAP[tk],
      shares, prevShares: prev,
      value, valuePrev,
      weight, weightPrev,
      deltaWeight: weight - weightPrev,
      deltaShares: shares - prev,
      action,
      held: shares > 0,
      seriesShares: h[tk],
    });
  }
  rows.sort((a, b) => b.weight - a.weight);
  return rows;
}

// all activity in a quarter (across managers): array of { mgrId, ticker, action, weight, deltaWeight, value, deltaValue }
function quarterActivity(qIdx) {
  const acts = [];
  for (const mgrId in HOLDINGS) {
    const port = managerPortfolio(mgrId, qIdx);
    for (const r of port) {
      if (r.action && r.action !== "HOLD") {
        acts.push({
          mgrId,
          mgr: MGR_MAP[mgrId],
          ticker: r.ticker,
          stock: r.stock,
          action: r.action,
          weight: r.weight,
          deltaWeight: r.deltaWeight,
          value: r.value,
          deltaValue: r.value - r.valuePrev,
        });
      }
    }
  }
  return acts;
}

// for a given ticker, who holds it across quarters
function tickerHolders(ticker, qIdx) {
  const arr = [];
  for (const mgrId in HOLDINGS) {
    const series = HOLDINGS[mgrId][ticker];
    if (!series) continue;
    const shares = series[qIdx];
    if (shares === 0) continue;
    const total = managerTotal(mgrId, qIdx);
    const value = positionValue(shares, ticker, qIdx);
    const weight = total > 0 ? value / total : 0;
    const prev = qIdx > 0 ? series[qIdx - 1] : 0;
    const action = classifyAction(prev, shares);
    arr.push({
      mgrId,
      mgr: MGR_MAP[mgrId],
      shares,
      value,
      weight,
      prevShares: prev,
      action,
      series,
    });
  }
  arr.sort((a, b) => b.weight - a.weight);
  return arr;
}

// crowdedness for a ticker — how many managers hold at qIdx
function tickerCrowdedness(ticker, qIdx) {
  let n = 0, sumWeight = 0;
  const holders = tickerHolders(ticker, qIdx);
  return { n: holders.length, holders };
}

// summary: count by action across all managers for a quarter
function quarterSummary(qIdx) {
  const acts = quarterActivity(qIdx);
  const by = { NEW: 0, ADD: 0, CUT: 0, EXIT: 0 };
  for (const a of acts) by[a.action] = (by[a.action] || 0) + 1;
  return { acts, by };
}

// Find the "spotlight" move for the latest quarter — biggest abs deltaValue
function spotlight(qIdx) {
  const acts = quarterActivity(qIdx);
  if (acts.length === 0) return null;
  return acts.slice().sort((a, b) => Math.abs(b.deltaValue) - Math.abs(a.deltaValue))[0];
}

// Compute a follow-strategy equity curve
// strategy: { manager: 'buffett', weighting: 'equal'|'bymgr', topN: number, start: qIdx, end: qIdx }
function followStrategyEquity(opts) {
  const { mgrId = "buffett", weighting = "equal", topN = 10, startQ = 0, endQ = QUARTERS.length - 1 } = opts;
  return runStrategy({
    type: "SingleManagerClone",
    params: { mgrId, weighting, topN },
    startQ, endQ,
  });
}

// =============================================================================
// Strategy library — 7 strategy types
// =============================================================================

// Each strategy implements pickHoldings(qIdx) → array of { ticker, weight } at qIdx-end.
// Then runStrategy computes equity by rolling holdings into next-quarter returns.

function pickHoldings_SingleManagerClone(params, qIdx) {
  const { mgrId = "buffett", weighting = "equal", topN = 10 } = params;
  const port = managerPortfolio(mgrId, qIdx).filter(r => r.held).slice(0, topN);
  if (port.length === 0) return [];
  if (weighting === "bymgr") {
    const total = port.reduce((a, b) => a + b.weight, 0) || 1;
    return port.map(r => ({ ticker: r.ticker, weight: r.weight / total }));
  }
  return port.map(r => ({ ticker: r.ticker, weight: 1 / port.length }));
}

function pickHoldings_MultiManager(params, qIdx) {
  const { mgrIds = ["buffett"], weighting = "equal", topN = 10 } = params;
  // Each manager contributes their top picks; aggregate by ticker, average weights
  const agg = {};
  for (const id of mgrIds) {
    const port = managerPortfolio(id, qIdx).filter(r => r.held).slice(0, topN);
    for (const r of port) {
      agg[r.ticker] = (agg[r.ticker] || 0) + r.weight;
    }
  }
  const list = Object.entries(agg).map(([t, w]) => ({ ticker: t, score: w }));
  list.sort((a, b) => b.score - a.score);
  const picks = list.slice(0, topN);
  if (picks.length === 0) return [];
  if (weighting === "byscore") {
    const total = picks.reduce((a, b) => a + b.score, 0) || 1;
    return picks.map(r => ({ ticker: r.ticker, weight: r.score / total }));
  }
  return picks.map(r => ({ ticker: r.ticker, weight: 1 / picks.length }));
}

function pickHoldings_NewBuyOnly(params, qIdx) {
  // Tickers where ANY manager opened a new position OR added significantly this quarter
  const { minHolders = 2, topN = 15 } = params;
  if (qIdx === 0) return [];
  const acts = quarterActivity(qIdx).filter(a => a.action === "NEW" || a.action === "ADD");
  // Count how many managers acted positively per ticker
  const byTicker = {};
  for (const a of acts) {
    if (!byTicker[a.ticker]) byTicker[a.ticker] = { ticker: a.ticker, n: 0, sumDelta: 0 };
    byTicker[a.ticker].n += 1;
    byTicker[a.ticker].sumDelta += a.deltaValue;
  }
  const filtered = Object.values(byTicker).filter(r => r.n >= minHolders);
  filtered.sort((a, b) => b.sumDelta - a.sumDelta);
  const picks = filtered.slice(0, topN);
  if (picks.length === 0) return [];
  return picks.map(r => ({ ticker: r.ticker, weight: 1 / picks.length }));
}

function pickHoldings_ScoreTopK(params, qIdx) {
  // Score = sum across managers of (weight × log(1+holdersCount) × persistence)
  // Persistence = how many consecutive prior quarters held (1..8)
  const { K = 20 } = params;
  const scores = {};
  for (const tk of Object.keys(STOCK_MAP)) {
    const holders = tickerHolders(tk, qIdx);
    if (holders.length === 0) continue;
    // count holders count and conviction
    let totalConviction = 0;
    let totalPersistence = 0;
    for (const h of holders) {
      totalConviction += h.weight;
      // count consecutive prior quarters held
      let p = 0;
      for (let q = qIdx; q >= 0; q--) {
        if (h.series[q] > 0) p++; else break;
      }
      totalPersistence += p;
    }
    const holdersCount = holders.length;
    scores[tk] = totalConviction * Math.log(1 + holdersCount) * (1 + totalPersistence / 16);
  }
  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]).slice(0, K);
  if (sorted.length === 0) return [];
  return sorted.map(([t]) => ({ ticker: t, weight: 1 / sorted.length }));
}

function pickHoldings_ConvictionFollow(params, qIdx) {
  // Tickers where at least one manager has weight >= minConviction (e.g. 10%)
  const { minConvictionPct = 10 } = params;
  const min = minConvictionPct / 100;
  const tickers = new Set();
  for (const id of Object.keys(HOLDINGS)) {
    const port = managerPortfolio(id, qIdx);
    for (const r of port) {
      if (r.held && r.weight >= min) tickers.add(r.ticker);
    }
  }
  const picks = Array.from(tickers);
  if (picks.length === 0) return [];
  return picks.map(t => ({ ticker: t, weight: 1 / picks.length }));
}

function pickHoldings_ConsensusTopK(params, qIdx) {
  const { minHolders = 3, K = 20 } = params;
  const list = [];
  for (const tk of Object.keys(STOCK_MAP)) {
    const holders = tickerHolders(tk, qIdx);
    if (holders.length >= minHolders) {
      list.push({ ticker: tk, n: holders.length, avgWeight: holders.reduce((a, b) => a + b.weight, 0) / holders.length });
    }
  }
  list.sort((a, b) => b.n - a.n || b.avgWeight - a.avgWeight);
  const picks = list.slice(0, K);
  if (picks.length === 0) return [];
  return picks.map(r => ({ ticker: r.ticker, weight: 1 / picks.length }));
}

function pickHoldings_Ensemble(params, qIdx) {
  // params.components: [{ type, params, weight }]
  // Aggregate weighted holdings from each component
  const { components = [] } = params;
  const agg = {};
  let totalWeight = 0;
  for (const c of components) {
    totalWeight += c.weight;
    const subPicks = pickByType(c.type, c.params || {}, qIdx);
    for (const p of subPicks) {
      agg[p.ticker] = (agg[p.ticker] || 0) + p.weight * c.weight;
    }
  }
  if (totalWeight === 0) return [];
  // Normalize so weights sum to 1
  const list = Object.entries(agg).map(([t, w]) => ({ ticker: t, weight: w / totalWeight }));
  // sort by weight desc and drop tiny
  list.sort((a, b) => b.weight - a.weight);
  return list.filter(p => p.weight > 0);
}

function pickByType(type, params, qIdx) {
  switch (type) {
    case "SingleManagerClone": return pickHoldings_SingleManagerClone(params, qIdx);
    case "MultiManager":       return pickHoldings_MultiManager(params, qIdx);
    case "NewBuyOnly":         return pickHoldings_NewBuyOnly(params, qIdx);
    case "ScoreTopK":          return pickHoldings_ScoreTopK(params, qIdx);
    case "ConvictionFollow":   return pickHoldings_ConvictionFollow(params, qIdx);
    case "ConsensusTopK":      return pickHoldings_ConsensusTopK(params, qIdx);
    case "Ensemble":           return pickHoldings_Ensemble(params, qIdx);
    default: return [];
  }
}

// Generic strategy runner — works for all 7 types
function runStrategy({ type, params = {}, startQ = 0, endQ = QUARTERS.length - 1, cashYield = 0.04 }) {
  const equity = [1.0];
  const benchEquity = [1.0];
  const holdingsLog = []; // [{ q, picks }]
  let v = 1.0, bv = 1.0;
  for (let q = startQ; q < endQ; q++) {
    const picks = pickByType(type, params, q);
    holdingsLog.push({ q, picks });
    let ret = 0;
    if (picks.length === 0) {
      // Hold cash — earn cash yield
      ret = cashYield / 4;
    } else {
      // weights sum to 1; if not, normalize
      const totalW = picks.reduce((a, b) => a + b.weight, 0);
      for (const p of picks) {
        const s = STOCK_MAP[p.ticker];
        if (!s) continue;
        const px0 = s.px[q];
        const px1 = s.px[q + 1];
        const w = totalW > 0 ? p.weight / totalW : 0;
        ret += w * (px1 - px0) / px0;
        // Add dividend yield (annualized → quarterly approx)
        ret += w * (s.yld / 100) / 4;
      }
    }
    let bret = 0;
    for (const s of STOCKS) bret += (s.px[q + 1] - s.px[q]) / s.px[q];
    bret /= STOCKS.length;
    v *= (1 + ret);
    bv *= (1 + bret);
    equity.push(v);
    benchEquity.push(bv);
  }
  // Drawdown
  const dd = [];
  let peak = equity[0];
  for (const e of equity) {
    if (e > peak) peak = e;
    dd.push((e - peak) / peak);
  }
  const ddBench = [];
  let peakBench = benchEquity[0];
  for (const e of benchEquity) {
    if (e > peakBench) peakBench = e;
    ddBench.push((e - peakBench) / peakBench);
  }
  // Metrics
  const totalRet = equity[equity.length - 1] - 1;
  const benchRet = benchEquity[benchEquity.length - 1] - 1;
  const years = (endQ - startQ) / 4;
  const cagr = years > 0 ? Math.pow(1 + totalRet, 1 / years) - 1 : 0;
  const benchCagr = years > 0 ? Math.pow(1 + benchRet, 1 / years) - 1 : 0;
  const maxDD = Math.min(...dd);
  const qrets = [];
  const qretsBench = [];
  for (let i = 1; i < equity.length; i++) {
    qrets.push(equity[i] / equity[i - 1] - 1);
    qretsBench.push(benchEquity[i] / benchEquity[i - 1] - 1);
  }
  const mean = qrets.reduce((a, b) => a + b, 0) / Math.max(1, qrets.length);
  const variance = qrets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, qrets.length);
  const vol = Math.sqrt(variance * 4);
  const sharpe = vol > 0 ? (cagr - cashYield) / vol : 0;
  // Sortino — downside deviation
  const downside = qrets.filter(r => r < 0);
  const downVar = downside.reduce((a, b) => a + b * b, 0) / Math.max(1, downside.length);
  const downVol = Math.sqrt(downVar * 4);
  const sortino = downVol > 0 ? (cagr - cashYield) / downVol : 0;
  // Calmar
  const calmar = maxDD < 0 ? cagr / Math.abs(maxDD) : 0;
  // Beta vs bench (covariance / variance)
  const meanB = qretsBench.reduce((a, b) => a + b, 0) / Math.max(1, qretsBench.length);
  let cov = 0, varB = 0;
  for (let i = 0; i < qrets.length; i++) {
    cov += (qrets[i] - mean) * (qretsBench[i] - meanB);
    varB += (qretsBench[i] - meanB) ** 2;
  }
  cov /= Math.max(1, qrets.length); varB /= Math.max(1, qrets.length);
  const beta = varB > 0 ? cov / varB : 0;
  // hit rate vs bench
  let hits = 0;
  for (let i = 0; i < qrets.length; i++) if (qrets[i] >= qretsBench[i]) hits++;
  const hitRate = qrets.length > 0 ? hits / qrets.length : 0;
  // turnover estimate (avg # of name changes between consecutive rebalances)
  let turnoverSum = 0;
  for (let i = 1; i < holdingsLog.length; i++) {
    const prev = new Set(holdingsLog[i - 1].picks.map(p => p.ticker));
    const curr = new Set(holdingsLog[i].picks.map(p => p.ticker));
    let diffs = 0;
    for (const t of curr) if (!prev.has(t)) diffs++;
    for (const t of prev) if (!curr.has(t)) diffs++;
    turnoverSum += diffs / Math.max(1, curr.size);
  }
  const turnover = holdingsLog.length > 1 ? turnoverSum / (holdingsLog.length - 1) : 0;
  return {
    equity, benchEquity, dd, ddBench, qrets, qretsBench, holdingsLog,
    cagr, benchCagr, vol, sharpe, sortino, calmar, beta, maxDD, hitRate,
    alpha: cagr - benchCagr,
    totalRet, benchRet, turnover,
  };
}

// Strategy type metadata for UI
const STRATEGY_TYPES = [
  {
    type: "SingleManagerClone",
    name: "Single Manager Clone",
    desc: "한 매니저의 Top N 포지션을 그대로 복제",
    color: "#1d6dc8",
    params: [
      { key: "mgrId", label: "Manager", kind: "manager", default: "buffett" },
      { key: "topN", label: "Top N", kind: "int", min: 3, max: 20, default: 10 },
      { key: "weighting", label: "Weighting", kind: "enum", options: ["equal", "bymgr"], default: "equal" },
    ],
    summary: p => `${MGR_MAP[p.mgrId]?.name.split(" ").slice(-1)[0] || "?"} · top ${p.topN || 10}`,
  },
  {
    type: "MultiManager",
    name: "Multi-Manager Blend",
    desc: "여러 매니저의 Top 포지션을 합쳐 점수 순으로 선정",
    color: "#0e7490",
    params: [
      { key: "mgrIds", label: "Managers", kind: "managerList", default: ["buffett", "ackman", "tepper"] },
      { key: "topN", label: "Top N", kind: "int", min: 3, max: 30, default: 15 },
      { key: "weighting", label: "Weighting", kind: "enum", options: ["equal", "byscore"], default: "equal" },
    ],
    summary: p => `${(p.mgrIds || []).length} mgrs · top ${p.topN || 15}`,
  },
  {
    type: "NewBuyOnly",
    name: "New Buys Only",
    desc: "이번 분기 신규 매수·추가 매수만 — 모멘텀 추종",
    color: "#0e8a3b",
    params: [
      { key: "minHolders", label: "Min holders", kind: "int", min: 1, max: 5, default: 2 },
      { key: "topN", label: "Top N", kind: "int", min: 5, max: 30, default: 15 },
    ],
    summary: p => `≥${p.minHolders || 2} mgrs · top ${p.topN || 15}`,
  },
  {
    type: "ScoreTopK",
    name: "Score Top K",
    desc: "Conviction × #holders × Persistence 점수 상위 K",
    color: "#7c3aed",
    params: [
      { key: "K", label: "Top K", kind: "int", min: 5, max: 30, default: 20 },
    ],
    summary: p => `top ${p.K || 20}`,
  },
  {
    type: "ConvictionFollow",
    name: "Conviction Follow",
    desc: "매니저 포트의 비중이 임계값 이상인 모든 종목",
    color: "#b45309",
    params: [
      { key: "minConvictionPct", label: "Min weight %", kind: "int", min: 3, max: 25, default: 10 },
    ],
    summary: p => `≥${p.minConvictionPct || 10}%`,
  },
  {
    type: "ConsensusTopK",
    name: "Consensus Top K",
    desc: "최소 N명이 보유한 종목 중 # holders 상위 K",
    color: "#c8261e",
    params: [
      { key: "minHolders", label: "Min holders", kind: "int", min: 2, max: 5, default: 3 },
      { key: "K", label: "Top K", kind: "int", min: 5, max: 30, default: 20 },
    ],
    summary: p => `≥${p.minHolders || 3} mgrs · top ${p.K || 20}`,
  },
  {
    type: "Ensemble",
    name: "Ensemble",
    desc: "여러 전략을 가중치로 블렌드",
    color: "#0a0d14",
    params: [
      { key: "components", label: "Components", kind: "components", default: [
        { type: "SingleManagerClone", params: { mgrId: "buffett", topN: 10 }, weight: 0.4 },
        { type: "ScoreTopK", params: { K: 20 }, weight: 0.4 },
        { type: "ConsensusTopK", params: { minHolders: 3, K: 20 }, weight: 0.2 },
      ]},
    ],
    summary: p => `${(p.components || []).length} components`,
  },
];

const STRATEGY_TYPE_MAP = Object.fromEntries(STRATEGY_TYPES.map(s => [s.type, s]));

function makeDefaultStrategyParams(type) {
  const meta = STRATEGY_TYPE_MAP[type];
  if (!meta) return {};
  const out = {};
  for (const p of meta.params) {
    out[p.key] = p.default;
  }
  return out;
}

function strategyLabel(s) {
  const meta = STRATEGY_TYPE_MAP[s.type];
  if (!meta) return s.type;
  const summary = meta.summary(s.params || {});
  return `${s.type}(${summary})`;
}

// =============================================================================
// Bootstrap — fetch /data/*.json into module-level state (Phase 5 C1)
// =============================================================================

async function bootstrapFromJson(baseUrl = "/data") {
  async function fetchJson(path, fallback) {
    try {
      const r = await fetch(`${baseUrl}/${path}`);
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      if (fallback !== undefined) return fallback;
      throw e;
    }
  }

  const [meta, quarters, managers, stocks, holdings, holdingsUnmapped, backtests, llm] = await Promise.all([
    fetchJson("meta.json"),
    fetchJson("quarters.json"),
    fetchJson("managers.json"),
    fetchJson("stocks.json"),
    fetchJson("holdings.json"),
    fetchJson("holdings_unmapped.json", {}),
    fetchJson("backtest.json", []),
    fetchJson("llm_summary.json", {}),
  ]);

  META = meta;
  QUARTERS = quarters.map(q => q.key);
  Q_LABELS = quarters.map(q => q.label);
  STOCKS = stocks;
  STOCK_MAP = Object.fromEntries(STOCKS.map(s => [s.t, s]));
  STOCKS.forEach(st => {
    if (Array.isArray(st.px) && st.px.length > 1) {
      st.pxWeekly = buildWeeklyPrices(st.px);
    } else {
      st.pxWeekly = st.px ? st.px.slice() : [];
    }
  });
  MANAGERS = managers;
  MGR_MAP = Object.fromEntries(MANAGERS.map(m => [m.id, m]));
  HOLDINGS = holdings;
  HOLDINGS_UNMAPPED = holdingsUnmapped;
  BACKTESTS = backtests;
  LLM_SUMMARY = llm;

  Object.assign(window, {
    QUARTERS, Q_LABELS, STOCKS, STOCK_MAP, MANAGERS, MGR_MAP,
    HOLDINGS, HOLDINGS_UNMAPPED, BACKTESTS, LLM_SUMMARY, META,
  });
  return META;
}

// Lazy daily price fetch — called per-ticker by StockScreen (Phase 5 C3).
// Returns {date:[], close:[]} fallback so consumers can treat as iterable.
async function fetchDailyPx(ticker, baseUrl = "/data") {
  try {
    const r = await fetch(`${baseUrl}/prices/${encodeURIComponent(ticker)}.json`);
    if (!r.ok) return { date: [], close: [] };
    return await r.json();
  } catch {
    return { date: [], close: [] };
  }
}

// expose globals + bootstrap (loaded as a plain script tag)
Object.assign(window, {
  QUARTERS, Q_LABELS, STOCKS, STOCK_MAP, MANAGERS, MGR_MAP, HOLDINGS,
  HOLDINGS_UNMAPPED, BACKTESTS, LLM_SUMMARY, META, SECTOR_COLORS,
  classifyAction, positionValue, managerTotal, managerPortfolio,
  quarterActivity, tickerHolders, tickerCrowdedness, quarterSummary, spotlight,
  followStrategyEquity, runStrategy, pickByType,
  STRATEGY_TYPES, STRATEGY_TYPE_MAP, makeDefaultStrategyParams, strategyLabel,
  bootstrapFromJson, fetchDailyPx,
});
