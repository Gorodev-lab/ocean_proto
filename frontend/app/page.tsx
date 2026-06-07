"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { useOceanState } from "@/hooks/useOceanState";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import LayerPanel from "@/components/LayerPanel";
import StatsBar from "@/components/StatsBar";
import InfoPanel from "@/components/InfoPanel";
import KGPanel from "@/components/KGPanel";
import IntelPanel from "@/components/IntelPanel";
import TimelineChart from "@/components/TimelineChart";
import WorkflowGuide from "@/components/WorkflowGuide";
import type { LayerCounts } from "@/types/ocean";
import styles from "./page.module.css";

// Dynamic imports to prevent SSR errors
const OceanMap = dynamic(() => import("@/components/OceanMap"), { ssr: false });
const GraphVisualizer = dynamic(() => import("@/components/GraphVisualizer"), { ssr: false });

export default function HomePage() {
  const {
    layerVisibility,
    layerCounts,
    setLayerCounts,
    infoPanel,
    showInfo,
    closeInfo,
    statMaxRisk,
    setStatMaxRisk,
    isRefreshing,
    setIsRefreshing,
    isBuildingKG,
    setIsBuildingKG,
    toggleLayer,
  } = useOceanState();

  const [kgNodes, setKgNodes] = useState(0);
  const [kgEdges, setKgEdges] = useState(0);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [kgRefreshTrigger, setKgRefreshTrigger] = useState(0);

  // Layout states
  const [viewMode, setViewMode] = useState<"map" | "graph">("map");
  const [isMobile, setIsMobile] = useState(false);
  // Sidebars collapsed by default on mobile, open on desktop
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [mapCenter, setMapCenter] = useState<[number, number] | null>(null);

  // Workflow guide state — auto-open on first visit
  const [guideOpen, setGuideOpen] = useState(false);

  useEffect(() => {
    const seen = localStorage.getItem("ocean_proto_guide_seen");
    if (!seen) {
      setGuideOpen(true);
      localStorage.setItem("ocean_proto_guide_seen", "1");
    }
  }, []);

  // Detect mobile viewport and default sidebars closed on small screens
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const handleChange = (e: MediaQueryListEvent | MediaQueryList) => {
      const mobile = e.matches;
      setIsMobile(mobile);
      if (mobile) {
        setLeftSidebarOpen(false);
        setRightSidebarOpen(false);
      }
    };
    handleChange(mq); // run immediately on mount
    mq.addEventListener("change", handleChange);
    return () => mq.removeEventListener("change", handleChange);
  }, []);

  const handleCounts = useCallback(
    (partial: Partial<LayerCounts>) => {
      setLayerCounts((prev: LayerCounts) => ({ ...prev, ...partial }));
    },
    [setLayerCounts]
  );

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await api.refresh(false);
      // Wait 8s for pipeline processing
      setTimeout(() => {
        setRefreshTrigger((n) => n + 1);
        setIsRefreshing(false);
      }, 8000);
    } catch {
      setIsRefreshing(false);
    }
  }, [setIsRefreshing]);

  const handleBuildKG = useCallback(async () => {
    setIsBuildingKG(true);
    try {
      await api.refresh(true);
      // Poll KGPanel every 5s until ready (max ~60s)
      let attempts = 0;
      const poll = setInterval(() => {
        attempts++;
        setKgRefreshTrigger((n) => n + 1);
        if (attempts >= 12) {
          clearInterval(poll);
          setIsBuildingKG(false);
        }
      }, 5000);
    } catch {
      setIsBuildingKG(false);
    }
  }, [setIsBuildingKG]);

  // Handler for node selection from graph to inspect/sync
  const handleSelectNode = useCallback((nodeId: string | null) => {
    setFocusedNodeId(nodeId);
  }, []);

  return (
    <div className={styles.shell}>
      <Header
        isRefreshing={isRefreshing}
        isBuildingKG={isBuildingKG}
        onRefresh={handleRefresh}
        onBuildKG={handleBuildKG}
        onGuideOpen={() => setGuideOpen(true)}
      />

      <WorkflowGuide isOpen={guideOpen} onClose={() => setGuideOpen(false)} />

      <div className={styles.dashboardBody}>
        {/* SIDEBAR LEFT (Control & Layers) */}
        <aside
          className={`${styles.sidebarLeft} ${
            !leftSidebarOpen ? styles.sidebarLeftCollapsed : ""
          }`}
        >
          <div className={styles.sidebarHeader}>
            <h4 className={styles.sidebarTitle}>
              <span className={styles.sidebarTitlePrefix}>&gt;</span> CONTROL
            </h4>
          </div>

          <div className={styles.viewToggleGroup}>
            <button
              className={`${styles.viewToggleBtn} ${
                viewMode === "map" ? styles.viewToggleBtnActive : ""
              }`}
              onClick={() => setViewMode("map")}
            >
              Mapa
            </button>
            <button
              className={`${styles.viewToggleBtn} ${
                viewMode === "graph" ? styles.viewToggleBtnActive : ""
              }`}
              onClick={() => setViewMode("graph")}
            >
              Grafo
            </button>
          </div>

          <div className={styles.sidebarContent}>
            {viewMode === "map" ? (
              <LayerPanel
                visibility={layerVisibility}
                counts={layerCounts}
                onToggle={toggleLayer}
              />
            ) : (
              <div style={{ padding: "18px", color: "var(--color-text-muted)", fontSize: "12px", fontFamily: "IBM Plex Mono" }}>
                <div style={{ marginBottom: "14px", borderBottom: "1px solid var(--color-border)", paddingBottom: "8px", fontWeight: 600, color: "var(--color-text-primary)" }}>EXPLORADOR DE RED</div>
                Usa el buscador del grafo para localizar barcos, especies o zonas de riesgo y analizar sus dependencias directas en la vista física.
              </div>
            )}
          </div>
        </aside>

        {/* SIDEBAR LEFT COLLAPSE TOGGLE */}
        <button
          className={`${styles.toggleBtn} ${styles.toggleBtnLeft}`}
          onClick={() => setLeftSidebarOpen((o) => !o)}
          title={leftSidebarOpen ? "Colapsar Panel Izquierdo" : "Expandir Panel Izquierdo"}
          aria-label={leftSidebarOpen ? "Colapsar Izquierda" : "Expandir Izquierda"}
          // On desktop: nudge button to follow the open sidebar edge.
          // On mobile: CSS media query fixes position — no inline override needed.
          style={!isMobile ? { left: leftSidebarOpen ? "294px" : "14px" } : undefined}
        >
          {leftSidebarOpen ? "◀" : "▶"}
        </button>

        {/* MAIN WORKSPACE (Map or Graph) */}
        <main className={styles.mainContent}>
          <div className={styles.mapOrGraphContainer}>
            {/* Map wrapper - display hidden when graph is active to preserve leaflet map instance state */}
            <div style={{ display: viewMode === "map" ? "block" : "none", height: "100%", width: "100%" }}>
              <OceanMap
                visibility={layerVisibility}
                onCounts={handleCounts}
                onMaxRisk={setStatMaxRisk}
                onFeatureClick={showInfo}
                refreshTrigger={refreshTrigger}
                center={mapCenter}
              />
            </div>

            {/* Graph Visualizer wrapper */}
            {viewMode === "graph" && (
              <GraphVisualizer
                focusedNodeId={focusedNodeId}
                onSelectNode={handleSelectNode}
                onLocateOnMap={(lat, lon) => {
                  setMapCenter([lat, lon]);
                  setViewMode("map");
                }}
              />
            )}
          </div>

          <StatsBar
            vessels={layerCounts.vessels}
            megafauna={layerCounts.megafauna}
            hotspots={layerCounts.hotspots}
            maxRisk={statMaxRisk}
            platforms={layerCounts.platforms}
            gaps={layerCounts.gaps}
            kgNodes={kgNodes}
            kgEdges={kgEdges}
          />
        </main>

        {/* SIDEBAR RIGHT COLLAPSE TOGGLE */}
        <button
          className={`${styles.toggleBtn} ${styles.toggleBtnRight}`}
          onClick={() => setRightSidebarOpen((o) => !o)}
          title={rightSidebarOpen ? "Colapsar Panel Derecho" : "Expandir Panel Derecho"}
          aria-label={rightSidebarOpen ? "Colapsar Derecha" : "Expandir Derecha"}
          // On desktop: nudge button to follow the open sidebar edge.
          // On mobile: CSS media query fixes position — no inline override needed.
          style={!isMobile ? { right: rightSidebarOpen ? "374px" : "14px" } : undefined}
        >
          {rightSidebarOpen ? "▶" : "◀"}
        </button>

        {/* SIDEBAR RIGHT (Analysis: Traffic Intel & KG Stats) */}
        <aside
          className={`${styles.sidebarRight} ${
            !rightSidebarOpen ? styles.sidebarRightCollapsed : ""
          }`}
        >
          <div className={styles.sidebarHeader}>
            <h4 className={styles.sidebarTitle}>
              <span className={styles.sidebarTitlePrefix}>&gt;</span> ANÁLISIS
            </h4>
          </div>

          <div className={styles.sidebarContent}>
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "14px", padding: "14px 0" }}>
              <IntelPanel />

              {/* Timeline: serie temporal histórica con vedas */}
              <div
                style={{
                  margin: "0 14px",
                  padding: "14px",
                  background: "#0d0d0d",
                  border: "1px solid #1a1a1a",
                }}
              >
                <TimelineChart />
              </div>

              <KGPanel
                onStats={(nodes, edges) => {
                  setKgNodes(nodes);
                  setKgEdges(edges);
                }}
                refreshTrigger={kgRefreshTrigger}
              />
            </div>
          </div>
        </aside>

        <InfoPanel state={infoPanel} onClose={closeInfo} />
      </div>
    </div>
  );
}

