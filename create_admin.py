#!/usr/bin/env python3
"""Create admin user for testing"""

from app import app, db, User
from werkzeug.security import generate_password_hash

print("=" * 60)
print("ADMIN USER CREATION SCRIPT")
print("=" * 60)

try:
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("\n✓ Admin user already exists!")
            print(f"  Username: admin")
            print(f"  Email: {admin.email}")
            print(f"  Email Verified: {admin.email_verified}")
        else:
            print("\nCreating new admin user...")
            
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),  # Change this!
                email='amritxtamu132@gmail.com',  # Your email
                role='admin',
                email_verified=True  # Mark as verified so they can login immediately
            )
            
            db.session.add(admin)
            db.session.commit()
            
            print("\n✅ Admin user created successfully!")
            print("\n" + "=" * 60)
            print("LOGIN CREDENTIALS:")
            print("=" * 60)
            print(f"Username: admin")
            print(f"Password: admin123")
            print(f"Email: amritxtamu132@gmail.com")
            print(f"Role: admin")
            print(f"Email Verified: Yes (can login immediately)")
            print("=" * 60)
            print("\n⚠️  IMPORTANT NOTES:")
            print("- Change the default password after first login")
            print("- Update .env file with correct Gmail app-specific password")
            print("  (Visit: https://myaccount.google.com/apppasswords)")
            print("=" * 60)
            
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
