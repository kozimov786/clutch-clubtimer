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
from django.db.models import F
from django.utils import timezone

CHECK_INTERVAL_SECONDS = 30


def _process_once():
    from .models import Session, Customer, CustomerTransaction, award_balance_spend_points

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
        if tariff and float(tariff.price_per_hour) <= 0:
            continue

        if tariff:
            # calculate_price_for_period() — seans boshlanishidan hozirgi
            # daqiqagacha bo'lgan BUTUN oraliqni, kunlik 10:00-18:00
            # chegirma oynasi bo'yicha to'g'ri (aralash) narxlaydi. Avval
            # bu yerda hozirgi lahzadagi BITTA stavka butun o'tgan vaqtga
            # (elapsed_minutes) qo'llanilardi — agar seans chegirma
            # oynasi chegarasidan (10:00 yoki 18:00) o'tsa, BUTUN o'tgan
            # vaqt (hatto chegaradan OLDINGI qismi ham) noto'g'ri stavka
            # bo'yicha qayta hisoblanib qolardi.
            total_due = round(tariff.calculate_price_for_period(session.start_time, now), 2)
        else:
            # Tarif seans boshlangandan keyin o'chirilgan/ajratilmagan
            # bo'lishi mumkin (customer_start_session yangi seans
            # boshlashda tarifsiz ruxsat bermaydi, lekin mavjud seansning
            # tarifi keyinchalik o'chirilishi mumkin). Avval bunday holatda
            # hisoblash butunlay o'tkazib yuborilar edi — mijoz cheksiz
            # bepul o'ynardi. Boshqa hamma joydagi bitta umumiy zaxira
            # narxga tayaniladi, shunda hech bo'lmasa noto'g'ri (0) emas,
            # oqilona narx bo'yicha hisoblanadi.
            from .views import FALLBACK_PRICE_PER_HOUR
            elapsed_minutes = max(0.0, (now - session.start_time).total_seconds() / 60.0)
            total_due = round((FALLBACK_PRICE_PER_HOUR / 60.0) * elapsed_minutes, 2)
        increment = round(total_due - float(session.balance_deducted), 2)
        if increment <= 0:
            continue

        # Har tsiklda balansni QAYTA o'qiymiz (eskirgan qiymat bilan
        # ishlamaslik uchun) — top_up/spend yoki boshqa PC'dagi
        # balance_worker tsikli shu orada balansni o'zgartirgan
        # bo'lishi mumkin.
        customer.refresh_from_db(fields=['balance'])
        available = float(customer.balance)

        if available <= 0:
            stop_balance_session(pc, session, customer, now, reason="balans tugagani uchun")
            continue

        charge = min(increment, available)
        # F() ifodasi orqali bitta atom SQL UPDATE (balance__gte sharti
        # bilan) — top_up/spend yoki shu funksiyaning boshqa
        # chaqiruvi bilan bir vaqtda ishlasa ham, hech qanday
        # yangilanish yo'qolmaydi/qayta yozilmaydi.
        updated = Customer.objects.filter(pk=customer.pk, balance__gte=charge).update(balance=F('balance') - charge)
        if not updated:
            # Balans bizning oxirgi o'qishimizdan keyin kamayib
            # ketdi (masalan boshqa joyda sarflandi) — bu safar
            # hech narsa yechmaymiz, keyingi tsiklda qayta hisoblanadi.
            continue
        customer.refresh_from_db(fields=['balance'])

        session.balance_deducted = round(float(session.balance_deducted) + charge, 2)
        session.total_price = session.balance_deducted
        session.duration_minutes = round(elapsed_minutes)
        session.save(update_fields=['balance_deducted', 'total_price', 'duration_minutes'])

        CustomerTransaction.objects.create(
            customer=customer, type='SPEND', amount=charge, balance_after=customer.balance,
            note=f"{pc.name}: balansdan seans uchun (avtomatik)"
        )
        award_balance_spend_points(customer.pk, charge)

        if customer.balance <= 0:
            stop_balance_session(pc, session, customer, now, reason="balans tugagani uchun")


def stop_balance_session(pc, session, customer, now, reason="mijoz o'zi to'xtatdi"):
    """BALANCE seansni yakunlaydi va PC'ni qulflaydi — ham balans
    tugagan (worker orqali), ham mijoz "Kabinet"dan o'zi to'xtatgan
    holatlar uchun umumiy funksiya (server bilan BIR XIL jarayonda
    chaqirilishi shart — modul boshidagi izohga qarang)."""
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
        description=f"{customer.full_name} ({customer.phone}): {reason} {pc.name} to'xtatildi"
    )

    notify_pc_status_change({
        'action': 'SESSION_STOPPED',
        'pc': ComputerSerializer(pc).data
    })
    print(f"[BalanceWorker] {pc.name}: {customer.full_name} — {reason}")


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
