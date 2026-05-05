"use client";

import styles from "./InfoPanel.module.css";
import type { InfoPanelState } from "@/types/ocean";

interface InfoPanelProps {
  state: InfoPanelState;
  onClose: () => void;
}

export default function InfoPanel({ state, onClose }: InfoPanelProps) {
  if (!state.visible) return null;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.type}>{state.type}</span>
        <button className={styles.close} onClick={onClose} aria-label="Cerrar panel">
          ✕ cerrar
        </button>
      </div>
      <div className={styles.body}>
        {state.rows.map((row, i) => (
          <div key={i} className={styles.row}>
            <span className={styles.key}>{row.key}</span>
            <span className={`${styles.val} ${row.cls ? styles[row.cls] ?? "" : ""}`}>
              {row.val}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
