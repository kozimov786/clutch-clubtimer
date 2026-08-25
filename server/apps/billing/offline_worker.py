"""Kompyuterlar bir muncha vaqt heartbeat yubormasa (o'chirilgan,
tarmoqdan uzilgan, dastur qulagan va h.k.), ularni avtomatik 'OFFLINE'
holatiga o'tkazadi — server (Daphne) jarayoni ichida orqa fon oqimida
ishlaydi (balance_worker.py bilan bir xil sabab: real-vaqtli WebSocket
xabari faqat shu jarayon ichida ishlaganda haqiqiy ulangan kiosk
klientlariga/dashboard'larga yetib boradi).

Avval bu status HECH QACHON o'rnatilmagan edi — agar PC o'chirilsa yoki
tarmoqdan uzilsa, dashboard uni abadiy oxirgi bilgan holatida (masalan
"LOCKED" yoki hatto "ACTIVE") ko'rsatib turaverar edi, xodim PC
haqiqatan ishlab turganini yoki o'chib qolganini bilolmasdi."""
import threading
import time
import traceback

from django.db import close_old_connections
from django.utils import timezone
from datetime import timedelta

CHECK_INTERVAL_SECONDS = 15
OFFLINE_THRESHOLD_SECONDS = 30


def _process_once():
    from .models import Computer
    from .serializers import ComputerSerializer
    from .consumers import notify_pc_status_change

    close_old_connections()
    now = timezone.now()
    threshold = now - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS)

    stale = Computer.objects.exclude(status='OFFLINE').filter(last_heartbeat__lt=threshold)
    for pc in stale:
        pc.status = 'OFFLINE'
        pc.save(update_fields=['status'])
        notify_pc_status_change({'action': 'PC_OFFLINE', 'pc': ComputerSerializer(pc).data})
        print(f"[OfflineDetector] {pc.name}: OFFLINE deb belgilandi (oxirgi heartbeat: {pc.last_heartbeat})")


def _run_forever():
    while True:
        try:
            _process_once()
        except Exception:
            print("[OfflineDetector] Xato:")
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_offline_detector_worker():
    thread = threading.Thread(target=_run_forever, daemon=True, name="OfflineDetectorWorker")
    thread.start()
    print(f"[OfflineDetector] Ishga tushdi (har {CHECK_INTERVAL_SECONDS}s tekshiradi, "
          f"{OFFLINE_THRESHOLD_SECONDS}s heartbeat kelmasa OFFLINE deb belgilanadi)")
