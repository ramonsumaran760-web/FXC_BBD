// components/charts/PortfolioChart.jsx
import React, { useMemo } from "react";

const COLORS = ["#17cc85","#2196f3","#ab47bc","#f5a623","#f44336","#26c6da","#ffb74d","#a5d6a7"];

export default function PortfolioChart({ posiciones = [], prices = {}, size = 160 }) {
  const data = useMemo(() => {
    const items = posiciones.map(p => ({
      ticker: p.ticker,
      valor: (prices[p.ticker]?.price || p.precio_actual || 0) * (p.acciones || 0),
    })).filter(p => p.valor > 0);
    const total = items.reduce((s, i) => s + i.valor, 0) || 1;
    return items.map((item, idx) => ({ ...item, pct: item.valor / total * 100, color: COLORS[idx % COLORS.length] }));
  }, [posiciones, prices]);

  if (!data.length) return (
    <div style={{ height: size, display: "flex", alignItems: "center", justifyContent: "center", color: "#576880", fontSize: 11 }}>
      Sin posiciones
    </div>
  );

  // SVG donut
  const cx = size / 2, cy = size / 2, r = size * 0.38, inner = size * 0.22;
  let angle = -90;
  const slices = data.map(d => {
    const startAngle = angle;
    const sweep = d.pct / 100 * 360;
    angle += sweep;
    const start = polarToXY(cx, cy, r, startAngle);
    const end = polarToXY(cx, cy, r, angle - 0.3);
    const large = sweep > 180 ? 1 : 0;
    const innerStart = polarToXY(cx, cy, inner, angle - 0.3);
    const innerEnd = polarToXY(cx, cy, inner, startAngle);
    return { ...d, path: `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y} L ${innerStart.x} ${innerStart.y} A ${inner} ${inner} 0 ${large} 0 ${innerEnd.x} ${innerEnd.y} Z` };
  });

  const total = data.reduce((s, d) => s + d.valor, 0);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} opacity={0.9}>
            <title>{s.ticker}: {s.pct.toFixed(1)}% — ${s.valor.toLocaleString("en-US", { maximumFractionDigits: 0 })}</title>
          </path>
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fill="#dde4f0" fontSize={9} fontWeight="600">Total</text>
        <text x={cx} y={cy + 8} textAnchor="middle" fill="#17cc85" fontSize={10} fontWeight="700">
          ${(total / 1000).toFixed(1)}k
        </text>
      </svg>
      {/* Legend */}
      <div style={{ flex: 1 }}>
        {data.map(d => (
          <div key={d.ticker} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: d.color, flexShrink: 0 }} />
            <span style={{ fontSize: 10, color: "#8fa0b8", flex: 1 }}>{d.ticker}</span>
            <span style={{ fontSize: 10, color: "#dde4f0", fontWeight: 600 }}>{d.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function polarToXY(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
