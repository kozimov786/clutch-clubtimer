from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random

from apps.billing.models import Computer, Tariff, Session, Category, Product, Order, OrderItem, Expense

class Command(BaseCommand):
    help = 'Seeds realistic sample data for Bar Orders, Sessions, Inventory, and Cashflow Expenses'

    def handle(self, *args, **options):
        self.stdout.write("Populating full demo data...")

        # 1. Clear existing orders, sessions, and expenses for a fresh clean state
        Order.objects.all().delete()
        Session.objects.all().delete()
        Expense.objects.all().delete()

        now = timezone.now()

        # 2. Get computers & products
        pcs = list(Computer.objects.all())
        products = list(Product.objects.all())
        tariff_vip = Tariff.objects.filter(name='VIP Plan').first() or Tariff.objects.first()

        if not pcs or not products:
            self.stdout.write(self.style.ERROR("PCs or Products missing. Run init_data and seed_bar first!"))
            return

        # 3. Create Active Sessions for 8 Computers
        active_pc_indices = [0, 2, 7, 11, 14, 21, 28, 34] # PC-01, PC-03, PC-08, etc.
        for idx in active_pc_indices:
            pc = pcs[idx]
            duration = random.choice([60, 120, 180, 240])
            start = now - timedelta(minutes=random.randint(10, 50))
            end = start + timedelta(minutes=duration)
            remaining = int((end - now).total_seconds())
            pm = random.choice(['CASH', 'CARD'])

            pc.status = 'ACTIVE'
            pc.is_open_time = False
            pc.session_start_time = start
            pc.session_end_time = end
            pc.time_remaining = max(0, remaining)
            pc.save()

            total_price = float(pc.current_tariff.price_per_hour if pc.current_tariff else 12000) * (duration / 60.0)

            Session.objects.create(
                computer=pc,
                tariff=pc.current_tariff or tariff_vip,
                is_open_time=False,
                start_time=start,
                end_time=end,
                duration_minutes=duration,
                total_price=total_price,
                payment_method=pm,
                is_active=True
            )

        # 4. Create Historical Completed Sessions (Past 24 hours)
        for i in range(12):
            pc = random.choice(pcs)
            duration = random.choice([60, 120, 150, 180])
            start = now - timedelta(hours=random.randint(2, 20), minutes=random.randint(0, 50))
            end = start + timedelta(minutes=duration)
            pm = random.choice(['CASH', 'CARD', 'CASH'])
            total_price = 12000.0 * (duration / 60.0)

            Session.objects.create(
                computer=pc,
                tariff=tariff_vip,
                is_open_time=False,
                start_time=start,
                end_time=end,
                duration_minutes=duration,
                total_price=total_price,
                payment_method=pm,
                is_active=False
            )

        # 5. Create Bar Orders
        # A. Pending Orders (2)
        pending_pcs = [pcs[7], pcs[14]] # PC-08, PC-15
        for pc in pending_pcs:
            selected_prods = random.sample(products, 2)
            total = 0
            order = Order.objects.create(
                computer=pc,
                payment_method=random.choice(['CASH', 'CARD']),
                status='PENDING'
            )
            for p in selected_prods:
                qty = random.randint(1, 2)
                item_total = float(p.price) * qty
                total += item_total
                OrderItem.objects.create(
                    order=order,
                    product=p,
                    quantity=qty,
                    unit_price=p.price
                )
            order.total_price = total
            order.save()

        # B. Approved Orders (2)
        approved_pcs = [pcs[2], pcs[21]]
        for pc in approved_pcs:
            selected_prods = random.sample(products, 2)
            total = 0
            order = Order.objects.create(
                computer=pc,
                payment_method=random.choice(['CASH', 'CARD']),
                status='APPROVED'
            )
            for p in selected_prods:
                qty = random.randint(1, 3)
                item_total = float(p.price) * qty
                total += item_total
                OrderItem.objects.create(
                    order=order,
                    product=p,
                    quantity=qty,
                    unit_price=p.price
                )
            order.total_price = total
            order.save()

        # C. Delivered Orders (6 - brings revenue into Kassa)
        delivered_pcs = random.sample(pcs, 6)
        for pc in delivered_pcs:
            selected_prods = random.sample(products, random.randint(1, 3))
            total = 0
            pm = random.choice(['CASH', 'CASH', 'CARD'])
            order = Order.objects.create(
                computer=pc,
                payment_method=pm,
                status='DELIVERED'
            )
            for p in selected_prods:
                qty = random.randint(1, 2)
                item_total = float(p.price) * qty
                total += item_total
                OrderItem.objects.create(
                    order=order,
                    product=p,
                    quantity=qty,
                    unit_price=p.price
                )
            order.total_price = total
            order.save()

        # 6. Create Expenses (Cash & Card)
        sample_expenses = [
            {"amount": 150000, "payment_method": "CASH", "category": "Kommunal va Aloqa", "recipient_name": "Turon Telecom", "description": "Optik internet to'lovi (Avgust)"},
            {"amount": 350000, "payment_method": "CASH", "category": "Xaridlar (Bar)", "recipient_name": "Korzinka Market", "description": "Snickers va Cola to'ldirish"},
            {"amount": 100000, "payment_method": "CASH", "category": "Ish haqi / Avans", "recipient_name": "Shohruh (Administrator)", "description": "Kunlik navbatchilik maoshi"},
            {"amount": 500000, "payment_method": "CARD", "category": "Ta'mir va Texnika", "recipient_name": "UzCard / HyperX", "description": "VIP-01 garnitura almashtirish"},
        ]

        for exp in sample_expenses:
            Expense.objects.create(**exp)

        self.stdout.write(self.style.SUCCESS("Successfully populated full demo data for Bar, Warehouse, and Cashflow!"))
