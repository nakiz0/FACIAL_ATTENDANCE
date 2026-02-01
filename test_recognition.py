"""Quick test: loads encodings.json and evaluates distances for images in `face_data/`.
Prints per-image the best-matching username and distance.
"""
import os, json
import numpy as np
import face_recognition

BASE = os.path.dirname(os.path.abspath(__file__))
FACE_DIR = os.path.join(BASE, 'face_data')
ENC_FILE = os.path.join(BASE, 'models', 'encodings.json')

with open(ENC_FILE,'r') as f:
    data = json.load(f)

known_names = data.get('names', [])
known_encs = [np.array(e) for e in data.get('encodings', [])]

if not known_encs:
    print('No known encodings found. Run train_encodings.py first.')
    raise SystemExit(1)

for username in sorted(os.listdir(FACE_DIR)):
    user_folder = os.path.join(FACE_DIR, username)
    if not os.path.isdir(user_folder):
        continue
    for fname in sorted(os.listdir(user_folder)):
        if not fname.lower().endswith(('.jpg','.jpeg','.png')):
            continue
        path = os.path.join(user_folder, fname)
        img = face_recognition.load_image_file(path)
        encs = face_recognition.face_encodings(img)
        if not encs:
            print(f"{username}/{fname}: no face found")
            continue
        enc = encs[0]
        dists = face_recognition.face_distance(known_encs, enc)
        best_idx = int(np.argmin(dists))
        best_dist = float(dists[best_idx])
        best_name = known_names[best_idx]
        print(f"{username}/{fname}: best={best_name} dist={best_dist:.4f}")
