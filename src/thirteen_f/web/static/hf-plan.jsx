// 13F Terminal — Plan screen: 백테스트 비교 → 권장 전략 → 지금의 실행 계획.
// 데이터는 exporter.export_targets가 만든 targets.json (backend가 계산, 여기서는 표시만).

function PlanScreen({ route }) {
  const data = TARGETS;
  const strategies = data && Array.isArray(data.strategies) ? data.strategies : [];
  const [selectedName, setSelectedName] = useState(
    route.params.strategy || (data && data.recommended) || (strategies[0] && strategies[0].name)
  );
  const selected = strategies.find(s => s.name === selectedName) || strategies[0];

  if (!selected) {
    return (
      <>
        <Topbar crumbs={[{ label: "Plan" }]} />
        <div className="hf-pg plan">
          <Section title="실행 계획" sub="targets.json이 없습니다">
            <div className="plan-note">
              <span className="mono">uv run thirteen-f backtest --all</span> 후 <span className="mono">uv run thirteen-f export</span>를 실행하면 이 화면이 채워집니다.
            </div>
          </Section>
        </div>
      </>
    );
  }

  const ranked = strategies.slice().sort((a, b) => (b.metrics?.calmar ?? -Infinity) - (a.metrics?.calmar ?? -Infinity));
  const buys = selected.positions.filter(p => p.action === "buy");
  const periodLabel = (() => {
    const i = Q_DATES.indexOf(selected.period);
    return i >= 0 ? Q_LABELS[i] : selected.period || "—";
  })();
  const tickers = new Set(selected.positions.map(p => p.ticker));
  const etfs = selected.positions.filter(p => p.isEtf);
  const alphabet = ["GOOG", "GOOGL"].filter(t => tickers.has(t));
  const alphabetWeight = selected.positions.filter(p => alphabet.includes(p.ticker)).reduce((a, p) => a + p.weight, 0);

  const holdersCell = (p) => (
    <div className="dash-stacked-av">
      {(p.holderIds || []).slice(0, 5).map((id, i) => MGR_MAP[id] && (
        <span key={id} style={{ marginLeft: i ? -7 : 0 }} title={MGR_MAP[id].name}><Avatar mgr={MGR_MAP[id]} sz={20} /></span>
      ))}
      <span className="mono num b" style={{ marginLeft: 6 }}>{p.holders ?? "—"}</span>
    </div>
  );
  const sectorPill = (s) => s ? <span className="hf-pill" style={{ borderColor: SECTOR_COLORS[s], color: SECTOR_COLORS[s] }}>{s}</span> : <span className="muted">—</span>;

  return (
    <>
      <Topbar crumbs={[{ label: "Plan" }]} right={<span className="mono muted">as of {data.as_of}</span>} />
      <div className="hf-pg plan">
        {/* 1. 알고리즘 선정 */}
        <Section
          title="알고리즘 선정"
          sub={`기본 전략 ${strategies.length}개의 최신 백테스트 · 권장 기준: ${data.rule}`}
          right={<button className="hf-link mono" onClick={() => navigate("/backtest")}>수익 곡선 보기 →</button>}
        >
          <Table
            dense
            initialSort={{ key: "calmar", dir: "desc" }}
            rows={ranked}
            rowKey={r => r.name}
            onRowClick={r => setSelectedName(r.name)}
            cols={[
              { key: "rec", label: "", w: 52, sortable: false, render: r => (
                <span>
                  {r.name === data.recommended && <span className="plan-rec mono">권장</span>}
                  {r.name === selected.name && <span className="plan-sel mono">▶</span>}
                </span>
              ) },
              { key: "name", label: "STRATEGY", flex: 1.6, render: r => <span className={"hf-tx" + (r.name === selected.name ? " b" : "")}>{r.name}</span>, value: r => r.name },
              { key: "cagr", label: "CAGR", w: 80, align: "right", render: r => r.metrics ? <span className={"mono num b " + (r.metrics.cagr >= 0 ? "pos" : "neg")}>{fmtPct(r.metrics.cagr, { signed: true })}</span> : <span className="muted">—</span>, value: r => r.metrics?.cagr ?? -Infinity },
              { key: "mdd", label: "MDD", w: 80, align: "right", render: r => r.metrics ? <span className="mono num neg">{fmtPct(r.metrics.maxDD)}</span> : <span className="muted">—</span>, value: r => r.metrics?.maxDD ?? Infinity },
              { key: "calmar", label: "CALMAR", w: 80, align: "right", render: r => r.metrics ? <span className="mono num b">{r.metrics.calmar.toFixed(2)}</span> : <span className="muted">—</span>, value: r => r.metrics?.calmar ?? -Infinity },
              { key: "sharpe", label: "SHARPE", w: 80, align: "right", render: r => r.metrics ? <span className="mono num">{r.metrics.sharpe.toFixed(2)}</span> : <span className="muted">—</span>, value: r => r.metrics?.sharpe ?? -Infinity },
              { key: "alpha", label: "α vs SPY", w: 90, align: "right", render: r => r.metrics ? <Delta value={r.metrics.cagr - r.metrics.benchCagr} kind="pct" /> : <span className="muted">—</span>, value: r => r.metrics ? r.metrics.cagr - r.metrics.benchCagr : -Infinity },
              { key: "pos", label: "AVG POS", w: 80, align: "right", render: r => r.metrics ? <span className="mono num">{r.metrics.avgPositions.toFixed(1)}</span> : <span className="muted">—</span>, value: r => r.metrics?.avgPositions ?? 0 },
            ]}
          />
        </Section>

        {/* 2. 전략 선택 + 실행 계획 요약 */}
        <div className="plan-chips">
          {strategies.map(s => (
            <Pill key={s.name} on={s.name === selected.name} onClick={() => setSelectedName(s.name)}>
              {s.name === data.recommended ? "★ " : ""}{s.type === "SingleManagerClone" ? s.name : s.type}
            </Pill>
          ))}
        </div>
        <div className="dash-kpis">
          <Stat label="DATA QUARTER" value={periodLabel} sub={selected.public_since ? `공개 ${selected.public_since}` : "13F 없음"} />
          <Stat label="NEXT REBALANCE" value={selected.next_rebalance || "—"} sub="분기말 + 45일 (예상)" accent />
          <Stat label="TARGET NAMES" value={selected.positions.length} sub="동일가중 목표" />
          <Stat label="BUY" value={buys.length} sub="직전 목록에 없던 종목" />
          <Stat label="KEEP" value={selected.positions.length - buys.length} sub="직전 목록에도 있던 종목" />
          <Stat label="SELL" value={selected.sells.length} sub="직전 목록에서 빠진 종목" />
        </div>

        {/* 3. 목표 비중 */}
        <Section
          title={<><span className="bt-lead-tag mono">EXECUTION PLAN</span> <span className="b">{selected.name}</span></>}
          sub={selected.public_since ? `${periodLabel} 13F가 모두 공개된 ${selected.public_since}부터 유효한 목록 · 다음 교체는 ${selected.next_rebalance} 무렵` : "쓸 수 있는 13F가 없어 전액 현금"}
        >
          <Table
            dense
            rows={selected.positions}
            rowKey={r => r.ticker}
            cols={[
              { key: "action", label: "ACTION", w: 70, render: r => <Badge kind={r.action === "buy" ? "NEW" : "HOLD"}>{r.action === "buy" ? "BUY" : "KEEP"}</Badge>, value: r => r.action },
              { key: "ticker", label: "TICKER", w: 90, render: r => <span><button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>{r.isEtf && <span className="hf-badge sm plan-etf">ETF</span>}</span>, value: r => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.4, render: r => <span className="hf-tx">{r.name || "—"}</span>, value: r => r.name },
              { key: "sector", label: "SECTOR", w: 130, render: r => sectorPill(r.sector), value: r => r.sector },
              { key: "weight", label: "TARGET %", w: 90, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 1 })}</span>, value: r => r.weight },
              { key: "prev", label: "PREV %", w: 80, align: "right", render: r => <span className="mono num muted">{r.prevWeight != null ? fmtPct(r.prevWeight, { decimals: 1 }) : "—"}</span>, value: r => r.prevWeight ?? 0 },
              { key: "holders", label: "HOLDERS", w: 170, render: holdersCell, value: r => r.holders ?? 0 },
              { key: "px", label: "LAST CLOSE", w: 100, align: "right", render: r => <span className="mono num" title={r.lastCloseDate || ""}>{r.lastClose != null ? "$" + r.lastClose.toFixed(2) : "—"}</span>, value: r => r.lastClose ?? 0 },
            ]}
          />
          {selected.sells.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="bt-lead-sect-hd mono">SELL — 직전 목록에서 빠진 종목</div>
              <Table
                dense
                rows={selected.sells}
                rowKey={r => r.ticker}
                cols={[
                  { key: "action", label: "ACTION", w: 70, sortable: false, render: () => <Badge kind="EXIT">SELL</Badge> },
                  { key: "ticker", label: "TICKER", w: 90, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
                  { key: "name", label: "COMPANY", flex: 1.4, render: r => <span className="hf-tx">{r.name || "—"}</span>, value: r => r.name },
                  { key: "prev", label: "PREV %", w: 80, align: "right", render: r => <span className="mono num">{fmtPct(r.prevWeight, { decimals: 1 })}</span>, value: r => r.prevWeight },
                  { key: "px", label: "LAST CLOSE", w: 100, align: "right", render: r => <span className="mono num">{r.lastClose != null ? "$" + r.lastClose.toFixed(2) : "—"}</span>, value: r => r.lastClose ?? 0 },
                ]}
              />
            </div>
          )}
        </Section>

        {/* 4. 주의사항 */}
        <Section title="실행 전 확인" sub="이 화면은 백테스트 규칙의 기계적 출력이며 투자 권유가 아닙니다" dense>
          <ul className="plan-note">
            {alphabet.length === 2 && (
              <li><span className="plan-warn">GOOG·GOOGL은 같은 회사(Alphabet)</span>입니다 — 규칙대로면 합계 {fmtPct(alphabetWeight, { decimals: 0 })}. 한 종목으로 합칠지 정하세요.</li>
            )}
            {etfs.length > 0 && (
              <li><span className="plan-warn">ETF가 종목으로 들어 있습니다: {etfs.map(p => p.ticker).join(", ")}</span> — 거장이 13F에 담은 지수 상품이라 그대로 두면 지수를 {fmtPct(etfs.reduce((a, p) => a + p.weight, 0), { decimals: 0 })} 편입하는 셈입니다.</li>
            )}
            <li>목록은 그 분기 13F를 추적 매니저 전원이 제출한 날(보통 2·5·8·11월 중순)에만 바뀝니다. 그 사이에는 매매할 일이 없고, 교체 시 <b>SELL 목록 매도 → BUY 목록 매수 → 전 종목 동일 비중</b>으로 맞춥니다.</li>
            <li>백테스트는 2024-05 이후 분기 신호 10번짜리 표본이고 편도 10bp 비용만 가정했습니다(슬리피지·세금 없음). 표의 수치를 기대 수익으로 읽지 마세요. 근거와 한계는 <span className="mono">docs/backtest-optimization-2026-09.md</span>.</li>
            <li>같은 목록을 터미널에서 보려면 <span className="mono">uv run thirteen-f targets --strategy {selected.type}</span>.</li>
          </ul>
        </Section>
      </div>
    </>
  );
}

Object.assign(window, { PlanScreen });
