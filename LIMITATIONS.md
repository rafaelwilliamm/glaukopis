# Known Limitations & Simplifications

## Physics Simplifications

**Missile propulsion not modeled**
The interceptor has no longitudinal rocket motor. Velocity is built entirely through lateral PN acceleration, which is physically inconsistent with real SAM kinematics. This results in low intercept probability ($P_b \approx 2\%$ in Monte Carlo trials) against targets at operational ranges. Real systems such as the Pantsir-S1 missile achieve Mach 2.8 (~950 m/s) via solid-fuel boost-sustain motors not modeled here.

**Constant-velocity Kalman filter**
The tracker assumes constant velocity (CV model). Maneuvering targets violate this assumption, causing track lag during evasive maneuvers. The Singer and IMM models are planned for v0.2.0.

**Deterministic butterfly RCS pattern**
The aspect-angle RCS model ($\sigma(\theta) = \sigma_{min} + (\sigma_{max} - \sigma_{min}) \cdot \sin^2 \theta$) is a simplified 2D projection. Real aircraft RCS is a complex 3D function of aspect angle, polarization, and frequency. Swerling Type I fluctuation is applied on top of this pattern as a first-order approximation.

**No atmospheric attenuation**
Rain, humidity, and atmospheric absorption are not modeled. The system loss factor $L=2.0$ is a fixed approximation.

**Single target, single interceptor**
The simulation models one-on-one engagements only. Multi-target tracking, salvo fire, and saturating attacks are not supported.

**No electronic warfare**
Jamming, spoofing, chaff, and other ECM/ECCM effects are absent from the current model.

## Statistical Limitations

**10–50 Monte Carlo seeds per scenario**
Academic convention recommends $\ge 100$ runs for confident interval estimation. Results should be interpreted as preliminary with wider confidence intervals than reported.

**Single geometry per scenario**
All scenarios use head-on approach geometry. Crossing, tail-chase, and diving geometries — which substantially alter RCS aspect angle and engagement kinematics — are not yet implemented.

## What These Limitations Mean for Results

The current $P_b$ values ($\approx 2\%$ for Su-27 and F-16) reflect the absence of missile propulsion more than any limitation of the radar or guidance algorithms. The miss distance distributions and CDF curves are physically meaningful for comparative analysis between profiles, but absolute $P_b$ values should not be interpreted as representing a real Pantsir-S1 system performance.
