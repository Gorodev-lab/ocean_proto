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

  // Compute KG panel top position after layer panel
  // We use CSS custom property via inline style trick
  const kgPanelTop = layerPanelHeight > 0 ? layerPanelHeight + 14 + 10 : 280;

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
