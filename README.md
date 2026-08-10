# OpenClub Shell & Billing System (Senet Alternative)

An in-house, subscription-free LAN management and billing system for gaming lounges.

## Tech Stack
- **Server:** Python 3.12+, Django 5.x, Django REST Framework, Django Channels (WebSockets), SQLite3.
- **Server UI:** HTML5, TailwindCSS, Native JS, Dark Glassmorphic Design (Senet & Gizmo style).
- **Client App:** Python 3.12+, PyQt6, low-level Windows API keyboard hook (`ctypes`), `requests`, `websocket-client`.

---

## 🚀 Quick Start Guide

### 1. Server Setup & Launch
First, activate the virtual environment and run the server using `daphne` (for WebSocket ASGI support):

```bash
# Navigate to workspace
cd /path/to/Clutch_zone_clubtimer

# Activate venv & run server with Daphne
./venv/bin/daphne -b 0.0.0.0 -p 8000 server.config.asgi:application
```

Access the Web Dashboard in your browser:
👉 **[http://localhost:8000](http://localhost:8000)**

Admin Superuser Credentials:
- **Username**: `admin`
- **Password**: `admin123`

---

### 2. Client Locker App Launch
To start the client locker on client PCs (or test locally):

```bash
cd client
../venv/bin/python client_locker.py
```

- **Locked Mode**: Fullscreen borderless overlay window, system keys blocked (`Alt+Tab`, `Win Key`, `Alt+F4`).
- **Unlocked Mode**: When a session is started on the Web Dashboard for `PC-01`, the locker screen automatically unlocks, Playnite launches, and a floating HUD timer overlay appears in the top-right corner.
- **Session Expiry**: When time runs out or session is stopped from the dashboard, active game process trees are terminated (`taskkill`) and the lock screen is re-engaged.

---

## 🎯 Features
- ⚡ **Real-Time WebSockets**: Live sync between Server Dashboard and Client Locker apps.
- 🎨 **Senet / Gizmo Glassmorphism UI**: Dark mode, live countdown timers, station statistics.
- 🛠️ **Session Controls**: Start Session, Add Time (+15m, +30m, +1h, custom), Stop Session, Emergency Lock All.
- 🔒 **Client Protection**: Low-level Windows hook (`WH_KEYBOARD_LL`) blocking key combinations when locked.
