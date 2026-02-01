#!/usr/bin/env python3
"""Manually verify a user's email"""

from app import app, db, User

print("=" * 60)
print("EMAIL VERIFICATION SCRIPT")
print("=" * 60)

try:
    username = input("\nEnter username to verify: ").strip()
    
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"\n✗ User '{username}' not found!")
            exit(1)
        
        if user.email_verified:
            print(f"\n✓ User '{username}' is already verified!")
            print(f"  Email: {user.email}")
        else:
            print(f"\nVerifying user: {username}")
            print(f"Email: {user.email}")
            
            user.email_verified = True
            db.session.commit()
            
            print(f"\n✅ Email verified successfully!")
            print(f"   User '{username}' can now login!")
            
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
