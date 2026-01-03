## Verification Checklist

### Manual Testing Steps:

**1. Initial Login with Legacy Password:**
```
1. Visit http://127.0.0.1:5000/admin/login
2. Username: T
3. Password: 1
4. Should succeed and redirect to calendar
```

**2. Access Settings:**
```
1. Click the ⚙️ icon in navbar (next to "Admin logout")
2. Should see Settings page with three cards:
   - Profile Information
   - Change Password
   - Forgot Password info
```

**3. Update Profile (requires current password):**
```
1. Change username to: TestAdmin
2. Add email: admin@test.com
3. Add phone: 5141234567
4. Enter current password: 1
5. Click "Save Profile"
6. Should show success message
7. Verify changes persisted (refresh page)
```

**4. Change Password (enforce 8+ chars):**
```
1. Current password: 1
2. New password: 12345 (too short)
3. Should show error: "Password must be at least 8 characters"
4. Try again with: TestPass123
5. Confirm: TestPass123
6. Should show success
7. Logout and login with new password to verify
```

**5. Forgot Password via Email:**
```
1. Logout
2. Visit /admin/forgot
3. Enter email: admin@test.com
4. Select "Email (link)"
5. Click "Send Reset"
6. Check console/terminal for logged reset link
7. Copy the token from the logged URL
8. Visit /admin/reset?token=<token>
9. Enter new password (8+ chars) twice
10. Should redirect to login with success message
11. Login with new password
```

**6. Forgot Password via SMS:**
```
1. Logout
2. Visit /admin/forgot
3. Enter phone: 5141234567
4. Select "SMS (6-digit code)"
5. Click "Send Reset"
6. Check console/terminal for logged 6-digit code
7. Visit /admin/reset
8. Enter the 6-digit code
9. Enter new password (8+ chars) twice
10. Should redirect to login with success message
11. Login with new password
```

**7. Token Expiry (15 minutes):**
```
1. Request a reset code
2. Wait 16 minutes (or manually change expires_at in DB to past)
3. Try to use the token
4. Should show: "Reset code/token has expired"
```

**8. Token Single-Use:**
```
1. Request a reset code
2. Use it successfully to reset password
3. Try to use the same token again
4. Should show: "Invalid or already used reset code/token"
```

**9. Rate Limiting (60 second cooldown):**
```
1. Request a reset via email
2. Immediately try to request another
3. Should show: "Please wait X seconds before requesting another reset"
4. Wait 60 seconds
5. Should allow another request
```

**10. Max Attempts (5 tries):**
```
1. Request a reset code
2. Enter wrong code 5 times on /admin/reset
3. 6th attempt should show: "Too many attempts. Please request a new reset code/token"
```

**11. Security - Profile Changes Require Password:**
```
1. Try to change username without entering current password
2. Should show error
3. Try with wrong current password
4. Should show: "Current password is incorrect"