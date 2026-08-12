"""Mijoz balansidan o'zi ochgan (payment_method='BALANCE') seanslar
uchun bosqichma-bosqich (davriy) pul yechish — server (Daphne) jarayoni
ichida orqa fon oqimida ishlaydi.

MUHIM: bu logika ATAYLAB alohida Windows Task Scheduler vazifasi
(masalan alohida `manage.py` buyrug'i) sifatida emas, balki serverning
O'ZI ichida (shu jarayonda) ishlaydi — sababi: CHANNEL_LAYERS
InMemoryChannelLayer bo'lib, u faqat BITTA jarayon ichida ishlaydi.
Agar balansni tekshirish alohida jarayonda ishlaganida, u
notify_pc_status_change() orqali yuborgan xabari haqiqiy Daphne
jarayonidagi ulangan kiosk klientlariga HECH QACHON yetib bormas edi
(chunki ular butunlay boshqa, bo'sh channel layer nusxasiga
yozilgan bo'lardi) — PC balans tugaganda darhol emas, faqat keyingi
heartbeat siklida (besh soniyagacha kechikish bilan) qulflanardi.
"""
import threading
import time
import traceback

from django.db import close_old_connections
from django.utils import timezone

CHECK_INTERVAL_SECONDS = 30


def _process_once():
    from .models import Session, CustomerTransaction

    close_old_connections()
    now = timezone.now()

    active_sessions = Session.objects.filter(
        is_active=True, payment_method='BALANCE', customer__isnull=False
    ).select_related('computer', 'customer', 'tariff')

    for session in active_sessions:
        pc = session.computer
        customer = session.customer
        if not pc or pc.status not in ('ACTIVE', 'WARNING'):
            continue

        tariff = session.tariff or pc.current_tariff
        price_per_minute = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 0.0
        if price_per_minute <= 0:
            continue

        elapsed_minutes = max(0.0, (now - session.start_time).total_seconds() / 60.0)
        total_due = round(price_per_minute * elapsed_minutes, 2)
        increment = round(total_due - float(session.balance_deducted), 2)
        if increment <= 0:
            continue

        available = float(customer.balance)

        if available <= 0:
            _stop_session_for_depletion(pc, session, customer, now)
            continue

        charge = min(increment, available)
        customer.balance = round(available - charge, 2)
        customer.save(update_fields=['balance'])

        session.balance_deducted = round(float(session.balance_deducted) + charge, 2)
        session.total_price = session.balance_deducted
        session.duration_minutes = round(elapsed_minutes)
        session.save(update_fields=['balance_deducted', 'total_price', 'duration_minutes'])

        CustomerTransaction.objects.create(
            customer=customer, type='SPEND', amount=charge, balance_after=customer.balance,
            note=f"{pc.name}: balansdan seans uchun (avtomatik)"
        )

        if customer.balance <= 0:
            _stop_session_for_depletion(pc, session, customer, now)


def _stop_session_for_depletion(pc, session, customer, now):
    from .models import AuditLog
    from .serializers import ComputerSerializer
    from .consumers import notify_pc_status_change

    session.end_time = now
    session.is_active = False
    session.total_price = session.balance_deducted
    session.duration_minutes = round(max(0.0, (now - session.start_time).total_seconds() / 60.0))
    session.save(update_fields=['end_time', 'is_active', 'total_price', 'duration_minutes'])

    pc.status = 'LOCKED'
    pc.is_open_time = False
    pc.time_remaining = 0
    pc.session_start_time = None
    pc.session_end_time = None
    pc.current_tariff = None
    pc.save()

    AuditLog.objects.create(
        action='CUSTOMER_SPEND',
        description=f"{customer.full_name} ({customer.phone}): balans tugagani uchun {pc.name} avtomatik to'xtatildi"
    )

    notify_pc_status_change({
        'action': 'SESSION_STOPPED',
        'pc': ComputerSerializer(pc).data
    })
    print(f"[BalanceWorker] {pc.name}: {customer.full_name} balansi tugadi, seans avtomatik to'xtatildi")


def _run_forever():
    while True:
        try:
            _process_once()
        except Exception:
            print("[BalanceWorker] Xato:")
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_balance_deduction_worker():
    thread = threading.Thread(target=_run_forever, daemon=True, name="BalanceDeductionWorker")
    thread.start()
    print(f"[BalanceWorker] Ishga tushdi (har {CHECK_INTERVAL_SECONDS}s tekshiradi)")
