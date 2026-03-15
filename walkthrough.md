# Glaukopis v1.0.0 — Initial Release (Pantsir-S1 Baseline)

Welcome to **Glaukopis**, a high-fidelity tactical engagement simulator developed as a Digital Twin for advanced research in aerospace engineering and radar systems. This consolidated version (v1.0.0) marks the initial milestone of the project, integrating rigorous physical models with a modern Tactical Control Station (GCS) interface.

## System Overview

The simulator models the entire "sensor-to-shooter" chain with an absolute focus on **Truth Leak Prevention**. This ensures that no agent (missile or operator) has access to the raw coordinates of the universe; they depend exclusively on data processed and degraded by physical sensors.

### 1. Physics Engine (Python Backend)

The Glaukopis core has been upgraded to the **Pantsir-S1 (SA-22 Greyhound)** acquisition radar baseline.

*   **X-Band Radar:** Implements the Monostatic Radar Equation with 40dB gain and 150kW peak power.
*   **Boltzmann Thermal Noise Floor:** Receiver sensitivity is modeled by the Johnson-Nyquist equation ($P_n = k \cdot T_s \cdot B \cdot F$), ensuring detection is a real function of thermal physics.
*   **RK4 Integrator:** Kinematic trajectories use the 4th-order Runge-Kutta method, reducing truncation errors and enabling miss distance measurements with sub-meter precision in the terminal phase.
*   **Stochastic RCS (Swerling I):** Aircraft are not fixed points; they fluctuate according to Swerling theory, simulating the instability of radar echoes in real environments.

### 2. Tactical Control (Next.js GCS)

The Ground Control Station (GCS) allows for real-time interaction with the digital battlefield.

*   **Track Classification:** The system automatically classifies targets into RCS categories (LARGE, MEDIUM, SMALL, STEALTH) and Doppler.
*   **Engagement Doctrine:** Following standard operational patterns, aircraft are injected at **80% of their maximum detection range**. This ensures the interceptor has a realistic flight window.
*   **Advanced Telemetry:** Live panels monitor Signal-to-Noise Ratio (SNR), missile G-load (limited to 30G), and final approach.

## Research Findings

A highlight of this initial version is the physical validation of 5th-generation aircraft (**F-35 / F-22**) behavior against short/medium-range radars. The simulator demonstrates that under favorable lateral aspects (exposing higher RCS), these targets can still be detected and confirmed by the Pantsir-S1 at a distance of approximately **6-7 km**, a data point consistent with academic literature on X-Band stealth vulnerabilities.

## How to Run

To start the full simulation:

1.  **Backend:** `cd backend && python -m uvicorn main:app --port 8000`
2.  **Frontend:** `cd frontend && npm run dev` (Access [http://localhost:3000](http://localhost:3000))

---

*This document marks the stable initial release for research and future development of Smart Antenna algorithms.*
