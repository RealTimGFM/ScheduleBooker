// Admin calendar UI behavior: view switching + "now" line placement.

(function () {
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

  function setActiveView(view) {
    const views = {
      day: qs('#day-view'),
      week: qs('#week-view'),
      month: qs('#month-view'),
    };
    Object.keys(views).forEach((k) => {
      if (!views[k]) return;
      views[k].classList.toggle('active-view', k === view);
    });

    const buttons = {
      day: qs('#day-view-btn'),
      week: qs('#week-view-btn'),
      month: qs('#month-view-btn'),
    };
    Object.keys(buttons).forEach((k) => {
      if (!buttons[k]) return;
      buttons[k].classList.toggle('active', k === view);
    });
  }

  function buildMonthGrid() {
    const container = qs('#month-calendar');
    if (!container) return;

    // Simple static 30-day grid (good enough for layout); backend month logic can be added later.
    container.innerHTML = '';
    for (let day = 1; day <= 30; day += 1) {
      const cell = document.createElement('div');
      cell.className = 'month-day';
      cell.textContent = String(day);
      // Add a few decorative dots so the UI matches the provided mockup.
      if (day % 5 === 0) {
        const dotWrap = document.createElement('div');
        dotWrap.className = 'booking-dots';
        for (let i = 0; i < 3; i += 1) {
          const dot = document.createElement('span');
          dot.className = 'dot';
          dotWrap.appendChild(dot);
        }
        cell.appendChild(dotWrap);
      }
      container.appendChild(cell);
    }
  }

  function updateNowIndicator() {
    const nowLine = qs('#now-indicator');
    const dayCal = qs('.day-calendar');
    if (!nowLine || !dayCal) return;

    const selected = qs('#admin-date');
    const selectedDate = selected ? selected.value : '';
    const today = new Date();
    const todayStr = today.toISOString().slice(0, 10);

    // Only show the "now" line when viewing today's date.
    if (selectedDate && selectedDate !== todayStr) {
      nowLine.style.display = 'none';
      return;
    }

    nowLine.style.display = 'block';

    const hours = today.getHours();
    const minutes = today.getMinutes();

    const slots = qsa('.day-calendar .time-slot');
    if (slots.length === 0) return;

    const slotHeight = slots[0].getBoundingClientRect().height;
    const topPx = (hours * slotHeight) + ((minutes / 60) * slotHeight);

    // Keep line inside the container.
    const maxTop = dayCal.scrollHeight - 2;
    nowLine.style.top = String(Math.max(0, Math.min(topPx, maxTop))) + 'px';
  }

  document.addEventListener('DOMContentLoaded', () => {
    const dayBtn = qs('#day-view-btn');
    const weekBtn = qs('#week-view-btn');
    const monthBtn = qs('#month-view-btn');

    if (dayBtn) dayBtn.addEventListener('click', () => setActiveView('day'));
    if (weekBtn) weekBtn.addEventListener('click', () => setActiveView('week'));
    if (monthBtn) monthBtn.addEventListener('click', () => setActiveView('month'));

    buildMonthGrid();
    updateNowIndicator();
    setInterval(updateNowIndicator, 60 * 1000);
  });
})();
