from django.core.management.base import BaseCommand
from apps.billing.models import Game

class Command(BaseCommand):
    help = 'Seeds initial Game catalog into Django database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding Game catalog...")

        games_data = [
            # FPS / Shooter
            {
                "name": "Counter-Strike 2",
                "category": "FPS",
                "cover_path": "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=500&q=80",
                "executable_path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Counter-Strike Global Offensive\\game\\bin\\win64\\cs2.exe"
            },
            {
                "name": "Valorant",
                "category": "FPS",
                "cover_path": "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=500&q=80",
                "executable_path": "C:\\Riot Games\\VALORANT\\live\\VALORANT.exe"
            },
            {
                "name": "PUBG: BATTLEGROUNDS",
                "category": "FPS",
                "cover_path": "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=500&q=80",
                "executable_path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\PUBG\\TslGame\\Binaries\\Win64\\TslGame.exe"
            },

            # Action / Adventure
            {
                "name": "Grand Theft Auto V",
                "category": "Action",
                "cover_path": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=500&q=80",
                "executable_path": "C:\\Program Files\\Epic Games\\GTA5\\GTA5.exe"
            },
            {
                "name": "Cyberpunk 2077",
                "category": "Action",
                "cover_path": "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=500&q=80",
                "executable_path": "C:\\GOG Games\\Cyberpunk 2077\\bin\\x64\\Cyberpunk2077.exe"
            },
            {
                "name": "Red Dead Redemption 2",
                "category": "Action",
                "cover_path": "https://images.unsplash.com/photo-1579373903781-fd5c0c30c4cd?w=500&q=80",
                "executable_path": "C:\\Program Files\\Rockstar Games\\Red Dead Redemption II\\RDR2.exe"
            },

            # Sports / Racing
            {
                "name": "EA SPORTS FC 24",
                "category": "Sports",
                "cover_path": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=500&q=80",
                "executable_path": "C:\\Program Files\\EA Games\\EA SPORTS FC 24\\FC24.exe"
            },
            {
                "name": "Need for Speed Unbound",
                "category": "Sports",
                "cover_path": "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?w=500&q=80",
                "executable_path": "C:\\Program Files\\EA Games\\NFS Unbound\\NFSUnbound.exe"
            },
            {
                "name": "NBA 2K24",
                "category": "Sports",
                "cover_path": "https://images.unsplash.com/photo-1546519638-68e109498ffc?w=500&q=80",
                "executable_path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\NBA 2K24\\NBA2K24.exe"
            },

            # Strategy / MOBA
            {
                "name": "Dota 2",
                "category": "Strategy",
                "cover_path": "https://images.unsplash.com/photo-1563089145-599997674d42?w=500&q=80",
                "executable_path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\dota 2 beta\\game\\bin\\win64\\dota2.exe"
            },
            {
                "name": "League of Legends",
                "category": "Strategy",
                "cover_path": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=500&q=80",
                "executable_path": "C:\\Riot Games\\League of Legends\\LeagueClient.exe"
            }
        ]

        for g_data in games_data:
            g, created = Game.objects.get_or_create(
                name=g_data["name"],
                defaults=g_data
            )
            if not created:
                g.category = g_data["category"]
                g.cover_path = g_data["cover_path"]
                g.executable_path = g_data["executable_path"]
                g.save()

        self.stdout.write(self.style.SUCCESS("Successfully seeded 11 popular games into catalog!"))
