from django.db import models
from django.utils import timezone
import math

class Tariff(models.Model):
    objects = models.Manager()

    name = models.CharField(max_length=100)
    price_per_hour = models.DecimalField(max_digits=12, decimal_places=2, default=12000.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_effective_price_per_hour(self, dt=None):
        if dt is None:
            dt = timezone.localtime()
        # 10:00:00 to 17:59:59 (10:00 to 18:00) gets 50% discount
        if 10 <= dt.hour < 18:
            return float(self.price_per_hour) * 0.5
        return float(self.price_per_hour)

    def __str__(self):
        return f"{self.name} - {self.price_per_hour:,.0f} UZS/h"

class Computer(models.Model):
    objects = models.Manager()

    STATUS_CHOICES = [
        ('LOCKED', 'Locked'),
        ('ACTIVE', 'Active'),
        ('WARNING', 'Warning'),
        ('OFFLINE', 'Offline'),
    ]

    name = models.CharField(max_length=50, unique=True)
    zone = models.CharField(max_length=50, default='Standard Zone')
    hardware_spec = models.CharField(max_length=100, default='RTX 4070 | i7-13700K | 32GB')
    ip_address = models.GenericIPAddressField(default='127.0.0.1')
    mac_address = models.CharField(max_length=17, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='LOCKED')
    is_open_time = models.BooleanField(default=False, help_text="True if open-ended session without fixed timer")
    time_remaining = models.IntegerField(default=0, help_text="Remaining or elapsed seconds")
    current_tariff = models.ForeignKey(Tariff, on_delete=models.SET_NULL, null=True, blank=True)
    session_start_time = models.DateTimeField(null=True, blank=True)
    session_end_time = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(auto_now=True)

    def calculate_time_remaining(self):
        if self.status == 'ACTIVE':
            now = timezone.now()
            if self.is_open_time and self.session_start_time:
                diff = (now - self.session_start_time).total_seconds()
                self.time_remaining = int(diff)
                self.save(update_fields=['time_remaining'])
                return self.time_remaining
            elif self.session_end_time:
                diff = (self.session_end_time - now).total_seconds()
                if diff <= 0:
                    self.status = 'LOCKED'
                    self.time_remaining = 0
                    self.is_open_time = False
                    self.session_start_time = None
                    self.session_end_time = None
                    self.save(update_fields=['status', 'time_remaining', 'is_open_time', 'session_start_time', 'session_end_time'])
                    return 0
                elif diff <= 300: # 5 minutes left -> WARNING
                    self.time_remaining = int(diff)
                    self.status = 'WARNING'
                    self.save(update_fields=['status', 'time_remaining'])
                    return self.time_remaining
                else:
                    self.time_remaining = int(diff)
                    self.save(update_fields=['time_remaining'])
                    return self.time_remaining
        return self.time_remaining

    def __str__(self):
        return f"{self.name} ({self.status}) - {self.time_remaining}s {'elapsed' if self.is_open_time else 'remaining'}"

PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Naqd'),
    ('CARD', 'Plastik'),
    ('SPLIT', 'Aralash (Naqd + Card)'),
]

class Customer(models.Model):
    objects = models.Manager()

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    bonus_points = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.phone}) - Balans: {self.balance:,.0f} UZS"

CUSTOMER_TRANSACTION_CHOICES = [
    ('TOPUP', "To'ldirish"),
    ('SPEND', 'Sarflash'),
    ('ADJUST', 'Tuzatish'),
]

class CustomerTransaction(models.Model):
    objects = models.Manager()

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=CUSTOMER_TRANSACTION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()}: {self.amount:,.0f} UZS - {self.customer.full_name}"

class Session(models.Model):
    objects = models.Manager()

    computer = models.ForeignKey(Computer, on_delete=models.CASCADE, related_name='sessions')
    tariff = models.ForeignKey(Tariff, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    is_open_time = models.BooleanField(default=False)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    card_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Session for {self.computer.name} ({self.payment_method}) - {self.duration_minutes} mins"

class Category(models.Model):
    objects = models.Manager()

    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, default='🍿')

    def __str__(self):
        return self.name

class Product(models.Model):
    objects = models.Manager()

    name = models.CharField(max_length=100)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Tannarx / Olish narxi")
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Sotish narxi")
    stock = models.IntegerField(default=0)
    image = models.CharField(max_length=255, default='https://images.unsplash.com/photo-1541592106381-b31e9677c0e5?w=200&q=80')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - Sotish: {self.price:,.0f} UZS | Tannarx: {self.cost_price:,.0f} UZS (Stock: {self.stock})"

class StockSupply(models.Model):
    objects = models.Manager()

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_supplies')
    product_name = models.CharField(max_length=150)
    quantity = models.IntegerField(default=1)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    supplier_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Kirim: {self.quantity}x {self.product_name} @ {self.cost_price:,.0f} UZS ({self.get_payment_method_display()}) - Jami: {self.total_cost:,.0f} UZS"

class Order(models.Model):
    objects = models.Manager()

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]

    computer = models.ForeignKey(Computer, on_delete=models.CASCADE, related_name='bar_orders', null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cash_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    card_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        pc_str = self.computer.name if self.computer else 'Direct POS'
        return f"Order #{self.id} ({pc_str}) [{self.payment_method}] - {self.status} - {self.total_price:,.0f} UZS"

class OrderItem(models.Model):
    objects = models.Manager()

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name} @ Order #{self.order.id}"

class Expense(models.Model):
    objects = models.Manager()

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    category = models.CharField(max_length=100, default='Boshqa')
    recipient_name = models.CharField(max_length=150, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Expense #{self.id}: {self.amount:,.0f} UZS ({self.get_payment_method_display()}) - {self.category}"

GAME_CATEGORY_CHOICES = [
    ('FPS', 'FPS / Shooter'),
    ('Action', 'Action / Adventure'),
    ('Sports', 'Sports / Racing'),
    ('Strategy', 'Strategy / MOBA'),
]

class Game(models.Model):
    objects = models.Manager()

    name = models.CharField(max_length=150)
    cover_path = models.CharField(max_length=500, help_text="Cover banner image URL or local file path")
    executable_path = models.CharField(max_length=500, help_text="Executable file path or launch command")
    working_directory = models.CharField(max_length=500, blank=True, null=True, help_text="Working directory path for executable")
    category = models.CharField(max_length=50, choices=GAME_CATEGORY_CHOICES, default='FPS')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.category}]"


class ClientBuild(models.Model):
    """Kiosk klient (client_locker.py) yangi versiyasi shu yerga
    yuklanadi (zip). Klientlar davriy ravishda shu ro'yxatdagi eng
    so'nggi is_active=True versiyani tekshirib, o'zini avtomatik
    yangilaydi — endi har bir PC'ga qo'lda git pull qilish shart emas."""
    objects = models.Manager()

    version = models.CharField(max_length=30, unique=True, help_text="Masalan: 1.0.1")
    zip_file = models.FileField(upload_to='client_builds/', help_text="client/ papkasining zip arxivi (config.json'siz)")
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True, help_text="Faqat True bo'lgan eng so'nggi versiya kiosklarga taqdim etiladi")
    released_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-released_at']

    def __str__(self):
        return f"v{self.version}" + ("" if self.is_active else " (nofaol)")


AUDIT_ACTION_CHOICES = [
    ('LOGIN', 'Tizimga kirdi'),
    ('SESSION_STOPPED', 'Seans yakunlandi'),
    ('EMERGENCY_LOCK', 'Favqulodda bloklandi'),
    ('TARIFF_CHANGED', "Tarif narxi o'zgartirildi"),
    ('ORDER_APPROVED', 'Buyurtma tasdiqlandi'),
    ('ORDER_DELIVERED', 'Buyurtma yetkazildi'),
    ('ORDER_CANCELLED', 'Buyurtma bekor qilindi'),
    ('CUSTOMER_TOPUP', "Mijoz balansi to'ldirildi"),
    ('CUSTOMER_SPEND', 'Mijoz balansidan yechildi'),
    ('EXPENSE_CREATED', "Rasxod qo'shildi"),
    ('STOCK_SUPPLY', 'Tovar kirim qilindi'),
    ('OTHER', 'Boshqa'),
]

class AuditLog(models.Model):
    """Kim (qaysi tizimga kirgan xodim) qachon qanday muhim amal
    bajarganini yozib boradi — kelajakda bir nechta xodim/rol
    qo'shilganda buni kengaytirish mumkin, hozircha bitta admin
    ostida ham kunlik voqealar tarixi sifatida foydali."""
    objects = models.Manager()

    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=30, choices=AUDIT_ACTION_CHOICES, default='OTHER')
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.user.username if self.user else 'tizim'
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {who}: {self.description}"


