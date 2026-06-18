from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import re
import pytz
from datetime import datetime, timedelta

app = Flask(__name__)
LUX = pytz.timezone("Europe/Luxembourg")
scheduler = BackgroundScheduler(timezone=LUX)
scheduler.start()

ID_INSTANCE = "7107654600"
API_TOKEN = "f7806905c9c147fda53ad017bea347c79d9c1fa2380044d7bd"
KENDI_NUMARA = "905336558434"

BASE_URL = "https://api.green-api.com/waInstance" + ID_INSTANCE

hatirlatmalar = {}
sayac = {"n": 0}


def simdi():
    return datetime.now(LUX)


def mesaj_gonder(numara, metin):
    url = BASE_URL + "/sendMessage/" + API_TOKEN
    payload = {"chatId": numara + "@c.us", "message": metin}
    requests.post(url, json=payload)


def parse_sure(metin):
    metin = metin.lower().strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(sa|saat|dk|dak|dakika|h|min)$", metin)
    if not m:
        return None
    sayi = float(m.group(1))
    birim = m.group(2)
    if birim in ("sa", "saat", "h"):
        return int(sayi * 60)
    return int(sayi)


def parse_saat(metin):
    m = re.match(r"^(\d{1,2}):(\d{2})$", metin.strip())
    if not m:
        return None
    saat = int(m.group(1))
    dakika = int(m.group(2))
    if not (0 <= saat <= 23 and 0 <= dakika <= 59):
        return None
    s = simdi()
    hedef = s.replace(hour=saat, minute=dakika, second=0, microsecond=0)
    if hedef <= s:
        hedef += timedelta(days=1)
    return hedef


def parse_tarih_saat(metin):
    metin = metin.strip()
    formatlar = ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M"]
    for fmt in formatlar:
        try:
            dt = datetime.strptime(metin, fmt)
            return LUX.localize(dt)
        except ValueError:
            continue
    return None


def hatirlatma_gonder(hat_id, numara, icerik, hedef_numara=None):
    alici = hedef_numara if hedef_numara else numara
    mesaj_gonder(alici, "HATIRLATMA: " + icerik)
    if hat_id in hatirlatmalar:
        del hatirlatmalar[hat_id]


def komut_isle(numara, metin):
    metin = metin.strip()
    alt = metin.lower()

    if alt in ("listele", "liste"):
        if not hatirlatmalar:
            return "Aktif hatirlatma yok."
        satirlar = ["Aktif Hatirlatmalar:"]
        for hid, h in hatirlatmalar.items():
            zaman_str = h["zaman"].strftime("%d.%m.%Y %H:%M")
            hedef = " -> " + h["hedef"] if h.get("hedef") else ""
            satirlar.append("[" + hid + "] " + zaman_str + " - " + h["icerik"] + hedef)
        return "\n".join(satirlar)

    if alt.startswith("iptal"):
        parcalar = metin.split(None, 1)
        if len(parcalar) < 2:
            return "Kullanim: iptal 3  veya  iptal hepsi"
        arg = parcalar[1].strip().lower()
        if arg == "hepsi":
            for hid in list(hatirlatmalar.keys()):
                try:
                    scheduler.remove_job(hid)
                except Exception:
                    pass
            hatirlatmalar.clear()
            return "Tum hatirlatmalar silindi."
        if arg in hatirlatmalar:
            try:
                scheduler.remove_job(arg)
            except Exception:
                pass
            del hatirlatmalar[arg]
            return "[" + arg + "] silindi."
        return "[" + arg + "] bulunamadi."

    if alt.startswith("hatirla"):
        parcalar = metin.split(None, 1)
        if len(parcalar) < 2:
            return "Kullanim: hatirla 30dk gorev adi"
        geri_kalan = parcalar[1].strip()

        hedef_numara = None
        if "->" in geri_kalan:
            bolumler = geri_kalan.split("->", 1)
            geri_kalan = bolumler[0].strip()
            hedef_numara = bolumler[1].strip().replace("+", "").replace(" ", "")

        hedef_zaman = None
        ts_match = re.match(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}|\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})\s+(.+)$",
            geri_kalan
        )
        if ts_match:
            hedef_zaman = parse_tarih_saat(ts_match.group(1))
            icerik = ts_match.group(2).strip()
        else:
            ilk_kelime = geri_kalan.split(None, 1)
            if len(ilk_kelime) < 2:
                return "Gorev adi eksik. Ornek: hatirla 30dk ilac al"
            sure_veya_saat = ilk_kelime[0]
            icerik = ilk_kelime[1].strip()

            if ":" in sure_veya_saat:
                hedef_zaman = parse_saat(sure_veya_saat)
                if hedef_zaman is None:
                    return "Gecersiz saat. Ornek: 14:30"
            else:
                dakika = parse_sure(sure_veya_saat)
                if dakika is None:
                    return "Sureyi anlayamadim. Ornek: 30dk veya 2sa"
                hedef_zaman = simdi() + timedelta(minutes=dakika)

        if hedef_zaman is None:
            return "Zaman formati hatali."
        if hedef_zaman <= simdi():
            return "Belirtilen zaman gecmiste kalmis."

        sayac["n"] += 1
        hid = str(sayac["n"])
        hatirlatmalar[hid] = {
            "icerik": icerik,
            "zaman": hedef_zaman,
            "hedef": hedef_numara
        }
        scheduler.add_job(
            hatirlatma_gonder,
            "date",
            run_date=hedef_zaman,
            args=[hid, numara, icerik, hedef_numara],
            id=hid
        )
        zaman_str = hedef_zaman.strftime("%d.%m.%Y %H:%M")
        hedef_str = " -> " + hedef_numara if hedef_numara else ""
        return "OK [" + hid + "] " + zaman_str + " - " + icerik + hedef_str

    if alt in ("yardim", "?", "help"):
        return (
            "Komutlar:\n"
            "  hatirla 30dk gorev\n"
            "  hatirla 14:30 gorev\n"
            "  hatirla 2026-06-16 09:00 gorev\n"
            "  hatirla 30dk gorev -> 352XXXXXXXX\n"
            "  listele\n"
            "  iptal 3\n"
            "  iptal hepsi"
        )

    return None


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return "ok"
    try:
        tip = data.get("typeWebhook", "")
        if tip != "incomingMessageReceived":
            return "ok"
        msg_data = data.get("messageData", {})
        if msg_data.get("typeMessage", "") != "textMessage":
            return "ok"
        metin = msg_data["textMessageData"]["textMessage"]
        numara = data["senderData"]["sender"].replace("@c.us", "")
        if numara != KENDI_NUMARA:
            return "ok"
        yanit = komut_isle(numara, metin)
        if yanit:
            mesaj_gonder(numara, yanit)
    except Exception as e:
        print("Hata: " + str(e))
    return "ok"


if __name__ == "__main__":
    print("Bot basladi")
    app.run(host="0.0.0.0", port=10000, debug=False)
