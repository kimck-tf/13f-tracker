// 13F Terminal — Backtest screen with strategy library

function BacktestScreen({ route, quarter, setQuarter }) {
  const initMgr = route.params.mgr || "buffett";

  // Strategy list — each is { id, type, params, color, on }
  const [strategies, setStrategies] = useState(() => [
    {
      id: "s1",
      type: "SingleManagerClone",
      params: { mgrId: initMgr, topN: 10, weighting: "equal" },
      color: MGR_MAP[initMgr]?.color || "#1d6dc8",
      on: true,
    },
  ]);
  const [openPicker, setOpenPicker] = useState(false);
  const [leadStratId, setLeadStratId] = useState("s1");

  // Quick-controls — these mirror strategy s1 (SingleManagerClone) when it exists
  const quickStrat = strategies[0];

  const startQ = 0;
  const endQ = QUARTERS.length - 1;

  // Phase 5: backend BACKTESTS(real run) 우선, 매칭 실패 시 runStrategy(prototype) fallback.
  // 같은 type끼리는 createdAt DESC 순서로 첫 매칭 — frontend의 다중 strategy list는
  // 디자인 prototype이라 backend의 default suite와 1:1 정렬 안 됨. 일치/근사가 우선.
  const results = useMemo(() => {
    const used = new Set();
    return strategies.filter(s => s.on).map(s => {
      // 매칭 키: type prefix (e.g., "SingleManagerClone" matches "SingleManagerClone(Buffett)")
      const match = (Array.isArray(BACKTESTS) ? BACKTESTS : []).find(r =>
        r && r.run_id && !used.has(r.run_id) && typeof r.name === "string" && r.name.startsWith(s.type)
      );
      if (match && Array.isArray(match.equity) && match.equity.length > 0) {
        used.add(match.run_id);
        const m = match.metrics || {};
        return {
          strategy: s,
          data: {
            equity: match.equity,
            dd: match.dd || [],
            qrets: match.qrets || [],
            benchEquity: match.benchEquity || [],
            holdingsLog: match.holdingsLog || [],
            cagr: m.cagr ?? 0,
            sharpe: m.sharpe ?? 0,
            sortino: m.sortino ?? 0,
            maxDD: m.maxDD ?? 0,
            calmar: m.calmar ?? 0,
            hitRate: m.hitRate ?? 0,
            benchCagr: m.benchCagr ?? 0,
            totalRet: m.totalRet ?? 0,
            benchRet: m.benchTotalRet ?? 0,
            alpha: (m.cagr ?? 0) - (m.benchCagr ?? 0),
            // 미export 필드는 0 fallback (prototype과 shape 호환)
            vol: 0, beta: 0, turnover: 0,
            qretsBench: [], ddBench: [],
            _source: "backend",
            _runId: match.run_id,
          },
        };
      }
      // Fallback: prototype runStrategy (mock-era 시뮬, Builder/Compare UI 용도)
      return {
        strategy: s,
        data: { ...runStrategy({ type: s.type, params: s.params, startQ, endQ }), _source: "prototype" },
      };
    });
  }, [strategies]);

  // Benchmark from first result
  const bench = results[0]?.data.benchEquity || [];

  // Lead strategy — best by Sharpe
  const lead = useMemo(() => {
    if (results.length === 0) return null;
    const ranked = results.slice().sort((a, b) => b.data.sharpe - a.data.sharpe);
    return ranked[0];
  }, [results]);

  // Aggregate KPIs across strategies
  const bestCAGR = results.length ? Math.max(...results.map(r => r.data.cagr)) : 0;
  const bestSharpe = results.length ? Math.max(...results.map(r => r.data.sharpe)) : 0;
  const deepestMDD = results.length ? Math.min(...results.map(r => r.data.maxDD)) : 0;
  const benchCAGR = results[0]?.data.benchCagr || 0;

  function updateStrategy(id, patch) {
    setStrategies(list => list.map(s => s.id === id ? { ...s, ...patch } : s));
  }
  function updateStrategyParams(id, paramPatch) {
    setStrategies(list => list.map(s => s.id === id ? { ...s, params: { ...s.params, ...paramPatch } } : s));
  }
  function addStrategy(type) {
    const meta = STRATEGY_TYPE_MAP[type];
    const id = "s" + Date.now();
    const params = makeDefaultStrategyParams(type);
    const color = nextColor(strategies);
    setStrategies(list => [...list, { id, type, params, color, on: true }]);
    setOpenPicker(false);
  }
  function removeStrategy(id) {
    if (strategies.length <= 1) return;
    setStrategies(list => list.filter(s => s.id !== id));
    if (leadStratId === id) setLeadStratId(strategies[0]?.id);
  }

  const equitySeries = [
    ...results.map(r => ({
      label: strategyLabel(r.strategy),
      color: r.strategy.color,
      values: r.data.equity,
      width: r.strategy.id === (lead?.strategy.id) ? 2.2 : 1.5,
    })),
    { label: "S&P 500 (avg)", color: "var(--ink-3)", values: bench, dashed: true, width: 1.2 },
  ];

  const ddSeries = results.map(r => ({
    label: strategyLabel(r.strategy),
    color: r.strategy.color,
    values: r.data.dd,
    width: r.strategy.id === (lead?.strategy.id) ? 2 : 1.2,
  }));

  return (
    <>
      <Topbar
        crumbs={[{ label: "Backtest" }]}
        right={
          <div className="hf-top-actions">
            <Pill>save</Pill>
            <Pill>export</Pill>
          </div>
        }
      />
      <div className="hf-pg bt">
        {/* Aggregate KPI strip */}
        <div className="bt-agg-kpis">
          <Stat label="STRATEGIES" value={results.length} sub="active" />
          <Stat label="BEST CAGR" value={<span className="pos">{fmtPct(bestCAGR, { signed: true })}</span>} />
          <Stat label="BEST SHARPE" value={<span className="pos">{bestSharpe.toFixed(2)}</span>} />
          <Stat label="DEEPEST MDD" value={<span className="neg">{fmtPct(deepestMDD)}</span>} />
          <Stat label="BENCH CAGR" value={<span className="warn-c">{fmtPct(benchCAGR, { signed: true })}</span>} sub="S&P 500" />
        </div>

        {/* Strategy chips + add */}
        <div className="bt-strats-bar">
          <div className="bt-strats-list">
            {strategies.map((s, idx) => {
              const r = results.find(r => r.strategy.id === s.id);
              const isLead = lead?.strategy.id === s.id;
              return (
                <div key={s.id} className={"bt-strat-chip" + (s.on ? " on" : " off") + (isLead ? " lead" : "")} style={{ borderColor: s.on ? s.color : "var(--rule)" }}>
                  <button className="bt-strat-toggle" onClick={() => updateStrategy(s.id, { on: !s.on })} title={s.on ? "active" : "muted"}>
                    <span className="bt-strat-dot" style={{ background: s.on ? s.color : "var(--ink-3)" }}></span>
                  </button>
                  <div className="bt-strat-id">
                    <span className="bt-strat-type">{s.type}</span>
                    <span className="bt-strat-summary mono muted">({STRATEGY_TYPE_MAP[s.type]?.summary(s.params) || ""})</span>
                  </div>
                  {r && (
                    <div className="bt-strat-mini mono">
                      <span className={r.data.cagr >= 0 ? "pos" : "neg"}>{fmtPct(r.data.cagr, { signed: true, decimals: 1 })}</span>
                      <span className="muted">·</span>
                      <span>{r.data.sharpe.toFixed(2)}</span>
                    </div>
                  )}
                  {isLead && <span className="bt-strat-lead mono">LEAD</span>}
                  <button className="bt-strat-x" onClick={() => removeStrategy(s.id)} disabled={strategies.length <= 1} title="remove">×</button>
                </div>
              );
            })}
            <button className="bt-add-btn" onClick={() => setOpenPicker(p => !p)}>
              {openPicker ? "× cancel" : "+ add strategy"}
            </button>
          </div>
          {openPicker && (
            <div className="bt-picker">
              {STRATEGY_TYPES.map(s => (
                <button key={s.type} className="bt-picker-it" onClick={() => addStrategy(s.type)}>
                  <span className="bt-picker-dot" style={{ background: s.color }}></span>
                  <div className="bt-picker-id">
                    <div className="bt-picker-n b">{s.type}</div>
                    <div className="bt-picker-d muted">{s.desc}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Quick controls for the first strategy (preserves original UI) */}
        {quickStrat && (
          <div className="bt-controls">
            <div className="bt-controls-hd mono">QUICK CONTROLS · <span style={{ color: quickStrat.color }}>{quickStrat.type}</span></div>
            <StrategyEditor strategy={quickStrat} onChange={(patch) => updateStrategyParams(quickStrat.id, patch)} />
            <div className="bt-ctl row">
              <label className="bt-ctl-l mono">REBALANCE</label>
              <div className="bt-seg">
                <button className="on">Quarterly</button>
                <button disabled>On filing</button>
              </div>
              <label className="bt-ctl-l mono" style={{ marginLeft: 24 }}>PERIOD</label>
              <span className="mono num" style={{ color: "var(--ink-2)" }}>{Q_LABELS[startQ]} → {Q_LABELS[endQ]}</span>
              <span className="wf-spacer" style={{ flex: 1 }}></span>
              <label className="bt-ctl-l mono">COSTS</label>
              <span className="hf-pill">5 bps · yld reinvest</span>
            </div>
          </div>
        )}

        {/* Equity curves chart */}
        <Section title="Cumulative return (normalized)" sub={`starting $1.00 · rebalanced ${endQ - startQ} times · ${results.length} strategies + benchmark`} pad={false}>
          <LineChart
            series={equitySeries}
            w={1120} h={300}
            padding={{ l: 60, r: 12, t: 16, b: 30 }}
            formatY={v => v.toFixed(2) + "×"}
            formatX={i => Q_LABELS[i + startQ]}
            asPct
          />
        </Section>

        {/* Drawdown chart */}
        <Section title="Drawdown over time" sub="peak-to-trough decline per strategy" pad={false}>
          <LineChart
            series={ddSeries}
            w={1120} h={200}
            padding={{ l: 60, r: 12, t: 16, b: 30 }}
            formatY={v => fmtPct(v, { decimals: 1 })}
            formatX={i => Q_LABELS[i + startQ]}
          />
        </Section>

        {/* Metrics comparison table */}
        <Section title="Metrics comparison" sub="across all active strategies + benchmark · sort by any column">
          <Table
            cols={[
              { key: "lead", label: "★", w: 36, sortable: false, render: r => r._lead ? <span className="mono" style={{ color: "var(--accent)" }}>★</span> : null },
              { key: "color", label: "", w: 16, sortable: false, render: r => <span className="bt-strat-dot" style={{ background: r.color }}></span> },
              { key: "type", label: "STRATEGY", flex: 1.4, render: r => (
                <div className="bt-met-name">
                  <span className="b">{r.type}</span>
                  <span className="muted mono">{r.summary}</span>
                </div>
              ), value: r => r.type },
              { key: "cagr", label: "CAGR", w: 80, align: "right", render: r => <span className={"mono num b " + (r.cagr >= 0 ? "pos" : "neg")}>{fmtPct(r.cagr, { signed: true })}</span>, value: r => r.cagr },
              { key: "alpha", label: "α vs SPX", w: 80, align: "right", render: r => <Delta value={r.alpha} kind="pct" />, value: r => r.alpha },
              { key: "vol", label: "VOL", w: 70, align: "right", render: r => <span className="mono num">{fmtPct(r.vol)}</span>, value: r => r.vol },
              { key: "sharpe", label: "SHARPE", w: 70, align: "right", render: r => <span className="mono num b">{r.sharpe.toFixed(2)}</span>, value: r => r.sharpe },
              { key: "sortino", label: "SORTINO", w: 80, align: "right", render: r => <span className="mono num">{r.sortino.toFixed(2)}</span>, value: r => r.sortino },
              { key: "calmar", label: "CALMAR", w: 70, align: "right", render: r => <span className="mono num">{r.calmar.toFixed(2)}</span>, value: r => r.calmar },
              { key: "maxDD", label: "MAX DD", w: 80, align: "right", render: r => <span className="mono num neg">{fmtPct(r.maxDD)}</span>, value: r => r.maxDD },
              { key: "beta", label: "β", w: 60, align: "right", render: r => <span className="mono num">{r.beta.toFixed(2)}</span>, value: r => r.beta },
              { key: "hit", label: "HIT %", w: 70, align: "right", render: r => <span className="mono num">{fmtPct(r.hitRate, { decimals: 0 })}</span>, value: r => r.hitRate },
              { key: "turn", label: "TURN", w: 70, align: "right", render: r => <span className="mono num">{fmtPct(r.turnover, { decimals: 0 })}</span>, value: r => r.turnover },
            ]}
            rows={[
              ...results.map(r => ({
                _id: r.strategy.id,
                _lead: r.strategy.id === lead?.strategy.id,
                color: r.strategy.color,
                type: r.strategy.type,
                summary: "(" + (STRATEGY_TYPE_MAP[r.strategy.type]?.summary(r.strategy.params) || "") + ")",
                cagr: r.data.cagr,
                alpha: r.data.alpha,
                vol: r.data.vol,
                sharpe: r.data.sharpe,
                sortino: r.data.sortino,
                calmar: r.data.calmar,
                maxDD: r.data.maxDD,
                beta: r.data.beta,
                hitRate: r.data.hitRate,
                turnover: r.data.turnover,
              })),
              {
                _id: "bench",
                _lead: false,
                color: "var(--ink-3)",
                type: "Benchmark",
                summary: "(S&P 500 · avg of tracked tickers)",
                cagr: benchCAGR, alpha: 0, vol: 0,
                sharpe: 0, sortino: 0, calmar: 0,
                maxDD: 0, beta: 1, hitRate: 0.5, turnover: 0,
              },
            ]}
            rowKey={r => r._id}
            initialSort={{ key: "sharpe", dir: "desc" }}
          />
        </Section>

        {/* Lead strategy detail */}
        {lead && (
          <Section
            title={<><span className="bt-lead-tag mono">LEAD STRATEGY</span> <span className="b">{lead.strategy.type}</span> <span className="muted mono">({STRATEGY_TYPE_MAP[lead.strategy.type]?.summary(lead.strategy.params)})</span></>}
            sub="best Sharpe in current selection · click composition tickers to drill"
          >
            <div className="bt-lead-stats">
              <Stat label="CAGR" value={fmtPct(lead.data.cagr, { signed: true })} sub={`+${fmtPct(lead.data.alpha, { decimals: 1 })}p vs SPX`} accent />
              <Stat label="SHARPE" value={lead.data.sharpe.toFixed(2)} sub={`Sortino ${lead.data.sortino.toFixed(2)}`} />
              <Stat label="MAX DD" value={<span className="neg">{fmtPct(lead.data.maxDD)}</span>} sub={`Calmar ${lead.data.calmar.toFixed(2)}`} />
              <Stat label="WIN RATE" value={fmtPct(lead.data.hitRate, { decimals: 0 })} sub={`Total ret ${fmtPct(lead.data.totalRet, { signed: true })}`} />
              <Stat label="BETA · VOL" value={<span className="mono num">{lead.data.beta.toFixed(2)} · {fmtPct(lead.data.vol)}</span>} sub="ann. volatility" />
              <Stat label="TURNOVER" value={fmtPct(lead.data.turnover, { decimals: 0 })} sub="avg / rebal" />
            </div>

            <div className="bt-lead-grid">
              <div>
                <div className="bt-lead-sect-hd mono">QUARTERLY RETURNS</div>
                <BarChart values={lead.data.qrets} w={560} h={120} signed formatY={v => fmtPct(v, { decimals: 1 })} />
                <div className="bt-qrets mono">
                  {lead.data.qrets.map((v, i) => (
                    <div key={i} className="bt-qret"><span className="bt-qret-l">{Q_LABELS[i + 1]}</span><Delta value={v} kind="pct" decimals={1} /></div>
                  ))}
                </div>
              </div>
              <div>
                <div className="bt-lead-sect-hd mono">HOLDINGS PER REBALANCE</div>
                <div className="bt-comp">
                  <div className="bt-comp-head">
                    <div className="bt-comp-q mono">REBAL</div>
                    <div className="bt-comp-h mono">TOP HOLDINGS</div>
                    <div className="bt-comp-r mono">RETURN</div>
                  </div>
                  {lead.data.holdingsLog.map((log, i) => {
                    const next = i + 1 < lead.data.equity.length ? lead.data.equity[i + 1] / lead.data.equity[i] - 1 : 0;
                    return (
                      <div key={i} className="bt-comp-row">
                        <div className="bt-comp-q mono"><span className="b">{Q_LABELS[log.q]}</span><span className="muted"> → {Q_LABELS[log.q + 1]}</span></div>
                        <div className="bt-comp-h">
                          {log.picks.slice(0, 12).map(p => (
                            <button key={p.ticker} className="bt-comp-tk" onClick={() => navigate("/stocks/" + p.ticker)} title={`${p.ticker} · ${fmtPct(p.weight, { decimals: 1 })}`}>
                              {p.ticker}
                            </button>
                          ))}
                          {log.picks.length > 12 && <span className="mono muted bt-comp-more">+{log.picks.length - 12}</span>}
                        </div>
                        <div className="bt-comp-r"><Delta value={next} kind="pct" decimals={2} /></div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </Section>
        )}

        {/* Per-strategy editor — let user fine-tune each */}
        <Section title="Strategy editor" sub="adjust parameters per strategy · changes recompute live">
          <div className="bt-editor-list">
            {strategies.map(s => (
              <div key={s.id} className="bt-editor-card" style={{ borderLeftColor: s.color }}>
                <div className="bt-editor-hd">
                  <span className="bt-strat-dot" style={{ background: s.color }}></span>
                  <span className="b">{s.type}</span>
                  <span className="muted mono">({STRATEGY_TYPE_MAP[s.type]?.summary(s.params)})</span>
                  <span className="wf-spacer" style={{ flex: 1 }}></span>
                  <button className="hf-pill" onClick={() => updateStrategy(s.id, { on: !s.on })}>{s.on ? "active" : "muted"}</button>
                </div>
                <StrategyEditor strategy={s} onChange={(patch) => updateStrategyParams(s.id, patch)} />
              </div>
            ))}
          </div>
        </Section>
      </div>
    </>
  );
}

// ─── StrategyEditor — renders param controls per strategy type ───────────
function StrategyEditor({ strategy, onChange }) {
  const meta = STRATEGY_TYPE_MAP[strategy.type];
  if (!meta) return null;
  return (
    <div className="bt-ctl-list">
      {meta.params.map(p => (
        <ParamEditor key={p.key} param={p} value={strategy.params[p.key]} onChange={(v) => onChange({ [p.key]: v })} />
      ))}
    </div>
  );
}

function ParamEditor({ param, value, onChange }) {
  if (param.kind === "manager") {
    return (
      <div className="bt-ctl row">
        <label className="bt-ctl-l mono">{param.label}</label>
        <div className="bt-ctl-mgrs">
          {MANAGERS.map(m => (
            <button key={m.id} className={"bt-mgr-pick" + (value === m.id ? " on" : "")} onClick={() => onChange(m.id)} style={value === m.id ? { borderColor: m.color, background: m.color + "15" } : {}}>
              <Avatar mgr={m} sz={16} />
              <span>{m.name.split(" ").slice(-1)[0]}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (param.kind === "managerList") {
    const arr = value || [];
    return (
      <div className="bt-ctl row">
        <label className="bt-ctl-l mono">{param.label}</label>
        <div className="bt-ctl-mgrs">
          {MANAGERS.map(m => {
            const on = arr.includes(m.id);
            return (
              <button key={m.id} className={"bt-mgr-pick" + (on ? " on" : "")} onClick={() => onChange(on ? arr.filter(x => x !== m.id) : [...arr, m.id])} style={on ? { borderColor: m.color, background: m.color + "15" } : {}}>
                <Avatar mgr={m} sz={16} />
                <span>{m.name.split(" ").slice(-1)[0]}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }
  if (param.kind === "int") {
    return (
      <div className="bt-ctl row">
        <label className="bt-ctl-l mono">{param.label}</label>
        <div className="bt-step">
          <button onClick={() => onChange(Math.max(param.min, value - 1))}>−</button>
          <span className="mono">{value}</span>
          <button onClick={() => onChange(Math.min(param.max, value + 1))}>+</button>
        </div>
      </div>
    );
  }
  if (param.kind === "enum") {
    return (
      <div className="bt-ctl row">
        <label className="bt-ctl-l mono">{param.label}</label>
        <div className="bt-seg">
          {param.options.map(opt => (
            <button key={opt} className={value === opt ? "on" : ""} onClick={() => onChange(opt)}>{opt}</button>
          ))}
        </div>
      </div>
    );
  }
  if (param.kind === "components") {
    const comps = value || [];
    function updateComp(idx, patch) {
      const next = comps.slice();
      next[idx] = { ...next[idx], ...patch };
      onChange(next);
    }
    function removeComp(idx) {
      onChange(comps.filter((_, i) => i !== idx));
    }
    function addComp() {
      onChange([...comps, { type: "ScoreTopK", params: makeDefaultStrategyParams("ScoreTopK"), weight: 0.2 }]);
    }
    const totalW = comps.reduce((a, b) => a + b.weight, 0);
    return (
      <div className="bt-ctl row" style={{ flexDirection: "column", alignItems: "stretch" }}>
        <label className="bt-ctl-l mono">{param.label} <span className="muted" style={{ marginLeft: 6 }}>(sum {totalW.toFixed(2)})</span></label>
        <div className="bt-comp-editor">
          {comps.map((c, idx) => (
            <div key={idx} className="bt-comp-edit-row">
              <select className="bt-ens-sel" value={c.type} onChange={e => updateComp(idx, { type: e.target.value, params: makeDefaultStrategyParams(e.target.value) })}>
                {STRATEGY_TYPES.filter(s => s.type !== "Ensemble").map(s => <option key={s.type} value={s.type}>{s.type}</option>)}
              </select>
              <span className="muted mono">({STRATEGY_TYPE_MAP[c.type]?.summary(c.params)})</span>
              <span className="wf-spacer" style={{ flex: 1 }}></span>
              <label className="mono muted" style={{ fontSize: 10 }}>weight</label>
              <input type="number" min="0" max="1" step="0.05" className="bt-ens-num mono" value={c.weight} onChange={e => updateComp(idx, { weight: parseFloat(e.target.value) || 0 })} />
              <button className="bt-strat-x" onClick={() => removeComp(idx)} disabled={comps.length <= 1}>×</button>
            </div>
          ))}
          <button className="bt-add-btn" style={{ alignSelf: "flex-start", marginTop: 6 }} onClick={addComp}>+ add component</button>
        </div>
      </div>
    );
  }
  return null;
}

// helper — pick next palette color for new strategy
function nextColor(existing) {
  const palette = ["#1d6dc8", "#0e8a3b", "#7c3aed", "#b45309", "#c8261e", "#0e7490", "#db2777", "#0a0d14"];
  const used = new Set(existing.map(s => s.color));
  for (const c of palette) if (!used.has(c)) return c;
  return palette[existing.length % palette.length];
}

Object.assign(window, { BacktestScreen, StrategyEditor, ParamEditor });
