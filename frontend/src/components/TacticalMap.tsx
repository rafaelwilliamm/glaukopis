"use client";

import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// ─── Leaflet Icons ─────────────────────────────────────────────────────────
const iconRadar = new L.Icon({
  iconUrl: 'https://cdn-icons-png.flaticon.com/512/3222/3222544.png',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

const iconTargetHostile = new L.Icon({
  iconUrl: 'https://cdn-icons-png.flaticon.com/512/71/71410.png',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const iconTargetFriendly = new L.Icon({
  iconUrl: 'https://cdn-icons-png.flaticon.com/512/71/71410.png',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const iconMissile = new L.Icon({
  iconUrl: 'https://cdn-icons-png.flaticon.com/128/1042/1042337.png',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

interface TacticalMapProps {
  entities: any[];
}

export default function TacticalMap({ entities }: TacticalMapProps) {
  const trackHistory = useRef<{[id: string]: [number, number][]}>({});

  // Map physics meters → Lat/Lng
  const BASE_LAT = 37.23;
  const BASE_LNG = -115.8;
  const METERS_PER_DEG_LAT = 111320;
  const METERS_PER_DEG_LNG = 111320 * Math.cos(BASE_LAT * Math.PI / 180.0);

  const convertToLatLng = (pos: {x: number, y: number, z: number}): [number, number] => {
    const lat = BASE_LAT + (pos.y / METERS_PER_DEG_LAT);
    const lng = BASE_LNG + (pos.x / METERS_PER_DEG_LNG);
    return [lat, lng];
  };

  useEffect(() => {
    entities.forEach(e => {
      if (e.type !== "Radar") {
        const ll = convertToLatLng(e.pos);
        if (!trackHistory.current[e.id]) {
          trackHistory.current[e.id] = [];
        }
        trackHistory.current[e.id].push(ll);
        // Limit trail length
        if (trackHistory.current[e.id].length > 500) {
          trackHistory.current[e.id].shift();
        }
      }
    });
  }, [entities]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <MapContainer
        center={[BASE_LAT, BASE_LNG]}
        zoom={11}
        scrollWheelZoom={true}
        style={{ height: '100%', width: '100%', background: '#0a0a0a' }}
        attributionControl={false}
      >
        <TileLayer
          url="https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png"
          maxZoom={20}
        />

        {entities.map((entity) => {
          const pos = convertToLatLng(entity.pos);
          let icon;
          let trailColor: string;
          let trailWeight = 1.5;
          let trailDash: string | undefined;

          if (entity.type === 'Radar') {
            icon = iconRadar;
            trailColor = '#22d3ee';
          } else if (entity.type === 'Target') {
            // IFF-based color coding
            const isIff = entity.telemetry?.iff ?? false;
            icon = isIff ? iconTargetFriendly : iconTargetHostile;
            trailColor = isIff ? '#22d3ee' : '#ef4444';
            trailWeight = 2;
          } else {
            // Missile
            icon = iconMissile;
            trailColor = '#fb923c';
            trailDash = '4';
          }

          const speed = Math.sqrt(
            entity.vel.x ** 2 + entity.vel.y ** 2 + entity.vel.z ** 2
          ).toFixed(1);

          return (
            <div key={entity.id}>
              <Marker position={pos} icon={icon}>
                <Popup>
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: '#fff', background: '#1a1a1a', padding: 6, borderRadius: 4 }}>
                    <strong>{entity.id}</strong> ({entity.type})<br />
                    Alt: {entity.pos.z.toFixed(0)} m<br />
                    Spd: {speed} m/s
                    {entity.telemetry?.engagement_result && (
                      <><br />Result: <strong>{entity.telemetry.engagement_result}</strong></>
                    )}
                    {entity.telemetry?.profile && (
                      <><br />Profile: {entity.telemetry.profile}</>
                    )}
                  </div>
                </Popup>
              </Marker>

              {/* Trail */}
              {trackHistory.current[entity.id] && trackHistory.current[entity.id].length > 1 && (
                <Polyline
                  positions={trackHistory.current[entity.id]}
                  pathOptions={{
                    color: trailColor,
                    weight: trailWeight,
                    opacity: 0.6,
                    dashArray: trailDash,
                  }}
                />
              )}

              {/* Radar estimated track position (dashed circle) */}
              {entity.type === 'Radar' && entity.telemetry?.track && (
                <Circle
                  center={convertToLatLng(entity.telemetry.track)}
                  radius={300}
                  pathOptions={{
                    color: '#22d3ee',
                    weight: 1,
                    dashArray: '5,5',
                    fillOpacity: 0.05,
                  }}
                />
              )}
            </div>
          );
        })}
      </MapContainer>
    </div>
  );
}
