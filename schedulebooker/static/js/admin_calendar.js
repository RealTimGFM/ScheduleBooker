// schedulebooker/static/js/admin_calendar.js
// Handles: Day/Week/Month view switching, date navigation, "now" indicator, booking blocks, and modal.

(function () {
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ============ VIEW SWITCHING ============
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

    if (viewKey === "day") {
      updateNowIndicator();
      positionBookingBlocks();
    }
  }

  // ============ NOW INDICATOR ============
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

  // ============ DATE NAVIGATION ============
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

  // ============ BOOKING BLOCKS POSITIONING ============
  function positionBookingBlocks() {
    const dayView = qs("#day-view");
    const container = qs("#booking-blocks");
    if (!dayView || !container || !dayView.classList.contains("active")) return;

    const startHour = parseInt(dayView.dataset.startHour || "0", 10);
    const slots = qsa(".day-calendar .time-slot");
    if (slots.length === 0) return;

    const slotHeight = slots[0].getBoundingClientRect().height || 60;
    const blocks = qsa(".booking-block", container);

    // Parse booking data
    const bookings = blocks.map(block => {
      const start = new Date(block.dataset.start);
      const end = new Date(block.dataset.end);
      return {
        element: block,
        id: block.dataset.id,
        start: start,
        end: end,
        startMinutes: start.getHours() * 60 + start.getMinutes(),
        endMinutes: end.getHours() * 60 + end.getMinutes(),
      };
    }).filter(b => !isNaN(b.startMinutes) && !isNaN(b.endMinutes));

    // Sort by start time
    bookings.sort((a, b) => a.startMinutes - b.startMinutes);

    // Detect overlaps and assign columns
    const columns = assignColumns(bookings);

    // Position each block
    bookings.forEach((booking, idx) => {
      const { element, startMinutes, endMinutes } = booking;
      const { column, columnCount } = columns[idx];

      // Calculate top position
      const startOffsetMinutes = startMinutes - (startHour * 60);
      const top = (startOffsetMinutes / 60) * slotHeight;

      // Calculate height
      const durationMinutes = endMinutes - startMinutes;
      const height = Math.max((durationMinutes / 60) * slotHeight, 40); // min 40px

      // Apply positioning
      element.style.top = `${top}px`;
      element.style.height = `${height}px`;
      element.style.display = "block";

      // Apply column layout
      element.dataset.column = column;
      element.dataset.columnCount = Math.min(columnCount, 4); // Cap at 4
    });
  }

  // Overlap detection and column assignment
  function assignColumns(bookings) {
    const columns = [];
    const groups = [];

    bookings.forEach((booking, idx) => {
      // Find overlapping group
      let group = null;
      for (const g of groups) {
        if (g.some(i => overlaps(bookings[i], booking))) {
          group = g;
          break;
        }
      }

      if (!group) {
        // Start new group
        group = [idx];
        groups.push(group);
      } else {
        group.push(idx);
      }

      // Assign to first available column in group
      const usedColumns = group.slice(0, -1).map(i => columns[i].column);
      let column = 0;
      while (usedColumns.includes(column)) column++;

      columns[idx] = {
        column: Math.min(column, 3), // Cap at column 3 (4 columns max)
        columnCount: 0 // Will be set after
      };
    });

    // Set column counts for each group
    groups.forEach(group => {
      const maxColumn = Math.max(...group.map(i => columns[i].column));
      const columnCount = Math.min(maxColumn + 1, 4); // Cap at 4
      group.forEach(i => {
        columns[i].columnCount = columnCount;
      });
    });

    return columns;
  }

  function overlaps(a, b) {
    return a.startMinutes < b.endMinutes && a.endMinutes > b.startMinutes;
  }

  // ============ MODAL MANAGEMENT ============
  let modalMode = "create"; // "create" or "edit"
  let currentBookingId = null;

  function openModal(mode = "create", data = {}) {
    const modal = qs("#booking-modal");
    const form = qs("#booking-form");
    const title = qs("#booking-modal-title");
    const submitBtn = qs("#modal-submit-btn");
    const deleteBtn = qs("#modal-delete-btn");

    if (!modal || !form) return;

    modalMode = mode;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");

    if (mode === "create") {
      title.textContent = "Create booking";
      submitBtn.textContent = "Create";
      deleteBtn.style.display = "none";
      form.action = form.dataset.createAction || "/admin/book";
      currentBookingId = null;

      // Reset form
      form.reset();

      // Prefill date/time if provided
      const adminDate = qs("#admin-date");
      if (adminDate && adminDate.value) {
        qs("#booking-date").value = adminDate.value;
      }
      if (data.time) {
        qs("#booking-time").value = data.time;
      }
    } else if (mode === "edit") {
      title.textContent = "Edit booking";
      submitBtn.textContent = "Save";
      deleteBtn.style.display = "inline-flex";
      currentBookingId = data.id;
      form.action = `/admin/book/${data.id}/edit`;

      // Populate form
      qs("#booking-customer-name").value = data.customer || "";
      qs("#booking-phone").value = data.phone || "";
      qs("#booking-email").value = data.email || "";
      qs("#booking-service").value = data.serviceId || "";
      qs("#booking-barber").value = data.barberId || "";
      qs("#booking-date").value = data.date || "";
      qs("#booking-time").value = data.time || "";
      qs("#booking-notes").value = data.notes || "";
    }

    // Focus first input
    const nameField = qs("#booking-customer-name");
    if (nameField) setTimeout(() => nameField.focus(), 100);
  }

  function closeModal() {
    const modal = qs("#booking-modal");
    if (!modal) return;

    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    modalMode = "create";
    currentBookingId = null;
  }

  function setupModal() {
    const modal = qs("#booking-modal");
    const openBtn = qs("#open-booking-modal");
    const deleteBtn = qs("#modal-delete-btn");
    if (!modal || !openBtn) return;

    const closeEls = qsa("[data-modal-close]");

    openBtn.addEventListener("click", () => openModal("create"));

    closeEls.forEach((el) => el.addEventListener("click", closeModal));

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
    });

    // Delete button
    if (deleteBtn) {
      deleteBtn.addEventListener("click", () => {
        if (!currentBookingId) return;
        if (!confirm("Delete this booking?")) return;

        const form = document.createElement("form");
        form.method = "POST";
        form.action = `/admin/book/${currentBookingId}/delete`;
        document.body.appendChild(form);
        form.submit();
      });
    }
  }

  // ============ CLICK HANDLERS ============
  function setupClickHandlers() {
    // Time slot clicks (empty space)
    qsa(".time-slot").forEach((slot) => {
      slot.addEventListener("click", (e) => {
        // Only trigger if clicking the slot itself, not a booking block
        if (e.target !== slot) return;

        const time = slot.dataset.time || "";
        openModal("create", { time });
      });
    });

    // Booking block clicks
    const container = qs("#booking-blocks");
    if (container) {
      container.addEventListener("click", (e) => {
        const block = e.target.closest(".booking-block");
        if (!block) return;

        const data = {
          id: block.dataset.id,
          customer: block.dataset.customer,
          phone: block.dataset.phone,
          email: block.dataset.email,
          serviceId: block.dataset.serviceId,
          barberId: block.dataset.barberId,
          date: block.dataset.start.slice(0, 10),
          time: block.dataset.start.slice(11, 16),
          notes: block.dataset.notes,
        };

        openModal("edit", data);
      });
    }

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
  }

  // ============ INITIALIZATION ============
  document.addEventListener("DOMContentLoaded", () => {
    // View switching
    qs("#day-view-btn")?.addEventListener("click", () => setActiveView("day"));
    qs("#week-view-btn")?.addEventListener("click", () => setActiveView("week"));
    qs("#month-view-btn")?.addEventListener("click", () => setActiveView("month"));

    setupDateNavigation();
    setupModal();
    setupClickHandlers();

    // Initial positioning
    positionBookingBlocks();
    updateNowIndicator();

    // Refresh positioning on window resize
    let resizeTimeout;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        positionBookingBlocks();
        updateNowIndicator();
      }, 150);
    });

    // Update now indicator every minute
    setInterval(updateNowIndicator, 60 * 1000);
  });
})();