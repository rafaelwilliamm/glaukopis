"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";

interface SummaryRow {
  scenario_id: string;
  random_seed: number;
  profile: string;
  rcs_m2: number;
  result: string;
  miss_distance_m: number;
  time_to_detect_s: number | null;
  time_to_confirm_s: number | null;
  time_to_launch_s: number | null;
  time_to_intercept_s: number | null;
  total_duration_s: number;
  mean_snr_db: number;
  peak_snr_db: number;
  peak_g_force: number;
}

interface Progress {
  running: boolean;
  aborted: boolean;
  completed: number;
  total: number;
  percent: number;
  pk_percent: number;
  hits: number;
  misses: number;
  mean_miss_distance_m: number;
  std_miss_distance_m: number;
  rows: SummaryRow[];
}

interface ScenarioInfo {
  id: string;
  description: string;
  profile: string;
  inject_at_time: number | null;
  seed: number;
}

const API = "http://localhost:8000";

// ─── Target profiles (match backend) ──────────────────────────────────────
const PROFILES = [
  // ── CIVILIAN ──────────────────────────────────────────────────────────
  { name: "Boeing 747",                 label: "Boeing 747  —  σ=10–100 m²" },
  // ── CONVENTIONAL MILITARY ─────────────────────────────────────────────
  { name: "F/A-18 Hornet",              label: "F/A-18 Hornet  —  σ=1–10 m²" },
  { name: "F-16 Fighting Falcon",       label: "F-16 Fighting Falcon  —  σ=0.5–5 m²" },
  { name: "Su-27 Flanker",              label: "Su-27 Flanker  —  σ=3–15 m²" },
  { name: "MiG-31 Foxhound",            label: "MiG-31 Foxhound  —  σ=5–20 m²" },
  // ── STEALTH ───────────────────────────────────────────────────────────
  { name: "F-35 / F-22 Stealth",        label: "F-35 / F-22 Stealth  —  σ=0.001–0.05 m²" },
  { name: "PAK FA / Su-57",             label: "PAK FA / Su-57  —  σ=0.01–0.5 m²" },
  // ── MISSILES & DRONES ─────────────────────────────────────────────────
  { name: "Cruise Missile / DJI Drone", label: "Cruise Missile / DJI Drone  —  σ=0.05–0.1 m²" },
  { name: "Bird (Large)",               label: "Bird (Large)  —  σ=0.005–0.01 m²" },
];

export default function MonteCarloClient() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("CM_01_15km_head-on");
  const [seedStart, setSeedStart] = useState(1);
  const [seedEnd, setSeedEnd] = useState(50);
  const [includeTimeseries, setIncludeTimeseries] = useState(true);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Load scenarios on mount
  useEffect(() => {
    fetch(`${API}/api/scenarios`)
      .then((r) => r.json())
      .then((data) => {
        setScenarios(data);
        if (data.length > 0) setSelectedScenario(data[0].id);
      })
      .catch(() => {});
  }, []);

  // Poll progress while running
  useEffect(() => {
    if (polling) {
      const poll = () => {
        fetch(`${API}/api/monte-carlo/progress`)
          .then((r) => r.json())
          .then((data: Progress) => {
            setProgress(data);
            if (!data.running) {
              setPolling(false);
            }
          })
          .catch(() => {});
      };
      poll(); // immediate first
      pollRef.current = setInterval(poll, 300);
      return () => {
        if (pollRef.current) clearInterval(pollRef.current);
      };
    }
  }, [polling]);

  const handleStart = async () => {
    const params = new URLSearchParams({
      scenario_id: selectedScenario,
      seed_start: seedStart.toString(),
      seed_end: seedEnd.toString(),
      include_timeseries: includeTimeseries.toString(),
    });
    await fetch(`${API}/api/monte-carlo/start?${params}`, { method: "POST" });
    setPolling(true);
  };

  const handleStop = async () => {
    await fetch(`${API}/api/monte-carlo/stop`, { method: "POST" });
  };

  const handleDownload = (type: "summary" | "timeseries") => {
    const link = document.createElement("a");
    link.href = `${API}/api/monte-carlo/${type}.csv`;
    link.download = `monte_carlo_${type}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const isRunning = progress?.running ?? false;
  const isDone = progress && !progress.running && progress.completed > 0;
  const rows = progress?.rows ?? [];

  return (
    <div className="flex flex-col h-screen bg-neutral-950 text-white font-mono">
      {/* ── HEADER ───────────────────────────────────────────────────── */}
      <div className="flex justify-between items-center px-6 py-3 border-b border-neutral-800 bg-neutral-900/80 backdrop-blur-sm">
        <div>
          <h1 className="text-2xl font-black tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500">
            GLAUKOPIS GCS
          </h1>
          <p className="text-xs text-neutral-500 tracking-widest">
            MONTE CARLO BATCH SIMULATION
          </p>
        </div>
        <div className="flex gap-3 items-center">
          <Link
            href="/"
            className="px-4 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-xs font-semibold rounded border border-neutral-600 transition-all uppercase tracking-wider"
          >
            🎯 Interactive Sim
          </Link>
        </div>
      </div>

      {/* ── MAIN ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto space-y-6">

          {/* ── CONTROLS ─────────────────────────────────────────────── */}
          <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
            <h2 className="text-xs text-neutral-500 uppercase tracking-widest mb-4">
              Batch Configuration
            </h2>
            <div className="grid grid-cols-4 gap-4 items-end">
              {/* Scenario */}
              <div className="col-span-2">
                <label className="text-xs text-neutral-400 uppercase tracking-wider block mb-1">
                  Scenario
                </label>
                <select
                  value={selectedScenario}
                  onChange={(e) => setSelectedScenario(e.target.value)}
                  disabled={isRunning}
                  className="w-full bg-neutral-800 border border-neutral-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                >
                  {scenarios.map((s) => {
                    const profileLabel = PROFILES.find(p => p.name === s.profile)?.label || s.profile;
                    return (
                      <option key={s.id} value={s.id}>
                        {s.id} — {profileLabel}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Seed range */}
              <div>
                <label className="text-xs text-neutral-400 uppercase tracking-wider block mb-1">
                  Seeds
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={seedStart}
                    onChange={(e) => setSeedStart(parseInt(e.target.value) || 1)}
                    disabled={isRunning}
                    className="w-20 bg-neutral-800 border border-neutral-600 rounded px-2 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                  />
                  <span className="text-neutral-500 text-xs">to</span>
                  <input
                    type="number"
                    value={seedEnd}
                    onChange={(e) => setSeedEnd(parseInt(e.target.value) || 50)}
                    disabled={isRunning}
                    className="w-20 bg-neutral-800 border border-neutral-600 rounded px-2 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                  />
                </div>
              </div>

              {/* Timeseries checkbox */}
              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeTimeseries}
                    onChange={(e) => setIncludeTimeseries(e.target.checked)}
                    disabled={isRunning}
                    className="w-4 h-4 accent-cyan-500"
                  />
                  <span className="text-xs text-neutral-400 uppercase tracking-wider">
                    Export Timeseries
                  </span>
                </label>
              </div>
            </div>

            {/* Buttons */}
            <div className="flex gap-3 mt-5">
              <button
                onClick={handleStart}
                disabled={isRunning}
                className={`px-8 py-3 rounded-lg text-sm font-black uppercase tracking-widest transition-all border-2 ${
                  !isRunning
                    ? "bg-green-600 hover:bg-green-500 border-green-400 text-white shadow-[0_0_20px_rgba(34,197,94,0.4)] cursor-pointer active:scale-95"
                    : "bg-neutral-800 border-neutral-700 text-neutral-600 cursor-not-allowed"
                }`}
              >
                ▶ START
              </button>
              <button
                onClick={handleStop}
                disabled={!isRunning}
                className={`px-8 py-3 rounded-lg text-sm font-black uppercase tracking-widest transition-all border-2 ${
                  isRunning
                    ? "bg-red-600 hover:bg-red-500 border-red-400 text-white cursor-pointer"
                    : "bg-neutral-800 border-neutral-700 text-neutral-600 cursor-not-allowed"
                }`}
              >
                ⏹ STOP
              </button>

              {isDone && (
                <>
                  <button
                    onClick={() => handleDownload("summary")}
                    className="px-6 py-3 bg-neutral-800 hover:bg-neutral-700 text-cyan-400 text-sm font-semibold rounded-lg border border-neutral-600 transition-all uppercase tracking-wider"
                  >
                    📥 Summary CSV
                  </button>
                  {includeTimeseries && (
                    <button
                      onClick={() => handleDownload("timeseries")}
                      className="px-6 py-3 bg-neutral-800 hover:bg-neutral-700 text-cyan-400 text-sm font-semibold rounded-lg border border-neutral-600 transition-all uppercase tracking-wider"
                    >
                      📥 Timeseries CSV
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* ── PROGRESS ─────────────────────────────────────────────── */}
          {progress && progress.total > 0 && (
            <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
              {/* Progress bar */}
              <div className="mb-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs text-neutral-400 uppercase tracking-wider">
                    {isRunning ? `Running seed ${progress.completed + 1}…` : progress.aborted ? "Aborted" : "Complete"}
                  </span>
                  <span className="text-sm font-bold text-cyan-400">
                    {progress.completed}/{progress.total} ({progress.percent}%)
                  </span>
                </div>
                <div className="w-full h-3 bg-neutral-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      isRunning ? "bg-gradient-to-r from-cyan-500 to-blue-500" : "bg-green-500"
                    }`}
                    style={{ width: `${progress.percent}%` }}
                  />
                </div>
              </div>

              {/* Stats cards */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-neutral-800 rounded-lg p-4 text-center border border-neutral-700">
                  <p className="text-[10px] text-neutral-500 uppercase tracking-widest mb-1">P_k</p>
                  <p className="text-3xl font-black text-green-400">{progress.pk_percent}%</p>
                  <p className="text-[10px] text-neutral-500 mt-1">{progress.hits} HIT / {progress.misses} MISS</p>
                </div>
                <div className="bg-neutral-800 rounded-lg p-4 text-center border border-neutral-700">
                  <p className="text-[10px] text-neutral-500 uppercase tracking-widest mb-1">Mean Miss Dist.</p>
                  <p className="text-3xl font-black text-orange-400">{progress.mean_miss_distance_m}</p>
                  <p className="text-[10px] text-neutral-500 mt-1">meters</p>
                </div>
                <div className="bg-neutral-800 rounded-lg p-4 text-center border border-neutral-700">
                  <p className="text-[10px] text-neutral-500 uppercase tracking-widest mb-1">σ Miss Dist.</p>
                  <p className="text-3xl font-black text-yellow-400">{progress.std_miss_distance_m}</p>
                  <p className="text-[10px] text-neutral-500 mt-1">meters</p>
                </div>
                <div className="bg-neutral-800 rounded-lg p-4 text-center border border-neutral-700">
                  <p className="text-[10px] text-neutral-500 uppercase tracking-widest mb-1">Completed</p>
                  <p className="text-3xl font-black text-cyan-400">{progress.completed}</p>
                  <p className="text-[10px] text-neutral-500 mt-1">of {progress.total} seeds</p>
                </div>
              </div>
            </div>
          )}

          {/* ── RESULTS TABLE ────────────────────────────────────────── */}
          {rows.length > 0 && (
            <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
              <h2 className="text-xs text-neutral-500 uppercase tracking-widest mb-4">
                Results ({rows.length} seeds)
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-neutral-500 uppercase tracking-wider border-b border-neutral-700">
                      <th className="text-left py-2 px-2">Seed</th>
                      <th className="text-left py-2 px-2">Result</th>
                      <th className="text-right py-2 px-2">Miss (m)</th>
                      <th className="text-right py-2 px-2">t_detect</th>
                      <th className="text-right py-2 px-2">t_confirm</th>
                      <th className="text-right py-2 px-2">t_launch</th>
                      <th className="text-right py-2 px-2">t_intercept</th>
                      <th className="text-right py-2 px-2">SNR_mean</th>
                      <th className="text-right py-2 px-2">SNR_peak</th>
                      <th className="text-right py-2 px-2">G_peak</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => (
                      <tr
                        key={i}
                        className="border-b border-neutral-800 hover:bg-neutral-800/50 transition-colors"
                      >
                        <td className="py-2 px-2 text-neutral-300">{row.random_seed}</td>
                        <td className="py-2 px-2">
                          <span
                            className={`font-bold ${
                              row.result === "HIT" ? "text-green-400" : row.result === "MISS" ? "text-red-400" : "text-yellow-400"
                            }`}
                          >
                            {row.result}
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right text-neutral-300">{row.miss_distance_m}</td>
                        <td className="py-2 px-2 text-right text-neutral-400">{row.time_to_detect_s ?? "—"}</td>
                        <td className="py-2 px-2 text-right text-neutral-400">{row.time_to_confirm_s ?? "—"}</td>
                        <td className="py-2 px-2 text-right text-neutral-400">{row.time_to_launch_s ?? "—"}</td>
                        <td className="py-2 px-2 text-right text-neutral-400">{row.time_to_intercept_s ?? "—"}</td>
                        <td className="py-2 px-2 text-right text-cyan-400">{row.mean_snr_db}</td>
                        <td className="py-2 px-2 text-right text-cyan-300">{row.peak_snr_db}</td>
                        <td className="py-2 px-2 text-right text-orange-400">{row.peak_g_force}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
