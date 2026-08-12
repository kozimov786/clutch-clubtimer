import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings

class PCStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Dashboard (brauzer): AuthMiddlewareStack sessiya cookie orqali
        # self.scope['user']ni avtomatik to'ldiradi — tizimga kirgan xodim
        # bo'lishi kerak.
        user = self.scope.get('user')
        is_staff = bool(user and getattr(user, 'is_authenticated', False) and user.is_staff)

        # Kiosk klienti (client_locker.py): foydalanuvchi hisobi yo'q,
        # shuning uchun ulanish URL'iga qo'shilgan ?api_key= orqali
        # tekshiriladi.
        query_params = parse_qs(self.scope.get('query_string', b'').decode())
        api_key = (query_params.get('api_key') or [None])[0]
        has_valid_key = bool(api_key) and api_key == settings.CLIENT_API_KEY

        if not (is_staff or has_valid_key):
            await self.close(code=4401)
            return

        self.group_name = 'pc_status_group'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        # Ulangan klientlardan kelgan xabarlar ENDI qayta uzatilmaydi.
        # Avval bu yerda har qanday ulangan klient (autentifikatsiyasiz
        # ham) o'zboshimchalik bilan soxta PC holati yoki hatto
        # EMERGENCY_LOCK_ALL xabarini butun tarmoqqa (barcha kiosk
        # klientlariga) yuborishi mumkin edi. Haqiqiy broadcastlar faqat
        # notify_pc_status_change()/notify_bar_order_change() orqali,
        # server (Django view'lar) tomonidan amalga oshiriladi — hech bir
        # qonuniy klient bu websocket orqali xabar yubormaydi.
        pass

    async def pc_update(self, event):
        await self.send(text_data=json.dumps(event['data']))

def notify_pc_status_change(computer_data):
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'pc_status_group',
            {
                'type': 'pc_update',
                'data': computer_data
            }
        )

def notify_bar_order_change(order_data):
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            'pc_status_group',
            {
                'type': 'pc_update',
                'data': {
                    'type': 'BAR_ORDER_UPDATE',
                    'order': order_data
                }
            }
        )
