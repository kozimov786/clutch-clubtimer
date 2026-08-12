import sys
from django.apps import AppConfig

class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing & Session Management'

    def ready(self):
        # ready() har qanday `manage.py` buyrug'ida (migrate, shell,
        # makemigrations va h.k.) ham chaqiriladi — orqa fon ishchisini
        # FAQAT haqiqiy server (daphne) ishga tushganda boshlash kerak,
        # aks holda har bir qisqa umrli buyruq bekorga bitta ortiqcha
        # oqim ochib qo'yardi.
        argv0 = sys.argv[0] if sys.argv else ''
        if 'manage.py' in argv0:
            return
        from . import balance_worker
        balance_worker.start_balance_deduction_worker()
