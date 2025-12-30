// schedulebooker/static/js/admin_calendar.js
// Handles: Day/Week/Month view switching, date navigation, "now" indicator, and booking modal.

(function () {
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function setActiveView(viewKey) {
    const views = {
      day: qs("#day-view"),
      week: qs("#week-view"),
      month: qs("#month-view"),
    };
    const btns = {
      day: qs("#day-view-btn"),
      week: qs("#week-view-btn"),
      month: qs("#month-view-btn"),
    };

    Object.keys(views).forEach((k) => {
      if (views[k]) views[k].classList.toggle("active", k === viewKey);
    });
    Object.keys(btns).forEach((k) => {
      if (btns[k]) btns[k].classList.toggle("active", k === viewKey);
    });

    const now = qs("#now-indicator");
    if (now) now.style.display = viewKey === "day" ? "flex" : "none";

    updateNowIndicator();
  }

  function updateNowIndicator() {
    const dayView = qs("#day-view");
    const now = qs("#now-indicator");
    const dateInput = qs("#admin-date");
    const dayCal = qs(".day-calendar");
    if (!dayView || !now || !dateInput || !dayCal) return;

    if (!dayView.classList.contains("active")) {
      now.style.display = "none";
      return;
    }

    const today = new Date();
    const todayStr = today.toISOString().slice(0, 10);
    if (dateInput.value && dateInput.value !== todayStr) {
      now.style.display = "none";
      return;
    }

    const startHour = parseInt(dayView.dataset.startHour || "0", 10);
    const slots = qsa(".day-calendar .time-slot");
    if (slots.length === 0) return;

    const slotHeight = slots[0].getBoundingClientRect().height || 60;
    const hours = today.getHours();
    const minutes = today.getMinutes();

    const topPx = ((hours - startHour) + minutes / 60) * slotHeight;
    const maxTop = Math.max(0, dayCal.scrollHeight - 2);

    now.style.display = "flex";
    now.style.top = `${Math.max(0, Math.min(topPx, maxTop))}px`;
  }

  function setupDateNavigation() {
    const dateInput = qs("#admin-date");
    if (!dateInput) return;

    dateInput.addEventListener("change", () => {
      const val = dateInput.value;
      const url = new URL(window.location.href);
      url.searchParams.set("date", val);
      window.location.href = url.toString();
    });
  }

  function setupModal() {
    const modal = qs("#booking-modal");
    const openBtn = qs("#open-booking-modal");
    if (!modal || !openBtn) return;

    const closeEls = qsa("[data-modal-close]");
    const adminDate = qs("#admin-date");
    const formDate = qs("#booking-date");
    const formTime = qs("#booking-time");

    function openModal(prefillTime) {
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");

      if (formDate && adminDate && adminDate.value) formDate.value = adminDate.value;
      if (formTime && prefillTime) formTime.value = prefillTime;

      const nameField = qs("#booking-customer-name");
      if (nameField) nameField.focus();
    }

    function closeModal() {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("modal-open");
    }

    openBtn.addEventListener("click", () => openModal());

    closeEls.forEach((el) => el.addEventListener("click", closeModal));

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
    });

    qsa(".time-slot").forEach((slot) => {
      slot.addEventListener("click", () => {
        const t = slot.dataset.time || "";
        openModal(t);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    qs("#day-view-btn")?.addEventListener("click", () => setActiveView("day"));
    qs("#week-view-btn")?.addEventListener("click", () => setActiveView("week"));
    qs("#month-view-btn")?.addEventListener("click", () => setActiveView("month"));

    setupDateNavigation();
    setupModal();

    // Month cells: click a date to jump to that day
    qsa(".date-cell[data-date]").forEach((cell) => {
      cell.addEventListener("click", () => {
        const d = cell.dataset.date;
        if (!d) return;
        const url = new URL(window.location.href);
        url.searchParams.set("date", d);
        window.location.href = url.toString();
      });
    });

    updateNowIndicator();
    setInterval(updateNowIndicator, 60 * 1000);
  });
})();
