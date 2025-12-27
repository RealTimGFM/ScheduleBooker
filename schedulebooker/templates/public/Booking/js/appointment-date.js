const API = "http://localhost:3000/api/appointment";

const datePicker = document.getElementById("datePicker");
const timeGrid = document.getElementById("timeGrid");
const barberList = document.getElementById("barberList");

const summaryDate = document.getElementById("summaryDate");
const summaryTime = document.getElementById("summaryTime");
const summaryBarber = document.getElementById("summaryBarber");
const nextBtn = document.getElementById("nextBtn");

let selected = {
  date: null,
  time: null,
  barber: null
};

/* Disable past dates */
const today = new Date().toISOString().split("T")[0];
datePicker.min = today;

/* DATE CHANGE */
datePicker.addEventListener("change", async () => {
  selected.date = datePicker.value;
  summaryDate.textContent = selected.date;

  const res = await fetch(`${API}/times?date=${selected.date}`);
  const times = await res.json();

  renderTimes(times);
});

/* NEXT AVAILABLE */
document.getElementById("nextAvailable").onclick = async () => {
  const res = await fetch(`${API}/next-available?from=${datePicker.value}`);
  const data = await res.json();

  datePicker.value = data.date;
  summaryDate.textContent = data.date;
  renderTimes(data.times);
};

/* RENDER TIMES */
function renderTimes(times) {
  timeGrid.innerHTML = "";

  if (times.length === 0) {
    timeGrid.innerHTML = "<p>No time available</p>";
    return;
  }

  times.forEach(t => {
    const btn = document.createElement("button");
    btn.textContent = t;
    btn.onclick = () => selectTime(t, btn);
    timeGrid.appendChild(btn);
  });
}

async function selectTime(time, btn) {
  selected.time = time;
  summaryTime.textContent = time;

  document.querySelectorAll("#timeGrid button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");

  const res = await fetch(`${API}/barbers?date=${selected.date}&time=${time}`);
  const barbers = await res.json();

  renderBarbers(barbers);
}

/* BARBERS */
function renderBarbers(barbers) {
  barberList.innerHTML = "";

  barbers.forEach(b => {
    const div = document.createElement("div");
    div.textContent = b.name;
    div.className = "barber";

    if (!b.available) {
      div.classList.add("disabled");
    } else {
      div.onclick = () => selectBarber(b, div);
    }

    barberList.appendChild(div);
  });
}

function selectBarber(barber, div) {
  selected.barber = barber.name;
  summaryBarber.textContent = barber.name;

  document.querySelectorAll(".barber").forEach(b => b.classList.remove("active"));
  div.classList.add("active");

  nextBtn.disabled = false;
}

       const toggle = document.getElementById("theme-toggle");

        const savedTheme = localStorage.getItem("theme");
        if (savedTheme) {
            document.body.setAttribute("data-theme", savedTheme);
            toggle.textContent = savedTheme === "dark" ? "☀️" : "🌙";
        }

        toggle.addEventListener("click", () => {
            const isDark = document.body.getAttribute("data-theme") === "dark";
            document.body.setAttribute("data-theme", isDark ? "light" : "dark");
            localStorage.setItem("theme", isDark ? "light" : "dark");
            toggle.textContent = isDark ? "🌙" : "☀️";
        });

        /* ARROW SCROLL */
        const galleryWrapper = document.querySelector('.gallery-wrapper');
        document.querySelector('.gallery-arrow.left').onclick = () => {
            galleryWrapper.scrollBy({ left: -300, behavior: 'smooth' });
        };
        document.querySelector('.gallery-arrow.right').onclick = () => {
            galleryWrapper.scrollBy({ left: 300, behavior: 'smooth' });
        };

        /* LIGHTBOX */
        const lightbox = document.getElementById('lightbox');
        const lightboxImg = document.querySelector('.lightbox-img');
        const closeBtn = document.querySelector('.lightbox-close');

        document.querySelectorAll('.gallery-item').forEach(item => {
            item.addEventListener('click', () => {
                const img = item.getAttribute('data-img');
                lightboxImg.src = img;
                lightbox.classList.add('show');
            });
        });

        closeBtn.onclick = () => {
            lightbox.classList.remove('show');
        };

        lightbox.onclick = (e) => {
            if (e.target === lightbox) {
                lightbox.classList.remove('show');
            }
        };
