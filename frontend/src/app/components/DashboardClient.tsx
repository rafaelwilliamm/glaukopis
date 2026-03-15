"use client";

import { useEffect, useState, useRef } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const MapComponent = dynamic(() => import('@/components/TacticalMap'), { ssr: false });

// ─── Target profiles (match backend) ──────────────────────────────────────
const PROFILES = [
  // ── CIVILIAN ──────────────────────────────────────────────────────────
  { name: "Boeing 747",                 label: "Boeing 747  —  σ=10–100 m²",              rcs: "10–100 m²",  iff: true,  swerling: 0, desc: "Large Commercial Airliner" },
  // ── CONVENTIONAL MILITARY ─────────────────────────────────────────────
  { name: "F/A-18 Hornet",              label: "F/A-18 Hornet  —  σ=1–10 m²",             rcs: "1–10 m²",    iff: false, swerling: 1, desc: "Non-stealth multirole." },
  { name: "F-16 Fighting Falcon",       label: "F-16 Fighting Falcon  —  σ=0.5–5 m²",     rcs: "0.5–5 m²",   iff: false, swerling: 1, desc: "Light multirole." },
  { name: "Su-27 Flanker",              label: "Su-27 Flanker  —  σ=3–15 m²",             rcs: "3–15 m²",    iff: false, swerling: 1, desc: "Heavy air superiority." },
  { name: "MiG-31 Foxhound",            label: "MiG-31 Foxhound  —  σ=5–20 m²",           rcs: "5–20 m²",    iff: false, swerling: 1, desc: "Heavy interceptor." },
  // ── STEALTH ───────────────────────────────────────────────────────────
  { name: "F-35 / F-22 Stealth",        label: "F-35 / F-22 Stealth  —  σ=0.001–0.05 m²", rcs: "0.001–0.05 m²", iff: false, swerling: 1, desc: "5th gen stealth." },
  { name: "PAK FA / Su-57",             label: "PAK FA / Su-57  —  σ=0.01–0.5 m²",        rcs: "0.01–0.5 m²",   iff: false, swerling: 1, desc: "Russian 5th gen." },
  // ── MISSILES & DRONES ─────────────────────────────────────────────────
  { name: "Cruise Missile / DJI Drone", label: "Cruise Missile / DJI Drone  —  σ=0.05–0.1 m²", rcs: "0.05–0.1 m²", iff: false, swerling: 1, desc: "Small cross-section drone or missile." },
  { name: "Bird (Large)",               label: "Bird (Large)  —  σ=0.005–0.01 m²",        rcs: "0.005–0.01 m²", iff: true,  swerling: 1, desc: "Clutter reference (40 km/h max)." },
];

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);
  const [simulationState, setSimulationState] = useState<any>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<any[]>([]);
  const [socketStatus, setSocketStatus] = useState("Connecting...");
  const [selectedProfile, setSelectedProfile] = useState("Cruise Missile / DJI Drone");
  const [seed, setSeed] = useState(42);
  const wsRef = useRef<WebSocket | null>(null);

  // Derived state
  const missileEntity = simulationState?.entities?.find((e: any) => e.type === "Missile");
  const radarEntity   = simulationState?.entities?.find((e: any) => e.type === "Radar");
  const targetEntity  = simulationState?.entities?.find((e: any) => e.type === "Target");
  const engagementFrozen  = simulationState?.engagement_frozen ?? false;
  const engagementResult  = simulationState?.engagement_result ?? null;
  const threatInjected    = simulationState?.threat_injected ?? false;
  const interceptorLaunched = simulationState?.interceptor_launched ?? false;
  const isPaused          = simulationState?.is_paused ?? false;
  const trackStatus = radarEntity?.telemetry?.track_status ?? "SEARCHING";

  useEffect(() => {
    setMounted(true);
    let keepAliveInterval: NodeJS.Timeout;

    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8000/ws/telemetry');
      wsRef.current = ws;

      ws.onopen = () => {
        setSocketStatus("Connected");
        keepAliveInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 1000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setSimulationState(data);

          let currentSnr = 0;
          let currentMissDistance: number | null = null;
          let currentGForce = 0;

          data.entities.forEach((e: any) => {
            if (e.type === "Radar" && e.telemetry) currentSnr = e.telemetry.snr;
            if (e.type === "Missile" && e.telemetry) {
              currentMissDistance = e.telemetry.miss_distance;
              currentGForce = e.telemetry.g_force;
            }
          });

          setTelemetryHistory(prev => {
            const newHistory = [...prev, {
              time: data.time.toFixed(1),
              snr: currentSnr,
              miss: currentMissDistance,
              gforce: currentGForce,
            }];
            if (newHistory.length > 150) newHistory.shift();
            return newHistory;
          });
        } catch { /* ignore parse errors */ }
      };

      ws.onclose = () => {
        setSocketStatus("Disconnected. Reconnecting...");
        wsRef.current = null;
        setTimeout(connectWebSocket, 2000);
      };
      ws.onerror = () => setSocketStatus("Error");
    };

    connectWebSocket();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (keepAliveInterval) clearInterval(keepAliveInterval);
    };
  }, []);

  // ─── Commands ────────────────────────────────────────────────────────────
  const sendCommand = (cmd: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  };

  const handleProfileChange = (profile: string) => {
    setSelectedProfile(profile);
    sendCommand({ type: "set_profile", profile });
    setTelemetryHistory([]);
  };

  const handleInjectThreat = () => {
    sendCommand({ type: "inject_threat" });
  };

  const handleRestart = () => {
    sendCommand({ type: "restart" });
    setTelemetryHistory([]);
  };

  const handleSeedChange = (newSeed: number) => {
    setSeed(newSeed);
    sendCommand({ type: "set_seed", seed: newSeed });
    setTelemetryHistory([]);
  };

  const handleDownloadCSV = () => {
    const link = document.createElement("a");
    link.href = "http://localhost:8000/api/export/csv";
    link.download = "glaukopis_telemetry.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!mounted) return null;

  // ─── Styling helpers ─────────────────────────────────────────────────────
  const trackStatusColor: Record<string, string> = {
    SEARCHING:  "text-neutral-400",
    TENTATIVE:  "text-yellow-400",
    CONFIRMED:  "text-green-400",
    TRACK_LOST: "text-red-400",
  };

  const iffColor = radarEntity?.telemetry?.iff ? "text-cyan-400" : "text-red-400";
  const iffLabel = radarEntity?.telemetry?.iff ? "FRIENDLY" : "HOSTILE";

  // Fire Control status
  let fcStatus = "STANDBY";
  let fcColor  = "text-neutral-500";
  if (engagementFrozen) { fcStatus = engagementResult === "HIT" ? "TARGET DESTROYED" : "MISS — NO KILL"; fcColor = engagementResult === "HIT" ? "text-green-400" : "text-red-400"; }
  else if (interceptorLaunched) { fcStatus = "INTERCEPTOR IN FLIGHT"; fcColor = "text-orange-400"; }
  else if (trackStatus === "CONFIRMED" && !radarEntity?.telemetry?.iff) { fcStatus = "ENGAGING..."; fcColor = "text-red-400"; }
  else if (threatInjected) { fcStatus = "TRACKING"; fcColor = "text-yellow-400"; }
  else { fcStatus = "SCANNING — NO THREATS"; fcColor = "text-neutral-500"; }

  return (
    <div className="flex flex-col h-screen bg-neutral-950 text-white font-mono">
      {/* ── HEADER ───────────────────────────────────────────────────── */}
      <div className="flex justify-between items-center px-6 py-3 border-b border-neutral-800 bg-neutral-900/80 backdrop-blur-sm">
        <div>
          <h1 className="text-2xl font-black tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500">
            GLAUKOPIS GCS
          </h1>
          <p className="text-xs text-neutral-500 tracking-widest">TACTICAL ENGAGEMENT SIMULATOR v0.2.0</p>
        </div>

        <div className="flex gap-3 items-center">
          {/* Profile Selector */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-neutral-400 uppercase tracking-wider">Threat:</label>
            <div className="relative group">
              <select
                id="profile-selector"
                value={selectedProfile}
                onChange={(e) => handleProfileChange(e.target.value)}
                className="bg-neutral-800 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-500 transition-colors cursor-pointer"
              >
                {PROFILES.map(p => (
                  <option key={p.name} value={p.name}>{p.label}</option>
                ))}
              </select>
              
              {/* Info Card Sidebar/Tooltip */}
              <div className="absolute top-full right-0 mt-2 w-72 bg-neutral-900 border border-neutral-700 rounded shadow-2xl hidden group-hover:block z-50 p-4">
                <div className="text-xs">
                  {(() => {
                    const p = PROFILES.find(x => x.name === selectedProfile);
                    if (!p) return null;
                    return (
                      <>
                        <div className="font-bold text-cyan-400 mb-2 border-b border-neutral-800 pb-1">{p.name}</div>
                        <div className="grid grid-cols-2 gap-y-2 gap-x-1 text-neutral-300">
                          <span className="text-neutral-500 font-semibold">RCS:</span><span>{p.rcs}</span>
                          <span className="text-neutral-500 font-semibold">IFF:</span><span className={p.iff ? "text-green-400 font-bold" : "text-red-400 font-bold"}>{p.iff ? "FRIENDLY" : "HOSTILE"}</span>
                          <span className="text-neutral-500 font-semibold">Swerling:</span><span>Type {p.swerling}</span>
                        </div>
                        <div className="mt-3 text-neutral-400 italic text-[11px] leading-tight text-justify">
                          {p.desc}
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* Radar Profile Display */}
          <div className="flex items-center gap-2 ml-2 px-3 py-1.5 bg-neutral-800/30 rounded border border-neutral-700/50">
            <span className="text-[10px] text-neutral-500 uppercase tracking-widest font-black">Radar:</span>
            <span className="text-xs font-bold text-cyan-400">
              {radarEntity?.telemetry?.radar_profile ? (
                `${radarEntity.telemetry.radar_profile} (Band X, ${radarEntity.telemetry.radar_gain_db}dB)`
              ) : (
                "Pantsir-S1 (Band X, 40dB)"
              )}
            </span>
          </div>

          {/* Seed */}
          <div className="flex items-center gap-1">
            <label className="text-xs text-neutral-400 uppercase tracking-wider">Seed:</label>
            <input
              type="number"
              value={seed}
              onChange={(e) => handleSeedChange(parseInt(e.target.value) || 0)}
              className="bg-neutral-800 border border-neutral-600 rounded px-2 py-1.5 text-sm text-white w-20 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Connection */}
          <div className="flex items-center gap-2 px-3 py-1 rounded bg-neutral-800 border border-neutral-700">
            <div className={`w-2.5 h-2.5 rounded-full ${socketStatus === 'Connected' ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.7)]' : 'bg-red-500 animate-pulse'}`} />
            <span className="text-xs">{socketStatus}</span>
          </div>

          {/* Export CSV */}
          <button onClick={handleDownloadCSV} className="px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-cyan-400 text-xs font-semibold rounded border border-neutral-600 transition-all uppercase tracking-wider">
            📥 CSV
          </button>

          {/* Monte Carlo */}
          <Link href="/monte-carlo" className="px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-violet-400 text-xs font-semibold rounded border border-neutral-600 transition-all uppercase tracking-wider">
            📊 Monte Carlo
          </Link>

          {/* Pause / Resume */}
          <button onClick={() => sendCommand({ type: isPaused ? "resume" : "pause" })} className={`px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold rounded border transition-all uppercase tracking-wider w-24 ${isPaused ? 'text-green-400 border-green-700/50' : 'text-yellow-400 border-neutral-600'}`}>
            {isPaused ? "▶ Play" : "⏸ Pause"}
          </button>

          {/* Reset */}
          <button onClick={handleRestart} className="px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-xs font-semibold rounded border border-neutral-600 transition-all uppercase tracking-wider">
            Reset
          </button>
        </div>
      </div>

      {/* ── MAIN CONTENT ─────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: Map ──────────────────────────────────────────────── */}
        <div className="flex-[2] relative border-r border-neutral-800">
          <MapComponent entities={simulationState?.entities || []} />

          {/* Sim Time Overlay */}
          <div className="absolute top-4 right-4 bg-black/70 px-4 py-3 rounded-lg border border-neutral-700 backdrop-blur-sm z-[1000] pointer-events-none">
            <p className="text-[10px] text-neutral-500 uppercase tracking-widest mb-1">Sim Time</p>
            <p className="font-mono text-cyan-400 text-2xl font-bold">
              {simulationState?.time?.toFixed(2) || "0.00"}<span className="text-sm text-neutral-500 ml-1">s</span>
            </p>
          </div>

          {/* Engagement Result Banner */}
          {engagementFrozen && (
            <div className="absolute inset-x-0 top-1/3 flex justify-center z-[1001] pointer-events-none">
              <div className={`px-12 py-6 rounded-xl border-2 backdrop-blur-md shadow-2xl ${
                engagementResult === "HIT"
                  ? "bg-green-900/80 border-green-400 shadow-green-500/30"
                  : "bg-red-900/80 border-red-400 shadow-red-500/30"
              }`}>
                <p className={`text-4xl font-black tracking-widest ${
                  engagementResult === "HIT" ? "text-green-300" : "text-red-300"
                }`}>
                  {engagementResult === "HIT" ? "🎯 TARGET DESTROYED" : "💨 ENGAGEMENT FAILED"}
                </p>
                <p className="text-center text-sm text-neutral-300 mt-2">
                  Miss Distance: {missileEntity?.telemetry?.miss_distance?.toFixed(2) ?? "—"} m
                </p>
              </div>
            </div>
          )}

          {/* Interceptor Auto-Launch Banner */}
          {interceptorLaunched && !engagementFrozen && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1001] pointer-events-none">
              <div className="px-6 py-2 rounded-lg bg-orange-900/80 border border-orange-400 backdrop-blur-sm">
                <p className="text-orange-300 text-sm font-bold tracking-wider">
                  ⚡ TRACK CONFIRMED — INTERCEPTOR LAUNCHED (AUTO)
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT: Control & Telemetry ─────────────────────────────── */}
        <div className="flex-[1] flex flex-col gap-0 overflow-y-auto bg-neutral-900">

          {/* ── THREAT INJECTION ─────────────────────────────────────── */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-3">Threat Injection</h2>
            <button
              id="inject-threat-button"
              onClick={handleInjectThreat}
              disabled={threatInjected}
              className={`w-full py-3 rounded-lg text-sm font-black uppercase tracking-widest transition-all border-2 ${
                !threatInjected
                  ? "bg-amber-600 hover:bg-amber-500 border-amber-400 text-white shadow-[0_0_25px_rgba(217,119,6,0.5)] hover:shadow-[0_0_40px_rgba(217,119,6,0.7)] cursor-pointer active:scale-95"
                  : "bg-neutral-800 border-neutral-700 text-neutral-600 cursor-not-allowed"
              }`}
            >
              {threatInjected ? "⚠ THREAT IN AIRSPACE" : "🚀 INJECT THREAT"}
            </button>
            {!threatInjected && (
              <p className="text-[10px] text-neutral-500 mt-2 text-center">
                Radar scanning empty space… Inject threat to begin engagement.
              </p>
            )}
          </div>

          {/* ── FIRE CONTROL STATUS ──────────────────────────────────── */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-2">Fire Control (Automatic)</h2>
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                fcStatus.includes("DESTROYED") ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.7)]" :
                fcStatus.includes("FLIGHT") ? "bg-orange-500 animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.7)]" :
                fcStatus.includes("ENGAGING") ? "bg-red-500 animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.7)]" :
                "bg-neutral-600"
              }`} />
              <span className={`text-sm font-bold tracking-wider ${fcColor}`}>{fcStatus}</span>
            </div>
          </div>

          {/* ── TRACK TABLE ─────────────────────────────────────────── */}
          <div className="p-4 border-b border-neutral-800">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-3">Track Classification</h2>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div className="text-neutral-500">Status</div>
              <div className={`font-bold ${trackStatusColor[trackStatus] || "text-neutral-400"}`}>
                {trackStatus === "CONFIRMED" && "● "}{trackStatus}
              </div>
              <div className="text-neutral-500">RCS Class</div>
              <div className="text-white">{radarEntity?.telemetry?.rcs_class ?? "—"}</div>
              <div className="text-neutral-500">Doppler</div>
              <div className="text-white">{radarEntity?.telemetry?.doppler_speed ?? "—"} m/s</div>
              <div className="text-neutral-500">IFF</div>
              <div className={`font-bold ${iffColor}`}>{trackStatus !== "SEARCHING" ? iffLabel : "—"}</div>
              <div className="text-neutral-500">SNR</div>
              <div className="text-cyan-400">{radarEntity?.telemetry?.snr ?? "—"} dB</div>
              <div className="text-neutral-500">Profile</div>
              <div className="text-neutral-300">{targetEntity?.telemetry?.profile ?? "—"}</div>
            </div>
          </div>

          {/* ── SNR Chart ───────────────────────────────────────────── */}
          <div className="p-4 border-b border-neutral-800 min-h-[180px]">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-sm bg-cyan-500" /> Radar SNR (dB)
            </h2>
            <div className="h-[130px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={telemetryHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                  <XAxis dataKey="time" stroke="#525252" tick={{ fontSize: 9 }} />
                  <YAxis stroke="#525252" tick={{ fontSize: 9 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', fontSize: 11 }} />
                  <Line type="monotone" dataKey="snr" stroke="#22d3ee" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── Miss Distance Chart ─────────────────────────────────── */}
          <div className="p-4 border-b border-neutral-800 min-h-[180px]">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-sm bg-orange-500" /> Miss Distance (m)
            </h2>
            <div className="h-[130px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={telemetryHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                  <XAxis dataKey="time" stroke="#525252" tick={{ fontSize: 9 }} />
                  <YAxis stroke="#525252" tick={{ fontSize: 9 }} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', fontSize: 11 }} />
                  <Line type="monotone" dataKey="miss" stroke="#fb923c" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── G-Force Chart ───────────────────────────────────────── */}
          <div className="p-4 min-h-[180px]">
            <h2 className="text-[10px] text-neutral-500 uppercase tracking-widest mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-sm bg-red-500" /> Interceptor G-Force
            </h2>
            <div className="h-[130px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={telemetryHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                  <XAxis dataKey="time" stroke="#525252" tick={{ fontSize: 9 }} />
                  <YAxis stroke="#525252" tick={{ fontSize: 9 }} domain={[0, 35]} />
                  <Tooltip contentStyle={{ backgroundColor: '#171717', border: '1px solid #404040', fontSize: 11 }} />
                  <Line type="monotone" dataKey="gforce" stroke="#ef4444" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
