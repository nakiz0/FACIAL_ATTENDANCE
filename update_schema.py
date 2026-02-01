#!/usr/bin/env python3
"""Update database schema to add email_otp column to User model."""

from app import app, db, User

with app.app_context():
    try:
        # Check if email_otp column exists
        if not hasattr(User, 'email_otp'):
            print("❌ email_otp column not found. Adding it...")
            # Add the column
            with db.engine.begin() as conn:
                conn.execute("ALTER TABLE user ADD COLUMN email_otp VARCHAR(6)")
            print("✅ email_otp column added successfully")
        else:
            print("✅ email_otp column already exists")
        
        # Verify the schema
        users = User.query.all()
        print(f"\n✅ Database updated. Total users: {len(users)}")
        
    except Exception as e:
        print(f"⚠️ Error: {e}")
        print("Note: You may need to reset the database if this is a fresh start.")
        print("Run: rm db.sqlite3 && python init_db.py")
