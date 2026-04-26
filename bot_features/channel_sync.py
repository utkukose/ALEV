"""
bot_features/channel_sync.py — Telegram Kanal Skor Panosu

Bir Telegram kanalında sabit bir mesaj tutar ve
her skor değişiminde o mesajı günceller (edit_message).

Kurulum:
  1. Botu kanala admin olarak ekle
  2. .env'e ALEV_SCORE_CHANNEL_ID ekle
  3. İlk çalıştırmada /init_channel_post komutu gönder

Sonrası otomatik: skor değişince kanal mesajı güncellenir.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from core.config_loader import GameConfig
from core.game_engine import GameEngine
import core.db as db

log = logging.getLogger(__name__)

CHANNEL_ID   = int(os.getenv("ALEV_SCORE_CHANNEL_ID", "0"))
# İlk /init_channel_post'tan sonra bu ID'yi .env'e kaydedin
MESSAGE_ID_FILE = ".channel_message_id"


class ChannelSync:
    def __init__(self, cfg: GameConfig, engine: GameEngine, bot: Bot):
        self.cfg = cfg
        self.engine = engine
        self.bot = bot
        self._message_id: int | None = self._load_message_id()

    def _load_message_id(self) -> int | None:
        try:
            return int(open(MESSAGE_ID_FILE).read().strip())
        except Exception:
            return None

    def _save_message_id(self, mid: int):
        self._message_id = mid
        try:
            open(MESSAGE_ID_FILE, "w").write(str(mid))
        except Exception:
            pass

    def _build_scoreboard_text(self, takimlar: list[dict]) -> str:
        madalya = ["🥇", "🥈", "🥉"] + ["4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        brand = self.cfg.brand
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        lines = [
            f"🔥 *{brand.name} — Canlı Liderlik Tablosu*",
            f"_{brand.full_name}_",
            f"\n🕐 Son güncelleme: `{now}`\n",
        ]
        for i, t in enumerate(takimlar[:10]):
            lv  = self.cfg.level_for_xp(t["xp"])
            bar = self.engine.format_xp_bar(t["xp"], width=8)
            rol = self.engine.format_role(t["rol"])
            lines.append(
                f"{madalya[i]} *{t['ad']}*\n"
                f"   {rol} · Lv.{lv} · `{bar}` {t['xp']:,} XP"
            )
        lines.append(f"\n_ALEV v{brand.version} — Telegram üzerinden canlı_")
        return "\n".join(lines)

    async def init_channel_post(self) -> int | None:
        """Kanala ilk mesajı gönder, ID'yi kaydet."""
        if not CHANNEL_ID:
            log.warning("ALEV_SCORE_CHANNEL_ID ayarlanmamış.")
            return None
        takimlar = await db.liderlik_tablosu(10)
        text = self._build_scoreboard_text(takimlar)
        try:
            msg = await self.bot.send_message(
                CHANNEL_ID, text, parse_mode=ParseMode.MARKDOWN
            )
            self._save_message_id(msg.message_id)
            log.info(f"Kanal mesajı oluşturuldu: {msg.message_id}")
            return msg.message_id
        except TelegramError as e:
            log.error(f"Kanal mesajı gönderilemedi: {e}")
            return None

    async def update_channel_score(self):
        """Mevcut kanal mesajını güncelle. WebSocket onayından sonra çağrılır."""
        if not CHANNEL_ID or not self._message_id:
            return
        takimlar = await db.liderlik_tablosu(10)
        text = self._build_scoreboard_text(takimlar)
        try:
            await self.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=self._message_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except TelegramError as e:
            log.warning(f"Kanal mesajı güncellenemedi: {e}")
            # Mesaj silinmişse yeniden oluştur
            if "message to edit not found" in str(e).lower():
                await self.init_channel_post()

    async def pin_score_message(self):
        """Kanal mesajını sabitle."""
        if not CHANNEL_ID or not self._message_id: return
        try:
            await self.bot.pin_chat_message(CHANNEL_ID, self._message_id, disable_notification=True)
        except TelegramError as e:
            log.warning(f"Mesaj sabitlenemedi: {e}")
