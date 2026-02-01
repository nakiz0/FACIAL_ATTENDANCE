#!/usr/bin/env python3
"""Quick script to check user email verification status."""

from app import app, db, User

with app.app_context():
    users = User.query.all()
    print(f"Total users: {len(users)}\n")
    for u in users:
        status = "✅ Verified" if u.email_verified else "❌ Not Verified"
        print(f"{u.username} ({u.role}): {u.email} - {status}")
    
    print("\n--- To manually mark a user as verified ---")
    print("Usage: python verify_user.py <username>")
