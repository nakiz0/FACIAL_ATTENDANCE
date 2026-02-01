#!/usr/bin/env python3
"""List all users in database"""

from app import app, db, User

print("=" * 60)
print("ALL USERS IN DATABASE")
print("=" * 60)

try:
    with app.app_context():
        users = User.query.all()
        
        if not users:
            print("\n✗ No users found in database!")
        else:
            print(f"\nTotal users: {len(users)}\n")
            for user in users:
                status = "✅ Verified" if user.email_verified else "❌ Not Verified"
                print(f"Username: {user.username}")
                print(f"Email: {user.email}")
                print(f"Role: {user.role}")
                print(f"Status: {status}")
                print("-" * 40)
            
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
