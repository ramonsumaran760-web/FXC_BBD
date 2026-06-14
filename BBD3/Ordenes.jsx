// pages/Ordenes.jsx — Historial completo de órdenes con filtros y estadísticas
import React, { useState, useEffect } from "react";
import { useStore } from "../store/store";
import api from "../services/api";

const C = { bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880" };
const fmtUSD = n=>`$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

export default function Ordenes() {
  const { state, actions } = useStore();
  const { ordenes } = state;
  const [filtroTipo, setFiltroTipo] = useState("todos");
  const [filtroEstado, setFiltroEstado] = useState("todos");
  const [filtroTicker, setFiltroTicker] = useState("");
  const [sortBy, setSortBy] = useState("creado");
  const [sortDir, setSortDir] = useState(-1);
  const [cancelando, setCancelando] = useState(null);

  useEffect(() => { actions.loadOrdenes(); }, []);

  const filtered = ordenes
    .filter(o=>{
      if(filtroTipo!=="todos" && o.tipo!==filtroTipo) return false;
      if(filtroEstado!=="todos" && o.estado!==filtroEstado) return false;
      if(filtroTicker && !o.ticker.toLowerCase().includes(filtroTicker.toLowerCase())) return false;
      return true;
    })
    .sort((a,b)=>{
      const va = a[sortBy]||"", vb = b[sortBy]||"";
      if(typeof va==="string") return sortDir*va.localeCompare(vb);
      return sortDir*(va-vb);
    });

  // Stats
  const totalBuy = ordenes.filter(o=>o.tipo==="buy" && o.estado==="filled").reduce((s,o)=>s+o.monto_usd,0);
  const totalSell = ordenes.filter(o=>o.tipo==="sell" && o.estado==="filled").reduce((s,o)=>s+o.monto_usd,0);
  const nFilled = ordenes.filter(o=>o.estado==="filled").length;
  const nFirmaOk = ordenes.filter(o=>o.firma_verificada).length;
  const nAMLok = ordenes.filter(o=>o.aml_check==="clear").length;
  const tickersUnicos = [...new Set(ordenes.map(o=>o.ticker))];

  const cancelar = async (id) => {
    setCancelando(id);
    try { await api.cancelarOrden(id); actions.loadOrdenes(); actions.toast("Orden cancelada"); }
    catch(e) { actions.toast(e.message, "error"); }
    setCancelando(null);
  };

  const Th = ({label,k})=>(
    <th onClick={()=>{if(sortBy===k)setSortDir(d=>-d);else{setSortBy(k);setSortDir(-1);}}}
      style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,textAlign:"left",fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`,cursor:"pointer",whiteSpace:"nowrap"}}>
      {label} {sortBy===k?(sortDir>0?"↑":"↓"):""}
    </th>
  );

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>

      {/* KPIs */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:10 }}>
        {[
          {label:"Total comprado",value:fmtUSD(totalBuy),color:C.g,icon:"fa-arrow-up"},
          {label:"Total vendido",value:fmtUSD(totalSell),color:C.r,icon:"fa-arrow-down"},
          {label:"Órdenes ejecutadas",value:nFilled,color:C.b,icon:"fa-check-circle"},
          {label:"Firmas ECDSA OK",value:`${nFirmaOk}/${ordenes.length}`,color:C.p,icon:"fa-key"},
          {label:"AML clear",value:`${nAMLok}/${ordenes.length}`,color:C.a,icon:"fa-shield-alt"},
        ].map(m=>(
          <div key={m.label} style={{background:C.bg2,border:`1px solid ${C.border}`,borderTop:`2.5px solid ${m.color}`,borderRadius:10,padding:"12px 14px"}}>
            <div style={{width:30,height:30,borderRadius:7,background:`${m.color}22`,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:8}}>
              <i className={`fas ${m.icon}`} style={{color:m.color,fontSize:13}} />
            </div>
            <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",letterSpacing:".07em",marginBottom:3}}>{m.label}</div>
            <div style={{fontSize:18,fontWeight:700,color:m.color}}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:"12px 14px",display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <span style={{fontSize:11,color:C.text3,fontWeight:600}}>Filtrar:</span>
        <select value={filtroTipo} onChange={e=>setFiltroTipo(e.target.value)}
          style={{background:C.bg4,border:`1px solid ${C.border}`,color:C.text,padding:"6px 10px",borderRadius:6,fontSize:11,outline:"none"}}>
          <option value="todos">Todos los tipos</option>
          <option value="buy">Solo Compras</option>
          <option value="sell">Solo Ventas</option>
        </select>
        <select value={filtroEstado} onChange={e=>setFiltroEstado(e.target.value)}
          style={{background:C.bg4,border:`1px solid ${C.border}`,color:C.text,padding:"6px 10px",borderRadius:6,fontSize:11,outline:"none"}}>
          <option value="todos">Todos los estados</option>
          <option value="filled">Ejecutadas</option>
          <option value="pending">Pendientes</option>
          <option value="cancelled">Canceladas</option>
        </select>
        <select value={filtroTicker} onChange={e=>setFiltroTicker(e.target.value)}
          style={{background:C.bg4,border:`1px solid ${C.border}`,color:C.text,padding:"6px 10px",borderRadius:6,fontSize:11,outline:"none"}}>
          <option value="">Todos los tickers</option>
          {tickersUnicos.map(t=><option key={t} value={t}>{t}</option>)}
        </select>
        <span style={{marginLeft:"auto",fontSize:11,color:C.text3}}>{filtered.length} órdenes</span>
        <button onClick={()=>actions.openPanel("ordenes")}
          style={{background:C.g2,color:"#fff",border:"none",borderRadius:7,padding:"7px 14px",fontSize:11,fontWeight:700,cursor:"pointer",boxShadow:"0 0 10px rgba(18,160,104,.3)"}}>
          <i className="fas fa-plus" style={{marginRight:5}} />Nueva orden
        </button>
      </div>

      {/* Tabla órdenes */}
      <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,overflow:"hidden"}}>
        <div style={{overflowX:"auto",maxHeight:400,overflowY:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
            <thead>
              <tr>
                <Th label="#" k="id" />
                <Th label="Ticker" k="ticker" />
                <Th label="Tipo" k="tipo" />
                <Th label="Tipo orden" k="tipo_orden" />
                <Th label="Monto USD" k="monto_usd" />
                <Th label="Acciones" k="acciones" />
                <Th label="Precio ejec." k="precio_ejecucion" />
                <Th label="Estado" k="estado" />
                <Th label="Broker" k="broker" />
                <th style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>Firma</th>
                <th style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`}}>AML</th>
                <Th label="Fecha" k="creado" />
                <th style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`}}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(o=>(
                <tr key={o.id}>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3}}>#{o.id}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,fontWeight:700,color:C.text,fontFamily:"monospace"}}>{o.ticker}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                    <span style={{padding:"2px 8px",borderRadius:6,fontSize:9,fontWeight:700,
                      background:o.tipo==="buy"?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)",
                      color:o.tipo==="buy"?C.g:C.r}}>{o.tipo?.toUpperCase()}</span>
                  </td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:10}}>{o.tipo_orden||"market"}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text,fontWeight:600}}>{fmtUSD(o.monto_usd)}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text2,fontFamily:"monospace",fontSize:10}}>{parseFloat(o.acciones||0).toFixed(8)}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text2}}>{fmtUSD(o.precio_ejecucion)}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                    <span style={{padding:"2px 7px",borderRadius:6,fontSize:9,fontWeight:700,
                      background:o.estado==="filled"?"rgba(23,204,133,.15)":o.estado==="pending"?"rgba(245,166,35,.15)":"rgba(244,67,54,.1)",
                      color:o.estado==="filled"?C.g:o.estado==="pending"?C.a:C.r}}>{o.estado}</span>
                  </td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:9}}>{o.broker}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:o.firma_verificada?C.g:C.r,fontSize:10}}>
                    {o.firma_verificada?"✓ P-256":"✗"}
                  </td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:o.aml_check==="clear"?C.g:C.a,fontSize:9}}>{o.aml_check||"—"}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:9}}>{o.creado?.slice(0,16)}</td>
                  <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                    {o.estado==="pending" && (
                      <button onClick={()=>cancelar(o.id)} disabled={cancelando===o.id}
                        style={{background:C.r,color:"#fff",border:"none",borderRadius:5,padding:"3px 8px",fontSize:9,cursor:"pointer",opacity:cancelando===o.id?0.6:1}}>
                        {cancelando===o.id?"…":"Cancelar"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length===0 && (
                <tr><td colSpan={13} style={{padding:"30px",textAlign:"center",color:C.text3,fontSize:11}}>Sin órdenes con los filtros actuales</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Breakdown por ticker */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:10}}>
        {tickersUnicos.slice(0,8).map(tick=>{
          const ords = ordenes.filter(o=>o.ticker===tick);
          const totalInv = ords.filter(o=>o.tipo==="buy").reduce((s,o)=>s+o.monto_usd,0);
          return (
            <div key={tick} style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:"12px 14px"}}>
              <div style={{fontSize:14,fontWeight:700,color:C.g,marginBottom:4,fontFamily:"monospace"}}>{tick}</div>
              <div style={{fontSize:10,color:C.text3,marginBottom:2}}>{ords.length} órdenes</div>
              <div style={{fontSize:12,color:C.text,fontWeight:600}}>{fmtUSD(totalInv)}</div>
              <div style={{fontSize:9,color:C.text3}}>invertido total</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
