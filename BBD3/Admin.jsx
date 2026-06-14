// pages/Admin.jsx — Owner Portal: métricas globales, usuarios, config sistema
import React, { useState, useEffect } from "react";
import { useStore } from "../store/store";
import api from "../services/api";

const C = { bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",t:"#26c6da",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880" };
const fmtUSD = n=>`$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

export default function Admin() {
  const { state } = useStore();
  const { metricas } = state;
  const [health, setHealth] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [configPagos, setConfigPagos] = useState({});
  const [tab, setTab] = useState("sistema");

  useEffect(()=>{
    fetch("/api/v1/health").then(r=>r.json()).then(setHealth).catch(()=>{});
    api.getAuditoria().then(setAuditLogs).catch(()=>{});
    fetch("/api/v1/pagos/config").then(r=>r.json()).then(setConfigPagos).catch(()=>{});
  },[]);

  const StatusDot = ({ok})=>(
    <span style={{display:"inline-block",width:8,height:8,borderRadius:"50%",
      background:ok?C.g:C.r,marginRight:6,animation:"blink 2s infinite"}} />
  );

  return (
    <div style={{display:"flex",flexDirection:"column",gap:12}}>

      <div style={{fontSize:16,fontWeight:500,color:C.text,marginBottom:4}}>
        <i className="fas fa-user-shield" style={{color:C.p,marginRight:8}} />Owner Portal
      </div>

      {/* System health */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
        {[
          {label:"Estado sistema",value:health?.status==="ok"?"Operativo":"Verificando…",color:health?.status==="ok"?C.g:C.a,icon:"fa-server"},
          {label:"Versión API",value:health?.version||"1.0.0",color:C.b,icon:"fa-code-branch"},
          {label:"Broker",value:health?.services?.broker||"alpaca_paper",color:C.t,icon:"fa-building-columns"},
          {label:"IA / Robo-Advisor",value:health?.services?.ia||"claude_ready",color:C.p,icon:"fa-robot"},
        ].map(m=>(
          <div key={m.label} style={{background:C.bg2,border:`1px solid ${C.border}`,borderTop:`2.5px solid ${m.color}`,borderRadius:10,padding:"12px 14px"}}>
            <div style={{width:30,height:30,borderRadius:7,background:`${m.color}22`,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:8}}>
              <i className={`fas ${m.icon}`} style={{color:m.color,fontSize:13}} />
            </div>
            <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",letterSpacing:".07em",marginBottom:3}}>{m.label}</div>
            <div style={{fontSize:14,fontWeight:700,color:m.color}}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:4}}>
        {["sistema","apis","metricas","logs"].map(t=>(
          <button key={t} onClick={()=>setTab(t)}
            style={{padding:"7px 14px",borderRadius:7,fontSize:11,cursor:"pointer",
              border:`1px solid ${tab===t?C.g2:C.border}`,
              background:tab===t?C.g2:"transparent",
              color:tab===t?C.g:C.text2,textTransform:"capitalize"}}>
            {t.charAt(0).toUpperCase()+t.slice(1)}
          </button>
        ))}
      </div>

      {tab==="sistema" && (
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:12}}>
              <i className="fas fa-microchip" style={{color:C.g,marginRight:6}} />Infraestructura
            </div>
            {[
              ["FastAPI","Python 3.12","ok"],
              ["SQLAlchemy","13 tablas · SQLite/PostgreSQL","ok"],
              ["Redis cache","Fallback en memoria","warn"],
              ["WebSocket","Precios cada 4s","ok"],
              ["ECDSA P-256","Firma de órdenes activa","ok"],
              ["bcrypt","Passwords hasheados","ok"],
              ["MFA/TOTP","Disponible, no activado","warn"],
              ["Nginx","Config lista (deploy)","ok"],
              ["Docker","Compose listo","ok"],
            ].map(([l,v,s])=>(
              <div key={l} style={{display:"flex",alignItems:"center",padding:"7px 0",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                <StatusDot ok={s==="ok"} />
                <span style={{flex:1,fontSize:11,color:C.text2}}>{l}</span>
                <span style={{fontSize:10,color:s==="ok"?C.g:C.a}}>{v}</span>
              </div>
            ))}
          </div>

          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:12}}>
              <i className="fas fa-rocket" style={{color:C.b,marginRight:6}} />Deploy rápido
            </div>
            {[
              {name:"Railway (recomendado)",time:"3 min",cmd:"railway up",color:C.g},
              {name:"Render.com",time:"5 min",cmd:"render deploy",color:C.b},
              {name:"VPS Ubuntu 22.04",time:"15 min",cmd:"bash setup_vps.sh",color:C.a},
              {name:"Docker Compose",time:"2 min",cmd:"docker-compose up -d",color:C.p},
            ].map(d=>(
              <div key={d.name} style={{padding:"10px 12px",background:C.bg4,border:`1px solid ${C.border}`,borderRadius:8,marginBottom:8}}>
                <div style={{display:"flex",alignItems:"center",gap:8}}>
                  <div style={{fontSize:11,fontWeight:600,color:C.text,flex:1}}>{d.name}</div>
                  <span style={{fontSize:9,padding:"2px 7px",borderRadius:5,background:`${d.color}22`,color:d.color}}>{d.time}</span>
                </div>
                <code style={{display:"block",marginTop:5,fontSize:10,color:d.color,fontFamily:"monospace"}}>{d.cmd}</code>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab==="apis" && (
        <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
          <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
            <i className="fas fa-plug" style={{color:C.t,marginRight:6}} />Estado de integraciones
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
            {[
              {name:"Alpaca Paper Trading",key:"ALPACA_API_KEY",status:"demo",desc:"Órdenes fraccionadas reales",url:"https://app.alpaca.markets"},
              {name:"Claude API",key:"CLAUDE_API_KEY",status:"demo",desc:"Robo-Advisor con Prompts JSON",url:"https://console.anthropic.com"},
              {name:"Stripe",key:"STRIPE_SECRET_KEY",status:configPagos.stripe?"active":"config",desc:"Pagos con tarjeta internacional",url:"https://dashboard.stripe.com"},
              {name:"MercadoPago",key:"MERCADOPAGO_ACCESS_TOKEN",status:configPagos.mercadopago?"active":"config",desc:"Pagos LATAM",url:"https://mercadopago.com.pe/developers"},
              {name:"OpenSanctions AML",key:"—",status:"active",desc:"Verificación listas sanción",url:"https://opensanctions.org"},
              {name:"Yahoo Finance",key:"—",status:"active",desc:"Precios reales sin API key",url:"https://finance.yahoo.com"},
              {name:"Coinbase Commerce",key:"COINBASE_COMMERCE_KEY",status:configPagos.crypto?"active":"config",desc:"Depósitos crypto USDC",url:"https://commerce.coinbase.com"},
              {name:"PostgreSQL+TimescaleDB",key:"DATABASE_URL",status:"sqlite_dev",desc:"Cambiar a PostgreSQL en prod",url:"https://www.timescale.com"},
            ].map(a=>{
              const col = a.status==="active"?C.g:a.status==="demo"?C.b:C.a;
              const lbl = a.status==="active"?"ACTIVO":a.status==="demo"?"DEMO":"CONFIGURAR";
              return (
                <div key={a.name} style={{padding:"12px 14px",background:C.bg4,border:`1px solid ${C.border}`,borderRadius:9}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
                    <StatusDot ok={a.status==="active"||a.status==="demo"} />
                    <span style={{fontSize:12,fontWeight:600,color:C.text,flex:1}}>{a.name}</span>
                    <span style={{fontSize:8,padding:"2px 7px",borderRadius:5,background:`${col}22`,color:col,fontWeight:700}}>{lbl}</span>
                  </div>
                  <div style={{fontSize:10,color:C.text3,marginBottom:6}}>{a.desc}</div>
                  {a.key!=="—" && <code style={{fontSize:9,color:C.a,fontFamily:"monospace"}}>{a.key}</code>}
                  <div style={{marginTop:6}}>
                    <a href={a.url} target="_blank" rel="noreferrer" style={{fontSize:9,color:C.b}}>Documentación →</a>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab==="metricas" && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10}}>
          {[
            ["Portafolio total",fmtUSD(metricas.valor_portafolio||0),C.g],
            ["G/P total",fmtUSD(metricas.ganancia_total||0),(metricas.ganancia_total||0)>=0?C.g:C.r],
            ["Saldo disponible",fmtUSD(metricas.saldo_disponible||0),C.b],
            ["Órdenes ejecutadas",metricas.ordenes_total||0,C.a],
            ["Posiciones activas",metricas.posiciones||0,C.p],
            ["Alertas nuevas",metricas.alertas_nuevas||0,C.r],
            ["G/P %",`${(metricas.ganancia_pct||0).toFixed(3)}%`,(metricas.ganancia_pct||0)>=0?C.g:C.r],
            ["Dividendos",fmtUSD(metricas.dividendos_total||0),C.t],
            ["Asientos contables","—",C.text3],
          ].map(([l,v,col])=>(
            <div key={l} style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:"14px 16px"}}>
              <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",letterSpacing:".07em",marginBottom:4}}>{l}</div>
              <div style={{fontSize:20,fontWeight:700,color:col}}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {tab==="logs" && (
        <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,overflow:"hidden"}}>
          <div style={{padding:"12px 14px",borderBottom:`1px solid ${C.border}`,fontSize:12,fontWeight:600,color:C.text}}>
            <i className="fas fa-terminal" style={{color:C.g,marginRight:6}} />Audit log del sistema ({auditLogs.length} entradas)
          </div>
          <div style={{overflowY:"auto",maxHeight:400}}>
            {auditLogs.map(l=>(
              <div key={l.id} style={{display:"flex",gap:10,padding:"8px 14px",borderBottom:`1px solid rgba(42,53,69,.3)`,fontSize:10}}>
                <span style={{color:C.text3,minWidth:24}}>#{l.id}</span>
                <span style={{color:C.g,fontWeight:600,minWidth:160}}>{l.accion}</span>
                <span style={{padding:"1px 6px",borderRadius:4,background:"rgba(38,198,218,.1)",color:C.t,fontSize:9,height:"fit-content"}}>{l.modulo}</span>
                <span style={{flex:1,color:C.text2}}>{l.detalle}</span>
                <span style={{color:C.text3,minWidth:120,textAlign:"right"}}>{l.fecha?.slice(0,16)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
