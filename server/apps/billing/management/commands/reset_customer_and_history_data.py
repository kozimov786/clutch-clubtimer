import shutil
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import (
    Computer, Customer, CustomerTransaction, Session, Order, OrderItem, Expense, AuditLog,
)


class Command(BaseCommand):
    help = (
        "Mijozlar, ularning balansi, seanslar, buyurtmalar, chiqimlar va faoliyat "
        "jurnalini BUTUNLAY o'chiradi (eski tarixni tozalash uchun). "
        "Kompyuterlar, Tariflar, Bar mahsulotlari va admin login'lar SAQLANIB QOLADI. "
        "SQLite bo'lsa, o'chirishdan OLDIN avtomatik zaxira nusxa oladi. "
        "Ishlatish: python manage.py reset_customer_and_history_data --yes"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes', action='store_true',
            help="Tasdiqlash so'ralmasdan, to'g'ridan-to'g'ri o'chirishni boshlaydi."
        )

    def handle(self, *args, **options):
        counts = {
            "Mijozlar (Customer)": Customer.objects.count(),
            "Mijoz tranzaksiyalari (CustomerTransaction, balans tarixi)": CustomerTransaction.objects.count(),
            "Seanslar (Session)": Session.objects.count(),
            "Bar buyurtmalari (Order + OrderItem)": Order.objects.count(),
            "Chiqimlar (Expense)": Expense.objects.count(),
            "Faoliyat jurnali (AuditLog)": AuditLog.objects.count(),
        }

        self.stdout.write(self.style.WARNING("\n=== QUYIDAGILAR BUTUNLAY O'CHIRILADI ===\n"))
        for label, n in counts.items():
            self.stdout.write(f"  - {label}: {n} ta yozuv")
        self.stdout.write(self.style.SUCCESS(
            "\n=== SAQLANIB QOLADI ===\n"
            "  - Kompyuterlar (40 PC), Zonalar, Tariflar\n"
            "  - Bar mahsulotlari, Kategoriyalar, O'yinlar\n"
            "  - Admin/xodim login'lari\n"
        ))
        self.stdout.write(self.style.ERROR(
            "DIQQAT: mijozlarning joriy balansi (ular to'lagan, hali sarflamagan puli) "
            "ham shu bilan birga butunlay yo'qoladi. Bu amalni ORQAGA QAYTARIB BO'LMAYDI.\n"
        ))

        if not options['yes']:
            answer = input("Davom etish uchun katta harflar bilan 'HA' deb yozing: ")
            if answer.strip() != 'HA':
                self.stdout.write(self.style.WARNING("Bekor qilindi. Hech narsa o'chirilmadi."))
                return

        db_conf = settings.DATABASES.get('default', {})
        if db_conf.get('ENGINE', '').endswith('sqlite3'):
            db_path = Path(db_conf['NAME'])
            if db_path.exists():
                backup_path = db_path.with_name(
                    f"{db_path.stem}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{db_path.suffix}"
                )
                shutil.copy2(db_path, backup_path)
                self.stdout.write(self.style.SUCCESS(f"Zaxira nusxa yaratildi: {backup_path}"))

        with transaction.atomic():
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            CustomerTransaction.objects.all().delete()
            Customer.objects.all().delete()
            Session.objects.all().delete()
            Expense.objects.all().delete()
            AuditLog.objects.all().delete()

            # Session'lar o'chirilgani uchun kompyuterlarni toza LOCKED holatga qaytaramiz
            Computer.objects.update(
                status='LOCKED', is_open_time=False, time_remaining=0,
                current_tariff=None, session_start_time=None, session_end_time=None,
            )

        self.stdout.write(self.style.SUCCESS(
            "\nTayyor. Mijozlar, balanslar, seanslar, buyurtmalar, chiqimlar va "
            "faoliyat jurnali tozalandi. Barcha kompyuterlar LOCKED holatga qaytarildi.\n"
        ))
