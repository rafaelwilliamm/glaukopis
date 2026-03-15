from batch_runner import BatchRunner
import json
import time

print("Loading scenario...")
with open('../scenarios/CM_01_15km_head-on.json') as f:
    scenario = json.load(f)

runner = BatchRunner(scenario)

print("Running Monte Carlo batch (3 seeds)...")
t0 = time.time()
runner.run(seed_start=1, seed_end=3, include_timeseries=False)
t1 = time.time()

p = runner.get_progress()

print(f"\nCompleted in {t1-t0:.3f} seconds.")
print(f"Seeds: {p['completed']}/{p['total']}")
print(f"Pk: {p['pk_percent']}%  Hits: {p['hits']}  Misses: {p['misses']}")
print(f"Mean miss: {p['mean_miss_distance_m']} m  Std: {p['std_miss_distance_m']} m\n")

for row in p['rows']:
    print(f"Seed {row['random_seed']:2d}: {row['result']:5s} | "
          f"Miss: {row['miss_distance_m']:5.2f}m | "
          f"Detect: {row['time_to_detect_s']}s | "
          f"Confirm: {row['time_to_confirm_s']}s | "
          f"Launch: {row['time_to_launch_s']}s | "
          f"Intercept: {row['time_to_intercept_s']}s")
