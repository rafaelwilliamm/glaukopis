"""
missile.py — Interceptor with 3-D Proportional Navigation Guidance

This module implements the interceptor missile for the Glaukopis simulator.
The missile is decoupled from the radar sensor: it starts in an "idle"
state at the launch base and only activates upon an explicit engagement
authorization from the GCS operator.

Guidance Law — True Proportional Navigation (TPN):

    The lateral acceleration command normal to the Line-of-Sight is:

        a_c = N · V_c · (Ω × LOS_hat)

    Where:
        N        = Navigation constant (dimensionless, typically 3–5).
        V_c      = Closing velocity (scalar, m/s).
        Ω        = LOS angular rate vector = (R × V_rel) / |R|²
        LOS_hat  = Unit vector along the Line-of-Sight.

    The resulting acceleration is clamped to the structural G-limit
    of the airframe (30 G for a typical air-to-air interceptor).

Proximity Fuze:
    Detonation is triggered when the missile-to-target distance
    falls below 15.0 m.  If the missile passes CPA without entering
    the fuze radius, the engagement is classified as a MISS.

References:
    [1] Zarchan, P. "Tactical and Strategic Missile Guidance", AIAA, 6th ed.
    [2] Guidance Filter Fundamentals, JHU/APL Technical Digest, Vol. 29 No. 1.
"""

import numpy as np
from physics.universe import PhysicsEntity
from physics.entities.radar import Radar


class Missile(PhysicsEntity):
    """
    Air-to-air interceptor using True Proportional Navigation (TPN).

    The missile is launched from the ground station and guided by the
    radar's estimated track — never by the Truth Model position.
    This enforces the sensor-shooter decoupling and Truth Leak prevention.

    Attributes:
        max_speed (float): Maximum sustain speed [m/s].
        N         (float): Navigation constant (dimensionless).
        max_g     (float): Structural G-limit [m/s²].
        launched  (bool) : Whether the missile has been launched.
        fuze_radius (float): Proximity fuze detonation radius [m].
    """

    def __init__(self, id: str, x: float, y: float, z: float):
        super().__init__(id, x, y, z)

        # ── Performance parameters ───────────────────────────────────────
        self.max_speed: float = 1000.0    # Mach ≈ 3.0
        self.N: float = 3.0               # Navigation constant
        self.max_g: float = 30.0 * 9.81   # 30 G structural limit [m/s²]
        self.current_g: float = 0.0

        # ── State ────────────────────────────────────────────────────────
        self.launched: bool = False        # Idle until engagement authorized
        self.detonated: bool = False
        self.engagement_result: str = "IDLE"  # IDLE | FLYING | HIT | MISS

        # ── Radar data link ──────────────────────────────────────────────
        self.radar_link: Radar = None

        # ── Proximity fuze ───────────────────────────────────────────────
        self.fuze_radius: float = 15.0    # meters (per spec)
        self.miss_distance: float = 0.0
        self.prev_miss_distance: float = float("inf")
        self.final_miss_distance: float = 0.0

        # ── Launch origin (for reset) ────────────────────────────────────
        self.origin = np.array([x, y, z], dtype=float)

    # ──────────────────────────────────────────────────────────────────────
    #  Link & Launch
    # ──────────────────────────────────────────────────────────────────────
    def link_to_radar(self, radar: Radar):
        """Establishes the data-link to the radar's track feed."""
        self.radar_link = radar

    def launch(self, track_pos: np.ndarray):
        """
        Activates the missile and imparts an initial boost vector toward
        the radar's estimated target position.

        Called by the GCS operator via the "Authorize Engagement" button.

        Args:
            track_pos: Radar-estimated target position at launch time [m].
        """
        if self.launched or self.detonated:
            return

        direction = track_pos - self.pos
        dist = np.linalg.norm(direction)
        if dist < 1.0:
            return

        launch_dir = direction / dist
        self.vel = launch_dir * self.max_speed
        self.launched = True
        self.engagement_result = "FLYING"

    # ──────────────────────────────────────────────────────────────────────
    #  Proportional Navigation
    # ──────────────────────────────────────────────────────────────────────
    def compute_pn_acceleration(
        self, track_pos: np.ndarray, track_vel: np.ndarray
    ) -> np.ndarray:
        """
        3-D True Proportional Navigation (TPN) acceleration command.

        The guidance law is:

            Ω  = (R × V_rel) / |R|²      (LOS angular rate vector)
            a_c = N · V_c · (Ω × R̂)     (acceleration normal to LOS)

        Where R̂ is the LOS unit vector and V_c = − V_rel · R̂  is the
        scalar closing velocity.

        The result is clamped to ±30 G to respect airframe structural
        limits (G-saturation).

        Args:
            track_pos: Radar-estimated target position [m].
            track_vel: Radar-estimated target velocity [m/s].

        Returns:
            Acceleration command vector [m/s²].
        """
        R_m = track_pos - self.pos
        R_range = np.linalg.norm(R_m)

        if R_range < 1.0:
            return np.array([0.0, 0.0, 0.0])

        los_unit = R_m / R_range

        # Relative velocity (target velocity relative to missile)
        V_rel = track_vel - self.vel

        # Closing velocity (positive when closing)
        V_c = -np.dot(V_rel, los_unit)

        # LOS angular rate:  Ω = (R × V_rel) / |R|²
        los_rate_vec = np.cross(R_m, V_rel) / (R_range ** 2)

        # Acceleration command:  a_c = N · V_c · (Ω × R̂)
        a_c = self.N * V_c * np.cross(los_rate_vec, los_unit)

        # ── G-Saturation ─────────────────────────────────────────────────
        accel_mag = np.linalg.norm(a_c)
        self.current_g = accel_mag / 9.81

        if accel_mag > self.max_g:
            a_c = (a_c / accel_mag) * self.max_g
            self.current_g = self.max_g / 9.81

        return a_c

    # ──────────────────────────────────────────────────────────────────────
    #  Tick — simulation frame update
    # ──────────────────────────────────────────────────────────────────────
    def tick(self, universe, dt: float):
        """
        Per-frame update.  Does nothing until the missile is launched.

        After launch:
            1. Computes true miss distance (for fuze logic only — NOT
               fed to the guidance loop; Truth Leak prevention).
            2. Checks proximity fuze (≤ 15 m → HIT).
            3. Checks CPA fly-through (distance increasing → MISS).
            4. Runs PN guidance from the radar's estimated track.
        """
        # ── Idle — do nothing ────────────────────────────────────────────
        if not self.launched or self.detonated:
            self.vel = np.array([0.0, 0.0, 0.0])
            self.accel = np.array([0.0, 0.0, 0.0])
            return

        # ── Compute true miss distance (for fuze, NOT for guidance) ──────
        for e in universe.entities:
            if e.__class__.__name__ == "Target":
                self.miss_distance = float(np.linalg.norm(e.pos - self.pos))
                break

        # ── Proximity Fuze: ≤ 15 m → HIT ────────────────────────────────
        if self.miss_distance <= self.fuze_radius:
            self._detonate("HIT")
            return

        # ── CPA Detection: distance increasing → MISS ───────────────────
        if (
            self.miss_distance > self.prev_miss_distance
            and self.prev_miss_distance < 5000.0  # record MISS even if it missed by a large margin
        ):
            self._detonate("MISS")
            return

        self.prev_miss_distance = self.miss_distance

        # ── Guidance from radar track ────────────────────────────────────
        if self.radar_link and self.radar_link.track["valid"]:
            track_pos = self.radar_link.track["estimated_pos"]
            track_vel = self.radar_link.track["estimated_vel"]

            a_cmd = self.compute_pn_acceleration(track_pos, track_vel)

            a_cmd = self.compute_pn_acceleration(track_pos, track_vel)
            self.accel = a_cmd
        else:
            # Track lost — fly ballistic
            self.accel = np.array([0.0, 0.0, 0.0])
            self.current_g = 0.0

    # ──────────────────────────────────────────────────────────────────────
    #  Kinematics override
    # ──────────────────────────────────────────────────────────────────────
    def update_kinematics(self, dt: float):
        """
        Uses the RK4 integrator from the base class, then clamps speed
        to maintain the PN constant-speed assumption.
        """
        super().update_kinematics(dt)
        current_speed = np.linalg.norm(self.vel)
        if current_speed > 0:
            self.vel = (self.vel / current_speed) * self.max_speed

    # ──────────────────────────────────────────────────────────────────────
    def _detonate(self, result: str):
        """Freezes the missile and records the engagement outcome."""
        self.detonated = True
        self.engagement_result = result
        self.final_miss_distance = (
            self.prev_miss_distance if result == "MISS" else self.miss_distance
        )
        self.vel = np.array([0.0, 0.0, 0.0])
        self.accel = np.array([0.0, 0.0, 0.0])

    # ──────────────────────────────────────────────────────────────────────
    #  Reset
    # ──────────────────────────────────────────────────────────────────────
    def reset(self):
        """Returns the missile to its idle launch-pad state."""
        self.pos = self.origin.copy()
        self.vel = np.array([0.0, 0.0, 0.0])
        self.accel = np.array([0.0, 0.0, 0.0])
        self.launched = False
        self.detonated = False
        self.engagement_result = "IDLE"
        self.current_g = 0.0
        self.miss_distance = 0.0
        self.prev_miss_distance = float("inf")
        self.final_miss_distance = 0.0

    # ──────────────────────────────────────────────────────────────────────
    #  Telemetry
    # ──────────────────────────────────────────────────────────────────────
    def get_telemetry(self):
        return {
            "g_force": round(self.current_g, 2),
            "miss_distance": round(
                self.final_miss_distance if self.detonated else self.miss_distance, 2
            ),
            "launched": self.launched,
            "engagement_result": self.engagement_result,
        }
