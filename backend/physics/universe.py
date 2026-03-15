"""
universe.py — Truth Model, Fire Control, and Simulation Engine

The Universe owns all entity positions/velocities as they truly are.
No downstream consumer receives truth — only sensor-processed data.

Key behaviours:
    • Threat Injection: the target does NOT exist at t=0.  It is injected
      either at a pre-programmed time (inject_at_time from a scenario file)
      or manually via the GCS "INJECT THREAT" button.  Until injection the
      radar scans empty space.

    • Automatic Fire Control: when the radar's track reaches CONFIRMED
      status and the IFF classification returns HOSTILE, the Fire Control
      System launches the interceptor automatically — no human in the
      time-critical loop.

    • Deterministic RNG: np.random.seed(scenario_seed) is set at scenario
      load time so every AWGN sample, Swerling fluctuation, etc. is
      reproducible.  Same seed → same results.

    • CSV Telemetry: every frame is recorded for MATLAB export.  The CSV
      includes scenario_id and random_seed in every row.
"""

from typing import List
import math
import numpy as np
import random
import asyncio
import json
import csv
import io
from fastapi import WebSocket

# ─── Target Spawn Ranges (80% of max detection) ───────────────────────────
PROFILE_SPAWN_RANGES = {
    "Boeing 747":              60_000,   # 80% of ~85km max (easily detected)
    "Su-27 Flanker":           43_000,   # 80% of 54km
    "MiG-31 Foxhound":         50_000,   # 80% of ~62km (large RCS)
    "F/A-18 Hornet":           38_000,   # 80% of ~47km
    "F-16 Fighting Falcon":    28_000,   # 80% of 35km
    "PAK FA / Su-57":          18_000,   # 80% of ~22km (partial stealth)
    "Cruise Missile / DJI Drone": 18_000,# 80% of 23km
    "F-35 / F-22 Stealth":      6_000,  # 80% of 7km — very short, by design
    "Bird (Large)":             5_000,   # low and slow, short range
}


class PhysicsEntity:
    """Base class for every object in the simulation universe."""

    def __init__(self, id: str, x: float, y: float, z: float):
        self.id = id
        self.pos = np.array([x, y, z], dtype=float)
        self.vel = np.array([0.0, 0.0, 0.0], dtype=float)
        self.accel = np.array([0.0, 0.0, 0.0], dtype=float)

    def update_kinematics(self, dt: float):
        """
        4th-order Runge-Kutta kinematic integrator.
        Reduces positional truncation error from O(dt²) to O(dt⁴).
        Critical for terminal phase accuracy where miss distance is measured.
        """
        # k1
        k1_v = self.accel
        k1_p = self.vel
        
        # k2
        v2 = self.vel + 0.5 * dt * k1_v
        k2_v = self.accel
        k2_p = v2
        
        # k3
        v3 = self.vel + 0.5 * dt * k2_v
        k3_v = self.accel
        k3_p = v3
        
        # k4
        v4 = self.vel + dt * k3_v
        k4_v = self.accel
        k4_p = v4
        
        self.pos += (dt / 6.0) * (k1_p + 2*k2_p + 2*k3_p + k4_p)
        self.vel += (dt / 6.0) * (k1_v + 2*k2_v + 2*k3_v + k4_v)


class Universe:
    """
    The authoritative Truth Model of the simulation.

    Implements:
        • Threat injection (timed or manual)
        • Automatic Fire Control (no manual missile launch)
        • Engagement freeze on HIT/MISS
        • Per-frame telemetry recording for CSV export
    """

    def __init__(self):
        self.entities: List[PhysicsEntity] = []
        self.time: float = 0.0
        self.dt: float = 0.1          # 10 Hz tick rate
        self.running: bool = False
        self.connected_clients: List[WebSocket] = []

        # ── Scenario ─────────────────────────────────────────────────────
        self.scenario_id: str = "manual"
        self.random_seed: int = 0

        # ── Execution state ──────────────────────────────────────────────
        self.running: bool = False
        self.paused: bool = False
        self.dt: float = 0.1          # 10 Hz tick rate

        # ── Threat injection ─────────────────────────────────────────────
        self.threat_injected: bool = False
        self.inject_at_time: float | None = None  # None = manual injection

        # ── Pending threat (staged but not yet injected) ─────────────────
        self._pending_threat = None  # PhysicsEntity to add when inject fires

        # ── Engagement ───────────────────────────────────────────────────
        self.engagement_frozen: bool = False
        self.engagement_result: str | None = None  # "HIT" | "MISS" | None
        self.interceptor_launched: bool = False

        # ── Telemetry log ────────────────────────────────────────────────
        self.telemetry_log: list[dict] = []

    # ──────────────────────────────────────────────────────────────────────
    def get_entity(self, entity_id: str) -> PhysicsEntity | None:
        for e in self.entities:
            if e.id == entity_id:
                return e
        return None

    def add_entity(self, entity: PhysicsEntity):
        self.entities.append(entity)

    def stage_threat(self, threat):
        """
        Stages a threat entity for deferred injection.
        The threat will be added to the universe either at inject_at_time
        or when the operator clicks INJECT THREAT.
        """
        self._pending_threat = threat

    def inject_threat(self):
        """Injects the staged threat into the simulation immediately."""
        if self._pending_threat is not None and not self.threat_injected:
            self.entities.append(self._pending_threat)
            self.threat_injected = True

    # ──────────────────────────────────────────────────────────────────────
    #  Automatic Fire Control
    # ──────────────────────────────────────────────────────────────────────
    def _fire_control(self):
        """
        Automatic Fire Control System (FCS).

        Logic:
            IF   radar track status == CONFIRMED
            AND  IFF classification == HOSTILE (iff == False)
            AND  interceptor not yet launched
            THEN launch the interceptor automatically

        This mirrors real SAM/SHORAD doctrine where the human authorizes
        engagement policy, not individual shots.
        """
        radar = None
        missile = None

        for e in self.entities:
            if e.__class__.__name__ == "Radar":
                radar = e
            elif e.__class__.__name__ == "Missile":
                missile = e

        if radar is None or missile is None:
            return

        if (
            radar.track["valid"]
            and radar.track["status"] == "CONFIRMED"
            and not radar.track["iff"]           # IFF=False → HOSTILE
            and not missile.launched
            and not self.interceptor_launched
        ):
            missile.launch(radar.track["estimated_pos"].copy())
            self.interceptor_launched = True

    # ──────────────────────────────────────────────────────────────────────
    #  Broadcast — WebSocket push to all GCS clients
    # ──────────────────────────────────────────────────────────────────────
    async def broadcast_state(self):
        if not self.connected_clients:
            return

        state = {
            "time": round(self.time, 2),
            "engagement_frozen": self.engagement_frozen,
            "engagement_result": self.engagement_result,
            "threat_injected": self.threat_injected,
            "interceptor_launched": self.interceptor_launched,
            "scenario_id": self.scenario_id,
            "is_paused": self.paused,
            "entities": [],
        }

        for e in self.entities:
            entry = {
                "id": e.id,
                "type": e.__class__.__name__,
                "pos": {
                    "x": float(e.pos[0]),
                    "y": float(e.pos[1]),
                    "z": float(e.pos[2]),
                },
                "vel": {
                    "x": float(e.vel[0]),
                    "y": float(e.vel[1]),
                    "z": float(e.vel[2]),
                },
            }
            if hasattr(e, "get_telemetry"):
                entry["telemetry"] = e.get_telemetry()
            state["entities"].append(entry)

        disconnected = []
        for client in self.connected_clients:
            try:
                await client.send_json(state)
            except Exception:
                disconnected.append(client)
        for c in disconnected:
            self.connected_clients.remove(c)

    # ──────────────────────────────────────────────────────────────────────
    #  Step — one simulation frame
    # ──────────────────────────────────────────────────────────────────────
    async def step(self):
        """
        Order of operations:
            1. Check timed threat injection.
            2. Agent logic tick (Radar scan, Missile guidance).
            3. Automatic Fire Control.
            4. Check engagement outcomes (HIT/MISS).
            5. Kinematics integration.
            6. Record telemetry.
            7. Broadcast to GCS.
        """
        if self.engagement_frozen:
            await self.broadcast_state()
            return

        # 1. Timed threat injection
        if (
            not self.threat_injected
            and self.inject_at_time is not None
            and self.time >= self.inject_at_time
        ):
            self.inject_threat()

        # 2. Agent logic
        for e in self.entities:
            if hasattr(e, "tick"):
                e.tick(self, self.dt)

        # 3. Automatic Fire Control
        if self.threat_injected:
            self._fire_control()

        # 4. Engagement outcome
        for e in self.entities:
            if e.__class__.__name__ == "Missile" and hasattr(e, "detonated"):
                if e.detonated and not self.engagement_frozen:
                    self.engagement_frozen = True
                    self.engagement_result = e.engagement_result
                    break

        # 5. Kinematics
        if not self.engagement_frozen:
            for e in self.entities:
                e.update_kinematics(self.dt)

        self.time += self.dt

        # 6. Telemetry
        self._record_telemetry()

        # 7. Broadcast
        await self.broadcast_state()

    # ──────────────────────────────────────────────────────────────────────
    async def run(self):
        self.running = True
        while self.running:
            if not self.paused:
                await self.step()
            else:
                # Still broadcast state when paused so frontend knows we are alive
                await self.broadcast_state()
            await asyncio.sleep(self.dt)

    # ──────────────────────────────────────────────────────────────────────
    def reset(self):
        """Resets engagement-level state."""
        self.time = 0.0
        self.engagement_frozen = False
        self.engagement_result = None
        self.threat_injected = False
        self.interceptor_launched = False
        self._pending_threat = None
        self.telemetry_log.clear()

    # ──────────────────────────────────────────────────────────────────────
    #  Scenario Loading
    # ──────────────────────────────────────────────────────────────────────
    def load_scenario_config(self, scenario: dict):
        """
        Applies scenario parameters (seed, inject time, IDs).
        Entity creation is handled by main.py.
        """
        self.scenario_id = scenario.get("scenario_id", "manual")
        self.random_seed = scenario.get("random_seed", 0)
        self.inject_at_time = scenario.get("threat", {}).get("inject_at_time", None)

        # Freeze RNG for reproducibility
        np.random.seed(self.random_seed)
        random.seed(self.random_seed)

    # ──────────────────────────────────────────────────────────────────────
    #  Geometry Optimization (v0.3.0)
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def recommended_inject_time(target_rcs: float, initial_distance: float, closing_speed: float = 1250.0, desired_flight_time: float = 15.0) -> float:
        """
        Calculates the recommended injection time to guarantee a desired flight time
        for the interceptor, given the radar's physical detection range.
        
        If R_max (detection range) is large enough, we can delay injection (inject_at_time > 0)
        to skip empty simulation space and save CPU cycles in Monte Carlo.
        If R_max is too small, a flight time of 15s is physically impossible.
        """
        # Physical constants (from radar.py)
        from physics.entities.radar import RADAR_PROFILE, BOLTZMANN_K
        
        Pt = RADAR_PROFILE["pt_watts"]
        G = RADAR_PROFILE["gain_linear"]
        lmbda = RADAR_PROFILE["wavelength_m"]
        L = 2.0
        Pn = BOLTZMANN_K * 290.0 * 10e6 * 3.0
        cfar_snr = 20.0
        
        numerator = Pt * (G**2) * (lmbda**2) * target_rcs
        denominator = (4 * math.pi)**3 * L * cfar_snr * Pn
        r_max = (numerator / denominator) ** 0.25
        
        required_detect_dist = desired_flight_time * closing_speed
        
        # We want to inject the target just as it enters radar range (or just before required distance)
        target_dist = min(r_max, required_detect_dist)
        
        # If it starts further than target_dist, calculate time to reach it
        if initial_distance > target_dist:
            # Assuming target travels at ~250m/s radially
            target_vel_radial = 250.0
            return (initial_distance - target_dist) / target_vel_radial
            
        return 0.0

    # ──────────────────────────────────────────────────────────────────────
    #  Telemetry Recording
    # ──────────────────────────────────────────────────────────────────────
    def _record_telemetry(self):
        """Appends one row to the telemetry log."""
        row: dict = {
            "time": round(self.time, 3),
            "scenario_id": self.scenario_id,
            "random_seed": self.random_seed,
        }

        for e in self.entities:
            prefix = e.id
            row[f"{prefix}_pos_x"] = round(float(e.pos[0]), 3)
            row[f"{prefix}_pos_y"] = round(float(e.pos[1]), 3)
            row[f"{prefix}_pos_z"] = round(float(e.pos[2]), 3)
            row[f"{prefix}_vel_x"] = round(float(e.vel[0]), 3)
            row[f"{prefix}_vel_y"] = round(float(e.vel[1]), 3)
            row[f"{prefix}_vel_z"] = round(float(e.vel[2]), 3)

            if hasattr(e, "get_telemetry"):
                telem = e.get_telemetry()
                for k, v in telem.items():
                    if isinstance(v, (int, float, bool, str)):
                        row[f"{prefix}_{k}"] = v

        self.telemetry_log.append(row)

    def export_csv(self) -> str:
        """Exports the telemetry log as a CSV string for MATLAB."""
        if not self.telemetry_log:
            return "no data\n"

        output = io.StringIO()
        fieldnames = list(self.telemetry_log[0].keys())
        for row in self.telemetry_log:
            for k in row.keys():
                if k not in fieldnames:
                    fieldnames.append(k)

        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.telemetry_log)
        return output.getvalue()
