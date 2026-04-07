import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path

# Add backend to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.abspath(os.path.join(script_dir, "..", "backend"))
sys.path.append(backend_path)

from physics.entities.target import Target, TARGET_PROFILES
from physics.entities.radar import Radar
from physics.universe import PhysicsEntity

def generate_time_series_dataset(output_file="time_series_radar_data.csv"):
    print("Initializing Glaukopis simulation for dataset generation...")
    
    # 1. Setup entities
    dt = 0.1
    max_time = 60.0
    
    radar = Radar("AESA_01", 0.0, 0.0, 0.0)
    
    # Use a Su-27 Flanker for a clear signal
    profile = TARGET_PROFILES["Su-27 Flanker"]
    target = Target(
        id="TGT_01",
        x=35000.0, y=5000.0, z=8000.0,
        sigma_min=profile["sigma_min"],
        sigma_max=profile["sigma_max"],
        swerling_type=profile["swerling_type"],
        iff=profile["iff"],
        profile_name="Su-27 Flanker"
    )
    # Give it a constant velocity vector moving towards origin (with slight offset)
    target.vel = np.array([-400.0, -50.0, -10.0]) 

    entities = [radar, target]
    
    # Mock universe for tick()
    class Universe:
        pass
    uni = Universe()
    uni.entities = entities

    rows = []
    
    print(f"Simulating {max_time} seconds of tactical data...")
    for t in np.arange(0, max_time, dt):
        # Tick radar to process detection and update filter
        radar.tick(uni, dt)
        
        # We need to manually capture the "Noisy" measurement before it disappears.
        # radar.tick() internally calls _apply_awgn.
        # We'll simulate it here to capture the raw 'Measured' point.
        snr, true_vector = radar.ping(target)
        noisy_pos = [0, 0, 0]
        if snr > radar.cfar_threshold_snr:
             # This matches how radar._apply_awgn works
             error_std_dev = 500.0 / np.sqrt(snr)
             noise = np.random.normal(0, error_std_dev, 3)
             noisy_pos = target.pos + noise
        
        # Capture state
        row = {
            "time_s": round(t, 2),
            "true_x": round(target.pos[0], 2),
            "true_y": round(target.pos[1], 2),
            "true_z": round(target.pos[2], 2),
            "measured_x": round(noisy_pos[0], 2) if snr > radar.cfar_threshold_snr else np.nan,
            "measured_y": round(noisy_pos[1], 2) if snr > radar.cfar_threshold_snr else np.nan,
            "measured_z": round(noisy_pos[2], 2) if snr > radar.cfar_threshold_snr else np.nan,
            "filtered_x": round(radar.track["estimated_pos"][0], 2) if radar.track["valid"] else np.nan,
            "filtered_y": round(radar.track["estimated_pos"][1], 2) if radar.track["valid"] else np.nan,
            "filtered_z": round(radar.track["estimated_pos"][2], 2) if radar.track["valid"] else np.nan,
            "snr_db": round(radar.track["last_snr_db"], 2),
            "status": radar.track["status"]
        }
        rows.append(row)
        
        # Update kinematics (Euler is fine for this high-level extraction)
        target.update_kinematics(dt)

    # 2. Save to CSV
    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False)
    print(f"Dataset successfully exported to {output_file}")
    
    return df

if __name__ == "__main__":
    generate_time_series_dataset()
