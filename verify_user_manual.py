#!/usr/bin/env python3
"""Manually mark a user's email as verified."""

import sys
from app import app, db, User

if len(sys.argv) < 2:
    print("Usage: python verify_user_manual.py <username>")
    sys.exit(1)

username = sys.argv[1]

with app.app_context():
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"❌ User '{username}' not found")
        sys.exit(1)
    
    if user.email_verified:
        print(f"✅ User '{username}' is already verified")
        sys.exit(0)
    
    user.email_verified = True
    db.session.commit()
    print(f"✅ User '{username}' ({user.email}) has been marked as verified")
