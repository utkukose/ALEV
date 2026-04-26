"""ALEV Telegram bot — TR/EN komut işleme."""
import logging
log = logging.getLogger(__name__)

DIFF_EMOJI = {
    "kolay": "🟢", "easy": "🟢",
    "orta": "🟡", "medium": "🟡",
    "zor": "🔴", "hard": "🔴",
    "efsane": "💀", "legendary": "💀",
}
MEDAL = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def bp_label(lang): return "BP" if lang == "tr" else "SP"


def t(lang, key, **kw):
    """Basit çeviri fonksiyonu."""
    msgs = {
        "tr": {
            "no_team":          "❌ Önce takıma katıl: <code>/join DAVET_KODU</code>",
            "join_usage":       "📌 Kullanım: <code>/join DAVET_KODU</code>",
            "join_invalid":     "❌ Geçersiz davet kodu.",
            "join_full":        "❌ Takım dolu.",
            "join_already":     "ℹ️ Zaten bu takımdasın.",
            "role_warn":        "\n\n⚠️ <b>Henüz rol seçmedin!</b>\nGörev göndermek için önce rol seç:\n/role_list — rolleri gör\n/role NUMARA — rol seç",
            "role_warn_block":  "⚠️ <b>Rol seçmedin!</b>\n\nGörev göndermek için önce rol seçmen gerekiyor.\n\n1️⃣ /role_list — rolleri listele\n2️⃣ /role NUMARA — rolünü seç",
            "no_active_sc":     "ℹ️ Henüz aktif senaryo yok.",
            "no_tasks":         "ℹ️ Henüz aktif görev yok.",
            "sc_done_all":      "🏆 Tebrikler! <b>{sc}</b> senaryosunu tamamladınız.\nYeni senaryo açıldığında burada görünecek.",
            "task_invalid":     "❌ Geçersiz görev ID.",
            "task_wrong_sc":    "❌ Bu görev aktif senaryoya ait değil.",
            "task_already":     "ℹ️ Bu görevi zaten gönderdin.",
            "limit_hit":        "🚫 Bu etkinlikte en fazla {max} görev tamamlayabilirsin.\nLimitine ulaştın ({done}/{max}).",
            "submit_ok":        "📤 <b>Gönderildi!</b>\n\n📌 Görev: <b>{title}</b>\n💰 Onaylanırsa: <b>+{sp} {bp}</b>\n\n⏳ Admin onayı bekleniyor...",
            "submit_usage":     "📤 Kullanım: <code>/submit GÖREV_ID LINK</code>\nÖrnek: <code>/submit {ex} https://drive.google.com/...</code>",
            "no_role_defined":  "ℹ️ Rol tanımlanmamış.",
            "role_invalid":     "❌ Geçersiz numara. /role_list",
            "role_notfound":    "❌ Rol bulunamadı.",
            "role_ok":          "✅ Rol güncellendi!\n\n{emoji} <b>{name}</b>{attrs}",
            "role_attrs":       "\n\n📊 Başlangıç nitelikleri:\n{a}",
            "role_list_header": "⚔️ <b>ROL LİSTESİ</b>\n",
            "role_select_hint": "Seçmek için: <code>/role NUMARA</code>",
            "no_scores":        "ℹ️ Henüz puan yok.",
            "scores_header":    "🏆 <b>LİDERLİK TABLOSU</b>\n{event}\n",
            "my_rank":          "\n📍 Takımın: <b>{rank}. sırada</b>",
            "status_no_team":   "❌ Bu komut için takımda olman gerekiyor.",
            "profile_notfound": "❌ Profil bulunamadı.",
            "limit_info":       "\n📊 Kişisel limit: <b>{done}/{max}</b> görev",
            "unknown_cmd":      "❓ Bilinmeyen komut.\n/help yazarak tüm komutları görebilirsin.",
        },
        "en": {
            "no_team":          "❌ Join a team first: <code>/join INVITE_CODE</code>",
            "join_usage":       "📌 Usage: <code>/join INVITE_CODE</code>",
            "join_invalid":     "❌ Invalid invite code.",
            "join_full":        "❌ Team is full.",
            "join_already":     "ℹ️ You're already in this team.",
            "role_warn":        "\n\n⚠️ <b>You haven't selected a role yet!</b>\nSelect a role before submitting tasks:\n/role_list — see roles\n/role NUMBER — select role",
            "role_warn_block":  "⚠️ <b>No role selected!</b>\n\nYou need to select a role before submitting tasks.\n\n1️⃣ /role_list — list roles\n2️⃣ /role NUMBER — select your role",
            "no_active_sc":     "ℹ️ No active scenario yet.",
            "no_tasks":         "ℹ️ No active tasks yet.",
            "sc_done_all":      "🏆 Congrats! You completed <b>{sc}</b>.\nA new scenario will appear when available.",
            "task_invalid":     "❌ Invalid task ID.",
            "task_wrong_sc":    "❌ This task doesn't belong to the active scenario.",
            "task_already":     "ℹ️ You already submitted this task.",
            "limit_hit":        "🚫 You can complete at most {max} tasks in this event.\nYou've reached the limit ({done}/{max}).",
            "submit_ok":        "📤 <b>Submitted!</b>\n\n📌 Task: <b>{title}</b>\n💰 If approved: <b>+{sp} {bp}</b>\n\n⏳ Awaiting admin approval...",
            "submit_usage":     "📤 Usage: <code>/submit TASK_ID LINK</code>\nExample: <code>/submit {ex} https://drive.google.com/...</code>",
            "no_role_defined":  "ℹ️ No roles defined.",
            "role_invalid":     "❌ Invalid number. /role_list",
            "role_notfound":    "❌ Role not found.",
            "role_ok":          "✅ Role updated!\n\n{emoji} <b>{name}</b>{attrs}",
            "role_attrs":       "\n\n📊 Starting attributes:\n{a}",
            "role_list_header": "⚔️ <b>ROLE LIST</b>\n",
            "role_select_hint": "To select: <code>/role NUMBER</code>",
            "no_scores":        "ℹ️ No scores yet.",
            "scores_header":    "🏆 <b>LEADERBOARD</b>\n{event}\n",
            "my_rank":          "\n📍 Your team is <b>#{rank}</b>",
            "status_no_team":   "❌ You need to be in a team for this command.",
            "profile_notfound": "❌ Profile not found.",
            "limit_info":       "\n📊 Personal limit: <b>{done}/{max}</b> tasks",
            "unknown_cmd":      "❓ Unknown command.\nType /help to see all commands.",
        }
    }
    s = msgs.get(lang, msgs["tr"]).get(key, msgs["tr"].get(key, key))
    return s.format(**kw) if kw else s


async def send(token: str, chat_id: int, text: str, parse_mode: str = "HTML"):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text,
                      "parse_mode": parse_mode,
                      "disable_web_page_preview": True})
            resp = r.json()
            if not resp.get("ok"):
                log.warning(f"send HATA chat_id={chat_id}: {resp.get('description','?')}")
    except Exception as e:
        log.warning(f"send hatası: {e}")


async def handle_update(update: dict, token: str, event_id: int):
    import core.db as db
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    user = message.get("from", {})
    tg_id = user.get("id", 0)
    username = user.get("username", "")
    full_name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return
    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    event = await db.event_get(event_id)
    if not event or event["status"] not in ("active", "paused"):
        return
    lang = event.get("language", "tr") or "tr"
    team = await db.team_by_tg(tg_id, event_id)
    handlers = {
        "/start":     _cmd_start,
        "/join":      _cmd_join,      "/katil":      _cmd_join,
        "/scenarios": _cmd_scenarios, "/senaryolar": _cmd_scenarios,
        "/tasks":     _cmd_tasks,     "/gorevler":   _cmd_tasks,
        "/submit":    _cmd_submit,    "/gonder":     _cmd_submit,
        "/profile":   _cmd_profile,   "/profil":     _cmd_profile,
        "/status":    _cmd_status,    "/durum":      _cmd_status,
        "/scores":    _cmd_scores,    "/puan":       _cmd_scores,
        "/role_list": _cmd_role_list, "/rol_list":   _cmd_role_list,
        "/role":      _cmd_role,      "/rol":        _cmd_role,
        "/help":      _cmd_help,      "/yardim":     _cmd_help,
    }
    handler = handlers.get(command, _cmd_unknown)
    try:
        await handler(token=token, chat_id=chat_id, tg_id=tg_id,
                      username=username, full_name=full_name,
                      lang=lang, args=args, event=event, team=team)
    except Exception as e:
        log.error(f"Handler hatası ({command}): {e}", exc_info=True)


# ══════════════════════════════════════════
async def _cmd_start(token, chat_id, tg_id, username, full_name,
                     lang, args, event, team, **_):
    import core.db as db
    bp = bp_label(lang)
    tr = lang == "tr"
    if team:
        members = await db.member_list(team["id"])
        history = await db.completion_history(team["id"])
        done = len([h for h in history if h["status"] == "approved"])
        me = next((m for m in members if m.get("telegram_id") == tg_id), None)
        role_warn = t(lang, "role_warn") if (me and not me.get("role_id")) else ""
        if tr:
            msg = (f"🔥 <b>{team['name']}</b> — hoş geldin, {full_name}!\n\n"
                   f"⚡ {bp}: <b>{team['xp']:,}</b>\n"
                   f"✅ Tamamlanan görev: <b>{done}</b>\n"
                   f"👥 Üye sayısı: <b>{len(members)}</b>"
                   f"{role_warn}\n\n"
                   f"📋 /tasks — görevler\n"
                   f"🏆 /scores — sıralama\n"
                   f"❓ /help — tüm komutlar")
        else:
            msg = (f"🔥 <b>{team['name']}</b> — welcome back, {full_name}!\n\n"
                   f"⚡ {bp}: <b>{team['xp']:,}</b>\n"
                   f"✅ Completed tasks: <b>{done}</b>\n"
                   f"👥 Members: <b>{len(members)}</b>"
                   f"{role_warn}\n\n"
                   f"📋 /tasks — tasks\n"
                   f"🏆 /scores — leaderboard\n"
                   f"❓ /help — all commands")
    else:
        if tr:
            msg = (f"👋 Merhaba, <b>{full_name}</b>!\n\n"
                   f"🎯 <b>{event['name']}</b> etkinliğine hoş geldin.\n\n"
                   f"Katılmak için:\n<code>/join DAVET_KODU</code>\n\n"
                   f"❓ /help — tüm komutlar")
        else:
            msg = (f"👋 Hello, <b>{full_name}</b>!\n\n"
                   f"🎯 Welcome to <b>{event['name']}</b>.\n\n"
                   f"To join a team:\n<code>/join INVITE_CODE</code>\n\n"
                   f"❓ /help — all commands")
    await send(token, chat_id, msg)


# ══════════════════════════════════════════
async def _cmd_join(token, chat_id, tg_id, username, full_name,
                    lang, args, event, team, **_):
    import core.db as db
    if not args:
        await send(token, chat_id, t(lang, "join_usage"))
        return
    code = args.strip().upper()
    tm = await db.team_by_code(code)
    if not tm or tm["event_id"] != event["id"]:
        await send(token, chat_id, t(lang, "join_invalid"))
        return
    members = await db.member_list(tm["id"])
    if len(members) >= event.get("max_members_per_team", 6):
        await send(token, chat_id, t(lang, "join_full"))
        return
    if any(m["telegram_id"] == tg_id for m in members):
        await send(token, chat_id, t(lang, "join_already"))
        return
    await db.member_add(tm["id"], {
        "telegram_id": tg_id, "username": username, "display_name": full_name})
    await send(token, chat_id, t(lang, "join_ok", team=tm["name"]))


# ══════════════════════════════════════════
async def _cmd_scenarios(token, chat_id, tg_id, username, full_name,
                         lang, args, event, team, **_):
    import core.db as db
    bp = bp_label(lang)
    tr = lang == "tr"
    scenarios = await db.scenario_list(event["id"])
    active = [sc for sc in scenarios if sc["status"] == "active"]
    if not active:
        await send(token, chat_id, t(lang, "no_active_sc"))
        return
    header = (f"🗺 <b>{'SENARYOLAR' if tr else 'SCENARIOS'}</b> — {event['name']}\n")
    lines = [header]
    for sc in active:
        task_count = sc.get("task_count", 0)
        min_req = sc.get("min_tasks_required", 2)
        first_b = sc.get("first_bonus_sp", 200)
        other_b = sc.get("bonus_sp", 150)
        if tr:
            lines.append(
                f"🎯 <b>{sc['name']}</b>\n"
                f"   📌 {task_count} görev | En az {min_req} tamamlanmalı\n"
                f"   🏆 1. bonus: <b>+{first_b} {bp}</b>\n"
                f"   🎖 Diğer: <b>+{other_b} {bp}</b>")
        else:
            lines.append(
                f"🎯 <b>{sc['name']}</b>\n"
                f"   📌 {task_count} tasks | At least {min_req} required\n"
                f"   🏆 1st bonus: <b>+{first_b} {bp}</b>\n"
                f"   🎖 Others: <b>+{other_b} {bp}</b>")
        if sc.get("bonus_badge"):
            lines.append(f"   🏅 {'Rozet' if tr else 'Badge'}: {sc['bonus_badge']}")
        if sc.get("description"):
            lines.append(f"   ℹ️ {sc['description']}")
        lines.append("")
    if team:
        async with db.conn() as c:
            for sc in active:
                done = await c.fetchrow(
                    "SELECT rank FROM scenario_completions WHERE scenario_id=$1 AND team_id=$2",
                    sc["id"], team["id"])
                if done:
                    lines.append(
                        f"✅ <b>{sc['name']}</b> "
                        f"{'tamamlandı' if tr else 'completed'}! (#{done['rank']}. {'tamamlayan' if tr else 'to finish'})")
    await send(token, chat_id, "\n".join(lines))


# ══════════════════════════════════════════
async def _cmd_tasks(token, chat_id, tg_id, username, full_name,
                     lang, args, event, team, **_):
    import core.db as db
    bp = bp_label(lang)
    tr = lang == "tr"
    # Rol kontrolü
    if team:
        members_t = await db.member_list(team["id"])
        me_t = next((m for m in members_t if m.get("telegram_id") == tg_id), None)
        if me_t and not me_t.get("role_id"):
            await send(token, chat_id, t(lang, "role_warn_block"))
            return
    # Tamamlanan senaryo kontrolü
    if team:
        scenarios_t = await db.scenario_list(event["id"])
        active_sc_t = next((sc for sc in scenarios_t if sc["status"] == "active"), None)
        if active_sc_t:
            async with db.conn() as c:
                sc_done = await c.fetchrow(
                    "SELECT id FROM scenario_completions WHERE scenario_id=$1 AND team_id=$2",
                    active_sc_t["id"], team["id"])
            if sc_done:
                await send(token, chat_id, t(lang, "sc_done_all", sc=active_sc_t["name"]))
                return
    all_tasks = await db.task_list(event["id"], active_only=True)
    scenarios = await db.scenario_list(event["id"])
    active_sc_ids = {sc["id"] for sc in scenarios if sc["status"] == "active"}
    tasks = [tk for tk in all_tasks if tk.get("scenario_id") in active_sc_ids]
    if not tasks:
        await send(token, chat_id, t(lang, "no_tasks"))
        return
    completed_ids = set()
    pending_ids = set()
    if team:
        history = await db.completion_history(team["id"])
        completed_ids = {h["task_id"] for h in history if h["status"] == "approved"}
        pending_ids   = {h["task_id"] for h in history if h["status"] == "pending"}
    sc_map = {sc["id"]: sc["name"] for sc in scenarios}
    grouped: dict = {}
    for tk in tasks:
        grouped.setdefault(tk.get("scenario_id"), []).append(tk)
    header = f"📋 <b>{'GÖREVLER' if tr else 'TASKS'}</b> — {event['name']}\n"
    lines = [header]
    for sid, sc_tasks in grouped.items():
        lines.append(f"🗺 <b>{sc_map.get(sid,'?')}</b>")
        for tk in sc_tasks:
            title = tk["title_tr"] if tr else (tk.get("title_en") or tk["title_tr"])
            diff = DIFF_EMOJI.get(tk["difficulty"], "⚪")
            if tk["id"] in completed_ids:   st = "✅"
            elif tk["id"] in pending_ids:   st = "⏳"
            else:                           st = diff
            lines.append(f"  {st} <b>#{tk['id']}</b> {title}  <b>+{tk['sp_reward']} {bp}</b>")
        lines.append("")
    if tasks:
        if tr:
            lines.append(f"📤 <code>/submit GÖREV_ID LINK</code>")
            lines.append(f"Örnek: <code>/submit {tasks[0]['id']} https://...</code>")
        else:
            lines.append(f"📤 <code>/submit TASK_ID LINK</code>")
            lines.append(f"Example: <code>/submit {tasks[0]['id']} https://...</code>")
    max_limit = event.get("max_tasks_per_member") or 0
    if max_limit > 0 and team:
        async with db.conn() as c:
            done_cnt = await c.fetchval(
                "SELECT COUNT(*) FROM task_completions tc "
                "JOIN tasks tk ON tc.task_id=tk.id "
                "WHERE tc.submitted_by=$1 AND tc.status='approved' AND tk.event_id=$2",
                tg_id, event["id"])
        lines.append(t(lang, "limit_info", done=done_cnt or 0, max=max_limit))
    await send(token, chat_id, "\n".join(lines))


# ══════════════════════════════════════════
async def _cmd_submit(token, chat_id, tg_id, username, full_name,
                      lang, args, event, team, **_):
    import core.db as db
    tr = lang == "tr"
    bp = bp_label(lang)
    if not team:
        await send(token, chat_id, t(lang, "no_team"))
        return
    parts = args.split(maxsplit=1)
    task_id = None
    proof = ""
    if len(parts) >= 1 and parts[0].isdigit():
        task_id = int(parts[0])
        proof = parts[1].strip() if len(parts) > 1 else ""
    if not task_id or not proof:
        await send(token, chat_id, t(lang, "submit_usage", ex="3"))
        return
    task = await db.task_get(task_id)
    if not task or task["event_id"] != event["id"] or not task["active"]:
        await send(token, chat_id, t(lang, "task_invalid"))
        return
    scenarios = await db.scenario_list(event["id"])
    active_sc_ids = {sc["id"] for sc in scenarios if sc["status"] == "active"}
    if task.get("scenario_id") and task["scenario_id"] not in active_sc_ids:
        await send(token, chat_id, t(lang, "task_wrong_sc"))
        return
    history = await db.completion_history(team["id"])
    if any(h["task_id"] == task_id and h["status"] in ("pending", "approved")
           for h in history):
        await send(token, chat_id, t(lang, "task_already"))
        return
    async with db.conn() as _rc:
        _m = await _rc.fetchrow(
            "SELECT role_id FROM team_members WHERE telegram_id=$1 AND team_id=$2",
            tg_id, team["id"])
        if not _m or not _m["role_id"]:
            await send(token, chat_id, t(lang, "role_warn_block"))
            return
        max_limit = event.get("max_tasks_per_member") or 0
        if max_limit > 0:
            done = await _rc.fetchval(
                "SELECT COUNT(*) FROM task_completions tc "
                "JOIN tasks tk ON tc.task_id=tk.id "
                "WHERE tc.submitted_by=$1 AND tc.status='approved' AND tk.event_id=$2",
                tg_id, event["id"])
            if (done or 0) >= max_limit:
                await send(token, chat_id, t(lang, "limit_hit", done=done, max=max_limit))
                return
    result = await db.completion_submit(task_id, team["id"], tg_id, proof)
    if isinstance(result, dict) and result.get("error"):
        await send(token, chat_id, "⚠️ " + result.get("message", "Hata"))
        return
    try:
        from web.app import broadcast as _bc
        title = task["title_tr"] if tr else task.get("title_en", task["title_tr"])
        await _bc("admin", {"type": "new_completion", "event_id": event["id"],
                             "task_title": title, "team_id": team["id"],
                             "team_name": team["name"]})
    except Exception:
        pass
    title = task["title_tr"] if tr else task.get("title_en", task["title_tr"])
    await send(token, chat_id, t(lang, "submit_ok", title=title,
                                  sp=task["sp_reward"], bp=bp))


# ══════════════════════════════════════════
async def _cmd_status(token, chat_id, tg_id, username, full_name,
                      lang, args, event, team, **_):
    import core.db as db
    tr = lang == "tr"
    bp = bp_label(lang)
    if not team:
        await send(token, chat_id, t(lang, "status_no_team"))
        return
    members = await db.member_list(team["id"])
    history = await db.completion_history(team["id"])
    approved = [h for h in history if h["status"] == "approved"]
    attrs = team.get("attributes") or {}
    if tr:
        lines = [f"⚔️ <b>{team['name']}</b> — Takım Durumu\n",
                 f"⚡ Toplam {bp}: <b>{team['xp']:,}</b>",
                 f"✅ Tamamlanan görev: <b>{len(approved)}</b>"]
    else:
        lines = [f"⚔️ <b>{team['name']}</b> — Team Status\n",
                 f"⚡ Total {bp}: <b>{team['xp']:,}</b>",
                 f"✅ Completed tasks: <b>{len(approved)}</b>"]
    if team.get("badges"):
        lines.append(f"🏅 {'Rozetler' if tr else 'Badges'}: {' '.join(team['badges'])}")
    lines.append(f"\n👥 <b>{'Üyeler' if tr else 'Members'}:</b>")
    for m in members:
        role_str = ""
        if m.get("char_role_name"):
            role_str = f" {m.get('char_role_emoji','⚔️')} {m['char_role_name']}"
        m_bp = m.get("bp", 0) or 0
        lines.append(f"  • {m.get('display_name') or m.get('username','?')}"
                     f"{role_str} — <b>{m_bp} {bp}</b>")
    if attrs:
        lines.append(f"\n🎮 <b>{'Takım RPG Nitelikleri' if tr else 'Team RPG Attributes'}:</b>")
        for k, v in attrs.items():
            if v:
                lines.append(f"  {k}: <b>{v}</b>")
    await send(token, chat_id, "\n".join(lines))


# ══════════════════════════════════════════
async def _cmd_profile(token, chat_id, tg_id, username, full_name,
                       lang, args, event, team, **_):
    import core.db as db
    tr = lang == "tr"
    bp = bp_label(lang)
    if not team:
        await send(token, chat_id, t(lang, "status_no_team"))
        return
    members = await db.member_list(team["id"])
    me = next((m for m in members if m.get("telegram_id") == tg_id), None)
    if not me:
        await send(token, chat_id, t(lang, "profile_notfound"))
        return
    history = await db.completion_history(team["id"])
    my_done    = [h for h in history if h["status"] == "approved" and h.get("submitted_by") == tg_id]
    my_pending = [h for h in history if h["status"] == "pending"  and h.get("submitted_by") == tg_id]
    if me.get("char_role_name"):
        role_str = f"{me.get('char_role_emoji','⚔️')} <b>{me['char_role_name']}</b>"
    else:
        role_str = f"⚠️ {'Rol seçilmemiş — /role_list' if tr else 'No role selected — /role_list'}"
    m_bp = me.get("bp", 0) or 0
    max_limit = event.get("max_tasks_per_member") or 0
    limit_str = t(lang, "limit_info", done=len(my_done), max=max_limit) if max_limit else ""
    if tr:
        msg = (f"👤 <b>{full_name}</b>\n\n"
               f"🏷 Rol: {role_str}\n"
               f"⚡ Kişisel {bp}: <b>{m_bp:,}</b>\n"
               f"✅ Tamamladığım görevler: <b>{len(my_done)}</b>\n"
               f"⏳ Bekleyen: <b>{len(my_pending)}</b>"
               f"{limit_str}\n\n"
               f"🏠 Takım: <b>{team['name']}</b> — {team['xp']:,} {bp}")
    else:
        msg = (f"👤 <b>{full_name}</b>\n\n"
               f"🏷 Role: {role_str}\n"
               f"⚡ Personal {bp}: <b>{m_bp:,}</b>\n"
               f"✅ My completed tasks: <b>{len(my_done)}</b>\n"
               f"⏳ Pending: <b>{len(my_pending)}</b>"
               f"{limit_str}\n\n"
               f"🏠 Team: <b>{team['name']}</b> — {team['xp']:,} {bp}")
    await send(token, chat_id, msg)


# ══════════════════════════════════════════
async def _cmd_scores(token, chat_id, tg_id, username, full_name,
                      lang, args, event, team, **_):
    import core.db as db
    bp = bp_label(lang)
    tr = lang == "tr"
    lb = await db.leaderboard(event["id"])
    if not lb:
        await send(token, chat_id, t(lang, "no_scores"))
        return
    lines = [t(lang, "scores_header", event=event["name"])]
    for i, tm in enumerate(lb[:10]):
        medal = MEDAL[i] if i < len(MEDAL) else f"{i+1}."
        badge_str = " " + " ".join(tm["badges"]) if tm.get("badges") else ""
        role_emoji = tm.get("role_emoji", "") or ""
        lines.append(f"{medal} <b>{tm['name']}</b> {role_emoji}{badge_str}\n"
                     f"    ⚡ <b>{tm['xp']:,} {bp}</b>")
    if team:
        my_rank = next((i+1 for i, tm in enumerate(lb) if tm["id"] == team["id"]), None)
        if my_rank and my_rank > 10:
            lines.append(t(lang, "my_rank", rank=my_rank))
    await send(token, chat_id, "\n".join(lines))


# ══════════════════════════════════════════
async def _cmd_role_list(token, chat_id, tg_id, username, full_name,
                         lang, args, event, team, **_):
    import core.db as db
    tr = lang == "tr"
    roles = await db.role_list(event["id"])
    if not roles:
        await send(token, chat_id, t(lang, "no_role_defined"))
        return
    lines = [t(lang, "role_list_header")]
    for i, r in enumerate(roles, 1):
        name = r.get("name") or r.get("name_tr", "")
        emoji = r.get("emoji", "⚔️")
        ba = r.get("base_attributes") or {}
        attr_str = ""
        if ba:
            attr_str = "\n   📊 " + " | ".join(f"{k}: {v}" for k, v in ba.items() if v)
        lines.append(f"{i}. {emoji} <b>{name}</b>{attr_str}\n")
    lines.append(t(lang, "role_select_hint"))
    await send(token, chat_id, "\n".join(lines))


# ══════════════════════════════════════════
async def _cmd_role(token, chat_id, tg_id, username, full_name,
                    lang, args, event, team, **_):
    import core.db as db
    if not team:
        await send(token, chat_id, t(lang, "status_no_team"))
        return
    roles = await db.role_list(event["id"])
    if not roles:
        await send(token, chat_id, t(lang, "no_role_defined"))
        return
    if not args:
        await _cmd_role_list(token=token, chat_id=chat_id, tg_id=tg_id,
                             username=username, full_name=full_name,
                             lang=lang, args=args, event=event, team=team)
        return
    if args.isdigit():
        idx = int(args) - 1
        if idx < 0 or idx >= len(roles):
            await send(token, chat_id, t(lang, "role_invalid"))
            return
        chosen = roles[idx]
    else:
        chosen = next((r for r in roles
                       if args.lower() in (r.get("name","") or r.get("name_tr","")).lower()), None)
        if not chosen:
            await send(token, chat_id, t(lang, "role_notfound"))
            return
    async with db.conn() as _c:
        await _c.execute(
            "UPDATE team_members SET role_id=$1 WHERE telegram_id=$2 AND team_id=$3",
            chosen["id"], tg_id, team["id"])
    name = chosen.get("name") or chosen.get("name_tr", "")
    emoji = chosen.get("emoji", "⚔️")
    ba = chosen.get("base_attributes") or {}
    attrs_str = ""
    if ba:
        attrs_str = t(lang, "role_attrs",
                      a="\n".join(f"  {k}: {v}" for k, v in ba.items() if v))
    await send(token, chat_id, t(lang, "role_ok", emoji=emoji, name=name, attrs=attrs_str))


# ══════════════════════════════════════════
async def _cmd_help(token, chat_id, tg_id, username, full_name,
                    lang, args, event, team, **_):
    bp = bp_label(lang)
    tr = lang == "tr"
    if tr:
        await send(token, chat_id,
                   f"🤖 <b>ALEV Bot Komutları</b>\n\n"
                   f"👤 <b>Katılım</b>\n"
                   f"  /start — Hoş geldin & durum\n"
                   f"  /join KOD — Takıma katıl\n"
                   f"  /role_list — Rolleri listele\n"
                   f"  /role NUM — Rol seç\n\n"
                   f"📋 <b>Görevler</b>\n"
                   f"  /scenarios — Senaryo listesi\n"
                   f"  /tasks — Aktif görevler\n"
                   f"  /submit ID LINK — Görev gönder\n\n"
                   f"📊 <b>Durum</b>\n"
                   f"  /profile — Kişisel profilim\n"
                   f"  /status — Takım durumu\n"
                   f"  /scores — Liderlik tablosu\n\n"
                   f"💡 Puan birimi: <b>{bp}</b>")
    else:
        await send(token, chat_id,
                   f"🤖 <b>ALEV Bot Commands</b>\n\n"
                   f"👤 <b>Joining</b>\n"
                   f"  /start — Welcome & status\n"
                   f"  /join CODE — Join a team\n"
                   f"  /role_list — List roles\n"
                   f"  /role NUM — Select role\n\n"
                   f"📋 <b>Tasks</b>\n"
                   f"  /scenarios — Scenario list\n"
                   f"  /tasks — Active tasks\n"
                   f"  /submit ID LINK — Submit task\n\n"
                   f"📊 <b>Status</b>\n"
                   f"  /profile — My personal profile\n"
                   f"  /status — Team status\n"
                   f"  /scores — Leaderboard\n\n"
                   f"💡 Score unit: <b>{bp}</b>")


# ══════════════════════════════════════════
async def _cmd_unknown(token, chat_id, tg_id, username, full_name,
                       lang, args, event, team, **_):
    await send(token, chat_id, t(lang, "unknown_cmd"))


# ══════════════════════════════════════════
# Bildirim fonksiyonları (web/api/teams.py tarafından çağrılır)
# ══════════════════════════════════════════
async def notify_approval(token: str, chat_id: int, task_title: str,
                          total_sp: int, bonus_sp: int, team_xp: int,
                          lang: str = "tr"):
    bp = bp_label(lang)
    tr = lang == "tr"
    bonus_str = (f"\n🎯 {'Rol bonusu' if tr else 'Role bonus'}: <b>+{bonus_sp} {bp}</b>"
                 if bonus_sp > 0 else "")
    if tr:
        msg = (f"✅ <b>Görev Onaylandı!</b>\n\n"
               f"📌 <b>{task_title}</b>\n"
               f"⚡ Kazanılan: <b>+{total_sp} {bp}</b>{bonus_str}\n"
               f"🏠 Takım toplam: <b>{team_xp:,} {bp}</b>")
    else:
        msg = (f"✅ <b>Task Approved!</b>\n\n"
               f"📌 <b>{task_title}</b>\n"
               f"⚡ Earned: <b>+{total_sp} {bp}</b>{bonus_str}\n"
               f"🏠 Team total: <b>{team_xp:,} {bp}</b>")
    await send(token, chat_id, msg)


async def notify_rejection(token: str, chat_id: int, task_title: str,
                           note: str = "", lang: str = "tr"):
    tr = lang == "tr"
    note_str = f"\n💬 {'Neden' if tr else 'Reason'}: {note}" if note else ""
    if tr:
        msg = (f"❌ <b>Görev Reddedildi</b>\n\n"
               f"📌 <b>{task_title}</b>{note_str}\n\n"
               f"📋 Diğer görevleri dene: /tasks")
    else:
        msg = (f"❌ <b>Task Rejected</b>\n\n"
               f"📌 <b>{task_title}</b>{note_str}\n\n"
               f"📋 Try other tasks: /tasks")
    await send(token, chat_id, msg)


async def notify_scenario_complete(token: str, chat_id: int, scenario_name: str,
                                   rank: int, bonus_sp: int, badge: str = "",
                                   lang: str = "tr"):
    bp = bp_label(lang)
    tr = lang == "tr"
    medal = MEDAL[rank - 1] if rank <= len(MEDAL) else f"#{rank}."
    badge_str = (f"\n🏅 {'Rozet kazanıldı' if tr else 'Badge earned'}: <b>{badge}</b>"
                 if badge else "")
    if tr:
        msg = (f"🏆 <b>Senaryo Tamamlandı!</b>\n\n"
               f"🗺 <b>{scenario_name}</b>\n"
               f"{medal} {rank}. tamamlayan\n"
               f"⚡ Bonus: <b>+{bonus_sp} {bp}</b>{badge_str}")
    else:
        msg = (f"🏆 <b>Scenario Completed!</b>\n\n"
               f"🗺 <b>{scenario_name}</b>\n"
               f"{medal} #{rank} to finish\n"
               f"⚡ Bonus: <b>+{bonus_sp} {bp}</b>{badge_str}")
    await send(token, chat_id, msg)
