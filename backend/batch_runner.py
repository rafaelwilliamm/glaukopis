"""
batch_runner.py — Monte Carlo Batch Simulation Engine

Runs N simulations of a scenario with different random seeds,
collecting per-run summary metrics and optional per-frame timeseries.

This engine runs **synchronously without any sleep()** — pure
computation.  A 120-second scenario at 10 Hz (1200 frames) completes
in ~50-200 ms depending on hardware.

Output:
    summary_rows : list[dict]  — one row per seed (for summary.csv)
    timeseries   : list[dict]  — all frames for all seeds (optional)

Usage from the API:
    runner = BatchRunner(scenario_config)
    runner.run(seed_start=1, seed_end=50)
    summary_csv = runner.export_summary_csv()
    ts_csv      = runner.export_timeseries_csv()
"""

import csv
import io
import json
import math
import random
from pathlib import Path
from typing import Callable

import numpy as np

from physics.universe import PhysicsEntity
from physics.entities.target import Target, TARGET_PROFILES
from physics.entities.radar import Radar
from physics.entities.missile import Missile


class BatchRunner:
    """
    Monte Carlo batch runner for deterministic simulation sweeps.

    Each seed produces an independent realization of the engagement,
    with identical geometry but different AWGN / Swerling sequences.
    """

    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.dt = scenario.get("simulation", {}).get("dt", 0.1)
        self.max_duration = scenario.get("simulation", {}).get("max_duration", 120.0)
        self.scenario_id = scenario.get("scenario_id", "manual")
        self.include_timeseries = True

        # Results
        self.summary_rows: list[dict] = []
        self.timeseries_rows: list[dict] = []

        # Progress tracking
        self.total_seeds: int = 0
        self.completed_seeds: int = 0
        self.running: bool = False
        self.aborted: bool = False

        # Callback for progress updates (set by API)
        self.on_progress: Callable | None = None

    # ──────────────────────────────────────────────────────────────────────
    def run(self, seed_start: int = 1, seed_end: int = 50,
            include_timeseries: bool = True):
        """
        Runs the full Monte Carlo sweep.

        Args:
            seed_start: First seed (inclusive).
            seed_end:   Last seed (inclusive).
            include_timeseries: Whether to record frame-by-frame data.
        """
        self.include_timeseries = include_timeseries
        self.summary_rows.clear()
        self.timeseries_rows.clear()
        self.total_seeds = seed_end - seed_start + 1
        self.completed_seeds = 0
        self.running = True
        self.aborted = False

        for seed in range(seed_start, seed_end + 1):
            if self.aborted:
                break

            result = self._run_single(seed)
            self.summary_rows.append(result["summary"])

            if include_timeseries:
                self.timeseries_rows.extend(result["timeseries"])

            self.completed_seeds += 1

        self.running = False

    # ──────────────────────────────────────────────────────────────────────
    def stop(self):
        """Aborts the batch after the current seed completes."""
        self.aborted = True

    # ──────────────────────────────────────────────────────────────────────
    def _run_single(self, seed: int) -> dict:
        """
        Runs one complete simulation for a given seed.

        Returns dict with 'summary' (one row) and 'timeseries' (list of rows).
        """
        # ── Freeze RNG ───────────────────────────────────────────────────
        np.random.seed(seed)
        random.seed(seed)

        # ── Build entities ───────────────────────────────────────────────
        threat_cfg = self.scenario.get("threat", {})
        profile_name = threat_cfg.get("profile", "Cruise Missile / DJI Drone")
        profile = TARGET_PROFILES.get(profile_name, TARGET_PROFILES["Cruise Missile / DJI Drone"])
        inject_at_time = threat_cfg.get("inject_at_time", 5.0)

        pos = threat_cfg.get("initial_position", [15000.0, 2000.0, 8000.0])
        vel = threat_cfg.get("velocity", profile["default_velocity"].tolist())

        # Radar at origin
        radar = Radar("AESA_01", 0.0, 0.0, 0.0)

        # Missile at base
        missile = Missile("INTERCEPTOR_01", 0.0, 0.0, 0.0)
        missile.link_to_radar(radar)

        # Target (created but not active yet)
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

        # ── Simulation state ─────────────────────────────────────────────
        entities: list[PhysicsEntity] = [radar, missile]
        threat_injected = False
        engagement_frozen = False
        engagement_result = "TIMEOUT"

        # Metrics to collect
        time_to_detect = None       # First SNR > CFAR
        time_to_confirm = None      # Track CONFIRMED
        time_to_launch = None       # Missile launched
        time_to_intercept = None    # Detonation / CPA
        snr_accumulator = []
        peak_g = 0.0

        timeseries = []
        t = 0.0

        # ── Mini Universe for tick() compatibility ───────────────────────
        class MiniUniverse:
            pass
        mini = MiniUniverse()
        mini.entities = entities

        # ── Main loop ────────────────────────────────────────────────────
        max_frames = int(self.max_duration / self.dt)

        for frame in range(max_frames):
            if engagement_frozen:
                break

            # Inject threat at scheduled time
            if not threat_injected and t >= inject_at_time:
                entities.append(target)
                mini.entities = entities
                threat_injected = True

            # Agent ticks
            radar.tick(mini, self.dt)

            if missile.launched and not missile.detonated:
                missile.tick(mini, self.dt)

            # ── Collect metrics ──────────────────────────────────────────
            if threat_injected:
                snr_db = radar.track["last_snr_db"]

                # First detection
                if time_to_detect is None and radar.track["last_snr"] > radar.cfar_threshold_snr:
                    time_to_detect = round(t, 3)

                # Track confirmed
                if time_to_confirm is None and radar.track["status"] == "CONFIRMED":
                    time_to_confirm = round(t, 3)

                # SNR samples (only while tracking)
                if radar.track["last_snr"] > radar.cfar_threshold_snr:
                    snr_accumulator.append(snr_db)

                # Auto Fire Control
                if (
                    radar.track["valid"]
                    and radar.track["status"] == "CONFIRMED"
                    and not radar.track["iff"]  # HOSTILE
                    and not missile.launched
                ):
                    missile.launch(radar.track["estimated_pos"].copy())
                    time_to_launch = round(t, 3)

            # G-force tracking
            if missile.launched:
                peak_g = max(peak_g, missile.current_g)

            # Engagement outcome
            if missile.detonated:
                engagement_frozen = True
                engagement_result = missile.engagement_result
                time_to_intercept = round(t, 3)

            # Kinematics
            if not engagement_frozen:
                for e in entities:
                    e.update_kinematics(self.dt)

            # Timeseries recording
            if self.include_timeseries and threat_injected:
                row = {
                    "time": round(t, 3),
                    "random_seed": seed,
                    "scenario_id": self.scenario_id,
                    "TGT_01_pos_x": round(float(target.pos[0]), 2),
                    "TGT_01_pos_y": round(float(target.pos[1]), 2),
                    "TGT_01_pos_z": round(float(target.pos[2]), 2),
                    "INTERCEPTOR_01_pos_x": round(float(missile.pos[0]), 2),
                    "INTERCEPTOR_01_pos_y": round(float(missile.pos[1]), 2),
                    "INTERCEPTOR_01_pos_z": round(float(missile.pos[2]), 2),
                    "snr_db": round(snr_db, 2) if threat_injected else 0,
                    "miss_distance_m": round(missile.miss_distance, 2),
                    "g_force": round(missile.current_g, 2),
                    "track_status": radar.track["status"],
                    "missile_launched": missile.launched,
                    "TGT_01_rcs_instantaneous": round(target.current_rcs, 5),
                    "TGT_01_rcs_mean": round(target.mean_rcs, 5),
                    "TGT_01_sigma_min": target.rcs_min,
                    "TGT_01_sigma_max": target.rcs_max,
                    "TGT_01_display_label": target.display_label,
                }
                timeseries.append(row)

            t += self.dt

        # ── Summary row ──────────────────────────────────────────────────
        miss_dist = missile.final_miss_distance if missile.detonated else missile.miss_distance
        mean_snr = round(np.mean(snr_accumulator), 2) if snr_accumulator else 0.0
        peak_snr = round(max(snr_accumulator), 2) if snr_accumulator else 0.0

        summary = {
            "scenario_id": self.scenario_id,
            "random_seed": seed,
            "profile": profile_name,
            "rcs_m2": profile.get("sigma_max", 0.0),
            "result": engagement_result,
            "miss_distance_m": round(miss_dist, 2),
            "time_to_detect_s": time_to_detect,
            "time_to_confirm_s": time_to_confirm,
            "time_to_launch_s": time_to_launch,
            "time_to_intercept_s": time_to_intercept,
            "total_duration_s": round(t, 2),
            "mean_snr_db": mean_snr,
            "peak_snr_db": peak_snr,
            "peak_g_force": round(peak_g, 2),
        }

        return {"summary": summary, "timeseries": timeseries}

    # ──────────────────────────────────────────────────────────────────────
    #  CSV Export
    # ──────────────────────────────────────────────────────────────────────
    def export_summary_csv(self) -> str:
        """Exports the summary table as CSV (one row per seed)."""
        if not self.summary_rows:
            return "no data\n"

        output = io.StringIO()
        fieldnames = list(self.summary_rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(self.summary_rows)
        return output.getvalue()

    def export_timeseries_csv(self) -> str:
        """Exports frame-by-frame data as CSV (all seeds concatenated)."""
        if not self.timeseries_rows:
            return "no data\n"

        output = io.StringIO()
        fieldnames = list(self.timeseries_rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(self.timeseries_rows)
        return output.getvalue()

    # ──────────────────────────────────────────────────────────────────────
    def get_progress(self) -> dict:
        """Returns current progress for the GCS display."""
        hits = sum(1 for r in self.summary_rows if r["result"] == "HIT")
        total = len(self.summary_rows)
        pk = round(hits / total * 100, 1) if total > 0 else 0.0
        mean_miss = (
            round(np.mean([r["miss_distance_m"] for r in self.summary_rows]), 2)
            if total > 0 else 0.0
        )
        std_miss = (
            round(float(np.std([r["miss_distance_m"] for r in self.summary_rows])), 2)
            if total > 1 else 0.0
        )

        return {
            "running": self.running,
            "aborted": self.aborted,
            "completed": self.completed_seeds,
            "total": self.total_seeds,
            "percent": round(self.completed_seeds / max(self.total_seeds, 1) * 100, 1),
            "pk_percent": pk,
            "hits": hits,
            "misses": total - hits,
            "mean_miss_distance_m": mean_miss,
            "std_miss_distance_m": std_miss,
            "rows": self.summary_rows,
        }
