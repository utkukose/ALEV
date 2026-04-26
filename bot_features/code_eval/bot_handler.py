"""
bot_features/code_eval/bot_handler.py — Kod Değerlendirme Bot Entegrasyonu

Telegram akışı:
  Takım:  /submit karbon_hesaplayici
  Bot:    "Kodunuzu gönderin (text mesaj olarak)"
  Takım:  [kaynak kodu yapıştırır]
  Bot:    Değerlendirme çalışır → rapor gönderilir
  Admin:  Raporu görür, onaylar veya reddeder

Admin:   /eval_config karbon_hesaplayici
         → Referans kod ve çıktı tanımlama
"""
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import asdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler,
)
from telegram.constants import ParseMode

from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db
from bot_features.code_eval.evaluator import CodeEvaluator, FullEvalResult

log = logging.getLogger(__name__)

AWAITING_CODE = 1       # ConversationHandler state


class CodeEvalHandler:
    def __init__(self, cfg: GameConfig, engine: GameEngine, admin_ids: list[int]):
        self.cfg = cfg
        self.engine = engine
        self.admin_ids = admin_ids
        self.evaluator = CodeEvaluator()
        # task_id → {reference_code, reference_output, test_inputs}
        # Prod'da DB'de tutulur; şimdilik in-memory + JSON dosyası
        self._configs: dict[str, dict] = self._load_configs()
        # user_id → beklenen task_id
        self._pending: dict[int, str] = {}
        # task_id → {team_id: code} — plagiarizm için tüm göndermeler
        self._submissions: dict[str, dict[int, str]] = {}

    def _load_configs(self) -> dict:
        try:
            return json.loads(open("config/code_eval_configs.json").read())
        except Exception:
            return {}

    def _save_configs(self):
        try:
            json.dump(self._configs, open("config/code_eval_configs.json", "w"),
                      ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"Config kaydedilemedi: {e}")

    # ─── /submit <task_id> ────────────────────
    async def cmd_submit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        lang = await db.kullanici_dil_getir(user.id)
        t = i18n.t(lang)
        takim = await db.takim_getir(user.id)
        if not takim:
            await update.message.reply_text(t("errors.not_registered")); return

        if not ctx.args:
            # Kod gönderilebilecek görevleri listele
            tasks_with_eval = [
                task for task in self.cfg.active_tasks()
                if task.id in self._configs
            ]
            if not tasks_with_eval:
                msg = ("Şu an kod değerlendirmesi olan aktif görev yok."
                       if lang == "tr" else
                       "No tasks with code evaluation active.")
                await update.message.reply_text(msg); return
            ids = ", ".join(f"`{t.id}`" for t in tasks_with_eval)
            msg = (f"Kullanım: `/submit <görev_id>`\nKod görevi olan görevler: {ids}"
                   if lang == "tr" else
                   f"Usage: `/submit <task_id>`\nTasks with code eval: {ids}")
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN); return

        task_id = ctx.args[0]
        task = self.cfg.task(task_id)
        if not task:
            await update.message.reply_text(
                f"`{task_id}` geçersiz görev." if lang == "tr"
                else f"`{task_id}` is not a valid task.",
                parse_mode=ParseMode.MARKDOWN); return

        if task_id not in self._configs:
            await update.message.reply_text(
                "Bu görev için henüz referans kod tanımlanmamış. Admin ile iletişime geçin."
                if lang == "tr" else
                "No reference code configured for this task. Contact admin."); return

        self._pending[user.id] = task_id
        msg = (f"📎 *{task.title}* için kodunuzu gönderin.\n\n"
               f"Bir sonraki mesajınız kaynak kodunuz olarak alınacak.\n"
               f"Desteklenen diller: Python, JavaScript, SQL\n\n"
               f"_İptal için: /cancel_"
               if lang == "tr" else
               f"📎 Send your code for *{task.title}*.\n\n"
               f"Your next message will be taken as source code.\n"
               f"Supported: Python, JavaScript, SQL\n\n"
               f"_To cancel: /cancel_")
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # ─── Gelen kod mesajı ─────────────────────
    async def handle_code_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in self._pending:
            return  # Bu kullanıcı submit modunda değil
        lang = await db.kullanici_dil_getir(user.id)
        task_id = self._pending.pop(user.id)
        team_code = update.message.text or ""

        if not team_code.strip():
            await update.message.reply_text(
                "Boş kod gönderildi." if lang == "tr" else "Empty code received."); return

        takim = await db.takim_getir(user.id)
        task  = self.cfg.task(task_id)
        config = self._configs.get(task_id, {})

        # "Değerlendiriliyor..." mesajı
        waiting_msg = await update.message.reply_text(
            "⏳ Kod değerlendiriliyor..." if lang == "tr"
            else "⏳ Evaluating code...")

        # Tüm takım göndermelerini al (plagiarizm için)
        all_subs = dict(self._submissions.get(task_id, {}))
        all_subs[user.id] = team_code
        self._submissions.setdefault(task_id, {})[user.id] = team_code

        # Değerlendirme (I/O yoğun değil ama CPU yoğun olabilir — executor'da çalıştır)
        loop = asyncio.get_event_loop()
        result: FullEvalResult = await loop.run_in_executor(
            None,
            lambda: self.evaluator.evaluate(
                team_id=user.id,
                task_id=task_id,
                team_code=team_code,
                reference_code=config.get("reference_code", ""),
                reference_output=config.get("reference_output", ""),
                test_inputs=config.get("test_inputs"),
                all_submissions=all_subs,
                base_xp=task.xp_reward,
            )
        )

        # Değerlendirme mesajını sil
        try: await waiting_msg.delete()
        except Exception: pass

        # Raporu formatla
        report = self._format_report(result, task.title, lang)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

        # Admin bildirimi (plagiarizm riski > 70 ise özellikle vurgula)
        if result.passed or result.plagiarism_risk > 70:
            await self._notify_admins(ctx, takim, task, result, team_code, lang)

    def _format_report(self, r: FullEvalResult, task_title: str, lang: str) -> str:
        d = r.details
        status_emoji = "✅" if r.passed else "❌"

        def bar(score: float, width: int = 10) -> str:
            filled = int(score / 100 * width)
            return "█" * filled + "░" * (width - filled)

        if lang == "tr":
            lines = [
                f"📊 *Kod Değerlendirme Raporu*",
                f"Görev: *{task_title}*",
                f"Sonuç: {status_emoji} `{r.final_score}/100`\n",
                f"🎯 Çıktı Doğruluğu: `{bar(r.output_score)}` {r.output_score}",
                f"   _{d.get('output_feedback_tr', '')}_",
                f"",
                f"🔬 Algoritma Benzerliği: `{bar(r.similarity_score)}` {r.similarity_score}",
                f"   _{d.get('similarity_feedback_tr', '')}_",
                f"",
                f"✨ Kod Kalitesi: `{bar(r.quality_score)}` {r.quality_score}",
                f"   _{d.get('quality_feedback_tr', '')}_",
            ]
            plag_tr, _ = self.evaluator.plagiarism.risk_label(r.plagiarism_risk)
            lines.append(f"\n🔍 Özgünlük: {plag_tr} ({r.plagiarism_risk}%)")
            if r.passed:
                lines.append(f"\n🎉 Kazanılan XP: *+{r.xp_reward}*")
            else:
                lines.append(f"\n⚠️ Minimum eşiği geçemediniz. Kodu güncelleyip tekrar gönderin.")
        else:
            lines = [
                f"📊 *Code Evaluation Report*",
                f"Task: *{task_title}*",
                f"Result: {status_emoji} `{r.final_score}/100`\n",
                f"🎯 Output Accuracy: `{bar(r.output_score)}` {r.output_score}",
                f"   _{d.get('output_feedback_en', '')}_",
                f"",
                f"🔬 Algorithm Similarity: `{bar(r.similarity_score)}` {r.similarity_score}",
                f"   _{d.get('similarity_feedback_en', '')}_",
                f"",
                f"✨ Code Quality: `{bar(r.quality_score)}` {r.quality_score}",
                f"   _{d.get('quality_feedback_en', '')}_",
            ]
            _, plag_en = self.evaluator.plagiarism.risk_label(r.plagiarism_risk)
            lines.append(f"\n🔍 Originality: {plag_en} ({r.plagiarism_risk}%)")
            if r.passed:
                lines.append(f"\n🎉 XP Earned: *+{r.xp_reward}*")
            else:
                lines.append(f"\n⚠️ Did not meet minimum threshold. Update and resubmit.")
        return "\n".join(lines)

    async def _notify_admins(
        self, ctx, takim, task, result: FullEvalResult, code: str, lang: str
    ):
        plag_tr, plag_en = self.evaluator.plagiarism.risk_label(result.plagiarism_risk)
        admin_msg = (
            f"📬 *Kod Gönderimi*\n"
            f"Takım: *{takim['ad']}* | Görev: *{task.title}*\n"
            f"Final Skor: `{result.final_score}/100`\n"
            f"Çıktı: {result.output_score} | Benzerlik: {result.similarity_score} | "
            f"Kalite: {result.quality_score}\n"
            f"Özgünlük: {plag_tr} ({result.plagiarism_risk}%)\n"
        )
        if result.plagiarism_risk > 70:
            admin_msg += "\n⚠️ *YÜKSEK KOPYALamA RİSKİ — İnceleme gerekiyor!*"

        approve_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"✅ Onayla (+{result.xp_reward} XP)",
                callback_data=f"ceval_approve_{takim['id']}_{task.id}_{result.xp_reward}"
            ),
            InlineKeyboardButton(
                "❌ Reddet",
                callback_data=f"ceval_reject_{takim['id']}_{task.id}"
            ),
        ]])

        for aid in self.admin_ids:
            if not aid: continue
            try:
                await ctx.bot.send_message(
                    aid, admin_msg, parse_mode=ParseMode.MARKDOWN,
                    reply_markup=approve_kb if result.passed else None
                )
                # Kodu da gönder (çok uzunsa kısalt)
                code_preview = code[:3000] + "\n...[kısaltıldı]" if len(code) > 3000 else code
                await ctx.bot.send_message(aid, f"```\n{code_preview}\n```",
                                           parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                log.warning(f"Admin bildirimi hatası: {e}")

    # ─── Admin onay/red callback ──────────────
    async def handle_eval_decision(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.from_user.id not in self.admin_ids:
            await query.answer("Yetkisiz.", show_alert=True); return

        parts = query.data.split("_")
        # ceval_approve_{team_id}_{task_id}_{xp}
        # ceval_reject_{team_id}_{task_id}
        action = parts[1]
        team_id = int(parts[2])
        task_id = parts[3]
        takim = await db.takim_getir(team_id)
        task = self.cfg.task(task_id)

        if action == "approve":
            xp = int(parts[4]) if len(parts) > 4 else 0
            kanit = f"code_eval:{task_id}"
            onay_id = await db.onay_istegi_olustur(team_id, team_id, task_id, kanit)
            await db.gorev_onayla(onay_id, team_id, team_id, task_id, xp)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ *{takim['ad']}* → +{xp} XP onaylandı.",
                parse_mode=ParseMode.MARKDOWN)
            lang = await db.kullanici_dil_getir(team_id)
            await ctx.bot.send_message(
                team_id,
                f"🎉 Kodunuz onaylandı! *{task.title}* +*{xp} XP*"
                if lang == "tr" else
                f"🎉 Code approved! *{task.title}* +*{xp} XP*",
                parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_reply_markup(reply_markup=None)
            lang = await db.kullanici_dil_getir(team_id)
            await ctx.bot.send_message(
                team_id,
                f"❌ Kodunuz reddedildi. Düzenleyip tekrar gönderin: `/submit {task_id}`"
                if lang == "tr" else
                f"❌ Code rejected. Fix and resubmit: `/submit {task_id}`",
                parse_mode=ParseMode.MARKDOWN)

    # ─── Admin: referans kod tanımlama ────────
    async def cmd_eval_set(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        /eval_set <task_id>
        Sonraki mesajlar:
          1. Referans Python kodu
          2. Beklenen çıktı
        """
        if update.effective_user.id not in self.admin_ids:
            await update.message.reply_text("Yetkisiz."); return
        if not ctx.args:
            await update.message.reply_text("Kullanım: `/eval_set <task_id>`",
                                            parse_mode=ParseMode.MARKDOWN); return
        task_id = ctx.args[0]
        # Basit JSON formatında gönder
        await update.message.reply_text(
            f"*{task_id}* için referans config gönderin (JSON):\n\n"
            f"```\n"
            f'{{"reference_code": "def solution(n):\\n    return n*2",\n'
            f'"reference_output": "20",\n'
            f'"test_inputs": ["10\\n", "5\\n"]}}\n'
            f"```",
            parse_mode=ParseMode.MARKDOWN)
        self._pending[update.effective_user.id] = f"__config__{task_id}"

    async def handle_config_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in self._pending: return
        task_key = self._pending.get(user.id, "")
        if not task_key.startswith("__config__"): return
        task_id = task_key.replace("__config__", "")
        self._pending.pop(user.id)
        try:
            config = json.loads(update.message.text)
            self._configs[task_id] = config
            self._save_configs()
            await update.message.reply_text(
                f"✅ `{task_id}` için referans config kaydedildi.\n"
                f"Referans çıktı: `{config.get('reference_output','')}`",
                parse_mode=ParseMode.MARKDOWN)
        except json.JSONDecodeError as e:
            await update.message.reply_text(f"JSON hatası: {e}")

    # ─── /cancel ──────────────────────────────
    async def cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._pending.pop(update.effective_user.id, None)
        lang = await db.kullanici_dil_getir(update.effective_user.id)
        await update.message.reply_text(
            "İptal edildi." if lang == "tr" else "Cancelled.")


def register_code_eval_handlers(app: Application, handler: CodeEvalHandler):
    app.add_handler(CommandHandler("submit",   handler.cmd_submit))
    app.add_handler(CommandHandler("eval_set", handler.cmd_eval_set))
    app.add_handler(CommandHandler("cancel",   handler.cmd_cancel))
    app.add_handler(CallbackQueryHandler(
        handler.handle_eval_decision, pattern=r"^ceval_(approve|reject)_"))
    # Metin mesajları — submit ve config akışı için
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handler.handle_code_message))
