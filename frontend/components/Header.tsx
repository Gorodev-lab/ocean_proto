"use client";

import styles from "./Header.module.css";

interface HeaderProps {
  isRefreshing: boolean;
  isBuildingKG: boolean;
  onRefresh: () => void;
  onBuildKG: () => void;
  onGuideOpen?: () => void;
}

export default function Header({
  isRefreshing,
  isBuildingKG,
  onRefresh,
  onBuildKG,
  onGuideOpen,
}: HeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <h1 className={styles.title}>
          ZOHAR <span className={styles.accent}>{"//"}</span> OCEAN PROTO
        </h1>
        <small className={styles.subtitle}>
          Cruceros · Yates · Pesca Industrial — Impacto en Hábitats de Cetáceos · Baja California Sur
        </small>
      </div>
      <div className={styles.actions}>
        {onGuideOpen && (
          <button
            className={styles.btn}
            onClick={onGuideOpen}
            aria-label="Guía de uso"
            title="Cómo usar Ocean Proto"
            style={{ minWidth: 32 }}
          >
            ?
          </button>
        )}
        <button
          className={styles.btn}
          onClick={onBuildKG}
          disabled={isBuildingKG || isRefreshing}
          aria-label="Build Knowledge Graph"
        >
          {isBuildingKG ? "⬡ Construyendo..." : "⬡ Build KG"}
        </button>
        <button
          className={styles.btn}
          onClick={onRefresh}
          disabled={isRefreshing || isBuildingKG}
          aria-label="Ejecutar Pipeline"
        >
          {isRefreshing ? "⟳ Actualizando..." : "⟳ Ejecutar Pipeline"}
        </button>
      </div>
    </header>
  );
}
