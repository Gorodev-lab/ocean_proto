"use client";

import { useState, useCallback } from "react";
import type { InfoPanelState, LayerCounts, LayerVisibility } from "@/types/ocean";

const DEFAULT_VISIBILITY: LayerVisibility = {
  hotspots: true,
  vessels: true,
  megafauna: true,
  platforms: true,
  osvs: true,
  gaps: true,
};

export function useOceanState() {
  const [layerVisibility, setLayerVisibility] =
    useState<LayerVisibility>(DEFAULT_VISIBILITY);
  const [layerCounts, setLayerCounts] = useState<LayerCounts>({
    hotspots: 0,
    vessels: 0,
    megafauna: 0,
    platforms: 0,
    osvs: 0,
    gaps: 0,
  });
  const [infoPanel, setInfoPanel] = useState<InfoPanelState>({
    visible: false,
    type: "",
    rows: [],
  });
  const [statMaxRisk, setStatMaxRisk] = useState<number>(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isBuildingKG, setIsBuildingKG] = useState(false);

  const toggleLayer = useCallback((layer: keyof LayerVisibility) => {
    setLayerVisibility((prev) => ({ ...prev, [layer]: !prev[layer] }));
  }, []);

  const showInfo = useCallback((type: string, rows: InfoPanelState["rows"]) => {
    setInfoPanel({ visible: true, type, rows });
  }, []);

  const closeInfo = useCallback(() => {
    setInfoPanel((prev) => ({ ...prev, visible: false }));
  }, []);

  return {
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
  };
}
