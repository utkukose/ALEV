"""
bot_features/branching_scenario.py — Karar Ağacı Senaryo Motoru

Her takım kendi seçimlerine göre farklı bir yol izler.
Bir seçim, hangi görev kolunun açılacağını belirler.

config/branching_scenarios.yaml'da tanımlanır.
Bot inline klavyeyle seçenek sunar.

Örnek akış:
  Bot: "Takımınız hangi alana odaklanacak?"
       [💧 Su Ekosistemleri] [⚡ Yenilenebilir Enerji]
  Takım: Butona basar
  Bot: Su kolundaki görevler açılır, diğer kol gizlenir
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from core.config_loader import GameConfig
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db

log = logging.getLogger(__name__)
BRANCH_PATH = Path("config/branching_scenarios.yaml")


@dataclass
class BranchChoice:
    id: str
    label_tr: str
    label_en: str
    emoji: str
    next_node: str      # Sonraki düğüm ID'si
    xp_bonus: int = 0   # Seçim bonusu

    def label(self, lang="tr"):
        return self.label_tr if lang == "tr" else self.label_en


@dataclass
class BranchNode:
    id: str
    type: str               # "choice" | "task_set" | "end"
    title_tr: str
    title_en: str
    description_tr: str
    description_en: str
    choices: list[BranchChoice]
    task_set: str = ""      # type=="task_set" ise hangi görevler
    xp_multiplier: float = 1.0

    def title(self, lang="tr"):
        return self.title_tr if lang == "tr" else self.title_en
    def description(self, lang="tr"):
        return self.description_tr if lang == "tr" else self.description_en


@dataclass
class BranchingScenario:
    id: str
    name_tr: str
    name_en: str
    root_node: str          # Başlangıç düğümü
    nodes: dict[str, BranchNode]

    def name(self, lang="tr"):
        return self.name_tr if lang == "tr" else self.name_en
    def node(self, nid: str) -> BranchNode | None:
        return self.nodes.get(nid)


def load_branching_scenarios() -> dict[str, BranchingScenario]:
    if not BRANCH_PATH.exists():
        return {}
    data = yaml.safe_load(BRANCH_PATH.read_text(encoding="utf-8")) or {}
    result = {}
    for s in data.get("branching_scenarios", []):
        nodes = {}
        for n in s.get("nodes", []):
            choices = [
                BranchChoice(
                    id=c["id"], label_tr=c["label_tr"],
                    label_en=c.get("label_en", c["label_tr"]),
                    emoji=c.get("emoji", "▶"),
                    next_node=c["next_node"],
                    xp_bonus=c.get("xp_bonus", 0),
                )
                for c in n.get("choices", [])
            ]
            nodes[n["id"]] = BranchNode(
                id=n["id"], type=n["type"],
                title_tr=n["title_tr"], title_en=n.get("title_en", n["title_tr"]),
                description_tr=n.get("description_tr", ""),
                description_en=n.get("description_en", ""),
                choices=choices,
                task_set=n.get("task_set", ""),
                xp_multiplier=n.get("xp_multiplier", 1.0),
            )
        result[s["id"]] = BranchingScenario(
            id=s["id"], name_tr=s["name_tr"],
            name_en=s.get("name_en", s["name_tr"]),
            root_node=s["root_node"], nodes=nodes,
        )
    return result


class BranchingScenarioManager:
    def __init__(self, cfg: GameConfig, engine: GameEngine):
        self.cfg = cfg
        self.engine = engine
        self.scenarios = load_branching_scenarios()
        # team_id → {scenario_id, current_node, path: [...], task_set}
        self._state: dict[int, dict] = {}

    def reload(self):
        self.scenarios = load_branching_scenarios()

    def _save_state(self, team_id: int, state: dict):
        self._state[team_id] = state
        # Prod'da DB'ye yazılmalı

    def get_state(self, team_id: int) -> dict | None:
        return self._state.get(team_id)

    def current_task_set(self, team_id: int) -> str:
        state = self._state.get(team_id)
        return state.get("task_set", "default") if state else "default"

    def current_multiplier(self, team_id: int) -> float:
        state = self._state.get(team_id)
        if not state: return 1.0
        sc = self.scenarios.get(state.get("scenario_id", ""))
        if not sc: return 1.0
        node = sc.node(state.get("current_node", ""))
        return node.xp_multiplier if node else 1.0

    # ─── /branch <scenario_id> ─────────────────
    async def cmd_branch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        lang = await db.kullanici_dil_getir(user.id)
        takim = await db.takim_getir(user.id)
        if not takim:
            await update.message.reply_text(
                "Kayıtlı değilsiniz." if lang == "tr" else "Not registered."); return

        if not ctx.args:
            names = ", ".join(f"`{sid}`" for sid in self.scenarios)
            msg = (f"Kullanım: `/branch <senaryo_id>`\nMevcut: {names}"
                   if lang == "tr" else
                   f"Usage: `/branch <scenario_id>`\nAvailable: {names}")
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN); return

        sid = ctx.args[0]
        sc = self.scenarios.get(sid)
        if not sc:
            await update.message.reply_text(
                f"`{sid}` bulunamadı." if lang == "tr" else f"`{sid}` not found.",
                parse_mode=ParseMode.MARKDOWN); return

        # Başlangıç düğümünü göster
        state = {"scenario_id": sid, "current_node": sc.root_node, "path": [], "task_set": "default"}
        self._save_state(user.id, state)
        await self._show_node(update, ctx, sc, sc.root_node, user.id, lang)

    async def _show_node(
        self, update_or_query, ctx, sc: BranchingScenario,
        node_id: str, team_id: int, lang: str
    ):
        node = sc.node(node_id)
        if not node:
            return

        if node.type == "choice":
            # Seçim düğümü — butonlar göster
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{c.emoji} {c.label(lang)}",
                    callback_data=f"branch_{sc.id}_{c.id}_{node_id}"
                )
            ] for c in node.choices])
            msg = f"🌿 *{node.title(lang)}*\n\n{node.description(lang)}"
            if hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            else:
                await update_or_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

        elif node.type == "task_set":
            # Görev kolu açıldı
            state = self._state.get(team_id, {})
            state["task_set"] = node.task_set
            state["current_node"] = node_id
            self._save_state(team_id, state)
            tasks = self.cfg.active_tasks(node.task_set)
            task_list = "\n".join(f"• *{t.title}* (`+{t.xp_reward} XP`)" for t in tasks)
            mult_str = (f"\n⚡ Bu kolda `{node.xp_multiplier}x XP` çarpanı aktif!"
                        if node.xp_multiplier != 1.0 else "")
            msg = (
                f"✅ *{node.title(lang)}*\n\n{node.description(lang)}{mult_str}\n\n"
                f"Açılan görevler:\n{task_list}\n\n"
                f"/tasks yazarak görevleri görün."
            )
            if hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            else:
                await update_or_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

        elif node.type == "end":
            msg = f"🏁 *{node.title(lang)}*\n\n{node.description(lang)}"
            if hasattr(update_or_query, 'message'):
                await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            else:
                await update_or_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

    # ─── Seçim callback ──────────────────────
    async def handle_branch_choice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.split("_", 3)  # branch_{sc_id}_{choice_id}_{node_id}
        if len(parts) < 4: return
        _, sc_id, choice_id, node_id = parts
        sc = self.scenarios.get(sc_id)
        if not sc: return
        node = sc.node(node_id)
        if not node: return

        team_id = query.from_user.id
        lang = await db.kullanici_dil_getir(team_id)

        # Seçilen choice
        choice = next((c for c in node.choices if c.id == choice_id), None)
        if not choice: return

        # State güncelle
        state = self._state.get(team_id, {})
        state["path"] = state.get("path", []) + [{"node": node_id, "choice": choice_id}]
        state["current_node"] = choice.next_node
        self._save_state(team_id, state)

        # XP bonusu varsa ver
        if choice.xp_bonus:
            takim = await db.takim_getir(team_id)
            if takim:
                await db.xp_ekle(takim["id"], choice.xp_bonus, f"Seçim bonusu: {choice_id}")

        # Sonraki düğümü göster
        await self._show_node(query, ctx, sc, choice.next_node, team_id, lang)


def register_branching_handlers(app: Application, mgr: BranchingScenarioManager):
    app.add_handler(CommandHandler("branch", mgr.cmd_branch))
    app.add_handler(CallbackQueryHandler(
        mgr.handle_branch_choice, pattern=r"^branch_"))
