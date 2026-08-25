"""config.json faylini DASTUR orqali (qo'lda qayta terib/joylashtirmasdan)
qaytadan yozib chiqadi — qo'lda tahrirlashda ko'rinmas belgi (masalan
"aqlli tirnoq") tushib qolib, JSON buzilib qolishining oldini oladi.

BU NAMUNA (TEMPLATE) FAYL — git tomonidan kuzatiladi. Har bir PC uchun:
1. Shu faylni "regenerate_config.py" nomi bilan nusxalang (bu nom
   .gitignore'da, hech qachon git'ga tushmaydi va hech kim bilan
   to'qnashmaydi).
2. Pastdagi qiymatlarni (PC_NAME, SERVER_URL va h.k.) shu PC'ga mos
   qilib to'ldiring.
3. Ishga tushiring: python regenerate_config.py

Diqqat: bu skript server_url/pc_name/api_key va fallback_games ro'yxatini
QAYTA YOZADI. Agar keyinchalik yana yangi o'yin qo'shsangiz, shu faylning
o'zidagi FALLBACK_GAMES ro'yxatiga qo'shib, qayta ishga tushiring."""
import json

SERVER_URL = "http://192.168.88.100:8001"
WEBSOCKET_URL = "ws://192.168.88.100:8001/ws/pc-status/"
PC_NAME = "PC-01"
HEARTBEAT_INTERVAL_SECONDS = 5
API_KEY = "AKiv9qEeJqBlO8Xa4HJfJ_ZmMig6c5srmY7Nr1c4oOw"

# Favqulodda chiqish (Ctrl+Alt+Shift+U / Ctrl+Shift+P) uchun parol —
# OCHIQ MATN EMAS, SHA-256 xesh sifatida saqlanadi. Standart qiymat
# "4747" paroliga mos keladi — buni albatta o'zingizniki bilan
# almashtiring: python3 -c "import hashlib;
# print(hashlib.sha256('YANGI_PAROL'.encode()).hexdigest())"
ADMIN_EXIT_PASSWORD_HASH = "822a8e0aad6a68a99ee9db27651f1f6115414b7a772984b3f6609246ffbe3ef5"

FALLBACK_GAMES = [
    {
        "name": "Counter-Strike 2",
        "category": "FPS",
        "cover_path": "client/assets/games/cs2.jpg",
        "executable_path": r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe",
    },
    {
        "name": "Valorant",
        "category": "FPS",
        "cover_path": "client/assets/games/valorant.jpg",
        "executable_path": r"C:\Riot Games\VALORANT\live\VALORANT.exe",
    },
]

CONFIG_PATH = "config.json"


def main():
    cfg = {
        "server_url": SERVER_URL,
        "websocket_url": WEBSOCKET_URL,
        "pc_name": PC_NAME,
        "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "api_key": API_KEY,
        "admin_exit_password_hash": ADMIN_EXIT_PASSWORD_HASH,
        "fallback_games": FALLBACK_GAMES,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        json.load(f)  # o'zi yozgan faylni o'zi qayta o'qib tekshiradi
    print("config.json muvaffaqiyatli qayta yozildi va tekshirildi — JSON to'g'ri.")


if __name__ == "__main__":
    main()
