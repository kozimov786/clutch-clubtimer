// ===== CLUTCH ZONE — Til tizimi (uz / ru / en) =====
// Bosqichma-bosqich to'ldirilmoqda: hozircha yuqori panel (header, navbar,
// mobil menyu) va Stations Grid asboblar paneli tarjima qilingan. Qolgan
// bo'limlar (Buyurtmalar, Mijozlar, Kassa, Settings sahifalari, modallar)
// keyingi bosqichlarda shu I18N lug'atiga qo'shiladi.

const I18N = {
  uz: {
    'header.slogan': "GAMING LOUNGE & BILLING SYSTEM",
    'header.emergency_lock': "Favqulodda bloklash — barcha PC",
    'header.shutdown_all': "Hammasini o'chirish",

    'nav.grid': "STATIONS GRID (40 PC)",
    'nav.bar': "BUYURTMALAR",
    'nav.customers': "MIJOZLAR",
    'nav.finance': "KASSA",
    'nav.settings': "SETTINGS",
    'settings.tariffs': "Tariflar va Narxlar",
    'settings.analytics': "Ombor & Hisobot",
    'settings.auditlog': "Faoliyat Jurnali",
    'settings.sessions': "Seanslar Tarixi",

    'mobile.grid_title': "Stations Grid",
    'mobile.grid_sub': "40 PC boshqaruvi",
    'mobile.bar_title': "Buyurtmalar",
    'mobile.bar_sub': "POS terminal va buyurtmalar",
    'mobile.customers_title': "Mijozlar",
    'mobile.customers_sub': "A'zolik va balans",
    'mobile.finance_title': "Kassa",
    'mobile.finance_sub': "Moliya va chiqimlar nazorati",
    'mobile.settings_header': "Settings",
    'mobile.tariffs_title': "Tariflar va Narxlar",
    'mobile.tariffs_sub': "Tarif rejalarini boshqarish",
    'mobile.analytics_title': "Ombor & Hisobot",
    'mobile.analytics_sub': "Inventar va analitika",
    'mobile.auditlog_title': "Faoliyat Jurnali",
    'mobile.auditlog_sub': "Kim nima qildi",
    'mobile.sessions_title': "Seanslar Tarixi",
    'mobile.sessions_sub': "O'tgan seanslar jurnali",
    'mobile.emergency_lock': "EMERGENCY LOCK — Barcha PC yoping",
    'mobile.shutdown_all': "HAMMASINI O'CHIRISH — Barcha PC quvvatini",

    'kpi.total_pcs': "Jami Kompyuterlar",
    'kpi.active_pcs': "Band Komplar",
    'kpi.locked_pcs': "Bo'sh (Bloklangan)",
    'kpi.revenue': "Jami Kassa Tushumi",

    'grid.zone_all': "Hamma (40 PC)",
    'grid.zone_vip1': "👑 1-VIP Zone",
    'grid.zone_vip2': "👑 2-VIP Zone",
    'grid.zone_main': "⚡ Main Zone",
    'grid.zone_standard': "🎮 Standard Zone",
    'grid.status_all': "Barchasi",
    'grid.status_active': "Band",
    'grid.status_locked': "Bo'sh",
    'grid.search_placeholder': "Qidiruv: PC-05...",
  },

  ru: {
    'header.slogan': "ИГРОВОЙ КЛУБ И БИЛЛИНГ",
    'header.emergency_lock': "Экстренная блокировка — все ПК",
    'header.shutdown_all': "Выключить все",

    'nav.grid': "СТАНЦИИ (40 ПК)",
    'nav.bar': "ЗАКАЗЫ",
    'nav.customers': "КЛИЕНТЫ",
    'nav.finance': "КАССА",
    'nav.settings': "НАСТРОЙКИ",
    'settings.tariffs': "Тарифы и цены",
    'settings.analytics': "Склад и отчёты",
    'settings.auditlog': "Журнал действий",
    'settings.sessions': "История сеансов",

    'mobile.grid_title': "Станции",
    'mobile.grid_sub': "Управление 40 ПК",
    'mobile.bar_title': "Заказы",
    'mobile.bar_sub': "POS-терминал и заказы",
    'mobile.customers_title': "Клиенты",
    'mobile.customers_sub': "Членство и баланс",
    'mobile.finance_title': "Касса",
    'mobile.finance_sub': "Финансы и контроль расходов",
    'mobile.settings_header': "Настройки",
    'mobile.tariffs_title': "Тарифы и цены",
    'mobile.tariffs_sub': "Управление тарифами",
    'mobile.analytics_title': "Склад и отчёты",
    'mobile.analytics_sub': "Инвентарь и аналитика",
    'mobile.auditlog_title': "Журнал действий",
    'mobile.auditlog_sub': "Кто что сделал",
    'mobile.sessions_title': "История сеансов",
    'mobile.sessions_sub': "Журнал прошедших сеансов",
    'mobile.emergency_lock': "ЭКСТРЕННАЯ БЛОКИРОВКА — закрыть все ПК",
    'mobile.shutdown_all': "ВЫКЛЮЧИТЬ ВСЕ — питание всех ПК",

    'kpi.total_pcs': "Всего компьютеров",
    'kpi.active_pcs': "Занятые ПК",
    'kpi.locked_pcs': "Свободные (заблок.)",
    'kpi.revenue': "Общая выручка кассы",

    'grid.zone_all': "Все (40 ПК)",
    'grid.zone_vip1': "👑 VIP-зона 1",
    'grid.zone_vip2': "👑 VIP-зона 2",
    'grid.zone_main': "⚡ Основная зона",
    'grid.zone_standard': "🎮 Стандартная зона",
    'grid.status_all': "Все",
    'grid.status_active': "Занят",
    'grid.status_locked': "Свободен",
    'grid.search_placeholder': "Поиск: PC-05...",
  },

  en: {
    'header.slogan': "GAMING LOUNGE & BILLING SYSTEM",
    'header.emergency_lock': "Emergency lock — all PCs",
    'header.shutdown_all': "Shut down all",

    'nav.grid': "STATIONS GRID (40 PCs)",
    'nav.bar': "ORDERS",
    'nav.customers': "CUSTOMERS",
    'nav.finance': "CASHBOX",
    'nav.settings': "SETTINGS",
    'settings.tariffs': "Tariffs & Pricing",
    'settings.analytics': "Stock & Reports",
    'settings.auditlog': "Activity Log",
    'settings.sessions': "Session History",

    'mobile.grid_title': "Stations Grid",
    'mobile.grid_sub': "Manage 40 PCs",
    'mobile.bar_title': "Orders",
    'mobile.bar_sub': "POS terminal & orders",
    'mobile.customers_title': "Customers",
    'mobile.customers_sub': "Membership & balance",
    'mobile.finance_title': "Cashbox",
    'mobile.finance_sub': "Finance & expense control",
    'mobile.settings_header': "Settings",
    'mobile.tariffs_title': "Tariffs & Pricing",
    'mobile.tariffs_sub': "Manage tariff plans",
    'mobile.analytics_title': "Stock & Reports",
    'mobile.analytics_sub': "Inventory & analytics",
    'mobile.auditlog_title': "Activity Log",
    'mobile.auditlog_sub': "Who did what",
    'mobile.sessions_title': "Session History",
    'mobile.sessions_sub': "Past sessions log",
    'mobile.emergency_lock': "EMERGENCY LOCK — close all PCs",
    'mobile.shutdown_all': "SHUT DOWN ALL — power off every PC",

    'kpi.total_pcs': "Total Computers",
    'kpi.active_pcs': "Busy PCs",
    'kpi.locked_pcs': "Free (Locked)",
    'kpi.revenue': "Total Cashbox Revenue",

    'grid.zone_all': "All (40 PCs)",
    'grid.zone_vip1': "👑 VIP Zone 1",
    'grid.zone_vip2': "👑 VIP Zone 2",
    'grid.zone_main': "⚡ Main Zone",
    'grid.zone_standard': "🎮 Standard Zone",
    'grid.status_all': "All",
    'grid.status_active': "Busy",
    'grid.status_locked': "Free",
    'grid.search_placeholder': "Search: PC-05...",
  },
};

function getCurrentLang() {
  return localStorage.getItem('cz_lang') || 'uz';
}

function t(key) {
  const lang = getCurrentLang();
  return (I18N[lang] && I18N[lang][key]) || I18N.uz[key] || key;
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.getAttribute('data-i18n-title'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  document.querySelectorAll('.lang-switch-btn').forEach(btn => {
    btn.classList.toggle('lang-switch-active', btn.dataset.langBtn === getCurrentLang());
  });
}

function setLanguage(lang) {
  localStorage.setItem('cz_lang', lang);
  applyTranslations();
}

document.addEventListener('DOMContentLoaded', applyTranslations);
