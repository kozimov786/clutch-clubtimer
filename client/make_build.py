"""Yangi klient versiyasini serverga yuklash uchun zip arxiv tayyorlaydi.

Ishlatilishi:
    1. client/VERSION faylidagi versiya raqamini oshiring (masalan 1.0.1)
    2. python make_build.py ni ishga tushiring — client_1.0.1.zip yaratiladi
    3. Django admin panelida (/admin/billing/clientbuild/add/) shu zip'ni
       "version"=1.0.1 bilan yuklang (is_active=True qoldiring)
    4. Kiosk PC'lar 30 daqiqa ichida (yoki qayta ishga tushganda) buni
       avtomatik topib, o'zini yangilaydi — qo'lda git pull kerak emas.
"""
import os
import zipfile

CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))

EXCLUDE_NAMES = {"config.json", "__pycache__", ".git", "make_build.py"}
EXCLUDE_EXTS = {".pyc", ".zip"}


def main():
    version_path = os.path.join(CLIENT_DIR, "VERSION")
    with open(version_path, "r") as f:
        version = f.read().strip()

    out_path = os.path.join(CLIENT_DIR, f"client_{version}.zip")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(CLIENT_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES]
            for fname in files:
                if fname in EXCLUDE_NAMES or os.path.splitext(fname)[1] in EXCLUDE_EXTS:
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, CLIENT_DIR)
                zf.write(full, rel)

    print(f"Tayyor: {out_path} (versiya {version})")
    print("Endi bu faylni Django admin (/admin/billing/clientbuild/add/) orqali yuklang.")


if __name__ == "__main__":
    main()
