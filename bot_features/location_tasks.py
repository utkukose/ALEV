"""
bot_features/location_tasks.py — Konum Bazlı Görev Doğrulama

Katılımcı belirli bir lokasyona gittiğinde konum paylaşır,
bot koordinatları kontrol eder ve görevi otomatik onaylar.

config/location_tasks.yaml'da lokasyon tanımları yapılır.
Tolerans yarıçapı (metre) ayarlanabilir.
"""
from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode

from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db

log = logging.getLogger(__name__)
LOC_TASKS_PATH = Path("config/location_tasks.yaml")


@dataclass
class LocationTask:
    task_id: str          # tasks.yaml'daki görev ID ile eşleşir
    name_tr: str
    name_en: str
    lat: float
    lon: float
    radius_meters: float  # Kabul edilen tolerans yarıçapı
    hint_tr: str = ""     # Katılımcıya ipucu
    hint_en: str = ""

    def name(self, lang="tr"): return self.name_tr if lang=="tr" else self.name_en
    def hint(self, lang="tr"): return self.hint_tr if lang=="tr" else self.hint_en


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """İki koordinat arasındaki mesafeyi metre olarak hesaplar."""
    R = 6371000  # Dünya yarıçapı (metre)
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_location_tasks() -> list[LocationTask]:
    if not LOC_TASKS_PATH.exists():
        return []
    data = yaml.safe_load(LOC_TASKS_PATH.read_text(encoding="utf-8")) or {}
    return [
        LocationTask(
            task_id=lt["task_id"],
            name_tr=lt["name_tr"], name_en=lt.get("name_en", lt["name_tr"]),
            lat=lt["lat"], lon=lt["lon"],
            radius_meters=lt.get("radius_meters", 100),
            hint_tr=lt.get("hint_tr", ""),
            hint_en=lt.get("hint_en", ""),
        )
        for lt in data.get("location_tasks", [])
    ]


class LocationTaskManager:
    def __init__(self, cfg: GameConfig, engine: GameEngine, admin_ids: list[int]):
        self.cfg = cfg
        self.engine = engine
        self.admin_ids = admin_ids
        self.location_tasks = load_location_tasks()
        # user_id → beklenen task_id (konum göndermesi beklenen kullanıcılar)
        self._pending: dict[int, str] = {}

    def reload(self):
        self.location_tasks = load_location_tasks()

    def _find_matching_task(self, lat: float, lon: float) -> LocationTask | None:
        """Verilen koordinata yakın konum görevi döndürür."""
        for lt in self.location_tasks:
            dist = _haversine(lat, lon, lt.lat, lt.lon)
            if dist <= lt.radius_meters:
                return lt
        return None

    async def cmd_checkin(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Kullanıcıdan konum göndermesini ister."""
        user = update.effective_user
        lang = await db.kullanici_dil_getir(user.id)
        takim = await db.takim_getir(user.id)
        if not takim:
            await update.message.reply_text(
                "Kayıtlı değilsiniz." if lang=="tr" else "You are not registered."); return

        if not self.location_tasks:
            await update.message.reply_text(
                "Aktif konum görevi yok." if lang=="tr" else "No active location tasks."); return

        # Aktif konum görevlerini listele
        completed = await db.tamamlanan_gorev_idleri(user.id)
        active = [lt for lt in self.location_tasks if lt.task_id not in completed]
        if not active:
            await update.message.reply_text(
                "Tüm konum görevleri tamamlandı! 🎉" if lang=="tr"
                else "All location tasks completed! 🎉"); return

        lines = ["📍 *Konum Görevleri*\n" if lang=="tr" else "📍 *Location Tasks*\n"]
        for lt in active:
            lines.append(f"• *{lt.name(lang)}*")
            if lt.hint(lang): lines.append(f"  _{lt.hint(lang)}_")
        if lang=="tr":
            lines.append("\nKonumunuzu paylaşın:")
        else:
            lines.append("\nShare your location:")

        kb = ReplyKeyboardMarkup(
            [[KeyboardButton(
                "📍 Konumumu Paylaş" if lang=="tr" else "📍 Share My Location",
                request_location=True
            )]],
            one_time_keyboard=True, resize_keyboard=True
        )
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

    async def handle_location(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Gelen konum mesajını işle."""
        user = update.effective_user
        loc = update.message.location
        if not loc: return
        lang = await db.kullanici_dil_getir(user.id)
        takim = await db.takim_getir(user.id)
        if not takim:
            await update.message.reply_text(
                "Kayıtlı değilsiniz." if lang=="tr" else "Not registered.",
                reply_markup=ReplyKeyboardRemove()); return

        matched = self._find_matching_task(loc.latitude, loc.longitude)
        completed = await db.tamamlanan_gorev_idleri(user.id)

        if not matched:
            await update.message.reply_text(
                "📍 Bu konumda aktif bir görev bulunamadı.\n"
                "Doğru noktada olduğunuzdan emin olun." if lang=="tr"
                else "📍 No active task found at this location.\nMake sure you're at the right spot.",
                reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN); return

        if matched.task_id in completed:
            await update.message.reply_text(
                f"✅ *{matched.name(lang)}* zaten tamamlandı!" if lang=="tr"
                else f"✅ *{matched.name(lang)}* already completed!",
                parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove()); return

        task = self.cfg.task(matched.task_id)
        if not task:
            await update.message.reply_text(
                "Görev yapılandırma hatası.", reply_markup=ReplyKeyboardRemove()); return

        # Konum görevi otomatik onaylanır — admin onayı gerekmez
        sd = await db.senaryo_durumu_getir()
        sm = self.engine.scenario.current_multiplier(sd["current_stage"] if sd else None)
        ev_m = self.engine.get_active_event_multiplier(task.type)
        import json
        stats = takim.get("stats") or {}
        if isinstance(stats, str):
            try: stats = json.loads(stats)
            except: stats = {}
        result = self.engine.calculate_xp(task, takim["rol"], takim["xp"], stats, ev_m, sm)
        new_stats = self.engine.attr.apply_action("task_complete", stats, task.type, stage_mult=sm)
        # Kanıt olarak koordinat bilgisi
        kanit = f"📍 {loc.latitude:.5f},{loc.longitude:.5f}"
        onay_id = await db.onay_istegi_olustur(user.id, user.id, task.id, kanit)
        await db.gorev_onayla(onay_id, takim["id"], user.id, task.id, result.final_xp)
        await db.stats_guncelle(takim["id"], new_stats)

        bonus_tag = f" _(x{round(result.bonus_multiplier,1)})_" if result.bonus_applied else ""
        attr_str = self.engine.format_attr_changes(result.attr_changes)

        if lang == "tr":
            msg = (f"✅ *{matched.name_tr}* doğrulandı!\n"
                   f"+*{result.final_xp} XP*{bonus_tag}")
        else:
            msg = (f"✅ *{matched.name_en}* verified!\n"
                   f"+*{result.final_xp} XP*{bonus_tag}")

        if attr_str: msg += f"\n{attr_str}"
        if result.leveled_up: msg += f"\n\n🆙 Lv.{result.level_after}!"
        await update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())

        log.info(f"Konum görevi onaylandı: {user.id} → {matched.task_id} @ "
                 f"{loc.latitude:.4f},{loc.longitude:.4f}")


def register_location_handlers(app: Application, mgr: LocationTaskManager):
    app.add_handler(CommandHandler("checkin", mgr.cmd_checkin))
    app.add_handler(MessageHandler(filters.LOCATION, mgr.handle_location))
