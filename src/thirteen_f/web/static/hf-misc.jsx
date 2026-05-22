// 13F Terminal — Ask (scripted chat) + lighter screens (QoQ, Consensus, Builder)

// =============================================================================
// ASK — scripted multi-turn with inline cards
// =============================================================================

const ASK_PROMPTS = [
  { id: "energy",     text: "이번 분기에 에너지 섹터로 자금을 옮긴 매니저는?" },
  { id: "burryEnergy", text: "Burry의 OXY 진입이 다른 매니저들과 일치하나?" },
  { id: "ackmanGoogl", text: "Ackman의 GOOGL 빌드업을 시각화해줘" },
  { id: "followBuffett", text: "Buffett 전략을 백테스트하면?" },
  { id: "crowded",    text: "지금 가장 붐비는 종목 Top 5는?" },
];

function AskScreen({ quarter }) {
  const [thread, setThread] = useState(() => initialThread(quarter));
  const inputRef = useRef(null);

  function send(text) {
    if (!text) return;
    const responses = scriptedReply(text, quarter);
    setThread(t => [
      ...t,
      { role: "user", text, ts: Date.now() },
      ...responses.map(r => ({ role: "bot", ...r, ts: Date.now() + 1 })),
    ]);
    setTimeout(() => {
      document.querySelector(".ask-thread")?.scrollTo({ top: 1e9, behavior: "smooth" });
    }, 50);
  }

  return (
    <>
      <Topbar
        crumbs={[{ label: "Ask" }]}
        right={<Pill on>scripted demo</Pill>}
      />
      <div className="hf-pg ask">
        <div className="ask-shell">
          <div className="ask-thread">
            {thread.map((msg, i) => <AskMessage key={i} msg={msg} quarter={quarter} />)}
          </div>
          <div className="ask-input-area">
            <div className="ask-suggests">
              <div className="ask-suggests-l mono">TRY</div>
              {ASK_PROMPTS.map(p => (
                <button key={p.id} className="ask-suggest" onClick={() => send(p.text)}>{p.text}</button>
              ))}
            </div>
            <form className="ask-input" onSubmit={e => { e.preventDefault(); const v = inputRef.current.value; inputRef.current.value = ""; send(v); }}>
              <input ref={inputRef} className="ask-input-fld" placeholder="ask anything about the tracked filings…" />
              <button type="submit" className="hf-btn primary">↩ Send</button>
            </form>
          </div>
        </div>

        <aside className="ask-side">
          <Section title="Pinned" dense>
            <div className="ask-pinned-empty muted">Pin charts from the conversation to keep them across sessions.</div>
          </Section>
          <Section title="Sources" dense>
            <div className="ask-sources">
              <div className="ask-source"><span className="mono">filings.q1.holdings</span><span className="muted mono">{MANAGERS.length} mgrs</span></div>
              <div className="ask-source"><span className="mono">prices.weekly</span><span className="muted mono">{STOCKS.length} tk · 8Q</span></div>
              <div className="ask-source"><span className="mono">sectors.map</span><span className="muted mono">5 sectors</span></div>
            </div>
          </Section>
        </aside>
      </div>
    </>
  );
}

function initialThread(quarter) {
  return [
    { role: "bot", text: `안녕하세요. ${MANAGERS.length}명의 슈퍼 인베스터, ${STOCKS.length}개 종목, ${QUARTERS.length}분기 데이터를 들고 있어요. ${Q_LABELS[quarter]} 기준 분석을 도와드릴게요.`, ts: 0 },
    { role: "bot", text: "아래 추천 질문을 눌러보시거나 직접 물어봐주세요.", ts: 1 },
  ];
}

function AskMessage({ msg, quarter }) {
  if (msg.role === "user") {
    return (
      <div className="ask-msg user">
        <div className="ask-msg-tag mono">YOU</div>
        <div className="ask-msg-body">{msg.text}</div>
      </div>
    );
  }
  return (
    <div className="ask-msg bot">
      <div className="ask-msg-tag mono">CLAUDE</div>
      <div className="ask-msg-body">
        {msg.text && <div className="ask-msg-text">{msg.text}</div>}
        {msg.card && <AskCard card={msg.card} quarter={quarter} />}
      </div>
    </div>
  );
}

function AskCard({ card, quarter }) {
  if (card.type === "table") {
    return (
      <div className="ask-card">
        <div className="ask-card-hd">
          <span className="mono ask-card-id">{card.id}</span>
          <span className="ask-card-t">{card.title}</span>
          <span className="ask-card-actions">
            <Pill>fork</Pill>
            <Pill>pin</Pill>
          </span>
        </div>
        <Table dense cols={card.cols} rows={card.rows} initialSort={card.sort} onRowClick={card.onRowClick} />
        {card.cite && <div className="ask-card-cite mono">— {card.cite}</div>}
      </div>
    );
  }
  if (card.type === "bar") {
    return (
      <div className="ask-card">
        <div className="ask-card-hd">
          <span className="mono ask-card-id">{card.id}</span>
          <span className="ask-card-t">{card.title}</span>
        </div>
        <BarChart values={card.values} w={620} h={120} signed colors={card.colors} />
        <div className="ask-card-labels mono">
          {card.labels?.map((l, i) => <span key={i}>{l}</span>)}
        </div>
        {card.cite && <div className="ask-card-cite mono">— {card.cite}</div>}
      </div>
    );
  }
  if (card.type === "line") {
    return (
      <div className="ask-card">
        <div className="ask-card-hd">
          <span className="mono ask-card-id">{card.id}</span>
          <span className="ask-card-t">{card.title}</span>
          <span className="ask-card-actions">
            <button className="hf-btn sm" onClick={() => navigate("/backtest", card.btParams || {})}>↗ open in Backtest</button>
          </span>
        </div>
        <LineChart
          series={card.series}
          w={640} h={200}
          padding={{ l: 50, r: 12, t: 12, b: 24 }}
          formatY={card.formatY || (v => v.toFixed(2))}
          formatX={i => Q_LABELS[i] || ""}
        />
        {card.cite && <div className="ask-card-cite mono">— {card.cite}</div>}
      </div>
    );
  }
  return null;
}

function scriptedReply(text, quarter) {
  const t = text.toLowerCase();
  // route by keywords
  if (/buffett.*\b(back|백테)/i.test(text) || t.includes("buffett 전략")) {
    const bt = followStrategyEquity({ mgrId: "buffett", weighting: "equal", topN: 10 });
    return [{
      text: `Buffett의 분기말 Top 10을 등비중 보유하면, 5분기 동안 누적 수익 ${fmtPct(bt.totalRet, { signed: true })}, CAGR ${fmtPct(bt.cagr, { signed: true })}로 시뮬레이션돼요. S&P 500(트래킹 종목 평균) 대비 알파는 ${fmtPct(bt.alpha, { signed: true })}.`,
      card: {
        type: "line",
        id: "bt-buffett-top10",
        title: "Follow Buffett · Top 10 · Equal weight",
        series: [
          { label: "Buffett follow", color: MGR_MAP.buffett.color, values: bt.equity, width: 1.8 },
          { label: "S&P 500 (avg)", color: "var(--ink-3)", values: bt.benchEquity, dashed: true },
        ],
        formatY: v => v.toFixed(2) + "×",
        cite: "computed from filings × prices · open Backtest to tweak",
        btParams: { mgr: "buffett" },
      },
    }, {
      text: "파라미터를 조정해서 더 보고 싶으시면 Backtest로 넘어가세요.",
    }];
  }
  if (t.includes("crowded") || t.includes("붐비") || t.includes("crowded")) {
    const stocks = STOCKS.map(s => {
      const h = tickerHolders(s.t, quarter);
      return { ticker: s.t, stock: s, holders: h, n: h.length, avgW: h.reduce((a, b) => a + b.weight, 0) / Math.max(1, h.length) };
    }).filter(s => s.n >= 2).sort((a, b) => b.n - a.n).slice(0, 5);
    return [{
      text: `${Q_LABELS[quarter]} 기준 가장 많은 매니저가 동시에 보유한 종목 Top 5예요. 평균 비중도 함께 봅니다.`,
      card: {
        type: "table",
        id: "consensus-top5",
        title: "Most-held tickers · " + Q_LABELS[quarter],
        cols: [
          { key: "ticker", label: "TICKER", w: 70, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button> },
          { key: "name", label: "COMPANY", flex: 1, render: r => <span className="hf-tx muted">{r.stock.n}</span> },
          { key: "n", label: "# HOLDERS", w: 90, align: "right", render: r => <span className="mono num b">{r.n}</span> },
          { key: "avgW", label: "AVG %", w: 80, align: "right", render: r => <span className="mono num">{fmtPct(r.avgW, { decimals: 1 })}</span> },
          { key: "stk", label: "STACK", w: 110, sortable: false, render: r => (
            <div className="dash-stacked-av">
              {r.holders.slice(0, 5).map((h, i) => <span key={h.mgrId} style={{ marginLeft: i ? -7 : 0 }}><Avatar mgr={h.mgr} sz={18} /></span>)}
              {r.holders.length > 5 && <span className="mono dash-stacked-more">+{r.holders.length - 5}</span>}
            </div>
          ) },
        ],
        rows: stocks,
        sort: { key: "n", dir: "desc" },
        onRowClick: r => navigate("/stocks/" + r.ticker),
        cite: "tickerHolders × " + STOCKS.length + " · live",
      },
    }];
  }
  if (t.includes("oxy") || (t.includes("burry") && t.includes("energy")) || (t.includes("burry") && t.includes("일치"))) {
    const holders = tickerHolders("OXY", quarter);
    const series = QUARTERS.map((_, q) => tickerHolders("OXY", q).length);
    return [{
      text: `OXY는 ${Q_LABELS[quarter]} 현재 ${holders.length}명의 매니저가 보유 중이에요. Burry가 ${Q_LABELS[6]}에 신규 진입한 직후 ${Q_LABELS[7]}에 Druckenmiller, Klarman이 합류하는 패턴을 보입니다.`,
      card: {
        type: "bar",
        id: "oxy-holders-q",
        title: "OXY · # of holders by quarter",
        values: series,
        labels: Q_LABELS,
        colors: series.map((_, i) => i === quarter ? "var(--accent)" : "var(--ink-3)"),
      },
    }, {
      text: "OXY 상세 페이지에서 매니저별 진입 시점까지 확인할 수 있어요.",
      card: {
        type: "table",
        id: "oxy-holders",
        title: "Current OXY holders · " + Q_LABELS[quarter],
        cols: [
          { key: "mgr", label: "MANAGER", flex: 1, render: r => <button className="hf-link mgrcell" onClick={(e) => { e.stopPropagation(); navigate("/managers/" + r.mgrId); }}><Avatar mgr={r.mgr} sz={18} /> {r.mgr.name}</button> },
          { key: "shares", label: "SHARES", w: 90, align: "right", render: r => <span className="mono num">{fmtShares(r.shares)}</span> },
          { key: "weight", label: "% PORT", w: 80, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 2 })}</span> },
          { key: "act", label: "ACT", w: 60, render: r => r.action && r.action !== "HOLD" ? <Badge kind={r.action} /> : <span className="muted mono" style={{ fontSize: 10 }}>hold</span> },
        ],
        rows: holders,
      },
    }];
  }
  if (t.includes("ackman") && (t.includes("googl") || t.includes("google"))) {
    const series = QUARTERS.map((_, q) => {
      const h = HOLDINGS.ackman.GOOGL?.[q] || 0;
      const total = managerTotal("ackman", q);
      if (total === 0) return 0;
      return positionValue(h, "GOOGL", q) / total;
    });
    return [{
      text: `Ackman은 ${Q_LABELS[3]}에 GOOGL을 신규 진입해서 4분기 연속 add 중이에요. ${Q_LABELS[quarter]} 현재 ${fmtPct(series[quarter], { decimals: 1 })} 비중까지 키웠습니다.`,
      card: {
        type: "line",
        id: "ackman-googl-buildup",
        title: "Ackman · GOOGL portfolio weight",
        series: [{
          label: "% of port",
          color: MGR_MAP.ackman.color,
          values: series,
          width: 1.8,
          fill: true,
        }],
        formatY: v => fmtPct(v, { decimals: 1 }),
        cite: "managerPortfolio · ackman · 8 quarters",
      },
    }];
  }
  if (t.includes("energy") || t.includes("에너지")) {
    // Find managers who added/opened energy positions this quarter
    const acts = quarterActivity(quarter).filter(a => a.stock.s === "Energy");
    const positive = acts.filter(a => a.action === "NEW" || a.action === "ADD");
    return [{
      text: `${Q_LABELS[quarter]}에 에너지 섹터를 늘린 매니저는 ${new Set(positive.map(p => p.mgrId)).size}명, 총 ${positive.length}건의 매수성 액션이에요.`,
      card: {
        type: "table",
        id: "energy-flow-q",
        title: "Energy sector — buy actions · " + Q_LABELS[quarter],
        cols: [
          { key: "mgr", label: "MANAGER", flex: 1, render: r => <button className="hf-link mgrcell" onClick={(e) => { e.stopPropagation(); navigate("/managers/" + r.mgrId); }}><Avatar mgr={r.mgr} sz={18} /> {r.mgr.name}</button> },
          { key: "tk", label: "TICKER", w: 70, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button> },
          { key: "act", label: "ACT", w: 60, render: r => <Badge kind={r.action} /> },
          { key: "w", label: "TO %", w: 70, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 2 })}</span> },
          { key: "dv", label: "Δ VALUE", w: 90, align: "right", render: r => <Delta value={r.deltaValue * 1e6} kind="money" /> },
        ],
        rows: positive,
        cite: "quarterActivity · sector=Energy",
      },
    }, {
      text: "OXY, CVX, EOG 세 종목에 집중적으로 자금이 들어왔어요. Backtest에서 'energy basket' 전략으로 검증해보고 싶으시면 알려주세요.",
    }];
  }
  // fallback
  return [{
    text: "음, 그 질문은 아직 시나리오에 없네요. 추천 질문 중 하나를 눌러보시거나 더 구체적으로 적어주세요. (실제 LLM 연동은 다음 라운드에)",
  }];
}

// =============================================================================
// QoQ — quarter-over-quarter changes (lighter version)
// =============================================================================

function QoQScreen({ quarter, setQuarter }) {
  const acts = quarterActivity(quarter);
  const [actFilter, setActFilter] = useState("all");
  const filtered = acts.filter(a => {
    if (actFilter === "all") return true;
    if (actFilter === "buy") return a.action === "NEW" || a.action === "ADD";
    if (actFilter === "sell") return a.action === "CUT" || a.action === "EXIT";
    return a.action === actFilter;
  });

  return (
    <>
      <Topbar crumbs={[{ label: "Changes" }]} quarter={quarter} onQuarter={setQuarter} />
      <div className="hf-pg">
        <Section title={`Q-over-Q changes — ${Q_LABELS[quarter]}`} sub={`${acts.length} actions across ${new Set(acts.map(a => a.mgrId)).size} managers`}>
          <div className="hf-chips">
            {[
              { id: "all", label: "All · " + acts.length },
              { id: "NEW", label: "NEW · " + acts.filter(a => a.action === "NEW").length },
              { id: "ADD", label: "ADD · " + acts.filter(a => a.action === "ADD").length },
              { id: "CUT", label: "CUT · " + acts.filter(a => a.action === "CUT").length },
              { id: "EXIT", label: "EXIT · " + acts.filter(a => a.action === "EXIT").length },
              { id: "buy", label: "🠕 Buy-side" },
              { id: "sell", label: "🠗 Sell-side" },
            ].map(c => (
              <Pill key={c.id} on={actFilter === c.id} onClick={() => setActFilter(c.id)}>{c.label}</Pill>
            ))}
          </div>
          <Table
            dense
            cols={[
              { key: "act", label: "ACT", w: 50, render: r => <Badge kind={r.action} />, value: r => r.action },
              { key: "tk", label: "TICKER", w: 70, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.2, render: r => <span className="hf-tx muted">{r.stock.n}</span> },
              { key: "sec", label: "SECTOR", w: 90, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.stock.s], borderColor: SECTOR_COLORS[r.stock.s] }}>{r.stock.s}</span>, value: r => r.stock.s },
              { key: "mgr", label: "MANAGER", flex: 1, render: r => <button className="hf-link mgrcell" onClick={(e) => { e.stopPropagation(); navigate("/managers/" + r.mgrId); }}><Avatar mgr={r.mgr} sz={18} /> {r.mgr.name}</button>, value: r => r.mgr.name },
              { key: "w", label: "TO %", w: 70, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 2 })}</span>, value: r => r.weight },
              { key: "dw", label: "Δ %PT", w: 70, align: "right", render: r => <Delta value={r.deltaWeight} kind="pct" decimals={2} />, value: r => r.deltaWeight },
              { key: "dv", label: "Δ VALUE", w: 90, align: "right", render: r => <Delta value={r.deltaValue * 1e6} kind="money" decimals={1} />, value: r => r.deltaValue },
            ]}
            rows={filtered}
            initialSort={{ key: "dv", dir: "desc" }}
            striped
          />
        </Section>
      </div>
    </>
  );
}

// =============================================================================
// CONSENSUS — ranked crowded trades
// =============================================================================

function ConsensusScreen({ quarter, setQuarter }) {
  const rows = useMemo(() => STOCKS.map(s => {
    const holders = tickerHolders(s.t, quarter);
    return { ticker: s.t, stock: s, holders, n: holders.length, avgW: holders.reduce((a, b) => a + b.weight, 0) / Math.max(1, holders.length) };
  }).filter(r => r.n >= 1).sort((a, b) => b.n - a.n), [quarter]);

  return (
    <>
      <Topbar crumbs={[{ label: "Consensus" }]} quarter={quarter} onQuarter={setQuarter} />
      <div className="hf-pg">
        <Section title="Crowded trades" sub={`ranked by # of super-investors holding · ${Q_LABELS[quarter]}`}>
          <Table
            cols={[
              { key: "rank", label: "#", w: 40, render: (r, i) => <span className="mono muted">{i + 1}</span>, sortable: false },
              { key: "ticker", label: "TICKER", w: 80, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.4, render: r => <span className="hf-tx">{r.stock.n}</span> },
              { key: "sec", label: "SECTOR", w: 100, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.stock.s], borderColor: SECTOR_COLORS[r.stock.s] }}>{r.stock.s}</span> },
              { key: "stk", label: "HOLDERS", w: 160, sortable: false, render: r => (
                <div className="dash-stacked-av">
                  {r.holders.slice(0, 6).map((h, i) => <span key={h.mgrId} style={{ marginLeft: i ? -7 : 0 }}><Avatar mgr={h.mgr} sz={20} /></span>)}
                  {r.holders.length > 6 && <span className="mono dash-stacked-more">+{r.holders.length - 6}</span>}
                </div>
              ) },
              { key: "n", label: "#", w: 50, align: "right", render: r => <span className="mono num b">{r.n}</span>, value: r => r.n },
              { key: "avgW", label: "AVG %", w: 80, align: "right", render: r => <span className="mono num">{fmtPct(r.avgW, { decimals: 1 })}</span>, value: r => r.avgW },
              { key: "bar", label: "", flex: 0.8, sortable: false, render: r => <BarCell value={r.n} max={Math.max(...rows.map(x => x.n))} color="var(--accent)" /> },
              { key: "spark", label: "PRICE 12W", w: 110, sortable: false, render: r => <Spark values={r.stock.pxWeekly.slice(-12)} w={100} h={24} fill /> },
            ]}
            rows={rows}
            initialSort={{ key: "n", dir: "desc" }}
            onRowClick={r => navigate("/stocks/" + r.ticker)}
          />
        </Section>
      </div>
    </>
  );
}

// =============================================================================
// BUILDER — quick filter chips → preview
// =============================================================================

function BuilderScreen({ quarter, setQuarter }) {
  const [filters, setFilters] = useState({
    actions: ["NEW", "ADD"],
    minHolders: 2,
    minWeight: 0.02,
    sectors: [],
    topN: 25,
  });
  const F = filters;

  const results = useMemo(() => {
    const acts = quarterActivity(quarter);
    const byTicker = {};
    for (const a of acts) {
      if (!F.actions.includes(a.action)) continue;
      if (a.weight < F.minWeight) continue;
      if (F.sectors.length > 0 && !F.sectors.includes(a.stock.s)) continue;
      if (!byTicker[a.ticker]) byTicker[a.ticker] = { ticker: a.ticker, stock: a.stock, mgrs: [], avgDw: 0 };
      byTicker[a.ticker].mgrs.push(a);
    }
    return Object.values(byTicker)
      .filter(r => r.mgrs.length >= F.minHolders)
      .map(r => ({
        ...r,
        n: r.mgrs.length,
        avgWeight: r.mgrs.reduce((a, b) => a + b.weight, 0) / r.mgrs.length,
        sumDeltaValue: r.mgrs.reduce((a, b) => a + b.deltaValue, 0),
      }))
      .sort((a, b) => b.sumDeltaValue - a.sumDeltaValue)
      .slice(0, F.topN);
  }, [filters, quarter]);

  // Quick estimate equity if you bought this basket equal-weight, held to quarter+1
  const estReturn = useMemo(() => {
    if (results.length === 0 || quarter >= QUARTERS.length - 1) return null;
    let r = 0;
    for (const it of results) {
      r += (it.stock.px[quarter + 1] - it.stock.px[quarter]) / it.stock.px[quarter];
    }
    return r / results.length;
  }, [results, quarter]);

  return (
    <>
      <Topbar crumbs={[{ label: "Builder" }]} quarter={quarter} onQuarter={setQuarter} />
      <div className="hf-pg bld">
        <Section title="Quick strategy" sub="filter → see basket → backtest" right={<button className="hf-btn primary" onClick={() => navigate("/backtest")}>▶ Open in Backtest</button>}>
          <div className="bld-flt-rows">
            <div className="bld-flt-row">
              <label className="bld-flt-l mono">ACTION</label>
              {["NEW", "ADD", "CUT", "EXIT"].map(a => (
                <Pill key={a} on={F.actions.includes(a)} onClick={() => setFilters(f => ({ ...f, actions: f.actions.includes(a) ? f.actions.filter(x => x !== a) : [...f.actions, a] }))}>{a}</Pill>
              ))}
            </div>
            <div className="bld-flt-row">
              <label className="bld-flt-l mono">SECTOR</label>
              {Object.keys(SECTOR_COLORS).map(s => (
                <Pill key={s} on={F.sectors.includes(s)} onClick={() => setFilters(f => ({ ...f, sectors: f.sectors.includes(s) ? f.sectors.filter(x => x !== s) : [...f.sectors, s] }))}>{s}</Pill>
              ))}
              {F.sectors.length === 0 && <span className="muted hf-tx" style={{ marginLeft: 8 }}>(all)</span>}
            </div>
            <div className="bld-flt-row">
              <label className="bld-flt-l mono">MIN HOLDERS</label>
              <div className="bt-step"><button onClick={() => setFilters(f => ({ ...f, minHolders: Math.max(1, f.minHolders - 1) }))}>−</button><span className="mono">{F.minHolders}</span><button onClick={() => setFilters(f => ({ ...f, minHolders: f.minHolders + 1 }))}>+</button></div>
              <label className="bld-flt-l mono" style={{ marginLeft: 20 }}>MIN WEIGHT</label>
              <div className="bt-step"><button onClick={() => setFilters(f => ({ ...f, minWeight: Math.max(0, +(f.minWeight - 0.005).toFixed(3)) }))}>−</button><span className="mono">{fmtPct(F.minWeight, { decimals: 1 })}</span><button onClick={() => setFilters(f => ({ ...f, minWeight: +(f.minWeight + 0.005).toFixed(3) }))}>+</button></div>
              <label className="bld-flt-l mono" style={{ marginLeft: 20 }}>TOP N</label>
              <div className="bt-step"><button onClick={() => setFilters(f => ({ ...f, topN: Math.max(5, f.topN - 5) }))}>−</button><span className="mono">{F.topN}</span><button onClick={() => setFilters(f => ({ ...f, topN: f.topN + 5 }))}>+</button></div>
            </div>
          </div>

          <div className="bld-result">
            <div className="bld-result-l">
              <div className="bld-result-stat"><div className="bld-result-stat-l">MATCHES</div><div className="mono num b" style={{ fontSize: 22 }}>{results.length}</div></div>
              <div className="bld-result-stat"><div className="bld-result-stat-l">EST. NEXT-Q RET</div><div className="mono num b" style={{ fontSize: 22 }}>{estReturn != null ? <Delta value={estReturn} kind="pct" decimals={2} bold /> : "—"}</div></div>
              <div className="bld-result-stat"><div className="bld-result-stat-l">UNIQUE MGRS</div><div className="mono num b" style={{ fontSize: 22 }}>{new Set(results.flatMap(r => r.mgrs.map(m => m.mgrId))).size}</div></div>
            </div>
          </div>
        </Section>

        <Section title="Basket preview" sub="tickers matching your filters">
          <Table
            dense
            cols={[
              { key: "tk", label: "TICKER", w: 70, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.2, render: r => <span className="hf-tx muted">{r.stock.n}</span> },
              { key: "sec", label: "SECTOR", w: 100, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.stock.s], borderColor: SECTOR_COLORS[r.stock.s] }}>{r.stock.s}</span> },
              { key: "n", label: "MGRS", w: 60, align: "right", render: r => <span className="mono num b">{r.n}</span>, value: r => r.n },
              { key: "stk", label: "HOLDERS", w: 140, sortable: false, render: r => (
                <div className="dash-stacked-av">
                  {r.mgrs.slice(0, 5).map((h, i) => <span key={h.mgrId} style={{ marginLeft: i ? -7 : 0 }}><Avatar mgr={h.mgr} sz={18} /></span>)}
                  {r.mgrs.length > 5 && <span className="mono dash-stacked-more">+{r.mgrs.length - 5}</span>}
                </div>
              ) },
              { key: "avgW", label: "AVG %", w: 80, align: "right", render: r => <span className="mono num">{fmtPct(r.avgWeight, { decimals: 1 })}</span>, value: r => r.avgWeight },
              { key: "sumDv", label: "SUM ΔV", w: 90, align: "right", render: r => <Delta value={r.sumDeltaValue * 1e6} kind="money" />, value: r => r.sumDeltaValue },
              { key: "spark", label: "12W", w: 90, sortable: false, render: r => <Spark values={r.stock.pxWeekly.slice(-12)} w={80} h={20} fill /> },
            ]}
            rows={results}
            initialSort={{ key: "sumDv", dir: "desc" }}
            onRowClick={r => navigate("/stocks/" + r.ticker)}
          />
        </Section>
      </div>
    </>
  );
}

Object.assign(window, { AskScreen, AskCard, scriptedReply, QoQScreen, ConsensusScreen, BuilderScreen });
