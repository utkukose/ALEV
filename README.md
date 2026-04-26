# ALEV — Adaptive Live Event Venue for Telegram

> **Etkinliklerinizi alevlendirin.**

ALEV, hackathon, yarışma, kurs veya topluluk etkinlikleri için
YAML ile tam özelleştirilebilir, WebSocket destekli bir
gamification platformudur.

---

## Ne içeriyor?

| Bileşen | Açıklama |
|---------|----------|
| Telegram Botu | Takım kaydı, görev tamamlama, düello, liderlik |
| Web Paneli | Canlı sıralama, profil, görev geçmişi, feedback |
| Admin Paneli | Onay/red, XP düzenleme, düello başlatma, duyuru |
| Projeksiyon | Büyük ekran modu, podium, canlı ticker |
| i18n | Türkçe / İngilizce, genişletilebilir |

---

## Dosya yapısı

```
alev/
├── config/
│   ├── brand.yaml          ← Marka adı, renk, slogan (tek nokta)
│   ├── roles.yaml          ← Roller ve XP bonusları
│   ├── tasks.yaml          ← Görevler ve ödüller
│   ├── events.yaml         ← Etkinlik takvimi
│   └── attributes.yaml     ← Nitelikler ve rozetler
├── core/
│   ├── config_loader.py    ← YAML → Python veri sınıfları
│   ├── game_engine.py      ← Oyun mantığı (XP, seviye, duel)
│   └── db.py               ← PostgreSQL erişim katmanı
├── web/
│   ├── app.py              ← FastAPI + WebSocket + JWT
│   ├── i18n.py             ← Dil yöneticisi
│   ├── locales/
│   │   ├── tr.json
│   │   └── en.json
│   └── templates/
│       ├── shared/base.html
│       ├── admin/{login,dashboard}.html
│       ├── user/{login,leaderboard,profile,history}.html
│       └── projection.html
├── bot.py
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Hızlı başlangıç

```bash
# 1. Ayarları girin
cp .env.example .env
# .env dosyasını açıp ALEV_BOT_TOKEN ve diğerlerini doldurun

# 2. Marka adını özelleştirin (isteğe bağlı)
# config/brand.yaml içindeki name, tagline vb. alanları düzenleyin

# 3. Başlatın
docker compose up -d
```

Web paneli → http://sunucu:8000
Admin → http://sunucu:8000/admin
Projeksiyon → http://sunucu:8000/projection

---

## Marka özelleştirme

`config/brand.yaml` dosyasını düzenleyin:

```yaml
brand:
  name: "ALEV"                                    # Kısa ad
  full_name: "Adaptive Live Event Venue for Telegram"
  tagline_tr: "Etkinliklerinizi alevlendirin"
  tagline_en: "Ignite your events"
  version: "1.0.0"
  color_primary: "#D85A30"
```

Botu yeniden başlatın — her yere yansır.

---

## İçerik özelleştirme (kod yazmadan)

| Ne? | Nerede? |
|-----|---------|
| Rol / sınıf ekle | `config/roles.yaml` |
| Görev / ödül ekle | `config/tasks.yaml` |
| Etkinlik / bonus hafta | `config/events.yaml` |
| Nitelik / rozet ekle | `config/attributes.yaml` |
| Arayüz metni değiştir | `web/locales/tr.json` veya `en.json` |
| Marka adı değiştir | `config/brand.yaml` |

---

## Sayfalar

| URL | Erişim | Açıklama |
|-----|--------|----------|
| `/leaderboard` | Herkese açık | Canlı sıralama |
| `/login` | Herkese açık | Telegram ID ile giriş |
| `/profile` | Giriş gerekli | Profil, stat, rozetler |
| `/history` | Giriş gerekli | Geçmiş + feedback |
| `/projection` | Herkese açık | Büyük ekran modu |
| `/admin` | Admin | Yönetim paneli |
| `/api/leaderboard` | Herkese açık | JSON API |
| `/set-lang?lang=en` | Herkese açık | Dil değiştir |

---

## Nginx + HTTPS

```nginx
server {
    listen 80;
    server_name alev.ornekdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

```bash
sudo certbot --nginx -d alev.ornekdomain.com
```

---

## Hızlı komutlar

```bash
docker compose up -d                    # Başlat
docker compose logs -f                  # Loglar
docker compose restart web bot          # Config değişikliği uygula
docker compose exec db psql -U alev alev  # DB'ye bağlan
docker compose down -v                  # Sıfırla (DİKKAT: veri silinir)
```
