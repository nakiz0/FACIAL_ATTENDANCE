# 📧 Email & Password Reset Setup Guide

## Problem: Email Not Working?

If you click "Forgot password?" but don't receive emails, it's because:

1. **Your `.env` has placeholder values** (not real credentials)
2. **SMTP server not configured correctly**

---

## Solution: Configure Real Email

### **Option A: Using Gmail (Recommended)**

1. **Enable 2-Factor Authentication** on your Google account
2. **Generate App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Windows Computer"
   - Google gives you a **16-character password**

3. **Update `.env`:**
   ```
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-16-char-app-password
   MAIL_DEFAULT_SENDER=your-email@gmail.com
   SECRET_KEY=your-secure-secret-key
   ```

4. **Restart the app:** `python app.py`

---

### **Option B: Using Outlook/Office365**

```
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USERNAME=your-email@outlook.com
MAIL_PASSWORD=your-password
MAIL_DEFAULT_SENDER=your-email@outlook.com
```

---

### **Option C: Using SendGrid (Free Tier Available)**

1. Sign up at https://sendgrid.com (free tier: 100 emails/day)
2. Get your API key from Dashboard
3. Update `.env`:
   ```
   MAIL_SERVER=smtp.sendgrid.net
   MAIL_PORT=587
   MAIL_USERNAME=apikey
   MAIL_PASSWORD=SG.your-api-key-here
   MAIL_DEFAULT_SENDER=noreply@yourdomain.com
   ```

---

## How to Test Email

### **From Admin Panel:**
1. Login as admin
2. Go to "Manage Users" section
3. Click **🔑 Reset** button next to any user
4. Enter a new password
5. Check terminal for `✅ Password for user reset to: ...`

### **Manually Send Test Email:**
1. Open browser and go to:
   ```
   http://localhost:5000/admin/test_email/username
   ```
   (Replace `username` with actual username)

2. Check terminal output:
   - ✅ `Reset email sent to email@example.com` = Working!
   - ❌ `Email send failed: ...` = Check credentials

---

## Admin Features Added

### **🔑 Reset User Password:**
- Click **Reset** button in "Manage Users"
- Enter new password (min 4 chars)
- User can login with new password immediately

### **🗑️ Delete User:**
- Click **Delete** button
- Removes user account, all attendance records, and face data

### **📧 Send Test Email:**
- Use `/admin/test_email/<username>` route
- Helps debug SMTP config

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No email received | Check `.env` credentials are correct |
| "Email send failed" error | Try using Gmail app password instead |
| "Only one usage of each socket address" | Port 5000 in use; run `taskkill /PID <pid> /F` |
| App crashes on startup | Check `itsdangerous` is installed: `pip install itsdangerous==2.1.2` |

---

## Important Notes

⚠️ **Passwords are stored PLAINTEXT** in the database.
- For production: Use `werkzeug.security.generate_password_hash()` and `check_password_hash()`
- Consider adding: Implement password hashing ASAP before deploying

✅ **Reset tokens expire in 1 hour** (configurable in code)

✅ **Email addresses required** for password reset to work

---

## Next Steps

1. Update `.env` with real email credentials
2. Restart app: `Ctrl+C` then `python app.py`
3. Test by clicking "Forgot password?" on login page
4. Check terminal for success/error messages
