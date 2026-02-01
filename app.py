import os, io, json, base64, random
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import numpy as np
import face_recognition

# ---------------- config ----------------
BASE = os.path.dirname(os.path.abspath(__file__))
FACE_DIR = os.path.join(BASE, 'face_data')
MODEL_DIR = os.path.join(BASE, 'models')
ENC_FILE = os.path.join(MODEL_DIR, 'encodings.json')
os.makedirs(FACE_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, '.env'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devsecret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE, 'db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT','587'))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
# Recognition thresholds (tweak for more active recognition)
# Higher MATCH_THRESHOLD -> allow larger distances (more permissive)
MATCH_THRESHOLD = float(os.getenv('MATCH_THRESHOLD','0.60'))
# KNN voting settings for recognition confidence - increase K for stronger voting
KNN_K = int(os.getenv('KNN_K','5'))
# Lower confidence threshold to be more permissive; fallback logic will still guard
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD','0.50'))

db = SQLAlchemy(app)
mail = Mail(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
# CSRF protection for forms. Exempt API/fetch endpoints separately below.
csrf = CSRFProtect(app)

# Make csrf_token available to all templates
@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)


@app.context_processor
def inject_current_user():
    """Inject current_user (User object or None) into all templates as `current_user`."""
    uid = session.get('user_id')
    user = None
    try:
        if uid:
            user = User.query.get(uid)
    except Exception:
        user = None
    return dict(current_user=user)

# token serializer for password reset
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# In-memory store for OTPs with timestamp: { username_or_email: { 'otp': '123456', 'sent_at': datetime } }
# Using in-memory store to avoid DB migrations; suitable for dev/test. Server restart clears OTPs.
EMAIL_OTP_STORE = {}

def send_verification_email(user):
    """Send email verification link (24 hour expiry)"""
    if not user.email:
        print(f'❌ User {user.username} has no email address')
        return False
    try:
        token = serializer.dumps(user.email, salt='email-verify-salt')
        link = url_for('verify_email', token=token, _external=True)
        msg = Message(subject='Verify your email address', recipients=[user.email])
        msg.html = render_template('verify_email_email.html', username=user.username, verify_link=link)
        mail.send(msg)
        print(f'✅ Verification email sent to {user.email}')
        return True
    except Exception as e:
        print(f'❌ Verification email send failed: {e}')
        app.logger.exception('verify mail failed: %s', e)
        return False

def send_reset_email(user):
    # Build reset link (always generate)
    if not user.email:
        print(f'❌ User {user.username} has no email address')
        return None
    token = serializer.dumps(user.email, salt='password-reset-salt')
    link = url_for('reset_password', token=token, _external=True)
    try:
        msg = Message(subject='Password reset request', recipients=[user.email])
        msg.html = render_template('password_reset_email.html', username=user.username, reset_link=link)
        mail.send(msg)
        print(f'✅ Reset email sent to {user.email}')
    except Exception as e:
        # Log but still return the link so local/dev testing can use it
        print(f'❌ Email send failed: {e}')
        app.logger.exception('reset mail failed: %s', e)
    return link

# ---------------- models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)  # use hashing in prod
    email = db.Column(db.String(200))
    email_otp = db.Column(db.String(6))  # 6-digit OTP for email verification
    email_verified = db.Column(db.Boolean, default=False)  # True only after email confirmation
    has_logged_in_once = db.Column(db.Boolean, default=False)  # Track first login
    role = db.Column(db.String(20), default='student')  # admin | teacher | student
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='attendances')
    subject = db.Column(db.String(150))
    date = db.Column(db.String(20))  # yyyy-mm-dd
    time = db.Column(db.String(8))
    status = db.Column(db.String(20), default='Present')

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10))   # Monday
    start = db.Column(db.String(5))  # HH:MM
    end = db.Column(db.String(5))
    subject = db.Column(db.String(120))


# Audit record for manual confirmations
class ManualConfirmation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.String(150))
    date = db.Column(db.String(20))
    time = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Audit log for edits and deletes
class EditAudit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(50))  # e.g., 'update', 'delete', 'create'
    target_type = db.Column(db.String(50))  # 'timetable', 'attendance', 'user'
    target_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- encodings helpers ----------------
def load_encodings():
    if not os.path.exists(ENC_FILE):
        return {"names": [], "encodings": []}
    with open(ENC_FILE,'r') as f:
        data = json.load(f)
    encs = [np.array(e) for e in data.get('encodings',[])]
    return {"names": data.get('names',[]), "encodings": encs}


def build_user_enc_map(enc_obj=None):
    """Return a dict mapping username -> list of numpy encodings.

    If enc_obj is None, uses the global ENC.
    """
    if enc_obj is None:
        enc_obj = globals().get('ENC', None)
    if not enc_obj or not enc_obj.get('encodings'):
        return {}
    m = {}
    names = enc_obj.get('names', [])
    encs = enc_obj.get('encodings', [])
    for n, e in zip(names, encs):
        m.setdefault(n, []).append(np.array(e))
    # convert lists to numpy arrays for faster distance computation
    for k in list(m.keys()):
        m[k] = np.vstack(m[k]) if len(m[k]) > 0 else np.array([])
    return m

def save_encodings(names, encodings):
    data = {"names": names, "encodings":[e.tolist() for e in encodings]}
    with open(ENC_FILE,'w') as f:
        json.dump(data,f)

def build_encodings_from_images():
    names=[]; encs=[]
    for username in os.listdir(FACE_DIR):
        folder = os.path.join(FACE_DIR, username)
        if not os.path.isdir(folder): continue
        for fname in os.listdir(folder):
            if fname.lower().endswith(('.jpg','.jpeg','.png')):
                path = os.path.join(folder,fname)
                try:
                    img = face_recognition.load_image_file(path)
                    d = face_recognition.face_encodings(img)
                    if d:
                        encs.append(d[0]); names.append(username)
                except Exception as e:
                    app.logger.warning('skip %s: %s', path, e)
    save_encodings(names, encs)
    return names, encs

# pre-load encodings
ENC = load_encodings()

# ---------------- email helper ----------------
def send_attendance_email_to_user(user:User, att_date:str, subject_name:str):
    if not user.email: return False
    try:
        msg = Message(subject=f'Attendance marked: {att_date}',
                      recipients=[user.email])
        msg.html = render_template('email_template.html',
                                   username=user.username,
                                   date=att_date,
                                   subject=subject_name,
                                   organization='Your Institute')
        mail.send(msg)
        return True
    except Exception as e:
        app.logger.exception('Mail send failed: %s', e)
        return False

# ---------------- views ----------------
@app.route('/')
def index():
    if 'user_id' in session:
        u = User.query.get(session['user_id'])
        if u.role=='admin': return redirect(url_for('admin_dashboard'))
        if u.role=='teacher': return redirect(url_for('teacher_take_attendance'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        u = request.form['username']; p = request.form['password']
        user = User.query.filter_by(username=u).first()
        if user:
            # Support existing plaintext passwords by migrating on first successful login
            pwd_ok = False
            try:
                # If stored password looks like a werkzeug hash use check_password_hash
                if user.password and (user.password.startswith('pbkdf2:') or user.password.startswith('argon2:')):
                    pwd_ok = check_password_hash(user.password, p)
                else:
                    # legacy plaintext: compare directly, then migrate to hashed password
                    if user.password == p:
                        pwd_ok = True
                        user.password = generate_password_hash(p)
                        db.session.commit()
            except Exception:
                pwd_ok = False

            if not pwd_ok:
                user = None
        if user:
            # For returning users: require email verification if email exists and not verified
            if user.has_logged_in_once and user.email and not user.email_verified:
                error = '❌ Please verify your email to login. Check your inbox for OTP and go to /verify_email.'
            else:
                # First-time login: allow access
                session['user_id'] = user.id
                # Mark that user has logged in once
                if not user.has_logged_in_once:
                    user.has_logged_in_once = True
                    db.session.commit()
                return redirect(url_for('index'))
        else:
            error = 'Invalid credentials'
    return render_template('login.html', error=error)


# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# User registration
@app.route('/register', methods=['GET','POST'])
def register():
    error = None
    message = None
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email') or None
        password = request.form.get('password')
        role = request.form.get('role') or 'student'

        if not username or not password:
            error = 'Username and password are required.'
        elif len(password) < 4:
            error = 'Password must be at least 4 characters.'
        elif User.query.filter_by(username=username).first():
            error = 'Username already exists. Choose another.'
        elif email and User.query.filter_by(email=email).first():
            error = f'❌ Email {email} is already registered. Use a different email or login if this is your account.'
        else:
            user = User(username=username,
                        password=generate_password_hash(password),
                        email=email,
                        role=role,
                        email_verified=False)
            db.session.add(user)
            db.session.commit()
            # Send OTP email if email provided
            if email:
                try:
                    # Generate 6-digit OTP
                    otp = str(random.randint(100000, 999999))
                    user.email_otp = otp
                    # record send time in in-memory store for expiry enforcement
                    try:
                        EMAIL_OTP_STORE[user.username] = {'otp': otp, 'sent_at': datetime.utcnow()}
                    except Exception:
                        pass
                    db.session.commit()
                    # Send OTP email
                    msg = Message(subject='Your Email Verification OTP', recipients=[email])
                    msg.html = render_template('otp_email.html', username=username, otp=otp)
                    mail.send(msg)
                    message = f'✅ Account created! An OTP has been sent to {email}. Enter it to verify your email.'
                except Exception as e:
                    message = f'Account created but OTP sending failed. Contact admin. Error: {str(e)}'
                    app.logger.exception('OTP mail failed: %s', e)
            else:
                message = '✅ Account created! You can now login (no email verification needed).'
                return render_template('register.html', message=message)
            
            # If email was provided, show OTP verification form
            if email:
                return render_template('register.html', verified_username=username, email_for_verification=email, message='✅ Account created! Check your email for OTP.')
            else:
                return render_template('register.html', message='✅ Account created! You can now login.')

    return render_template('register.html', error=error)


# Verify OTP during registration
@app.route('/verify_otp_register', methods=['POST'])
def verify_otp_register():
    username = request.form.get('username')
    otp = request.form.get('otp')
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return render_template('register.html', error='❌ User not found.')
    
    if user.email_verified:
        return render_template('register.html', message='✅ Email already verified! You can now login.')
    # Check for expiry if we have a record in our in-memory OTP store
    store = EMAIL_OTP_STORE.get(user.username)
    if store:
        sent = store.get('sent_at')
        if not sent or (datetime.utcnow() - sent) > timedelta(minutes=1):
            return render_template('register.html', error='❌ OTP expired. Please request a new OTP.', verified_username=username, email_for_verification=user.email or 'your email')
        if store.get('otp') != otp:
            return render_template('register.html', error='❌ Invalid OTP. Please check and try again.', verified_username=username, email_for_verification=user.email or 'your email')
    else:
        # fallback to legacy field check if in-memory store not present
        if not user.email_otp or user.email_otp != otp:
            email = user.email or 'your email'
            return render_template('register.html', error='❌ Invalid OTP. Please check and try again.', verified_username=username, email_for_verification=email)
    
    # Mark email as verified and clear OTP
    user.email_verified = True
    user.email_otp = None
    try:
        if user.username in EMAIL_OTP_STORE:
            del EMAIL_OTP_STORE[user.username]
    except Exception:
        pass
    db.session.commit()
    return render_template('register.html', message='✅ Email verified successfully! You can now login.')



# Password reset - request
@app.route('/password_reset', methods=['GET','POST'])
def password_reset_request():
    message=None
    if request.method=='POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        dev_link = None
        if user:
            dev_link = send_reset_email(user)
        # Do not reveal whether email exists in production; but if mail server is not configured,
        # surface the link for local testing so the developer can continue.
        if not app.config.get('MAIL_SERVER') and dev_link:
            message = f'A reset link has been generated (dev mode): {dev_link}'
            return render_template('password_reset_request.html', message=message)
        # Generic message otherwise
        message = 'If your email is in our system, a reset link has been sent.'
        return render_template('password_reset_request.html', message=message)
    return render_template('password_reset_request.html')


# Email verification - OTP based
@app.route('/verify_email', methods=['GET', 'POST'])
def verify_email():
    if request.method == 'POST':
        # If the form includes an email but no otp, treat as Send OTP request
        email = request.form.get('email')
        otp = request.form.get('otp')
        if email and not otp:
            # send OTP to this email if user exists
            user = User.query.filter_by(email=email).first()
            if not user:
                return render_template('verify_email_confirm.html', error='Email not found in our system.')
            # generate and store OTP
            try:
                code = str(random.randint(100000, 999999))
                user.email_otp = code
                db.session.commit()
                EMAIL_OTP_STORE[user.username] = {'otp': code, 'sent_at': datetime.utcnow()}
                msg = Message(subject='Your Email Verification OTP', recipients=[email])
                msg.html = render_template('otp_email.html', username=user.username, otp=code)
                mail.send(msg)
                return render_template('verify_email_confirm.html', message=f'OTP sent to {email}', username_to_verify=user.username)
            except Exception as e:
                app.logger.exception('Failed to send verification OTP: %s', e)
                return render_template('verify_email_confirm.html', error='Failed to send OTP. Try again later.')

        # Otherwise handle OTP verification (username+otp)
        username = request.form.get('username')
        otp = request.form.get('otp')
        user = User.query.filter_by(username=username).first()
        if not user:
            return render_template('verify_email_confirm.html', error='User not found.')
        if user.email_verified:
            return render_template('verify_email_confirm.html', message='✅ Your email is already verified!')

        # enforce 1-minute expiry if we have an in-memory record
        store = EMAIL_OTP_STORE.get(user.username)
        if store:
            sent = store.get('sent_at')
            if not sent or (datetime.utcnow() - sent) > timedelta(minutes=1):
                return render_template('verify_email_confirm.html', error='❌ OTP expired. Please request a new OTP.')
            if store.get('otp') != otp:
                return render_template('verify_email_confirm.html', error='❌ Invalid OTP. Please try again.')
        else:
            # fallback to legacy check
            if not user.email_otp or user.email_otp != otp:
                return render_template('verify_email_confirm.html', error='❌ Invalid OTP. Please try again.')

        # success
        user.email_verified = True
        user.email_otp = None
        try:
            if user.username in EMAIL_OTP_STORE:
                del EMAIL_OTP_STORE[user.username]
        except Exception:
            pass
        db.session.commit()
        return render_template('verify_email_confirm.html', message='✅ Email verified successfully! You can now login.')
    
    # GET request - show OTP form
    return render_template('verify_email_confirm.html')


# Old token-based verification (kept for backward compatibility, redirects to OTP)
@app.route('/verify_email/<token>')
def verify_email_token(token):
    try:
        email = serializer.loads(token, salt='email-verify-salt', max_age=86400)
    except Exception as e:
        return render_template('verify_email_confirm.html', error='Invalid or expired verification link. Please use the OTP sent to your email instead.')
    
    # Auto-verify if token is valid
    user = User.query.filter_by(email=email).first()
    if not user:
        return render_template('verify_email_confirm.html', error='User not found.')
    
    if user.email_verified:
        return render_template('verify_email_confirm.html', message='✅ Your email is already verified!')
    
    # Mark email as verified (legacy token verification)
    user.email_verified = True
    user.email_otp = None
    db.session.commit()
    return render_template('verify_email_confirm.html', message='✅ Email verified successfully! You can now login.')


# Password reset - token link
@app.route('/reset_password/<token>', methods=['GET','POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception as e:
        return render_template('password_reset_form.html', error='Invalid or expired token.')

    user = User.query.filter_by(email=email).first()
    if not user:
        return render_template('password_reset_form.html', error='User not found.')

    if request.method=='POST':
        pwd = request.form['password']
        conf = request.form['confirm']
        if pwd != conf:
            return render_template('password_reset_form.html', error='Passwords do not match.')
        # Update password (store hashed)
        user.password = generate_password_hash(pwd)
        db.session.commit()
        return render_template('password_reset_form.html', error='Password updated. You can now login.')

    return render_template('password_reset_form.html')


# Test email route (admin only)
@app.route('/admin/test_email/<username>')
def test_email(username):
    uid = session.get('user_id')
    admin = User.query.get(uid)
    if not admin or admin.role != 'admin':
        return jsonify({'ok': False, 'error': 'Admin only'})
    
    user = User.query.filter_by(username=username).first()
    if not user or not user.email:
        return jsonify({'ok': False, 'error': 'User not found or no email'})
    
    success = send_reset_email(user)
    if success:
        return jsonify({'ok': True, 'message': f'Test email sent to {user.email}'})
    else:
        return jsonify({'ok': False, 'error': 'Email send failed. Check terminal logs.'})


# Admin reset user password
@app.route('/admin/reset_user_password/<int:user_id>', methods=['POST'])
def admin_reset_password(user_id):
    uid = session.get('user_id')
    admin = User.query.get(uid)
    if not admin or admin.role != 'admin':
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'ok': False, 'error': 'User not found'})
    
    new_pwd = request.form.get('password')
    if not new_pwd or len(new_pwd) < 4:
        return jsonify({'ok': False, 'error': 'Password must be at least 4 characters'})
    # Store hashed password and do NOT return plaintext password in response
    user.password = generate_password_hash(new_pwd)
    db.session.commit()
    # Optionally send notification email
    try:
        send_reset_email(user)
    except Exception:
        pass
    return jsonify({'ok': True, 'message': f'Password for {user.username} has been reset.'})


# Admin dashboard (similar sections to screenshot)
@app.route('/admin')
def admin_dashboard():
    uid = session.get('user_id')
    if not uid: return redirect(url_for('login'))
    u = User.query.get(uid)
    if not u or u.role!='admin': return redirect(url_for('login'))
    # show students and teachers separately
    students = User.query.filter_by(role='student').order_by(User.username).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.username).all()
    attendance = Attendance.query.order_by(Attendance.date.desc()).limit(200).all()
    timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
    today = date.today().isoformat()
    return render_template('admin_dashboard.html', students=students, teachers=teachers, attendance=attendance, timetable=timetable, today=today)

# Add timetable entry
@app.route('/admin/timetable/add', methods=['POST'])
def admin_add_timetable():
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role not in ('admin','teacher'):
        return redirect(url_for('login'))
    day = request.form['day']
    start = request.form['start']
    end = request.form['end']
    subj = request.form['subject']
    t = Timetable(day=day, start=start, end=end, subject=subj)
    db.session.add(t)
    db.session.commit()
    # audit
    try:
        ea = EditAudit(actor_id=u.id if u else None, action='create', target_type='timetable', target_id=t.id, details=f'{t.day} {t.start}-{t.end} {t.subject}')
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Audit failed for timetable create')
    return redirect(url_for('admin_dashboard'))


# Update timetable entry
@app.route('/admin/timetable/update/<int:tid>', methods=['POST'])
def admin_update_timetable(tid):
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role not in ('admin','teacher'):
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    t = Timetable.query.get(tid)
    if not t:
        return jsonify({'ok': False, 'error': 'Not found'})
    data = request.json or {}
    t.day = data.get('day', t.day)
    t.start = data.get('start', t.start)
    t.end = data.get('end', t.end)
    t.subject = data.get('subject', t.subject)
    db.session.commit()
    # audit
    try:
        ea = EditAudit(actor_id=u.id if u else None, action='update', target_type='timetable', target_id=t.id, details=json.dumps({'day': t.day, 'start': t.start, 'end': t.end, 'subject': t.subject}))
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Audit failed for timetable update')
    return jsonify({'ok': True, 'message': 'Timetable updated'})


# Delete timetable entry
@app.route('/admin/timetable/delete/<int:tid>', methods=['POST'])
def admin_delete_timetable(tid):
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role not in ('admin','teacher'):
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    t = Timetable.query.get(tid)
    if not t:
        return jsonify({'ok': False, 'error': 'Not found'})
    db.session.delete(t)
    db.session.commit()
    try:
        ea = EditAudit(actor_id=u.id if u else None, action='delete', target_type='timetable', target_id=tid, details=f'deleted timetable {tid}')
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Audit failed for timetable delete')
    return jsonify({'ok': True, 'message': 'Timetable entry deleted'})

# Upload multiple images for a student (admin)
@app.route('/admin/upload_images', methods=['POST'])
def admin_upload_images():
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role != 'admin':
        return redirect(url_for('login'))
    username = request.form['username']
    # validate user exists
    target_user = User.query.filter_by(username=username).first()
    if not target_user:
        students = User.query.filter_by(role='student').all()
        teachers = User.query.filter_by(role='teacher').all()
        attendance = Attendance.query.order_by(Attendance.date.desc()).limit(200).all()
        timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
        return render_template('admin_dashboard.html', students=students, teachers=teachers, attendance=attendance, timetable=timetable, error=f'User "{username}" not found. Upload aborted.')
    files = request.files.getlist('images')
    folder = os.path.join(FACE_DIR, username)
    os.makedirs(folder, exist_ok=True)
    for f in files:
        fname = secure_filename(f.filename)
        f.save(os.path.join(folder, fname))
    # rebuild encodings
    build_encodings_from_images()
    global ENC
    ENC = load_encodings()
    return redirect(url_for('admin_dashboard'))

# Admin manual mark attendance
@app.route('/admin/mark', methods=['POST'])
def admin_mark():
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role != 'admin':
        return redirect(url_for('login'))
    username = request.form['username']
    subj = request.form['subject']
    dt = request.form.get('date') or date.today().isoformat()
    # Validate: Only allow marking for today and past dates, not future dates
    try:
        selected_date = datetime.strptime(dt, '%Y-%m-%d').date()
        if selected_date > date.today():
            students = User.query.filter_by(role='student').all()
            attendance = Attendance.query.order_by(Attendance.date.desc()).limit(200).all()
            timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
            return render_template('admin_dashboard.html', students=students, attendance=attendance, timetable=timetable, error='❌ Cannot mark attendance for future dates. Only today and past dates are allowed.')
    except ValueError:
        # Invalid date format
        students = User.query.filter_by(role='student').all()
        attendance = Attendance.query.order_by(Attendance.date.desc()).limit(200).all()
        timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
        return render_template('admin_dashboard.html', students=students, attendance=attendance, timetable=timetable, error='❌ Invalid date format. Please use YYYY-MM-DD.')

    user = User.query.filter_by(username=username).first()
    if user:
        att = Attendance(user_id=user.id, subject=subj, date=dt, time=datetime.now().strftime('%H:%M:%S'), status='Present')
        db.session.add(att)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))


# Update attendance record (change subject/date/time/status)
@app.route('/admin/attendance/update/<int:att_id>', methods=['POST'])
def admin_update_attendance(att_id):
    uid = session.get('user_id')
    u = User.query.get(uid)
    # allow both admin and teacher roles to edit attendance
    if not u or u.role not in ('admin', 'teacher'):
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    att = Attendance.query.get(att_id)
    if not att:
        return jsonify({'ok': False, 'error': 'Not found'})
    data = request.json or {}
    att.subject = data.get('subject', att.subject)
    att.date = data.get('date', att.date)
    att.time = data.get('time', att.time)
    att.status = data.get('status', att.status)
    db.session.commit()
    try:
        ea = EditAudit(actor_id=u.id if u else None, action='update', target_type='attendance', target_id=att.id, details=json.dumps({'subject': att.subject, 'date': att.date, 'time': att.time, 'status': att.status}))
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Audit failed for attendance update')
    return jsonify({'ok': True, 'message': 'Attendance updated'})


# Delete attendance record
@app.route('/admin/attendance/delete/<int:att_id>', methods=['POST'])
def admin_delete_attendance(att_id):
    uid = session.get('user_id')
    u = User.query.get(uid)
    # allow both admin and teacher roles to delete attendance
    if not u or u.role not in ('admin', 'teacher'):
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    att = Attendance.query.get(att_id)
    if not att:
        return jsonify({'ok': False, 'error': 'Not found'})
    db.session.delete(att)
    db.session.commit()
    try:
        ea = EditAudit(actor_id=u.id if u else None, action='delete', target_type='attendance', target_id=att_id, details=f'deleted attendance {att_id}')
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Audit failed for attendance delete')
    return jsonify({'ok': True, 'message': 'Attendance deleted'})

# Teacher - take attendance page
@app.route('/teacher/take')
def teacher_take_attendance():
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role not in ('teacher', 'admin'):
        return redirect(url_for('login'))
    # find current subject by timetable
    todayname = datetime.today().strftime('%A')
    nowt = datetime.now().time()
    todays = Timetable.query.filter_by(day=todayname).all()
    current_subject = None
    current_subject_time = ''
    for t in todays:
        s = datetime.strptime(t.start, '%H:%M').time()
        e = datetime.strptime(t.end, '%H:%M').time()
        if s <= nowt <= e:
            current_subject = t.subject
            current_subject_time = f"{t.start} - {t.end}"
            break

    # recent attendance (today) - show last 50 records
    today_iso = date.today().isoformat()
    recent = Attendance.query.filter(Attendance.date == today_iso).order_by(Attendance.time.desc()).limit(50).all()
    return render_template('teacher_take_attendance.html', subject=current_subject or '', subject_time=current_subject_time, timetable=todays, attendance=recent)


# Teacher dashboard
@app.route('/teacher/dashboard')
def teacher_dashboard():
    uid = session.get('user_id')
    u = User.query.get(uid)
    if not u or u.role not in ('teacher', 'admin'):
        return redirect(url_for('login'))
    # basic stats for teacher
    students_count = User.query.filter_by(role='student').count()
    # upcoming/today timetable
    todayname = datetime.today().strftime('%A')
    todays = Timetable.query.filter_by(day=todayname).all()
    return render_template('teacher_dashboard.html', user=u, students_count=students_count, timetable=todays)


@app.route('/teacher/timetable')
def teacher_timetable():
    uid = session.get('user_id')
    u = User.query.get(uid) if uid else None
    if not u or u.role not in ('teacher','admin'):
        return redirect(url_for('login'))
    timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
    return render_template('teacher_timetable.html', timetable=timetable)


# Timetable view (read-only) for students and teachers
@app.route('/timetable')
def view_timetable():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    u = User.query.get(uid)
    if not u:
        return redirect(url_for('login'))
    timetable = Timetable.query.order_by(Timetable.day, Timetable.start).all()
    return render_template('timetable.html', timetable=timetable)

# API recognize: receives base64 frame, marks attendance if matches
@app.route('/api/recognize', methods=['POST'])
@csrf.exempt
def api_recognize():
    payload = request.json
    frame_b64 = payload.get('frame')
    subject = payload.get('subject') or 'General'
    if not frame_b64:
        return jsonify({'ok': False, 'error': 'no_frame'})
    header, data = frame_b64.split(',', 1) if ',' in frame_b64 else ('', frame_b64)
    img_bytes = base64.b64decode(data)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    rgb = np.array(img)  # RGB
    face_locations = face_recognition.face_locations(rgb)
    face_encodings = face_recognition.face_encodings(rgb, face_locations)
    global ENC
    if not ENC or not ENC.get('encodings'):
        return jsonify({'ok': False, 'error': 'no_known_faces'})

    # Build per-user encodings map for robust matching
    user_map = build_user_enc_map(ENC)
    results = []
    marked_user_ids = set()

    # Prepare flat encodings list for simple KNN voting (indices map to ENC['names'])
    flat_names = ENC.get('names', [])
    flat_encs = ENC.get('encodings', [])

    for enc in face_encodings:
        # KNN across all known encodings
        try:
            all_dists = face_recognition.face_distance(flat_encs, enc)
        except Exception:
            all_dists = np.array([])

        if all_dists.size == 0:
            results.append({'ok': True, 'marked': False, 'reason': 'no_known_encodings'})
            continue

        # get top-k nearest encodings
        k = min(KNN_K, len(all_dists))
        idxs = np.argsort(all_dists)[:k]
        top_names = [flat_names[i] for i in idxs]
        top_dists = [float(all_dists[i]) for i in idxs]

        # voting majority label
        from collections import Counter
        cnt = Counter(top_names)
        majority_name, majority_count = cnt.most_common(1)[0]
        confidence = majority_count / k
        avg_dist = float(np.mean(top_dists))

        # Also compute per-user min distance (backup metric)
        per_user_min = None
        if user_map:
            per_user_min_vals = []
            for username, u_encs in user_map.items():
                if u_encs.size == 0:
                    continue
                d = face_recognition.face_distance(u_encs, enc)
                if len(d):
                    per_user_min_vals.append((username, float(np.min(d))))
            if per_user_min_vals:
                per_user_min_vals.sort(key=lambda x: x[1])
                per_user_min = per_user_min_vals[0]

        # Decision logic:
        # - If avg_dist <= MATCH_THRESHOLD and confidence >= CONFIDENCE_THRESHOLD -> accept
        # - If avg_dist <= MATCH_THRESHOLD but confidence below threshold -> low_confidence
        # - Otherwise -> no_match
        if avg_dist <= MATCH_THRESHOLD and confidence >= CONFIDENCE_THRESHOLD:
            chosen = majority_name
            chosen_dist = avg_dist
            decision = 'accept'
        elif avg_dist <= MATCH_THRESHOLD and confidence < CONFIDENCE_THRESHOLD:
            chosen = majority_name
            chosen_dist = avg_dist
            decision = 'low_confidence'
            # Promote low_confidence to accept if per-user min distance strongly supports it
            if per_user_min and per_user_min[1] <= (MATCH_THRESHOLD * 1.05):
                chosen = per_user_min[0]
                chosen_dist = per_user_min[1]
                decision = 'accept_fallback'
        else:
            # try per-user min as fallback if present
            if per_user_min and per_user_min[1] <= MATCH_THRESHOLD:
                chosen = per_user_min[0]
                chosen_dist = per_user_min[1]
                decision = 'accept_fallback'
            else:
                chosen = None
                chosen_dist = float(np.min(all_dists)) if all_dists.size else None
                decision = 'no_match'

        if chosen and decision.startswith('accept'):
            user = User.query.filter_by(username=chosen).first()
            if not user:
                results.append({'ok': False, 'reason': 'no_user_record', 'username': chosen, 'dist': chosen_dist, 'decision': decision})
                continue

            # Avoid marking the same user multiple times within this request
            if user.id in marked_user_ids:
                results.append({'ok': True, 'marked': False, 'reason': 'already_marked_request', 'username': chosen, 'dist': chosen_dist, 'decision': decision})
                continue

            today = date.today().isoformat()
            exists = Attendance.query.filter_by(user_id=user.id, date=today, subject=subject, status='Present').first()
            if exists:
                marked_user_ids.add(user.id)
                # emit event so front-end can show a popup that user was already marked
                try:
                    socketio.emit('attendance_already', {'username': chosen, 'subject': subject, 'date': today})
                except Exception:
                    pass
                results.append({'ok': True, 'marked': False, 'reason': 'already_marked_db', 'username': chosen, 'dist': chosen_dist, 'decision': decision, 'message': 'Already marked present for this subject today'})
                continue

            nowt = datetime.now().strftime('%H:%M:%S')
            att = Attendance(user_id=user.id, subject=subject, date=today, time=nowt, status='Present')
            db.session.add(att)
            db.session.commit()
            marked_user_ids.add(user.id)

            # emit socket event so teacher/admin/student dashboards can update in real time
            socketio.emit('attendance_marked', {'username': chosen, 'subject': subject, 'date': today, 'time': nowt})
            try:
                socketio.emit('attendance_popup', {'username': chosen, 'subject': subject, 'date': today, 'time': nowt, 'message': 'Attendance recorded'})
            except Exception:
                pass
            # send email
            send_attendance_email_to_user(user, today, subject)
            results.append({'ok': True, 'marked': True, 'username': chosen, 'dist': chosen_dist, 'confidence': confidence, 'decision': decision, 'message': 'Attendance recorded'})
        else:
            # no match or low confidence
            extra = {'ok': True, 'marked': False, 'reason': decision, 'dist': chosen_dist}
            if chosen:
                extra['username'] = chosen
                extra['confidence'] = confidence
            # provide a friendly message for common cases
            if decision == 'low_confidence':
                extra['message'] = 'Low confidence match — please confirm manually.'
            elif decision == 'no_match':
                extra['message'] = 'No matching face found.'
            else:
                extra['message'] = 'Not marked.'
            results.append(extra)

    return jsonify({'ok': True, 'results': results})

# API train: accepts frames for a username, saves images and rebuilds encodings
@app.route('/api/train', methods=['POST'])
@csrf.exempt
def api_train():
    payload = request.json
    username = payload.get('username')
    frames = payload.get('frames', [])
    if not username or not frames:
        return jsonify({'ok': False, 'error': 'need_username_frames'})
    # Ensure username exists before saving frames
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'ok': False, 'error': 'no_user'})
    folder = os.path.join(FACE_DIR, username)
    os.makedirs(folder, exist_ok=True)
    saved = 0
    for idx, b64 in enumerate(frames):
        h, d = b64.split(',', 1) if ',' in b64 else ('', b64)
        data = base64.b64decode(d)
        fname = f'{int(datetime.utcnow().timestamp()*1000)}_{idx}.jpg'
        with open(os.path.join(folder, fname), 'wb') as f:
            f.write(data)
        saved += 1
    build_encodings_from_images()
    global ENC
    ENC = load_encodings()
    return jsonify({'ok':True,'saved':saved})


# API confirm mark: teacher/admin can manually confirm a username to mark attendance
@app.route('/api/confirm_mark', methods=['POST'])
def api_confirm_mark():
    uid = session.get('user_id')
    actor = User.query.get(uid) if uid else None
    if not actor or actor.role not in ('teacher', 'admin'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    payload = request.json or {}
    username = payload.get('username')
    subject = payload.get('subject') or 'General'
    if not username:
        return jsonify({'ok': False, 'error': 'no_username'}), 400

    student = User.query.filter_by(username=username).first()
    if not student:
        return jsonify({'ok': False, 'error': 'no_user'}), 404

    today = date.today().isoformat()
    exists = Attendance.query.filter_by(user_id=student.id, date=today, subject=subject, status='Present').first()
    if exists:
        return jsonify({'ok': True, 'marked': False, 'reason': 'already_marked_db'})

    nowt = datetime.now().strftime('%H:%M:%S')
    att = Attendance(user_id=student.id, subject=subject, date=today, time=nowt, status='Present')
    db.session.add(att)
    db.session.commit()

    # Record manual confirmation audit
    try:
        mc = ManualConfirmation(actor_id=actor.id if actor else None,
                                 student_id=student.id,
                                 subject=subject,
                                 date=today,
                                 time=nowt)
        db.session.add(mc)
        db.session.commit()
    except Exception:
        app.logger.exception('Failed to record manual confirmation audit')
    try:
        ea = EditAudit(actor_id=actor.id if actor else None, action='create', target_type='attendance', target_id=att.id, details=f'manual_confirm by {actor.username if actor else None}')
        db.session.add(ea)
        db.session.commit()
    except Exception:
        app.logger.exception('Failed to record EditAudit for manual confirmation')

    # broadcast and notify
    socketio.emit('attendance_marked', {'username': student.username, 'subject': subject, 'date': today, 'time': nowt})
    send_attendance_email_to_user(student, today, subject)

    return jsonify({'ok': True, 'marked': True, 'username': student.username})


@app.route('/admin/manual_confirmations')
def admin_manual_confirmations():
    uid = session.get('user_id')
    admin = User.query.get(uid) if uid else None
    if not admin or admin.role != 'admin':
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    entries = ManualConfirmation.query.order_by(ManualConfirmation.created_at.desc()).limit(200).all()
    out = []
    for e in entries:
        actor = User.query.get(e.actor_id) if e.actor_id else None
        student = User.query.get(e.student_id) if e.student_id else None
        out.append({
            'id': e.id,
            'actor': actor.username if actor else None,
            'student': student.username if student else None,
            'subject': e.subject,
            'date': e.date,
            'time': e.time,
            'created_at': e.created_at.isoformat()
        })
    return jsonify({'ok': True, 'entries': out})

# list student attendance (student dashboard)
@app.route('/student')
def student_dashboard():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))
    user = User.query.get(uid)
    if user.role != 'student':
        return redirect(url_for('login'))
    
    # Get all attendance records for this student
    atts = Attendance.query.filter_by(user_id=user.id).order_by(Attendance.date.desc()).all()
    
    # Calculate statistics
    total_attendance = len(atts)
    present_count = len([a for a in atts if a.status == 'Present'])
    absent_count = len([a for a in atts if a.status != 'Present'])
    attendance_percentage = int((present_count / total_attendance * 100)) if total_attendance > 0 else 0
    
    # Calculate attendance by subject
    attendance_by_subject = {}
    for att in atts:
        if att.subject not in attendance_by_subject:
            attendance_by_subject[att.subject] = {'total': 0, 'present': 0, 'absent': 0, 'percentage': 0}
        attendance_by_subject[att.subject]['total'] += 1
        if att.status == 'Present':
            attendance_by_subject[att.subject]['present'] += 1
        else:
            attendance_by_subject[att.subject]['absent'] += 1
    
    # Calculate percentage for each subject
    for subject in attendance_by_subject:
        data = attendance_by_subject[subject]
        data['percentage'] = int((data['present'] / data['total'] * 100)) if data['total'] > 0 else 0
    
    return render_template('student_dashboard.html', 
                         user=user, 
                         attendance=atts,
                         total_attendance=total_attendance,
                         present_count=present_count,
                         absent_count=absent_count,
                         attendance_percentage=attendance_percentage,
                         attendance_by_subject=attendance_by_subject)

# serve face images
@app.route('/face_data/<path:filename>')
def face_file(filename):
    return send_from_directory(FACE_DIR, filename)

# Delete user (admin only)
@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    uid = session.get('user_id')
    admin = User.query.get(uid)
    if not admin or admin.role != 'admin':
        return jsonify({'ok': False, 'error': 'Unauthorized'})
    
    user = User.query.get(user_id)
    if user:
        # Don't allow deleting admin accounts
        if user.role == 'admin':
            return jsonify({'ok': False, 'error': 'Cannot delete admin users'})
        
        # Delete all attendance records for this user
        Attendance.query.filter_by(user_id=user_id).delete()
        
        # Delete user face data from filesystem
        user_folder = os.path.join(FACE_DIR, user.username)
        if os.path.exists(user_folder):
            import shutil
            shutil.rmtree(user_folder)
        
        # Record audit before deletion
        try:
            ea = EditAudit(actor_id=admin.id if admin else None, action='delete', target_type='user', target_id=user.id, details=f'deleted user {user.username}')
            db.session.add(ea)
            db.session.commit()
        except Exception:
            app.logger.exception('Audit failed for user delete')

        # Delete user from database
        db.session.delete(user)
        db.session.commit()
        
        # Rebuild encodings
        build_encodings_from_images()
        global ENC
        ENC = load_encodings()
        
        return jsonify({'ok': True, 'message': f'User {user.username} deleted successfully'})
    
    return jsonify({'ok': False, 'error': 'User not found'})

# ---------- init & run -------------
with app.app_context():
    db.create_all()
    # initial build encodings if not exist
    enc = load_encodings()
    if not enc['encodings']:
        build_encodings_from_images()
        ENC = load_encodings()

if __name__ == '__main__':
    # use socketio server (eventlet)
    # disable debug and use_reloader to prevent startup hangs
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, use_reloader=False)
