// components/layout/Sidebar.jsx
import React from "react";
import { useStore } from "../../store/store";

const C = { bg2:"#111820", border:"#2a3545", g:"#17cc85", g2:"#12a068", g1:"#0D7A4E",
  text:"#dde4f0", text2:"#8fa0b8", text3:"#576880", text4:"#3a4e65", bg3:"#171f2a", bg4:"#1E2835", bg5:"#252f3e" };

const NAV_ITEMS = [
  { section: "Inversiones", items: [
    { key:"dashboard", icon:"fa-tachometer-alt", label:"Dashboard" },
    { key:"mercado", icon:"fa-chart-candlestick", label:"Mercado Live" },
    { key:"portafolio", icon:"fa-briefcase", label:"Portafolio" },
    { key:"robo", icon:"fa-robot", label:"Robo-Advisor IA", badge:"IA", panel:"robo" },
    { key:"ordenes", icon:"fa-bolt", label:"Órdenes", badgeKey:"ordenes" },
    { key:"depositos", icon:"fa-piggy-bank", label:"Depósitos / Retiros" },
    { key:"dividendos", icon:"fa-coins", label:"Dividendos" },
  ]},
  { section: "Seguridad", items: [
    { key:"kyc", icon:"fa-id-card", label:"KYC / Verificación", panel:"kyc" },
    { key:"aml", icon:"fa-shield-alt", label:"AML / OFAC" },
    { key:"mfa", icon:"fa-lock", label:"Seguridad MFA" },
    { key:"crypto", icon:"fa-key", label:"Firmas ECDSA" },
  ]},
  { section: "Fiscal / Admin", items: [
    { key:"fiscal", icon:"fa-file-invoice-dollar", label:"Reportes Fiscales", panel:"fiscal" },
    { key:"auditoria", icon:"fa-list-check", label:"Auditoría", panel:"audit" },
    { key:"admin", icon:"fa-user-shield", label:"Owner Portal" },
    { key:"config", icon:"fa-cog", label:"Configuración" },
  ]},
];

export default function Sidebar() {
  const { state, actions } = useStore();

  return (
    <aside style={{ background: C.bg2, borderRight: `1px solid ${C.border}`, overflowY: "auto", padding: "12px 0" }}>
      {NAV_ITEMS.map(section => (
        <div key={section.section} style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: C.text4, textTransform: "uppercase",
            letterSpacing: ".12em", padding: "0 14px", marginBottom: 6 }}>
            {section.section}
          </div>
          {section.items.map(item => {
            const isActive = state.activeNav === item.key;
            const badge = item.badge || (item.badgeKey === "ordenes" ? state.ordenes.length : undefined);
            return (
              <div key={item.key}
                onClick={() => {
                  actions.setNav(item.key);
                  if (item.panel) actions.openPanel(item.panel);
                }}
                style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 14px",
                  cursor: "pointer", fontSize: 11, transition: "all .18s",
                  color: isActive ? C.g : C.text2,
                  borderLeft: isActive ? `3px solid ${C.g2}` : "3px solid transparent",
                  background: isActive ? "rgba(13,122,78,.12)" : "transparent",
                  fontWeight: isActive ? 600 : 400 }}>
                <i className={`fas ${item.icon}`} style={{ width: 15, textAlign: "center", fontSize: 12 }} />
                <span style={{ flex: 1 }}>{item.label}</span>
                {badge !== undefined && (
                  <span style={{ background: isActive ? C.g1 : C.bg5, fontSize: 9,
                    padding: "2px 5px", borderRadius: 8,
                    color: isActive ? C.g : C.text3 }}>
                    {badge}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ))}

      {/* DB / Infra status */}
      <div style={{ margin: "12px 10px 0", padding: 9, background: C.bg3,
        borderRadius: 6, border: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 8, color: C.text4, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
          Infraestructura
        </div>
        <div style={{ fontSize: 10, color: C.g, fontWeight: 600 }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: C.g,
            display: "inline-block", marginRight: 4, animation: "blink 2s infinite" }} />
          FastAPI · SQLAlchemy
        </div>
        <div style={{ fontSize: 9, color: C.text3, marginTop: 2 }}>Alpaca Paper Trading</div>
        <div style={{ fontSize: 9, color: C.text3 }}>Claude API · Robo-Advisor</div>
        <div style={{ fontSize: 9, color: C.text3 }}>ECDSA P-256 · AML · MFA · Redis</div>
      </div>
    </aside>
  );
}
