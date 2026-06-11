/* ============================================================
   mockData.js — single source of truth for the frontend.
   Shape mirrors the API contract:
     GET /api/research/{request_id}  ->  { request_id, ticker, status, brief }
   Components read ONLY from here. When the backend is live,
   flip USE_BACKEND in index.html — nothing else changes.

   --- Using this in a Vite/CRA React project? ---
   Delete the `window.MOCK = ...` line at the bottom and add:
       export const TOOLS = [...];
       export function getResearch(ticker) {...}
       export const MOCK_BRIEF = getResearch("AAPL");
   The objects themselves stay identical.
   ============================================================ */

(function(){
/* The 7 agent tools, in execution order (drives the live pipeline
   + the confidence chart). Matches WS tool_number / total_tools = 7. */
const TOOLS = [
  { id: "get_price_and_metrics", label: "Price & Metrics" },
  { id: "get_valuation",         label: "Valuation"       },
  { id: "get_company_profile",   label: "Company Profile" },
  { id: "get_recent_news",       label: "Recent News"     },
  { id: "score_sentiment",       label: "ML Sentiment"    },
  { id: "assess_risks",          label: "Risk Analysis"   },
  { id: "synthesize_brief",      label: "Synthesis"       },
];

/* ---- Seeded briefs (full richness for the demo) ---- */
const SEED = {
  AAPL: {
    company_snapshot: {
      ticker: "AAPL", company_name: "Apple Inc.", current_price: 211.45,
      market_cap: "$3.18T", day_change_pct: 1.48, sector: "Technology",
    },
    valuation: { pe_forward: 27.8, ev_ebitda: 22.3, valuation_quality_label: "FAIRLY_PRICED" },
    sentiment: { score: 0.68, label: "BULLISH", positive_count: 8, negative_count: 2, total_headlines: 12 },
    risks: [
      "ELEVATED_PE — forward P/E above sector median",
      "REGULATORY — App Store fee and default-search agreements under scrutiny",
      "GROWTH — revenue growth below peer median",
    ],
    strengths: [
      "SERVICES_MOAT — high-margin recurring Services engine on a ~2.2B-device base",
      "CASH_GENERATION — $108B TTM free cash flow funds aggressive capital return",
      "PRICING_POWER — ecosystem lock-in preserves gross margin through soft cycles",
    ],
    company_overview:
      "Apple designs consumer hardware, software and services across a tightly integrated ecosystem. The investment story has matured from unit growth toward a high-margin, recurring Services engine layered on a ~2.2B-device installed base, with best-in-class capital return.",
    analyst_summary:
      "Apple remains a quality compounder anchored by a widening, high-margin Services moat and prodigious cash generation. The debate is valuation, not durability: at ~28x forward earnings on low-single-digit revenue growth, returns lean on Services attach and buybacks rather than hardware units. Regulatory tail-risks are real but slow-moving. A core holding for quality mandates; valuation-sensitive investors may prefer to accumulate on weakness.",
    freshness: { price: "real-time", news: "last 24h", fundamentals: "Q3 FY24 filing" },
    data_quality: {
      overall_score: 0.86,
      flags: ["ELEVATED_PE", "REGULATORY_OVERHANG"],
      missing_information: [
        "EV/EBITDA computed on trailing data — forward estimate pending next guidance.",
        "2 of 12 recent headlines could not be reliably scored by the sentiment model.",
      ],
    },
    confidence_assessment: [
      { tool: "get_price_and_metrics", confidence: 0.98, rating: "HIGH",   summary: "Price $211.45 · Mkt cap $3.18T · real-time quote" },
      { tool: "get_valuation",         confidence: 0.83, rating: "MEDIUM", summary: "Fwd P/E 27.8 · EV/EBITDA 22.3 · FAIRLY_PRICED" },
      { tool: "get_company_profile",   confidence: 0.95, rating: "HIGH",   summary: "Technology · Consumer Electronics" },
      { tool: "get_recent_news",       confidence: 0.79, rating: "MEDIUM", summary: "12 headlines from 9 sources · last 24h" },
      { tool: "score_sentiment",       confidence: 0.74, rating: "MEDIUM", summary: "Custom model · 0.68 BULLISH · 2 unscored" },
      { tool: "assess_risks",          confidence: 0.88, rating: "HIGH",   summary: "3 risks flagged · valuation + regulatory" },
      { tool: "synthesize_brief",      confidence: 0.90, rating: "HIGH",   summary: "Structured brief generated" },
    ],
  },

  TSLA: {
    company_snapshot: {
      ticker: "TSLA", company_name: "Tesla, Inc.", current_price: 248.42,
      market_cap: "$792B", day_change_pct: 2.13, sector: "Consumer Discretionary",
    },
    valuation: { pe_forward: 71.4, ev_ebitda: 41.7, valuation_quality_label: "ELEVATED" },
    sentiment: { score: 0.62, label: "CAUTIOUSLY_BULLISH", positive_count: 6, negative_count: 4, total_headlines: 10 },
    risks: [
      "MARGIN_PRESSURE — automotive gross margin compressed by price cuts and aging lineup",
      "HIGH_VALUATION — 71x forward earnings prices in autonomy/energy upside",
      "KEY_PERSON — governance concentration around the CEO adds idiosyncratic volatility",
    ],
    strengths: [
      "NET_CASH — -$15.1B net debt and positive FCF cushion the autonomy roadmap",
      "ENERGY_RAMP — storage deployments compounding at record volumes",
      "COST_CURVE — vertical integration and 4680 ramp improving unit economics",
    ],
    company_overview:
      "Tesla designs, manufactures and sells electric vehicles and energy generation/storage systems. The 2024–25 narrative has shifted from delivery growth toward margin defence and the optionality embedded in autonomy and the energy business.",
    analyst_summary:
      "Tesla screens as a high-beta optionality play rather than a value name. The thesis hinges less on this year's deliveries and more on whether the energy business and autonomy stack convert into the cash flows the multiple already implies. A fortress balance sheet cushions downside, but at 71x forward earnings the execution bar is high and margin trends warrant close monitoring.",
    freshness: { price: "real-time", news: "last 24h — partial", fundamentals: "Q2 FY24 filing" },
    data_quality: {
      overall_score: 0.74,
      flags: ["HIGH_VALUATION", "MARGIN_WATCH", "STALE_NEWS"],
      missing_information: [
        "Latest quarterly delivery figures not yet released — growth metrics use prior period.",
        "Forward gross-margin guidance withheld by management this quarter.",
        "News feed degraded: 2 sources timed out, sentiment scored on 8 of 10 headlines.",
      ],
    },
    confidence_assessment: [
      { tool: "get_price_and_metrics", confidence: 0.97, rating: "HIGH",   summary: "Price $248.42 · Mkt cap $792B · real-time" },
      { tool: "get_valuation",         confidence: 0.70, rating: "MEDIUM", summary: "Fwd P/E 71.4 · EV/EBITDA 41.7 · ELEVATED" },
      { tool: "get_company_profile",   confidence: 0.93, rating: "HIGH",   summary: "Consumer Discretionary · Automobiles/EV" },
      { tool: "get_recent_news",       confidence: 0.55, rating: "LOW",    summary: "8/10 headlines · 2 sources timed out" },
      { tool: "score_sentiment",       confidence: 0.61, rating: "LOW",    summary: "Custom model · 0.62 · partial coverage" },
      { tool: "assess_risks",          confidence: 0.82, rating: "MEDIUM", summary: "3 risks · margin + valuation + governance" },
      { tool: "synthesize_brief",      confidence: 0.78, rating: "MEDIUM", summary: "Brief generated · flagged data gaps" },
    ],
  },

  NVDA: {
    company_snapshot: {
      ticker: "NVDA", company_name: "NVIDIA Corporation", current_price: 138.07,
      market_cap: "$3.38T", day_change_pct: 2.92, sector: "Technology",
    },
    valuation: { pe_forward: 38.5, ev_ebitda: 34.1, valuation_quality_label: "ELEVATED" },
    sentiment: { score: 0.71, label: "BULLISH", positive_count: 9, negative_count: 2, total_headlines: 11 },
    risks: [
      "CONCENTRATION — a handful of hyperscale customers drive the bulk of sales",
      "GEOPOLITICAL — export controls put a material China revenue slice at risk",
      "COMPETITION — in-house custom silicon from cloud majors is a structural threat",
    ],
    strengths: [
      "CUDA_MOAT — software ecosystem creates deep, durable switching costs",
      "ECONOMICS — 75% gross margin, net-cash balance sheet, $56B FCF",
      "FULL_STACK — GPU + networking + software captures systems-level AI spend",
    ],
    company_overview:
      "NVIDIA designs accelerated-computing platforms spanning GPUs, networking and the CUDA software stack that has become the de-facto standard for AI training and inference. Data-center is now the overwhelming revenue driver.",
    analyst_summary:
      "NVIDIA is the defining beneficiary of the AI infrastructure build-out, with economics and an ecosystem moat that justify a premium. The crux is durability: at ~38x forward earnings the market assumes the demand curve bends gently, not sharply. CUDA lock-in argues for staying power, but customer concentration and a future capex-digestion cycle are the swing factors to monitor.",
    freshness: { price: "real-time", news: "last 24h", fundamentals: "Q3 FY25 filing" },
    data_quality: {
      overall_score: 0.81,
      flags: ["HIGH_VALUATION", "CONCENTRATION_RISK"],
      missing_information: [
        "Segment-level China revenue not separately disclosed in latest filing.",
        "Forward EV/EBITDA constrained by a wide management guidance range.",
      ],
    },
    confidence_assessment: [
      { tool: "get_price_and_metrics", confidence: 0.98, rating: "HIGH",   summary: "Price $138.07 · Mkt cap $3.38T · real-time" },
      { tool: "get_valuation",         confidence: 0.76, rating: "MEDIUM", summary: "Fwd P/E 38.5 · EV/EBITDA 34.1 · ELEVATED" },
      { tool: "get_company_profile",   confidence: 0.96, rating: "HIGH",   summary: "Technology · Semiconductors" },
      { tool: "get_recent_news",       confidence: 0.86, rating: "HIGH",   summary: "11 headlines from 8 sources · last 24h" },
      { tool: "score_sentiment",       confidence: 0.80, rating: "MEDIUM", summary: "Custom model · 0.71 BULLISH" },
      { tool: "assess_risks",          confidence: 0.84, rating: "MEDIUM", summary: "3 risks · concentration + geopolitics" },
      { tool: "synthesize_brief",      confidence: 0.89, rating: "HIGH",   summary: "Structured brief generated" },
    ],
  },
};

/* ---- deterministic generator so ANY ticker returns a stable brief ---- */
function hashStr(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function rng(seed){let x=seed%2147483647;if(x<=0)x+=2147483646;return ()=>{x=(x*16807)%2147483647;return (x-1)/2147483646}}
const SECTORS=["Technology","Health Care","Financials","Consumer Discretionary","Industrials","Energy","Communication Services","Materials"];
function ratingFor(c){return c>=0.85?"HIGH":c>=0.65?"MEDIUM":"LOW"}

function generateBrief(ticker){
  const t = ticker.toUpperCase();
  const r = rng(hashStr(t));
  const price = +(20+r()*480).toFixed(2);
  const dch = +((r()*8)-3.2).toFixed(2);
  const sector = SECTORS[Math.floor(r()*SECTORS.length)];
  const total = 10+Math.floor(r()*4);
  const pos = Math.floor(total*(0.35+r()*0.4));
  const neg = Math.max(0, Math.floor((total-pos)*(0.3+r()*0.4)));
  const score = +(((pos + (total-pos-neg)*0.5)/total)).toFixed(2);
  const label = score>0.66?"BULLISH":score>0.55?"CAUTIOUSLY_BULLISH":score>0.45?"NEUTRAL":"CAUTIOUS";
  const pe = +(8+r()*55).toFixed(1);
  const vlabel = pe>40?"ELEVATED":pe>22?"FAIRLY_PRICED":"ATTRACTIVE";
  const newsConf = +(0.5+r()*0.45).toFixed(2);
  const conf = (c)=>({confidence:+c.toFixed(2), rating:ratingFor(c)});
  const tConf = [0.97, 0.6+r()*0.3, 0.9+r()*0.08, newsConf, newsConf-0.05+r()*0.1, 0.7+r()*0.2, 0.75+r()*0.18];
  const overall = +(tConf.reduce((a,b)=>a+b,0)/tConf.length).toFixed(2);
  const flags = [];
  if(pe>40) flags.push("HIGH_VALUATION");
  if(dch<0) flags.push("MACRO_WATCH");
  if(newsConf<0.7) flags.push("STALE_NEWS");
  if(flags.length===0) flags.push("STANDARD_SCHEMA");
  const missing = [];
  if(newsConf<0.7) missing.push(`News feed degraded — sentiment scored on ${Math.max(1,total-2)} of ${total} headlines.`);
  missing.push("Forward estimates use most recent filing; next guidance pending.");
  return {
    company_snapshot:{ ticker:t, company_name:`${t} Holdings`, current_price:price,
      market_cap:`$${(r()*900+10).toFixed(0)}B`, day_change_pct:dch, sector },
    valuation:{ pe_forward:pe, ev_ebitda:+(pe*0.7).toFixed(1), valuation_quality_label:vlabel },
    sentiment:{ score, label, positive_count:pos, negative_count:neg, total_headlines:total },
    risks:[
      `MACRO_SENSITIVITY — forward estimates sensitive to the macro backdrop and sector rotation`,
      `COMPETITION — intensity within ${sector} could pressure pricing and share`,
      `EXECUTION — delivery against the stated growth framework remains unproven`,
    ],
    strengths:[
      `BALANCE_SHEET — flexibility to fund the strategic roadmap through the cycle`,
      `DIVERSIFICATION — reduces reliance on any single revenue line within ${sector}`,
      `FRAMEWORK — coherent medium-term growth framework anchors the case`,
    ],
    company_overview:`${t} operates within the ${sector} sector. This brief is generated from the agent's standard research schema; with the live data tools connected it populates real fundamentals, news and custom-scored sentiment in the identical structure.`,
    analyst_summary:`${t} presents a ${label.toLowerCase().replace("_"," ")} setup on the current read. The standardized schema surfaces a balanced risk/strength profile, a sentiment score of ${score.toFixed(2)}, and an overall data-quality score of ${overall.toFixed(2)}. Once the live tools are connected this same structure fills with real-time data — a verifiable, comparable brief in under two minutes.`,
    freshness:{ price:"real-time", news:"last 24h", fundamentals:"latest filing" },
    data_quality:{ overall_score:overall, flags, missing_information:missing },
    confidence_assessment: TOOLS.map((tool,i)=>{
      const c = Math.min(0.99, Math.max(0.45, tConf[i]));
      return { tool:tool.id, ...conf(c), summary:`${tool.label} resolved` };
    }),
  };
}

/* envelope matching GET /api/research/{request_id} */
let _seq = 1000;
function getResearch(ticker){
  const t = (ticker||"").toUpperCase();
  const brief = SEED[t] ? JSON.parse(JSON.stringify(SEED[t])) : generateBrief(t);
  return {
    request_id: `mock-${(++_seq)}`,
    ticker: t,
    status: "complete",
    created_at: "2026-06-10T16:00:00Z",
    brief,
  };
}

/* expose for the single-file CDN demo */
if (typeof window !== "undefined") window.MOCK = { TOOLS, getResearch, ratingFor };
})();
