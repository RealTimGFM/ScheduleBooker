(function () {
    function formatMoney(value) {
        return new Intl.NumberFormat("en-CA", {
            style: "currency",
            currency: "CAD",
            minimumFractionDigits: 2,
        }).format(Number(value || 0));
    }

    function escapeHtml(text) {
        return String(text ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function renderEmpty(root, message) {
        if (!root) return;
        root.innerHTML = `<div class="income-empty">${escapeHtml(message)}</div>`;
    }

    function buildSvg(width, height, content) {
        return `
            <svg class="income-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                ${content}
            </svg>
        `;
    }

    function renderRevenueTrend(root, points) {
        if (!root) return;
        if (!Array.isArray(points) || points.length === 0) {
            renderEmpty(root, "No revenue data yet.");
            return;
        }

        const values = points.map((p) => Number(p.income || 0));
        const maxValue = Math.max(...values, 1);

        const width = 760;
        const height = 280;
        const left = 48;
        const right = 18;
        const top = 18;
        const bottom = 48;
        const chartW = width - left - right;
        const chartH = height - top - bottom;

        const stepX = points.length > 1 ? chartW / (points.length - 1) : chartW;
        const linePoints = points.map((point, idx) => {
            const x = left + idx * stepX;
            const y = top + chartH - (Number(point.income || 0) / maxValue) * chartH;
            return { x, y, label: point.label, value: Number(point.income || 0) };
        });

        const polyline = linePoints.map((p) => `${p.x},${p.y}`).join(" ");
        const areaPoints = [
            `${left},${top + chartH}`,
            ...linePoints.map((p) => `${p.x},${p.y}`),
            `${left + chartW},${top + chartH}`,
        ].join(" ");

        const gridLines = Array.from({ length: 5 }, (_, i) => {
            const y = top + (chartH / 4) * i;
            const value = maxValue - (maxValue / 4) * i;
            return `
                <line x1="${left}" y1="${y}" x2="${left + chartW}" y2="${y}" class="income-grid-line" />
                <text x="${left - 8}" y="${y + 4}" text-anchor="end" class="income-axis-label">
                    $${value.toFixed(0)}
                </text>
            `;
        }).join("");

        const every = points.length > 16 ? Math.ceil(points.length / 8) : 1;
        const xLabels = linePoints.map((p, idx) => {
            if (idx % every !== 0 && idx !== points.length - 1) return "";
            return `
                <text x="${p.x}" y="${height - 14}" text-anchor="middle" class="income-axis-label">
                    ${escapeHtml(p.label)}
                </text>
            `;
        }).join("");

        const dots = linePoints.map((p) => `
            <circle cx="${p.x}" cy="${p.y}" r="4" class="income-line-dot">
                <title>${escapeHtml(p.label)}: ${formatMoney(p.value)}</title>
            </circle>
        `).join("");

        root.innerHTML = buildSvg(
            width,
            height,
            `
                ${gridLines}
                <polygon points="${areaPoints}" class="income-area-fill"></polygon>
                <polyline points="${polyline}" class="income-line-path"></polyline>
                ${dots}
                ${xLabels}
            `
        );
    }

    function renderActivityChart(root, points) {
        if (!root) return;
        if (!Array.isArray(points) || points.length === 0) {
            renderEmpty(root, "No booking activity data yet.");
            return;
        }

        const completedValues = points.map((p) => Number(p.bookings || 0));
        const cancelledValues = points.map((p) => Number(p.cancellations || 0));
        const maxValue = Math.max(...completedValues, ...cancelledValues, 1);

        const width = 760;
        const height = 280;
        const left = 48;
        const right = 18;
        const top = 18;
        const bottom = 48;
        const chartW = width - left - right;
        const chartH = height - top - bottom;

        const groupWidth = chartW / Math.max(points.length, 1);
        const barWidth = Math.max(6, Math.min(18, groupWidth * 0.28));

        const gridLines = Array.from({ length: 5 }, (_, i) => {
            const y = top + (chartH / 4) * i;
            const value = Math.round(maxValue - (maxValue / 4) * i);
            return `
                <line x1="${left}" y1="${y}" x2="${left + chartW}" y2="${y}" class="income-grid-line" />
                <text x="${left - 8}" y="${y + 4}" text-anchor="end" class="income-axis-label">
                    ${value}
                </text>
            `;
        }).join("");

        const every = points.length > 16 ? Math.ceil(points.length / 8) : 1;

        const bars = points.map((point, idx) => {
            const groupX = left + idx * groupWidth + groupWidth / 2;
            const bookingsH = (Number(point.bookings || 0) / maxValue) * chartH;
            const cancellationsH = (Number(point.cancellations || 0) / maxValue) * chartH;

            const bookingsX = groupX - barWidth - 2;
            const cancellationsX = groupX + 2;
            const bookingsY = top + chartH - bookingsH;
            const cancellationsY = top + chartH - cancellationsH;

            const label = (idx % every === 0 || idx === points.length - 1)
                ? `
                    <text x="${groupX}" y="${height - 14}" text-anchor="middle" class="income-axis-label">
                        ${escapeHtml(point.label)}
                    </text>
                  `
                : "";

            return `
                <rect x="${bookingsX}" y="${bookingsY}" width="${barWidth}" height="${bookingsH}" class="income-bar income-bar-completed">
                    <title>${escapeHtml(point.label)} completed: ${Number(point.bookings || 0)}</title>
                </rect>
                <rect x="${cancellationsX}" y="${cancellationsY}" width="${barWidth}" height="${cancellationsH}" class="income-bar income-bar-cancelled">
                    <title>${escapeHtml(point.label)} cancelled: ${Number(point.cancellations || 0)}</title>
                </rect>
                ${label}
            `;
        }).join("");

        root.innerHTML = `
            ${buildSvg(width, height, `${gridLines}${bars}`)}
            <div class="income-legend">
                <span><i class="income-legend-swatch income-legend-completed"></i> Completed</span>
                <span><i class="income-legend-swatch income-legend-cancelled"></i> Cancelled</span>
            </div>
        `;
    }

    function renderHorizontalBars(root, items, config) {
        if (!root) return;

        const labelKey = config.labelKey;
        const valueKey = config.valueKey;
        const countKey = config.countKey;
        const topItems = Array.isArray(items) ? items.slice(0, 8) : [];

        if (topItems.length === 0) {
            renderEmpty(root, "No data in this period yet.");
            return;
        }

        const maxValue = Math.max(...topItems.map((item) => Number(item[valueKey] || 0)), 1);

        root.innerHTML = `
            <div class="income-bar-list">
                ${topItems.map((item) => {
                    const label = item[labelKey] || "Unknown";
                    const value = Number(item[valueKey] || 0);
                    const count = Number(item[countKey] || 0);
                    const pct = (value / maxValue) * 100;

                    return `
                        <div class="income-bar-item">
                            <div class="income-bar-item-head">
                                <span class="income-bar-item-label">${escapeHtml(label)}</span>
                                <span class="income-bar-item-value">${formatMoney(value)}</span>
                            </div>
                            <div class="income-bar-track">
                                <div class="income-bar-fill" style="width:${pct.toFixed(2)}%"></div>
                            </div>
                            <div class="income-bar-item-meta">${count} completed booking${count === 1 ? "" : "s"}</div>
                        </div>
                    `;
                }).join("")}
            </div>
        `;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const dataEl = document.getElementById("income-chart-data");
        if (!dataEl) return;

        let payload = {};
        try {
            payload = JSON.parse(dataEl.textContent || "{}");
        } catch (err) {
            console.error("Could not parse income chart data:", err);
            return;
        }

        renderRevenueTrend(
            document.getElementById("income-revenue-chart"),
            payload.trend_points || []
        );

        renderActivityChart(
            document.getElementById("income-activity-chart"),
            payload.trend_points || []
        );

        renderHorizontalBars(
            document.getElementById("income-services-chart"),
            payload.services_breakdown || [],
            {
                labelKey: "service_name",
                valueKey: "revenue",
                countKey: "bookings_count",
            }
        );

        renderHorizontalBars(
            document.getElementById("income-barbers-chart"),
            payload.barbers_breakdown || [],
            {
                labelKey: "barber_name",
                valueKey: "revenue",
                countKey: "bookings_count",
            }
        );
    });
})();