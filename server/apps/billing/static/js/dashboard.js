let computers = [];
let tariffs = [];
let sessions = [];
let barOrders = [];
let socket = null;
let selectedPcId = null;
let timerInterval = null;
let currentZone = 'ALL'; // 'ALL', '1-VIP Zone', '2-VIP Zone', 'Main Zone', 'Standard Zone'
let currentStatusFilter = 'ALL';
let barFilterStatus = 'ALL';
let searchQuery = '';
let currentTab = 'grid';
let activeInputMode = 'money';

// Server endi har bir API so'rovi uchun tizimga kirgan bo'lishni talab
// qiladi. Har bir fetch() chaqiruvini alohida tekshirish o'rniga,
// global fetch() bitta joyda "o'raladi": 401/403 qaytgan har qanday
// so'rov (login so'rovining o'zidan tashqari) login oynasini avtomatik
// ochadi, shunda xodim sessiyasi tugagan/hali kirmagan bo'lsa ham,
// nima uchun ma'lumotlar yuklanmayotganini tushunadi.
(function () {
  const _originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const res = await _originalFetch(...args);
    const url = (args[0] && args[0].toString()) || '';
    if ((res.status === 401 || res.status === 403) && !url.includes('/api/login/')) {
      if (typeof openLoginModal === 'function') openLoginModal();
    }
    return res;
  };
})();

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}


// Web Audio API Synthesizer
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
function playAudioTone(freq, type, duration) {
  try {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {
    console.log("Audio play error:", e);
  }
}

function playSound(name) {
  if (name === 'start') {
    playAudioTone(523.25, 'triangle', 0.15);
    setTimeout(() => playAudioTone(659.25, 'triangle', 0.25), 120);
  } else if (name === 'add') {
    playAudioTone(440, 'sine', 0.15);
    setTimeout(() => playAudioTone(880, 'sine', 0.2), 100);
  } else if (name === 'lock') {
    playAudioTone(300, 'sawtooth', 0.3);
  } else if (name === 'alert') {
    playAudioTone(800, 'square', 0.15);
    setTimeout(() => playAudioTone(400, 'square', 0.25), 150);
  }
}

function formatTime(seconds) {
  if (seconds <= 0) return "00:00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [
    h.toString().padStart(2, '0'),
    m.toString().padStart(2, '0'),
    s.toString().padStart(2, '0')
  ].join(':');
}

function formatDurationText(totalMinutes) {
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h > 0 && m > 0) return `${h} Soat ${m} Daqiqa`;
  if (h > 0) return `${h} Soat`;
  return `${m} Daqiqa`;
}

function formatMoney(amount) {
  return new Intl.NumberFormat('uz-UZ').format(Math.round(amount)) + ' UZS';
}

// Authentication
async function handleAdminLogin(e) {
  if (e) e.preventDefault();
  const username = document.getElementById('login-username').value || 'admin';
  const password = document.getElementById('login-password').value || 'admin123';
  const errorMsg = document.getElementById('login-error-msg');

  try {
    const res = await fetch('/api/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      localStorage.setItem('admin_logged_in', 'true');
      localStorage.setItem('admin_username', data.username);
      updateAuthUI(true, data.username);
      closeLoginModal();
    } else {
      errorMsg.textContent = data.error || 'Invalid credentials!';
      errorMsg.classList.remove('hidden');
      playSound('alert');
    }
  } catch (err) {
    console.error("Login failed:", err);
    errorMsg.textContent = 'Server connection error!';
    errorMsg.classList.remove('hidden');
  }
}

async function handleAdminLogout() {
  try {
    await fetch('/api/logout/', { method: 'POST' });
  } catch (e) {}
  localStorage.removeItem('admin_logged_in');
  localStorage.removeItem('admin_username');
  updateAuthUI(false);
}

function updateAuthUI(isLoggedIn, username = 'Admin') {
  const profileSection = document.getElementById('user-profile-section');
  const loginGate = document.getElementById('login-modal');

  if (isLoggedIn) {
    profileSection.innerHTML = `
      <div class="flex items-center gap-3 bg-slate-900/90 border border-slate-800 rounded-xl px-3.5 py-1.5">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-purple-600 flex items-center justify-center font-bold text-black text-xs font-orbitron">
          ${username.substring(0, 2).toUpperCase()}
        </div>
        <div class="hidden sm:block text-left">
          <div class="text-xs font-bold text-white leading-tight">${username}</div>
          <div class="text-[10px] text-emerald-400 font-mono font-semibold">SUPERADMIN</div>
        </div>
        <button onclick="handleAdminLogout()" title="Logout" class="ml-1 text-slate-400 hover:text-rose-400 transition-colors">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
        </button>
      </div>
    `;
    loginGate.classList.add('hidden');
  } else {
    profileSection.innerHTML = `
      <button onclick="openLoginModal()" class="glow-btn-cyan py-1.5 px-4 rounded-xl text-xs font-bold flex items-center gap-1.5">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"/></svg>
        ADMIN LOGIN
      </button>
    `;
  }
}

function openLoginModal() {
  document.getElementById('login-modal').classList.remove('hidden');
}

function closeLoginModal() {
  document.getElementById('login-modal').classList.add('hidden');
}

// WebSockets
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/pc-status/`;
  
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    document.getElementById('ws-status-badge').innerHTML = `
      <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
      <span class="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Live WebSockets</span>
    `;
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'BAR_ORDER_UPDATE' || (data.action && data.action.includes('ORDER'))) {
        if (data.action === 'NEW_ORDER') {
          playSound('alert');
        }
        fetchBarOrders();
        fetchAnalytics();
      }
    } catch(e) {}
    fetchComputers();
    fetchSessions();
  };


  socket.onclose = () => {
    document.getElementById('ws-status-badge').innerHTML = `
      <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
      <span class="text-xs font-semibold text-rose-400 uppercase tracking-wider">Sync Offline</span>
    `;
    setTimeout(initWebSocket, 3000);
  };
}

// Data Fetching
async function fetchTariffs() {
  try {
    const res = await fetch('/api/tariffs/');
    tariffs = await res.json();
    populateTariffSelect();
    renderTariffsTable();
  } catch (err) {
    console.error("Tariffs fetch error:", err);
  }
}

async function fetchComputers() {
  try {
    const res = await fetch('/api/computers/');
    computers = await res.json();
    renderPCGrid();
    updateStatsHeader();
    renderPOSPCDropdown();
  } catch (err) {
    console.error("Computers fetch error:", err);
  }
}

async function fetchSessions() {
  try {
    const res = await fetch('/api/sessions/');
    sessions = await res.json();
    renderSessionsTable();
    updateStatsHeader();
  } catch (err) {
    console.error("Sessions fetch error:", err);
  }
}

// Countdown / Count Up Loop
function startCountdownTimer() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    let stateChanged = false;
    computers.forEach(pc => {
      if (pc.status === 'ACTIVE' || pc.status === 'WARNING') {
        if (pc.is_open_time) {
          pc.time_remaining++;
          const timerEl = document.getElementById(`timer-display-${pc.id}`);
          if (timerEl) {
            timerEl.textContent = formatTime(pc.time_remaining) + " ♾️";
          }
        } else {
          if (pc.time_remaining > 0) {
            pc.time_remaining--;
            if (pc.time_remaining <= 300 && pc.status !== 'WARNING') {
              pc.status = 'WARNING';
              stateChanged = true;
              playSound('alert');
            }
          } else {
            pc.status = 'LOCKED';
            pc.time_remaining = 0;
            stateChanged = true;
            playSound('lock');
          }
          const timerEl = document.getElementById(`timer-display-${pc.id}`);
          if (timerEl) {
            timerEl.textContent = formatTime(pc.time_remaining);
          }
        }
      }
    });
    if (stateChanged) {
      renderPCGrid();
      updateStatsHeader();
    }
  }, 1000);
}

// Header Stats & Discount Banner
function updateStatsHeader() {
  const total = computers.length;
  const active = computers.filter(c => c.status === 'ACTIVE' || c.status === 'WARNING').length;
  const locked = computers.filter(c => c.status === 'LOCKED').length;

  document.getElementById('stat-total-pcs').textContent = total;
  document.getElementById('stat-active-pcs').textContent = active;
  document.getElementById('stat-locked-pcs').textContent = locked;

  let revenue = 0;
  sessions.forEach(s => {
    revenue += parseFloat(s.total_price || 0);
  });
  document.getElementById('stat-revenue').textContent = (revenue > 0 ? '+' : '') + formatMoney(revenue);
}

// Filtering & Navigation
function filterZone(zoneName) {
  currentZone = zoneName;
  document.querySelectorAll('.zone-btn').forEach(btn => {
    if (btn.dataset.zone === zoneName) {
      btn.className = 'zone-btn px-4 py-2 rounded-xl text-xs font-bold border transition-all nav-tab-active';
    } else {
      btn.className = 'zone-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-800 bg-slate-900/60 text-slate-400 hover:text-white transition-all';
    }
  });
  renderPCGrid();
}

function filterStatus(statusName) {
  currentStatusFilter = statusName;
  document.querySelectorAll('.status-filter-btn').forEach(btn => {
    if (btn.dataset.status === statusName) {
      btn.className = 'status-filter-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 transition-all';
    } else {
      btn.className = 'status-filter-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-slate-400 hover:text-white border border-slate-800 transition-all';
    }
  });
  renderPCGrid();
}

function handleSearch(val) {
  searchQuery = val.toLowerCase();
  renderPCGrid();
}

// "SETTINGS" ochiladigan menyusi ostidagi bo'limlar — shulardan biri
// tanlangan bo'lsa, "SETTINGS" pillasining o'zi ham faol ko'rinishi
// kerak (aks holda foydalanuvchi qaysi menyuda ekanini yo'qotib qo'yadi).
const SETTINGS_SUB_TABS = ['tariffs', 'analytics', 'auditlog', 'sessions'];

function toggleSettingsMenu(event) {
  event.stopPropagation();
  const panel = document.getElementById('settings-dropdown-panel');
  const btn = document.getElementById('settings-nav-btn');
  if (!panel || !btn) return;
  const willShow = panel.classList.contains('hidden');
  if (willShow) {
    // position:fixed bo'lgani uchun joylashuvi tugma ekrandagi joyiga
    // qarab har safar hisoblanadi (nav skroll qilingan/o'zgargan bo'lsa
    // ham to'g'ri joyda chiqishi uchun).
    const rect = btn.getBoundingClientRect();
    panel.style.top = (rect.bottom + 8) + 'px';
    panel.style.left = rect.left + 'px';
  }
  panel.classList.toggle('hidden', !willShow);
}

document.addEventListener('click', (e) => {
  const panel = document.getElementById('settings-dropdown-panel');
  const btn = document.getElementById('settings-nav-btn');
  if (!panel || panel.classList.contains('hidden')) return;
  if (!panel.contains(e.target) && e.target !== btn && !btn?.contains(e.target)) {
    panel.classList.add('hidden');
  }
});

function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.main-nav-btn').forEach(btn => {
    if (btn.dataset.tab === tabName) {
      btn.classList.add('nav-tab-active');
      btn.classList.remove('text-slate-400', 'border-transparent');
    } else {
      btn.classList.remove('nav-tab-active');
      btn.classList.add('text-slate-400', 'border-transparent');
    }
  });

  const settingsBtn = document.getElementById('settings-nav-btn');
  if (settingsBtn) {
    settingsBtn.classList.toggle('nav-tab-active', SETTINGS_SUB_TABS.includes(tabName));
  }
  document.getElementById('settings-dropdown-panel')?.classList.add('hidden');

  document.getElementById('tab-view-grid').classList.toggle('hidden', tabName !== 'grid');
  document.getElementById('tab-view-tariffs').classList.toggle('hidden', tabName !== 'tariffs');
  document.getElementById('tab-view-sessions').classList.toggle('hidden', tabName !== 'sessions');
  document.getElementById('tab-view-bar').classList.toggle('hidden', tabName !== 'bar');
  document.getElementById('tab-view-analytics').classList.toggle('hidden', tabName !== 'analytics');
  const finTab = document.getElementById('tab-view-finance');
  if (finTab) finTab.classList.toggle('hidden', tabName !== 'finance');
  const custTab = document.getElementById('tab-view-customers');
  if (custTab) custTab.classList.toggle('hidden', tabName !== 'customers');
  const auditTab = document.getElementById('tab-view-auditlog');
  if (auditTab) auditTab.classList.toggle('hidden', tabName !== 'auditlog');

  if (tabName === 'bar') fetchBarOrders();
  if (tabName === 'analytics') fetchAnalytics();
  if (tabName === 'finance') fetchFinanceData();
  if (tabName === 'customers') fetchCustomers();
  if (tabName === 'auditlog') fetchAuditLog();
}


// Ultra Sleek Modern PC Card Generator
function generatePCCardHTML(pc) {
  let statusClass = 'card-status-locked';
  let statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center gap-1.5 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> ${t('card.locked')}</span>`;

  if (pc.status === 'ACTIVE') {
    if (pc.is_open_time) {
      statusClass = 'card-status-active';
      statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5 animate-pulse whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span> ${t('card.open_time')}</span>`;
    } else {
      statusClass = 'card-status-active';
      statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ${t('card.active')}</span>`;
    }
  } else if (pc.status === 'WARNING') {
    statusClass = 'card-status-warning';
    statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1.5 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce"></span> ${t('card.low_time')}</span>`;
  }

  const timerText = formatTime(pc.time_remaining) + (pc.is_open_time ? " ♾️" : "");
  const tariffName = pc.is_open_time ? "VIP Open Time" : (pc.current_tariff_name || 'Standard Plan');

  return `
    <div class="glass-card ${statusClass} rounded-2xl p-4 border border-slate-800/80 bg-slate-900/60 hover:border-cyan-500/40 hover:shadow-xl hover:shadow-cyan-500/5 transition-all duration-300 flex flex-col justify-between group">
      <div>
        <!-- Top Row: Station Badge (name + zone caption) & Status -->
        <div class="flex items-start justify-between mb-3 gap-2">
          <div class="flex flex-col items-start gap-1 min-w-0">
            <div class="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center font-orbitron font-black text-base text-cyan-400 group-hover:border-cyan-500/50 group-hover:text-cyan-300 transition-colors shadow-inner whitespace-nowrap">
              ${pc.name}
            </div>
            <span class="text-[10px] font-bold text-slate-400 font-mono pl-1 truncate">${pc.zone}</span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            ${statusBadge}
          </div>
        </div>

        <!-- Utility Icons Row (screenshot / force-close / shutdown) -->
        <div class="flex items-center justify-end gap-1.5 mb-2.5">
          <button onclick="openScreenshotModal(${pc.id}, '${pc.name}')" title="${t('card.view_screen')}" class="w-6 h-6 rounded-md bg-slate-800/80 hover:bg-cyan-500/20 border border-slate-700 hover:border-cyan-500/40 text-slate-400 hover:text-cyan-400 flex items-center justify-center transition-all">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
          </button>
          <button onclick="forceCloseApp(${pc.id}, '${pc.name}')" title="${t('card.force_close')}" class="w-6 h-6 rounded-md bg-slate-800/80 hover:bg-amber-500/20 border border-slate-700 hover:border-amber-500/40 text-slate-400 hover:text-amber-400 flex items-center justify-center transition-all">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <button onclick="remoteShutdownPc(${pc.id}, '${pc.name}')" title="${t('card.shutdown_pc')}" class="w-6 h-6 rounded-md bg-slate-800/80 hover:bg-rose-500/20 border border-slate-700 hover:border-rose-500/40 text-slate-400 hover:text-rose-400 flex items-center justify-center transition-all">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9"/></svg>
          </button>
        </div>

        <!-- Giant Timer Box -->
        <div class="my-3 py-3 px-3 rounded-xl bg-slate-950/90 border border-slate-800/90 text-center relative overflow-hidden group-hover:border-cyan-500/30 transition-colors">
          <div class="text-[9px] text-slate-400 uppercase tracking-widest font-semibold mb-1 flex items-center justify-center gap-1">
            ${pc.is_open_time ? `<span class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span> ${t('card.time_played')}` : t('card.time_remaining')}
          </div>
          <div id="timer-display-${pc.id}" class="text-3xl font-black font-orbitron tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-purple-400">
            ${timerText}
          </div>
        </div>

        <!-- Tariff Info Line -->
        <div class="flex items-center justify-between text-xs px-1 mb-3 pt-1">
          <span class="text-[11px] text-slate-400">${t('finish_modal.tariff_label')}</span>
          <span class="text-[11px] font-bold font-orbitron text-slate-200">${tariffName}</span>
        </div>
      </div>

      <!-- Action Buttons Footer -->
      <div class="pt-2.5 border-t border-slate-800/80">
        ${(pc.status === 'LOCKED' || pc.status === 'OFFLINE') ? `
          <button onclick="openStartModal(${pc.id})" class="w-full py-2.5 px-3 rounded-xl glow-btn-cyan text-xs font-extrabold flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            ${t('card.start_session')}
          </button>
        ` : `
          <div class="flex items-center justify-center gap-2">
            <button onclick="openAddTimeModal(${pc.id})" class="py-2 px-3.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/40 text-xs font-extrabold flex items-center justify-center gap-1 transition-all">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/></svg>
              ${t('card.add_time')}
            </button>
            <button onclick="stopSession(${pc.id})" class="py-2 px-3.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-extrabold flex items-center justify-center gap-1 transition-all">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"/></svg>
              ${t('card.finish')}
            </button>
          </div>
        `}
      </div>
    </div>
  `;
}

// Render PC Grid Groups (1-VIP, 2-VIP, Main, Standard)
function renderPCGrid() {
  const container = document.getElementById('pc-grid-container');
  if (!container) return;
  container.innerHTML = '';

  const zoneDefinitions = [
    { title: "👑 1-VIP Zone (PC-01 ... PC-10)", zoneKey: "1-VIP Zone", badge: "VIP 12,000 UZS/h" },
    { title: "👑 2-VIP Zone (PC-11 ... PC-20)", zoneKey: "2-VIP Zone", badge: "VIP 12,000 UZS/h" },
    { title: "⚡ Main Zone (PC-21 ... PC-30)", zoneKey: "Main Zone", badge: "VIP 12,000 UZS/h" },
    { title: "🎮 Standard Zone (PC-31 ... PC-40)", zoneKey: "Standard Zone", badge: "VIP 12,000 UZS/h" },
  ];

  const activeZones = currentZone === 'ALL' ? zoneDefinitions : zoneDefinitions.filter(z => z.zoneKey === currentZone);

  activeZones.forEach(zoneDef => {
    const pcsInZone = computers.filter(pc => {
      const matchZone = pc.zone === zoneDef.zoneKey;
      const matchStatus = currentStatusFilter === 'ALL' || 
                          (currentStatusFilter === 'ACTIVE' && (pc.status === 'ACTIVE' || pc.status === 'WARNING')) ||
                          (currentStatusFilter === 'LOCKED' && pc.status === 'LOCKED');
      const matchSearch = pc.name.toLowerCase().includes(searchQuery);
      return matchZone && matchStatus && matchSearch;
    });

    if (pcsInZone.length === 0 && currentZone !== 'ALL') return;

    // Zone Header Section
    const section = document.createElement('div');
    section.className = 'w-full mb-8';

    section.innerHTML = `
      <div class="flex items-center justify-between mb-4 pb-2 border-b border-slate-800/80">
        <h3 class="text-base font-extrabold font-orbitron text-white flex items-center gap-2">
          ${zoneDef.title}
          <span class="text-[11px] px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-mono font-semibold">${pcsInZone.length} PCs</span>
        </h3>
        <span class="text-xs font-mono font-bold text-slate-400">${zoneDef.badge}</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-5">
        ${pcsInZone.map(pc => generatePCCardHTML(pc)).join('')}
      </div>
    `;

    container.appendChild(section);
  });
}

// Populate Tariff Options
function populateTariffSelect() {
  const select = document.getElementById('start-tariff-select');
  if (!select) return;
  select.innerHTML = '';

  tariffs.forEach(tariff => {
    const opt = document.createElement('option');
    opt.value = tariff.id;
    const price = parseFloat(tariff.price_per_hour);
    opt.textContent = `${tariff.name} — ${formatMoney(price)} / ${t('unit.hour_lower')}`;
    select.appendChild(opt);
  });
}

function renderTariffsTable() {
  const tbody = document.getElementById('tariffs-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  tariffs.forEach(tariff => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-800 hover:bg-slate-900/50 transition-colors';
    const basePrice = parseFloat(tariff.price_per_hour);

    tr.innerHTML = `
      <td class="py-3 px-4 font-bold text-white font-orbitron">${tariff.name}</td>
      <td class="py-3 px-4 text-cyan-400 font-bold font-orbitron">${formatMoney(basePrice)} / ${t('unit.hour_lower')}</td>
      <td class="py-3 px-4 text-xs text-slate-400 font-mono">${new Date(tariff.created_at).toLocaleDateString()}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderSessionsTable() {
  const tbody = document.getElementById('sessions-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';
  sessions.slice(0, 20).forEach(s => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-800 hover:bg-slate-900/50 transition-colors';
    tr.innerHTML = `
      <td class="py-3 px-4 font-bold text-cyan-400 font-orbitron">${s.computer_name}</td>
      <td class="py-3 px-4 text-xs text-slate-300">${s.is_open_time ? "♾️ VIP Open Time" : (s.tariff_name || t('sessions.standard'))}</td>
      <td class="py-3 px-4 font-mono text-xs text-slate-300">${s.is_open_time ? s.duration_minutes + " " + t('sessions.min_open') : formatDurationText(s.duration_minutes)}</td>
      <td class="py-3 px-4 font-bold text-emerald-400 font-orbitron">${formatMoney(s.total_price)}</td>
      <td class="py-3 px-4 text-xs text-slate-400 font-mono">${new Date(s.start_time).toLocaleTimeString()}</td>
      <td class="py-3 px-4">
        ${s.is_active ?
          `<span class="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/20 text-emerald-400">${t('card.active')}</span>` :
          `<span class="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-400">${t('sessions.completed')}</span>`}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function setStartPaymentMethod(method) {
  const input = document.getElementById('start-payment-method');
  if (input) input.value = method;

  const btnCash = document.getElementById('start-pm-btn-cash');
  const btnCard = document.getElementById('start-pm-btn-card');
  const btnFree = document.getElementById('start-pm-btn-free');
  const inactive = "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-slate-900 text-slate-400 border-slate-800";

  if (btnCash) btnCash.className = method === 'CASH' ? "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-emerald-500/20 text-emerald-400 border-emerald-500/50" : inactive;
  if (btnCard) btnCard.className = method === 'CARD' ? "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-cyan-500/20 text-cyan-400 border-cyan-500/50" : inactive;
  if (btnFree) btnFree.className = method === 'FREE' ? "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-pink-500/20 text-pink-300 border-pink-500/50" : inactive;
}

// Modal Handlers & Presets
function openStartModal(pcId) {
  selectedPcId = pcId;
  const pc = computers.find(c => c.id === pcId);
  document.getElementById('start-pc-title').textContent = pc ? pc.name : `PC-${pcId}`;
  
  if (pc && pc.current_tariff) {
    document.getElementById('start-tariff-select').value = pc.current_tariff;
  }
  
  setStartPaymentMethod('CASH');
  document.getElementById('start-modal').classList.remove('hidden');
  setMoneyPreset(5000); // Default to 5000 UZS quick preset
}

function closeStartModal() {
  document.getElementById('start-modal').classList.add('hidden');
  selectedPcId = null;
}

// Masofadan ekranni ko'rish
let screenshotRefreshInterval = null;
let screenshotPcId = null;

function _refreshScreenshotImg() {
  if (!screenshotPcId) return;
  const img = document.getElementById('screenshot-img');
  const errorMsg = document.getElementById('screenshot-error');
  img.classList.remove('hidden');
  errorMsg.classList.add('hidden');
  img.src = `/api/computers/${screenshotPcId}/screenshot/?t=${Date.now()}`;
}

function openScreenshotModal(pcId, pcName) {
  screenshotPcId = pcId;
  document.getElementById('screenshot-pc-title').textContent = pcName;
  document.getElementById('screenshot-modal').classList.remove('hidden');
  _refreshScreenshotImg();
  if (screenshotRefreshInterval) clearInterval(screenshotRefreshInterval);
  screenshotRefreshInterval = setInterval(_refreshScreenshotImg, 5000);
}

function closeScreenshotModal() {
  document.getElementById('screenshot-modal').classList.add('hidden');
  if (screenshotRefreshInterval) {
    clearInterval(screenshotRefreshInterval);
    screenshotRefreshInterval = null;
  }
  screenshotPcId = null;
}

function setMoneyPreset(sumAmount) {
  activeInputMode = 'money';
  document.getElementById('start-amount-input').value = sumAmount;
  updateCalculatedPrice();
}

function setPresetMinutes(mins) {
  activeInputMode = 'minutes';
  document.getElementById('start-minutes-input').value = mins;
  updateCalculatedPrice();
}

function setOpenTimePreset() {
  activeInputMode = 'open';
  updateCalculatedPrice();
}

function updateCalculatedPrice() {
  const tariffId = document.getElementById('start-tariff-select').value;
  const tariff = tariffs.find(t => t.id == tariffId) || tariffs[0];
  
  if (!tariff) return;

  const pricePerHour = parseFloat(tariff.price_per_hour);
  const pricePerMin = pricePerHour / 60.0;

  const openBoxNote = document.getElementById('open-time-note-box');
  const calcCustomInputs = document.getElementById('custom-inputs-wrapper');

  if (activeInputMode === 'open') {
    if (openBoxNote) openBoxNote.classList.remove('hidden');
    if (calcCustomInputs) calcCustomInputs.classList.add('hidden');

    document.getElementById('calculated-price-display').textContent = "Turishda Hisoblanadi";
    document.getElementById('calculated-duration-display').textContent = "♾️ VIP Open Time";
  } else {
    if (openBoxNote) openBoxNote.classList.add('hidden');
    if (calcCustomInputs) calcCustomInputs.classList.remove('hidden');

    if (activeInputMode === 'money') {
      const moneyVal = parseFloat(document.getElementById('start-amount-input').value) || 0;
      const calculatedMins = Math.round(moneyVal / pricePerMin);
      document.getElementById('start-minutes-input').value = calculatedMins;

      document.getElementById('calculated-price-display').textContent = formatMoney(moneyVal);
      document.getElementById('calculated-duration-display').textContent = formatDurationText(calculatedMins);
    } else {
      const minsVal = parseInt(document.getElementById('start-minutes-input').value) || 0;
      const calculatedSum = Math.round(minsVal * pricePerMin);
      document.getElementById('start-amount-input').value = calculatedSum;

      document.getElementById('calculated-price-display').textContent = formatMoney(calculatedSum);
      document.getElementById('calculated-duration-display').textContent = formatDurationText(minsVal);
    }
  }

  const noteEl = document.getElementById('discount-calc-note');
  if (noteEl) {
    if (tariff.name.includes('Skidka') || pricePerHour <= 6000) {
      noteEl.textContent = `⚡ Skidka 50% Tarifi Tanlandi: 6,000 UZS / Soat (100 UZS / daqiqa)`;
      noteEl.classList.remove('hidden');
    } else {
      noteEl.classList.add('hidden');
    }
  }
}

async function confirmStartSession() {
  if (!selectedPcId) return;
  const tariffId = document.getElementById('start-tariff-select').value;
  const amount = parseFloat(document.getElementById('start-amount-input').value) || 0;
  const minutes = parseInt(document.getElementById('start-minutes-input').value) || 60;
  const paymentMethod = document.getElementById('start-payment-method') ? document.getElementById('start-payment-method').value : 'CASH';

  try {
    const bodyData = { tariff_id: tariffId, payment_method: paymentMethod };
    if (activeInputMode === 'open') {
      bodyData.is_open_time = true;
    } else if (activeInputMode === 'money' && amount > 0) {
      bodyData.amount = amount;
    } else {
      bodyData.minutes = minutes;
    }

    const res = await fetch(`/api/computers/${selectedPcId}/start_session/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyData)
    });
    if (res.ok) {
      playSound('start');
      closeStartModal();
      fetchComputers();
      fetchSessions();
    } else {
      alert("Seansni boshlashda xatolik!");
    }
  } catch (err) {
    console.error("Error starting session:", err);
  }
}

function openAddTimeModal(pcId) {
  selectedPcId = pcId;
  const pc = computers.find(c => c.id === pcId);
  document.getElementById('add-pc-title').textContent = pc ? pc.name : `PC-${pcId}`;
  document.getElementById('add-time-modal').classList.remove('hidden');
}

function closeAddTimeModal() {
  document.getElementById('add-time-modal').classList.add('hidden');
  selectedPcId = null;
}

async function confirmAddTime(mins) {
  if (!selectedPcId) return;
  const minutes = mins || parseInt(document.getElementById('add-minutes-input').value) || 30;

  try {
    const res = await fetch(`/api/computers/${selectedPcId}/add_time/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ minutes: minutes })
    });
    if (res.ok) {
      playSound('add');
      closeAddTimeModal();
      fetchComputers();
      fetchSessions();
    } else {
      alert("Vaqt qo'shishda xatolik!");
    }
  } catch (err) {
    console.error("Error adding time:", err);
  }
}

let currentFinishPcId = null;

async function stopSession(pcId) {
  openFinishSessionModal(pcId);
}

async function openFinishSessionModal(pcId) {
  currentFinishPcId = pcId;
  const modal = document.getElementById('finish-session-modal');
  const loading = document.getElementById('finish-modal-loading');
  const body = document.getElementById('finish-modal-body');
  const footer = document.getElementById('finish-modal-footer');
  const submitBtn = document.getElementById('finish-submit-btn');

  if (!modal) return;

  modal.classList.remove('hidden');
  loading.classList.remove('hidden');
  body.classList.add('hidden');
  footer.classList.add('hidden');
  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.innerText = "TO'LOVNI QABUL QILISH VA YOPISH";
  }

  try {
    const res = await fetch(`/api/computers/${pcId}/finish_summary/`);
    if (!res.ok) {
      alert("Seans chek ma'lumotlarini olishda xatolik!");
      closeFinishSessionModal();
      return;
    }
    const data = await res.json();

    document.getElementById('finish-pc-title').innerText = data.computer_name;
    document.getElementById('finish-pc-zone').innerText = data.zone || 'Standard';
    
    let durText = `${data.duration_minutes} Daqiqa`;
    if (data.duration_minutes >= 60) {
      const h = Math.floor(data.duration_minutes / 60);
      const m = data.duration_minutes % 60;
      durText = `${h} Soat ${m} Daqiqa`;
    }
    document.getElementById('finish-duration-display').innerText = durText;
    document.getElementById('finish-time-price').innerText = `${Math.round(data.time_price).toLocaleString()} UZS`;
    document.getElementById('finish-tariff-name').innerText = data.tariff_name;
    document.getElementById('finish-session-type').innerText = data.is_open_time ? "♾️ VIP Open Time" : "Standard Timer";

    const container = document.getElementById('finish-bar-items-container');
    container.innerHTML = '';
    if (data.bar_items && data.bar_items.length > 0) {
      data.bar_items.forEach(item => {
        const itemEl = document.createElement('div');
        itemEl.className = "flex items-center justify-between p-2 rounded-lg bg-slate-950/70 border border-slate-800/80";
        itemEl.innerHTML = `
          <span class="font-medium text-slate-200">${item.product_name} <span class="text-amber-400 font-bold ml-1">x${item.quantity}</span></span>
          <span class="font-mono text-slate-300 font-semibold">${Math.round(item.total_price).toLocaleString()} UZS</span>
        `;
        container.appendChild(itemEl);
      });
    } else {
      container.innerHTML = `<div class="text-slate-500 italic text-center py-2">Ushbu seansda bar buyurtmalari yo'q (0 UZS)</div>`;
    }

    currentFinishGrandTotal = Math.round(data.grand_total || 0);
    document.getElementById('finish-bar-price').innerText = `${Math.round(data.bar_total_price).toLocaleString()} UZS`;
    document.getElementById('finish-grand-total').innerText = `${currentFinishGrandTotal.toLocaleString()} UZS`;

    setFinishPaymentMethod(data.payment_method || 'CASH');

    loading.classList.add('hidden');
    body.classList.remove('hidden');
    footer.classList.remove('hidden');
  } catch (err) {
    console.error("Error fetching finish summary:", err);
    alert("Chek ma'lumotlarini yuklashda xatolik yuz berdi!");
    closeFinishSessionModal();
  }
}

let currentFinishGrandTotal = 0;

function setFinishPaymentMethod(method) {
  const input = document.getElementById('finish-payment-method');
  const btnCash = document.getElementById('finish-pm-btn-cash');
  const btnCard = document.getElementById('finish-pm-btn-card');
  const btnSplit = document.getElementById('finish-pm-btn-split');
  const btnFree = document.getElementById('finish-pm-btn-free');
  const splitContainer = document.getElementById('finish-split-container');
  const cashInput = document.getElementById('finish-split-cash');
  const cardInput = document.getElementById('finish-split-card');
  const inactive = "py-3 rounded-xl border font-bold text-xs flex items-center justify-center gap-1.5 bg-slate-900 text-slate-400 border-slate-800";

  if (input) input.value = method;

  if (btnCash) btnCash.className = method === 'CASH' ? "py-3 rounded-xl border font-bold text-xs flex items-center justify-center gap-1.5 bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-md" : inactive;
  if (btnCard) btnCard.className = method === 'CARD' ? "py-3 rounded-xl border font-bold text-xs flex items-center justify-center gap-1.5 bg-sky-500/20 text-sky-400 border-sky-500/50 shadow-md" : inactive;
  if (btnSplit) btnSplit.className = method === 'SPLIT' ? "py-3 rounded-xl border font-bold text-xs flex items-center justify-center gap-1.5 bg-purple-500/20 text-purple-400 border-purple-500/50 shadow-md" : inactive;
  if (btnFree) btnFree.className = method === 'FREE' ? "py-3 rounded-xl border font-bold text-xs flex items-center justify-center gap-1.5 bg-pink-500/20 text-pink-300 border-pink-500/50 shadow-md" : inactive;

  if (method === 'SPLIT') {
    if (splitContainer) splitContainer.classList.remove('hidden');
    const halfCash = Math.round(currentFinishGrandTotal / 2);
    if (cashInput) cashInput.value = halfCash;
    if (cardInput) cardInput.value = currentFinishGrandTotal - halfCash;
    updateFinishSplitCalc('cash');
  } else {
    if (splitContainer) splitContainer.classList.add('hidden');
  }
}

function updateFinishSplitCalc(changedSide = 'cash') {
  const cashInput = document.getElementById('finish-split-cash');
  const cardInput = document.getElementById('finish-split-card');
  const statusEl = document.getElementById('finish-split-status');

  let cashVal = parseFloat(cashInput?.value) || 0;
  let cardVal = parseFloat(cardInput?.value) || 0;

  if (changedSide === 'cash') {
    cardVal = Math.max(0, currentFinishGrandTotal - cashVal);
    if (cardInput) cardInput.value = cardVal;
  } else if (changedSide === 'card') {
    cashVal = Math.max(0, currentFinishGrandTotal - cardVal);
    if (cashInput) cashInput.value = cashVal;
  }

  const sum = cashVal + cardVal;
  if (statusEl) {
    if (Math.abs(sum - currentFinishGrandTotal) < 1) {
      statusEl.textContent = "100% Mos keldi";
      statusEl.className = "text-emerald-400 font-bold font-mono";
    } else {
      const diff = currentFinishGrandTotal - sum;
      statusEl.textContent = diff > 0 ? `${formatMoney(diff)} yetmayapti` : `${formatMoney(-diff)} ortiqcha`;
      statusEl.className = "text-rose-400 font-bold font-mono";
    }
  }
}

function closeFinishSessionModal() {
  const modal = document.getElementById('finish-session-modal');
  if (modal) modal.classList.add('hidden');
  currentFinishPcId = null;
}

async function confirmFinishSession() {
  if (!currentFinishPcId) return;

  const paymentMethod = document.getElementById('finish-payment-method')?.value || 'CASH';
  const submitBtn = document.getElementById('finish-submit-btn');

  let cashAmt = 0;
  let cardAmt = 0;

  if (paymentMethod === 'CASH') {
    cashAmt = currentFinishGrandTotal;
    cardAmt = 0;
  } else if (paymentMethod === 'CARD') {
    cashAmt = 0;
    cardAmt = currentFinishGrandTotal;
  } else if (paymentMethod === 'SPLIT') {
    cashAmt = parseFloat(document.getElementById('finish-split-cash')?.value) || 0;
    cardAmt = parseFloat(document.getElementById('finish-split-card')?.value) || 0;

    if (Math.abs((cashAmt + cardAmt) - currentFinishGrandTotal) > 1) {
      alert(`Naqd va Plastik to'lovlar yig'indisi Jami Summa (${formatMoney(currentFinishGrandTotal)}) ga teng bo'lishi kerak!`);
      return;
    }
  } else if (paymentMethod === 'FREE') {
    cashAmt = 0;
    cardAmt = 0;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "YOPILMOQDA...";
  }

  try {
    const res = await fetch(`/api/computers/${currentFinishPcId}/stop_session/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payment_method: paymentMethod,
        cash_amount: cashAmt,
        card_amount: cardAmt
      })
    });

    if (res.ok) {
      playSound('lock');
      closeFinishSessionModal();
      fetchComputers();
      fetchSessions();
      fetchBarOrders();
      fetchAnalytics();
      fetchFinanceData();
    } else {
      alert("Seansni tugatishda va to'lovni qabul qilishda xatolik!");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = "TO'LOVNI QABUL QILISH VA YOPISH";
      }
    }
  } catch (err) {
    console.error("Error confirming finish session:", err);
    alert("To'lovni yopishda xatolik yuz berdi!");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "TO'LOVNI QABUL QILISH VA YOPISH";
    }
  }
}

async function emergencyLockAll() {
  if (!confirm("DIQQAT: Favqulodda bloklash BARCHA kompyuterlarni darhol bloklaydi. Davom etasizmi?")) return;

  try {
    const res = await fetch(`/api/computers/emergency_lock_all/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      playSound('alert');
      fetchComputers();
      fetchSessions();
    } else {
      alert("Emergency lock error!");
    }
  } catch (err) {
    console.error("Error in emergency lock:", err);
  }
}

async function shutdownAllPcs() {
  if (!confirm("DIQQAT: Bu BARCHA kompyuterlarni butunlay o'chiradi (Windows shutdown). Davom etasizmi?")) return;

  try {
    const res = await fetch(`/api/computers/shutdown_all_pcs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      playSound('alert');
    } else {
      alert("Kompyuterlarni o'chirishda xatolik!");
    }
  } catch (err) {
    console.error("Error in shutdown all:", err);
  }
}

async function remoteShutdownPc(pcId, pcName) {
  if (!confirm(`"${pcName}" kompyuterini o'chirmoqchimisiz?`)) return;
  try {
    const res = await fetch(`/api/computers/${pcId}/remote_shutdown/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) alert("Kompyuterni o'chirishda xatolik!");
  } catch (err) {
    console.error("Error in remote shutdown:", err);
  }
}

async function forceCloseApp(pcId, pcName) {
  if (!confirm(`"${pcName}"da muzlab qolgan dasturni majburan yopmoqchimisiz?`)) return;
  try {
    const res = await fetch(`/api/computers/${pcId}/force_close_app/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) alert("Dasturni yopishda xatolik!");
  } catch (err) {
    console.error("Error in force close app:", err);
  }
}

// Live Clock
function updateHeaderClock() {
  const clockEl = document.getElementById('header-clock');
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-GB');
  }
}

// Add New Tariff
async function handleAddTariff(e) {
  e.preventDefault();
  const name = document.getElementById('new-tariff-name').value;
  const price = parseFloat(document.getElementById('new-tariff-price').value);

  if (!name || !price) return;

  try {
    const res = await fetch('/api/tariffs/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, price_per_hour: price })
    });
    if (res.ok) {
      fetchTariffs();
      document.getElementById('new-tariff-name').value = '';
      document.getElementById('new-tariff-price').value = '';
    }
  } catch (err) {
    console.error("Error adding tariff:", err);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Standart admin/admin123 login ma'lumotlari endi formada oldindan
  // to'ldirilmaydi (xavfsizlik uchun), shuning uchun avtomatik login
  // urinishning ma'nosi yo'q. Buning o'rniga: agar brauzerda avvaldan
  // amaldagi sessiya bo'lsa (oxirgi ~2 hafta ichida tizimga kirilgan
  // bo'lsa), quyidagi so'rovlar shunchaki muvaffaqiyatli o'tadi. Aks
  // holda ular 401/403 qaytaradi va pastdagi global fetch himoyachisi
  // login oynasini avtomatik ochadi.
  updateAuthUI(false);
  try {
    const sessionCheck = await fetch('/api/computers/');
    if (sessionCheck.ok) {
      updateAuthUI(true, localStorage.getItem('admin_username') || 'Admin');
    }
  } catch (err) {}

  fetchTariffs();
  fetchComputers();
  fetchSessions();
  fetchBarOrders();
  fetchAnalytics();
  initWebSocket();
  startCountdownTimer();
  setInterval(updateHeaderClock, 1000);
  updateHeaderClock();
});

// Bar Orders & Inventory Analytics
async function fetchBarOrders() {
  try {
    const res = await fetch('/api/orders/');
    barOrders = await res.json();
    renderBarOrders();
    renderBarPOSProducts();
  } catch (err) {
    console.error("Bar orders fetch error:", err);
  }
}

function filterBarOrders(status) {
  barFilterStatus = status;
  document.querySelectorAll('.bar-filter-btn').forEach(btn => {
    if (btn.dataset.barStatus === status) {
      btn.className = 'bar-filter-btn px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 transition-all';
    } else {
      btn.className = 'bar-filter-btn px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition-all';
    }
  });
  renderBarOrders();
}

function renderBarOrders() {
  const container = document.getElementById('bar-orders-container');
  if (!container) return;

  const pendingCount = barOrders.filter(o => o.status === 'PENDING').length;
  const pendingBadge = document.getElementById('bar-pending-badge');
  const navPendingBadge = document.getElementById('nav-bar-pending-badge');

  if (pendingBadge) {
    pendingBadge.textContent = `${pendingCount} ${t('bar.status_pending')}`;
    pendingBadge.classList.toggle('bg-rose-500/20', pendingCount > 0);
  }

  if (navPendingBadge) {
    if (pendingCount > 0) {
      navPendingBadge.textContent = pendingCount;
      navPendingBadge.classList.remove('hidden');
    } else {
      navPendingBadge.classList.add('hidden');
    }
  }

  const filtered = barOrders.filter(o => barFilterStatus === 'ALL' || o.status === barFilterStatus);

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="glass-panel p-8 text-center rounded-2xl text-slate-500">
        <svg class="w-12 h-12 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
        ${t('bar.no_orders')}
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(order => {
    let statusBadge = `<span class="px-3 py-1 text-xs font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse flex items-center gap-1">⏳ ${t('bar.badge_pending')}</span>`;
    if (order.status === 'APPROVED') {
      statusBadge = `<span class="px-3 py-1 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1">👍 ${t('bar.badge_approved')}</span>`;
    } else if (order.status === 'DELIVERED') {
      statusBadge = `<span class="px-3 py-1 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1">🚚 ${t('bar.badge_delivered')}</span>`;
    } else if (order.status === 'CANCELLED') {
      statusBadge = `<span class="px-3 py-1 text-xs font-bold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 flex items-center gap-1">❌ ${t('bar.badge_cancelled')}</span>`;
    }

    const pcDisplayName = order.computer_name || (order.computer ? `PC-${String(order.computer).padStart(2, '0')}` : t('bar.quick_sale'));
    const isDirectBarSale = !order.computer && (!order.computer_name || order.computer_name === 'TEZKOR BAR');

    const pcBadgeHTML = isDirectBarSale ? `
      <div class="px-3.5 py-1.5 rounded-xl bg-amber-500/15 border border-amber-500/40 text-amber-300 font-orbitron font-extrabold text-xs flex items-center gap-1.5 shrink-0 whitespace-nowrap shadow-md shadow-amber-500/10">
        <span class="text-base">🛍️</span>
        <span>${t('bar.quick_sale')}</span>
      </div>
    ` : `
      <div class="px-3.5 py-1.5 rounded-xl bg-cyan-500/20 border border-cyan-400/50 text-cyan-300 font-orbitron font-black text-sm flex items-center gap-2 shrink-0 whitespace-nowrap shadow-lg shadow-cyan-500/15">
        <span class="text-base">🖥️</span>
        <span class="tracking-wider text-white">${pcDisplayName}</span>
      </div>
    `;

    const itemsHTML = (order.items || []).map(item => `
      <div class="flex items-center justify-between text-xs py-2 border-b border-slate-800/60 last:border-0">
        <div class="flex items-center gap-2.5">
          ${item.product_image ? `<img src="${item.product_image}" class="w-8 h-8 rounded-lg object-cover border border-slate-700">` : `<div class="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-xs">🥤</div>`}
          <span class="text-slate-100 font-bold text-xs">${item.product_name}</span>
          <span class="px-2 py-0.5 rounded-md bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold font-mono text-[11px]">x${item.quantity}</span>
        </div>
        <span class="text-slate-200 font-bold font-mono text-xs">${formatMoney(item.unit_price * item.quantity)}</span>
      </div>
    `).join('');

    const timeAgo = new Date(order.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    // order.payment_method_display serverdan keladi va doim o'zbekcha
    // (Django choice label) — shuning uchun til almashtirilganda mos
    // kelmay qolmasligi uchun bu yerda ATAYLAB ishlatilmaydi, buning
    // o'rniga joriy tilga mos kalit orqali hisoblanadi.
    const paymentMethodLabel = t(
      { CASH: 'pm.cash', CARD: 'pm.card', SPLIT: 'pm.split_short', BALANCE: 'pm.balance', FREE: 'pm.free_short' }[order.payment_method] || 'pm.cash'
    );

    return `
      <div class="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3.5 relative hover:border-slate-700 transition-all">
        <!-- Top Row Header -->
        <div class="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-800/80">
          <div class="flex items-center gap-3">
            ${pcBadgeHTML}
            <div>
              <div class="flex items-center gap-2">
                <span class="text-sm font-black text-white font-orbitron">${t('bar.order_number')} #${order.id}</span>
                <span class="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-[10px] font-bold text-slate-400">${paymentMethodLabel}</span>
              </div>
              <div class="text-[11px] text-slate-400 font-mono mt-0.5">${t('bar.order_time')} ${timeAgo}</div>
            </div>
          </div>
          <div>
            ${statusBadge}
          </div>
        </div>

        <!-- Products List & Total -->
        <div class="bg-slate-950/80 p-3.5 rounded-xl border border-slate-800/80 space-y-1">
          ${itemsHTML}
          <div class="flex justify-between items-center pt-2.5 mt-1 border-t border-slate-800/80">
            <span class="text-slate-400 font-bold uppercase tracking-wider text-xs">${t('bar.total_amount')}</span>
            <span class="text-emerald-400 font-orbitron font-black text-lg">${formatMoney(order.total_price)}</span>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center gap-2 pt-1">
          ${order.status === 'PENDING' ? `
            <button onclick="approveOrder(${order.id})" class="flex-1 py-2.5 rounded-xl glow-btn-cyan text-xs font-bold flex items-center justify-center gap-1.5 transition-all">
              ✓ ${t('bar.approve_btn')}
            </button>
            <button onclick="deliverOrder(${order.id})" class="flex-1 py-2.5 rounded-xl glow-btn-emerald text-xs font-bold flex items-center justify-center gap-1.5 transition-all">
              🚚 ${t('bar.deliver_btn')}
            </button>
            <button onclick="cancelOrder(${order.id})" class="py-2.5 px-3.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-bold transition-all">
              ${t('common.cancel')}
            </button>
          ` : order.status === 'APPROVED' ? `
            <button onclick="deliverOrder(${order.id})" class="flex-1 py-2.5 rounded-xl glow-btn-emerald text-xs font-bold flex items-center justify-center gap-1.5 transition-all">
              🚚 ${t('bar.deliver_btn')}
            </button>
            <button onclick="cancelOrder(${order.id})" class="py-2.5 px-3.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-bold transition-all">
              ${t('common.cancel')}
            </button>
          ` : `
            <div class="text-xs text-slate-500 font-mono italic flex items-center gap-1">
              <span>✓ ${t('bar.order_completed')} (${order.status})</span>
            </div>
          `}
        </div>
      </div>
    `;
  }).join('');
}

async function approveOrder(orderId) {
  try {
    const res = await fetch(`/api/orders/${orderId}/approve/`, { method: 'POST' });
    if (res.ok) {
      playSound('add');
      fetchBarOrders();
      fetchAnalytics();
    }
  } catch (err) {
    console.error("Approve order error:", err);
  }
}

async function deliverOrder(orderId) {
  try {
    const res = await fetch(`/api/orders/${orderId}/deliver/`, { method: 'POST' });
    if (res.ok) {
      playSound('start');
      fetchBarOrders();
      fetchAnalytics();
    }
  } catch (err) {
    console.error("Deliver order error:", err);
  }
}

async function cancelOrder(orderId) {
  if (!confirm("Haqiqatan ham ushbu buyurtmani bekor qilmoqchimisiz?")) return;
  try {
    const res = await fetch(`/api/orders/${orderId}/cancel/`, { method: 'POST' });
    if (res.ok) {
      playSound('lock');
      fetchBarOrders();
      fetchAnalytics();
    }
  } catch (err) {
    console.error("Cancel order error:", err);
  }
}

async function fetchAnalytics() {
  try {
    const res = await fetch('/api/orders/analytics/');
    const data = await res.json();

    document.getElementById('analytics-total-revenue').textContent = formatMoney(data.total_revenue || 0);
    document.getElementById('analytics-total-orders').textContent = data.total_orders_count || 0;
    document.getElementById('analytics-low-stock-count').textContent = data.low_stock_count || 0;

    const topSeller = (data.top_selling && data.top_selling.length > 0) ? data.top_selling[0].product__name : "-";
    document.getElementById('analytics-top-seller-name').textContent = topSeller;

    renderInventoryTable(data.inventory || []);
    renderTopSellers(data.top_selling || []);
  } catch (err) {
    console.error("Analytics fetch error:", err);
  }
}

function renderInventoryTable(products) {
  const tbody = document.getElementById('inventory-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  products.forEach(p => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-800/80 hover:bg-slate-900/50 transition-colors text-xs';

    let stockBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">${p.stock} ${t('unit.pcs')}</span>`;
    if (p.stock < 5) {
      stockBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 font-mono animate-pulse">⚠️ ${p.stock} ${t('unit.pcs')} (${t('analytics.low')})</span>`;
    }

    const costPrice = parseFloat(p.cost_price || 0);
    const sellingPrice = parseFloat(p.price || 0);
    const totalAssetVal = costPrice * p.stock;

    tr.innerHTML = `
      <td class="py-3 px-3 whitespace-nowrap">
        <div class="flex items-center gap-2.5">
          <img src="${p.image}" class="w-8 h-8 rounded-lg object-cover border border-slate-700 shrink-0">
          <span class="font-bold text-white text-sm truncate max-w-[160px] sm:max-w-xs inline-block" title="${p.name}">${p.name}</span>
        </div>
      </td>
      <td class="py-3 px-3 text-xs text-slate-400 font-semibold whitespace-nowrap">${p.category_name || t('common.all')}</td>
      <td class="py-3 px-3 font-mono text-amber-400 font-bold whitespace-nowrap">${formatMoney(costPrice)}</td>
      <td class="py-3 px-3 font-mono text-emerald-400 font-bold whitespace-nowrap">${formatMoney(sellingPrice)}</td>
      <td class="py-3 px-3 whitespace-nowrap">${stockBadge}</td>
      <td class="py-3 px-3 font-mono text-slate-300 font-semibold whitespace-nowrap">${formatMoney(totalAssetVal)}</td>
      <td class="py-3 px-3 text-right flex items-center justify-end gap-1.5 whitespace-nowrap">
        <button onclick="openRestockModal(${p.id})" class="py-1 px-2.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-bold transition-all flex items-center gap-1 shrink-0" title="${t('analytics.stock_in')}">
          📦 ${t('analytics.intake_short')}
        </button>
        <button onclick="openSpisaniyeModal(${p.id})" class="py-1 px-2.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-bold transition-all flex items-center gap-1 shrink-0" title="${t('bar.writeoff')}">
          🗑️ ${t('bar.writeoff')}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function renderTopSellers(topSellers) {
  const container = document.getElementById('top-sellers-container');
  if (!container) return;

  if (topSellers.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500">${t('analytics.no_sales')}</div>`;
    return;
  }

  container.innerHTML = topSellers.map((item, idx) => `
    <div class="flex items-center justify-between p-3 rounded-xl bg-slate-950/60 border border-slate-800">
      <div class="flex items-center gap-3">
        <span class="w-6 h-6 rounded-lg bg-cyan-500/20 text-cyan-400 font-orbitron font-bold text-xs flex items-center justify-center">#${idx+1}</span>
        <img src="${item.product__image}" class="w-8 h-8 rounded-lg object-cover border border-slate-700">
        <div>
          <div class="text-xs font-bold text-white">${item.product__name}</div>
          <div class="text-[10px] text-emerald-400 font-mono">${formatMoney(item.total_amount || 0)}</div>
        </div>
      </div>
      <div class="text-right">
        <span class="px-2 py-1 rounded-lg bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-bold font-mono">${item.total_sold} ${t('unit.pcs')}</span>
      </div>
    </div>
  `).join('');
}

// POS Cart state & Direct Sales Logic
let posCart = {};

function addToPOSCart(productId) {
  const prod = cachedProducts.find(p => p.id === productId);
  if (!prod) return;

  if (prod.stock <= 0) {
    alert(`${prod.name} ${t('bar.out_of_stock')}`);
    return;
  }

  const currentQty = posCart[productId] ? posCart[productId].quantity : 0;
  if (currentQty + 1 > prod.stock) {
    alert(`${prod.name} ${t('bar.insufficient_stock')} (${t('bar.available')}: ${prod.stock})`);
    return;
  }

  if (!posCart[productId]) {
    posCart[productId] = {
      product: prod,
      quantity: 1
    };
  } else {
    posCart[productId].quantity++;
  }

  playSound('add');
  renderPOSCart();
}

function updatePOSCartQty(productId, delta) {
  if (!posCart[productId]) return;
  const newQty = posCart[productId].quantity + delta;
  const prod = posCart[productId].product;

  if (newQty <= 0) {
    delete posCart[productId];
  } else {
    if (newQty > prod.stock) {
      alert(`${prod.name} ${t('bar.insufficient_stock')} (${t('bar.available')}: ${prod.stock})`);
      return;
    }
    posCart[productId].quantity = newQty;
  }
  renderPOSCart();
}

function removeFromPOSCart(productId) {
  delete posCart[productId];
  renderPOSCart();
}

function clearPOSCart() {
  posCart = {};
  renderPOSCart();
}

function renderPOSCart() {
  const container = document.getElementById('pos-cart-items');
  const totalDisplay = document.getElementById('pos-cart-total');

  if (!container) return;

  const cartEntries = Object.values(posCart);
  if (cartEntries.length === 0) {
    container.innerHTML = `<div class="text-slate-500 italic text-center py-3">${t('bar.cart_empty')}</div>`;
    if (totalDisplay) totalDisplay.innerText = '0 UZS';
    return;
  }

  let grandTotal = 0;
  container.innerHTML = cartEntries.map(item => {
    const itemTotal = item.product.price * item.quantity;
    grandTotal += itemTotal;
    return `
      <div class="flex items-center justify-between p-2 rounded-lg bg-slate-900 border border-slate-800">
        <div class="truncate font-semibold text-slate-200 text-xs w-28">${item.product.name}</div>
        <div class="flex items-center gap-1.5">
          <button onclick="updatePOSCartQty(${item.product.id}, -1)" class="w-5 h-5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold flex items-center justify-center">-</button>
          <span class="font-mono font-bold text-amber-400 text-xs w-4 text-center">${item.quantity}</span>
          <button onclick="updatePOSCartQty(${item.product.id}, 1)" class="w-5 h-5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold flex items-center justify-center">+</button>
        </div>
        <div class="font-mono text-xs text-slate-300 font-semibold">${formatMoney(itemTotal)}</div>
        <button onclick="removeFromPOSCart(${item.product.id})" class="text-slate-500 hover:text-rose-400 ml-1">✕</button>
      </div>
    `;
  }).join('');

  if (totalDisplay) totalDisplay.innerText = formatMoney(grandTotal);
}

function renderPOSPCDropdown() {
  const select = document.getElementById('pos-pc-select');
  if (!select) return;

  const activePCs = computers.filter(pc => pc.status === 'ACTIVE' || pc.status === 'WARNING');
  if (activePCs.length === 0) {
    select.innerHTML = `<option value="">${t('bar.no_active_pcs')}</option>`;
    return;
  }

  select.innerHTML = activePCs.map(pc => `
    <option value="${pc.id}">${pc.name} (${pc.zone})</option>
  `).join('');
}

async function checkoutDirectPOS(paymentMethod) {
  const cartEntries = Object.values(posCart);
  if (cartEntries.length === 0) {
    alert(t('bar.alert_cart_empty'));
    return;
  }

  const items = cartEntries.map(item => ({
    product_id: item.product.id,
    quantity: item.quantity
  }));

  try {
    const res = await fetch('/api/orders/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        is_direct_sale: true,
        payment_method: paymentMethod,
        items: items
      })
    });

    if (res.ok) {
      playSound('add');
      clearPOSCart();
      fetchBarOrders();
      fetchAnalytics();
      fetchFinanceData();
      productsCacheHTML();
      alert(`${t('bar.alert_direct_sale_ok')} (${paymentMethod === 'CASH' ? t('pm.cash') : t('pm.card')})!`);
    } else {
      const errData = await res.json();
      alert(errData.error || t('bar.alert_sale_error'));
    }
  } catch (err) {
    console.error("Direct POS sale error:", err);
    alert(t('bar.alert_sale_error'));
  }
}

async function checkoutAddToPCSession() {
  const cartEntries = Object.values(posCart);
  if (cartEntries.length === 0) {
    alert(t('bar.alert_cart_empty_select'));
    return;
  }

  const select = document.getElementById('pos-pc-select');
  const pcId = select ? select.value : null;

  if (!pcId) {
    alert(t('bar.alert_select_pc'));
    return;
  }

  const items = cartEntries.map(item => ({
    product_id: item.product.id,
    quantity: item.quantity
  }));

  try {
    const res = await fetch('/api/orders/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        computer: pcId,
        status: 'DELIVERED',
        payment_method: 'CASH',
        items: items
      })
    });

    if (res.ok) {
      playSound('add');
      clearPOSCart();
      fetchBarOrders();
      fetchComputers();
      fetchAnalytics();
      fetchFinanceData();
      productsCacheHTML();
      alert(t('bar.alert_attach_ok'));
    } else {
      const errData = await res.json();
      alert(errData.error || t('bar.alert_attach_error'));
    }
  } catch (err) {
    console.error("Add to PC session error:", err);
    alert(t('bar.alert_attach_error'));
  }
}

// Write-off / Internal Expense (Spisaniye) Modal Logic
function openSpisaniyeModal(productId = null) {
  const modal = document.getElementById('spisaniye-modal');
  const select = document.getElementById('spisaniye-product-select');

  if (!modal || !select) return;

  select.innerHTML = cachedProducts.map(p => `
    <option value="${p.id}" ${productId && p.id === productId ? 'selected' : ''}>${p.name} (Qoldiq: ${p.stock} ta - ${formatMoney(p.price)})</option>
  `).join('');

  modal.classList.remove('hidden');
}

function closeSpisaniyeModal() {
  const modal = document.getElementById('spisaniye-modal');
  if (modal) modal.classList.add('hidden');
}

async function handleSpisaniyeSubmit(e) {
  e.preventDefault();

  const productId = document.getElementById('spisaniye-product-select')?.value;
  const quantity = document.getElementById('spisaniye-quantity')?.value || 1;
  const employeeName = document.getElementById('spisaniye-employee')?.value || 'Shohruh (Barman)';
  const reason = document.getElementById('spisaniye-reason')?.value || 'Ichki rasxod / Spisaniye';
  const submitBtn = document.getElementById('spisaniye-submit-btn');

  if (!productId) return;

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "BAJARILMOQDA...";
  }

  try {
    const res = await fetch('/api/products/internal_expense/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_id: productId,
        quantity: parseInt(quantity),
        employee_name: employeeName,
        reason: reason
      })
    });

    if (res.ok) {
      playSound('alert');
      closeSpisaniyeModal();
      productsCacheHTML();
      fetchAnalytics();
      fetchFinanceData();
      alert("Spisaniye muvaffaqiyatli bajarildi va Chiqim jurnaliga yozildi!");
    } else {
      const errData = await res.json();
      alert(errData.error || "Spisaniye xatoligi!");
    }
  } catch (err) {
    console.error("Spisaniye error:", err);
    alert("Spisaniyeda xatolik yuz berdi!");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "SPISANIYE QILISH";
    }
  }
}

function renderBarPOSProducts() {
  const container = document.getElementById('bar-pos-products-list');
  if (!container) return;

  container.innerHTML = barOrders.length >= 0 ? productsCacheHTML() : '';
}

let cachedProducts = [];
async function productsCacheHTML() {
  const container = document.getElementById('bar-pos-products-list');
  if (!container) return;

  try {
    const res = await fetch('/api/products/');
    cachedProducts = await res.json();
    container.innerHTML = cachedProducts.map(p => `
      <div class="flex items-center justify-between p-2 rounded-xl bg-slate-950/60 border border-slate-800 text-xs">
        <div class="flex items-center gap-2">
          <img src="${p.image}" class="w-7 h-7 rounded-lg object-cover">
          <div>
            <div class="font-bold text-white leading-tight">${p.name}</div>
            <div class="text-[10px] text-slate-400 font-mono">${formatMoney(p.price)}</div>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <span class="px-1.5 py-0.5 rounded font-mono text-[10px] ${p.stock < 5 ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-slate-900 text-slate-300'}">
            ${p.stock} ta
          </span>
          <button onclick="addToPOSCart(${p.id})" class="px-2 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/40 font-bold text-[10px]" title="Savatga qo'shish">
            + Sabat
          </button>
          <button onclick="openSpisaniyeModal(${p.id})" class="px-1.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 font-bold text-[10px]" title="Spisaniye (Ichki rasxod)">
            🗑️
          </button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Products cache error:", err);
  }
}

async function restockProduct(productId, qty) {
  try {
    const res = await fetch(`/api/products/${productId}/restock/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity: qty })
    });
    if (res.ok) {
      playSound('add');
      fetchAnalytics();
      productsCacheHTML();
    }
  } catch (err) {
    console.error("Restock error:", err);
  }
}

// Kassa & Cashflow Accounting Logic
let currentFinancePeriod = 'daily';

function openExpenseModal() {
  const modal = document.getElementById('expense-modal');
  if (modal) modal.classList.remove('hidden');
}

function closeExpenseModal() {
  const modal = document.getElementById('expense-modal');
  if (modal) modal.classList.add('hidden');
}

function setFinancePeriod(period) {
  currentFinancePeriod = period;

  document.querySelectorAll('.finance-period-btn').forEach(btn => {
    btn.className = 'finance-period-btn px-3.5 py-1.5 rounded-xl text-xs font-bold bg-slate-900 text-slate-400 hover:text-white border border-slate-800 transition-all';
  });

  const activeBtn = document.getElementById(`btn-period-${period}`);
  if (activeBtn) {
    activeBtn.className = 'finance-period-btn px-3.5 py-1.5 rounded-xl text-xs font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 transition-all';
  }

  fetchFinanceData();
}

async function fetchFinanceData() {
  try {
    let periodQs = `period=${currentFinancePeriod}`;
    if (currentFinancePeriod === 'custom') {
      const df = document.getElementById('finance-date-from')?.value;
      const dt = document.getElementById('finance-date-to')?.value;
      if (df) periodQs += `&date_from=${df}`;
      if (dt) periodQs += `&date_to=${dt}`;
    }

    const res = await fetch(`/api/expenses/cashflow/?${periodQs}`);
    if (res.ok) {
      const data = await res.json();
      renderFinanceDashboard(data);
    }

    const ledgerRes = await fetch(`/api/expenses/kassa_report/?${periodQs}`);
    if (ledgerRes.ok) {
      const ledgerData = await ledgerRes.json();
      renderKassaLedger(ledgerData);
    }
  } catch (err) {
    console.error("Fetch finance error:", err);
  }
}

function renderKassaLedger(data) {
  const openingEl = document.getElementById('kassa-ledger-opening');
  const currentEl = document.getElementById('kassa-ledger-current');
  const tbody = document.getElementById('kassa-ledger-table-body');

  if (openingEl) openingEl.textContent = formatMoney(data.opening_balance || 0);
  if (currentEl) currentEl.textContent = formatMoney(data.current_kassa || 0);

  if (!tbody) return;

  const ledger = data.ledger || [];
  if (ledger.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-xs text-slate-500">Ushbu davrda kassa harakati mavjud emas</td></tr>`;
    return;
  }

  tbody.innerHTML = ledger.map(row => `
    <tr class="border-b border-slate-800/60 hover:bg-slate-900/50 transition-all text-xs">
      <td class="py-2.5 px-3 font-mono text-slate-400 whitespace-nowrap">${row.date}</td>
      <td class="py-2.5 px-3 text-slate-200 whitespace-nowrap">${row.detail}</td>
      <td class="py-2.5 px-3 font-bold font-orbitron whitespace-nowrap ${row.income ? 'text-emerald-400' : 'text-slate-600'}">${row.income ? '+' + formatMoney(row.income) : '—'}</td>
      <td class="py-2.5 px-3 font-bold font-orbitron whitespace-nowrap ${row.expense ? 'text-rose-400' : 'text-slate-600'}">${row.expense ? '-' + formatMoney(row.expense) : '—'}</td>
      <td class="py-2.5 px-3 font-bold font-orbitron text-white whitespace-nowrap">${formatMoney(row.balance)}</td>
    </tr>
  `).join('');
}

function renderFinanceDashboard(data) {
  const cashBalEl = document.getElementById('finance-cash-balance');
  const cardBalEl = document.getElementById('finance-card-balance');
  const totalBalEl = document.getElementById('finance-total-balance');
  const totalExpEl = document.getElementById('finance-total-expenses');
  const expBreakdownEl = document.getElementById('finance-expenses-breakdown');

  const cashBal = data.cash_balance || 0;
  const cardBal = data.card_balance || 0;
  const totalBal = data.total_balance || 0;
  const totalExp = data.total_expenses || 0;

  if (cashBalEl) {
    if (cashBal > 0) {
      cashBalEl.textContent = `+${formatMoney(cashBal)}`;
      cashBalEl.className = "text-base font-black font-orbitron text-emerald-400 mt-1 truncate";
    } else if (cashBal < 0) {
      cashBalEl.textContent = `-${formatMoney(Math.abs(cashBal))}`;
      cashBalEl.className = "text-base font-black font-orbitron text-rose-400 mt-1 truncate";
    } else {
      cashBalEl.textContent = `0 UZS`;
      cashBalEl.className = "text-base font-black font-orbitron text-slate-400 mt-1 truncate";
    }
  }

  if (cardBalEl) {
    if (cardBal > 0) {
      cardBalEl.textContent = `+${formatMoney(cardBal)}`;
      cardBalEl.className = "text-base font-black font-orbitron text-cyan-400 mt-1 truncate";
    } else if (cardBal < 0) {
      cardBalEl.textContent = `-${formatMoney(Math.abs(cardBal))}`;
      cardBalEl.className = "text-base font-black font-orbitron text-rose-400 mt-1 truncate";
    } else {
      cardBalEl.textContent = `0 UZS`;
      cardBalEl.className = "text-base font-black font-orbitron text-slate-400 mt-1 truncate";
    }
  }

  if (totalBalEl) {
    if (totalBal > 0) {
      totalBalEl.textContent = `+${formatMoney(totalBal)}`;
      totalBalEl.className = "text-base font-black font-orbitron text-purple-400 mt-1 truncate";
    } else if (totalBal < 0) {
      totalBalEl.textContent = `-${formatMoney(Math.abs(totalBal))}`;
      totalBalEl.className = "text-base font-black font-orbitron text-rose-400 mt-1 truncate";
    } else {
      totalBalEl.textContent = `0 UZS`;
      totalBalEl.className = "text-base font-black font-orbitron text-slate-400 mt-1 truncate";
    }
  }

  if (totalExpEl) {
    totalExpEl.textContent = totalExp > 0 ? `-${formatMoney(totalExp)}` : `0 UZS`;
  }
  if (expBreakdownEl) {
    const expCash = data.expense_cash || 0;
    const expCard = data.expense_card || 0;
    expBreakdownEl.textContent = `Naqd: ${expCash > 0 ? '-' : ''}${formatMoney(expCash)} | Card: ${expCard > 0 ? '-' : ''}${formatMoney(expCard)}`;
  }

  const barRevEl = document.getElementById('finance-bar-revenue');
  const barCogsEl = document.getElementById('finance-bar-cogs');
  const barMarginEl = document.getElementById('finance-bar-margin');
  const barMarginPctEl = document.getElementById('finance-bar-margin-pct');

  if (barRevEl) barRevEl.textContent = (data.total_bar > 0 ? '+' : '') + formatMoney(data.total_bar || 0);
  if (barCogsEl) barCogsEl.textContent = (data.bar_cogs > 0 ? '-' : '') + formatMoney(data.bar_cogs || 0);
  if (barMarginEl) barMarginEl.textContent = (data.bar_margin > 0 ? '+' : data.bar_margin < 0 ? '-' : '') + formatMoney(Math.abs(data.bar_margin || 0));
  if (barMarginPctEl) barMarginPctEl.textContent = `${data.bar_margin_percent || 0}%`;

  const sessCashEl = document.getElementById('breakdown-session-cash');
  const sessCardEl = document.getElementById('breakdown-session-card');
  const barCashEl = document.getElementById('breakdown-bar-cash');
  const barCardEl = document.getElementById('breakdown-bar-card');

  if (sessCashEl) sessCashEl.textContent = (data.session_cash > 0 ? '+' : '') + formatMoney(data.session_cash || 0);
  if (sessCardEl) sessCardEl.textContent = (data.session_card > 0 ? '+' : '') + formatMoney(data.session_card || 0);
  if (barCashEl) barCashEl.textContent = (data.bar_cash > 0 ? '+' : '') + formatMoney(data.bar_cash || 0);
  if (barCardEl) barCardEl.textContent = (data.bar_card > 0 ? '+' : '') + formatMoney(data.bar_card || 0);

  const topupCashEl = document.getElementById('breakdown-topup-cash');
  const topupCardEl = document.getElementById('breakdown-topup-card');
  if (topupCashEl) topupCashEl.textContent = (data.topup_cash > 0 ? '+' : '') + formatMoney(data.topup_cash || 0);
  if (topupCardEl) topupCardEl.textContent = (data.topup_card > 0 ? '+' : '') + formatMoney(data.topup_card || 0);

  // Render Recent Sales Table
  const salesTbody = document.getElementById('sales-table-body');
  const recentSales = data.recent_sales || [];

  if (salesTbody) {
    if (recentSales.length === 0) {
      salesTbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-xs text-slate-500">Ushbu davrda savdolar mavjud emas</td></tr>`;
    } else {
      salesTbody.innerHTML = recentSales.map(s => {
        const pmColors = {
          CASH: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
          CARD: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
          SPLIT: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
          BALANCE: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
          FREE: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
        };
        const pmClass = pmColors[s.payment_method] || pmColors.SPLIT;
        const pmBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold border ${pmClass}">${s.payment_method_display || s.payment_method}</span>`;
        const typeBadges = {
          SESSION: `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">🎮 Seans</span>`,
          BAR: `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">🍸 Bar</span>`,
          TOPUP: `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">👛 To'ldirish</span>`,
        };
        const typeBadge = typeBadges[s.type] || typeBadges.BAR;
        const balanceNote = s.payment_method === 'FREE'
          ? `<div class="text-[9px] text-pink-400 font-semibold mt-0.5">Bepul (Comp) — kassaga yangi pul qo'shilmaydi</div>`
          : s.from_balance
            ? `<div class="text-[9px] text-indigo-400 font-semibold mt-0.5">Balansdan — kassaga yangi pul qo'shilmaydi</div>`
            : '';

        return `
          <tr class="border-b border-slate-800/60 hover:bg-slate-900/50 transition-all text-xs">
            <td class="py-2.5 px-3 font-bold text-white font-orbitron whitespace-nowrap">${s.client_name}</td>
            <td class="py-2.5 px-3 whitespace-nowrap">${typeBadge}</td>
            <td class="py-2.5 px-3 whitespace-nowrap">${pmBadge}</td>
            <td class="py-2.5 px-3 font-bold ${s.from_balance ? 'text-indigo-300' : 'text-emerald-400'} font-orbitron whitespace-nowrap">+${formatMoney(s.amount)}</td>
            <td class="py-2.5 px-3 text-slate-400 whitespace-nowrap">
              <div class="font-mono text-[11px] text-slate-300">${s.created_at}</div>
              <div class="text-[10px] text-slate-500 truncate max-w-[160px]">${s.details}</div>
              ${balanceNote}
            </td>
          </tr>
        `;
      }).join('');
    }
  }

  // Render Expenses Table
  const countBadge = document.getElementById('expenses-count-badge');
  const expTbody = document.getElementById('expenses-table-body');
  const expenses = data.expenses || [];

  if (countBadge) countBadge.textContent = `${expenses.length} ta chiqim`;

  if (expTbody) {
    if (expenses.length === 0) {
      expTbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-xs text-slate-500">Ushbu davrda chiqimlar mavjud emas</td></tr>`;
    } else {
      expTbody.innerHTML = expenses.map(e => {
        const formattedDate = new Date(e.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
        const expPmColors = {
          CASH: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
          CARD: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
          FREE: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
        };
        const expPmClass = expPmColors[e.payment_method] || expPmColors.CARD;
        return `
          <tr class="border-b border-slate-800/60 hover:bg-slate-900/50 transition-all text-xs">
            <td class="py-2.5 px-2.5 font-mono text-slate-400 whitespace-nowrap">${formattedDate}</td>
            <td class="py-2.5 px-2.5 whitespace-nowrap">
              <div class="font-bold text-cyan-300 text-xs">${e.category || 'Boshqa'}</div>
              <div class="text-[10px] text-slate-400">${e.recipient_name || '-'}</div>
            </td>
            <td class="py-2.5 px-2.5 whitespace-nowrap">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${expPmClass}">
                ${e.payment_method_display || e.payment_method}
              </span>
              ${e.payment_method === 'FREE' ? `<div class="text-[9px] text-pink-400 font-semibold mt-0.5">Kassadan pul chiqmagan</div>` : ''}
            </td>
            <td class="py-2.5 px-2.5 font-bold text-rose-400 font-orbitron whitespace-nowrap">-${formatMoney(Math.abs(parseFloat(e.amount || 0)))}</td>
            <td class="py-2.5 px-2.5 text-slate-400 max-w-[150px] truncate" title="${e.description || ''}">${e.description || '-'}</td>
            <td class="py-2.5 px-2.5 text-right whitespace-nowrap">
              <button onclick="handleDeleteExpense(${e.id})" class="text-rose-400 hover:text-rose-300 p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-all">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }
  }
}

async function handleCreateExpense(e) {
  if (e) e.preventDefault();
  const amountInput = document.getElementById('expense-amount-input');
  const recipientInput = document.getElementById('expense-recipient-input');
  const descInput = document.getElementById('expense-description-input');

  const amount = parseFloat(amountInput.value) || 0;
  const paymentMethod = document.getElementById('expense-payment-method').value || 'CASH';
  const category = document.getElementById('expense-category-input').value || 'Boshqa Chiqim';
  const recipientName = recipientInput.value.trim();
  const description = descInput.value.trim();

  if (amount <= 0) {
    alert("Iltimos, musbat summa kiriting!");
    return;
  }

  try {
    const res = await fetch('/api/expenses/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || ''
      },
      body: JSON.stringify({
        amount: amount,
        payment_method: paymentMethod,
        category: category,
        recipient_name: recipientName,
        description: description
      })
    });

    if (res.ok) {
      playSound('add');
      closeExpenseModal();
      amountInput.value = '';
      recipientInput.value = '';
      descInput.value = '';
      fetchFinanceData();
    } else {
      const errData = await res.json().catch(() => ({}));
      console.error("Create expense error response:", errData);
      alert("Chiqimni saqlashda xatolik yuz berdi!");
    }
  } catch (err) {
    console.error("Create expense error:", err);
  }
}

async function handleDeleteExpense(id) {
  if (!confirm("Ushbu chiqim yozuvini o'chirmoqchimisiz?")) return;

  try {
    const res = await fetch(`/api/expenses/${id}/`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': getCookie('csrftoken') || ''
      }
    });
    if (res.ok) {
      playSound('lock');
      fetchFinanceData();
    }
  } catch (err) {
    console.error("Delete expense error:", err);
  }
}

// Restock Modal & StockSupply Functions
let currentRestockMode = 'existing';

function toggleRestockProductMode(mode) {
  currentRestockMode = mode;
  const existingContainer = document.getElementById('restock-existing-container');
  const newContainer = document.getElementById('restock-new-container');
  const tabExisting = document.getElementById('restock-tab-existing');
  const tabNew = document.getElementById('restock-tab-new');
  const select = document.getElementById('restock-product-select');
  const newNameInput = document.getElementById('restock-new-product-name');
  const costInput = document.getElementById('restock-cost-price');
  const priceInput = document.getElementById('restock-selling-price');

  if (mode === 'existing') {
    if (existingContainer) existingContainer.classList.remove('hidden');
    if (newContainer) newContainer.classList.add('hidden');
    
    if (tabExisting) tabExisting.className = "px-2.5 py-1 rounded-md text-xs font-semibold transition-all bg-cyan-500/20 text-cyan-400 border border-cyan-500/40";
    if (tabNew) tabNew.className = "px-2.5 py-1 rounded-md text-xs font-semibold transition-all text-slate-400 hover:text-white border border-transparent";
    
    if (select) {
      if (select.value === '__NEW__') select.value = '';
      onRestockProductSelect();
    }
  } else {
    if (existingContainer) existingContainer.classList.add('hidden');
    if (newContainer) newContainer.classList.remove('hidden');

    if (tabNew) tabNew.className = "px-2.5 py-1 rounded-md text-xs font-semibold transition-all bg-cyan-500/20 text-cyan-400 border border-cyan-500/40";
    if (tabExisting) tabExisting.className = "px-2.5 py-1 rounded-md text-xs font-semibold transition-all text-slate-400 hover:text-white border border-transparent";

    if (select) select.value = '__NEW__';
    if (costInput) costInput.value = '0';
    if (priceInput) priceInput.value = '0';
    if (newNameInput) {
      newNameInput.focus();
    }
  }
  updateRestockCalc();
}

function openRestockModal(productId = null) {
  const modal = document.getElementById('modal-restock');
  const select = document.getElementById('restock-product-select');
  const nameInput = document.getElementById('restock-product-name');
  const newNameInput = document.getElementById('restock-new-product-name');
  const costInput = document.getElementById('restock-cost-price');
  const priceInput = document.getElementById('restock-selling-price');

  if (!modal || !select) return;

  select.innerHTML = `
    <option value="">-- Ro'yxatdan Mahsulotni Tanlang --</option>
    <option value="__NEW__">➕ Yangi Mahsulot Qo'shish...</option>
    ${cachedProducts.map(p => `<option value="${p.id}" ${productId === p.id ? 'selected' : ''}>${p.name} (Tannarx: ${formatMoney(p.cost_price || 0)} | Sotish: ${formatMoney(p.price)})</option>`).join('')}
  `;

  if (newNameInput) newNameInput.value = '';
  if (nameInput) nameInput.value = '';
  const newImageInput = document.getElementById('restock-new-product-image');
  if (newImageInput) newImageInput.value = '';

  if (productId) {
    toggleRestockProductMode('existing');
    select.value = productId;
    onRestockProductSelect();
  } else {
    toggleRestockProductMode('existing');
    select.value = '';
    if (costInput) costInput.value = '0';
    if (priceInput) priceInput.value = '0';
    updateRestockCalc();
  }

  modal.classList.remove('hidden');
}

function closeRestockModal() {
  const modal = document.getElementById('modal-restock');
  if (modal) modal.classList.add('hidden');
}

function onRestockProductSelect() {
  const select = document.getElementById('restock-product-select');
  const nameInput = document.getElementById('restock-product-name');
  const costInput = document.getElementById('restock-cost-price');
  const priceInput = document.getElementById('restock-selling-price');

  if (!select) return;

  const productId = select.value;
  if (productId === '__NEW__') {
    toggleRestockProductMode('new');
    return;
  }

  if (!productId) {
    if (nameInput) nameInput.value = '';
    if (costInput) costInput.value = '0';
    if (priceInput) priceInput.value = '0';
    updateRestockCalc();
    return;
  }

  const p = cachedProducts.find(prod => prod.id == productId);
  if (p) {
    if (nameInput) nameInput.value = p.name;
    if (costInput) costInput.value = p.cost_price || 0;
    if (priceInput) priceInput.value = p.price || 0;
    updateRestockCalc();
  }
}

function updateRestockCalc() {
  const qty = parseInt(document.getElementById('restock-quantity')?.value) || 0;
  const costPrice = parseFloat(document.getElementById('restock-cost-price')?.value) || 0;
  const sellingPrice = parseFloat(document.getElementById('restock-selling-price')?.value) || 0;

  const totalCost = qty * costPrice;
  const unitProfit = sellingPrice - costPrice;

  const totalCostEl = document.getElementById('restock-calc-total-cost');
  const unitProfitEl = document.getElementById('restock-calc-unit-profit');

  if (totalCostEl) totalCostEl.textContent = formatMoney(totalCost);
  if (unitProfitEl) unitProfitEl.textContent = formatMoney(unitProfit);
}

async function handleRestockSubmit(e) {
  e.preventDefault();

  const selectVal = document.getElementById('restock-product-select')?.value || '';
  const newNameInputVal = document.getElementById('restock-new-product-name')?.value.trim() || '';
  const newImageInputVal = document.getElementById('restock-new-product-image')?.value.trim() || '';

  let productId = null;
  let productName = '';

  if (currentRestockMode === 'new' || selectVal === '__NEW__') {
    if (!newNameInputVal) {
      alert("Iltimos, yangi mahsulot nomini kiriting!");
      document.getElementById('restock-new-product-name')?.focus();
      return;
    }
    productName = newNameInputVal;
  } else {
    if (!selectVal) {
      alert("Iltimos, ro'yxatdan mahsulotni tanlang yoki '+ Yangi Mahsulot' tugmasini bosing!");
      return;
    }
    productId = selectVal;
    const selectedProd = cachedProducts.find(p => p.id == productId);
    productName = selectedProd ? selectedProd.name : (document.getElementById('restock-product-name')?.value || '');
  }

  const quantity = parseInt(document.getElementById('restock-quantity')?.value) || 1;
  const costPrice = parseFloat(document.getElementById('restock-cost-price')?.value) || 0;
  const sellingPrice = parseFloat(document.getElementById('restock-selling-price')?.value) || 0;
  const paymentMethod = document.getElementById('restock-payment-method')?.value || 'CASH';
  const supplierNote = document.getElementById('restock-supplier-note')?.value || '';
  const submitBtn = document.getElementById('restock-submit-btn');

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "SAQLANMOQDA...";
  }

  try {
    const res = await fetch('/api/stock-supplies/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_id: productId,
        product_name: productName,
        product_image: newImageInputVal,
        quantity: quantity,
        cost_price: costPrice,
        selling_price: sellingPrice,
        payment_method: paymentMethod,
        supplier_note: supplierNote
      })
    });

    if (res.ok) {
      playSound('add');
      closeRestockModal();
      productsCacheHTML();
      fetchAnalytics();
      fetchFinanceData();
      alert(`Kirim muvaffaqiyatli saqlandi! (${quantity}x ${productName} - Jami: ${formatMoney(quantity * costPrice)})`);
    } else {
      const errData = await res.json();
      alert(errData.error || "Kirimni saqlashda xatolik!");
    }
  } catch (err) {
    console.error("Restock submit error:", err);
    alert("Kirimni saqlashda xatolik yuz berdi!");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "KIRIMNI SAQLASH";
    }
  }
}

function openStockHistoryModal() {
  const modal = document.getElementById('modal-stock-history');
  if (modal) {
    modal.classList.remove('hidden');
    fetchStockHistory();
  }
}

function closeStockHistoryModal() {
  const modal = document.getElementById('modal-stock-history');
  if (modal) modal.classList.add('hidden');
}

async function fetchStockHistory() {
  const tbody = document.getElementById('stock-history-table-body');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-xs text-slate-500">Yuklanmoqda...</td></tr>`;

  try {
    const res = await fetch('/api/stock-supplies/');
    if (res.ok) {
      const supplies = await res.json();
      if (supplies.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-xs text-slate-500">Kirimlar tarixi yo'q</td></tr>`;
        return;
      }

      tbody.innerHTML = supplies.map(s => `
        <tr class="border-b border-slate-800 hover:bg-slate-900/50 transition-colors whitespace-nowrap text-xs">
          <td class="py-2.5 px-3 text-slate-400 font-mono whitespace-nowrap">${new Date(s.created_at).toLocaleString('uz-UZ')}</td>
          <td class="py-2.5 px-3 font-bold text-white max-w-[150px] truncate" title="${s.product_name}">${s.product_name}</td>
          <td class="py-2.5 px-3 font-mono text-cyan-400 font-bold whitespace-nowrap">+${s.quantity} ta</td>
          <td class="py-2.5 px-3 font-mono text-amber-400 whitespace-nowrap">${formatMoney(s.cost_price)}</td>
          <td class="py-2.5 px-3 font-mono text-emerald-400 whitespace-nowrap">${formatMoney(s.selling_price)}</td>
          <td class="py-2.5 px-3 font-mono text-rose-400 font-bold whitespace-nowrap">${formatMoney(s.total_cost)}</td>
          <td class="py-2.5 px-3 whitespace-nowrap">
            ${s.payment_method === 'CASH' ?
              '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold">💵 Naqd</span>' :
              '<span class="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 font-bold">💳 Plastik</span>'}
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error("Stock history fetch error:", err);
  }
}




// ══════════════════════════════════════════════════════════════════
//  MIJOZLAR (Customers / Membership)
// ══════════════════════════════════════════════════════════════════
let customerSearchDebounce = null;
let activeCustomerId = null;

function onCustomerSearchInput() {
  clearTimeout(customerSearchDebounce);
  customerSearchDebounce = setTimeout(fetchCustomers, 300);
}

async function fetchCustomers() {
  const tbody = document.getElementById('customers-table-body');
  if (!tbody) return;
  const search = document.getElementById('customer-search-input')?.value.trim() || '';
  try {
    const url = search ? `/api/customers/?search=${encodeURIComponent(search)}` : '/api/customers/';
    const res = await fetch(url);
    if (!res.ok) return;
    const customers = await res.json();
    renderCustomers(customers);
  } catch (err) {
    console.error("Customers fetch error:", err);
  }
}

function renderCustomers(customers) {
  const tbody = document.getElementById('customers-table-body');
  if (!customers.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-xs text-slate-500">Mijozlar topilmadi</td></tr>`;
    return;
  }
  tbody.innerHTML = customers.map(c => `
    <tr class="border-b border-slate-800 hover:bg-slate-900/50 transition-colors whitespace-nowrap text-xs">
      <td class="py-2.5 px-2.5 font-bold text-white">${c.full_name}</td>
      <td class="py-2.5 px-2.5 font-mono text-slate-300">${c.phone}</td>
      <td class="py-2.5 px-2.5 font-mono font-bold text-emerald-400">${formatMoney(c.balance)}</td>
      <td class="py-2.5 px-2.5 font-mono text-amber-400">${c.bonus_points} ball</td>
      <td class="py-2.5 px-2.5 font-mono text-slate-300">${formatMoney(c.total_spent)}</td>
      <td class="py-2.5 px-2.5 font-mono text-slate-400">${c.session_count}</td>
      <td class="py-2.5 px-2.5 text-right">
        <button onclick="openCustomerModal(${c.id})" class="px-2.5 py-1 rounded-lg bg-pink-600/20 hover:bg-pink-600/30 border border-pink-500/40 text-pink-400 text-xs font-bold transition-all">Ochish</button>
      </td>
    </tr>
  `).join('');
}

async function openCustomerModal(customerId) {
  activeCustomerId = customerId || null;
  document.getElementById('customer-id-input').value = customerId || '';
  document.getElementById('customer-modal-error').classList.add('hidden');
  const balanceSection = document.getElementById('customer-balance-section');

  if (customerId) {
    document.getElementById('customer-modal-title').textContent = 'Mijozni tahrirlash';
    balanceSection.classList.remove('hidden');
    try {
      const res = await fetch(`/api/customers/${customerId}/`);
      const c = res.ok ? await res.json() : null;
      if (c) {
        document.getElementById('customer-name-input').value = c.full_name;
        document.getElementById('customer-phone-input').value = c.phone;
        document.getElementById('customer-notes-input').value = c.notes || '';
        document.getElementById('customer-modal-balance').textContent = formatMoney(c.balance);
        document.getElementById('customer-modal-points').textContent = c.bonus_points || 0;
      }
    } catch (err) { console.error(err); }
    loadCustomerTransactions(customerId);
  } else {
    document.getElementById('customer-modal-title').textContent = 'Yangi mijoz';
    balanceSection.classList.add('hidden');
    document.getElementById('customer-name-input').value = '';
    document.getElementById('customer-phone-input').value = '';
    document.getElementById('customer-notes-input').value = '';
  }
  document.getElementById('customer-tx-amount').value = '';
  document.getElementById('customer-modal').classList.remove('hidden');
}

function closeCustomerModal() {
  document.getElementById('customer-modal').classList.add('hidden');
  activeCustomerId = null;
}

async function saveCustomer() {
  const errEl = document.getElementById('customer-modal-error');
  errEl.classList.add('hidden');
  const fullName = document.getElementById('customer-name-input').value.trim();
  const phone = document.getElementById('customer-phone-input').value.trim();
  const notes = document.getElementById('customer-notes-input').value.trim();

  if (!fullName || !phone) {
    errEl.textContent = "Ism va telefon raqamini kiriting!";
    errEl.classList.remove('hidden');
    return;
  }

  const isEdit = !!activeCustomerId;
  const url = isEdit ? `/api/customers/${activeCustomerId}/` : '/api/customers/';
  const method = isEdit ? 'PATCH' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: fullName, phone, notes })
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      errEl.textContent = data.phone ? "Bu telefon raqami allaqachon ro'yxatdan o'tgan!" : "Xato yuz berdi, qayta urinib ko'ring.";
      errEl.classList.remove('hidden');
      return;
    }
    closeCustomerModal();
    fetchCustomers();
  } catch (err) {
    errEl.textContent = "Tarmoq xatosi.";
    errEl.classList.remove('hidden');
  }
}

async function resetCustomerPassword() {
  if (!activeCustomerId) return;
  if (!confirm("Bu mijozning kiosk paroli tozalanadi — keyingi safar kirganda yangi parol o'rnatishi kerak bo'ladi. Davom etilsinmi?")) return;
  try {
    const res = await fetch(`/api/customers/${activeCustomerId}/reset_password/`, { method: 'POST' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "Xato yuz berdi");
      return;
    }
    alert("Parol tozalandi. Mijoz keyingi safar kiosk'da kirganda yangi parol o'rnatadi.");
  } catch (err) {
    console.error(err);
  }
}

async function customerTopUp() {
  await customerBalanceOp('top_up');
}

async function customerSpend() {
  await customerBalanceOp('spend');
}

async function customerBalanceOp(action) {
  if (!activeCustomerId) return;
  const amountInput = document.getElementById('customer-tx-amount');
  const amount = parseFloat(amountInput.value);
  if (!amount || amount <= 0) {
    alert("Summani to'g'ri kiriting!");
    return;
  }
  const body = { amount };
  if (action === 'top_up') {
    body.payment_method = document.getElementById('customer-topup-method')?.value || 'CASH';
  }
  try {
    const res = await fetch(`/api/customers/${activeCustomerId}/${action}/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Xato yuz berdi");
      return;
    }
    document.getElementById('customer-modal-balance').textContent = formatMoney(data.balance);
    document.getElementById('customer-modal-points').textContent = data.bonus_points || 0;
    amountInput.value = '';
    loadCustomerTransactions(activeCustomerId);
    fetchCustomers();
  } catch (err) {
    console.error(err);
  }
}

async function loadCustomerTransactions(customerId) {
  const list = document.getElementById('customer-tx-list');
  try {
    const res = await fetch(`/api/customers/${customerId}/transactions/`);
    if (!res.ok) return;
    const txs = await res.json();
    if (!txs.length) {
      list.innerHTML = `<div class="text-slate-500 text-xs py-2">${t('customer_modal.no_transactions')}</div>`;
      return;
    }
    list.innerHTML = txs.map(tx => `
      <div class="flex items-center justify-between gap-2 py-1.5 border-b border-slate-800/60 last:border-b-0">
        <div class="min-w-0">
          <div class="text-slate-300 font-semibold truncate">${tx.note || tx.type_display || ''}</div>
          <div class="text-slate-500 text-[10px]">${new Date(tx.created_at).toLocaleString('uz-UZ')}</div>
        </div>
        <span class="font-mono font-bold shrink-0 ${(tx.type === 'TOPUP' || tx.type === 'BONUS') ? 'text-emerald-400' : 'text-rose-400'}">
          ${(tx.type === 'TOPUP' || tx.type === 'BONUS') ? '+' : '−'}${formatMoney(tx.amount)}
        </span>
      </div>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}


// ══════════════════════════════════════════════════════════════════
//  FAOLIYAT JURNALI (Audit Log)
// ══════════════════════════════════════════════════════════════════
async function fetchAuditLog() {
  const tbody = document.getElementById('auditlog-table-body');
  if (!tbody) return;
  try {
    const res = await fetch('/api/audit-logs/');
    if (!res.ok) return;
    const logs = await res.json();
    renderAuditLog(logs);
  } catch (err) {
    console.error("Audit log fetch error:", err);
  }
}

function renderAuditLog(logs) {
  const tbody = document.getElementById('auditlog-table-body');
  if (!logs.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-xs text-slate-500">Hali yozuvlar yo'q</td></tr>`;
    return;
  }
  tbody.innerHTML = logs.map(l => `
    <tr class="border-b border-slate-800 hover:bg-slate-900/50 transition-colors whitespace-nowrap text-xs">
      <td class="py-2.5 px-2.5 text-slate-400 font-mono">${new Date(l.created_at).toLocaleString('uz-UZ')}</td>
      <td class="py-2.5 px-2.5 font-bold text-cyan-400">${l.username || 'tizim'}</td>
      <td class="py-2.5 px-2.5"><span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-semibold">${l.action_display}</span></td>
      <td class="py-2.5 px-2.5 text-slate-300 whitespace-normal">${l.description}</td>
    </tr>
  `).join('');
}
