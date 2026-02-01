"""Analyze face encodings to suggest a matching threshold.

- Loads `models/encodings.json` (must be created by `train_encodings.py`).
- Computes pairwise Euclidean distances between encodings.
- Separates intra-class (same username) and inter-class distances.
- Prints summary statistics and suggests a threshold.

Usage:
    python analyze_thresholds.py
"""
import os, json, sys
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
ENC_FILE = os.path.join(BASE, 'models', 'encodings.json')

if not os.path.exists(ENC_FILE):
    print(f"Encodings file not found: {ENC_FILE}\nRun train_encodings.py first.")
    sys.exit(1)

with open(ENC_FILE, 'r') as f:
    data = json.load(f)

names = data.get('names', [])
encodings = data.get('encodings', [])
if not encodings:
    print('No encodings found in file. Run training first.')
    sys.exit(1)

encs = np.array(encodings)
N = len(encs)
print(f"Loaded {N} encodings for {len(set(names))} unique users.")

# Compute pairwise distances
# Efficient vectorized computation
D = np.linalg.norm(encs[:, None, :] - encs[None, :, :], axis=2)
# We'll consider only i<j to avoid duplicates and zeros on diagonal
intra = []
inter = []
for i in range(N):
    for j in range(i+1, N):
        if names[i] == names[j]:
            intra.append(D[i, j])
        else:
            inter.append(D[i, j])

intra = np.array(intra)
inter = np.array(inter)

def stats(arr):
    return {
        'count': int(len(arr)),
        'mean': float(np.mean(arr)) if len(arr) else None,
        'median': float(np.median(arr)) if len(arr) else None,
        'std': float(np.std(arr)) if len(arr) else None,
        'min': float(np.min(arr)) if len(arr) else None,
        'max': float(np.max(arr)) if len(arr) else None,
        'p05': float(np.percentile(arr, 5)) if len(arr) else None,
        'p25': float(np.percentile(arr, 25)) if len(arr) else None,
        'p75': float(np.percentile(arr, 75)) if len(arr) else None,
        'p95': float(np.percentile(arr, 95)) if len(arr) else None,
    }

print('\nIntra-class (same user) distances:')
if len(intra):
    s_in = stats(intra)
    for k, v in s_in.items():
        print(f"  {k}: {v}")
else:
    print('  (no intra-class pairs — probably only one encoding per user or only one user present)')

print('\nInter-class (different users) distances:')
if len(inter):
    s_out = stats(inter)
    for k, v in s_out.items():
        print(f"  {k}: {v}")
else:
    print('  (no inter-class pairs — only one user present)')

# Suggest thresholds if possible
candidates = []
if len(intra) and len(inter):
    # Conservative: 95th percentile of intra and 5th percentile of inter
    p95_intra = np.percentile(intra, 95)
    p05_inter = np.percentile(inter, 5)
    candidates.append(('mid_95in_05out', float((p95_intra + p05_inter)/2)))
    # Midpoint of means
    candidates.append(('mid_mean', float((np.mean(intra) + np.mean(inter))/2)))
    # Midpoint of medians
    candidates.append(('mid_median', float((np.median(intra) + np.median(inter))/2)))

    print('\nSuggested threshold candidates:')
    for name, val in candidates:
        print(f"  {name}: {val:.4f}")
    print('\nGuidance: choose a threshold between typical intra and inter distances. Lower is stricter.')
else:
    print('\nCannot compute reliable threshold because there are not both intra- and inter-class pairs.')
    print('Add more users and/or more images per user and re-run the analysis to get a recommendation.')

# Optionally dump CSV of pairs for manual inspection
OUT = os.path.join(BASE, 'models', 'distance_pairs.csv')
with open(OUT, 'w') as f:
    f.write('i,j,name_i,name_j,distance,type\n')
    for i in range(N):
        for j in range(i+1, N):
            t = 'intra' if names[i]==names[j] else 'inter'
            f.write(f"{i},{j},{names[i]},{names[j]},{D[i,j]:.6f},{t}\n")
print(f"\nDetailed pair distances saved to {OUT}")
