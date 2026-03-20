# Glaukopis

**Tactical Engagement Simulator — Digital Twin**

[Placeholder for GIF]

Glaukopis is a physics-driven radar-and-missile interception simulator built for Aerospace Engineering research on **Smart Antennas and Radars**. It models the full sensor-to-shooter chain — from electromagnetic wave propagation and thermal noise to proportional navigation guidance and proximity fuze detonation — with strict **Truth Leak Prevention** ensuring that no agent in the simulation has omniscient access to the world state.

The current baseline system represents the **Pantsir-S1 (SA-22 Greyhound)** acquisition radar operating in Band X.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        TRUTH MODEL (Universe)                     │
│  Target.pos ─── true position ──────────────────────────────────  │
│  Target.vel ─── true velocity                                     │
│  ──────────── FIREWALL ─── No entity reads these directly ──────  │
├──────────────────────────────────────────────────────────────────┤
│  RADAR (Sensor)                                                   │
│    1. Radar Equation → P_r                                        │
│    2. Boltzmann Noise → P_n = k·T·B·F                            │
│    3. SNR = P_r / P_n                                             │
│    4. CFAR Threshold                                              │
│    5. AWGN corruption ∝ 1/√SNR                                   │
│    6. M-of-N Track Initiation (3/5)                               │
│    7. Alpha-Beta Track Filter                                     │
│    Output: estimated_pos, estimated_vel (noisy, delayed)          │
├──────────────────────────────────────────────────────────────────┤
│  MISSILE (Shooter)                                                │
│    Input: Radar estimated track (NOT truth)                       │
│    1. Proportional Navigation: a_c = N·V_c·(Ω × R̂)             │
│    2. G-Saturation (30G structural limit)                         │
│    3. Proximity Fuze (≤ 15 m → HIT)                              │
│    4. CPA Detection (miss → MISS)                                 │
├──────────────────────────────────────────────────────────────────┤
│  GCS FRONTEND (Next.js)                                           │
│    • Target Profile Selector (dynamic RCS)                        │
│    • Manual Engagement Authorization                              │
│    • Track Classification (RCS / Doppler / IFF)                   │
│    • Real-time SNR, Miss Distance, G-Force charts                 │
└──────────────────────────────────────────────────────────────────┘
```

### Truth Leak Prevention

The simulation strictly separates the **Truth Model** (Universe) from **Sensor Observations** (Radar). The missile guidance loop receives only the radar's noisy, delayed estimated track — never the target's true position. This ensures realistic engagement outcomes where low-SNR conditions, track initiation delays, and measurement noise degrade intercept probability just as they would in real hardware.

---

## Physics & Mathematics

### Boltzmann Thermal Noise Floor

The radar receiver's minimum detectable signal is governed by the Johnson-Nyquist thermal noise equation:

$$P_n = k \cdot T_s \cdot B \cdot F$$

| Symbol | Value | Description |
|--------|-------|-------------|
| $k$ | $1.380649 \times 10^{-23}$ J/K | Boltzmann constant |
| $T_s$ | 290 K | System temperature |
| $B$ | 10 MHz | Receiver bandwidth |
| $F$ | 3 (≈ 4.77 dB) | Noise figure |

### Radar Equation

Received power from a target at range $R$ with RCS $\sigma$:

$$P_r = \frac{P_t \cdot G^2 \cdot \lambda^2 \cdot \sigma}{(4\pi)^3 \cdot R^4 \cdot L}$$

| Parameter | Symbol | Value | Description |
|-----------|:------:|:------|:------------|
| Peak Power| $P_t$  | 150 kW| Pantsir-S1 peak transmit power |
| Gain      | $G$    | 40 dB | linear 10,000 (phased array) |
| Wavelength| $\lambda$| 0.03 m| Carrier frequency 10 GHz (Band X) |
| Loss      | $L$    | 2.0   | 3 dB system-wide losses |

### Signal-to-Noise Ratio

$$\text{SNR} = \frac{P_r}{P_n}$$

Detection is declared only when SNR exceeds the CFAR threshold (~13 dB).

### Proportional Navigation (PN)

The missile's lateral acceleration command normal to the Line-of-Sight:

$$\vec{a}_c = N \cdot V_c \cdot (\vec{\Omega} \times \hat{R})$$

Where:
- $N = 4$ — Navigation constant (Optimized for head-on)
- $V_c = -\vec{V}_{rel} \cdot \hat{R}$ — Closing velocity
- $\vec{\Omega} = \frac{\vec{R} \times \vec{V}_{rel}}{|\vec{R}|^2}$ — LOS angular rate

Acceleration is clamped to **30G** to model airframe structural limits.

### Kalman (Alpha-Beta) Track Filter

The radar maintains a smoothed track estimate using a first-order Alpha-Beta filter with prediction/correction cycle, preventing raw noisy measurements from reaching the fire-control loop.

---

## Target Profiles

| Profile | RCS (Frontal) | Doctrine (80% Rmax) | IFF |
|---------|:-------------:|:-------------------:|:---:|
| **Boeing 747** | 10.0 m² | 60,000 m | ✅ Friendly |
| **MiG-31 Foxhound** | 5.0 m² | 50,000 m | ❌ Hostile |
| **Su-27 Flanker** | 3.0 m² | 43,000 m | ❌ Hostile |
| **F/A-18 Hornet** | 1.0 m² | 38,000 m | ❌ Hostile |
| **F-16 Fighting Falcon** | 0.5 m² | 28,000 m | ❌ Hostile |
| **Cruise Missile / DJI Drone** | 0.05 m² | 18,000 m | ❌ Hostile |
| **PAK FA / Su-57** | 0.01 m² | 18,000 m | ❌ Hostile |
| **F-35 / F-22 Stealth** | 0.001 m² | 6,000 m | ❌ Hostile |
| **Bird (Large)** | 0.005 m² | 5,000 m | ✅ Friendly |
---

## Validation Experiments

For reproducible Jupyter notebooks documenting key design decisions and scientific validation — including the Euler vs RK4 kinematic integrator comparison (200 Monte Carlo seeds) — see the [`validation/`](./validation/) directory.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install fastapi uvicorn numpy websockets
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Usage

1. **Select a target profile** from the dropdown in the top bar.
2. Wait for the radar to establish a **Confirmed Track** (M-of-N initiation).
3. The **Fire Control System (FCS)** will automatically authorize engagement once a stable track is locked.
4. Observe the engagement outcome: **🎯 TARGET DESTROYED** or **💨 ENGAGEMENT FAILED**.
5. Click **Reset** to restart the scenario.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Physics | Python, NumPy, FastAPI |
| Real-time Comms | WebSocket |
| Frontend | Next.js 16, React 19, TypeScript |
| Mapping | Leaflet / react-leaflet |
| Charts | Recharts |
| Styling | Tailwind CSS 4 |

---

## License

This project is developed for academic research purposes.

---

*Glaukopis (Γλαυκῶπις) — "Bright-eyed", an epithet of Athena, goddess of strategic warfare.*
