"""
bot_features/task_buttons.py — Butonlu Görev Listesi

/tasks yazınca her görev tıklanabilir buton olarak gelir.
Butona basınca görev detayı + "Tamamladım" butonu çıkar.
"""
from __future__ import annotations
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db


class TaskButtonManager:
    def __init__(self, cfg: GameConfig, engine: GameEngine, admin_ids: list[int]):
        self.cfg = cfg
        self.engine = engine
        self.admin_ids = admin_ids

    def _task_list_keyboard(self, tasks, completed: set, lang: str) -> InlineKeyboardMarkup:
        """Her görev için bir satır buton üretir."""
        diff_emoji = {"kolay": "🟢", "orta": "🟡", "zor": "🔴", "efsane": "⭐"}
        rows = []
        for t in tasks:
            done = t.id in completed
            prefix = "✅ " if done else diff_emoji.get(t.difficulty, "🔷") + " "
            label = f"{prefix}{t.title[:32]}"
            if not done:
                rows.append([InlineKeyboardButton(label, callback_data=f"task_detail_{t.id}")])
            else:
                rows.append([InlineKeyboardButton(label, callback_data="task_done_noop")])
        return InlineKeyboardMarkup(rows)

    def _task_detail_keyboard(self, task_id: str, lang: str) -> InlineKeyboardMarkup:
        t = i18n.t(lang)
        label = "📎 Tamamladım / I'm done" if lang == "tr" else "📎 Mark as complete"
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(label, callback_data=f"task_start_{task_id}"),
            InlineKeyboardButton("◀ Geri / Back", callback_data="task_back"),
        ]])

    async def handle_tasks_command(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        lang = await db.kullanici_dil_getir(user.id)
        t_str = i18n.t(lang)
        takim = await db.takim_getir(user.id)
        completed = await db.tamamlanan_gorev_idleri(user.id) if takim else set()

        # Aktif senaryo aşamasına göre görev seti
        sd = await db.senaryo_durumu_getir()
        task_set = "default"
        stage_info = ""
        stage_mult = 1.0
        if sd:
            sc = self.cfg.scenario(sd["scenario_id"])
            if sc:
                stage = sc.stage(sd["current_stage"])
                if stage:
                    task_set = stage.task_set
                    stage_mult = stage.xp_multiplier
                    stage_info = f"\n⚡ *{stage.name}* — `{stage_mult}x XP`\n"

        tasks = self.cfg.active_tasks(task_set)
        header = t_str("tasks.header") + stage_info + "\n"
        header += f"{'Tamamlanan' if lang=='tr' else 'Completed'}: {len(completed & {t.id for t in tasks})}/{len(tasks)}"

        kb = self._task_list_keyboard(tasks, completed, lang)
        await update.message.reply_text(header, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

    async def handle_task_detail(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data == "task_done_noop":
            await query.answer("Bu görev zaten tamamlandı! ✅", show_alert=True)
            return
        if query.data == "task_back":
            # Görev listesine geri dön
            user = query.from_user
            lang = await db.kullanici_dil_getir(user.id)
            takim = await db.takim_getir(user.id)
            completed = await db.tamamlanan_gorev_idleri(user.id) if takim else set()
            sd = await db.senaryo_durumu_getir()
            task_set = "default"
            if sd:
                sc = self.cfg.scenario(sd["scenario_id"])
                if sc:
                    st = sc.stage(sd["current_stage"])
                    if st: task_set = st.task_set
            tasks = self.cfg.active_tasks(task_set)
            kb = self._task_list_keyboard(tasks, completed, lang)
            await query.edit_message_reply_markup(reply_markup=kb)
            return

        task_id = query.data.replace("task_detail_", "").replace("task_start_", "")
        task = self.cfg.task(task_id)
        if not task:
            await query.answer("Görev bulunamadı.", show_alert=True); return

        user = query.from_user
        lang = await db.kullanici_dil_getir(user.id)
        takim = await db.takim_getir(user.id)

        if query.data.startswith("task_start_"):
            # "Tamamladım" butonuna basıldı → kanıt iste
            msg = (
                f"📎 *{task.title}*\n\n"
                f"{'Kanıt linkinizi gönderin:' if lang=='tr' else 'Send your proof link:'}\n"
                f"`/complete {task.id} <link>`"
            )
            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀ Geri / Back", callback_data="task_back")
                ]]))
            return

        # Görev detayı göster
        ev_m = self.engine.get_active_event_multiplier(task.type)
        sd = await db.senaryo_durumu_getir()
        sm = self.engine.scenario.current_multiplier(sd["current_stage"] if sd else None)
        xp = int(task.xp_reward * ev_m * sm)
        diff_map_tr = {"kolay":"Kolay","orta":"Orta","zor":"Zor","efsane":"Efsane"}
        diff_map_en = {"kolay":"Easy","orta":"Medium","zor":"Hard","efsane":"Legendary"}
        diff = diff_map_tr[task.difficulty] if lang=="tr" else diff_map_en.get(task.difficulty, task.difficulty)

        msg = (
            f"📋 *{task.title}*\n\n"
            f"{task.description.strip()}\n\n"
            f"{'Ödül' if lang=='tr' else 'Reward'}: `+{xp} XP`"
            + (f" _(x{round(ev_m*sm,1)})_" if ev_m*sm != 1 else "") +
            f"\n{'Zorluk' if lang=='tr' else 'Difficulty'}: {diff}\n"
            f"{'Tür' if lang=='tr' else 'Type'}: `{task.type}`"
        )
        completed = await db.tamamlanan_gorev_idleri(user.id) if takim else set()
        if task_id in completed:
            msg += f"\n\n✅ {'Tamamlandı!' if lang=='tr' else 'Completed!'}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Geri / Back", callback_data="task_back")]])
        else:
            kb = self._task_detail_keyboard(task_id, lang)

        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


def register_task_button_handlers(app: Application, mgr: TaskButtonManager):
    app.add_handler(CommandHandler("tasks", mgr.handle_tasks_command))
    app.add_handler(CallbackQueryHandler(mgr.handle_task_detail, pattern=r"^task_"))
