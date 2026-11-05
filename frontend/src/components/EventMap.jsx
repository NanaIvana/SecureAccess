import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { useEffect } from "react";

function Fit({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 6);
    else if (points.length > 1) map.fitBounds(points, { padding: [40, 40], maxZoom: 7 });
  }, [map, points]);
  return null;
}

/** Carte : domicile déclaré et lieu de la connexion. */
export default function EventMap({ event, home }) {
  const points = [];
  const hasEvent = event?.latitude != null && event?.longitude != null;
  const hasHome = home?.lat != null && home?.lon != null;
  if (hasHome) points.push([home.lat, home.lon]);
  if (hasEvent) points.push([event.latitude, event.longitude]);
  if (!points.length) return <div className="empty">Pas de coordonnées pour cette connexion.</div>;
  const danger = getComputedStyle(document.documentElement).getPropertyValue("--danger").trim() || "#b42318";
  return (
    <div className="map">
      <MapContainer center={points[0]} zoom={5} style={{ height: "100%" }} scrollWheelZoom={false}>
        <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {hasHome && (
          <CircleMarker center={[home.lat, home.lon]} radius={8} pathOptions={{ color: "#2e7d4f", fillOpacity: 0.7 }}>
            <Tooltip permanent direction="top">Domicile : {home.city}</Tooltip>
          </CircleMarker>
        )}
        {hasEvent && (
          <CircleMarker center={[event.latitude, event.longitude]} radius={8} pathOptions={{ color: danger, fillOpacity: 0.7 }}>
            <Tooltip permanent direction="bottom">Connexion : {event.city || event.country}</Tooltip>
          </CircleMarker>
        )}
        {points.length === 2 && <Polyline positions={points} pathOptions={{ color: "#6b7b8c", dashArray: "6 6", weight: 2 }} />}
        <Fit points={points} />
      </MapContainer>
    </div>
  );
}
