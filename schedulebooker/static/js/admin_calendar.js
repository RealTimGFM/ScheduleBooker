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
      const barberId = block.dataset.barberId || 'none';
      return {
        element: block,
        id: block.dataset.id,
        barberId: barberId,
        start: start,
        end: end,
        startMinutes: start.getHours() * 60 + start.getMinutes(),
        endMinutes: end.getHours() * 60 + end.getMinutes(),
      };
    }).filter(b => !isNaN(b.startMinutes) && !isNaN(b.endMinutes));

    // Sort by start time
    bookings.sort((a, b) => a.startMinutes - b.startMinutes);

    // Detect overlaps and assign columns
    const { columns, overflowIntervals } = assignColumns(bookings);

    // Generate stable barber colors
    const barberColors = {};
    const colorPalette = [
      '#ff6b6b', '#4ecdc4', '#45b7d1', '#f7b731',
      '#5f27cd', '#00d2d3', '#ff9ff3', '#54a0ff'
    ];

    bookings.forEach(b => {
      if (!barberColors[b.barberId]) {
        // Hash barber ID to get consistent color
        let hash = 0;
        for (let i = 0; i < b.barberId.length; i++) {
          hash = b.barberId.charCodeAt(i) + ((hash << 5) - hash);
        }
        barberColors[b.barberId] = colorPalette[Math.abs(hash) % colorPalette.length];
      }
    });

    // Track overflow indicators per time slot
    const overflowBySlot = {};

    // Position each block
    bookings.forEach((booking, idx) => {
      const { element, startMinutes, endMinutes, barberId } = booking;
      const col = columns[idx];

      // Calculate top position
      const startOffsetMinutes = startMinutes - (startHour * 60);
      const top = (startOffsetMinutes / 60) * slotHeight;

      // Calculate height
      const durationMinutes = endMinutes - startMinutes;
      const height = Math.max((durationMinutes / 60) * slotHeight, 40);

      // Apply barber color
      const color = barberColors[barberId] || '#cccccc';
      element.style.borderColor = color;
      element.style.background = `linear-gradient(135deg, ${color}22, ${color}44)`;

      // Apply positioning
      element.style.top = `${top}px`;
      element.style.height = `${height}px`;

      // Apply column layout via data attributes
      element.setAttribute("data-column", String(col.column));
      element.setAttribute("data-column-count", String(col.columnCount));

      // Hide if overflow (beyond 4th lane)
      if (col.column >= 4) {
        element.style.display = "none";
        // Track overflow for this time range
        const slotKey = Math.floor(startMinutes / 30);
        if (!overflowBySlot[slotKey]) {
          overflowBySlot[slotKey] = {
            count: 0,
            top,
            height,
            startMinutes
          };
        }
        overflowBySlot[slotKey].count++;
      } else {
        element.style.display = "block";
      }
    });

    // Add "+X" overflow indicators
    qsa(".overflow-indicator", container).forEach((el) => el.remove());

    // Add overflow indicators (one per overflow interval)
    overflowIntervals.forEach(({ startMinutes, endMinutes, count }) => {
      if (count <= 0) return;

      const top = ((startMinutes - startHour * 60) / 60) * slotHeight;
      const height = Math.max(((endMinutes - startMinutes) / 60) * slotHeight, 40);

      const indicator = document.createElement("div");
      indicator.className = "overflow-indicator";
      indicator.textContent = `+${count}`;
      indicator.style.top = `${top}px`;
      indicator.style.height = `${height}px`;
      indicator.title = `${count} more booking(s) overlapping`;

      container.appendChild(indicator);
    });
  }

  // Overlap detection and column assignment with max 4 lanes
  // Overlap detection and column assignment (supports real overflow)
  function assignColumns(bookings) {
    const columns = new Array(bookings.length);

    // Helper: overlap test
    function overlaps(a, b) {
      return a.startMinutes < b.endMinutes && a.endMinutes > b.startMinutes;
    }

    // 1) Build overlap groups, WITH MERGING
    // (Your current logic does not merge groups when a booking bridges two groups.)
    const groups = []; // each group: { indices: [] }

    bookings.forEach((booking, idx) => {
      const hitGroupIdxs = [];

      for (let gi = 0; gi < groups.length; gi++) {
        const g = groups[gi];
        if (g.indices.some((i) => overlaps(bookings[i], booking))) {
          hitGroupIdxs.push(gi);
        }
      }

      if (hitGroupIdxs.length === 0) {
        groups.push({ indices: [idx] });
        return;
      }

      // Merge all hit groups into the first hit group
      const base = groups[hitGroupIdxs[0]];
      base.indices.push(idx);

      // Merge remaining groups (remove from end to keep indexes valid)
      for (let k = hitGroupIdxs.length - 1; k >= 1; k--) {
        const gi = hitGroupIdxs[k];
        base.indices.push(...groups[gi].indices);
        groups.splice(gi, 1);
      }
    });

    // 2) For each group, assign lanes using a standard greedy lane scheduler
    const overflowIntervals = [];

    groups.forEach((g) => {
      const indices = Array.from(new Set(g.indices)); // de-dupe
      indices.sort((ia, ib) => {
        const a = bookings[ia], b = bookings[ib];
        return a.startMinutes - b.startMinutes || a.endMinutes - b.endMinutes;
      });

      // Lane assignment (unbounded lanes)
      const laneEnds = []; // laneEnds[lane] = endMinutes
      let maxLanes = 0;

      indices.forEach((i) => {
        const b = bookings[i];

        // Find first available lane
        let lane = -1;
        for (let l = 0; l < laneEnds.length; l++) {
          if (laneEnds[l] <= b.startMinutes) {
            lane = l;
            break;
          }
        }
        if (lane === -1) {
          lane = laneEnds.length;
          laneEnds.push(b.endMinutes);
        } else {
          laneEnds[lane] = b.endMinutes;
        }

        maxLanes = Math.max(maxLanes, laneEnds.length);

        columns[i] = {
          column: lane,        // may be >= 4
          columnCount: 0,      // set after
        };
      });

      const visibleCols = Math.min(maxLanes, 4);

      // Set columnCount for all bookings in group
      indices.forEach((i) => {
        columns[i].columnCount = visibleCols;
      });

      // 3) Compute precise time intervals where overlap > 4 (for +X)
      // Sweep line over start/end events to find overflow segments.
      const events = [];
      indices.forEach((i) => {
        const b = bookings[i];
        events.push([b.startMinutes, +1]);
        events.push([b.endMinutes, -1]);
      });

      // End (-1) before start (+1) at same time
      events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

      let active = 0;
      let maxActive = 0;
      const intervals = [];

      let p = 0;
      while (p < events.length) {
        const t = events[p][0];

        // apply all deltas at time t
        while (p < events.length && events[p][0] === t) {
          active += events[p][1];
          maxActive = Math.max(maxActive, active);
          p++;
        }

        if (p >= events.length) break;

        const nextT = events[p][0];
        if (active > 4 && nextT > t) {
          intervals.push([t, nextT]);
        }
      }

      // Merge adjacent/overlapping intervals
      intervals.sort((a, b) => a[0] - b[0]);
      const merged = [];
      intervals.forEach(([s, e]) => {
        if (!merged.length || s > merged[merged.length - 1][1]) {
          merged.push([s, e]);
        } else {
          merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], e);
        }
      });

      const hiddenCount = Math.max(0, maxActive - 4);
      merged.forEach(([s, e]) => {
        overflowIntervals.push({ startMinutes: s, endMinutes: e, count: hiddenCount });
      });
    });

    return { columns, overflowIntervals };
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
        if (e.target !== slot) return;
        const time = slot.dataset.time || "";
        openModal("create", { time });
      });
    });

    // Booking block clicks (in calendar)
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

    // *** NEW: Booking card clicks (in sidebar list) ***
    qsa(".booking-card").forEach((card) => {
      card.style.cursor = "pointer";
      card.addEventListener("click", (e) => {
        // Find the booking ID from the card
        const bookingBlock = qsa(".booking-block").find(block => {
          return block.dataset.customer === card.querySelector('.booking-name')?.textContent;
        });

        if (bookingBlock) {
          const data = {
            id: bookingBlock.dataset.id,
            customer: bookingBlock.dataset.customer,
            phone: bookingBlock.dataset.phone,
            email: bookingBlock.dataset.email,
            serviceId: bookingBlock.dataset.serviceId,
            barberId: bookingBlock.dataset.barberId,
            date: bookingBlock.dataset.start.slice(0, 10),
            time: bookingBlock.dataset.start.slice(11, 16),
            notes: bookingBlock.dataset.notes,
          };
          openModal("edit", data);
        }
      });
    });

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