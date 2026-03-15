"""
radar.py — AESA Radar Model with Boltzmann Noise Floor and Track Initiation

This module implements a physically-grounded monostatic radar sensor for the
Glaukopis tactical simulator.  It replaces the MVP's arbitrary noise floor
with the Johnson-Nyquist thermal noise equation and enforces a rigorous
M-of-N Track Initiation protocol before a track is declared "Confirmed"
and eligible for weapons engagement.

Key Physics:
    Thermal Noise Floor (Pn):
        P_n = k · T_s · B · F
        where:
            k   = 1.380649 × 10⁻²³ J/K  (Boltzmann constant)
            T_s = 290 K                   (system temperature)
            B   = 10 MHz                  (receiver bandwidth)
            F   = 3 (linear, ≈ 4.77 dB)  (noise figure)

    Radar Equation — Received Power (Pr):
        P_r = (P_t · G² · λ² · σ) / ((4π)³ · R⁴ · L)

    Signal-to-Noise Ratio:
        SNR = P_r / P_n

    AWGN Measurement Error:
        σ_error = K / √(SNR)  — inversely proportional to SNR

Track Initiation (M-of-N = 3-of-5):
    A detection ("plot") only becomes a weaponizable "Confirmed Track"
    after being correlated in at least 3 of the last 5 consecutive scan
    frames.  Until then the track is "Tentative" and invisible to the
    fire-control loop.

Track Classification:
    Each track is automatically classified by:
        • Echo power (RCS magnitude class)
        • Doppler-derived radial velocity
        • IFF transponder response (True / False)
"""

import numpy as np
import math
from physics.universe import PhysicsEntity
from physics.entities.target import Target

# ─── Physical Constants ──────────────────────────────────────────────────────
BOLTZMANN_K = 1.380649e-23   # J/K

# ─── Radar Profiles ──────────────────────────────────────────────────────────
RADAR_PROFILE = {
    "name":        "Pantsir-S1 (acquisition radar)",
    "band":        "X",
    "frequency_hz": 10e9,
    "wavelength_m":  0.03,
    "pt_watts":    150_000,
    "gain_linear":  10_000,
    "gain_db":          40,
    "max_range_km": {
        "su27":          54,
        "f16":           35,
        "cruise_missile": 23,
        "f35":            7,
    },
    "reference": "Pantsir-S1 SA-22 Greyhound — Band X SHORAD/MRAD baseline"
}


class Radar(PhysicsEntity):
    """
    AESA X-Band (10 GHz) radar sensor.

    The radar observes the Truth Model targets through the physically-degraded
    chain: Radar Equation → SNR computation → CFAR thresholding → AWGN
    corruption → Alpha-Beta track filter.  At no point does any downstream
    consumer (missile, GCS display) receive the Truth position; only the
    estimated track produced by this sensor is ever exported —
    the "Truth Leak Prevention" architecture.

    Attributes:
        Pt      (float): Peak transmit power [W].
        G       (float): Antenna gain (linear).
        freq    (float): Carrier frequency [Hz].
        lmbda   (float): Wavelength [m].
        L       (float): System losses (linear factor).
        T_sys   (float): System noise temperature [K].
        B       (float): Receiver bandwidth [Hz].
        F       (float): Noise figure (linear).
        noise_power (float): P_n = k·T·B·F  [W].
    """

    def __init__(self, id: str, x: float, y: float, z: float, universe=None):
        super().__init__(id, x, y, z)
        self.universe = universe

        # ── Transmitter ──────────────────────────────────────────────────
        self.Pt: float = RADAR_PROFILE["pt_watts"]
        self.G: float = float(RADAR_PROFILE["gain_linear"])
        self.freq: float = RADAR_PROFILE["frequency_hz"]
        self.c: float = 3e8
        self.lmbda: float = RADAR_PROFILE["wavelength_m"]
        self.L: float = 2.0           # 3 dB system losses (linear factor)

        # ── Receiver — Boltzmann Noise Floor ─────────────────────────────
        #   P_n = k · T_s · B · F
        #   Per spec: T = 290 K, B = 10 MHz, F = 3 (linear ≈ 4.77 dB)
        self.T_sys: float = 290.0     # System temperature [K]
        self.B: float = 10e6          # Bandwidth 10 MHz
        self.F: float = 3.0           # Noise figure (linear)
        self.noise_power: float = BOLTZMANN_K * self.T_sys * self.B * self.F

        # ── CFAR Detection Threshold ────────────────────────────────────
        #   SNR must exceed this value (linear) for a detection
        #   13 dB ≈ linear factor of ~20
        self.cfar_threshold_snr: float = 20.0   # ~13 dB

        # ── Track Initiation — M-of-N (3 of 5) ──────────────────────────
        self.M_REQUIRED: int = 3
        self.N_WINDOW: int = 5
        self._detection_history: list[bool] = []  # rolling window of N

        # ── Track State ──────────────────────────────────────────────────
        self.track = {
            "valid": False,               # True only after M-of-N
            "tentative": False,            # True while accumulating
            "status": "SEARCHING",         # SEARCHING | TENTATIVE | CONFIRMED | TRACK_LOST
            "estimated_pos": np.array([0.0, 0.0, 0.0]),
            "estimated_vel": np.array([0.0, 0.0, 0.0]),
            "last_snr": 0.0,
            "last_snr_db": -999.0,
            # Classification
            "rcs_class": "UNKNOWN",
            "doppler_speed": 0.0,
            "iff": False,
        }

        # ── Coasting counter (frames without detection) ──────────────────
        self._coast_frames: int = 0
        self._max_coast: int = 10   # drop track after N missed frames

    # ──────────────────────────────────────────────────────────────────────
    #  Radar Equation
    # ──────────────────────────────────────────────────────────────────────
    def _radar_equation(self, R: float, rcs: float) -> float:
        """
        Monostatic Radar Equation — Received Power.

        Computes the power captured by the antenna after the electromagnetic
        wave travels to the target (range R) and back:

            P_r = (P_t · G² · λ² · σ) / ((4π)³ · R⁴ · L)

        Args:
            R   : Slant range to target [m].
            rcs : Effective Radar Cross Section σ [m²].

        Returns:
            P_r in Watts.
        """
        numerator = self.Pt * (self.G ** 2) * (self.lmbda ** 2) * rcs
        denominator = ((4.0 * np.pi) ** 3) * (R ** 4) * self.L
        if denominator == 0:
            return 0.0
        return numerator / denominator

    # ──────────────────────────────────────────────────────────────────────
    #  Ping — compute SNR against a single target
    # ──────────────────────────────────────────────────────────────────────
    def ping(self, target: Target) -> tuple[float, np.ndarray]:
        """
        Interrogates a target and returns the Signal-to-Noise Ratio and
        the true LOS vector (which will be corrupted by AWGN before use).

        SNR = P_r / P_n        (linear)

        Args:
            target: Target entity from the Truth Model.

        Returns:
            (snr_linear, true_vector_m)
        """
        true_vector = target.pos - self.pos
        R = np.linalg.norm(true_vector)

        if R < 1.0:
            R = 1.0

        rcs = target.get_rcs(self.pos)
        Pr = self._radar_equation(R, rcs)
        snr = Pr / self.noise_power

        return snr, true_vector

    # ──────────────────────────────────────────────────────────────────────
    #  AWGN Corruption — inversely proportional to SNR
    # ──────────────────────────────────────────────────────────────────────
    def _apply_awgn(self, true_vector: np.ndarray, snr: float) -> np.ndarray:
        """
        Simulates the measurement noise (AWGN) on the position vector.

        The standard deviation of the error is modelled as:

            σ_error = K / √(SNR)

        This is a simplified representation of the Cramér-Rao Lower Bound
        for range estimation accuracy.  When SNR is very high the
        measurement approaches the truth; when SNR is marginal the
        position estimate is heavily corrupted.

        Args:
            true_vector : true LOS vector from radar to target [m].
            snr         : linear SNR (dimensionless).

        Returns:
            Corrupted LOS vector [m].
        """
        if snr <= 0:
            snr = 0.01  # avoid division by zero

        # K = 500 m → at SNR=25 (~14 dB): error_std = 100 m
        #              at SNR=1000 (~30 dB): error_std = 15.8 m
        error_std_dev = 500.0 / math.sqrt(snr)
        noise = np.random.normal(0, error_std_dev, 3)
        return true_vector + noise

    # ──────────────────────────────────────────────────────────────────────
    #  Track Classification
    # ──────────────────────────────────────────────────────────────────────
    def _classify_track(self, target: Target, snr: float):
        """
        Automatic classification based on physics observables.

        Categories:
            RCS class — estimated from echo power and range:
                LARGE    (σ > 10 m²)   — likely commercial
                MEDIUM   (1 < σ ≤ 10)  — conventional fighter
                SMALL    (0.01 < σ ≤ 1)— drone / cruise missile
                STEALTH  (σ ≤ 0.01)    — 5th gen fighter / bird

            Doppler speed — radial component of velocity (closing rate).

            IFF — transponder interrogation response.
        """
        # Estimate RCS from measured Pr and known range
        R = np.linalg.norm(target.pos - self.pos)
        if R < 1:
            R = 1.0
        # Back-solve: σ_est = Pr · (4π)³ · R⁴ · L / (Pt · G² · λ²)
        Pr = snr * self.noise_power
        sigma_est = (
            Pr * ((4.0 * np.pi) ** 3) * (R ** 4) * self.L
        ) / (self.Pt * (self.G ** 2) * (self.lmbda ** 2))

        if sigma_est > 10.0:
            self.track["rcs_class"] = "LARGE"
        elif sigma_est > 1.0:
            self.track["rcs_class"] = "MEDIUM"
        elif sigma_est > 0.01:
            self.track["rcs_class"] = "SMALL"
        else:
            self.track["rcs_class"] = "STEALTH"

        # Doppler (radial velocity component)
        los_unit = (target.pos - self.pos)
        los_dist = np.linalg.norm(los_unit)
        if los_dist > 0:
            los_unit = los_unit / los_dist
        # Positive = closing, negative = opening
        doppler = -np.dot(target.vel, los_unit)
        self.track["doppler_speed"] = round(float(doppler), 1)

        # IFF transponder
        self.track["iff"] = target.iff

    # ──────────────────────────────────────────────────────────────────────
    #  M-of-N Track Initiation Logic
    # ──────────────────────────────────────────────────────────────────────
    def _update_initiation(self, detected: bool):
        """
        Implements the M-of-N (3-of-5) track initiation protocol.

        A detection only becomes a "Confirmed Track" after M successful
        detections within the last N scan frames.  This prevents single-
        pulse false alarms from generating phantom tracks.

        Args:
            detected: whether CFAR threshold was exceeded this frame.
        """
        self._detection_history.append(detected)
        if len(self._detection_history) > self.N_WINDOW:
            self._detection_history.pop(0)

        hits = sum(self._detection_history)

        if self.track["valid"]:
            # Already confirmed — check for track loss
            if not detected:
                self._coast_frames += 1
                if self._coast_frames >= self._max_coast:
                    self.track["valid"] = False
                    self.track["tentative"] = False
                    self.track["status"] = "TRACK_LOST"
                    self._detection_history.clear()
                    self._coast_frames = 0
            else:
                self._coast_frames = 0
        else:
            # Not yet confirmed — check M-of-N
            if hits >= self.M_REQUIRED:
                self.track["valid"] = True
                self.track["tentative"] = False
                self.track["status"] = "CONFIRMED"
                self._coast_frames = 0
            elif hits > 0:
                self.track["tentative"] = True
                self.track["status"] = "TENTATIVE"
            else:
                self.track["tentative"] = False
                self.track["status"] = "SEARCHING"

    # ──────────────────────────────────────────────────────────────────────
    #  Main Tick — called every simulation frame
    # ──────────────────────────────────────────────────────────────────────
    def tick(self, universe, dt: float):
        """
        The active scan cycle of the AESA radar.

        Each tick:
        1. Interrogates all targets via the Radar Equation.
        2. Computes SNR = P_r / P_n using the Boltzmann noise floor.
        3. Applies CFAR threshold.
        4. Corrupts the measurement with AWGN ∝ 1/√SNR.
        5. Feeds the M-of-N track initiation state machine.
        6. Updates the Alpha-Beta track filter if confirmed.
        """
        detected = False
        highest_snr = 0.0
        best_measurement = None
        best_target = None

        for entity in universe.entities:
            if isinstance(entity, Target):
                snr, true_vector = self.ping(entity)

                if snr > self.cfar_threshold_snr:
                    detected = True
                    if snr > highest_snr:
                        highest_snr = snr
                        noisy_vector = self._apply_awgn(true_vector, snr)
                        best_measurement = self.pos + noisy_vector
                        best_target = entity

        # ── SNR reporting ─────────────────────────────────────────────────
        if highest_snr > 0:
            # Target detected — real SNR
            self.track["last_snr"] = highest_snr
            self.track["last_snr_db"] = round(10.0 * math.log10(highest_snr), 2)
        else:
            # No target — simulate noise-only returns (noise / noise ≈ 1)
            # A real receiver sees thermal noise fluctuating around the
            # noise floor.  The ratio noise_sample / P_n follows an
            # exponential distribution with mean ≈ 1 (0 dB), giving
            # small random fluctuations that look realistic on the GCS.
            noise_sample = np.random.exponential(scale=self.noise_power)
            noise_only_snr = noise_sample / self.noise_power  # ≈ 1.0
            self.track["last_snr"] = noise_only_snr
            self.track["last_snr_db"] = round(10.0 * math.log10(max(noise_only_snr, 1e-6)), 2)

        # ── Track initiation state machine ───────────────────────────────
        self._update_initiation(detected)

        # ── Classification (runs even on tentative tracks) ───────────────
        if detected and best_target is not None:
            self._classify_track(best_target, highest_snr)

        # ── Alpha-Beta tracker update (only if confirmed) ────────────────
        if self.track["valid"] and detected and best_measurement is not None:
            if np.allclose(self.track["estimated_pos"], 0.0):
                # First confirmed measurement — initialise filter
                self.track["estimated_pos"] = best_measurement.copy()
                self.track["estimated_vel"] = np.array([0.0, 0.0, 0.0])
            else:
                alpha = 0.5
                beta = 0.1
                predicted_pos = (
                    self.track["estimated_pos"]
                    + self.track["estimated_vel"] * dt
                )
                residual = best_measurement - predicted_pos
                self.track["estimated_pos"] = predicted_pos + alpha * residual
                self.track["estimated_vel"] = (
                    self.track["estimated_vel"] + (beta / dt) * residual
                )
        elif self.track["valid"] and not detected:
            # Coasting — predict forward without correction
            self.track["estimated_pos"] = (
                self.track["estimated_pos"]
                + self.track["estimated_vel"] * dt
            )

    # ──────────────────────────────────────────────────────────────────────
    #  Telemetry — broadcast to GCS
    # ──────────────────────────────────────────────────────────────────────
    def get_telemetry(self):
        """Returns radar telemetry for the WebSocket broadcast."""
        telemetry = {
            "snr": self.track["last_snr_db"],
            "track_status": self.track["status"],
            "rcs_class": self.track["rcs_class"],
            "doppler_speed": self.track["doppler_speed"],
            "iff": self.track["iff"],
            "radar_profile": RADAR_PROFILE["name"],
            "radar_pt_watts": RADAR_PROFILE["pt_watts"],
            "radar_gain_db": RADAR_PROFILE["gain_db"],
        }
        if self.track["valid"] or self.track["tentative"]:
            telemetry["track"] = {
                "x": float(self.track["estimated_pos"][0]),
                "y": float(self.track["estimated_pos"][1]),
                "z": float(self.track["estimated_pos"][2]),
            }
        return telemetry
