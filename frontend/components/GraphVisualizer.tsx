"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import * as d3 from "d3";
import styles from "./GraphVisualizer.module.css";
import { VESSEL_COLORS, SPECIES_COLORS } from "@/lib/api";
import { db } from "@/lib/supabase";

// ── Types ────────────────────────────────────────────────────────────────────

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  type: string;
  h3_index?: string;
  risk_score?: number;
  vessel_count?: number;
  megafauna_count?: number;
  mmsi?: string;
  timestamp?: string;
  lat?: number;
  lon?: number;
  vessel_type?: string;
  vessel_name?: string;
  flag?: string;
  imo?: string;
  scientificName?: string;
  iucn_status?: string;
  oil_relevant?: boolean;
  taxa_group?: string;
  category?: string;
  label?: string;
  shipname?: string;
  vessel_id?: string;
  platform_id?: string;
  gap_id?: string;
  gap_hours?: number;
  start?: string;
  end?: string;
  zone_id?: string;
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode;
  target: string | GraphNode;
  relation: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface GraphVisualizerProps {
  focusedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  onLocateOnMap?: (lat: number, lon: number) => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// Custom SVG paths for Esoteria Style (flat, geometric, sharp)
function drawHexagon(r: number): string {
  const points = [];
  for (let i = 0; i < 6; i++) {
    const angle = (i * Math.PI) / 3 - Math.PI / 6; // oriented vertically
    points.push(`${(r * Math.cos(angle)).toFixed(1)},${(r * Math.sin(angle)).toFixed(1)}`);
  }
  return `M ${points.join(" L ")} Z`;
}

function drawDiamond(s: number): string {
  return `M 0,-${s} L ${s},0 L 0,${s} L -${s},0 Z`;
}

function drawSquare(s: number): string {
  return `M -${s},-${s} L ${s},-${s} L ${s},${s} L -${s},${s} Z`;
}

function drawTriangle(s: number): string {
  return `M 0,-${s} L ${s},${s} L -${s},${s} Z`;
}

function getNodePath(type: string, sizeMultiplier = 1): string {
  switch (type) {
    case "HexCell":
      return drawHexagon(8 * sizeMultiplier);
    case "RiskZone":
      return drawHexagon(15 * sizeMultiplier);
    case "Species":
    case "WhaleSpecies":
      return drawDiamond(9 * sizeMultiplier);
    case "AisGapEvent":
      return drawTriangle(9 * sizeMultiplier);
    case "VesselEvent":
    case "VesselIdentity":
    case "SupportVessel":
    default:
      return drawSquare(8 * sizeMultiplier);
  }
}

function getNodeColor(node: GraphNode): string {
  switch (node.type) {
    case "HexCell":
      return node.risk_score && node.risk_score > 10 ? "#ef4444" : "#475569";
    case "RiskZone":
      return "#ef4444";
    case "AisGapEvent":
      return "#facc15"; // Warning yellow
    case "Species":
    case "WhaleSpecies":
      return SPECIES_COLORS[node.scientificName ?? ""] ?? "#44bbff";
    case "OilPlatform":
      return "#a855f7"; // Cruceros / Yates color theme
    case "SupportVessel":
      return "#22c55e"; // Fishing color theme
    case "VesselEvent":
    case "VesselIdentity":
      return VESSEL_COLORS[node.vessel_type ?? ""] ?? "#3b82f6";
    default:
      return "#94a3b8";
  }
}

function getNodeLabel(node: GraphNode): string {
  switch (node.type) {
    case "HexCell":
      return node.h3_index ? `Hex ${node.h3_index.slice(-6)}` : node.id;
    case "VesselIdentity":
    case "VesselEvent":
      return node.vessel_name || (node.mmsi ? `MMSI ${node.mmsi}` : node.id);
    case "SupportVessel":
      return node.shipname || (node.mmsi ? `Pesquero ${node.mmsi}` : node.id);
    case "Species":
    case "WhaleSpecies":
      return node.scientificName || node.id;
    case "OilPlatform":
      return node.label || `Platform ${node.platform_id}`;
    case "AisGapEvent":
      return node.shipname ? `Gap ${node.shipname}` : `Gap ${node.mmsi || node.id}`;
    case "RiskZone":
      return `Risk Zone ${node.zone_id}`;
    default:
      return node.id;
  }
}

export default function GraphVisualizer({
  focusedNodeId,
  onSelectNode,
  onLocateOnMap,
}: GraphVisualizerProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters state
  const [showHexCells, setShowHexCells] = useState(false);
  const [showVesselEvents, setShowVesselEvents] = useState(false);
  const [depth, setDepth] = useState<1 | 2>(1);

  // Search autocomplete state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GraphNode[]>([]);

  // Detailed inspect node (single-click)
  const [inspectNode, setInspectNode] = useState<GraphNode | null>(null);

  // Loading graph data from Supabase directly for serverless compatibility
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const json = await db.knowledgeGraph();
        if (json && (json.nodes || json.links)) {
          setData(json as GraphData);
        } else {
          console.warn("Received empty or invalid knowledge graph data from Supabase:", json);
        }
      } catch (err) {
        console.error("Failed to load knowledge graph data from Supabase:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Update autocomplete list
  useEffect(() => {
    if (!data || !searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const q = searchQuery.toLowerCase();
    const matches = data.nodes
      .filter((n) => {
        // Exclude hexes and vessel events from general search to keep it clean
        if (n.type === "HexCell" || n.type === "VesselEvent") return false;
        const label = getNodeLabel(n).toLowerCase();
        const id = n.id.toLowerCase();
        const mmsi = n.mmsi ? n.mmsi.toLowerCase() : "";
        return label.includes(q) || id.includes(q) || mmsi.includes(q);
      })
      .slice(0, 10);
    setSearchResults(matches);
  }, [searchQuery, data]);

  // Compute active nodes and links for rendering based on focusedNodeId
  const activeGraph = useMemo(() => {
    if (!data) return { nodes: [], links: [] };

    // 1. If NO focal node is selected: Render the Macro-Graph
    if (!focusedNodeId) {
      const macroTypes = [
        "WhaleSpecies",
        "Species",
        "RiskZone",
        "OilPlatform",
        "AisGapEvent",
        "SupportVessel",
        "VesselIdentity"
      ];
      
      const filteredNodes = data.nodes.filter((n) => {
        // Don't show hexcells or event instances at macro level unless toggled
        if (n.type === "HexCell" && !showHexCells) return false;
        if (n.type === "VesselEvent" && !showVesselEvents) return false;
        return macroTypes.includes(n.type);
      });

      const nodeIds = new Set(filteredNodes.map((n) => n.id));
      const filteredLinks = data.links.filter((l) => {
        const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
        const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;
        return nodeIds.has(sourceId) && nodeIds.has(targetId);
      });

      return { nodes: filteredNodes, links: filteredLinks };
    }

    // 2. If a focal node is selected: Focus on its neighborhood
    const focalNode = data.nodes.find((n) => n.id === focusedNodeId);
    if (!focalNode) {
      return { nodes: [], links: [] };
    }

    // Find 1-hop connections
    const hop1NodeIds = new Set<string>([focusedNodeId]);
    const hop1Links = new Set<GraphLink>();

    data.links.forEach((l) => {
      const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
      const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;

      if (sourceId === focusedNodeId) {
        hop1NodeIds.add(targetId);
        hop1Links.add(l);
      } else if (targetId === focusedNodeId) {
        hop1NodeIds.add(sourceId);
        hop1Links.add(l);
      }
    });

    const activeNodeIds = new Set<string>(hop1NodeIds);
    const activeLinks = new Set<GraphLink>(hop1Links);

    // If depth is 2, find 2-hop connections
    if (depth === 2) {
      data.links.forEach((l) => {
        const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
        const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;

        // If a link connects to a 1-hop neighbor but not the focal itself, include it
        if (hop1NodeIds.has(sourceId) && !hop1NodeIds.has(targetId)) {
          activeNodeIds.add(targetId);
          activeLinks.add(l);
        } else if (hop1NodeIds.has(targetId) && !hop1NodeIds.has(sourceId)) {
          activeNodeIds.add(sourceId);
          activeLinks.add(l);
        }
      });
    }

    // Filter node types based on checkboxes
    const filteredNodeIds = new Set<string>();
    const filteredNodes = data.nodes.filter((n) => {
      if (!activeNodeIds.has(n.id)) return false;
      // Always show the focal node regardless of its type
      if (n.id === focusedNodeId) {
        filteredNodeIds.add(n.id);
        return true;
      }
      // Apply visibility filters for neighbors
      if (n.type === "HexCell" && !showHexCells) return false;
      if (n.type === "VesselEvent" && !showVesselEvents) return false;

      filteredNodeIds.add(n.id);
      return true;
    });

    const filteredLinks = Array.from(activeLinks).filter((l) => {
      const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
      const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;
      return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
    });

    return { nodes: filteredNodes, links: filteredLinks };
  }, [data, focusedNodeId, depth, showHexCells, showVesselEvents]);

  // Sync inspectNode when focusedNodeId changes
  useEffect(() => {
    if (data && focusedNodeId) {
      const node = data.nodes.find((n) => n.id === focusedNodeId);
      if (node) setInspectNode(node);
    }
  }, [focusedNodeId, data]);

  // Get direct connections of currently inspected node for list view
  const inspectedRelations = useMemo(() => {
    if (!data || !inspectNode) return [];
    
    return data.links
      .filter((l) => {
        const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
        const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;
        return sourceId === inspectNode.id || targetId === inspectNode.id;
      })
      .map((l) => {
        const sourceId = typeof l.source === "string" ? l.source : (l.source as any).id;
        const targetId = typeof l.target === "string" ? l.target : (l.target as any).id;
        const isOut = sourceId === inspectNode.id;
        const neighborId = isOut ? targetId : sourceId;
        const neighborNode = data.nodes.find((n) => n.id === neighborId);
        
        return {
          id: neighborId,
          relation: l.relation,
          isOutgoing: isOut,
          label: neighborNode ? getNodeLabel(neighborNode) : neighborId,
          type: neighborNode?.type ?? "Unknown",
        };
      });
  }, [data, inspectNode]);

  // ── D3 Canvas Rendering ───────────────────────────────────────────────────

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;

    // Clear previous elements
    d3.select(svgEl).selectAll("*").remove();

    const { nodes: originalNodes, links: originalLinks } = activeGraph;
    if (originalNodes.length === 0) return;

    // Size dimensions
    const width = svgEl.clientWidth || 800;
    const height = svgEl.clientHeight || 600;

    // Clone data for D3 force mutation safety (structuredClone is faster than JSON.parse roundtrip)
    const nodes: GraphNode[] = structuredClone(originalNodes);
    const links = originalLinks.map((l) => {
      const sId = typeof l.source === "string" ? l.source : (l.source as any).id;
      const tId = typeof l.target === "string" ? l.target : (l.target as any).id;
      return {
        source: sId,
        target: tId,
        relation: l.relation,
      };
    });

    const svg = d3.select(svgEl);

    // Zoom/Pan Container
    const zoomGroup = svg.append("g").attr("class", "zoom-container");

    const zoomBehavior = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 4])
      .on("zoom", (event) => {
        zoomGroup.attr("transform", event.transform);
      });

    svg.call(zoomBehavior);

    // Define defs for arrow markers
    const defs = svg.append("defs");
    defs
      .append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 18) // position offset from node center
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", "#333333");

    // Force simulation
    const simulation = d3
      .forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(links as any)
          .id((d) => d.id)
          .distance((d: any) => (d.source.type === "HexCell" || d.target.type === "HexCell" ? 70 : 130))
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(32));

    // Tooltip overlay
    const tooltip = d3
      .select(svgEl.parentElement)
      .append("div")
      .attr("class", styles.tooltip)
      .style("opacity", 0);

    // Render Links
    const linkG = zoomGroup
      .append("g")
      .selectAll(".link-group")
      .data(links)
      .enter()
      .append("g")
      .attr("class", styles.linkGroup);

    const linkLines = linkG
      .append("line")
      .attr("class", styles.linkElement)
      .attr("marker-end", "url(#arrow)");

    const linkText = linkG
      .append("text")
      .attr("class", styles.linkLabelElement)
      .text((d) => d.relation);

    // Render Nodes
    const nodeG = zoomGroup
      .append("g")
      .selectAll(".node-group")
      .data(nodes)
      .enter()
      .append("g")
      .attr("class", "node-group")
      .call(
        d3
          .drag<SVGGElement, any>()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended)
      );

    // Node shape path
    nodeG
      .append("path")
      .attr("class", styles.nodeElement)
      .attr("d", (d) => getNodePath(d.type, d.id === focusedNodeId ? 1.4 : 1))
      .attr("fill", (d) => getNodeColor(d))
      .attr("stroke", (d) => (d.id === focusedNodeId ? "#ffffff" : "#0A0A0A"))
      .attr("stroke-width", (d) => (d.id === focusedNodeId ? 2.5 : 1))
      .style("opacity", (d) => (focusedNodeId && d.id !== focusedNodeId ? 0.95 : 1));

    // Node labels
    nodeG
      .append("text")
      .attr("dx", 12)
      .attr("dy", ".35em")
      .style("font-size", (d) => (d.id === focusedNodeId ? "10px" : "8px"))
      .style("font-family", "IBM Plex Mono, monospace")
      .style("fill", (d) => (d.id === focusedNodeId ? "#ffffff" : "#aaaaaa"))
      .style("font-weight", (d) => (d.id === focusedNodeId ? "600" : "400"))
      .text((d) => getNodeLabel(d));

    // Interaction Events
    nodeG
      .on("mouseover", function (event, d) {
        d3.select(this).select("path").attr("stroke", "#ffffff").attr("stroke-width", 2);

        // Highlight connected links
        linkLines.style("stroke", (l: any) =>
          l.source.id === d.id || l.target.id === d.id ? "var(--color-accent)" : "#222222"
        );
        linkText.style("opacity", (l: any) =>
          l.source.id === d.id || l.target.id === d.id ? 1 : 0
        );

        // Show tooltip
        tooltip.transition().duration(100).style("opacity", 0.95);
        tooltip
          .html(
            `<div class="${styles.tooltipTitle}">${getNodeLabel(d)}</div>` +
              `<div style="color:var(--color-accent); font-weight:600; text-transform:uppercase; font-size:7px; letter-spacing:0.04em;">${d.type}</div>`
          )
          .style("left", `${event.clientX - svgEl.getBoundingClientRect().left + 15}px`)
          .style("top", `${event.clientY - svgEl.getBoundingClientRect().top - 15}px`);
      })
      .on("mousemove", function (event) {
        tooltip
          .style("left", `${event.clientX - svgEl.getBoundingClientRect().left + 15}px`)
          .style("top", `${event.clientY - svgEl.getBoundingClientRect().top - 15}px`);
      })
      .on("mouseout", function (event, d) {
        d3.select(this)
          .select("path")
          .attr("stroke", d.id === focusedNodeId ? "#ffffff" : "#0A0A0A")
          .attr("stroke-width", d.id === focusedNodeId ? 2.5 : 1);

        linkLines.style("stroke", "#222222");
        linkText.style("opacity", 0);

        tooltip.transition().duration(100).style("opacity", 0);
      })
      .on("click", function (event, d) {
        // Inspect node details (single-click)
        setInspectNode(d);
      })
      .on("dblclick", function (event, d) {
        // Focus graph around this node (double-click)
        onSelectNode(d.id);
      });

    // Update positions on tick
    simulation.on("tick", () => {
      linkLines
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      linkText
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2 - 4);

      nodeG.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    // Fit graph bounds on initial load
    setTimeout(() => {
      if (nodes.length > 0) {
        const bounds = zoomGroup.node()?.getBBox();
        if (bounds && bounds.width > 0 && bounds.height > 0) {
          const dx = bounds.width;
          const dy = bounds.height;
          const x = bounds.x + bounds.width / 2;
          const y = bounds.y + bounds.height / 2;
          const scale = Math.min(0.9, 0.85 / Math.max(dx / width, dy / height));
          const translate = [width / 2 - scale * x, height / 2 - scale * y];

          svg
            .transition()
            .duration(400)
            .call(zoomBehavior.transform as any, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
        }
      }
    }, 250);

    // Drag helpers
    function dragstarted(event: any, d: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event: any, d: any) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event: any, d: any) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    return () => {
      simulation.stop();
      tooltip.remove();
    };
  }, [activeGraph, focusedNodeId, onSelectNode]);

  // Handler for locating on map
  const handleMapLocate = useCallback(() => {
    if (!inspectNode || !onLocateOnMap) return;
    const lat = inspectNode.lat;
    const lon = inspectNode.lon;
    if (lat !== undefined && lon !== undefined) {
      onLocateOnMap(lat, lon);
    }
  }, [inspectNode, onLocateOnMap]);

  return (
    <div className={styles.container}>
      {/* ── CANVAS AREA ── */}
      <div className={styles.graphArea}>
        {loading ? (
          <div className={styles.loadingOverlay}>Cargando Knowledge Graph...</div>
        ) : (
          <svg ref={svgRef} className={styles.svgCanvas} />
        )}

        {/* ── FLOATING OVERLAY CONTROLS ── */}
        <div className={styles.controlsOverlay}>
          {/* Autocomplete Search */}
          <div className={styles.searchBox}>
            <input
              type="text"
              placeholder="Buscar entidad (MMSI, Especie...)"
              className={styles.searchInput}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchResults.length > 0 && (
              <ul className={styles.searchResults}>
                {searchResults.map((n) => (
                  <li
                    key={n.id}
                    className={styles.searchResultItem}
                    onClick={() => {
                      onSelectNode(n.id);
                      setInspectNode(n);
                      setSearchQuery("");
                    }}
                  >
                    <span>{getNodeLabel(n)}</span>
                    <span className={styles.searchResultType}>{n.type}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Config Controls */}
          <div className={styles.graphConfigBox}>
            <div className={styles.legendTitle}>Filtros y Configuración</div>
            <div className={styles.configRow}>
              <input
                type="checkbox"
                id="showHex"
                className={styles.configCheckbox}
                checked={showHexCells}
                onChange={(e) => setShowHexCells(e.target.checked)}
              />
              <label htmlFor="showHex" style={{ cursor: "pointer" }}>
                Mostrar Hexágonos H3
              </label>
            </div>
            <div className={styles.configRow}>
              <input
                type="checkbox"
                id="showVessels"
                className={styles.configCheckbox}
                checked={showVesselEvents}
                onChange={(e) => setShowVesselEvents(e.target.checked)}
              />
              <label htmlFor="showVessels" style={{ cursor: "pointer" }}>
                Mostrar Eventos AIS
              </label>
            </div>

            {focusedNodeId && (
              <div className={styles.configRow} style={{ marginTop: "8px", borderTop: "1px solid #222", paddingTop: "8px" }}>
                <span style={{ marginRight: "8px" }}>Vecindario:</span>
                <button
                  className={`${styles.resetBtn}`}
                  style={{ margin: 0, padding: "2px 6px", borderColor: depth === 1 ? "var(--color-accent)" : "var(--color-border)" }}
                  onClick={() => setDepth(1)}
                >
                  1 Nivel
                </button>
                <button
                  className={`${styles.resetBtn}`}
                  style={{ margin: "0 0 0 4px", padding: "2px 6px", borderColor: depth === 2 ? "var(--color-accent)" : "var(--color-border)" }}
                  onClick={() => setDepth(2)}
                >
                  2 Niveles
                </button>
              </div>
            )}

            {focusedNodeId && (
              <button className={styles.resetBtn} style={{ width: "100%", marginTop: "10px" }} onClick={() => onSelectNode(null)}>
                Volver a Vista Macro
              </button>
            )}
          </div>

          {/* Legend */}
          <div className={styles.legendBox}>
            <div className={styles.legendTitle}>Leyenda del Grafo</div>
            <div className={styles.legendItem}>
              <div className={styles.legendShape} style={{ background: "#44bbff", clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" }} />
              <div className={styles.legendLabel}>Megafauna / Especies</div>
            </div>
            <div className={styles.legendItem}>
              <div className={styles.legendShape} style={{ background: "#22c55e" }} />
              <div className={styles.legendLabel}>Pesca Industrial</div>
            </div>
            <div className={styles.legendItem}>
              <div className={styles.legendShape} style={{ background: "#a855f7" }} />
              <div className={styles.legendLabel}>Cruceros / Yates</div>
            </div>
            <div className={styles.legendItem}>
              <div className={styles.legendShape} style={{ background: "#facc15", clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)" }} />
              <div className={styles.legendLabel}>Apagón AIS (Gap)</div>
            </div>
            <div className={styles.legendItem}>
              <div className={styles.legendShape} style={{ background: "#ef4444", clipPath: "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)" }} />
              <div className={styles.legendLabel}>Zonas de Riesgo</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── NODE INSPECTOR SIDEBAR ( Crisp & Minimalist ) ── */}
      {inspectNode && (
        <div className={styles.inspectorCard}>
          <div className={styles.inspectorHeader}>
            <span className={styles.inspectorTitle}>Inspector de Nodo</span>
            <button className={styles.inspectorClose} onClick={() => setInspectNode(null)}>
              ×
            </button>
          </div>

          <div className={styles.inspectorBody}>
            <div>
              <span className={styles.nodeBadge} style={{ borderColor: getNodeColor(inspectNode), color: getNodeColor(inspectNode) }}>
                {inspectNode.type}
              </span>
              <div className={styles.nodeTitleText}>{getNodeLabel(inspectNode)}</div>
            </div>

            {/* Attributes table */}
            <div className={styles.attributesTable}>
              {inspectNode.id && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>ID</span>
                  <span className={styles.attributeVal}>{inspectNode.id}</span>
                </div>
              )}
              {inspectNode.mmsi && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>MMSI</span>
                  <span className={styles.attributeVal}>{inspectNode.mmsi}</span>
                </div>
              )}
              {inspectNode.vessel_type && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>Tipo Buque</span>
                  <span className={styles.attributeVal}>{inspectNode.vessel_type}</span>
                </div>
              )}
              {inspectNode.flag && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>Bandera</span>
                  <span className={styles.attributeVal}>{inspectNode.flag}</span>
                </div>
              )}
              {inspectNode.imo && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>IMO</span>
                  <span className={styles.attributeVal}>{inspectNode.imo}</span>
                </div>
              )}
              {inspectNode.iucn_status && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>IUCN Redlist</span>
                  <span className={styles.attributeVal}>{inspectNode.iucn_status}</span>
                </div>
              )}
              {inspectNode.gap_hours !== undefined && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>Horas Apagón</span>
                  <span className={styles.attributeVal}>{inspectNode.gap_hours} hrs</span>
                </div>
              )}
              {inspectNode.risk_score !== undefined && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>Risk Score</span>
                  <span className={styles.attributeVal}>{inspectNode.risk_score}</span>
                </div>
              )}
              {inspectNode.lat !== undefined && inspectNode.lon !== undefined && (
                <div className={styles.attributeRow}>
                  <span className={styles.attributeKey}>Coordenadas</span>
                  <span className={styles.attributeVal}>
                    {inspectNode.lat.toFixed(4)}, {inspectNode.lon.toFixed(4)}
                  </span>
                </div>
              )}
            </div>

            {/* Local Map locator button */}
            {inspectNode.lat !== undefined && inspectNode.lon !== undefined && onLocateOnMap && (
              <button className={styles.actionBtn} onClick={handleMapLocate}>
                Localizar en Mapa
              </button>
            )}

            {/* Direct relations list */}
            <div>
              <div className={styles.sectionTitle}>Relaciones Directas ({inspectedRelations.length})</div>
              <div className={styles.relationsList}>
                {inspectedRelations.slice(0, 15).map((r, idx) => (
                  <div
                    key={`${r.id}-${idx}`}
                    className={styles.relationRow}
                    onClick={() => {
                      onSelectNode(r.id);
                    }}
                    title="Doble clic para centrar en este nodo"
                  >
                    <span className={styles.relationName}>
                      {r.isOutgoing ? "→" : "←"} {r.relation}
                    </span>
                    <span className={styles.relationTarget}>{r.label}</span>
                  </div>
                ))}
                {inspectedRelations.length > 15 && (
                  <div style={{ fontSize: "8px", color: "var(--color-text-muted)", textAlign: "center", marginTop: "4px" }}>
                    + {inspectedRelations.length - 15} relaciones adicionales
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
