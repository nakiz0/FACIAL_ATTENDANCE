import os
import time
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

# Wait a bit and try to remove
time.sleep(1)

# Try removing db multiple times
for attempt in range(3):
    try:
        if os.path.exists('db.sqlite3'):
            os.remove('db.sqlite3')
        break
    except PermissionError:
        print(f"Attempt {attempt + 1}: Database locked, retrying...")
        time.sleep(2)

# Now import and create
from app import app, db, User, Attendance

with app.app_context():
    db.create_all()
    
    # Create test users
    admin = User(
        username='admin', 
        password=generate_password_hash('admin123'), 
        email='admin@test.com', 
        email_otp='000000', 
        email_verified=True, 
        role='admin', 
        has_logged_in_once=False
    )
    student1 = User(
        username='student1', 
        password=generate_password_hash('student123'), 
        email='student1@test.com', 
        email_otp='639576', 
        email_verified=False, 
        role='student', 
        has_logged_in_once=False
    )
    
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
    
    # Verify data
    print('Dashboard Test Setup Complete')
    print('=' * 50)
    
    # Get updated student1 from db
    s1 = User.query.filter_by(username='student1').first()
    present = len([a for a in s1.attendances if a.status == 'Present'])
    absent = len([a for a in s1.attendances if a.status != 'Present'])
    
    print(f'Student: {s1.username}')
    print(f'Email: {s1.email} (Verified: {s1.email_verified})')
    print(f'Total Attendance Records: {len(s1.attendances)}')
    print(f'Present: {present}')
    print(f'Absent: {absent}')
    
    # Show by subject
    by_subject = {}
    for att in s1.attendances:
        if att.subject not in by_subject:
            by_subject[att.subject] = {'present': 0, 'absent': 0}
        if att.status == 'Present':
            by_subject[att.subject]['present'] += 1
        else:
            by_subject[att.subject]['absent'] += 1
    
    print('\nBy Subject:')
    for subj, data in by_subject.items():
        total = data['present'] + data['absent']
        pct = int((data['present'] / total * 100)) if total > 0 else 0
        print(f'  {subj}: {data["present"]}/{total} ({pct}%)')
