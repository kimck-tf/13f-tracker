// 13F Terminal — Backtest screen (backend backtest runs only)

function BacktestScreen({ route, quarter, setQuarter }) {
  // 칩 = 전략 이름별 최신 backend run 하나씩. BACKTESTS는 created_at DESC라 이름별 첫 항목이 최신이다.
  const [strategies, setStrategies] = useState(() => {
    const seen = new Set();
    const list = [];
    for (const r of Array.isArray(BACKTESTS) ? BACKTESTS : []) {
      if (!r || typeof r.name !== "string" || seen.has(r.name)) continue;
      seen.add(r.name);
      if (!Array.isArray(r.equity) || r.equity.length === 0) continue;
      list.push({ id: r.run_id, name: r.name, type: r.name.split("(")[0], color: nextColor(list), on: true, run: r });
    }
    return list;
  });

  const results = useMemo(() => strategies.filter(s => s.on).map(s => {
    const r = s.run;
    const m = r.metrics || {};
    // backend equity·benchEquity는 NAV 금액이라 "시작 $1.00" 차트용으로 이 전략의 초기 NAV로 나눈다
    // (벤치마크도 같은 값으로 나눠 두 곡선의 상대 위치를 유지한다)
    const base = r.equity[0] || 1;
    return {
      strategy: s,
      data: {
        equity: r.equity.map(v => v / base),
        dd: r.dd || [],
        // backend qrets[0]은 첫 분기 자리를 채운 0 — qrets[i] = equity[i] → equity[i+1]로 맞춘다
        qrets: (r.qrets || []).slice(1),
        benchEquity: (r.benchEquity || []).map(v => v / base),
        holdingsLog: backendHoldingsLog(r.holdingsLog),
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
      },
    };
  }), [strategies]);

  // 거래 비용은 첫 run 기준 (backtest --all은 모든 전략을 같은 cost_bps로 돌린다)
  const costBps = strategies[0]?.run.costBps;
  const costLabel = costBps == null ? "—" : String(costBps);

  // Benchmark from first result
  const bench = results[0]?.data.benchEquity || [];

  // Lead strategy — best by Sharpe
  const lead = useMemo(() => {
    if (results.length === 0) return null;
    const ranked = results.slice().sort((a, b) => b.data.sharpe - a.data.sharpe);
    return ranked[0];
  }, [results]);

  const bestCAGR = results.length ? Math.max(...results.map(r => r.data.cagr)) : 0;
  const bestSharpe = results.length ? Math.max(...results.map(r => r.data.sharpe)) : 0;
  const deepestMDD = results.length ? Math.min(...results.map(r => r.data.maxDD)) : 0;
  const benchCAGR = results[0]?.data.benchCagr || 0;

  function toggleStrategy(id) {
    setStrategies(list => list.map(s => s.id === id ? { ...s, on: !s.on } : s));
  }

  const equitySeries = [
    ...results.map(r => ({
      label: r.strategy.name,
      color: r.strategy.color,
      values: r.data.equity,
      width: r.strategy.id === (lead?.strategy.id) ? 2.2 : 1.5,
    })),
    { label: "S&P 500 (SPY)", color: "var(--ink-3)", values: bench, dashed: true, width: 1.2 },
  ];

  const ddSeries = results.map(r => ({
    label: r.strategy.name,
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
          <Stat label="STRATEGIES" value={results.length} sub="backend runs" />
          <Stat label="BEST CAGR" value={<span className="pos">{fmtPct(bestCAGR, { signed: true })}</span>} />
          <Stat label="BEST SHARPE" value={<span className="pos">{bestSharpe.toFixed(2)}</span>} />
          <Stat label="DEEPEST MDD" value={<span className="neg">{fmtPct(deepestMDD)}</span>} />
          <Stat label="BENCH CAGR" value={<span className="warn-c">{fmtPct(benchCAGR, { signed: true })}</span>} sub="S&P 500 (SPY)" />
        </div>

        {/* Strategy chips — one per backend run name, click the dot to mute */}
        <div className="bt-strats-bar">
          <div className="bt-strats-list">
            {strategies.map(s => {
              const r = results.find(r => r.strategy.id === s.id);
              const isLead = lead?.strategy.id === s.id;
              return (
                <div key={s.id} className={"bt-strat-chip" + (s.on ? " on" : " off") + (isLead ? " lead" : "")} style={{ borderColor: s.on ? s.color : "var(--rule)" }} title={STRATEGY_TYPE_MAP[s.type]?.desc || s.name}>
                  <button className="bt-strat-toggle" onClick={() => toggleStrategy(s.id)} title={s.on ? "active" : "muted"}>
                    <span className="bt-strat-dot" style={{ background: s.on ? s.color : "var(--ink-3)" }}></span>
                  </button>
                  <div className="bt-strat-id">
                    <span className="bt-strat-type">{s.name}</span>
                  </div>
                  {r && (
                    <div className="bt-strat-mini mono">
                      <span className={r.data.cagr >= 0 ? "pos" : "neg"}>{fmtPct(r.data.cagr, { signed: true, decimals: 1 })}</span>
                      <span className="muted">·</span>
                      <span>{r.data.sharpe.toFixed(2)}</span>
                    </div>
                  )}
                  {isLead && <span className="bt-strat-lead mono">LEAD</span>}
                </div>
              );
            })}
          </div>
        </div>

        {/* Equity curves chart */}
        <Section title="Cumulative return (normalized)" sub={`starting $1.00 · ${results.length} strategies + benchmark · ${costLabel} bps · backend run`} pad={false}>
          <LineChart
            series={equitySeries}
            w={1120} h={300}
            padding={{ l: 60, r: 12, t: 16, b: 30 }}
            formatY={v => v.toFixed(2) + "×"}
            formatX={i => quarterLabelAt(i)}
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
            formatX={i => quarterLabelAt(i)}
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
                  {r.summary && <span className="muted mono">{r.summary}</span>}
                </div>
              ), value: r => r.type },
              { key: "cagr", label: "CAGR", w: 80, align: "right", render: r => <span className={"mono num b " + (r.cagr >= 0 ? "pos" : "neg")}>{fmtPct(r.cagr, { signed: true })}</span>, value: r => r.cagr },
              { key: "alpha", label: "α vs SPX", w: 80, align: "right", render: r => <Delta value={r.alpha} kind="pct" />, value: r => r.alpha },
              { key: "sharpe", label: "SHARPE", w: 70, align: "right", render: r => <span className="mono num b">{r.sharpe.toFixed(2)}</span>, value: r => r.sharpe },
              { key: "sortino", label: "SORTINO", w: 80, align: "right", render: r => <span className="mono num">{r.sortino.toFixed(2)}</span>, value: r => r.sortino },
              { key: "calmar", label: "CALMAR", w: 70, align: "right", render: r => <span className="mono num">{r.calmar.toFixed(2)}</span>, value: r => r.calmar },
              { key: "maxDD", label: "MAX DD", w: 80, align: "right", render: r => <span className="mono num neg">{fmtPct(r.maxDD)}</span>, value: r => r.maxDD },
              { key: "hit", label: "HIT %", w: 70, align: "right", render: r => <span className="mono num">{fmtPct(r.hitRate, { decimals: 0 })}</span>, value: r => r.hitRate },
            ]}
            rows={[
              ...results.map(r => ({
                _id: r.strategy.id,
                _lead: r.strategy.id === lead?.strategy.id,
                color: r.strategy.color,
                type: r.strategy.name,
                summary: "",
                cagr: r.data.cagr,
                alpha: r.data.alpha,
                sharpe: r.data.sharpe,
                sortino: r.data.sortino,
                calmar: r.data.calmar,
                maxDD: r.data.maxDD,
                hitRate: r.data.hitRate,
              })),
              {
                _id: "bench",
                _lead: false,
                color: "var(--ink-3)",
                type: "Benchmark",
                summary: "(S&P 500 · SPY)",
                cagr: benchCAGR, alpha: 0,
                sharpe: 0, sortino: 0, calmar: 0,
                maxDD: 0, hitRate: 0.5,
              },
            ]}
            rowKey={r => r._id}
            initialSort={{ key: "sharpe", dir: "desc" }}
          />
        </Section>

        {/* Lead strategy detail */}
        {lead && (
          <Section
            title={<><span className="bt-lead-tag mono">LEAD STRATEGY</span> <span className="b">{lead.strategy.name}</span></>}
            sub="best Sharpe in current selection · click composition tickers to drill"
          >
            <div className="bt-lead-stats">
              <Stat label="CAGR" value={fmtPct(lead.data.cagr, { signed: true })} sub={`+${fmtPct(lead.data.alpha, { decimals: 1 })}p vs SPX`} accent />
              <Stat label="SHARPE" value={lead.data.sharpe.toFixed(2)} sub={`Sortino ${lead.data.sortino.toFixed(2)}`} />
              <Stat label="MAX DD" value={<span className="neg">{fmtPct(lead.data.maxDD)}</span>} sub={`Calmar ${lead.data.calmar.toFixed(2)}`} />
              <Stat label="WIN RATE" value={fmtPct(lead.data.hitRate, { decimals: 0 })} sub={`Total ret ${fmtPct(lead.data.totalRet, { signed: true })}`} />
              <Stat label="COST" value={`${costLabel} bp 편도`} sub="backend run" />
            </div>

            <div className="bt-lead-grid">
              <div>
                <div className="bt-lead-sect-hd mono">QUARTERLY RETURNS</div>
                <BarChart values={lead.data.qrets} w={560} h={120} signed formatY={v => fmtPct(v, { decimals: 1 })} />
                <div className="bt-qrets mono">
                  {lead.data.qrets.map((v, i) => (
                    <div key={i} className="bt-qret"><span className="bt-qret-l">{quarterLabelAt(i + 1)}</span><Delta value={v} kind="pct" decimals={1} /></div>
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
                    const next = log.q >= 0 && log.q + 1 < lead.data.equity.length ? lead.data.equity[log.q + 1] / lead.data.equity[log.q] - 1 : 0;
                    return (
                      <div key={i} className="bt-comp-row">
                        <div className="bt-comp-q mono"><span className="b">{quarterLabelAt(log.q)}</span><span className="muted"> → {quarterLabelAt(log.q + 1)}</span></div>
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
      </div>
    </>
  );
}

// helper — pick next palette color for new strategy
function nextColor(existing) {
  const palette = ["#1d6dc8", "#0e8a3b", "#7c3aed", "#b45309", "#c8261e", "#0e7490", "#db2777", "#0a0d14"];
  const used = new Set(existing.map(s => s.color));
  for (const c of palette) if (!used.has(c)) return c;
  return palette[existing.length % palette.length];
}

// helper — backend holdingsLog [{date, holdings}] → 위 렌더링이 쓰는 prototype 형태 [{q, picks}].
// q = 리밸런스일 직전에 끝난 분기의 QUARTERS 인덱스라서 "q → q+1" 구간의 수익률이 equity[q] → equity[q+1]이다.
// backend equity는 분기말마다 한 점이고 QUARTERS[0]과 같은 분기에서 시작한다고 본다 (차트 x축과 같은 가정).
function backendHoldingsLog(log) {
  const base = quarterIndexOf(Q_DATES[0]);
  return (log || []).map(entry => ({ q: quarterIndexOf(entry.date) - 1 - base, picks: entry.holdings || [] }));
}

// helper — QUARTERS[0]부터 k번째 분기의 라벨. 백테스트는 최신 13F 분기 뒤(진행 중인 분기)까지
// 이어지므로 Q_LABELS 범위 밖은 계산해서 같은 형식("Q3'26")으로 만든다.
function quarterLabelAt(k) {
  if (k >= 0 && k < Q_LABELS.length) return Q_LABELS[k];
  const qi = quarterIndexOf(Q_DATES[0]) + k;
  return `Q${qi % 4 + 1}'${String(Math.floor(qi / 4)).slice(-2)}`;
}

// "2024-07-01" → 연도*4 + 분기(0~3)
function quarterIndexOf(isoDate) {
  return Number(isoDate.slice(0, 4)) * 4 + Math.floor((Number(isoDate.slice(5, 7)) - 1) / 3);
}

Object.assign(window, { BacktestScreen });
