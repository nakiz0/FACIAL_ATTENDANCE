#!/usr/bin/env python3
"""Initialize database with all tables"""

from app import app, db

print("Initializing database...")

try:
    with app.app_context():
        print("Creating all tables...")
        db.create_all()
        print("✓ Database tables created successfully!")
        
        # Verify tables exist
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\nCreated tables: {tables}")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
