import secrets
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = ("'admin' foydalanuvchisi uchun yangi, ishlashi kafolatlangan parol "
            "o'rnatadi (mavjud bo'lmasa, yaratadi). Joriy parolni bilish shart emas.")

    def handle(self, *args, **options):
        password = secrets.token_urlsafe(10)
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@example.com'}
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        action = "yaratildi" if created else "paroli yangilandi"
        self.stdout.write(self.style.SUCCESS(f"\n'admin' foydalanuvchisi {action}.\n"))
        self.stdout.write(self.style.WARNING(f"  Login : admin"))
        self.stdout.write(self.style.WARNING(f"  Parol : {password}\n"))
        self.stdout.write("Shu login/parol bilan dashboard'ga kiring. Bu parolni "
                           "xavfsiz joyga yozib qo'ying — qayta ko'rsatilmaydi.")
