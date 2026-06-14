// components/layout/TickerBar.jsx
import React from "react";
import { useStore } from "../../store/store";

export default function TickerBar() {
  const { state } = useStore();
  const entries = Object.entries(state.prices);
  if (!entries.length) return null;

  return (
    <div style={{ height: 26, background: "#171f2a", borderBottom: "1px solid #2a3545",
      overflow: "hidden", display: "flex", alignItems: "center" }}>
      <div style={{ display: "flex", gap: 28, animation: "ticker 45s linear infinite",
        whiteSpace: "nowrap", padding: "0 16px" }}>
        {[...entries, ...entries.slice(0, 6)].map(([t, d], i) => (
          <span key={`${t}_${i}`} style={{ fontSize: 10, display: "flex", gap: 6, alignItems: "center" }}>
            <b style={{ color: "#dde4f0" }}>{t}</b>
            <span style={{ color: (d.change_pct || 0) >= 0 ? "#17cc85" : "#f44336" }}>
              ${(d.price || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              {" "}{(d.change_pct || 0) >= 0 ? "+" : ""}{(d.change_pct || 0).toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
