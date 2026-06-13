/**
 * Summer.GG — global JS
 * Theme toggle · weather widget · nav XP/streak/name
 */

// ── Theme ────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("gg-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcon(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("gg-theme", next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("theme-icon");
  if (!icon) return;
  icon.className = theme === "dark" ? "ti ti-sun" : "ti ti-moon";
}

// ── Weather widget ───────────────────────────────────────────
const WX_CODES = {
  0:"Clear", 1:"Mostly clear", 2:"Partly cloudy", 3:"Overcast",
  45:"Foggy", 48:"Icy fog", 51:"Light drizzle", 53:"Drizzle",
  55:"Heavy drizzle", 61:"Light rain", 63:"Rain", 65:"Heavy rain",
  71:"Light snow", 73:"Snow", 75:"Heavy snow", 77:"Snow grains",
  80:"Showers", 81:"Showers", 82:"Heavy showers",
  85:"Snow showers", 86:"Heavy snow showers",
  95:"Thunderstorm", 96:"Thunderstorm+hail", 99:"Thunderstorm+hail",
};
const WX_ICONS = {
  0:"ti-sun", 1:"ti-sun", 2:"ti-cloud", 3:"ti-cloud",
  45:"ti-mist", 48:"ti-mist", 51:"ti-cloud-rain", 53:"ti-cloud-rain",
  55:"ti-cloud-rain", 61:"ti-cloud-rain", 63:"ti-cloud-rain", 65:"ti-cloud-rain",
  71:"ti-snowflake", 73:"ti-snowflake", 75:"ti-snowflake", 77:"ti-snowflake",
  80:"ti-cloud-rain", 81:"ti-cloud-rain", 82:"ti-cloud-rain",
  85:"ti-snowflake", 86:"ti-snowflake",
  95:"ti-bolt", 96:"ti-bolt", 99:"ti-bolt",
};

async function loadWeather() {
  const textEl = document.getElementById("weather-text");
  const iconEl = document.getElementById("weather-icon");
  if (!textEl) return;

  // Show EST time immediately — no API needed
  updateClock();
  setInterval(updateClock, 60000);

  if (!navigator.geolocation) {
    textEl.textContent = getESTTime();
    return;
  }

  navigator.geolocation.getCurrentPosition(async (pos) => {
    const { latitude: lat, longitude: lon } = pos.coords;
    try {
      // Weather from Open-Meteo (free, no key)
      const wx = await fetch(
        `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
        `&current=temperature_2m,weather_code&temperature_unit=fahrenheit&timezone=auto`
      ).then(r => r.json());

      const temp = Math.round(wx.current.temperature_2m);
      const code = wx.current.weather_code;
      const desc = WX_CODES[code] || "—";
      const icon = WX_ICONS[code] || "ti-cloud";

      // City from Nominatim (free reverse geocode)
      const geo = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`
      ).then(r => r.json());
      const city = geo.address?.city || geo.address?.town || geo.address?.suburb || "";

      if (iconEl) iconEl.className = `ti ${icon}`;
      textEl.textContent = `${temp}°F · ${desc}${city ? " · " + city : ""} · ${getESTTime()}`;
    } catch(_) {
      textEl.textContent = getESTTime();
    }
  }, () => {
    // Geolocation denied — just show the clock
    textEl.textContent = getESTTime();
  });
}

function getESTTime() {
  return new Date().toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "numeric", minute: "2-digit", hour12: true
  }) + " ET";
}

function updateClock() {
  const el = document.getElementById("weather-text");
  if (!el || el.textContent.length > 10) return; // don't overwrite full weather
  el.textContent = getESTTime();
}

// ── Nav XP / streak / name ───────────────────────────────────
async function refreshNavStatus() {
  try {
    const res = await fetch("/xp/status");
    const d   = await res.json();

    const xpEl     = document.getElementById("nav-xp-val");
    const streakEl = document.getElementById("nav-streak-num");
    const greetEl  = document.getElementById("nav-greeting");

    if (xpEl)     xpEl.textContent     = (d.total_xp || 0).toLocaleString() + " XP";
    if (streakEl) streakEl.textContent  = d.streak?.current_streak ?? "—";
    if (greetEl && d.student_name) {
      greetEl.textContent = "Hi " + d.student_name + "!";
    }
    return d;
  } catch(_) {}
}

// ── Utility: POST JSON helper ────────────────────────────────
async function postJSON(url, body = {}) {
  const res = await fetch(url, {
    method:  "POST",
    headers: {"Content-Type": "application/json"},
    body:    JSON.stringify(body),
  });
  return res.json();
}

// ── Toast notification ───────────────────────────────────────
function showToast(message, type = "info") {
  const existing = document.getElementById("gg-toast");
  if (existing) existing.remove();
  const colors = {info:"#7F77DD", success:"#72C257", warning:"#F0A830", error:"#E06060"};
  const toast = document.createElement("div");
  toast.id = "gg-toast";
  toast.style.cssText = `
    position:fixed; bottom:1.5rem; left:50%; transform:translateX(-50%);
    background:${colors[type]||colors.info}; color:#fff;
    padding:10px 20px; border-radius:8px; font-size:14px; font-weight:500;
    box-shadow:0 4px 16px rgba(0,0,0,.4); z-index:9999;
    animation:toastUp .2s ease;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// ── Confetti burst ───────────────────────────────────────────
/**
 * fireConfetti(xp, originEl)
 * Spawns colored confetti bursting from originEl (or screen center).
 * Particle count scales with XP: 75 XP → ~30 pieces, 500 XP → ~80 pieces.
 */
function fireConfetti(xp, originEl) {
  const count  = Math.min(30 + Math.round(((xp || 100) / 500) * 60), 90);
  const colors = ["#7F77DD","#72C257","#F0A830","#E06060","#4FB6E8","#F06292","#FFD700","#A78BFA"];
  const shapes = ["■","●","▲","★","♦","✿"];

  let ox = window.innerWidth  / 2;
  let oy = window.innerHeight / 2;
  if (originEl) {
    const r = originEl.getBoundingClientRect();
    ox = r.left + r.width  / 2;
    oy = r.top  + r.height / 2;
  }

  for (let i = 0; i < count; i++) {
    const p     = document.createElement("span");
    const color = colors[i % colors.length];
    const shape = shapes[Math.floor(Math.random() * shapes.length)];
    const size  = 8 + Math.random() * 10;
    const angle = (i / count) * 360 + Math.random() * 30;
    const dist  = 70 + Math.random() * 160;
    const dur   = 650 + Math.random() * 550;
    const dx    = Math.cos(angle * Math.PI / 180) * dist;
    const dy    = Math.sin(angle * Math.PI / 180) * dist - 50;

    p.textContent = shape;
    p.style.cssText = `
      position:fixed; left:${ox}px; top:${oy}px;
      font-size:${size}px; color:${color};
      pointer-events:none; z-index:99999; user-select:none;
      transform:translate(-50%,-50%);
      transition:transform ${dur}ms cubic-bezier(.2,.8,.4,1), opacity ${dur}ms ease-out;
      will-change:transform,opacity;
    `;
    document.body.appendChild(p);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      p.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) rotate(${Math.random()*360}deg) scale(0.2)`;
      p.style.opacity   = "0";
    }));
    setTimeout(() => p.remove(), dur + 60);
  }

  // Floating +XP label rises from origin
  if (xp > 0) {
    const pop = document.createElement("div");
    pop.textContent = `+${xp} XP`;
    pop.style.cssText = `
      position:fixed; left:${ox}px; top:${oy - 20}px;
      transform:translate(-50%,-50%);
      font-size:22px; font-weight:800; color:#FFD700;
      text-shadow:0 2px 8px rgba(0,0,0,.5);
      pointer-events:none; z-index:99999;
      transition:transform 900ms cubic-bezier(.2,.8,.3,1), opacity 900ms ease-out;
    `;
    document.body.appendChild(pop);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      pop.style.transform = `translate(-50%, calc(-50% - 80px))`;
      pop.style.opacity   = "0";
    }));
    setTimeout(() => pop.remove(), 960);
  }
}

// ── Activity logging (used by dashboard) ────────────────────
async function logActivity(key, btn) {
  btn.disabled = true;
  btn.textContent = "Logging…";
  try {
    const data = await postJSON("/xp/log", {activity_key: key});
    if (data.error) {
      btn.textContent = data.already_done ? "Done ✓" : data.error;
      btn.disabled = data.already_done;
      return;
    }
    const row = btn.closest(".activity-row");
    if (row) {
      row.querySelector(".status-dot").className = "status-dot dot-done";
      btn.outerHTML = `<span class="xp-pill xp-done">+${data.xp_earned} XP ✓</span>`;
    }
    const metricVals = document.querySelectorAll(".metric-card .metric-val");
    if (metricVals[0]) metricVals[0].textContent = data.total_today?.toLocaleString();
    if (metricVals[2]) metricVals[2].textContent = (data.gaming_hours||0).toFixed(1) + " hr";
    refreshNavStatus();
    showToast(`+${data.xp_earned} XP earned!`, "success");
    fireConfetti(data.xp_earned, document.querySelector(`.activity-row[data-key="${key}"]`) || null);
  } catch(_) {
    btn.textContent = "Error — try again";
    btn.disabled = false;
  }
}

// ── Keyframe (injected once) ─────────────────────────────────
const _s = document.createElement("style");
_s.textContent = `@keyframes toastUp { from{opacity:0;transform:translateX(-50%) translateY(8px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }`;
document.head.appendChild(_s);

// ── Boot ─────────────────────────────────────────────────────
initTheme();
refreshNavStatus();
setInterval(refreshNavStatus, 60000);
loadWeather();
