from django.core.management.base import BaseCommand
from apps.billing.models import Category, Product

class Command(BaseCommand):
    help = 'Seeds initial Bar categories and inventory products'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding Bar data...")

        cat_drinks, _ = Category.objects.get_or_create(name="Ichimliklar", defaults={'icon': '🥤'})
        cat_snacks, _ = Category.objects.get_or_create(name="Sneklar & Chips", defaults={'icon': '🍿'})
        cat_fastfood, _ = Category.objects.get_or_create(name="Fast Food & Yegulik", defaults={'icon': '🍔'})
        cat_hot, _ = Category.objects.get_or_create(name="Issiq Ichimliklar", defaults={'icon': '☕'})

        products = [
            # Drinks
            {"name": "Red Bull 0.25L", "price": 18000, "stock": 25, "category": cat_drinks, "image": "https://images.unsplash.com/photo-1622543925917-763c34d1a86e?w=200&q=80"},
            {"name": "Coca-Cola 0.5L", "price": 8000, "stock": 40, "category": cat_drinks, "image": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=200&q=80"},
            {"name": "Fanta Orange 0.5L", "price": 8000, "stock": 30, "category": cat_drinks, "image": "https://images.unsplash.com/photo-1624552184280-9e9631bbeee9?w=200&q=80"},
            {"name": "Flash Energy 0.45L", "price": 10000, "stock": 15, "category": cat_drinks, "image": "https://images.unsplash.com/photo-1527661591475-527312dd65f5?w=200&q=80"},
            {"name": "Mavsumiy Suv 0.5L", "price": 4000, "stock": 50, "category": cat_drinks, "image": "https://images.unsplash.com/photo-1548839140-29a749e1bc4e?w=200&q=80"},

            # Snacks
            {"name": "Lays Stax Smetana 110g", "price": 16000, "stock": 18, "category": cat_snacks, "image": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=200&q=80"},
            {"name": "Pringles Original 165g", "price": 28000, "stock": 12, "category": cat_snacks, "image": "https://images.unsplash.com/photo-1528751014936-863e6e7a319c?w=200&q=80"},
            {"name": "Snickers Super 80g", "price": 9000, "stock": 3, "category": cat_snacks, "image": "https://images.unsplash.com/photo-1582293041079-7814c2f12063?w=200&q=80"},
            {"name": "KitKat Chunky 40g", "price": 8000, "stock": 2, "category": cat_snacks, "image": "https://images.unsplash.com/photo-1606312619070-d48b4c652a52?w=200&q=80"},

            # Fast Food
            {"name": "Pepperoni Pizza (O'rtacha)", "price": 45000, "stock": 10, "category": cat_fastfood, "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=200&q=80"},
            {"name": "Cheeseburger Deluxe", "price": 25000, "stock": 14, "category": cat_fastfood, "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=200&q=80"},
            {"name": "Fri Kartoshkasi 150g", "price": 14000, "stock": 20, "category": cat_fastfood, "image": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=200&q=80"},

            # Hot beverages
            {"name": "Americano Kofe 200ml", "price": 12000, "stock": 50, "category": cat_hot, "image": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=200&q=80"},
            {"name": "Cappuccino 250ml", "price": 15000, "stock": 50, "category": cat_hot, "image": "https://images.unsplash.com/photo-1534778101976-62847782c213?w=200&q=80"},
            {"name": "Qora / Yashil Choy Pyala", "price": 5000, "stock": 100, "category": cat_hot, "image": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=200&q=80"},
        ]

        for p_data in products:
            p, created = Product.objects.get_or_create(
                name=p_data["name"],
                defaults=p_data
            )
            if not created:
                p.price = p_data["price"]
                p.stock = p_data["stock"]
                p.image = p_data["image"]
                p.category = p_data["category"]
                p.save()

        self.stdout.write(self.style.SUCCESS("Bar inventory successfully seeded!"))
