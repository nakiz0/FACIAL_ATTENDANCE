#!/usr/bin/env python3
"""Minimal Flask + SocketIO test"""

from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-key'

try:
    print("Initializing SocketIO...")
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
    print("✓ SocketIO initialized")
except Exception as e:
    print(f"✗ SocketIO init error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

@app.route('/')
def index():
    return 'Hello'

if __name__ == '__main__':
    try:
        print("Starting app on http://0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        print(f"✗ App startup error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
