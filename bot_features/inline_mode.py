"""
bot_features/inline_mode.py — Telegram Inline Mod

@bot_adi <takım_adı> yazınca herhangi bir sohbette
takım profilini paylaşılabilir kart olarak gösterir.

BotFather'da inline mode aktif edilmeli:
  /setinline → @bot_adi → "takım adı ara..."

Kullanım: herhangi bir sohbette "@bot_adi su koruyucu"
"""
from __future__ import annotations
import time
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, InlineQueryHandler, ContextTypes

from core.config_loader import GameConfig
from core.game_engine import GameEngine
import core.db as db


class InlineModeManager:
    def __init__(self, cfg: GameConfig, engine: GameEngine):
        self.cfg = cfg
        self.engine = engine

    async def handle_inline_query(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.inline_query
        if query is None:
            return
        search = query.query.strip().lower()
        results = []

        if not search:
            # Boş sorgu → top 5 göster
            takimlar = await db.liderlik_tablosu(5)
        else:
            # Ada göre filtrele
            all_t = await db.liderlik_tablosu(50)
            takimlar = [t for t in all_t if search in t["ad"].lower()][:5]

        madalya = ["🥇", "🥈", "🥉"] + ["🔷"] * 47
        for i, t in enumerate(takimlar):
            lv  = self.cfg.level_for_xp(t["xp"])
            bar = self.engine.format_xp_bar(t["xp"])
            rol = self.engine.format_role(t["rol"])
            xp  = f"{t['xp']:,}"

            # Inline kart metni
            text = (
                f"🔥 *{t['ad']}* {madalya[i]}\n"
                f"{rol} · Lv.*{lv}*\n"
                f"`{bar}` {xp} XP\n"
                f"_{self.cfg.brand.name} — {self.cfg.brand.full_name}_"
            )
            # Başlık satırı
            title = f"{madalya[i]} {t['ad']} — {xp} XP"
            description = f"{rol} · Lv.{lv}"

            results.append(InlineQueryResultArticle(
                id=str(t["id"]),
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text=text,
                    parse_mode="Markdown",
                ),
                thumbnail_url=None,
            ))

        # Global sıralama linki de ekle
        results.append(InlineQueryResultArticle(
            id="leaderboard_link",
            title="📊 Tüm Liderlik Tablosu / Full Leaderboard",
            description=f"{self.cfg.brand.name} — güncel sıralama",
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"📊 *{self.cfg.brand.name} Liderlik Tablosu*\n"
                    f"_{self.cfg.brand.full_name}_\n\n"
                    f"Canlı sıralama için web paneline bakın."
                ),
                parse_mode="Markdown",
            ),
        ))

        await query.answer(results, cache_time=10, is_personal=True)


def register_inline_handlers(app: Application, mgr: InlineModeManager):
    app.add_handler(InlineQueryHandler(mgr.handle_inline_query))
