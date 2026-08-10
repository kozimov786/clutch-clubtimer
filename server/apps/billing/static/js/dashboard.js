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

function isDaytimeDiscountActive() {
  const hour = new Date().getHours();
  return hour >= 10 && hour < 18;
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
  document.getElementById('stat-revenue').textContent = formatMoney(revenue);

  const isDaytime = isDaytimeDiscountActive();
  const discountBanner = document.getElementById('daytime-discount-badge');
  if (discountBanner) {
    if (isDaytime) {
      discountBanner.className = "flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs font-bold font-orbitron animate-pulse";
      discountBanner.innerHTML = `☀️ KUNDUZGI 50% CHEGIRMA (10:00 - 18:00)`;
    } else {
      discountBanner.className = "flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 text-slate-400 border border-slate-800 text-xs font-semibold";
      discountBanner.innerHTML = `🌙 TUNGITARIF (18:00 - 10:00)`;
    }
  }
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

  document.getElementById('tab-view-grid').classList.toggle('hidden', tabName !== 'grid');
  document.getElementById('tab-view-tariffs').classList.toggle('hidden', tabName !== 'tariffs');
  document.getElementById('tab-view-sessions').classList.toggle('hidden', tabName !== 'sessions');
  document.getElementById('tab-view-bar').classList.toggle('hidden', tabName !== 'bar');
  document.getElementById('tab-view-analytics').classList.toggle('hidden', tabName !== 'analytics');
  const finTab = document.getElementById('tab-view-finance');
  if (finTab) finTab.classList.toggle('hidden', tabName !== 'finance');

  if (tabName === 'bar') fetchBarOrders();
  if (tabName === 'analytics') fetchAnalytics();
  if (tabName === 'finance') fetchFinanceData();
}


// Ultra Sleek Modern PC Card Generator
function generatePCCardHTML(pc) {
  let statusClass = 'card-status-locked';
  let statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> LOCKED</span>`;
  
  if (pc.status === 'ACTIVE') {
    if (pc.is_open_time) {
      statusClass = 'card-status-active';
      statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 flex items-center gap-1.5 animate-pulse"><span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span> OPEN TIME</span>`;
    } else {
      statusClass = 'card-status-active';
      statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> ACTIVE</span>`;
    }
  } else if (pc.status === 'WARNING') {
    statusClass = 'card-status-warning';
    statusBadge = `<span class="px-2.5 py-1 text-[10px] font-extrabold rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce"></span> LOW TIME</span>`;
  }

  const pcNum = pc.name.replace('PC-', '');
  const timerText = formatTime(pc.time_remaining) + (pc.is_open_time ? " ♾️" : "");
  const tariffName = pc.is_open_time ? "VIP Open Time" : (pc.current_tariff_name || 'Standard Plan');

  return `
    <div class="glass-card ${statusClass} rounded-2xl p-4 border border-slate-800/80 bg-slate-900/60 hover:border-cyan-500/40 hover:shadow-xl hover:shadow-cyan-500/5 transition-all duration-300 flex flex-col justify-between group">
      <div>
        <!-- Top Row: Station Icon Badge, PC Name, Zone & Status -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2.5">
            <div class="w-9 h-9 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center font-orbitron font-black text-sm text-cyan-400 group-hover:border-cyan-500/50 group-hover:text-cyan-300 transition-colors shadow-inner">
              ${pcNum}
            </div>
            <div>
              <h3 class="text-base font-extrabold font-orbitron text-white group-hover:text-cyan-400 transition-colors leading-tight">${pc.name}</h3>
              <span class="text-[10px] font-bold text-slate-400 font-mono">${pc.zone}</span>
            </div>
          </div>
          ${statusBadge}
        </div>

        <!-- Giant Timer Box -->
        <div class="my-3 py-3 px-3 rounded-xl bg-slate-950/90 border border-slate-800/90 text-center relative overflow-hidden group-hover:border-cyan-500/30 transition-colors">
          <div class="text-[9px] text-slate-400 uppercase tracking-widest font-semibold mb-1 flex items-center justify-center gap-1">
            ${pc.is_open_time ? '<span class="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span> O\'YNALGAN VAQT' : 'QOLGAN VAQT'}
          </div>
          <div id="timer-display-${pc.id}" class="text-3xl font-black font-orbitron tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-sky-300 to-purple-400">
            ${timerText}
          </div>
        </div>

        <!-- Tariff Info Line -->
        <div class="flex items-center justify-between text-xs px-1 mb-3 pt-1">
          <span class="text-[11px] text-slate-400">Tarif:</span>
          <span class="text-[11px] font-bold font-orbitron text-slate-200">${tariffName}</span>
        </div>
      </div>

      <!-- Action Buttons Footer -->
      <div class="pt-2.5 border-t border-slate-800/80">
        ${(pc.status === 'LOCKED' || pc.status === 'OFFLINE') ? `
          <button onclick="openStartModal(${pc.id})" class="w-full py-2.5 px-3 rounded-xl glow-btn-cyan text-xs font-extrabold flex items-center justify-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            SEANS BOSHLASH
          </button>
        ` : `
          <div class="flex items-center gap-2">
            <button onclick="openAddTimeModal(${pc.id})" class="flex-1 py-2 px-2.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/40 text-xs font-extrabold flex items-center justify-center gap-1 transition-all">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/></svg>
              + Vaqt
            </button>
            <button onclick="stopSession(${pc.id})" class="py-2 px-3 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-extrabold flex items-center justify-center gap-1 transition-all">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"/></svg>
              Tugatish
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

  tariffs.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.id;
    const price = parseFloat(t.price_per_hour);
    opt.textContent = `${t.name} — ${formatMoney(price)} / soat`;
    select.appendChild(opt);
  });
}

function renderTariffsTable() {
  const tbody = document.getElementById('tariffs-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  tariffs.forEach(t => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-800 hover:bg-slate-900/50 transition-colors';
    const basePrice = parseFloat(t.price_per_hour);

    tr.innerHTML = `
      <td class="py-3 px-4 font-bold text-white font-orbitron">${t.name}</td>
      <td class="py-3 px-4 text-cyan-400 font-bold font-orbitron">${formatMoney(basePrice)} / soat</td>
      <td class="py-3 px-4 text-xs text-slate-400 font-mono">${new Date(t.created_at).toLocaleDateString()}</td>
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
      <td class="py-3 px-4 text-xs text-slate-300">${s.is_open_time ? "♾️ VIP Open Time" : (s.tariff_name || 'Standard')}</td>
      <td class="py-3 px-4 font-mono text-xs text-slate-300">${s.is_open_time ? s.duration_minutes + " min (Open)" : formatDurationText(s.duration_minutes)}</td>
      <td class="py-3 px-4 font-bold text-emerald-400 font-orbitron">${formatMoney(s.total_price)}</td>
      <td class="py-3 px-4 text-xs text-slate-400 font-mono">${new Date(s.start_time).toLocaleTimeString()}</td>
      <td class="py-3 px-4">
        ${s.is_active ? 
          '<span class="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/20 text-emerald-400">ACTIVE</span>' : 
          '<span class="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-400">COMPLETED</span>'}
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

  if (method === 'CASH') {
    if (btnCash) btnCash.className = "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-emerald-500/20 text-emerald-400 border-emerald-500/50";
    if (btnCard) btnCard.className = "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-slate-900 text-slate-400 border-slate-800";
  } else {
    if (btnCash) btnCash.className = "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-slate-900 text-slate-400 border-slate-800";
    if (btnCard) btnCard.className = "py-2.5 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 bg-cyan-500/20 text-cyan-400 border-cyan-500/50";
  }
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

async function stopSession(pcId) {
  if (!confirm(`Haqiqatan ham PC-${pcId} seansini yakunlamoqchimisiz?`)) return;

  try {
    const res = await fetch(`/api/computers/${pcId}/stop_session/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      playSound('lock');
      fetchComputers();
      fetchSessions();
    } else {
      alert("Seansni to'xtatishda xatolik!");
    }
  } catch (err) {
    console.error("Error stopping session:", err);
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

document.addEventListener('DOMContentLoaded', () => {
  fetchTariffs();
  fetchComputers();
  fetchSessions();
  fetchBarOrders();
  fetchAnalytics();
  initWebSocket();
  startCountdownTimer();
  setInterval(updateHeaderClock, 1000);
  updateHeaderClock();

  const loggedIn = localStorage.getItem('admin_logged_in') === 'true';
  const username = localStorage.getItem('admin_username') || 'admin';
  updateAuthUI(loggedIn, username);
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
    pendingBadge.textContent = `${pendingCount} Kutilmoqda`;
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
        Hozircha buyurtmalar yo'q
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(order => {
    let statusBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">⏳ PENDING</span>`;
    if (order.status === 'APPROVED') {
      statusBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">👍 APPROVED</span>`;
    } else if (order.status === 'DELIVERED') {
      statusBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">🚚 DELIVERED</span>`;
    } else if (order.status === 'CANCELLED') {
      statusBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40">❌ CANCELLED</span>`;
    }

    const itemsHTML = (order.items || []).map(item => `
      <div class="flex items-center justify-between text-xs py-1.5 border-b border-slate-800/50">
        <div class="flex items-center gap-2">
          <img src="${item.product_image}" class="w-7 h-7 rounded-lg object-cover border border-slate-700">
          <span class="text-slate-200 font-semibold">${item.product_name}</span>
          <span class="text-cyan-400 font-bold font-mono">x${item.quantity}</span>
        </div>
        <span class="text-slate-300 font-mono">${formatMoney(item.unit_price * item.quantity)}</span>
      </div>
    `).join('');

    const timeAgo = new Date(order.created_at).toLocaleTimeString();

    return `
      <div class="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3 relative">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/40 text-purple-300 flex items-center justify-center font-orbitron font-black text-sm">
              ${order.computer_name}
            </div>
            <div>
              <div class="text-sm font-bold text-white font-orbitron">Order #${order.id}</div>
              <div class="text-[11px] text-slate-400 font-mono">${timeAgo}</div>
            </div>
          </div>
          ${statusBadge}
        </div>

        <div class="bg-slate-950/70 p-3 rounded-xl border border-slate-800/80 space-y-1">
          ${itemsHTML}
          <div class="flex justify-between items-center pt-2 font-bold text-sm">
            <span class="text-slate-400 uppercase text-xs">Jami Summa:</span>
            <span class="text-emerald-400 font-orbitron text-base">${formatMoney(order.total_price)}</span>
          </div>
        </div>

        <div class="flex items-center gap-2 pt-1">
          ${order.status === 'PENDING' ? `
            <button onclick="approveOrder(${order.id})" class="flex-1 py-2 rounded-xl glow-btn-cyan text-xs flex items-center justify-center gap-1">
              ✓ Tasdiqlash (Approve)
            </button>
            <button onclick="deliverOrder(${order.id})" class="flex-1 py-2 rounded-xl glow-btn-emerald text-xs flex items-center justify-center gap-1">
              🚚 Topshirildi (Deliver)
            </button>
            <button onclick="cancelOrder(${order.id})" class="py-2 px-3 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-bold transition-all">
              Bekor Qilish
            </button>
          ` : order.status === 'APPROVED' ? `
            <button onclick="deliverOrder(${order.id})" class="flex-1 py-2 rounded-xl glow-btn-emerald text-xs flex items-center justify-center gap-1">
              🚚 Topshirildi (Deliver)
            </button>
            <button onclick="cancelOrder(${order.id})" class="py-2 px-3 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 text-xs font-bold transition-all">
              Bekor Qilish
            </button>
          ` : `
            <div class="text-xs text-slate-500 font-mono italic">Buyurtma yakunlangan (${order.status})</div>
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
    tr.className = 'border-b border-slate-800/80 hover:bg-slate-900/50 transition-colors';

    let stockBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">${p.stock} ta</span>`;
    if (p.stock < 5) {
      stockBadge = `<span class="px-2.5 py-1 text-xs font-bold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 font-mono animate-pulse">⚠️ ${p.stock} ta (KAM)</span>`;
    }

    tr.innerHTML = `
      <td class="py-3 px-3">
        <div class="flex items-center gap-2.5">
          <img src="${p.image}" class="w-8 h-8 rounded-lg object-cover border border-slate-700">
          <span class="font-bold text-white">${p.name}</span>
        </div>
      </td>
      <td class="py-3 px-3 text-xs text-slate-400 font-semibold">${p.category_name || 'Barchasi'}</td>
      <td class="py-3 px-3 font-mono text-cyan-400 font-bold">${formatMoney(p.price)}</td>
      <td class="py-3 px-3">${stockBadge}</td>
      <td class="py-3 px-3 text-right">
        <button onclick="restockProduct(${p.id}, 10)" class="py-1.5 px-3 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-bold transition-all">
          +10 Zaxira
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
    container.innerHTML = `<div class="text-xs text-slate-500">Hozircha sotuvlar yo'q</div>`;
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
        <span class="px-2 py-1 rounded-lg bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-bold font-mono">${item.total_sold} ta</span>
      </div>
    </div>
  `).join('');
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
      <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800 text-xs">
        <div class="flex items-center gap-2.5">
          <img src="${p.image}" class="w-8 h-8 rounded-lg object-cover">
          <div>
            <div class="font-bold text-white">${p.name}</div>
            <div class="text-[10px] text-slate-400 font-mono">${formatMoney(p.price)}</div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded font-mono text-[10px] ${p.stock < 5 ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-slate-900 text-slate-300'}">
            ${p.stock} ta
          </span>
          <button onclick="restockProduct(${p.id}, 10)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-400 font-bold text-[10px]">
            +10
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

function setFinancePeriod(period) {
  currentFinancePeriod = period;

  document.querySelectorAll('.finance-period-btn').forEach(btn => {
    btn.className = 'finance-period-btn px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 text-slate-400 hover:text-white border border-slate-800 transition-all';
  });

  const activeBtn = document.getElementById(`btn-period-${period}`);
  if (activeBtn) {
    activeBtn.className = 'finance-period-btn px-4 py-2 rounded-xl text-xs font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 transition-all';
  }

  fetchFinanceData();
}

async function fetchFinanceData() {
  try {
    let url = `/api/expenses/cashflow/?period=${currentFinancePeriod}`;
    if (currentFinancePeriod === 'custom') {
      const df = document.getElementById('finance-date-from')?.value;
      const dt = document.getElementById('finance-date-to')?.value;
      if (df) url += `&date_from=${df}`;
      if (dt) url += `&date_to=${dt}`;
    }

    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      renderFinanceDashboard(data);
    }
  } catch (err) {
    console.error("Fetch finance error:", err);
  }
}

function renderFinanceDashboard(data) {
  const cashBalEl = document.getElementById('finance-cash-balance');
  const cardBalEl = document.getElementById('finance-card-balance');
  const totalBalEl = document.getElementById('finance-total-balance');
  const totalExpEl = document.getElementById('finance-total-expenses');
  const expBreakdownEl = document.getElementById('finance-expenses-breakdown');

  if (cashBalEl) cashBalEl.textContent = formatMoney(data.cash_balance || 0);
  if (cardBalEl) cardBalEl.textContent = formatMoney(data.card_balance || 0);
  if (totalBalEl) totalBalEl.textContent = formatMoney(data.total_balance || 0);
  if (totalExpEl) totalExpEl.textContent = formatMoney(data.total_expenses || 0);
  if (expBreakdownEl) {
    expBreakdownEl.textContent = `Naqd: ${formatMoney(data.expense_cash || 0)} | Card: ${formatMoney(data.expense_card || 0)}`;
  }

  const sessCashEl = document.getElementById('breakdown-session-cash');
  const sessCardEl = document.getElementById('breakdown-session-card');
  const barCashEl = document.getElementById('breakdown-bar-cash');
  const barCardEl = document.getElementById('breakdown-bar-card');

  if (sessCashEl) sessCashEl.textContent = formatMoney(data.session_cash || 0);
  if (sessCardEl) sessCardEl.textContent = formatMoney(data.session_card || 0);
  if (barCashEl) barCashEl.textContent = formatMoney(data.bar_cash || 0);
  if (barCardEl) barCardEl.textContent = formatMoney(data.bar_card || 0);

  const countBadge = document.getElementById('expenses-count-badge');
  const tbody = document.getElementById('expenses-table-body');
  if (!tbody) return;

  const expenses = data.expenses || [];
  if (countBadge) countBadge.textContent = `${expenses.length} ta chiqim`;

  if (expenses.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-xs text-slate-500">Ushbu davrda chiqimlar mavjud emas</td></tr>`;
    return;
  }

  tbody.innerHTML = expenses.map(e => `
    <tr class="border-b border-slate-800 hover:bg-slate-900/50 transition-colors text-xs">
      <td class="py-3 px-3 text-slate-400 font-mono">${new Date(e.created_at).toLocaleString('uz-UZ')}</td>
      <td class="py-3 px-3">
        <span class="px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 font-bold border border-slate-700">${e.category}</span>
      </td>
      <td class="py-3 px-3 font-semibold text-slate-200">${e.recipient_name || '—'}</td>
      <td class="py-3 px-3">
        ${e.payment_method === 'CASH' ? 
          '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold">💵 Naqd</span>' : 
          '<span class="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 font-bold">💳 Plastik</span>'}
      </td>
      <td class="py-3 px-3 font-bold text-rose-400 font-orbitron">-${formatMoney(e.amount)}</td>
      <td class="py-3 px-3 text-slate-300 max-w-xs truncate" title="${e.description || ''}">${e.description || '—'}</td>
      <td class="py-3 px-3 text-right">
        <button onclick="handleDeleteExpense(${e.id})" class="p-1 rounded bg-rose-500/20 hover:bg-rose-500/40 text-rose-400 transition-colors" title="Chiqimni o'chirish">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
        </button>
      </td>
    </tr>
  `).join('');
}

async function handleCreateExpense(e) {
  if (e) e.preventDefault();
  const amount = parseFloat(document.getElementById('expense-amount-input').value) || 0;
  const paymentMethod = document.getElementById('expense-payment-method').value || 'CASH';
  const category = document.getElementById('expense-category-input').value || 'Boshqa';
  const recipientName = document.getElementById('expense-recipient-input').value.trim();
  const description = document.getElementById('expense-description-input').value.trim();

  if (amount <= 0) {
    alert("Iltimos, musbat summa kiriting!");
    return;
  }

  try {
    const res = await fetch('/api/expenses/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
      document.getElementById('expense-amount-input').value = '';
      document.getElementById('expense-recipient-input').value = '';
      document.getElementById('expense-description-input').value = '';
      fetchFinanceData();
    } else {
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
      method: 'DELETE'
    });
    if (res.ok) {
      playSound('lock');
      fetchFinanceData();
    }
  } catch (err) {
    console.error("Delete expense error:", err);
  }
}


