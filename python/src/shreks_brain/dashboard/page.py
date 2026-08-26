from __future__ import annotations

_DASHBOARD_HTML = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shreks Operator Dashboard</title>
<style>
:root{color-scheme:dark;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#0b0e0d;color:#e8efe9}
*{box-sizing:border-box}body{margin:0;background:#0b0e0d;color:#e8efe9}.shell{max-width:1180px;margin:0 auto;padding:18px}.top{display:flex;gap:16px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:18px}.brand h1{font-size:1.35rem;margin:0 0 5px}.muted{color:#97a69a}.live{border:1px solid #7d3c3c;background:#241313;color:#ffb6b6;border-radius:10px;padding:10px 12px;font-weight:800;letter-spacing:.03em}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.card{border:1px solid #27312a;background:#111613;border-radius:12px;padding:14px;min-width:0}.card h2{font-size:1rem;margin:0 0 12px}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.metric{border-top:1px solid #222b25;padding-top:7px}.label{display:block;color:#97a69a;font-size:.72rem;margin-bottom:3px}.value{display:block;overflow-wrap:anywhere}.wide{grid-column:1/-1}.status{font-weight:700}.error{color:#ffb6b6}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.82rem}th,td{text-align:left;padding:8px;border-bottom:1px solid #222b25;white-space:nowrap}tbody tr{cursor:pointer}tbody tr:focus,tbody tr:hover{background:#19201b;outline:none}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ledger{margin-top:10px}.footer{margin-top:14px;color:#718077;font-size:.72rem}@media(max-width:760px){.shell{padding:12px}.grid{grid-template-columns:1fr}.metrics,.detail-grid{grid-template-columns:1fr}.wide{grid-column:auto}.top{display:block}.live{display:inline-block;margin-top:10px}}
</style>
</head>
<body>
<main class="shell">
<header class="top">
<div class="brand"><h1>Shreks Operator Dashboard</h1><div class="muted">Read-only PAPER operations view · <span id="generated-at">UNAVAILABLE</span></div></div>
<div class="live">LIVE TRADING: DISABLED</div>
</header>
<section class="grid" aria-label="Monitoring layers">
<article class="card" id="system-layer"><h2>System</h2><div class="metrics">
<div class="metric"><span class="label">Status</span><span class="value status" id="system-status">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Market age</span><span class="value" id="market-age">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Providers</span><span class="value" id="provider-health">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Accounting</span><span class="value" id="accounting-status">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Latest checkpoint</span><span class="value" id="checkpoint-at">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Host metrics</span><span class="value" id="host-metrics">UNAVAILABLE</span></div>
</div></article>
<article class="card" id="trading-layer"><h2>Trading</h2><div class="metrics">
<div class="metric"><span class="label">Status</span><span class="value status" id="trading-status">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Candidates</span><span class="value" id="candidate-count">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Paper entries</span><span class="value" id="entry-count">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Open positions</span><span class="value" id="open-count">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Closed positions</span><span class="value" id="closed-count">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Candidate version</span><span class="value" id="candidate-version">UNAVAILABLE</span></div>
</div></article>
<article class="card" id="money-layer"><h2>Money</h2><div class="metrics">
<div class="metric"><span class="label">Status</span><span class="value status" id="money-status">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Realized PnL</span><span class="value" id="realized-pnl">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Unrealized PnL</span><span class="value" id="unrealized-pnl">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Net expectancy</span><span class="value" id="net-expectancy">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Profit factor</span><span class="value" id="profit-factor">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Maximum drawdown</span><span class="value" id="max-drawdown">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Total costs</span><span class="value" id="total-costs">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Cost burden</span><span class="value" id="cost-burden">UNAVAILABLE</span></div>
</div></article>
<article class="card" id="proof-risk-layer"><h2>Proof / Risk</h2><div class="metrics">
<div class="metric"><span class="label">Status</span><span class="value status" id="proof-status">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Proof decision</span><span class="value" id="proof-decision">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Promotion decision</span><span class="value" id="promotion-decision">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Proof trades</span><span class="value" id="proof-trades">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Distinct mints</span><span class="value" id="proof-mints">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Global risk halt</span><span class="value" id="risk-halt">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Accounting integrity</span><span class="value" id="accounting-integrity">UNAVAILABLE</span></div>
<div class="metric"><span class="label">Live state</span><span class="value" id="live-state">DISABLED</span></div>
</div></article>
<article class="card wide" id="recent-trades"><h2>Recent trades</h2><div id="trades-state" class="muted">UNAVAILABLE</div><div class="table-wrap"><table><thead><tr><th>Closed</th><th>Mint</th><th>Setup</th><th>Regime</th><th>Net PnL</th><th>Costs</th></tr></thead><tbody id="trades-body"></tbody></table></div></article>
<article class="card wide" id="trade-detail"><h2>Trade detail</h2><div id="detail-state" class="muted">Select a recent trade. Missing historical decision evidence is shown as NOT_PERSISTED.</div><div class="detail-grid">
<div><span class="label">Position</span><span class="value" id="detail-position">UNAVAILABLE</span></div>
<div><span class="label">Mint</span><span class="value" id="detail-mint">UNAVAILABLE</span></div>
<div><span class="label">Net PnL</span><span class="value" id="detail-pnl">UNAVAILABLE</span></div>
<div><span class="label">Safety assessment</span><span class="value" id="detail-safety">NOT_PERSISTED</span></div>
<div><span class="label">Feature vector</span><span class="value" id="detail-features">NOT_PERSISTED</span></div>
<div><span class="label">Score assessment</span><span class="value" id="detail-score">NOT_PERSISTED</span></div>
<div><span class="label">Entry decision</span><span class="value" id="detail-decision">NOT_PERSISTED</span></div>
<div><span class="label">Risk assessment</span><span class="value" id="detail-risk">NOT_PERSISTED</span></div>
<div><span class="label">Entry quote</span><span class="value" id="detail-quote">NOT_PERSISTED</span></div>
<div><span class="label">Strategic exit reason</span><span class="value" id="detail-exit">NOT_PERSISTED</span></div>
</div><div class="ledger"><span class="label">Ledger events</span><div id="detail-ledger">UNAVAILABLE</div></div></article>
</section>
<div class="footer">G5 private read-only view. Metrics are displayed from persisted Shreks telemetry and evidence; the browser does not derive trading performance or proof decisions.</div>
</main>
<script>
"use strict";
const byId=(id)=>document.getElementById(id);
const setText=(id,value)=>{byId(id).textContent=value===null||value===undefined?"UNAVAILABLE":String(value);};
const money=(value)=>value===null||value===undefined?"UNAVAILABLE":`$${Number(value).toFixed(2)}`;
const percent=(value)=>value===null||value===undefined?"UNAVAILABLE":`${Number(value).toFixed(2)}%`;
const when=(value)=>value===null||value===undefined?"UNAVAILABLE":new Date(value).toLocaleString();
const yesNo=(value)=>value===null||value===undefined?"UNAVAILABLE":value?"YES":"NO";

function renderSnapshot(payload){
 const telemetry=payload.telemetry;
 const system=telemetry.system;
 const trading=telemetry.trading;
 const moneyLayer=telemetry.money;
 const proof=telemetry.proof_risk;
 const performance=moneyLayer.performance;
 setText("generated-at",when(telemetry.generated_at_unix_ms));
 setText("system-status",system.status);setText("market-age",system.market_age_ms===null?null:`${system.market_age_ms} ms`);
 setText("provider-health",system.provider_count===null?null:`${system.provider_count-system.unhealthy_provider_count}/${system.provider_count} healthy`);
 setText("accounting-status",system.accounting_status);setText("checkpoint-at",when(system.latest_ingestion_checkpoint_at_unix_ms));setText("host-metrics",yesNo(system.host_metrics_available));
 setText("trading-status",trading.status);setText("candidate-count",trading.candidate_count);setText("entry-count",trading.terminal_paper_entry_count);setText("open-count",trading.open_position_count);setText("closed-count",trading.closed_position_count);setText("candidate-version",trading.candidate_version);
 setText("money-status",moneyLayer.status);setText("realized-pnl",money(moneyLayer.realized_pnl_usd));setText("unrealized-pnl",money(moneyLayer.unrealized_pnl_usd));
 setText("net-expectancy",performance?percent(performance.net_expectancy_pct):null);setText("profit-factor",performance?performance.profit_factor:null);setText("max-drawdown",performance?percent(performance.maximum_drawdown_pct):null);setText("total-costs",performance?money(performance.total_cost_usd):null);setText("cost-burden",performance?percent(performance.cost_burden_pct):null);
 setText("proof-status",proof.status);setText("proof-decision",proof.proof_decision);setText("promotion-decision",proof.promotion_decision);setText("proof-trades",proof.proof_trade_count);setText("proof-mints",proof.proof_distinct_mint_count);setText("risk-halt",yesNo(proof.global_risk_halt));setText("accounting-integrity",proof.accounting_integrity);setText("live-state",proof.live_state);
 // Authoritative server fields displayed above: net_pnl_usd unrealized_pnl_usd net_expectancy_pct profit_factor maximum_drawdown_pct total_cost_usd cost_burden_pct proof_trade_count proof_distinct_mint_count proof_decision promotion_decision global_risk_halt accounting_integrity
}

function makeCell(row,value){const cell=document.createElement("td");cell.textContent=value===null||value===undefined?"UNAVAILABLE":String(value);row.append(cell);}
function renderTrades(payload){
 const body=byId("trades-body");body.replaceChildren();
 const trades=Array.isArray(payload.trades)?payload.trades:[];setText("trades-state",trades.length?`${trades.length} persisted closed trades`:"No persisted closed trades");
 for(const trade of trades){const row=document.createElement("tr");row.tabIndex=0;row.setAttribute("role","button");
  makeCell(row,when(trade.closed_at_unix_ms));makeCell(row,trade.mint);makeCell(row,trade.setup_name);makeCell(row,trade.market_regime);makeCell(row,money(trade.net_pnl_usd));makeCell(row,money(trade.explicit_cost_usd+trade.execution_friction_usd));
  const open=()=>loadTrade(trade.position_id);row.addEventListener("click",open);row.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();open();}});body.append(row);
 }
}

async function loadTrade(positionId){
 setText("detail-state","Loading persisted evidence…");
 try{const response=await fetch(`/api/v1/trades/${encodeURIComponent(positionId)}`, {credentials: "same-origin"});if(!response.ok){throw new Error("SOURCE_UNAVAILABLE");}const detail=await response.json();
  setText("detail-state","Persisted trade evidence");setText("detail-position",detail.summary.position_id);setText("detail-mint",detail.summary.mint);setText("detail-pnl",money(detail.summary.net_pnl_usd));setText("detail-safety",detail.safety_assessment);setText("detail-features",detail.feature_vector);setText("detail-score",detail.score_assessment);setText("detail-decision",detail.entry_decision);setText("detail-risk",detail.risk_assessment);setText("detail-quote",detail.entry_quote);setText("detail-exit",detail.strategic_exit_reason);
  setText("detail-ledger",detail.ledger_events.length?detail.ledger_events.map(event=>`#${event.sequence} ${event.side} ${event.execution_state} ${money(event.filled_notional_usd)}`).join(" · "):"UNAVAILABLE");
 }catch(_error){setText("detail-state","SOURCE_UNAVAILABLE");}
}

async function refresh(){
 try{const response=await fetch("/api/v1/snapshot", {credentials: "same-origin"});if(!response.ok){throw new Error("SOURCE_UNAVAILABLE");}renderSnapshot(await response.json());}catch(_error){setText("generated-at","SOURCE_UNAVAILABLE");}
 try{const response=await fetch("/api/v1/trades", {credentials: "same-origin"});if(!response.ok){throw new Error("SOURCE_UNAVAILABLE");}renderTrades(await response.json());}catch(_error){setText("trades-state","SOURCE_UNAVAILABLE");}
}
refresh();setInterval(refresh,15000);
</script>
</body>
</html>
"""


def render_dashboard_page() -> bytes:
    return _DASHBOARD_HTML
