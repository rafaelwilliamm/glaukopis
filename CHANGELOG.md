# Changelog

All notable changes to the Glaukopis project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] - 2026-03-15

### Added

#### Physics & Radar Baseline (Pantsir-S1)
- **Radar Hardware Baseline**: Upgraded physical parameters to match **Pantsir-S1 (SA-22 Greyhound)** acquisition radar (150kW Peak Power, 40dB Gain).
- **Boltzmann Thermal Noise Floor**: Implemented `P_n = k · T · B · F` (T=290K, B=10MHz, F=3) for realistic sensitivity calculations.
- **RK4 Kinematic Integrator**: Replaced Euler integration with a 4th-order Runge-Kutta scheme for high-fidelity intercept accuracy.
- **Swerling Type I RCS**: Stochastic fluctuation on target echoes to model realistic radar return instability.
- **M-of-N Track Initiation**: Robust 3-of-5 confirmation logic before tracks are considered weaponizable.

#### Engagement & Doctrine
- **Doctrine-Based Spawning**: Targets now spawn at **80% of their maximum detection range** for each profile, ensuring realistic engagement windows.
- **Proportional Navigation (PN)**: 3D guidance with a 30G structural limit and proximity fuzing (15m radius).
- **Monte Carlo Engine**: Full batch runner for research-grade statistical analysis of engagement outcomes.

#### Tactical Interface (GCS)
- **Next.js Dashboard**: Real-time visualization of sensor data, tactical maps (Leaflet), and performance charts (SNR, G-Force, Miss Distance).
- **Target Profile Selector**: 9 authentic threat profiles ranging from Boeing 747s to 5th-gen Stealth (F-35/F-22).
- **Data Traceability**: Full CSV telemetry export with radar configuration metadata included in every row.

#### Documentation
- **Technical README**: Complete architecture and physics documentation with LaTeX formatting.
- **Scientific Docstrings**: Comprehensive theory-to-code mapping in all backend modules.

---

*Initial stable release for academic research on Smart Antennas and Radars.*
