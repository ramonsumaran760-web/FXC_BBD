// pages/Dashboard.jsx — Vista principal del dashboard
import React from "react";
import { useStore } from "../store/store";
import CandleChart from "../components/charts/CandleChart";
import PortfolioChart from "../components/charts/PortfolioChart";
import api from "../services/api";

const C = { bg:"#0b0f14", bg2:"#111820", bg3:"#171f2a", bg4:"#1E2835",
  border:"#2a3545", g:"#17cc85", g2:"#12a068", b:"#2196f3", a:"#f5a623", r:"#f44336",
  p:"#ab47bc", t:"#26c6da", text:"#dde4f0", text2:"#8fa0b8", text3:"#576880" };

const fmtUSD = n => `$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const fmtPct = n => `${n>=0?"+":""}${parseFloat(n||0).toFixed(3)}%`;
const fmtAcc = n => parseFloat(n||0).toFixed(6);

// ── Metric Card ───────────────────────────────────────────
function MetricCard({ label, value, sub, color, icon, onClick }) {
  const [hov, setHov] = React.useState(false);
  return (
    <div onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ background: C.bg2, border: `1px solid ${hov ? C.border+"99" : C.border}`,
        borderTop: `2.5px solid ${color}`, borderRadius: 10, padding: "12px 14px",
        cursor: onClick ? "pointer" : "default", transition: "all .25s",
        transform: hov ? "translateY(-1px)" : "none",
        boxShadow: hov ? "0 4px 24px rgba(0,0,0,.6)" : "none" }}>
      <div style={{ width: 32, height: 32, borderRadius: 7, marginBottom: 8,
        background: `${color}22`, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <i className={`fas ${icon}`} style={{ color, fontSize: 14 }} />
      </div>
      <div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", letterSpacing: ".07em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 19, fontWeight: 700, color, fontVariantNumeric: "tabular-nums", marginBottom: 3 }}>{value}</div>
      {sub && <div style={{ fontSize: 9, color: C.text3 }}>{sub}</div>}
    </div>
  );
}

// ── Progress Bar ──────────────────────────────────────────
function ProgressBar({ label, value, max, color }) {
  const pct = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 4 }}>
        <span style={{ color: C.text2 }}>{label}</span>
        <span style={{ color: C.text, fontWeight: 600 }}>{typeof value === "number" ? value.toLocaleString() : value}</span>
      </div>
      <div style={{ height: 6, background: C.bg4, borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, borderRadius: 3,
          background: `linear-gradient(90deg,${color}88,${color})`, transition: "width 1s ease" }} />
      </div>
    </div>
  );
}

// ── Slider ────────────────────────────────────────────────
function Slider({ label, min, max, step, value, onChange, unit = "" }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 5 }}>
        <span style={{ color: C.text2 }}>{label}</span>
        <span style={{ color: C.g, fontWeight: 700 }}>{unit}{parseFloat(value).toLocaleString()}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: C.g2, cursor: "pointer" }} />
    </div>
  );
}

export default function Dashboard() {
  const { state, actions } = useStore();
  const { portafolio, metricas, prices, candles, tickerChart, params, tasks, ordenes } = state;
  const [activeTab, setActiveTab] = React.useState("portafolio");
  const tasksDone = tasks.filter(t => t.completada).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 10 }}>
        <MetricCard label="Valor Portafolio" value={fmtUSD(portafolio.total_valor_usd)}
          sub={`${fmtPct(metricas.ganancia_pct)} total`} color={C.g} icon="fa-arrow-trend-up" />
        <MetricCard label="Ganancia / Pérdida"
          value={fmtUSD(portafolio.ganancia_perdida_total)}
          sub="desde primer depósito"
          color={portafolio.ganancia_perdida_total >= 0 ? C.g : C.r} icon="fa-chart-line" />
        <MetricCard label="Saldo Disponible" value={fmtUSD(metricas.saldo_disponible)}
          sub="listo para invertir" color={C.b} icon="fa-wallet"
          onClick={() => actions.depositar && prompt && undefined} />
        <MetricCard label="Posiciones" value={metricas.posiciones || 0}
          sub="activos en portafolio" color={C.p} icon="fa-briefcase" />
        <MetricCard label="Órdenes totales" value={metricas.ordenes_total || 0}
          sub="Alpaca Paper Trading" color={C.a} icon="fa-bolt" />
      </div>

      {/* ── Charts row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 10 }}>
        {/* Candles */}
        <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: C.text }}>
              <i className="fas fa-chart-candlestick" style={{ color: C.g, marginRight: 6 }} />
              Velas japonesas — {tickerChart}
            </span>
            <div style={{ display: "flex", gap: 4 }}>
              {["AAPL","NVDA","TSLA","SPY","MSFT"].map(t => (
                <button key={t} onClick={() => { actions.setTickerChart(t); actions.loadCandles(t); }}
                  style={{ padding: "3px 8px", borderRadius: 4, fontSize: 9, cursor: "pointer",
                    border: `1px solid ${tickerChart === t ? C.g2 : C.border}`,
                    background: tickerChart === t ? C.g2 : "transparent",
                    color: tickerChart === t ? "#fff" : C.text2 }}>{t}</button>
              ))}
              {["1d","1wk","1mo","3mo"].map(p => (
                <button key={p} onClick={() => actions.loadCandles(tickerChart, p === "1wk" ? "5d" : p)}
                  style={{ padding: "3px 8px", borderRadius: 4, fontSize: 9, cursor: "pointer",
                    border: `1px solid ${C.border}`, background: "transparent", color: C.text3 }}>{p}</button>
              ))}
            </div>
          </div>
          <CandleChart candles={candles[tickerChart] || []} height={180} />
        </div>

        {/* Donut */}
        <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 12 }}>
            <i className="fas fa-chart-pie" style={{ color: C.b, marginRight: 6 }} />Distribución portafolio
          </div>
          <PortfolioChart posiciones={portafolio.posiciones || []} prices={prices} size={140} />
        </div>
      </div>

      {/* ── Progress + Sliders ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 12 }}>
            <i className="fas fa-tasks" style={{ color: C.g, marginRight: 6 }} />Estado del sistema
          </div>
          <ProgressBar label="KYC verificado" value={100} max={100} color={C.g} />
          <ProgressBar label="AML completado" value={82} max={100} color={C.b} />
          <ProgressBar label="Órdenes ejecutadas" value={metricas.ordenes_total||0} max={50} color={C.p} />
          <ProgressBar label="Tareas completadas" value={tasksDone} max={tasks.length||1} color={C.a} />
          <ProgressBar label="Saldo invertido" value={portafolio.total_valor_usd||0}
            max={(portafolio.total_valor_usd||0)+(metricas.saldo_disponible||1)} color={C.r} />
        </div>

        <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 12 }}>
            <i className="fas fa-sliders-h" style={{ color: C.a, marginRight: 6 }} />Parámetros de inversión
          </div>
          <Slider label="Orden mínima (USD)" min={1} max={500} step={1} value={params.minOrden}
            onChange={v => actions.setParam("minOrden", v)} unit="$" />
          <Slider label="Concentración máx. por activo (%)" min={5} max={80} step={1} value={params.maxConcentracion}
            onChange={v => actions.setParam("maxConcentracion", v)} />
          <Slider label="Umbral alerta IA (%)" min={5} max={50} step={1} value={params.umbralIA}
            onChange={v => actions.setParam("umbralIA", v)} />
          <Slider label="Límite retiro mensual (USD)" min={100} max={10000} step={100} value={params.limiteRetiro}
            onChange={v => actions.setParam("limiteRetiro", v)} unit="$" />
        </div>
      </div>

      {/* ── Table ── */}
      <div style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "11px 14px", borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: C.text }}>
            <i className="fas fa-table" style={{ color: C.g, marginRight: 6 }} />Posiciones y operaciones
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            {["portafolio","ordenes"].map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                style={{ padding: "4px 9px", borderRadius: 4, fontSize: 10, cursor: "pointer",
                  border: `1px solid ${activeTab === t ? C.g2 : C.border}`,
                  background: activeTab === t ? C.g2 : "transparent",
                  color: activeTab === t ? C.g : C.text2 }}>
                {t === "portafolio" ? "Portafolio" : "Órdenes"}
              </button>
            ))}
          </div>
        </div>
        <div style={{ overflowX: "auto", maxHeight: 200, overflowY: "auto" }}>
          {activeTab === "portafolio" ? (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
              <thead>
                <tr>{["Ticker","Nombre","Acciones","P. Compra","P. Actual","Valor USD","G/P USD","G/P %"].map(h => (
                  <th key={h} style={{ padding: "7px 10px", background: C.bg3, color: C.text3, fontWeight: 600,
                    textAlign: "left", fontSize: 9, textTransform: "uppercase", borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" }}>{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {(portafolio.posiciones || []).map(p => {
                  const livePrice = prices[p.ticker]?.price || p.precio_actual;
                  const liveValor = livePrice * p.acciones;
                  const liveGP = liveValor - p.precio_promedio_compra * p.acciones;
                  const livePct = p.precio_promedio_compra > 0 ? (livePrice - p.precio_promedio_compra) / p.precio_promedio_compra * 100 : 0;
                  return (
                    <tr key={p.ticker}>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, fontWeight: 700, color: C.g }}>{p.ticker}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{p.nombre}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{fmtAcc(p.acciones)}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{fmtUSD(p.precio_promedio_compra)}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.g }}>{fmtUSD(livePrice)}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, fontWeight: 700, color: C.text }}>{fmtUSD(liveValor)}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: liveGP >= 0 ? C.g : C.r }}>{fmtUSD(liveGP)}</td>
                      <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: livePct >= 0 ? C.g : C.r }}>{fmtPct(livePct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
              <thead>
                <tr>{["#","Ticker","Tipo","Monto USD","Acciones","Precio Ejec.","Estado","Broker","Firma ECDSA","AML","Fecha"].map(h => (
                  <th key={h} style={{ padding: "7px 10px", background: C.bg3, color: C.text3, fontWeight: 600,
                    textAlign: "left", fontSize: 9, textTransform: "uppercase", borderBottom: `1px solid ${C.border}`, whiteSpace: "nowrap" }}>{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {ordenes.map(o => (
                  <tr key={o.id}>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text3 }}>#{o.id}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, fontWeight: 700, color: C.text }}>{o.ticker}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: o.tipo === "buy" ? C.g : C.r, fontWeight: 600 }}>{o.tipo?.toUpperCase()}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{fmtUSD(o.monto_usd)}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{fmtAcc(o.acciones)}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text2 }}>{fmtUSD(o.precio_ejecucion)}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)` }}>
                      <span style={{ padding: "2px 7px", borderRadius: 8, fontSize: 8, fontWeight: 700,
                        background: o.estado === "filled" ? `${C.g}22` : `${C.a}22`,
                        color: o.estado === "filled" ? C.g : C.a }}>{o.estado}</span>
                    </td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text3, fontSize: 9 }}>{o.broker}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: o.firma_verificada ? C.g : C.r }}>
                      {o.firma_verificada ? "✓ P-256" : "✗"}
                    </td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: o.aml_check === "clear" ? C.g : C.a, fontSize: 9 }}>{o.aml_check}</td>
                    <td style={{ padding: "7px 10px", borderBottom: `1px solid rgba(42,53,69,.3)`, color: C.text3, fontSize: 9 }}>{o.creado?.slice(0,16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}
