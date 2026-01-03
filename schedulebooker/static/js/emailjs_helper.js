// EmailJS helper for password reset emails
// Setup: 
// 1. Create account at https://www.emailjs.com/
// 2. Add your email service (Gmail, Outlook, etc.)
// 3. Create email template with variables: {{to_email}}, {{to_name}}, {{reset_url}}
// 4. Replace PUBLIC_KEY, SERVICE_ID, TEMPLATE_ID below

const EMAILJS_CONFIG = {
    PUBLIC_KEY: 'YOUR_EMAILJS_PUBLIC_KEY',  // Get from EmailJS dashboard
    SERVICE_ID: 'YOUR_SERVICE_ID',           // Your email service ID
    TEMPLATE_ID: 'YOUR_TEMPLATE_ID'          // Your template ID
};

async function sendPasswordResetEmail(toEmail, toName, resetUrl) {
    try {
        // Initialize EmailJS (only needed once)
        if (!window.emailjs) {
            console.error('EmailJS library not loaded');
            return false;
        }
        
        emailjs.init(EMAILJS_CONFIG.PUBLIC_KEY);
        
        // Send email
        const response = await emailjs.send(
            EMAILJS_CONFIG.SERVICE_ID,
            EMAILJS_CONFIG.TEMPLATE_ID,
            {
                to_email: toEmail,
                to_name: toName,
                reset_url: resetUrl,
                subject: 'Password Reset Request - ScheduleBooker Admin'
            }
        );
        
        console.log('Email sent successfully:', response);
        return true;
    } catch (error) {
        console.error('Email send failed:', error);
        return false;
    }
}
/*
```

**EmailJS Template Example:**

Create a template in EmailJS dashboard with this content:
```
Subject: Password Reset Request - ScheduleBooker Admin

Hello {{to_name}},

You requested a password reset for your ScheduleBooker admin account.

Click the link below to reset your password:
{{reset_url}}

This link expires in 15 minutes.

If you didn't request this, please ignore this email.

Best regards,
ScheduleBooker Team
*/