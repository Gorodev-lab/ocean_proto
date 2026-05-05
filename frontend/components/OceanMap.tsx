"use client";

import { useEffect, useRef, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  api,
  getRiskColor,
  getRiskClass,
  VESSEL_COLORS,
  SPECIES_COLORS,
  type GeoJSONFeatureCollection,
} from "@/lib/api";
import type { LayerVisibility, LayerCounts, InfoRow } from "@/types/ocean";

// Fix Leaflet default icon paths in Next.js
// eslint-disable-next-line @typescript-eslint/no-explicit-any
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface OceanMapProps {
  visibility: LayerVisibility;
  onCounts: (counts: Partial<LayerCounts>) => void;
  onMaxRisk: (val: number) => void;
  onFeatureClick: (type: string, rows: InfoRow[]) => void;
  refreshTrigger: number;
}

type LayerRef = L.GeoJSON | null;

export default function OceanMap({
  visibility,
  onCounts,
  onMaxRisk,
  onFeatureClick,
  refreshTrigger,
}: OceanMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  const hotspotsRef = useRef<LayerRef>(null);
  const vesselsRef  = useRef<LayerRef>(null);
  const megafaunaRef= useRef<LayerRef>(null);
  const platformsRef= useRef<LayerRef>(null);
  const osvsRef     = useRef<LayerRef>(null);
  const gapsRef     = useRef<LayerRef>(null);

  // ── Initialize map ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !mapContainerRef.current) return;

    const map = L.map(mapContainerRef.current, { zoomControl: true }).setView(
      [26.0, -111.0],
      6
    );

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 18,
      }
    ).addTo(map);

    // Risk score legend
    const legend = new L.Control({ position: "bottomright" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", "info legend");
      const grades = [0, 2, 5, 10, 15, 20];
      div.innerHTML = "<h4>Risk Score</h4>";
      for (let i = 0; i < grades.length; i++) {
        div.innerHTML +=
          `<i style="background:${getRiskColor(grades[i] + 1)}"></i> ` +
          grades[i] +
          (grades[i + 1] ? `&ndash;${grades[i + 1]}<br>` : "+");
      }
      return div;
    };
    legend.addTo(map);

    mapRef.current = map;
  }, []);

  // ── Load / reload all layers ────────────────────────────────────────────────
  const loadHotspots = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data: GeoJSONFeatureCollection = await api.hotspots();
      if (hotspotsRef.current) map.removeLayer(hotspotsRef.current);

      const features = data.features ?? [];
      let maxRisk = 0;
      features.forEach((f) => {
        const s = Number(f.properties.risk_score ?? f.properties.ipa_100 ?? 0);
        if (s > maxRisk) maxRisk = s;
      });

      onCounts({ hotspots: features.length });
      onMaxRisk(maxRisk);

      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        style: (feature) => ({
          fillColor: getRiskColor(
            Number(feature?.properties?.risk_score ?? feature?.properties?.ipa_100 ?? 0)
          ),
          weight: 1,
          opacity: 0.8,
          color: "rgba(255,255,255,0.12)",
          fillOpacity: 0.6,
        }),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          layer.on("click", () => {
            const score = Number(p.risk_score ?? p.ipa_100 ?? 0);
            onFeatureClick("Zona de Riesgo H3", [
              { key: "H3 Index",  val: String(p.h3_index ?? "—") },
              { key: "Buques",    val: Number(p.vessel_count ?? 0), cls: "vessel" },
              { key: "Megafauna", val: Number(p.megafauna_count ?? 0), cls: "species" },
              { key: "IPA Score", val: Number((p.ipa_100 ?? p.risk_score ?? 0)).toFixed(1), cls: getRiskClass(score) },
              { key: "Nivel",     val: String(p.ipa_level ?? "—") },
            ]);
          });
          layer.on("mouseover", function (this: L.Path) {
            this.setStyle({ weight: 2, color: "#00ff88", fillOpacity: 0.85 });
          });
          layer.on("mouseout", (e) => {
            (layer as unknown as { resetStyle(l: L.Layer): void }).resetStyle(e.target as L.Layer);
          });
        },
      });

      hotspotsRef.current = layer;
      if (visibility.hotspots) layer.addTo(map);
    } catch (e) {
      console.error("loadHotspots:", e);
    }
  }, [onCounts, onMaxRisk, onFeatureClick, visibility.hotspots]);

  const loadVessels = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data = await api.vessels();
      if (vesselsRef.current) map.removeLayer(vesselsRef.current);
      const features = data.features ?? [];
      onCounts({ vessels: features.length });
      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (feature, latlng) => {
          const vtype = String(feature.properties.vessel_type ?? "unknown").toLowerCase();
          return L.circleMarker(latlng, {
            radius: 4,
            fillColor: VESSEL_COLORS[vtype] ?? "#ff8844",
            color: "rgba(255,255,255,0.2)",
            weight: 1,
            fillOpacity: 0.85,
          });
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          layer.on("click", () =>
            onFeatureClick("Embarcación SAR (GFW)", [
              { key: "MMSI",      val: String(p.mmsi ?? "—") },
              { key: "Tipo",      val: String(p.vessel_type ?? "unknown").toUpperCase(), cls: "vessel" },
              { key: "Timestamp", val: String(p.timestamp ?? "—") },
              { key: "Lat",       val: lat.toFixed(4) },
              { key: "Lon",       val: lon.toFixed(4) },
            ])
          );
          layer.on("mouseover", function (this: L.CircleMarker) {
            this.setStyle({ radius: 7, fillOpacity: 1, weight: 2, color: "#fff" });
          });
          layer.on("mouseout", function (this: L.CircleMarker) {
            this.setStyle({ radius: 4, fillOpacity: 0.85, weight: 1, color: "rgba(255,255,255,0.2)" });
          });
        },
      });
      vesselsRef.current = layer;
      if (visibility.vessels) layer.addTo(map);
    } catch (e) {
      console.error("loadVessels:", e);
    }
  }, [onCounts, onFeatureClick, visibility.vessels]);

  const loadMegafauna = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data = await api.megafauna();
      if (megafaunaRef.current) map.removeLayer(megafaunaRef.current);
      const features = data.features ?? [];
      onCounts({ megafauna: features.length });
      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (feature, latlng) => {
          const sp = String(feature.properties.species ?? "Unknown");
          return L.circleMarker(latlng, {
            radius: 5,
            fillColor: SPECIES_COLORS[sp] ?? "#44bbff",
            color: "rgba(68,187,255,0.3)",
            weight: 1,
            fillOpacity: 0.8,
          });
        },
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          layer.on("click", () =>
            onFeatureClick("Avistamiento de Megafauna (OBIS)", [
              { key: "Especie",   val: String(p.species ?? "Desconocida"), cls: "species" },
              { key: "Grupo",     val: String(p.taxa_group ?? "—") },
              { key: "Relevancia",val: String(p.oil_relevance ?? "—") },
              { key: "Fecha",     val: String(p.timestamp ?? "—") },
              { key: "Lat",       val: lat.toFixed(4) },
              { key: "Lon",       val: lon.toFixed(4) },
            ])
          );
          layer.on("mouseover", function (this: L.CircleMarker) {
            this.setStyle({ radius: 8, fillOpacity: 1, weight: 2, color: "#fff" });
          });
          layer.on("mouseout", function (this: L.CircleMarker) {
            this.setStyle({ radius: 5, fillOpacity: 0.8, weight: 1, color: "rgba(68,187,255,0.3)" });
          });
        },
      });
      megafaunaRef.current = layer;
      if (visibility.megafauna) layer.addTo(map);
    } catch (e) {
      console.error("loadMegafauna:", e);
    }
  }, [onCounts, onFeatureClick, visibility.megafauna]);

  const loadPlatforms = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data = await api.platforms();
      if (platformsRef.current) map.removeLayer(platformsRef.current);
      const features = data.features ?? [];
      onCounts({ platforms: features.length });
      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (_, latlng) =>
          L.marker(latlng, {
            icon: L.divIcon({
              className: "",
              html: '<div class="platform-marker"></div>',
              iconSize: [10, 10],
              iconAnchor: [5, 5],
            }),
          }),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          layer.on("click", () =>
            onFeatureClick("Plataforma O&G", [
              { key: "ID",       val: String(p.platform_id ?? "—"), cls: "platform" },
              { key: "Categoría",val: String(p.category ?? "OIL"), cls: "platform" },
              { key: "Tipo",     val: String(p.label ?? "—") },
              { key: "Sub-cat",  val: String(p.sub_category ?? "—") },
              { key: "Fuente",   val: String(p.source ?? "—") },
              { key: "Lat",      val: lat.toFixed(4) },
              { key: "Lon",      val: lon.toFixed(4) },
            ])
          );
        },
      });
      platformsRef.current = layer;
      if (visibility.platforms) layer.addTo(map);
    } catch (e) {
      console.error("loadPlatforms:", e);
    }
  }, [onCounts, onFeatureClick, visibility.platforms]);

  const loadOsvs = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data = await api.osvs();
      if (osvsRef.current) map.removeLayer(osvsRef.current);
      const features = data.features ?? [];
      onCounts({ osvs: features.length });
      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (_, latlng) =>
          L.circleMarker(latlng, {
            radius: 5,
            fillColor: "#ff66cc",
            color: "rgba(255,102,204,0.3)",
            weight: 1.5,
            fillOpacity: 0.8,
          }),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          layer.on("click", () =>
            onFeatureClick("Buque de Apoyo O&G (OSV)", [
              { key: "Nombre", val: String(p.shipname ?? "—"), cls: "osv" },
              { key: "MMSI",   val: String(p.mmsi ?? "—") },
              { key: "Bandera",val: String(p.flag ?? "—") },
              { key: "Tipo",   val: String(p.vessel_type ?? "support"), cls: "osv" },
              { key: "Fuente", val: String(p.source ?? "—") },
              { key: "Lat",    val: lat.toFixed(4) },
              { key: "Lon",    val: lon.toFixed(4) },
            ])
          );
          layer.on("mouseover", function (this: L.CircleMarker) {
            this.setStyle({ radius: 8, fillOpacity: 1, weight: 2, color: "#fff" });
          });
          layer.on("mouseout", function (this: L.CircleMarker) {
            this.setStyle({ radius: 5, fillOpacity: 0.8, weight: 1.5, color: "rgba(255,102,204,0.3)" });
          });
        },
      });
      osvsRef.current = layer;
      if (visibility.osvs) layer.addTo(map);
    } catch (e) {
      console.error("loadOsvs:", e);
    }
  }, [onCounts, onFeatureClick, visibility.osvs]);

  const loadGaps = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    try {
      const data = await api.gaps();
      if (gapsRef.current) map.removeLayer(gapsRef.current);
      const features = data.features ?? [];
      onCounts({ gaps: features.length });
      if (features.length === 0) return;

      const layer = L.geoJSON(data as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (_, latlng) =>
          L.marker(latlng, {
            icon: L.divIcon({
              className: "",
              html: '<div class="gap-pulse"></div>',
              iconSize: [12, 12],
              iconAnchor: [6, 6],
            }),
          }),
        onEachFeature: (feature, layer) => {
          const p = feature.properties;
          const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
          const hours = Number(p.gap_hours ?? 0);
          layer.on("click", () =>
            onFeatureClick("AIS Gap Event (Apagón)", [
              { key: "Nombre",   val: String(p.shipname ?? "—"), cls: "gap" },
              { key: "MMSI",     val: String(p.mmsi ?? "—") },
              { key: "Bandera",  val: String(p.flag ?? "—") },
              { key: "Duración", val: `${hours}h`, cls: hours > 24 ? "risk-high" : "gap" },
              { key: "Inicio",   val: String(p.start ?? "—") },
              { key: "Fin",      val: String(p.end ?? "—") },
              { key: "Lat",      val: lat.toFixed(4) },
              { key: "Lon",      val: lon.toFixed(4) },
            ])
          );
        },
      });
      gapsRef.current = layer;
      if (visibility.gaps) layer.addTo(map);
    } catch (e) {
      console.error("loadGaps:", e);
    }
  }, [onCounts, onFeatureClick, visibility.gaps]);

  // ── Re-load all on refreshTrigger change ────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    loadHotspots();
    loadVessels();
    loadMegafauna();
    loadPlatforms();
    loadOsvs();
    loadGaps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger]);

  // ── Toggle layer visibility without reloading data ──────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const pairs: [LayerRef | null, boolean][] = [
      [hotspotsRef.current,  visibility.hotspots],
      [vesselsRef.current,   visibility.vessels],
      [megafaunaRef.current, visibility.megafauna],
      [platformsRef.current, visibility.platforms],
      [osvsRef.current,      visibility.osvs],
      [gapsRef.current,      visibility.gaps],
    ];
    pairs.forEach(([layer, show]) => {
      if (!layer) return;
      if (show && !map.hasLayer(layer)) layer.addTo(map);
      if (!show && map.hasLayer(layer)) map.removeLayer(layer);
    });
  }, [visibility]);

  return (
    <div
      ref={mapContainerRef}
      style={{ width: "100%", height: "100%", background: "#0A0A0A" }}
    />
  );
}
