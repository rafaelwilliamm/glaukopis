import sys
import os
import json
import pandas as pd

# Add backend to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.abspath(os.path.join(script_dir, "..", "backend"))
sys.path.append(backend_path)

from batch_runner import BatchRunner

def run_single_seed(scenario_file=None, seed=101):
    if scenario_file is None:
        scenario_file = os.path.join(script_dir, "..", "scenarios", "SU27_01_43km_head-on.json")
    # Ensure stdout handles UTF-8 for Windows console
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass # Python < 3.7
        
    # 1. Load Scenario
    with open(scenario_file, 'r', encoding='utf-8') as f:
        scenario_cfg = json.load(f)
    
    print(f"Running Monte Carlo for Seed {seed} on scenario: {scenario_cfg.get('description', scenario_file)}")
    
    # 2. Setup BatchRunner for a single seed
    runner = BatchRunner(scenario_cfg)
    
    # We run from seed X to X (one trial)
    # include_timeseries=True ensures we get the frame-by-frame data
    runner.run(seed_start=seed, seed_end=seed, include_timeseries=True)
    
    # 3. Export to CSV
    csv_content = runner.export_timeseries_csv()
    csv_filename = f"timeseries_seed_{seed}.csv"
    
    with open(csv_filename, 'w', encoding='utf-8') as f:
        f.write(csv_content)
    
    print(f"CSV generated: {csv_filename}")
    
    # 4. Import and Display
    df = pd.read_csv(csv_filename)
    print("\n--- CSV Data Imported Successfully (First 5 rows) ---")
    print(df.head().to_string())
    
    return df

if __name__ == "__main__":
    # You can change the seed here
    run_single_seed(seed=101)
