document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector(".booking-layout-wrapper");
    if (!root) return;

    // Prefer data-service-id, fallback to the hidden input inside the time form
    const serviceId =
        root.dataset.serviceId ||
        document.querySelector('#time-form input[name="service_id"]')?.value;

    if (!serviceId) return;

    const dateEl = document.getElementById("date-select");
    const barberEl = document.getElementById("barber-select");
    if (!dateEl || !barberEl) return;

    const refreshSchedule = () => {
        const url = new URL(window.location.href);

        url.searchParams.set("service_id", serviceId);

        if (dateEl.value) url.searchParams.set("date", dateEl.value);
        else url.searchParams.delete("date");

        if (barberEl.value) url.searchParams.set("barber_id", barberEl.value);
        else url.searchParams.delete("barber_id");

        // Critical: changing date/barber must reset the selected time (“hour”)
        url.searchParams.delete("time");

        if (url.toString() === window.location.href) return;
        window.location.href = url.toString();
    };

    // Date inputs can be inconsistent across browsers; listen to both
    dateEl.addEventListener("change", refreshSchedule);
    dateEl.addEventListener("input", refreshSchedule);
    barberEl.addEventListener("change", refreshSchedule);
});
