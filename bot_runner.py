"""
bot_runner.py — ALEV Bot Başlatıcı

DB'deki tüm kayıtlı bot tokenlerini okur ve her biri için
polling loop başlatır. .env'de ALEV_BOT_TOKEN da varsa onu da başlatır.

Kullanım:
  python bot_runner.py
  
Docker:
  docker compose up bot
"""
import asyncio
import logging
import os

logging.basicConfig(
    format="%(asctime)s [BOT] %(levelname)s — %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


async def polling_loop(group_id: str, token: str, event_id: int | None):
    """Tek bir bot için sonsuz polling döngüsü."""
    import httpx
    import core.db as db
    from core.bot_handler import handle_update

    log.info(f"Polling başladı: {group_id}")
    offset = 0
    consecutive_errors = 0

    while True:
        try:
            async with httpx.AsyncClient(timeout=36) as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": 30, "limit": 100}
                )
                data = r.json()

            if not data.get("ok"):
                log.warning(f"Telegram API hatası ({group_id}): {data.get('description','')}")
                await asyncio.sleep(5)
                continue

            consecutive_errors = 0
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    # event_id'yi her seferinde taze al
                    eid = event_id
                    if not eid:
                        ev = await db.event_active()
                        eid = ev["id"] if ev else None
                    if eid:
                        await handle_update(upd, token, eid)
                except Exception as e:
                    log.warning(f"Update handler hatası: {e}")

        except asyncio.CancelledError:
            log.info(f"Polling durduruldu: {group_id}")
            break
        except Exception as e:
            consecutive_errors += 1
            wait = min(30, 2 ** consecutive_errors)
            log.warning(f"Polling hatası ({group_id}): {e} — {wait}s bekle")
            await asyncio.sleep(wait)


async def main():
    import core.db as db
    from core.bot_registry import TokenCipher

    # DB bağlantısı
    await db.init_pool()
    await db.init_schema()
    await db.init_lang_schema()

    cipher = TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY", ""))
    tasks = {}

    # DB'deki tokenlar
    tokens = await db.bot_token_list()
    for tok_row in tokens:
        gid   = tok_row["group_id"]
        raw   = cipher.decrypt(tok_row.get("encrypted_token", ""))
        eid   = tok_row.get("event_id")
        if raw and raw not in ("TOKEN_BURAYA", ""):
            # Webhook var mı kontrol et
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5) as c:
                    wr = await c.get(f"https://api.telegram.org/bot{raw}/getWebhookInfo")
                    wh_url = wr.json().get("result", {}).get("url", "")
                if wh_url:
                    log.info(f"Webhook aktif, polling atlandı: {gid} → {wh_url}")
                    continue
            except Exception:
                pass
            tasks[gid] = asyncio.create_task(polling_loop(gid, raw, eid))
            log.info(f"Bot başlatıldı (DB): {gid}")

    # .env token (DB'de yoksa)
    env_token = os.getenv("ALEV_BOT_TOKEN", "").strip()
    if env_token and env_token not in ("TOKEN_BURAYA", "") and "env" not in tasks:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as c:
                wr = await c.get(f"https://api.telegram.org/bot{env_token}/getWebhookInfo")
                wh_url = wr.json().get("result", {}).get("url", "")
            if not wh_url:
                ev = await db.event_active()
                eid = ev["id"] if ev else None
                tasks["env"] = asyncio.create_task(polling_loop("env", env_token, eid))
                log.info("Bot başlatıldı (.env ALEV_BOT_TOKEN)")
            else:
                log.info(f"Webhook aktif (.env token), polling atlandı: {wh_url}")
        except Exception as e:
            log.warning(f".env token hatası: {e}")

    if not tasks:
        log.warning(
            "Hiç bot token bulunamadı!\n"
            "  → Admin paneli → Bot Yönetimi → Token Ekle\n"
            "  → VEYA .env dosyasına ALEV_BOT_TOKEN= ekleyin\n"
            "30 saniyede bir yeniden denenecek..."
        )

    # Ana döngü: polling task'leri izle + yeni token kontrolü
    try:
        while True:
            await asyncio.sleep(30)
            # Yeni token DB'ye eklendiyse başlat
            try:
                fresh_tokens = await db.bot_token_list()
                for tok_row in fresh_tokens:
                    gid = tok_row["group_id"]
                    if gid in tasks and not tasks[gid].done():
                        continue  # Zaten çalışıyor
                    raw = cipher.decrypt(tok_row.get("encrypted_token", ""))
                    eid = tok_row.get("event_id")
                    if raw and raw not in ("TOKEN_BURAYA", ""):
                        import httpx as _hx
                        try:
                            async with _hx.AsyncClient(timeout=4) as _c:
                                _wr = await _c.get(f"https://api.telegram.org/bot{raw}/getWebhookInfo")
                                _wh = _wr.json().get("result",{}).get("url","")
                            if not _wh:
                                tasks[gid] = asyncio.create_task(polling_loop(gid, raw, eid))
                                log.info(f"Yeni bot başlatıldı: {gid}")
                        except Exception:
                            pass
            except Exception as e:
                log.warning(f"Token kontrol hatası: {e}")
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks.values():
            t.cancel()
        await db.close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot durduruldu.")
