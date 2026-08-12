"""config.json'dagi 'api_key' maydonini serverning CLIENT_API_KEY'iga
mos qilib qo'yadi — boshqa maydonlarga (server_url, pc_name,
fallback_games va h.k.) tegmaydi. Qo'lda uzun kalitni ko'chirib-
joylashtirishda xato (masalan harf O bilan raqam 0 chalkashishi)
bo'lmasligi uchun, kalit shu faylning o'zida (git orqali yetkaziladi)."""
import json

CORRECT_API_KEY = "AKiv9qEeJqBlO8Xa4HJfJ_ZmMig6c5srmY7Nr1c4oOw"
CONFIG_PATH = "config.json"


def main():
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    old_key = cfg.get("api_key", "")
    cfg["api_key"] = CORRECT_API_KEY

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"Eski api_key : {old_key}")
    print(f"Yangi api_key: {cfg['api_key']}")
    print("TO'G'RILANDI:", cfg["api_key"] == CORRECT_API_KEY)


if __name__ == "__main__":
    main()
