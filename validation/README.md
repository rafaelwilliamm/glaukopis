# Simulator Integrator Validation: Euler vs RK4

This directory contains research on the effect of numerical integrators on the terminal interception physics of the Glaukopis Tactical Simulator.

**Conclusion:** Replacing the first-order Euler integrator with the fourth-order RK4 produced **no statistically significant improvement in the interception probability** ($\Delta P_b = 0.0\text{--}0.5\text{pp}$ in 200 realizations for high-speed intercepts). 

This outcome formally establishes that in systems where the performance bottleneck is terminal guidance dynamics rather than integration precision, the choice of the numerical scheme has a secondary impact. The limitation resides in the lack of sustained longitudinal propulsion and the boundaries of constant-speed True Proportional Navigation (TPN), not in the simulated kinematic trajectory propagation.

For full Python code, visualizations, and in-depth conclusions, view the Jupyter notebook: [monte_carlo_euler_vs_rk4.ipynb](./monte_carlo_euler_vs_rk4.ipynb).
