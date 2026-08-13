from django.core.management.base import BaseCommand

from apps.billing.models import Computer

# PC raqamiga qarab to'g'ri xona/zona — init_data.py'dagi asl mantiq bilan bir xil:
# 1-10 -> 1-VIP Zone (1-xona), 11-20 -> 2-VIP Zone (2-xona),
# 21-30 -> Main Zone (3-xona), 31-40 -> Standard Zone (4-xona)
ZONE_RANGES = [
    (1, 10, '1-VIP Zone'),
    (11, 20, '2-VIP Zone'),
    (21, 30, 'Main Zone'),
    (31, 40, 'Standard Zone'),
]


def correct_zone_for(pc_number):
    for lo, hi, zone in ZONE_RANGES:
        if lo <= pc_number <= hi:
            return zone
    return None


class Command(BaseCommand):
    help = (
        "PC-01..PC-40 uchun zona (xona) maydonini to'g'ri raqam oralig'iga "
        "moslab tuzatadi: 1-10=1-VIP Zone, 11-20=2-VIP Zone, 21-30=Main Zone, "
        "31-40=Standard Zone. Faqat 'zone' maydonini o'zgartiradi — tarif, "
        "status va boshqa hech narsaga tegmaydi."
    )

    def handle(self, *args, **options):
        changed = []
        for comp in Computer.objects.all().order_by('name'):
            try:
                pc_number = int(comp.name.replace('PC-', ''))
            except ValueError:
                continue
            correct_zone = correct_zone_for(pc_number)
            if correct_zone and comp.zone != correct_zone:
                changed.append((comp.name, comp.zone, correct_zone))
                comp.zone = correct_zone
                comp.save(update_fields=['zone'])

        if not changed:
            self.stdout.write(self.style.SUCCESS("Hammasi allaqachon to'g'ri joylashgan — hech narsa o'zgartirilmadi."))
            return

        self.stdout.write(self.style.SUCCESS(f"{len(changed)} ta kompyuterning zonasi tuzatildi:\n"))
        for name, old_zone, new_zone in changed:
            self.stdout.write(f"  {name}: {old_zone!r} -> {new_zone!r}")
