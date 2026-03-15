"""
target.py — Dynamic Target Entity with Parametric RCS Profiles

This module implements the Target class for the Glaukopis tactical simulator.
The Radar Cross Section (σ) is not hardcoded; it is received as a constructor
parameter from the GCS panel, allowing the operator to select different threat
profiles at runtime. An aspect-angle modifier simulates the dynamic RCS
variation caused by the target's orientation relative to the radar's LOS.

Target Profiles (σ in m²):
    Boeing 747 (Commercial)     : σ = 100.0  m²
    Su-27 (Conventional Fighter): σ = 5.0    m²
    Cruise Missile / DJI Drone  : σ = 0.1    m²
    F-35 / F-22 (Stealth)       : σ = 0.001  m²
    Large Bird                  : σ = 0.01   m²  (v_max = 40 km/h ≈ 11.11 m/s)

IFF (Identification Friend or Foe):
    Civilian / friendly targets transmit IFF = True.
    Hostile / unknown targets transmit IFF = False.
"""

from physics.universe import PhysicsEntity
import numpy as np

# ---------------------------------------------------------------------------
# Canonical target profiles — used by both backend and sent to frontend
# ---------------------------------------------------------------------------
TARGET_PROFILES = {
    # ── CIVILIAN ──────────────────────────────────────────────────────────
    "Boeing 747": {
        "sigma_min":    10.0,    # m² frontal (head-on)
        "sigma_max":   100.0,    # m² broadside
        "max_speed":   None,
        "iff":         True,
        "swerling_type": 0,      # large stable target — minimal fluctuation
        "display_label": "Boeing 747  —  σ=10–100 m²",
        "description": "Large Commercial Airliner",
        "default_velocity": np.array([-220.0, 20.0, 0.0]),   # ~Mach 0.65
    },

    # ── CONVENTIONAL MILITARY ─────────────────────────────────────────────
    "F/A-18 Hornet": {
        "sigma_min":    1.0,     # m² frontal
        "sigma_max":   10.0,     # m² broadside
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "F/A-18 Hornet  —  σ=1–10 m²",
        "description": "Non-stealth multirole. Ref: Stimson 'Introduction to Airborne Radar'.",
        "default_velocity": np.array([-350.0, 50.0, -20.0]),
    },
    "F-16 Fighting Falcon": {
        "sigma_min":    0.5,     # m²
        "sigma_max":    5.0,     # m²
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "F-16 Fighting Falcon  —  σ=0.5–5 m²",
        "description": "Light multirole. Smaller airframe than F/A-18.",
        "default_velocity": np.array([-350.0, 50.0, -20.0]),
    },
    "Su-27 Flanker": {
        "sigma_min":    3.0,     # m²
        "sigma_max":   15.0,     # m²
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "Su-27 Flanker  —  σ=3–15 m²",
        "description": "Heavy air superiority. Large airframe → high broadside RCS.",
        "default_velocity": np.array([-400.0, 60.0, -30.0]),
    },
    "MiG-31 Foxhound": {
        "sigma_min":    5.0,     # m² frontal — large nose section
        "sigma_max":   20.0,     # m² broadside — twin-engine heavy
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "MiG-31 Foxhound  —  σ=5–20 m²",
        "description": "Heavy interceptor. Largest RCS of conventional fighters here.",
        "default_velocity": np.array([-600.0, 60.0, -30.0]),
    },

    # ── STEALTH ───────────────────────────────────────────────────────────
    "F-35 / F-22 Stealth": {
        "sigma_min":    0.001,   # m² frontal — golf ball equivalent
        "sigma_max":    0.05,    # m² broadside estimate (classified)
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "F-35 / F-22 Stealth  —  σ=0.001–0.05 m²",
        "description": "5th gen stealth. Frontal RCS ~0.001m² (golf ball).",
        "default_velocity": np.array([-300.0, 50.0, -10.0]),
    },
    "PAK FA / Su-57": {
        "sigma_min":    0.01,    # m² — estimated, less mature than F-22
        "sigma_max":    0.5,     # m² broadside — airframe not fully optimised
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "PAK FA / Su-57  —  σ=0.01–0.5 m²",
        "description": "Russian 5th gen. Estimated frontal RCS 0.01–0.1m².",
        "default_velocity": np.array([-300.0, 50.0, -10.0]),
    },

    # ── MISSILES & DRONES ─────────────────────────────────────────────────
    "Cruise Missile / DJI Drone": {
        "sigma_min":    0.05,    # m²
        "sigma_max":    0.1,     # m²
        "max_speed":   None,
        "iff":         False,
        "swerling_type": 1,
        "display_label": "Cruise Missile / DJI Drone  —  σ=0.05–0.1 m²",
        "description": "Small cross-section by size (drone) or design (cruise missile).",
        "default_velocity": np.array([-250.0, 30.0, -20.0]),  # Subsonic
    },
    "Bird (Large)": {
        "sigma_min":    0.005,   # m²
        "sigma_max":    0.01,    # m²
        "max_speed":    11.11,   # 40 km/h
        "iff":         True,
        "swerling_type": 1,
        "display_label": "Bird (Large)  —  σ=0.005–0.01 m²",
        "description": "Clutter reference. Speed clamped to 40 km/h.",
        "default_velocity": np.array([-10.0, 3.0, 0.0]),
    },
}


class Target(PhysicsEntity):
    """
    Represents an airborne target with a dynamic Radar Cross Section.

    The RCS (σ) is set at instantiation from the selected profile and
    modulated at runtime by the aspect angle between the target's heading
    vector and the radar's Line-of-Sight (LOS) vector. This simulates
    the well-known phenomenon where stealth aircraft present minimal
    frontal RCS but much larger cross-sections when viewed broadside.

    Attributes:
        base_rcs (float): Nominal σ in m² from the profile.
        iff      (bool) : IFF transponder — True = friendly, False = hostile.
        max_speed (float | None): Speed cap in m/s (only used for birds).
        profile_name (str): Human-readable label of the selected profile.
    """

    def __init__(
        self,
        id: str,
        x: float,
        y: float,
        z: float,
        sigma_min: float = 0.05,
        sigma_max: float = 0.1,
        swerling_type: int = 1,
        iff: bool = False,
        max_speed: float | None = None,
        profile_name: str = "Unknown",
        display_label: str = "Unknown",
    ):
        super().__init__(id, x, y, z)
        self.rcs_min: float = sigma_min
        self.rcs_max: float = sigma_max
        self.swerling_type: int = swerling_type
        self.iff: bool = iff
        self.max_speed: float | None = max_speed
        self.profile_name: str = profile_name
        self.display_label: str = display_label
        
        # Telemetry fields for CSV
        self.current_rcs: float = 0.0
        self.mean_rcs: float = 0.0

        # Default velocity — overridden by main.py from the profile dict
        self.vel = np.array([0.0, 0.0, 0.0], dtype=float)

    # ------------------------------------------------------------------
    # Kinematics override — enforce speed limit for biological targets
    # ------------------------------------------------------------------
    def update_kinematics(self, dt: float):
        """
        Standard Euler integration with an optional speed clamp.

        For the "Large Bird" profile the velocity magnitude is capped at
        40 km/h (≈ 11.11 m/s). All other profiles are unconstrained.
        """
        super().update_kinematics(dt)

        if self.max_speed is not None:
            speed = np.linalg.norm(self.vel)
            if speed > self.max_speed:
                self.vel = (self.vel / speed) * self.max_speed

    # ------------------------------------------------------------------
    # Dynamic RCS with aspect-angle modulation
    # ------------------------------------------------------------------
    def get_rcs(self, radar_pos: np.ndarray) -> float:
        """
        Dynamic RCS with Swerling Type I stochastic fluctuation.

        Base model: butterfly aspect-angle pattern
            σ(θ) = σ_min + (σ_max - σ_min) · sin²(θ)

        Swerling Type I: models targets with many independent scatterers.
        Envelope follows Rayleigh → power follows exponential distribution.
        Mean equals the deterministic butterfly value.
        Correlation: slow (scan-to-scan) — fluctuation changes each radar ping.

        Args:
            radar_pos: radar position [x, y, z] for LOS calculation

        Returns:
            instantaneous RCS in m²
        """
        def normalize(v):
            norm = np.linalg.norm(v)
            if norm == 0: 
               return v
            return v / norm

        los_vec = normalize(radar_pos - self.pos)
        heading = normalize(self.vel)
        
        # If stationary, assume broadside max RCS
        if np.linalg.norm(self.vel) == 0:
            cos_theta = 0.0
        else:
            cos_theta = np.clip(np.dot(heading, los_vec), -1.0, 1.0)
            
        sin_theta_sq = 1.0 - cos_theta**2

        # Deterministic mean (butterfly pattern)
        sigma_mean = self.rcs_min + (self.rcs_max - self.rcs_min) * sin_theta_sq
        sigma_mean = max(sigma_mean, 1e-6)  # floor to avoid log(0)
        self.mean_rcs = sigma_mean

        if self.swerling_type == 0:
            self.current_rcs = sigma_mean
            return self.current_rcs

        # Swerling Type I: exponential distribution with mean = sigma_mean
        # np.random.exponential(scale) samples from Exp(1/scale)
        # E[X] = scale, so scale = sigma_mean gives correct mean
        sigma_fluctuated = np.random.exponential(scale=sigma_mean)

        # Clamp to physically reasonable bounds [σ_min/10, σ_max*10] to avoid complete 0
        sigma_fluctuated = float(np.clip(sigma_fluctuated, self.rcs_min / 10.0, self.rcs_max * 10.0))
        self.current_rcs = sigma_fluctuated
        return self.current_rcs

    # ------------------------------------------------------------------
    # Telemetry — exposed via WebSocket
    # ------------------------------------------------------------------
    def get_telemetry(self):
        """Returns target-specific telemetry for the GCS panel."""
        speed = np.linalg.norm(self.vel)
        return {
            "profile": self.profile_name,
            "display_label": self.display_label,
            "sigma_min": self.rcs_min,
            "sigma_max": self.rcs_max,
            "swerling_type": self.swerling_type,
            "iff": self.iff,
            "speed": round(speed, 1),
            "rcs_instantaneous": round(self.current_rcs, 5),
            "rcs_mean": round(self.mean_rcs, 5)
        }
