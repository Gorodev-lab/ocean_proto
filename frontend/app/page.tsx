"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import { useOceanState } from "@/hooks/useOceanState";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import LayerPanel from "@/components/LayerPanel";
import StatsBar from "@/components/StatsBar";
import InfoPanel from "@/components/InfoPanel";
import KGPanel from "@/components/KGPanel";
import IntelPanel from "@/components/IntelPanel";
import type { LayerCounts } from "@/types/ocean";
import styles from "./page.module.css";

// Dynamic import to prevent SSR of Leaflet
const OceanMap = dynamic(() => import("@/components/OceanMap"), { ssr: false });

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

  const [layerPanelHeight, setLayerPanelHeight] = useState(0);
  const layerPanelRef = useCallback((node: HTMLDivElement | null) => {
    if (node !== null) {
      setLayerPanelHeight(node.getBoundingClientRect().height);
    }
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
      // Espera 8s para que el pipeline procese
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
      // Poll KGPanel cada 5s hasta que esté listo (máx ~60s)
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

  // Intel panel height tracking (to position KG panel below it)
  const [intelPanelHeight, setIntelPanelHeight] = useState(0);
  const intelPanelRef = useCallback((node: HTMLDivElement | null) => {
    if (node !== null) {
      const ro = new ResizeObserver(() => {
        setIntelPanelHeight(node.getBoundingClientRect().height);
      });
      ro.observe(node);
    }
  }, []);

  // Compute KG panel top position after intel panel
  const kgPanelTop = intelPanelHeight > 0 ? intelPanelHeight + 14 + 8 : 460;

  return (
    <div className={styles.shell}>
      <Header
        isRefreshing={isRefreshing}
        isBuildingKG={isBuildingKG}
        onRefresh={handleRefresh}
        onBuildKG={handleBuildKG}
      />

      <div className={styles.mapWrapper}>
        {/* The map fills the wrapper 100% */}
        <OceanMap
          visibility={layerVisibility}
          onCounts={handleCounts}
          onMaxRisk={setStatMaxRisk}
          onFeatureClick={showInfo}
          refreshTrigger={refreshTrigger}
        />

        {/* Floating panels — positioned over the map */}
        <div ref={layerPanelRef}>
          <LayerPanel
            visibility={layerVisibility}
            counts={layerCounts}
            onToggle={toggleLayer}
          />
        </div>

        {/* Intel Panel — Traffic Intelligence */}
        <div
          ref={intelPanelRef}
          style={{ position: "absolute", top: 14, right: 14, zIndex: 1002 }}
        >
          <IntelPanel />
        </div>

        {/* KG Panel — below Intel Panel */}
        <div style={{ position: "absolute", top: kgPanelTop, right: 14, zIndex: 1001 }}>
          <KGPanel
            onStats={(nodes, edges) => {
              setKgNodes(nodes);
              setKgEdges(edges);
            }}
            refreshTrigger={kgRefreshTrigger}
          />
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

        <InfoPanel state={infoPanel} onClose={closeInfo} />
      </div>
    </div>
  );
}
