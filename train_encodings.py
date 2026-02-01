#!/usr/bin/env python3
"""Rebuild face encodings from images in `face_data/` and save to `models/encodings.json`.

Usage:
    python train_encodings.py

This script mirrors the app's `build_encodings_from_images` logic but runs standalone.
"""
import os
import json
import sys
import numpy as np
import face_recognition

BASE = os.path.dirname(os.path.abspath(__file__))
FACE_DIR = os.path.join(BASE, 'face_data')
MODEL_DIR = os.path.join(BASE, 'models')
ENC_FILE = os.path.join(MODEL_DIR, 'encodings.json')

os.makedirs(MODEL_DIR, exist_ok=True)

all_names = []
all_encs = []

count_skipped = 0
for username in sorted(os.listdir(FACE_DIR)):
    user_folder = os.path.join(FACE_DIR, username)
    if not os.path.isdir(user_folder):
        continue
    for fname in sorted(os.listdir(user_folder)):
        if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        path = os.path.join(user_folder, fname)
        try:
            img = face_recognition.load_image_file(path)
            encs = face_recognition.face_encodings(img)
            if not encs:
                print(f"No face found in {path}; skipping")
                count_skipped += 1
                continue
            # take first face encoding found in image
            all_encs.append(encs[0].tolist())
            all_names.append(username)
            print(f"Encoded: {username}/{fname}")
        except Exception as e:
            print(f"Error processing {path}: {e}")
            count_skipped += 1

if not all_encs:
    print("No encodings generated. Check that `face_data/` contains images.")
    sys.exit(1)

data = {"names": all_names, "encodings": all_encs}
with open(ENC_FILE, 'w') as f:
    json.dump(data, f)

print(f"Saved {len(all_encs)} encodings for {len(set(all_names))} users to {ENC_FILE}")
if count_skipped:
    print(f"Skipped {count_skipped} images (no face or errors)")
