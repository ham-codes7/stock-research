import { useState, useEffect, useRef, useCallback } from "react";

const BASE_URL = "http://localhost:8000";

const TOOL_META = {
  get_price_and_metrics: { label: "Price & Metrics", icon: "ti-chart-line", short: "tool_01_price" },
  get_recent_news: { label: "Recent News", icon: "ti-news", short: "tool_02_news" },
  sentiment_score: { label: "Sentiment Score", icon: "ti-mood-smile", short: "tool_03_sentiment" },
  get_financials_history: { label: "Financials History", icon: "ti-report-money", short: "tool_04_financials" },
  get_peer_comparison: { label: "Peer Comparison", icon: "ti-chart-bar", short: "tool_05_peers" },
  get_sec_filing_summary: { label: "SEC Filing", icon: "ti-file-text", short: "tool_06_sec" },
  get_earnings_call_transcript: { label: "Earnings Call", icon: "ti-microphone", short: "tool_07_transcript" },
};

const TOOL_ORDER = Object.keys(TOOL_META);

function ConfidenceRing({ score, label, size = 64 }) {
  const r = (size / 2) - 6;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(100, Math.max(0, score ?? 0));
  const dash = (pct / 100) * circ;
  const color = pct >= 80 ? "#1D9E75" : pct >= 60 ? "#EF9F27" : "#E24B4A";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-border-tertiary)" strokeWidth={5} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={5}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
      </svg>
      <span style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: -size - 2, lineHeight: `${size}px`, fontWeight: 500 }}>
        {pct}
      </span>
      <span style={{ fontSize: 10, color: "var(--color-text-tertiary)", textAlign: "center", maxWidth: 72, lineHeight: 1.3 }}>{label}</span>
    </div>
  );
}

function ConfidenceBar({ toolKey, score }) {
  const pct = Math.min(100, Math.max(0, score ?? 0));
  const color = pct >= 80 ? "#1D9E75" : pct >= 60 ? "#EF9F27" : "#E24B4A";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <span style={{ fontSize: 12, color: "var(--color-text-secondary)", width: 130, flexShrink: 0 }}>{toolKey}</span>
      <div style={{ flex: 1, height: 6, background: "var(--color-border-tertiary)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.8s ease" }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 500, color, width: 32, textAlign: "right" }}>{pct}</span>
    </div>
  );
}

function StatusBadge({ label, type = "neutral" }) {
  const colors = {
    bullish: { bg: "#EAF3DE", text: "#3B6D11" },
    bearish: { bg: "#FCEBEB", text: "#A32D2D" },
    neutral: { bg: "var(--color-background-secondary)", text: "var(--color-text-secondary)" },
    confident: { bg: "#E1F5EE", text: "#0F6E56" },
    defensive: { bg: "#FAECE7", text: "#993C1D" },
    hedging: { bg: "#FAEEDA", text: "#854F0B" },
    attractive: { bg: "#EAF3DE", text: "#3B6D11" },
    fairly_priced: { bg: "#E6F1FB", text: "#185FA5" },
    expensive: { bg: "#FAEEDA", text: "#854F0B" },
    value_trap_risk: { bg: "#FCEBEB", text: "#A32D2D" },
  };
  const key = (label || "").toLowerCase().replace(/\s/g, "_");
  const style = colors[key] || colors.neutral;
  return (
    <span style={{
      fontSize: 11, fontWeight: 500, padding: "2px 8px",
      borderRadius: 4, background: style.bg, color: style.text,
      letterSpacing: "0.02em", whiteSpace: "nowrap"
    }}>
      {label}
    </span>
  );
}

function Metric({ label, value, sub }) {
  return (
    <div style={{ background: "var(--color-background-secondary)", borderRadius: 8, padding: "12px 14px" }}>
      <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "0 0 4px" }}>{label}</p>
      <p style={{ fontSize: 22, fontWeight: 500, margin: 0, color: "var(--color-text-primary)" }}>{value ?? "—"}</p>
      {sub && <p style={{ fontSize: 11, color: "var(--color-text-tertiary)", margin: "2px 0 0" }}>{sub}</p>}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-secondary)", letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 14px", borderBottom: "0.5px solid var(--color-border-tertiary)", paddingBottom: 8 }}>{title}</h3>
      {children}
    </div>
  );
}

function FlagPill({ text, type = "warn" }) {
  const styles = {
    warn: { bg: "#FAEEDA", color: "#854F0B" },
    error: { bg: "#FCEBEB", color: "#A32D2D" },
    info: { bg: "#E6F1FB", color: "#185FA5" },
  };
  const s = styles[type] || styles.info;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, padding: "3px 10px", borderRadius: 20, background: s.bg, color: s.color, margin: "3px 4px 3px 0" }}>
      <i className={`ti ${type === "error" ? "ti-alert-triangle" : "ti-info-circle"}`} style={{ fontSize: 13 }} aria-hidden="true" />
      {text}
    </span>
  );
}

function ToolStep({ toolName, status, summary, duration }) {
  const meta = TOOL_META[toolName] || { label: toolName, icon: "ti-tool" };
  const statusIcon = status === "complete" ? "ti-circle-check" : status === "running" ? "ti-loader-2" : status === "error" ? "ti-alert-circle" : "ti-circle";
  const statusColor = status === "complete" ? "#1D9E75" : status === "running" ? "#378ADD" : status === "error" ? "#E24B4A" : "var(--color-border-tertiary)";
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "10px 0", borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
      <i className={`ti ${statusIcon}`} style={{ fontSize: 18, color: statusColor, flexShrink: 0, marginTop: 1, animation: status === "running" ? "spin 1s linear infinite" : "none" }} aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-primary)" }}>
            <i className={`ti ${meta.icon}`} style={{ fontSize: 14, marginRight: 6 }} aria-hidden="true" />
            {meta.label}
          </span>
          {duration && <span style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>{(duration / 1000).toFixed(1)}s</span>}
        </div>
        {summary && <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "3px 0 0" }}>{summary}</p>}
      </div>
    </div>
  );
}

function ResearchBrief({ brief, ticker }) {
  if (!brief) return null;
  const { company_snapshot, valuation, financials, competitive_position, sentiment, management_signals, risks, analyst_summary, data_quality } = brief;

  const dqEntries = data_quality ? Object.entries(data_quality) : [];
  const avgConfidence = dqEntries.length ? Math.round(dqEntries.reduce((s, [, v]) => s + (v || 0), 0) / dqEntries.length) : 0;

  const allFlags = [];
  if (risks) risks.forEach(r => allFlags.push({ text: r, type: "warn" }));

  return (
    <div>
      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} } @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }`}</style>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28, animation: "fadeUp 0.4s ease" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 style={{ fontSize: 26, fontWeight: 500, margin: 0 }}>{company_snapshot?.company_name || ticker}</h2>
            <span style={{ fontSize: 13, color: "var(--color-text-secondary)", background: "var(--color-background-secondary)", padding: "2px 8px", borderRadius: 4 }}>{company_snapshot?.ticker}</span>
          </div>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)", margin: "4px 0 0" }}>{company_snapshot?.sector} · {company_snapshot?.industry} · {company_snapshot?.exchange}</p>
        </div>
        <div style={{ textAlign: "right" }}>
          <p style={{ fontSize: 28, fontWeight: 500, margin: 0 }}>${company_snapshot?.current_price?.toLocaleString()}</p>
          <p style={{ fontSize: 13, margin: "2px 0 0", color: (company_snapshot?.day_change_pct || 0) >= 0 ? "#1D9E75" : "#E24B4A" }}>
            {(company_snapshot?.day_change_pct || 0) >= 0 ? "▲" : "▼"} {Math.abs(company_snapshot?.day_change_pct || 0).toFixed(2)}% today
          </p>
        </div>
      </div>

      {/* Analyst summary */}
      <div style={{ background: "var(--color-background-secondary)", borderLeft: "3px solid #378ADD", padding: "14px 18px", borderRadius: "0 8px 8px 0", marginBottom: 28, animation: "fadeUp 0.5s ease" }}>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, color: "var(--color-text-primary)" }}>{analyst_summary}</p>
      </div>

      {/* Key metrics */}
      <Section title="Company Snapshot">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10 }}>
          <Metric label="Market Cap" value={company_snapshot?.market_cap} />
          <Metric label="Beta" value={company_snapshot?.beta?.toFixed(2)} />
          <Metric label="52w Position" value={company_snapshot?.week_52_position_pct != null ? `${company_snapshot.week_52_position_pct}%` : null} />
          <Metric label="Forward P/E" value={valuation?.pe_forward?.toFixed(1) + "x"} sub={`Peer median ${valuation?.peer_median_pe_forward?.toFixed(1)}x`} />
          <Metric label="EV/EBITDA" value={valuation?.ev_ebitda?.toFixed(1) + "x"} />
          <Metric label="Price/Sales" value={valuation?.price_to_sales?.toFixed(1) + "x"} />
        </div>
        <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>Valuation:</span>
          <StatusBadge label={valuation?.valuation_quality_label?.replace(/_/g, " ")} />
        </div>
      </Section>

      {/* Financials */}
      <Section title="Financials (TTM)">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10 }}>
          <Metric label="Revenue" value={financials?.ttm_revenue_m != null ? `$${(financials.ttm_revenue_m / 1000).toFixed(1)}B` : null} sub={`${financials?.revenue_yoy_growth_pct?.toFixed(1)}% YoY`} />
          <Metric label="Net Income" value={financials?.ttm_net_income_m != null ? `$${(financials.ttm_net_income_m / 1000).toFixed(1)}B` : null} />
          <Metric label="Free Cash Flow" value={financials?.ttm_fcf_m != null ? `$${(financials.ttm_fcf_m / 1000).toFixed(1)}B` : null} />
          <Metric label="EBITDA" value={financials?.ttm_ebitda_m != null ? `$${(financials.ttm_ebitda_m / 1000).toFixed(1)}B` : null} />
          <Metric label="Net Margin" value={financials?.ttm_net_margin_pct != null ? `${financials.ttm_net_margin_pct.toFixed(1)}%` : null} />
          <Metric label="Net Debt" value={financials?.latest_net_debt_m != null ? `$${(financials.latest_net_debt_m / 1000).toFixed(1)}B` : null} />
        </div>
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {financials?.revenue_trend && <FlagPill text={`Revenue: ${financials.revenue_trend.replace(/_/g, " ")}`} type="info" />}
          {financials?.revenue_acceleration && <FlagPill text={`Accel: ${financials.revenue_acceleration}`} type="info" />}
        </div>
      </Section>

      {/* Sentiment & Management */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 28 }}>
        <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 12, padding: "16px 18px" }}>
          <h3 style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-secondary)", letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 12px" }}>Sentiment</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10 }}>
            <div style={{ position: "relative", width: 56, height: 56, flexShrink: 0 }}>
              <svg width={56} height={56} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={28} cy={28} r={22} fill="none" stroke="var(--color-border-tertiary)" strokeWidth={4} />
                <circle cx={28} cy={28} r={22} fill="none"
                  stroke={sentiment?.score >= 0.6 ? "#1D9E75" : sentiment?.score >= 0.4 ? "#EF9F27" : "#E24B4A"}
                  strokeWidth={4}
                  strokeDasharray={`${(sentiment?.score || 0) * 2 * Math.PI * 22} ${2 * Math.PI * 22}`}
                  strokeLinecap="round" style={{ transition: "stroke-dasharray 1s ease" }} />
              </svg>
              <span style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 500 }}>
                {Math.round((sentiment?.score || 0) * 100)}
              </span>
            </div>
            <div>
              <StatusBadge label={sentiment?.label} />
              <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "6px 0 0" }}>{sentiment?.positive_count}+ positive · {sentiment?.negative_count} negative</p>
            </div>
          </div>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)", margin: "0 0 8px", lineHeight: 1.5 }}>{sentiment?.summary_line}</p>
          {sentiment?.negative_themes?.length > 0 && (
            <div>{sentiment.negative_themes.map((t, i) => <FlagPill key={i} text={t} type="warn" />)}</div>
          )}
        </div>

        <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 12, padding: "16px 18px" }}>
          <h3 style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-secondary)", letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 12px" }}>Management signals</h3>
          <div style={{ marginBottom: 8 }}>
            <StatusBadge label={management_signals?.dominant_tone} type={management_signals?.dominant_tone?.toLowerCase()} />
            <span style={{ fontSize: 12, color: "var(--color-text-secondary)", marginLeft: 8 }}>{management_signals?.tone_interpretation}</span>
          </div>
          {management_signals?.top_themes?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              {management_signals.top_themes.map((t, i) => <FlagPill key={i} text={t} type="info" />)}
            </div>
          )}
          {management_signals?.red_flags?.length > 0 && (
            <div>{management_signals.red_flags.map((f, i) => <FlagPill key={i} text={f} type="error" />)}</div>
          )}
          {management_signals?.deflections?.length > 0 && (
            <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "8px 0 0" }}>
              <i className="ti ti-corner-down-right" style={{ marginRight: 4 }} aria-hidden="true" />
              {management_signals.deflections[0]}
            </p>
          )}
        </div>
      </div>

      {/* Competitive position */}
      <Section title="Competitive Position">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {competitive_position?.peers_identified?.map(p => (
            <span key={p} style={{ fontSize: 12, padding: "2px 8px", borderRadius: 4, background: "var(--color-background-secondary)", color: "var(--color-text-secondary)" }}>{p}</span>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div>
            <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "0 0 6px" }}>Strengths vs peers</p>
            {competitive_position?.strengths_vs_peers?.map((s, i) => (
              <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                <i className="ti ti-arrow-up-right" style={{ color: "#1D9E75", fontSize: 14, flexShrink: 0 }} aria-hidden="true" />
                <span style={{ fontSize: 13, color: "var(--color-text-primary)" }}>{s}</span>
              </div>
            ))}
          </div>
          <div>
            <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "0 0 6px" }}>Weaknesses vs peers</p>
            {competitive_position?.weaknesses_vs_peers?.map((w, i) => (
              <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                <i className="ti ti-arrow-down-right" style={{ color: "#E24B4A", fontSize: 14, flexShrink: 0 }} aria-hidden="true" />
                <span style={{ fontSize: 13, color: "var(--color-text-primary)" }}>{w}</span>
              </div>
            ))}
          </div>
        </div>
        {competitive_position?.analyst_summary && (
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)", margin: "12px 0 0", lineHeight: 1.6 }}>{competitive_position.analyst_summary}</p>
        )}
      </Section>

      {/* Risks */}
      {risks?.length > 0 && (
        <Section title="Key Risks">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {risks.map((r, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "8px 12px", background: "#FCEBEB", borderRadius: 8 }}>
                <i className="ti ti-alert-triangle" style={{ color: "#A32D2D", fontSize: 15, flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                <span style={{ fontSize: 13, color: "#501313" }}>{r}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Data quality */}
      {data_quality && (
        <Section title="Data Quality">
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>Overall confidence</span>
              <span style={{ fontSize: 20, fontWeight: 500 }}>{avgConfidence}%</span>
              <StatusBadge label={avgConfidence >= 80 ? "High" : avgConfidence >= 60 ? "Medium" : "Low"} type={avgConfidence >= 80 ? "bullish" : avgConfidence >= 60 ? "hedging" : "bearish"} />
            </div>
            {Object.entries(data_quality).map(([key, val]) => (
              <ConfidenceBar key={key} toolKey={key.replace(/_/g, " ")} score={val} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

export default function StockResearchAgent() {
  const [ticker, setTicker] = useState("");
  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [toolProgress, setToolProgress] = useState({});
  const [toolOrder, setToolOrder] = useState([]);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [brief, setBrief] = useState(null);
  const [requestId, setRequestId] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const startRef = useRef(null);
  const pollRef = useRef(null);

  const clearTimers = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const startTimer = () => {
    startRef.current = Date.now();
    timerRef.current = setInterval(() => setElapsedMs(Date.now() - startRef.current), 200);
  };

  const connectWS = useCallback((rid) => {
    const ws = new WebSocket(`${BASE_URL.replace("http", "ws")}/ws/progress/${rid}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.event === "tool_start") {
        setToolOrder(prev => prev.includes(msg.tool) ? prev : [...prev, msg.tool]);
        setToolProgress(prev => ({ ...prev, [msg.tool]: { status: "running" } }));
      } else if (msg.event === "tool_complete") {
        setToolProgress(prev => ({ ...prev, [msg.tool]: { status: "complete", summary: msg.summary, duration: msg.duration_ms } }));
      } else if (msg.event === "error") {
        setToolProgress(prev => ({ ...prev, [msg.tool]: { status: "error", summary: msg.message } }));
      } else if (msg.event === "complete") {
        ws.close();
        pollResult(rid);
      }
    };
    ws.onerror = () => pollResult(rid);
  }, []);

  const pollResult = useCallback((rid) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/research/${rid}`);
        const data = await res.json();
        if (data.status === "complete") {
          clearTimers();
          setElapsedMs(Date.now() - startRef.current);
          setBrief(data.brief);
          setPhase("done");
        } else if (data.status === "error") {
          clearTimers();
          setErrorMsg("The research agent returned an error.");
          setPhase("error");
        }
      } catch {
        // keep polling
      }
    }, 1500);
  }, []);

  const handleSubmit = async () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    clearTimers();
    if (wsRef.current) wsRef.current.close();
    setPhase("running");
    setBrief(null);
    setErrorMsg(null);
    setToolProgress({});
    setToolOrder([]);
    startTimer();
    try {
      const res = await fetch(`${BASE_URL}/api/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error.message);
      setRequestId(data.request_id);
      connectWS(data.request_id);
    } catch (err) {
      clearTimers();
      setErrorMsg(err.message || "Could not connect to the research server.");
      setPhase("error");
    }
  };

  useEffect(() => () => { clearTimers(); if (wsRef.current) wsRef.current.close(); }, []);

  const completedTools = Object.values(toolProgress).filter(t => t.status === "complete").length;
  const totalExpected = 7;
  const progressPct = Math.round((completedTools / totalExpected) * 100);

  const dqEntries = brief?.data_quality ? Object.entries(brief.data_quality) : [];

  return (
    <div style={{ fontFamily: "var(--font-sans)", color: "var(--color-text-primary)", maxWidth: 760, margin: "0 auto", padding: "2rem 1rem" }}>
      <style>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:none} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
        .ticker-input { font-size: 20px !important; font-weight: 500 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; }
        .run-btn { background: var(--color-text-primary) !important; color: var(--color-background-primary) !important; border: none !important; padding: 0 28px !important; height: 52px !important; font-size: 15px !important; font-weight: 500 !important; border-radius: 8px !important; cursor: pointer; transition: opacity 0.15s; }
        .run-btn:hover { opacity: 0.85; }
        .run-btn:disabled { opacity: 0.4; cursor: not-allowed; }
      `}</style>

      {/* Hero */}
      <div style={{ marginBottom: 36, animation: "fadeUp 0.4s ease" }}>
        <h1 style={{ fontSize: 28, fontWeight: 500, margin: "0 0 6px" }}>Stock Research Agent</h1>
        <p style={{ fontSize: 14, color: "var(--color-text-secondary)", margin: 0 }}>
          Enter a ticker. The agent runs 7 specialist tools, reasons across the data, and produces a professional research brief — in under 2 minutes.
        </p>
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: 10, marginBottom: 36, alignItems: "stretch" }}>
        <input
          className="ticker-input"
          type="text"
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && phase !== "running" && handleSubmit()}
          placeholder="AAPL"
          maxLength={10}
          disabled={phase === "running"}
          style={{ flex: 1, height: 52, padding: "0 16px" }}
        />
        <button className="run-btn" onClick={handleSubmit} disabled={phase === "running" || !ticker.trim()}>
          {phase === "running" ? <><i className="ti ti-loader-2" style={{ animation: "spin 1s linear infinite", marginRight: 8 }} />Researching…</> : "Run Research ↗"}
        </button>
      </div>

      {/* Running state */}
      {phase === "running" && (
        <div style={{ animation: "fadeUp 0.3s ease" }}>
          {/* Progress header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
              <i className="ti ti-loader-2" style={{ animation: "spin 1s linear infinite", marginRight: 6, fontSize: 14 }} aria-hidden="true" />
              Running agentic workflow — {completedTools}/{totalExpected} tools complete
            </span>
            <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>{(elapsedMs / 1000).toFixed(1)}s</span>
          </div>

          {/* Progress bar */}
          <div style={{ height: 3, background: "var(--color-border-tertiary)", borderRadius: 2, marginBottom: 24, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${progressPct}%`, background: "#378ADD", borderRadius: 2, transition: "width 0.5s ease" }} />
          </div>

          {/* Tool steps */}
          <div style={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 12, padding: "4px 16px", marginBottom: 28 }}>
            {(toolOrder.length ? toolOrder : TOOL_ORDER).map(tool => {
              const p = toolProgress[tool];
              return <ToolStep key={tool} toolName={tool} status={p?.status || "pending"} summary={p?.summary} duration={p?.duration} />;
            })}
          </div>

          {/* Live confidence rings if any data */}
          {Object.values(toolProgress).some(t => t.status === "complete") && (
            <div>
              <p style={{ fontSize: 12, color: "var(--color-text-secondary)", marginBottom: 12 }}>Live tool confidence</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
                {toolOrder.filter(t => toolProgress[t]?.status === "complete").map(tool => {
                  const meta = TOOL_META[tool] || {};
                  return <ConfidenceRing key={tool} score={undefined} label={meta.label} />;
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error state */}
      {phase === "error" && (
        <div style={{ background: "#FCEBEB", border: "0.5px solid #F09595", borderRadius: 10, padding: "16px 20px", animation: "fadeUp 0.3s ease" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <i className="ti ti-alert-circle" style={{ color: "#A32D2D", fontSize: 20, flexShrink: 0 }} aria-hidden="true" />
            <div>
              <p style={{ fontWeight: 500, margin: "0 0 4px", color: "#501313" }}>Research failed</p>
              <p style={{ fontSize: 13, color: "#791F1F", margin: 0 }}>{errorMsg}</p>
            </div>
          </div>
        </div>
      )}

      {/* Done state */}
      {phase === "done" && brief && (
        <div style={{ animation: "fadeUp 0.4s ease" }}>
          {/* Completion banner */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "#E1F5EE", borderRadius: 8, marginBottom: 28, border: "0.5px solid #9FE1CB" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <i className="ti ti-circle-check" style={{ color: "#0F6E56", fontSize: 20 }} aria-hidden="true" />
              <span style={{ fontSize: 14, color: "#085041", fontWeight: 500 }}>Research complete</span>
              <span style={{ fontSize: 13, color: "#0F6E56" }}>· {(elapsedMs / 1000).toFixed(1)}s total</span>
            </div>
            {/* Mini confidence rings row */}
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              {dqEntries.map(([key, val]) => (
                <ConfidenceRing key={key} score={val} label={TOOL_META[Object.keys(TOOL_META).find(k => TOOL_META[k].short === key) || ""]?.label?.split(" ")[0] || key.replace("tool_0", "T")} size={52} />
              ))}
            </div>
          </div>

          <ResearchBrief brief={brief} ticker={ticker} />

          <button
            style={{ marginTop: 16, fontSize: 13, color: "var(--color-text-secondary)", background: "none", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 6, padding: "6px 14px", cursor: "pointer" }}
            onClick={() => { setPhase("idle"); setBrief(null); setTicker(""); }}
          >
            <i className="ti ti-refresh" style={{ marginRight: 6 }} aria-hidden="true" />New research
          </button>
        </div>
      )}

      {/* Idle state explainer */}
      {phase === "idle" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, animation: "fadeUp 0.5s ease" }}>
          {TOOL_ORDER.map(tool => {
            const meta = TOOL_META[tool];
            return (
              <div key={tool} style={{ background: "var(--color-background-secondary)", borderRadius: 8, padding: "14px 16px" }}>
                <i className={`ti ${meta.icon}`} style={{ fontSize: 18, color: "var(--color-text-secondary)", marginBottom: 8, display: "block" }} aria-hidden="true" />
                <p style={{ fontSize: 13, fontWeight: 500, margin: "0 0 2px" }}>{meta.label}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
