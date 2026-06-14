// pages/Portafolio.jsx — Portafolio completo con métricas y gestión
import React, { useState, useEffect } from "react";
import { useStore } from "../store/store";
import PortfolioChart from "../components/charts/PortfolioChart";
import CandleChart from "../components/charts/CandleChart";
import api from "../services/api";

const C = { bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",t:"#26c6da",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880" };

const fmtUSD = n=>`$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const fmtPct = n=>`${n>=0?"+":""}${parseFloat(n||0).toFixed(3)}%`;
const fmtAcc = n=>parseFloat(n||0).toFixed(6);
const TICK_COLS = {AAPL:"#0D7A4E",MSFT:"#0D3D7A",NVDA:"#4A0D7A",TSLA:"#7A4E0D",AMZN:"#6B0D3A",SPY:"#2D5C1A",QQQ:"#185FA5",BND:"#854F0B",VTI:"#3B6D11",GLD:"#854F0B"};

export default function Portafolio() {
  const { state, actions } = useStore();
  const { portafolio, prices } = state;
  const [candles, setCandles] = useState({});
  const [dividendos, setDividendos] = useState([]);
  const [transacciones, setTransacciones] = useState([]);
  const [brokerPos, setBrokerPos] = useState([]);
  const [tab, setTab] = useState("posiciones");
  const [selectedPos, setSelectedPos] = useState(null);

  useEffect(() => {
    actions.loadPortafolio();
    api.getDividendos().then(setDividendos).catch(()=>{});
    api.getTransacciones().then(setTransacciones).catch(()=>{});
    // Broker positions
    fetch("/api/v1/portafolio").then(r=>r.json()).then(d=>setBrokerPos(d.posiciones_broker||[])).catch(()=>{});
  }, []);

  const loadCandle = async (ticker) => {
    if (candles[ticker]) return;
    try {
      const d = await api.getCandles(ticker, "1mo", "1d");
      setCandles(c=>({...c, [ticker]: d.candles||[]}));
    } catch {}
  };

  // Live metrics
  const posiciones = portafolio.posiciones || [];
  const totalValor = posiciones.reduce((s,p)=>{
    const live = prices[p.ticker]?.price || p.precio_actual || 0;
    return s + live * (p.acciones||0);
  }, 0);
  const totalCosto = posiciones.reduce((s,p)=>s+(p.precio_promedio_compra||0)*(p.acciones||0), 0);
  const totalGP = totalValor - totalCosto;
  const totalGPpct = totalCosto>0 ? totalGP/totalCosto*100 : 0;
  const mejorPos = posiciones.reduce((best,p)=>{
    const pct = p.precio_promedio_compra>0 ? ((prices[p.ticker]?.price||p.precio_actual)-p.precio_promedio_compra)/p.precio_promedio_compra*100 : 0;
    return pct > (best?.pct||−Infinity) ? {...p, pct} : best;
  }, null);
  const peorPos = posiciones.reduce((worst,p)=>{
    const pct = p.precio_promedio_compra>0 ? ((prices[p.ticker]?.price||p.precio_actual)-p.precio_promedio_compra)/p.precio_promedio_compra*100 : 0;
    return pct < (worst?.pct||Infinity) ? {...p, pct} : worst;
  }, null);
  const totalDiv = dividendos.reduce((s,d)=>s+(d.monto_usd||0),0);

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

      {/* KPIs */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:10 }}>
        {[
          { label:"Valor total", value:fmtUSD(totalValor), color:C.g, icon:"fa-briefcase" },
          { label:"G/P total", value:fmtUSD(totalGP), color:totalGP>=0?C.g:C.r, icon:"fa-chart-line", sub:fmtPct(totalGPpct) },
          { label:"Mejor posición", value:mejorPos?.ticker||"—", color:C.t, icon:"fa-trophy", sub:mejorPos?fmtPct(mejorPos.pct):"" },
          { label:"Dividendos totales", value:fmtUSD(totalDiv), color:C.p, icon:"fa-coins" },
          { label:"Posiciones activas", value:posiciones.length, color:C.a, icon:"fa-layer-group" },
        ].map(m=>(
          <div key={m.label} style={{ background:C.bg2, border:`1px solid ${C.border}`,
            borderTop:`2.5px solid ${m.color}`, borderRadius:10, padding:"12px 14px" }}>
            <div style={{ width:30, height:30, borderRadius:7, background:`${m.color}22`,
              display:"flex", alignItems:"center", justifyContent:"center", marginBottom:8 }}>
              <i className={`fas ${m.icon}`} style={{ color:m.color, fontSize:13 }} />
            </div>
            <div style={{ fontSize:9, color:C.text3, textTransform:"uppercase", letterSpacing:".07em", marginBottom:3 }}>{m.label}</div>
            <div style={{ fontSize:18, fontWeight:700, color:m.color }}>{m.value}</div>
            {m.sub && <div style={{ fontSize:10, color:m.color, opacity:.8 }}>{m.sub}</div>}
          </div>
        ))}
      </div>

      {/* Distribución + detalle posición */}
      <div style={{ display:"grid", gridTemplateColumns:"300px 1fr", gap:12 }}>
        <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, padding:14 }}>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:12 }}>
            <i className="fas fa-chart-pie" style={{ color:C.b, marginRight:6 }} />Distribución
          </div>
          <PortfolioChart posiciones={posiciones} prices={prices} size={160} />
        </div>

        <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, padding:14 }}>
          <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:12 }}>
            <i className="fas fa-chart-candlestick" style={{ color:C.g, marginRight:6 }} />
            {selectedPos ? `Gráfico ${selectedPos.ticker}` : "Selecciona una posición"}
          </div>
          {selectedPos && candles[selectedPos.ticker]
            ? <CandleChart candles={candles[selectedPos.ticker]} height={180} />
            : <div style={{ height:180, display:"flex", alignItems:"center", justifyContent:"center",
                color:C.text3, fontSize:11, flexDirection:"column", gap:8 }}>
                <i className="fas fa-mouse-pointer" style={{ fontSize:24, color:C.text3 }} />
                Haz clic en una posición para ver el gráfico
              </div>}
        </div>
      </div>

      {/* Tabs: posiciones, broker, dividendos, transacciones */}
      <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, overflow:"hidden" }}>
        <div style={{ display:"flex", alignItems:"center", padding:"10px 14px", borderBottom:`1px solid ${C.border}`, gap:4 }}>
          {["posiciones","broker","dividendos","transacciones"].map(t=>(
            <button key={t} onClick={()=>setTab(t)}
              style={{ padding:"5px 12px", borderRadius:6, fontSize:10, cursor:"pointer",
                border:`1px solid ${tab===t?C.g2:C.border}`,
                background:tab===t?C.g2:"transparent",
                color:tab===t?C.g:C.text2, textTransform:"capitalize" }}>
              {t.charAt(0).toUpperCase()+t.slice(1)}
            </button>
          ))}
          <span style={{ marginLeft:"auto", fontSize:10, color:C.text3 }}>
            {tab==="posiciones"&&`${posiciones.length} posiciones`}
            {tab==="broker"&&`${brokerPos.length} en Alpaca`}
            {tab==="dividendos"&&`${dividendos.length} pagos`}
            {tab==="transacciones"&&`${transacciones.length} registros`}
          </span>
        </div>

        <div style={{ overflowX:"auto", maxHeight:280, overflowY:"auto" }}>
          {tab==="posiciones" && (
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
              <thead><tr>
                {["","Ticker","Nombre","Acciones","P. Compra","P. Actual","Valor USD","G/P USD","G/P %","Acción"].map(h=>(
                  <th key={h} style={{ padding:"7px 10px", background:C.bg3, color:C.text3,
                    fontWeight:600, textAlign:"left", fontSize:9, textTransform:"uppercase",
                    borderBottom:`1px solid ${C.border}`, whiteSpace:"nowrap" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {posiciones.map(p=>{
                  const live = prices[p.ticker]?.price || p.precio_actual || 0;
                  const valor = live * (p.acciones||0);
                  const gp = valor - (p.precio_promedio_compra||0)*(p.acciones||0);
                  const gpPct = p.precio_promedio_compra>0 ? (live-p.precio_promedio_compra)/p.precio_promedio_compra*100 : 0;
                  const sel = selectedPos?.ticker === p.ticker;
                  return (
                    <tr key={p.ticker} onClick={()=>{setSelectedPos(p);loadCandle(p.ticker);}}
                      style={{ cursor:"pointer", background:sel?"rgba(23,204,133,.05)":"transparent" }}>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <div style={{ width:26, height:26, borderRadius:6, background:TICK_COLS[p.ticker]||C.bg4,
                          display:"flex", alignItems:"center", justifyContent:"center",
                          fontSize:8, fontWeight:700, color:"#fff" }}>{p.ticker}</div>
                      </td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:700, color:sel?C.g:C.text, fontFamily:"monospace" }}>{p.ticker}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2, maxWidth:140, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{p.nombre}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2, fontFamily:"monospace" }}>{fmtAcc(p.acciones)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2 }}>{fmtUSD(p.precio_promedio_compra)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.g, fontWeight:600 }}>{fmtUSD(live)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:700, color:C.text }}>{fmtUSD(valor)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:gp>=0?C.g:C.r, fontWeight:600 }}>{fmtUSD(gp)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <span style={{ padding:"2px 7px", borderRadius:6, fontSize:10, fontWeight:700,
                          background:gpPct>=0?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)",
                          color:gpPct>=0?C.g:C.r }}>{fmtPct(gpPct)}</span>
                      </td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <button onClick={e=>{e.stopPropagation();actions.openPanel("ordenes");}}
                          style={{ background:C.g2,color:"#fff",border:"none",borderRadius:5,padding:"3px 8px",fontSize:9,cursor:"pointer",fontWeight:700 }}>
                          Operar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr style={{ background:C.bg3 }}>
                  <td colSpan={6} style={{ padding:"8px 10px", fontSize:11, fontWeight:700, color:C.text }}>TOTAL</td>
                  <td style={{ padding:"8px 10px", fontWeight:700, color:C.g }}>{fmtUSD(totalValor)}</td>
                  <td style={{ padding:"8px 10px", fontWeight:700, color:totalGP>=0?C.g:C.r }}>{fmtUSD(totalGP)}</td>
                  <td style={{ padding:"8px 10px", fontWeight:700, color:totalGPpct>=0?C.g:C.r }}>{fmtPct(totalGPpct)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          )}

          {tab==="broker" && (
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
              <thead><tr>
                {["Symbol","Qty","Avg Entry","Current Price","Market Value","P&L","P&L %"].map(h=>(
                  <th key={h} style={{ padding:"7px 10px", background:C.bg3, color:C.text3, fontWeight:600, textAlign:"left", fontSize:9, textTransform:"uppercase", borderBottom:`1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {brokerPos.map((p,i)=>{
                  const pl = parseFloat(p.unrealized_pl||0);
                  const plpct = parseFloat(p.unrealized_plpc||0)*100;
                  return (
                    <tr key={i}>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:700, color:C.g }}>{p.symbol||p.ticker}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2, fontFamily:"monospace" }}>{parseFloat(p.qty||p.acciones||0).toFixed(6)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2 }}>{fmtUSD(p.avg_entry_price||p.precio_promedio_compra)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.g }}>{fmtUSD(p.current_price||p.precio_actual)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:700, color:C.text }}>{fmtUSD(p.market_value||p.valor_total_usd)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:pl>=0?C.g:C.r, fontWeight:600 }}>{fmtUSD(pl)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <span style={{ padding:"2px 7px", borderRadius:6, fontSize:10, fontWeight:700, background:plpct>=0?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)", color:plpct>=0?C.g:C.r }}>{fmtPct(plpct)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {tab==="dividendos" && (
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
              <thead><tr>
                {["#","Ticker","Acciones en fecha","Monto USD","Fecha pago"].map(h=>(
                  <th key={h} style={{ padding:"7px 10px", background:C.bg3, color:C.text3, fontWeight:600, textAlign:"left", fontSize:9, textTransform:"uppercase", borderBottom:`1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {dividendos.map((d,i)=>(
                  <tr key={d.id}>
                    <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3 }}>#{d.id}</td>
                    <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:700, color:C.p }}>{d.ticker}</td>
                    <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2 }}>{parseFloat(d.acciones_en_fecha||0).toFixed(4)}</td>
                    <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.g, fontWeight:600 }}>{fmtUSD(d.monto_usd)}</td>
                    <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3, fontSize:10 }}>{d.pago_date?.slice(0,10)}</td>
                  </tr>
                ))}
                {dividendos.length === 0 && <tr><td colSpan={5} style={{ padding:"20px", textAlign:"center", color:C.text3, fontSize:11 }}>Sin dividendos registrados</td></tr>}
              </tbody>
            </table>
          )}

          {tab==="transacciones" && (
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
              <thead><tr>
                {["#","Tipo","Monto USD","Método","Estado","Descripción","Fecha"].map(h=>(
                  <th key={h} style={{ padding:"7px 10px", background:C.bg3, color:C.text3, fontWeight:600, textAlign:"left", fontSize:9, textTransform:"uppercase", borderBottom:`1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {transacciones.map(t=>{
                  const es_dep = t.tipo==="deposito";
                  return (
                    <tr key={t.id}>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3 }}>#{t.id}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <span style={{ padding:"2px 8px", borderRadius:6, fontSize:9, fontWeight:700,
                          background:es_dep?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)",
                          color:es_dep?C.g:C.r }}>{t.tipo?.toUpperCase()}</span>
                      </td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:es_dep?C.g:C.r, fontWeight:700 }}>{fmtUSD(t.monto_usd)}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3, fontSize:10 }}>{t.metodo}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <span style={{ padding:"2px 7px", borderRadius:6, fontSize:9, fontWeight:700,
                          background:t.estado==="completed"?"rgba(23,204,133,.15)":"rgba(245,166,35,.15)",
                          color:t.estado==="completed"?C.g:C.a }}>{t.estado}</span>
                      </td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2, fontSize:10 }}>{t.descripcion}</td>
                      <td style={{ padding:"7px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3, fontSize:10 }}>{t.fecha?.slice(0,16)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}
