import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class PCStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'pc_status_group'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        # Re-broadcast or handle incoming client messages
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'pc_update',
                'data': data
            }
        )

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

