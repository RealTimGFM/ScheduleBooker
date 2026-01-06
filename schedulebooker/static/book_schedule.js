(function () {
    const root = document.querySelector(".booking-layout-wrapper");
    if (!root) return;

    const dateSelect = document.getElementById("date-select");
    const barberSelect = document.getElementById("barber-select");

    const serviceId = root.getAttribute("data-service-id");
    if (!serviceId) return;

    function refreshSchedule() {
        if (!dateSelect || !barberSelect) return;

        const date = dateSelect.value;
        const barberId = barberSelect.value;

        const url = new URL(window.location.href);
        url.searchParams.set("service_id", serviceId);
        if (date) url.searchParams.set("date", date);
        if (barberId) url.searchParams.set("barber_id", barberId);

        window.location.href = url.toString();
    }

    if (dateSelect) dateSelect.addEventListener("change", refreshSchedule);
    if (barberSelect) barberSelect.addEventListener("change", refreshSchedule);
})();
