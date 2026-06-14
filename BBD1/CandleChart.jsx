// components/charts/CandleChart.jsx
import React, { useMemo } from "react";

export default function CandleChart({ candles = [], height = 200, width = 680 }) {
  const data = useMemo(() => {
    if (!candles.length) return null;
    const recent = candles.slice(-80);
    const allH = recent.map(c => c.h); const allL = recent.map(c => c.l);
    const maxP = Math.max(...allH); const minP = Math.min(...allL);
    const range = maxP - minP || 1;
    const pad = 8;
    const cw = (width - pad * 2) / recent.length;
    const toY = (p) => pad + (1 - (p - minP) / range) * (height - pad * 2 - 20);
    // Price labels
    const labels = [];
    for (let i = 0; i <= 4; i++) {
      const price = minP + (range * i / 4);
      labels.push({ y: toY(price), price: price.toFixed(2) });
    }
    return { recent, cw, toY, labels, minP, maxP, range, pad };
  }, [candles, width, height]);

  if (!data) return (
    <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center",
      color: "#576880", fontSize: 11 }}>
      Cargando velas japonesas…
    </div>
  );

  const { recent, cw, toY, labels, pad } = data;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id="candleGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#17cc85" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#17cc85" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {labels.map((l, i) => (
        <g key={i}>
          <line x1={pad} y1={l.y} x2={width - pad} y2={l.y}
            stroke="rgba(255,255,255,.04)" strokeWidth={0.5} strokeDasharray="4,4" />
          <text x={width - 2} y={l.y + 3} textAnchor="end" fontSize={7} fill="#3a4e65">${l.price}</text>
        </g>
      ))}

      {/* Candles */}
      {recent.map((c, i) => {
        const x = pad + i * cw + cw * 0.15;
        const bw = Math.max(cw * 0.7, 1);
        const up = c.c >= c.o;
        const col = up ? "#17cc85" : "#f44336";
        const yO = toY(c.o); const yC = toY(c.c);
        const yH = toY(c.h); const yL = toY(c.l);
        const top = Math.min(yO, yC);
        const bh = Math.max(Math.abs(yO - yC), 1);
        return (
          <g key={i}>
            {/* Wick */}
            <line x1={x + bw / 2} y1={yH} x2={x + bw / 2} y2={yL}
              stroke={col} strokeWidth={0.8} opacity={0.8} />
            {/* Body */}
            <rect x={x} y={top} width={bw} height={bh}
              fill={col} rx={1} opacity={0.9} />
          </g>
        );
      })}

      {/* Last price line */}
      {recent.length > 0 && (() => {
        const last = recent[recent.length - 1];
        const y = toY(last.c);
        const up = last.c >= last.o;
        return (
          <g>
            <line x1={pad} y1={y} x2={width - 40} y2={y}
              stroke={up ? "#17cc85" : "#f44336"} strokeWidth={0.8}
              strokeDasharray="3,3" opacity={0.5} />
            <rect x={width - 42} y={y - 8} width={38} height={14} rx={3}
              fill={up ? "#17cc85" : "#f44336"} opacity={0.9} />
            <text x={width - 23} y={y + 3} textAnchor="middle" fontSize={7.5}
              fill="#fff" fontWeight="bold">${last.c.toFixed(2)}</text>
          </g>
        );
      })()}
    </svg>
  );
}
