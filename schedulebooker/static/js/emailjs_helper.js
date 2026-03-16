// EmailJS helper for password reset emails

(function () {
    let isInitialized = false;

    function getEmailJsConfig() {
        const cfg = window.EMAILJS_CONFIG || {};
        return {
            publicKey: (cfg.publicKey || "").trim(),
            serviceId: (cfg.serviceId || "").trim(),
            templateId: (cfg.templateId || "").trim(),
        };
    }

    function ensureEmailJsReady() {
        const cfg = getEmailJsConfig();

        if (!window.emailjs) {
            return { ok: false, error: "EmailJS library not loaded." };
        }

        if (!cfg.publicKey || !cfg.serviceId || !cfg.templateId) {
            return { ok: false, error: "EmailJS config is missing." };
        }

        if (!isInitialized) {
            window.emailjs.init({
                publicKey: cfg.publicKey,
            });
            isInitialized = true;
        }

        return { ok: true, cfg };
    }

    async function sendPasswordResetEmail(toEmail, toName, resetUrl) {
        const ready = ensureEmailJsReady();
        if (!ready.ok) {
            console.error(ready.error);
            return { ok: false, error: ready.error };
        }

        try {
            console.log({
                to_email: toEmail,
                to_name: toName,
                reset_url: resetUrl,
                service_id: ready.cfg.serviceId,
                template_id: ready.cfg.templateId
            });
            const response = await window.emailjs.send(
                ready.cfg.serviceId,
                ready.cfg.templateId,
                {
                    to_email: toEmail,
                    to_name: toName,
                    reset_url: resetUrl,
                    subject: "Password Reset Request - ScheduleBooker Admin",
                }
            );

            console.log("Email sent successfully:", response);
            return { ok: true, response };
        } catch (error) {
            console.error("Email send failed:", error);
            return {
                ok: false,
                error: error?.text || error?.message || "Unknown EmailJS error.",
            };
        }
    }

    window.sendPasswordResetEmail = sendPasswordResetEmail;
})();