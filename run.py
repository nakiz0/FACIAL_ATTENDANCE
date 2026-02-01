#!/usr/bin/env python3
import sys
import traceback

try:
    print("=" * 60)
    print("Starting Flask app with debug output...")
    print("=" * 60)
    
    from app import app, socketio
    
    print("\n✓ App module imported successfully")
    print("Starting SocketIO server...\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    
except KeyboardInterrupt:
    print("\n\nShutdown requested by user")
    sys.exit(0)
except Exception as e:
    print("\n" + "=" * 60)
    print("ERROR OCCURRED:")
    print("=" * 60)
    print(f"Exception: {type(e).__name__}: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("=" * 60)
    sys.exit(1)
