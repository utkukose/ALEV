"""
bot_features/scheduler.py — Zamanlanmış Mesajlar & Otomatik Senaryo

Gereksinim: pip install apscheduler

Özellikler:
  1. Senaryo starts_at doluysa otomatik başlatma
  2. Senaryo aşaması bitmeden X dakika önce hatırlatma
  3. Etkinlik başlamadan önce otomatik duyuru
  4. Periyodik skor yayını (ör. her saat liderlik tablosu)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram.ext import Application
from telegram.constants import ParseMode

from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db

log = logging.getLogger(__name__)


class ALEVScheduler:
    def __init__(self, cfg: GameConfig, engine: GameEngine,
                 bot_app: Application, group_ids: list[int],
                 admin_ids: list[int]):
        self.cfg = cfg
        self.engine = engine
        self.app = bot_app
        self.group_ids = group_ids      # Duyuru yapılacak grup chat_id listesi
        self.admin_ids = admin_ids
        self.scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    def start(self):
        """Tüm zamanlanmış görevleri kaydet ve başlat."""
        self._schedule_event_announcements()
        self._schedule_scenario_auto_start()
        self._schedule_periodic_score()
        self.scheduler.start()
        log.info("ALEVScheduler başlatıldı.")

    def stop(self):
        self.scheduler.shutdown(wait=False)

    # ─── Etkinlik duyuruları ───────────────────
    def _schedule_event_announcements(self):
        remind_before = self.cfg.events[0].xp_reward  # dummy — config'den al
        for event in self.cfg.events:
            if not event.announcement_channel:
                continue
            try:
                start_dt = datetime.fromisoformat(event.scheduled_at).astimezone(timezone.utc)
            except (ValueError, AttributeError):
                continue

            now = datetime.now(timezone.utc)
            # 60 dakika öncesi hatırlatma
            remind_at = start_dt - timedelta(minutes=60)
            if remind_at > now:
                self.scheduler.add_job(
                    self._send_event_reminder,
                    trigger=DateTrigger(run_date=remind_at),
                    args=[event.id],
                    id=f"remind_{event.id}",
                    replace_existing=True,
                )
            # Tam zamanında duyuru
            if start_dt > now:
                self.scheduler.add_job(
                    self._send_event_start,
                    trigger=DateTrigger(run_date=start_dt),
                    args=[event.id],
                    id=f"start_{event.id}",
                    replace_existing=True,
                )

    async def _send_event_reminder(self, event_id: str):
        event = self.cfg.event(event_id)
        if not event: return
        text_tr = f"⏰ *{event.title}* 60 dakika sonra başlıyor!\n{event.description.strip()[:120]}"
        text_en = f"⏰ *{event.title}* starts in 60 minutes!\n{event.description.strip()[:120]}"
        await self._broadcast(text_tr, text_en)

    async def _send_event_start(self, event_id: str):
        event = self.cfg.event(event_id)
        if not event: return
        text_tr = f"🚀 *{event.title}* BAŞLADI!\n{event.description.strip()[:200]}"
        text_en = f"🚀 *{event.title}* HAS STARTED!\n{event.description.strip()[:200]}"
        await self._broadcast(text_tr, text_en)

    # ─── Senaryo otomatik başlatma ────────────
    def _schedule_scenario_auto_start(self):
        for scenario in self.cfg.scenarios:
            if not scenario.active or not scenario.stages:
                continue
            first_stage = scenario.stages[0]
            if not first_stage.starts_at:
                continue
            try:
                start_dt = datetime.fromisoformat(first_stage.starts_at).astimezone(timezone.utc)
            except (ValueError, AttributeError):
                continue
            now = datetime.now(timezone.utc)
            if start_dt > now:
                self.scheduler.add_job(
                    self._auto_start_scenario,
                    trigger=DateTrigger(run_date=start_dt),
                    args=[scenario.id],
                    id=f"scenario_start_{scenario.id}",
                    replace_existing=True,
                )
                log.info(f"Senaryo '{scenario.id}' {start_dt} tarihinde otomatik başlatılacak.")
            # Aşama geçişlerini de planla
            for i, stage in enumerate(scenario.stages[1:], 1):
                if not stage.starts_at:
                    continue
                try:
                    stage_dt = datetime.fromisoformat(stage.starts_at).astimezone(timezone.utc)
                except (ValueError, AttributeError):
                    continue
                if stage_dt > now:
                    self.scheduler.add_job(
                        self._auto_advance_to_stage,
                        trigger=DateTrigger(run_date=stage_dt),
                        args=[scenario.id, stage.id],
                        id=f"stage_{scenario.id}_{stage.id}",
                        replace_existing=True,
                    )

    async def _auto_start_scenario(self, scenario_id: str):
        sc = self.cfg.scenario(scenario_id)
        if not sc or not sc.stages: return
        first = sc.stages[0]
        await db.senaryo_baslat(scenario_id, first.id)
        ann_tr = i18n.t("tr")("scenario.started",
            scenario_name=sc.name, stage_name=first.name, description=first.description.strip())
        ann_en = i18n.t("en")("scenario.started",
            scenario_name=sc.name, stage_name=first.name, description=first.description.strip())
        await self._broadcast(ann_tr, ann_en)
        log.info(f"Senaryo '{scenario_id}' otomatik başlatıldı.")

    async def _auto_advance_to_stage(self, scenario_id: str, stage_id: str):
        await db.senaryo_asama_guncelle(stage_id)
        sc = self.cfg.scenario(scenario_id)
        stage = sc.stage(stage_id) if sc else None
        if not stage: return
        ann_tr = i18n.t("tr")("scenario.advanced",
            stage_name=stage.name, description=stage.description.strip())
        ann_en = i18n.t("en")("scenario.advanced",
            stage_name=stage.name, description=stage.description.strip())
        await self._broadcast(ann_tr, ann_en)

    # ─── Periyodik skor yayını ─────────────────
    def _schedule_periodic_score(self):
        """Her saat başı aktif gruplara liderlik tablosu gönder."""
        self.scheduler.add_job(
            self._send_periodic_score,
            trigger=IntervalTrigger(hours=1),
            id="periodic_score",
            replace_existing=True,
        )

    async def _send_periodic_score(self):
        takimlar = await db.liderlik_tablosu(5)
        if not takimlar: return
        madalya = ["🥇","🥈","🥉","4️⃣","5️⃣"]
        brand = self.cfg.brand.name
        lines_tr = [f"📊 *{brand} — Güncel Sıralama*\n"]
        lines_en = [f"📊 *{brand} — Current Standings*\n"]
        for i, t in enumerate(takimlar):
            lv = self.cfg.level_for_xp(t["xp"])
            lines_tr.append(f"{madalya[i]} *{t['ad']}* — {t['xp']:,} XP · Lv.{lv}")
            lines_en.append(f"{madalya[i]} *{t['ad']}* — {t['xp']:,} XP · Lv.{lv}")
        await self._broadcast("\n".join(lines_tr), "\n".join(lines_en))

    # ─── Manuel görev zamanlama ───────────────
    def schedule_message(self, run_at: datetime, text_tr: str, text_en: str, job_id: str):
        """Admin tarafından tetiklenebilir özel zamanlı mesaj."""
        self.scheduler.add_job(
            self._broadcast,
            trigger=DateTrigger(run_date=run_at),
            args=[text_tr, text_en],
            id=job_id,
            replace_existing=True,
        )

    # ─── Broadcast yardımcısı ──────────────────
    async def _broadcast(self, text_tr: str, text_en: str):
        """Gruba göre dil seçerek yayın yapar.
        Şimdilik tüm gruplara TR, org gruba EN de gider."""
        bot = self.app.bot
        for gid in self.group_ids:
            if not gid: continue
            try:
                await bot.send_message(gid, text_tr, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                log.warning(f"Broadcast hatası ({gid}): {e}")
