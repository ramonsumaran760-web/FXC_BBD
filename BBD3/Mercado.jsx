// pages/Mercado.jsx — Mercado Live completo
import React, { useState, useEffect, useCallback } from "react";
import { useStore } from "../store/store";
import CandleChart from "../components/charts/CandleChart";
import api from "../services/api";

const C = { bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",border2:"#3a4a60",
  g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",t:"#26c6da",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880" };

const fmtUSD = n=>`$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const fmtPct = n=>`${n>=0?"+":""}${parseFloat(n||0).toFixed(2)}%`;
const fmtVol = n=>{ if(n>=1e9) return (n/1e9).toFixed(1)+"B"; if(n>=1e6) return (n/1e6).toFixed(1)+"M"; return n?.toLocaleString()||"—"; };

const SECTORES = ["Todos","Tecnología","Semiconductores","Automotriz","E-Commerce","Redes Sociales","Índice","Bonos","Materias Primas"];
const TICKERS_ALL = ["AAPL","MSFT","NVDA","TSLA","AMZN","GOOGL","META","SPY","QQQ","BND","VTI","GLD"];

export default function Mercado() {
  const { state, actions } = useStore();
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("Todos");
  const [sortBy, setSortBy] = useState("ticker");
  const [sortDir, setSortDir] = useState(1);
  const [selectedTicker, setSelectedTicker] = useState("AAPL");
  const [period, setPeriod] = useState("1mo");
  const [interval, setInterval] = useState("1d");
  const [activos, setActivos] = useState([]);
  const [candles, setCandles] = useState([]);
  const [loadingCandles, setLoadingCandles] = useState(false);
  const [tab, setTab] = useState("grafico");

  useEffect(() => {
    api.getActivos().then(setActivos).catch(()=>{});
    loadCandles(selectedTicker, period, interval);
  }, []);

  const loadCandles = async (t, p, i) => {
    setLoadingCandles(true);
    try {
      const d = await api.getCandles(t, p, i);
      setCandles(d.candles || []);
    } catch {}
    setLoadingCandles(false);
  };

  const selectTicker = (t) => {
    setSelectedTicker(t);
    loadCandles(t, period, interval);
  };

  const changePeriod = (p, i) => {
    setPeriod(p); setInterval(i);
    loadCandles(selectedTicker, p, i);
  };

  // Merge activos con prices en vivo
  const activosConPrecios = activos.map(a => ({
    ...a,
    precio_actual: state.prices[a.ticker]?.price || a.precio_actual || 0,
    variacion_pct: state.prices[a.ticker]?.change_pct ?? a.variacion_pct ?? 0,
  }));

  const filtered = activosConPrecios
    .filter(a => {
      const q = search.toLowerCase();
      const matchSearch = !q || a.ticker.toLowerCase().includes(q) || a.nombre?.toLowerCase().includes(q);
      const matchSector = sector === "Todos" || a.sector === sector;
      return matchSearch && matchSector;
    })
    .sort((a, b) => {
      let va = a[sortBy] || 0, vb = b[sortBy] || 0;
      if (typeof va === "string") return sortDir * va.localeCompare(vb);
      return sortDir * (va - vb);
    });

  const selectedActivo = activosConPrecios.find(a => a.ticker === selectedTicker);
  const selectedPrice = state.prices[selectedTicker];

  const Th = ({ label, key: k }) => (
    <th onClick={() => { if(sortBy === k) setSortDir(d=>-d); else { setSortBy(k); setSortDir(1); } }}
      style={{ padding:"7px 10px", background:C.bg3, color:C.text3, fontWeight:600, textAlign:"left",
        fontSize:9, textTransform:"uppercase", borderBottom:`1px solid ${C.border}`,
        cursor:"pointer", whiteSpace:"nowrap", userSelect:"none" }}>
      {label} {sortBy===k ? (sortDir>0?"↑":"↓") : ""}
    </th>
  );

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

      {/* Header + search */}
      <div style={{ display:"flex", alignItems:"center", gap:12 }}>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:16, fontWeight:500, color:C.text, marginBottom:2 }}>Mercado en vivo</div>
          <div style={{ fontSize:11, color:C.text3 }}>NYSE · NASDAQ · ETFs · Bonos · Materias primas</div>
        </div>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar ticker o nombre…"
          style={{ background:C.bg2, border:`1px solid ${C.border}`, color:C.text,
            padding:"8px 14px", borderRadius:8, fontSize:12, outline:"none", width:220 }} />
        <select value={sector} onChange={e=>setSector(e.target.value)}
          style={{ background:C.bg2, border:`1px solid ${C.border}`, color:C.text,
            padding:"8px 12px", borderRadius:8, fontSize:11, outline:"none" }}>
          {SECTORES.map(s=><option key={s}>{s}</option>)}
        </select>
      </div>

      {/* Layout: tabla izq + gráfico der */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 380px", gap:12 }}>

        {/* Tabla activos */}
        <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, overflow:"hidden" }}>
          <div style={{ padding:"10px 14px", borderBottom:`1px solid ${C.border}`, display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:11, fontWeight:600, color:C.text }}>
              <i className="fas fa-table" style={{ color:C.g, marginRight:6 }} />
              {filtered.length} activos
            </span>
            <span style={{ marginLeft:"auto", fontSize:10, color:C.text3 }}>
              <span style={{ display:"inline-block", width:8, height:8, borderRadius:"50%", background:C.g, marginRight:5, animation:"blink 1.5s infinite" }} />
              Precios actualizados
            </span>
          </div>
          <div style={{ overflowY:"auto", maxHeight:480 }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
              <thead>
                <tr>
                  <Th label="Ticker" key="ticker" />
                  <Th label="Nombre" key="nombre" />
                  <Th label="Precio" key="precio_actual" />
                  <Th label="Cambio%" key="variacion_pct" />
                  <Th label="Volumen" key="volumen" />
                  <Th label="Sector" key="sector" />
                  <th style={{ padding:"7px 10px", background:C.bg3, color:C.text3, fontWeight:600, fontSize:9, textTransform:"uppercase", borderBottom:`1px solid ${C.border}` }}>Acción</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(a => {
                  const up = a.variacion_pct >= 0;
                  const sel = a.ticker === selectedTicker;
                  return (
                    <tr key={a.ticker} onClick={()=>selectTicker(a.ticker)}
                      style={{ cursor:"pointer", background: sel ? "rgba(23,204,133,.06)" : "transparent" }}>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`,
                        fontWeight:700, color: sel ? C.g : C.text, fontFamily:"monospace" }}>{a.ticker}</td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text2, maxWidth:160, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{a.nombre}</td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, fontWeight:600, color:up?C.g:C.r, fontFamily:"monospace" }}>{fmtUSD(a.precio_actual)}</td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <span style={{ padding:"2px 7px", borderRadius:6, fontSize:10, fontWeight:700,
                          background:up?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)",
                          color:up?C.g:C.r }}>{fmtPct(a.variacion_pct)}</span>
                      </td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3, fontSize:10 }}>{fmtVol(a.volumen)}</td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)`, color:C.text3, fontSize:9 }}>{a.sector}</td>
                      <td style={{ padding:"8px 10px", borderBottom:`1px solid rgba(42,53,69,.3)` }}>
                        <button onClick={e=>{e.stopPropagation();actions.openPanel("ordenes");}}
                          style={{ background:C.g2, color:"#fff", border:"none", borderRadius:5,
                            padding:"3px 8px", fontSize:9, cursor:"pointer", fontWeight:700 }}>
                          Operar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Panel derecho: gráfico + info */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

          {/* Info activo seleccionado */}
          {selectedActivo && (
            <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, padding:14 }}>
              <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:10 }}>
                <div style={{ width:38, height:38, borderRadius:8, background:C.bg4,
                  display:"flex", alignItems:"center", justifyContent:"center",
                  fontWeight:700, fontSize:11, color:C.g, fontFamily:"monospace" }}>
                  {selectedActivo.ticker}
                </div>
                <div>
                  <div style={{ fontSize:13, fontWeight:600, color:C.text }}>{selectedActivo.nombre}</div>
                  <div style={{ fontSize:10, color:C.text3 }}>{selectedActivo.mercado} · {selectedActivo.sector}</div>
                </div>
                <div style={{ marginLeft:"auto", textAlign:"right" }}>
                  <div style={{ fontSize:20, fontWeight:700, color:selectedPrice?.change_pct>=0?C.g:C.r }}>
                    {fmtUSD(selectedActivo.precio_actual)}
                  </div>
                  <div style={{ fontSize:12, color:selectedPrice?.change_pct>=0?C.g:C.r }}>
                    {fmtPct(selectedActivo.variacion_pct)}
                  </div>
                </div>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6 }}>
                {[
                  ["Apertura", fmtUSD(selectedPrice?.open || selectedActivo.precio_apertura)],
                  ["Volumen", fmtVol(selectedActivo.volumen)],
                  ["Market Cap", selectedActivo.market_cap ? fmtVol(selectedActivo.market_cap) : "—"],
                  ["P/E Ratio", selectedActivo.pe_ratio?.toFixed(1) || "—"],
                ].map(([l,v])=>(
                  <div key={l} style={{ background:C.bg4, borderRadius:6, padding:"6px 10px" }}>
                    <div style={{ fontSize:9, color:C.text3, textTransform:"uppercase", marginBottom:2 }}>{l}</div>
                    <div style={{ fontSize:12, color:C.text, fontWeight:600 }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Gráfico */}
          <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, padding:14, flex:1 }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
              <span style={{ fontSize:11, fontWeight:600, color:C.text }}>
                <i className="fas fa-chart-candlestick" style={{ color:C.g, marginRight:5 }} />
                {selectedTicker}
              </span>
              <div style={{ display:"flex", gap:3 }}>
                {[["1d","1m","1m"],["5d","5d","5m"],["1mo","1mo","1d"],["3mo","3mo","1d"],["1y","1y","1wk"]].map(([lbl,p,i])=>(
                  <button key={lbl} onClick={()=>changePeriod(p,i)}
                    style={{ padding:"3px 7px", borderRadius:4, fontSize:9, cursor:"pointer",
                      border:`1px solid ${period===p?C.g2:C.border}`,
                      background:period===p?C.g2:"transparent",
                      color:period===p?"#fff":C.text2 }}>{lbl}</button>
                ))}
              </div>
            </div>
            {loadingCandles
              ? <div style={{ height:200, display:"flex", alignItems:"center", justifyContent:"center", color:C.text3, fontSize:11 }}>Cargando…</div>
              : <CandleChart candles={candles} height={200} />}
          </div>

          {/* Operar rápido */}
          <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:10, padding:14 }}>
            <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:10 }}>
              <i className="fas fa-bolt" style={{ color:C.a, marginRight:6 }} />
              Operar {selectedTicker}
            </div>
            <div style={{ display:"flex", gap:8 }}>
              <button onClick={()=>actions.openPanel("ordenes")}
                style={{ flex:1, background:C.g2, color:"#fff", border:"none", borderRadius:7,
                  padding:"9px", fontSize:11, fontWeight:700, cursor:"pointer",
                  boxShadow:"0 0 12px rgba(18,160,104,.3)" }}>
                <i className="fas fa-arrow-up" style={{ marginRight:5 }} />Comprar
              </button>
              <button onClick={()=>actions.openPanel("ordenes")}
                style={{ flex:1, background:C.r, color:"#fff", border:"none", borderRadius:7,
                  padding:"9px", fontSize:11, fontWeight:700, cursor:"pointer",
                  boxShadow:"0 0 12px rgba(244,67,54,.3)" }}>
                <i className="fas fa-arrow-down" style={{ marginRight:5 }} />Vender
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
