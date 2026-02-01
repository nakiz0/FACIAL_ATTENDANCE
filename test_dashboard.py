import os
import time
from app import app, db, User, Attendance
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Remove and recreate database
if os.path.exists('db.sqlite3'):
    try:
        os.remove('db.sqlite3')
    except PermissionError:
        print("Database is locked, waiting...")
        time.sleep(2)
        os.remove('db.sqlite3')

with app.app_context():
    db.create_all()
    
    # Create test users
    admin = User(username='admin', password=generate_password_hash('admin123'), email='admin@test.com', email_otp='000000', email_verified=True, role='admin', has_logged_in_once=False)
    student1 = User(username='student1', password=generate_password_hash('student123'), email='student1@test.com', email_otp='639576', email_verified=False, role='student', has_logged_in_once=False)
    
    db.session.add(admin)
    db.session.add(student1)
    db.session.commit()
    
    # Add some attendance records for student1
    subjects = ['Math', 'English', 'Science', 'History', 'Computer Science']
    base_date = datetime.now() - timedelta(days=30)
    
    for i in range(20):
        current_date = base_date + timedelta(days=i)
        subject = subjects[i % len(subjects)]
        status = 'Present' if i % 3 != 0 else 'Absent'
        
        att = Attendance(
            user_id=student1.id,
            subject=subject,
            date=current_date.strftime('%Y-%m-%d'),
            time='10:00',
            status=status
        )
        db.session.add(att)
    
    db.session.commit()
    print('✅ Database reset with test data')
    present = len([a for a in student1.attendances if a.status == 'Present'])
    absent = len([a for a in student1.attendances if a.status != 'Present'])
    print(f'   Total attendance records: {len(student1.attendances)}')
    print(f'   Present: {present}')
    print(f'   Absent: {absent}')
