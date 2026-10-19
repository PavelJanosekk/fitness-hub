import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { useTheme } from "../../lib/theme";
import { useChartColors } from "../charts/palette";

/** OpenStreetMap tiles; dark themes invert them so the map doesn't glare inside a dark card. */
const TILE_FILTER = {
  minimal: "invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.9) saturate(0.6)",
  modern: "invert(1) hue-rotate(200deg) brightness(0.85) contrast(0.9) saturate(0.7)",
  zen: "sepia(0.25) saturate(0.8)",
} as const;

/** The route on an OSM map with start / finish dots and the point under the chart cursor. */
export function RunMap({ route, marker }: { route: [number, number][]; marker: [number, number] | null }) {
  const theme = useTheme();
  const colors = useChartColors();
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const cursor = useRef<L.CircleMarker | null>(null);

  useEffect(() => {
    if (!element.current || route.length < 2) return;
    const m = L.map(element.current, { scrollWheelZoom: false, attributionControl: true, zoomSnap: 0.25 });
    m.attributionControl.setPrefix(false);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m);
    const line = L.polyline(route, { color: colors.series[0], weight: 4, opacity: 0.95 }).addTo(m);
    const dot = (at: [number, number], fill: string) =>
      L.circleMarker(at, { radius: 6, color: colors.surface, weight: 2, fillColor: fill, fillOpacity: 1 }).addTo(m);
    dot(route[0], colors.series[2]);
    dot(route[route.length - 1], colors.series[1]);
    cursor.current = L.circleMarker(route[0], { radius: 7, color: colors.surface, weight: 2, fillColor: colors.ink.primary, fillOpacity: 0 });
    m.fitBounds(line.getBounds(), { padding: [16, 16] });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
      cursor.current = null;
    };
  }, [route, colors]);

  useEffect(() => {
    const m = map.current;
    const c = cursor.current;
    if (!m || !c) return;
    if (marker) {
      c.setLatLng(marker).setStyle({ fillOpacity: 1, opacity: 1 });
      if (!m.hasLayer(c)) c.addTo(m);
    } else if (m.hasLayer(c)) c.remove();
  }, [marker]);

  return (
    // isolate: Leaflet's panes use z-index 400+, which would cover the sticky header and the tab bar
    <div
      ref={element}
      className="isolate h-64 overflow-hidden rounded-xl bg-zinc-900 [&_.leaflet-tile-pane]:[filter:var(--tile-filter)]"
      style={{ "--tile-filter": TILE_FILTER[theme] } as React.CSSProperties}
      role="img"
      aria-label="Mapa trasy běhu"
    />
  );
}
