"""
main.py — Glaukopis Backend Server

FastAPI + WebSocket server for the Glaukopis tactical simulator.

Architecture:
    • The radar scans continuously from t=0 (empty space initially).
    • The target (threat) is injected into the airspace either:
        - At a pre-programmed time from a scenario JSON file, OR
        - Manually via the GCS "INJECT THREAT" button.
    • When the radar confirms a track (M-of-N) and classifies it as
      HOSTILE (IFF=False), the Fire Control System launches the
      interceptor AUTOMATICALLY — no manual trigger.

WebSocket Commands (JSON):
    {"type": "inject_threat"}
        → Spawns the staged threat into the airspace immediately.

    {"type": "set_profile", "profile": "<name>"}
        → Changes the threat profile and resets the scenario.

    {"type": "load_scenario", "scenario_id": "<id>"}
        → Loads a scenario JSON file (sets seed, inject time, profile).

    {"type": "set_seed", "seed": <int>}
        → Changes the random seed for the current scenario.

    {"type": "pause"}
        → Pauses the simulation loop.

    {"type": "resume"}
        → Resumes the simulation loop.

    {"type": "restart"}
        → Full scenario reset.

REST Endpoints:
    GET /api/status        → Simulation status
    GET /api/profiles      → Available target profiles
    GET /api/scenarios     → Available scenario files
    GET /api/export/csv    → Download telemetry CSV for MATLAB

    POST /api/monte-carlo/start   → Start batch run
    POST /api/monte-carlo/stop    → Abort batch run
    GET  /api/monte-carlo/progress → Current progress + partial results
    GET  /api/monte-carlo/summary.csv    → Download summary CSV
    GET  /api/monte-carlo/timeseries.csv → Download timeseries CSV
"""

import asyncio
import json
import os
import random
import threading
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import numpy as np

from batch_runner import BatchRunner

from physics.universe import Universe, PROFILE_SPAWN_RANGES
from physics.entities.target import Target, TARGET_PROFILES
from physics.entities.radar import Radar
from physics.entities.missile import Missile

app = FastAPI(title="Glaukopis — Tactical Engagement Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Paths ───────────────────────────────────────────────────────────────────
SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"

# ─── Global simulation state ────────────────────────────────────────────────
universe = Universe()
radar: Radar = None        # type: ignore
missile: Missile = None    # type: ignore
current_profile: str = "Cruise Missile / DJI Drone"
current_seed: int = 42


def _create_scenario(
    profile_name: str,
    seed: int = 42,
    inject_at_time: float | None = None,
    threat_position: list | None = None,
    threat_velocity: list | None = None,
    scenario_id: str = "manual",
):
    """
    Instantiates the simulation entities.

    The radar and missile are added to the universe immediately.
    The target (threat) is STAGED but NOT injected — it appears only
    when the timed trigger fires or the operator clicks INJECT THREAT.
    """
    global radar, missile, current_profile, current_seed
    current_profile = profile_name
    current_seed = seed

    universe.entities.clear()
    universe.reset()

    # Apply scenario config (seed + inject time)
    universe.load_scenario_config({
        "scenario_id": scenario_id,
        "random_seed": seed,
        "threat": {"inject_at_time": inject_at_time},
    })

    # Radar fixed at origin
    radar = Radar("AESA_01", 0.0, 0.0, 0.0, universe=universe)

    # Missile idle at base
    missile = Missile("INTERCEPTOR_01", 0.0, 0.0, 0.0)
    missile.link_to_radar(radar)

    universe.add_entity(radar)
    universe.add_entity(missile)

    # Stage the threat (NOT added to universe yet)
    profile = TARGET_PROFILES.get(profile_name, TARGET_PROFILES["Cruise Missile / DJI Drone"])

    spawn_x = PROFILE_SPAWN_RANGES.get(profile_name, 20_000)
    pos = threat_position or [float(spawn_x), 2000.0, 3000.0]
    vel = threat_velocity or profile["default_velocity"].tolist()

    target = Target(
        id="TGT_01",
        x=pos[0], y=pos[1], z=pos[2],
        sigma_min=profile.get("sigma_min", 0.05),
        sigma_max=profile.get("sigma_max", 0.1),
        swerling_type=profile.get("swerling_type", 1),
        iff=profile.get("iff", False),
        max_speed=profile.get("max_speed"),
        profile_name=profile_name,
        display_label=profile.get("display_label", profile_name),
    )
    target.vel = np.array(vel, dtype=float)

    universe.stage_threat(target)


def _load_scenario_file(scenario_id: str) -> dict | None:
    """Loads a scenario JSON file from the scenarios/ directory."""
    filepath = SCENARIOS_DIR / f"{scenario_id}.json"
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    return None


def _apply_scenario(scenario: dict):
    """Creates the simulation from a scenario dict."""
    threat = scenario.get("threat", {})
    _create_scenario(
        profile_name=threat.get("profile", "Cruise Missile / DJI Drone"),
        seed=scenario.get("random_seed", 42),
        inject_at_time=threat.get("inject_at_time", None),
        threat_position=threat.get("initial_position", None),
        threat_velocity=threat.get("velocity", None),
        scenario_id=scenario.get("scenario_id", "manual"),
    )


# ─── Initial scenario ───────────────────────────────────────────────────────
_create_scenario(current_profile, seed=current_seed)

physics_task = None


@app.on_event("startup")
async def startup_event():
    global physics_task
    physics_task = asyncio.create_task(universe.run())


@app.on_event("shutdown")
async def shutdown_event():
    universe.running = False
    if physics_task:
        await physics_task


# ─── REST endpoints ─────────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    return {
        "status": "running",
        "time": universe.time,
        "entities": len(universe.entities),
        "profile": current_profile,
        "scenario_id": universe.scenario_id,
        "seed": current_seed,
        "threat_injected": universe.threat_injected,
        "interceptor_launched": universe.interceptor_launched,
    }


@app.get("/api/profiles")
async def get_profiles():
    """Returns available target profiles for the GCS dropdown."""
    profiles = []
    for name, data in TARGET_PROFILES.items():
        profiles.append({
            "name": name,
            "rcs": data["rcs"],
            "iff": data["iff"],
            "description": data["description"],
            "max_speed": data["max_speed"],
        })
    return profiles


@app.get("/api/scenarios")
async def get_scenarios():
    """Returns available scenario files."""
    scenarios = []
    if SCENARIOS_DIR.exists():
        for f in sorted(SCENARIOS_DIR.glob("*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                scenarios.append({
                    "id": data.get("scenario_id", f.stem),
                    "description": data.get("description", ""),
                    "profile": data.get("threat", {}).get("profile", ""),
                    "inject_at_time": data.get("threat", {}).get("inject_at_time", None),
                    "seed": data.get("random_seed", 0),
                })
            except Exception:
                pass
    return scenarios


@app.get("/api/export/csv")
async def export_csv():
    """Downloads the telemetry log as a CSV file for MATLAB."""
    csv_content = universe.export_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={universe.scenario_id}_seed{current_seed}.csv"
        },
    )


# ─── Monte Carlo Endpoints ───────────────────────────────────────────────────
batch_runner: BatchRunner | None = None
batch_thread: threading.Thread | None = None


@app.post("/api/monte-carlo/start")
async def mc_start(
    scenario_id: str = "CM_01_15km_head-on",
    seed_start: int = 1,
    seed_end: int = 50,
    include_timeseries: bool = True,
):
    """Starts a Monte Carlo batch run in a background thread."""
    global batch_runner, batch_thread

    # Load scenario file
    scenario = _load_scenario_file(scenario_id)
    if not scenario:
        return {"error": f"Scenario '{scenario_id}' not found"}

    # Stop any running batch
    if batch_runner and batch_runner.running:
        batch_runner.stop()
        if batch_thread:
            batch_thread.join(timeout=5)

    batch_runner = BatchRunner(scenario)

    def _run():
        batch_runner.run(
            seed_start=seed_start,
            seed_end=seed_end,
            include_timeseries=include_timeseries,
        )

    batch_thread = threading.Thread(target=_run, daemon=True)
    batch_thread.start()

    return {
        "status": "started",
        "scenario_id": scenario_id,
        "seeds": f"{seed_start}-{seed_end}",
        "total": seed_end - seed_start + 1,
    }


@app.post("/api/monte-carlo/stop")
async def mc_stop():
    """Aborts the current Monte Carlo batch after the current seed."""
    if batch_runner and batch_runner.running:
        batch_runner.stop()
        return {"status": "stopping"}
    return {"status": "not_running"}


@app.get("/api/monte-carlo/progress")
async def mc_progress():
    """Returns current batch progress and partial results."""
    if batch_runner is None:
        return {"running": False, "completed": 0, "total": 0, "rows": []}
    return batch_runner.get_progress()


@app.get("/api/monte-carlo/summary.csv")
async def mc_summary_csv():
    """Downloads the Monte Carlo summary CSV."""
    if batch_runner is None:
        return Response(content="no data\n", media_type="text/csv")
    csv_content = batch_runner.export_summary_csv()
    sid = batch_runner.scenario_id
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={sid}_monte_carlo_summary.csv"},
    )


@app.get("/api/monte-carlo/timeseries.csv")
async def mc_timeseries_csv():
    """Downloads the Monte Carlo timeseries CSV."""
    if batch_runner is None:
        return Response(content="no data\n", media_type="text/csv")
    csv_content = batch_runner.export_timeseries_csv()
    sid = batch_runner.scenario_id
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={sid}_monte_carlo_timeseries.csv"},
    )


# ─── WebSocket ───────────────────────────────────────────────────────────────
@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    universe.connected_clients.append(websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                msg = {"type": raw}

            cmd_type = msg.get("type", "")

            # ── INJECT THREAT ────────────────────────────────────────────
            if cmd_type == "inject_threat":
                universe.inject_threat()

            # ── SET PROFILE (resets scenario) ────────────────────────────
            elif cmd_type == "set_profile":
                profile_name = msg.get("profile", current_profile)
                if profile_name in TARGET_PROFILES:
                    _create_scenario(profile_name, seed=current_seed)
                    universe.paused = False

            # ── LOAD SCENARIO FILE ───────────────────────────────────────
            elif cmd_type == "load_scenario":
                scenario_id = msg.get("scenario_id", "")
                scenario = _load_scenario_file(scenario_id)
                if scenario:
                    _apply_scenario(scenario)
                    universe.paused = False

            # ── SET SEED ─────────────────────────────────────────────────
            elif cmd_type == "set_seed":
                new_seed = msg.get("seed", current_seed)
                _create_scenario(current_profile, seed=int(new_seed))
                universe.paused = False

            # ── PAUSE / RESUME ───────────────────────────────────────────
            elif cmd_type == "pause":
                universe.paused = True

            elif cmd_type == "resume":
                universe.paused = False

            # ── RESTART ──────────────────────────────────────────────────
            elif cmd_type == "restart":
                _create_scenario(current_profile, seed=current_seed)
                universe.paused = False

    except WebSocketDisconnect:
        if websocket in universe.connected_clients:
            universe.connected_clients.remove(websocket)
