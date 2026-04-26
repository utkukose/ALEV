"""
bot_features/quiz.py — Telegram Quiz Sistemi

Kullanım (bot.py'de):
    from bot_features.quiz import QuizManager, register_quiz_handlers
    quiz_mgr = QuizManager(cfg, engine)
    register_quiz_handlers(app, quiz_mgr)

Admin komutu: /quiz <quiz_id>
Quiz tanımları: config/quizzes.yaml

Telegram'ın native Poll/Quiz özelliğini kullanır — 
doğru cevap otomatik gösterilir, bot cevabı yakalar.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import yaml

from telegram import Update, Poll
from telegram.ext import (
    Application, CommandHandler, PollAnswerHandler, ContextTypes
)
from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db

QUIZ_CONFIG_PATH = Path("config/quizzes.yaml")


@dataclass
class QuizQuestion:
    id: str
    text_tr: str
    text_en: str
    options_tr: list[str]
    options_en: list[str]
    correct_index: int      # 0 tabanlı doğru cevap indeksi
    xp_reward: int
    explanation_tr: str = ""
    explanation_en: str = ""

    def text(self, lang="tr"): return self.text_tr if lang=="tr" else self.text_en
    def options(self, lang="tr"): return self.options_tr if lang=="tr" else self.options_en
    def explanation(self, lang="tr"): return self.explanation_tr if lang=="tr" else self.explanation_en


@dataclass
class QuizSet:
    id: str
    title_tr: str
    title_en: str
    questions: list[QuizQuestion]
    cooldown_minutes: int = 60  # Aynı kullanıcı kaç dakika sonra tekrar katılabilir

    def title(self, lang="tr"): return self.title_tr if lang=="tr" else self.title_en


def load_quizzes() -> dict[str, QuizSet]:
    if not QUIZ_CONFIG_PATH.exists():
        return {}
    data = yaml.safe_load(QUIZ_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    result = {}
    for qs in data.get("quiz_sets", []):
        questions = [
            QuizQuestion(
                id=q["id"],
                text_tr=q["text_tr"], text_en=q.get("text_en", q["text_tr"]),
                options_tr=q["options_tr"], options_en=q.get("options_en", q["options_tr"]),
                correct_index=q["correct_index"],
                xp_reward=q.get("xp_reward", 50),
                explanation_tr=q.get("explanation_tr", ""),
                explanation_en=q.get("explanation_en", ""),
            )
            for q in qs.get("questions", [])
        ]
        result[qs["id"]] = QuizSet(
            id=qs["id"], title_tr=qs["title_tr"],
            title_en=qs.get("title_en", qs["title_tr"]),
            questions=questions,
            cooldown_minutes=qs.get("cooldown_minutes", 60),
        )
    return result


class QuizManager:
    def __init__(self, cfg: GameConfig, engine: GameEngine):
        self.cfg = cfg
        self.engine = engine
        self.quiz_sets = load_quizzes()
        # poll_id → (quiz_id, question, chat_id)
        self._active: dict[str, tuple[str, QuizQuestion, int]] = {}
        # user_id → set(quiz_id) — cooldown takibi (prod'da Redis/DB kullanılmalı)
        self._answered: dict[int, dict[str, float]] = {}

    def reload(self):
        self.quiz_sets = load_quizzes()

    async def send_quiz(
        self, ctx: ContextTypes.DEFAULT_TYPE,
        chat_id: int, quiz_id: str, question_idx: int = 0, lang: str = "tr"
    ) -> bool:
        qs = self.quiz_sets.get(quiz_id)
        if not qs or question_idx >= len(qs.questions):
            return False
        q = qs.questions[question_idx]
        msg = await ctx.bot.send_poll(
            chat_id=chat_id,
            question=q.text(lang),
            options=q.options(lang),
            type=Poll.QUIZ,
            correct_option_id=q.correct_index,
            explanation=q.explanation(lang) or None,
            is_anonymous=False,  # Kim cevapladı bilinsin → XP verilebilsin
            open_period=60,       # 60 saniye açık
        )
        self._active[msg.poll.id] = (quiz_id, q, chat_id)
        return True

    async def send_quiz_set(
        self, ctx: ContextTypes.DEFAULT_TYPE,
        chat_id: int, quiz_id: str, lang: str = "tr", delay_secs: int = 5
    ):
        """Tüm soruları sırayla gönder (aralarında delay_secs saniye bekle)."""
        qs = self.quiz_sets.get(quiz_id)
        if not qs: return
        for i in range(len(qs.questions)):
            await self.send_quiz(ctx, chat_id, quiz_id, i, lang)
            if i < len(qs.questions) - 1:
                await asyncio.sleep(delay_secs)

    async def handle_poll_answer(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ):
        answer = update.poll_answer
        poll_id = answer.poll_id
        user_id = answer.user.id
        if poll_id not in self._active:
            return
        quiz_id, question, chat_id = self._active[poll_id]
        selected = answer.option_ids[0] if answer.option_ids else -1
        if selected != question.correct_index:
            return  # Yanlış cevap — XP yok

        # Cooldown kontrolü
        import time
        qs = self.quiz_sets.get(quiz_id)
        now = time.time()
        user_answers = self._answered.setdefault(user_id, {})
        last = user_answers.get(quiz_id, 0)
        cooldown = (qs.cooldown_minutes if qs else 60) * 60
        if now - last < cooldown:
            remaining = int((cooldown - (now - last)) / 60)
            try:
                lang = await db.kullanici_dil_getir(user_id)
                t = i18n.t(lang)
                await ctx.bot.send_message(
                    user_id,
                    f"⏳ {remaining} dakika sonra tekrar katılabilirsiniz.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        user_answers[quiz_id] = now
        takim = await db.takim_getir(user_id)
        if not takim:
            return
        xp = question.xp_reward
        await db.xp_ekle(takim["id"], xp, f"Quiz: {question.id}")
        lang = await db.kullanici_dil_getir(user_id)
        try:
            await ctx.bot.send_message(
                chat_id,
                f"✅ *{answer.user.first_name}* doğru cevapladı! +{xp} XP"
                if lang == "tr" else
                f"✅ *{answer.user.first_name}* got it right! +{xp} XP",
                parse_mode="Markdown"
            )
        except Exception:
            pass


def register_quiz_handlers(app: Application, quiz_mgr: QuizManager, admin_ids: list[int]):
    async def cmd_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in admin_ids:
            await update.message.reply_text("Yetkisiz / Unauthorized."); return
        if not ctx.args:
            sets = ", ".join(f"`{k}`" for k in quiz_mgr.quiz_sets)
            await update.message.reply_text(
                f"Kullanım: `/quiz <quiz_id>`\nMevcut: {sets}", parse_mode="Markdown"); return
        quiz_id = ctx.args[0]
        chat_id = update.effective_chat.id
        lang = await db.kullanici_dil_getir(update.effective_user.id)
        ok = await quiz_mgr.send_quiz_set(ctx, chat_id, quiz_id, lang)
        if not ok:
            await update.message.reply_text(f"`{quiz_id}` bulunamadı.", parse_mode="Markdown")

    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(PollAnswerHandler(quiz_mgr.handle_poll_answer))
