from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.billing.models import Computer, Tariff

class Command(BaseCommand):
    help = 'Initialize 40 computers across 1-VIP Zone, 2-VIP Zone, Main Zone, and Standard Zone'

    def handle(self, *args, **options):
        # 1. Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write(self.style.SUCCESS('Created superuser: admin / admin123'))
        else:
            admin = User.objects.get(username='admin')
            admin.set_password('admin123')
            admin.save()
            self.stdout.write('Superuser "admin" password updated to admin123')

        # 2. Clear old tariffs and recreate 2 tariffs
        Tariff.objects.all().delete()

        t_vip = Tariff.objects.create(name='VIP Plan', price_per_hour=12000.00)
        t_skidka = Tariff.objects.create(name='Skidka 50%', price_per_hour=6000.00)

        self.stdout.write(self.style.SUCCESS(f'Created Tariff: {t_vip.name} ({t_vip.price_per_hour:,.0f} UZS/h)'))
        self.stdout.write(self.style.SUCCESS(f'Created Tariff: {t_skidka.name} ({t_skidka.price_per_hour:,.0f} UZS/h)'))

        # 3. 40 Computers (10 in 1-VIP Zone, 10 in 2-VIP Zone, 10 in Main Zone, 10 in Standard Zone)
        Computer.objects.exclude(name__in=[f'PC-{i:02d}' for i in range(1, 41)]).delete()

        for i in range(1, 41):
            name = f'PC-{i:02d}'
            ip_address = f'192.168.1.{100 + i}'

            if i <= 10:
                zone = '1-VIP Zone'
                tariff = t_vip
                spec = 'RTX 4090 | i9-14900K | 64GB RAM | 240Hz OLED'
            elif i <= 20:
                zone = '2-VIP Zone'
                tariff = t_vip
                spec = 'RTX 4090 | i9-14900K | 64GB RAM | 240Hz OLED'
            elif i <= 30:
                zone = 'Main Zone'
                tariff = t_vip
                spec = 'RTX 4080 | i7-14700K | 32GB RAM | 240Hz'
            else:
                zone = 'Standard Zone'
                tariff = t_vip
                spec = 'RTX 4070 | i7-13700K | 32GB RAM | 165Hz'

            comp, created = Computer.objects.get_or_create(
                name=name,
                defaults={
                    'zone': zone,
                    'hardware_spec': spec,
                    'ip_address': ip_address,
                    'status': 'LOCKED',
                    'time_remaining': 0,
                    'current_tariff': tariff,
                }
            )
            comp.zone = zone
            comp.hardware_spec = spec
            comp.current_tariff = tariff
            comp.save()

        self.stdout.write(self.style.SUCCESS('Successfully split into 1-VIP Zone, 2-VIP Zone, Main Zone, and Standard Zone!'))
