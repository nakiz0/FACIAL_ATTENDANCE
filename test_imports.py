#!/usr/bin/env python3
"""Test if all imports work and app can initialize"""

import sys
import os

print("Testing imports...")

try:
    print("1. Testing flask imports...")
    from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
    print("   ✓ Flask imports OK")
except Exception as e:
    print(f"   ✗ Flask import error: {e}")
    sys.exit(1)

try:
    print("2. Testing flask_sqlalchemy...")
    from flask_sqlalchemy import SQLAlchemy
    print("   ✓ SQLAlchemy import OK")
except Exception as e:
    print(f"   ✗ SQLAlchemy import error: {e}")
    sys.exit(1)

try:
    print("3. Testing flask_mail...")
    from flask_mail import Mail, Message
    print("   ✓ Mail import OK")
except Exception as e:
    print(f"   ✗ Mail import error: {e}")
    sys.exit(1)

try:
    print("4. Testing itsdangerous...")
    from itsdangerous import URLSafeTimedSerializer
    print("   ✓ itsdangerous import OK")
except Exception as e:
    print(f"   ✗ itsdangerous import error: {e}")
    sys.exit(1)

try:
    print("5. Testing flask_socketio...")
    from flask_socketio import SocketIO, emit
    print("   ✓ SocketIO import OK")
except Exception as e:
    print(f"   ✗ SocketIO import error: {e}")
    sys.exit(1)

try:
    print("6. Testing flask_wtf.csrf...")
    from flask_wtf.csrf import CSRFProtect
    print("   ✓ CSRFProtect import OK")
except Exception as e:
    print(f"   ✗ CSRFProtect import error: {e}")
    sys.exit(1)

try:
    print("7. Testing werkzeug security...")
    from werkzeug.security import generate_password_hash, check_password_hash
    print("   ✓ Werkzeug security import OK")
except Exception as e:
    print(f"   ✗ Werkzeug security import error: {e}")
    sys.exit(1)

try:
    print("8. Testing apscheduler...")
    from apscheduler.schedulers.background import BackgroundScheduler
    print("   ✓ APScheduler import OK")
except Exception as e:
    print(f"   ✗ APScheduler import error: {e}")
    sys.exit(1)

try:
    print("9. Testing image libraries...")
    from PIL import Image
    import numpy as np
    import face_recognition
    print("   ✓ Image libraries OK")
except Exception as e:
    print(f"   ✗ Image libraries error: {e}")
    sys.exit(1)

try:
    print("10. Testing dotenv...")
    from dotenv import load_dotenv
    print("   ✓ dotenv import OK")
except Exception as e:
    print(f"   ✗ dotenv import error: {e}")
    sys.exit(1)

print("\n✓ All imports successful!")
print("\nNow testing app initialization...")

try:
    print("Loading app.py...")
    import app as app_module
    print("✓ app.py loaded successfully!")
except Exception as e:
    print(f"✗ Failed to load app.py: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓✓✓ All tests passed! App should start OK.")
