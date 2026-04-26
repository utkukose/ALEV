"""
bot_features/mini_app.py — Telegram Mini App (WebApp)

Telegram içinde açılan tam ekran web paneli.
Mevcut ALEV web uygulaması doğrudan Mini App olarak kullanılır.

Kurulum:
  1. BotFather → /newapp veya /setmenubutton
  2. WEB_APP_URL = "https://alev.sirketiniz.com" (HTTPS zorunlu)
  3. Bot menü butonuna veya inline butona URL ekle

Telegram Mini App avantajları:
  - Telegram kullanıcı bilgileri otomatik iletilir (initData)
  - Geri tuşu, tema renkleri Telegram ile entegre
  - Kamera, konum, QR okuyucu erişimi
  - Ödeme entegrasyonu
"""
from __future__ import annotations
import hashlib, hmac, json, os
from urllib.parse import unquote

from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode

WEB_APP_URL = os.getenv("ALEV_WEB_APP_URL", "https://alev.example.com")
BOT_TOKEN   = os.getenv("ALEV_BOT_TOKEN", "")


def verify_webapp_data(init_data: str) -> dict | None:
    """
    Telegram'dan gelen initData'yı doğrular.
    Web uygulaması backend'inde çağrılmalı.
    Geçerliyse kullanıcı verilerini döndürür, değilse None.
    """
    try:
        pairs = dict(pair.split("=", 1) for pair in unquote(init_data).split("&"))
        received_hash = pairs.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected   = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received_hash, expected):
            return None
        user_data = json.loads(pairs.get("user", "{}"))
        return user_data
    except Exception:
        return None


class MiniAppManager:
    def __init__(self, web_app_url: str = WEB_APP_URL):
        self.url = web_app_url

    async def setup_menu_button(self, bot):
        """Bot ana menü butonunu WebApp olarak ayarla."""
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🔥 ALEV Panel",
                    web_app=WebAppInfo(url=self.url)
                )
            )
        except Exception as e:
            import logging; logging.warning(f"Mini App menü ayarlanamadı: {e}")

    async def cmd_panel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Kullanıcıya Mini App açan buton gönderir."""
        from core.bot_i18n import i18n
        import core.db as db
        lang = await db.kullanici_dil_getir(update.effective_user.id)
        if lang == "tr":
            btn_text = "🔥 ALEV Panelini Aç"
            msg_text = "Profilinizi, liderlik tablosunu ve jüri puanlarını görmek için:"
        else:
            btn_text = "🔥 Open ALEV Panel"
            msg_text = "To see your profile, leaderboard and jury scores:"

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                btn_text,
                web_app=WebAppInfo(url=self.url)
            )
        ]])
        await update.message.reply_text(msg_text, reply_markup=kb)

    async def cmd_leaderboard_app(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Doğrudan liderlik tablosunu Mini App'te aç."""
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📊 Canlı Liderlik / Live Leaderboard",
                web_app=WebAppInfo(url=f"{self.url}/leaderboard")
            )
        ]])
        await update.message.reply_text("Canlı sıralama:", reply_markup=kb)

    async def cmd_projection_app(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Projeksiyon modunu Mini App'te aç."""
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🎯 Projeksiyon Modu",
                web_app=WebAppInfo(url=f"{self.url}/projection")
            )
        ]])
        await update.message.reply_text("Büyük ekran modu:", reply_markup=kb)

    async def handle_web_app_data(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Mini App'ten gelen veriyi işle (ör. form submit)."""
        data = update.message.web_app_data
        if not data: return
        try:
            payload = json.loads(data.data)
            action = payload.get("action")
            if action == "feedback":
                # Feedback formundan gelen veri
                import core.db as db
                user_id = update.effective_user.id
                await db.conn().__aenter__()  # dummy — gerçekte db.feedback_kaydet çağırılır
                await update.message.reply_text("✅ Feedback alındı!", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"Veri işlenemedi: {e}")


def register_mini_app_handlers(app: Application, mgr: MiniAppManager):
    app.add_handler(CommandHandler("panel",       mgr.cmd_panel))
    app.add_handler(CommandHandler("leaderboard_app", mgr.cmd_leaderboard_app))
    app.add_handler(CommandHandler("projection",  mgr.cmd_projection_app))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, mgr.handle_web_app_data))
