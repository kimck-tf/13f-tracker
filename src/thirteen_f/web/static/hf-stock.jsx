// 13F Terminal — Stock screens (list + detail)

function StocksListScreen({ quarter, setQuarter }) {
  const rows = useMemo(() => STOCKS.map(s => {
    const holders = tickerHolders(s.t, quarter);
    const pxNow = s.px[quarter];
    const pxPrev = quarter > 0 ? s.px[quarter - 1] : pxNow;
    const ret = (pxNow - pxPrev) / pxPrev;
    const totalShares = holders.reduce((a, b) => a + b.shares, 0);
    const totalValue = totalShares * pxNow;
    return { ...s, holders, pxNow, ret, totalShares, totalValue, nHolders: holders.length };
  }), [quarter]);

  return (
    <>
      <Topbar crumbs={[{ label: "Stocks" }]} quarter={quarter} onQuarter={setQuarter} />
      <div className="hf-pg">
        <Section title="Tracked tickers" sub={`${STOCKS.length} tickers · ${Q_LABELS[quarter]}`}>
          <Table
            cols={[
              { key: "t", label: "TICKER", w: 70, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.t); }}>{r.t}</button>, value: r => r.t },
              { key: "n", label: "COMPANY", flex: 1.2, render: r => <span className="hf-tx">{r.n}</span> },
              { key: "s", label: "SECTOR", w: 100, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.s], borderColor: SECTOR_COLORS[r.s] }}>{r.s}</span> },
              { key: "px", label: "PRICE", w: 80, align: "right", render: r => <span className="mono num">${r.pxNow.toFixed(2)}</span>, value: r => r.pxNow },
              { key: "ret", label: "QoQ %", w: 80, align: "right", render: r => <Delta value={r.ret} />, value: r => r.ret },
              { key: "mc", label: "MKT CAP", w: 90, align: "right", render: r => <span className="mono num">{fmtMoney(r.mc * 1e9, { decimals: 0 })}</span>, value: r => r.mc },
              { key: "nHolders", label: "HOLDERS", w: 80, align: "right", render: r => <span className="mono num b">{r.nHolders}</span> },
              { key: "totalValue", label: "13F VAL", w: 100, align: "right", render: r => <span className="mono num">{fmtMoney(r.totalValue * 1e6)}</span> },
              { key: "spark", label: "12W", w: 100, sortable: false, render: r => <Spark values={r.pxWeekly.slice(-12)} w={90} h={22} fill /> },
            ]}
            rows={rows}
            initialSort={{ key: "nHolders", dir: "desc" }}
            onRowClick={r => navigate("/stocks/" + r.t)}
          />
        </Section>
      </div>
    </>
  );
}

function StockScreen({ ticker, quarter, setQuarter }) {
  const stock = STOCK_MAP[ticker];

  // Phase 5 C3: daily price series lazy-loaded per ticker
  // (kept on the screen for future chart upgrades; falls back to {date:[], close:[]})
  const [pxDaily, setPxDaily] = React.useState({ date: [], close: [] });
  React.useEffect(() => {
    let alive = true;
    fetchDailyPx(ticker).then(d => { if (alive) setPxDaily(d || { date: [], close: [] }); });
    return () => { alive = false; };
  }, [ticker]);

  if (!stock) {
    return (
      <>
        <Topbar crumbs={[{ label: "Stocks", onClick: () => navigate("/stocks") }, { label: ticker }]} />
        <div className="hf-pg"><Section title="Not found"><div className="muted">Ticker '{ticker}' not tracked.</div></Section></div>
      </>
    );
  }

  const holders = useMemo(() => tickerHolders(ticker, quarter), [ticker, quarter]);
  const pxNow = stock.px[quarter];
  const pxPrev = quarter > 0 ? stock.px[quarter - 1] : pxNow;
  const ret = (pxNow - pxPrev) / pxPrev;

  // Per-quarter holder count for trend
  const holdersByQ = QUARTERS.map((_, q) => tickerHolders(ticker, q).length);
  const totalValByQ = QUARTERS.map((_, q) => {
    const hs = tickerHolders(ticker, q);
    return hs.reduce((a, b) => a + b.value, 0);
  });

  // Holders matrix: rows = MANAGERS, cols = quarters, value = weight
  const matrix = MANAGERS.map(m => {
    const series = HOLDINGS[m.id]?.[ticker] || new Array(QUARTERS.length).fill(0);
    const cells = QUARTERS.map((_, q) => {
      const shares = series[q];
      if (shares === 0) return { shares: 0, weight: 0, value: 0 };
      const total = managerTotal(m.id, q);
      const value = positionValue(shares, ticker, q);
      const weight = total > 0 ? value / total : 0;
      return { shares, weight, value };
    });
    return { mgr: m, cells, anyHeld: cells.some(c => c.shares > 0) };
  }).filter(row => row.anyHeld);

  // Price line for full range
  const priceSeries = [{ label: "Price", color: "var(--ink)", values: stock.pxWeekly, width: 1.6 }];

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Stocks", onClick: () => navigate("/stocks") },
          { label: stock.t + " · " + stock.n },
        ]}
        quarter={quarter}
        onQuarter={setQuarter}
      />
      <div className="hf-pg stk">
        {/* Stock header */}
        <div className="stk-h">
          <div className="stk-h-id">
            <div className="stk-h-tk mono">{stock.t}</div>
            <div>
              <div className="stk-h-nm">{stock.n}</div>
              <div className="stk-h-sub muted">
                <span className="hf-pill" style={{ color: SECTOR_COLORS[stock.s], borderColor: SECTOR_COLORS[stock.s] }}>{stock.s}</span>
                <span>{stock.i}</span>
                <span>· MktCap {fmtMoney(stock.mc * 1e9, { decimals: 0 })}</span>
                {stock.yld > 0 && <span>· Yld {stock.yld.toFixed(1)}%</span>}
              </div>
            </div>
          </div>
          <div className="stk-h-px">
            <div className="stk-h-px-v mono">${pxNow.toFixed(2)}</div>
            <div className={"stk-h-px-d mono num " + (ret >= 0 ? "pos" : "neg")}>{fmtPct(ret, { signed: true, decimals: 2 })} QoQ</div>
          </div>
        </div>

        {/* Charts row */}
        <div className="stk-charts">
          <Section title="Price · weekly close" sub="hover for quarter-aligned values" pad={false}>
            <LineChart
              series={priceSeries}
              w={840} h={260}
              padding={{ l: 50, r: 12, t: 12, b: 28 }}
              formatY={v => "$" + v.toFixed(0)}
              formatX={i => {
                const q = Math.floor(i / 8);
                return q < Q_LABELS.length ? Q_LABELS[q] : "";
              }}
            />
          </Section>
          <div className="stk-side">
            <Stat label="Holders this Q" value={holders.length} sub={`of ${MANAGERS.length} tracked`} accent />
            <Stat label="Total 13F value" value={fmtMoney(holders.reduce((a, b) => a + b.value, 0) * 1e6)} />
            <Stat label="Avg conviction" value={fmtPct(holders.reduce((a, b) => a + b.weight, 0) / Math.max(1, holders.length), { decimals: 2 })} sub="avg % of port" />
            <div className="stk-side-trend">
              <div className="stk-side-trend-l mono">HOLDERS 8Q</div>
              <BarChart values={holdersByQ} w={220} h={50} signed={false} colors={holdersByQ.map(_ => "var(--accent)")} />
            </div>
          </div>
        </div>

        {/* Holders matrix */}
        <Section title="Who's holding · 8 quarters" sub="dot size = % of that manager's portfolio · click manager to drill" right={<Pill on>by weight</Pill>}>
          <div className="stk-matrix-w">
            <div className="stk-matrix-head">
              <div className="stk-matrix-mgr">MANAGER</div>
              {Q_LABELS.map((q, i) => (
                <div key={i} className={"stk-matrix-q mono" + (i === quarter ? " on" : "")}>{q}</div>
              ))}
              <div className="stk-matrix-end mono">SUMMARY</div>
            </div>
            {matrix.length === 0 && <div className="stk-matrix-empty muted">No managers in our tracked list hold {stock.t}.</div>}
            {matrix.map(row => {
              const heldCount = row.cells.filter(c => c.shares > 0).length;
              const maxW = Math.max(...row.cells.map(c => c.weight));
              return (
                <div key={row.mgr.id} className="stk-matrix-row">
                  <button className="hf-link mgrcell stk-matrix-mgr" onClick={() => navigate("/managers/" + row.mgr.id)}>
                    <Avatar mgr={row.mgr} sz={20} />
                    <span>{row.mgr.name}</span>
                  </button>
                  {row.cells.map((c, i) => {
                    if (c.shares === 0) return <div key={i} className="stk-matrix-cell"></div>;
                    const sz = 8 + (c.weight / 0.20) * 22;
                    const isCur = i === quarter;
                    return (
                      <div key={i} className={"stk-matrix-cell" + (isCur ? " on" : "")} title={fmtPct(c.weight, { decimals: 2 })}>
                        <div className="stk-matrix-dot" style={{
                          width: Math.min(28, sz), height: Math.min(28, sz),
                          background: row.mgr.color,
                          opacity: 0.55 + Math.min(0.4, c.weight * 3),
                        }}></div>
                        <span className="stk-matrix-cell-lbl mono">{fmtPct(c.weight, { decimals: 1 })}</span>
                      </div>
                    );
                  })}
                  <div className="stk-matrix-end mono num">
                    <div>{heldCount}/8Q</div>
                    <div className="muted">max {fmtPct(maxW, { decimals: 1 })}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>

        {/* Holders ranked */}
        <Section title={`Holders this quarter · ${Q_LABELS[quarter]}`} sub={`${holders.length} of ${MANAGERS.length} super-investors`}>
          <Table
            dense
            cols={[
              { key: "mgr", label: "MANAGER", flex: 1.4, render: r => (
                <button className="hf-link mgrcell" onClick={(e) => { e.stopPropagation(); navigate("/managers/" + r.mgrId); }}>
                  <Avatar mgr={r.mgr} sz={22} />
                  <span className="b">{r.mgr.name}</span>
                  <span className="muted">{r.mgr.firm}</span>
                </button>
              ), value: r => r.mgr.name },
              { key: "shares", label: "SHARES", w: 90, align: "right", render: r => <span className="mono num">{fmtShares(r.shares)}</span>, value: r => r.shares },
              { key: "value", label: "VALUE", w: 90, align: "right", render: r => <span className="mono num">{fmtMoney(r.value * 1e6)}</span>, value: r => r.value },
              { key: "weight", label: "% PORT", w: 80, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 2 })}</span>, value: r => r.weight },
              { key: "bar", label: "", flex: 0.8, sortable: false, render: r => <BarCell value={r.weight} max={Math.max(...holders.map(h => h.weight))} color={r.mgr.color} /> },
              { key: "act", label: "ACT THIS Q", w: 80, render: r => r.action && r.action !== "HOLD" ? <Badge kind={r.action} /> : <span className="muted mono" style={{ fontSize: 10 }}>hold</span>, value: r => r.action || "HOLD" },
              { key: "trend", label: "8Q SIZE", w: 100, sortable: false, render: r => <Spark values={r.series.map((sh, q) => sh * STOCK_MAP[ticker].px[q])} w={90} h={22} fill /> },
            ]}
            rows={holders}
            rowKey={r => r.mgrId}
            initialSort={{ key: "weight", dir: "desc" }}
            onRowClick={r => navigate("/managers/" + r.mgrId)}
          />
        </Section>
      </div>
    </>
  );
}

Object.assign(window, { StocksListScreen, StockScreen });
