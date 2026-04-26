"""bot.py — ALEV v2 Telegram Botu (PostgreSQL + BP sistemi)"""
from __future__ import annotations
import asyncio, json, logging, os

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeChat,
)
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from core.config_loader import load_config
from core.game_engine import GameEngine
from core.bot_i18n import i18n
import core.db as db

logging.basicConfig(format="%(asctime)s — %(levelname)s — %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("ALEV_BOT_TOKEN", "TOKEN_BURAYA")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
GROUP_ID  = int(os.getenv("GROUP_CHAT_ID", "0"))

cfg    = load_config()
engine = GameEngine(cfg)


# ═══════════════════════════════════════════
# Yardımcılar
# ═══════════════════════════════════════════
async def _lang(user_id: int) -> str:
    try:
        return await db.kullanici_dil_getir(user_id)
    except Exception:
        return "tr"

def _t(lang: str):
    return i18n.t(lang)

def _stats(takim: dict) -> dict:
    s = takim.get("stats") or {}
    if isinstance(s, str):
        try: s = json.loads(s)
        except: s = {}
    return s

def _format_bp_bar(bp: int, width: int = 10) -> str:
    """Basit BP ilerleme çubuğu — 1000 BP = dolu bar."""
    pct = min(1.0, bp / max(1, ((bp // 1000) + 1) * 1000))
    f = int(pct * width)
    return "█" * f + "░" * (width - f)

def _rol_klavyesi_db(roles: list):
    """DB'den gelen roller listesinden inline klavye oluştur."""
    rows, row = [], []
    for r in roles:
        row.append(InlineKeyboardButton(
            f"{r.get('emoji','⚔️')} {r.get('name_tr', r.get('name','?'))}",
            callback_data=f"rol_{r['id']}"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    return InlineKeyboardMarkup(rows) if rows else None

def _onay_klavyesi(onay_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Onayla / Approve", callback_data=f"onayla_{onay_id}"),
        InlineKeyboardButton("❌ Reddet / Reject",  callback_data=f"reddet_{onay_id}"),
    ]])

def _diff_key(difficulty: str) -> str:
    return {"kolay":"easy","orta":"medium","zor":"hard","efsane":"legendary"}.get(difficulty, difficulty)

async def _set_commands_for_user(bot, user_id: int, lang: str):
    t = _t(lang); cmds = t.commands()
    commands = [
        BotCommand("start",      cmds.get("start","Start")),
        BotCommand("register",   cmds.get("register","Register")),
        BotCommand("tasks",      cmds.get("tasks","Tasks")),
        BotCommand("complete",   cmds.get("complete","Complete")),
        BotCommand("events",     cmds.get("events","Events")),
        BotCommand("score",      cmds.get("score","Score")),
        BotCommand("profile",    cmds.get("profile","Profile")),
        BotCommand("duel",       cmds.get("duel","Duel")),
        BotCommand("language",   cmds.get("language","Language")),
        BotCommand("help",       cmds.get("help","Help")),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        log.debug(f"Komut menüsü ayarlanamadı {user_id}: {e}")

async def _broadcast_all_groups(ctx, text: str):
    teams = await db.liderlik_tablosu(100)
    sent = set()
    for tm in teams:
        gid = tm.get("telegram_group_id")
        if gid and gid not in sent:
            try:
                await ctx.bot.send_message(gid, text, parse_mode=ParseMode.MARKDOWN)
                sent.add(gid)
            except Exception as e:
                log.warning(f"Grup {gid} duyuru hatası: {e}")


# ═══════════════════════════════════════════
# /start
# ═══════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t = _t(lang)
    takim = await db.takim_getir(user.id)
    if takim:
        bp = takim.get("xp", 0)
        bar = _format_bp_bar(bp)
        rol_str = f"{takim.get('rol_emoji','⚔️')} {takim.get('rol_adi') or takim.get('rol','?')}"
        msg = t("start.welcome_back",
                team_name=takim["ad"], role=rol_str, bar=bar, bp=f"{bp:,}")
    else:
        msg = t("start.welcome_new",
                brand_name=cfg.brand.name, brand_full=cfg.brand.full_name)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /register
# ═══════════════════════════════════════════
async def cmd_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t = _t(lang)
    if not ctx.args:
        await update.message.reply_text(t("register.usage"), parse_mode=ParseMode.MARKDOWN); return
    if await db.takim_getir(user.id):
        await update.message.reply_text(t("register.already_registered")); return
    ad = " ".join(ctx.args)[:40]
    await db.takim_olustur(user.id, user.username or str(user.id), ad, {})
    # Etkinliğin rollerini DB'den çek
    ev = await db.event_active()
    eid = ev["id"] if ev else None
    roles = await db.role_list(eid) if eid else []
    msg = t("register.success", team_name=ad) + "\n\n" + t("register.choose_role")
    klavye = _rol_klavyesi_db(roles) if roles else None
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=klavye)


# ═══════════════════════════════════════════
# Rol seçim callback (DB role id ile)
# ═══════════════════════════════════════════
async def cb_rol_sec(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = await _lang(query.from_user.id)
    t = _t(lang)
    data = query.data.replace("rol_", "")
    try:
        role_id = int(data)
    except ValueError:
        # Legacy YAML key desteği
        await query.edit_message_text(t("errors.generic")); return

    takim = await db.takim_getir(query.from_user.id)
    if not takim:
        await query.edit_message_text(t("errors.not_registered")); return

    # Rol bilgisini DB'den al
    async with db.conn() as c:
        role_row = await c.fetchrow(
            "SELECT * FROM event_roles WHERE id=$1", role_id)
        if not role_row:
            await query.edit_message_text(t("errors.generic")); return
        role = dict(role_row)
        base_attrs = dict(role.get("base_attributes") or {})

        # Üyenin role_id'sini güncelle
        await c.execute("""
            UPDATE team_members SET role_id=$1
            WHERE telegram_id=$2
        """, role_id, query.from_user.id)

        # Takımın başlangıç niteliklerini güncelle
        await c.execute("""
            UPDATE teams SET attributes=$1 WHERE id=$2
        """, json.dumps(base_attrs), takim["id"])

    rol_adi = role.get("name_tr") or role.get("name_en","?")
    emoji = role.get("emoji","⚔️")
    stats_str = engine.format_stats(base_attrs) if base_attrs else "—"
    await query.edit_message_text(
        t("role.selected", emoji=emoji, name=rol_adi, stats=stats_str),
        parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /tasks — Aktif senaryo + aktif görevler
# ═══════════════════════════════════════════
async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t = _t(lang)
    takim = await db.takim_getir(user.id)
    tamamlananlar = await db.tamamlanan_gorev_idleri(user.id) if takim else set()
    senaryo = await db.senaryo_durumu_getir()
    stage_mult = senaryo["xp_multiplier"] if senaryo else 1.0
    stage_info = ""
    if senaryo:
        sn = senaryo.get("stage_name") or senaryo.get("name","?")
        stage_info = t("tasks.stage_active", stage_name=sn, mult=stage_mult)

    gorevler = await db.aktif_gorev_listesi()
    if not gorevler:
        await update.message.reply_text(
            t("tasks.header") + "\n\n" +
            ("Aktif senaryo veya görevi olmayan etkinlik." if lang=="tr"
             else "No active scenario or tasks."))
        return

    z = {"kolay":"🟢","orta":"🟡","zor":"🔴","efsane":"⭐"}
    lines = [t("tasks.header") + stage_info + "\n"]
    for task in gorevler:
        tid = str(task["id"])
        done = tid in tamamlananlar
        xp = int((task.get("sp_reward") or 300) * stage_mult)
        diff = task.get("difficulty","orta")
        diff_label = t(f"difficulty.{_diff_key(diff)}")
        desc = (task.get("description") or task.get("description_tr") or "")[:80]
        lines.append(t("tasks.item",
            id=task["id"],
            status="✅" if done else z.get(diff,"🔷"),
            title=task.get("title") or task.get("title_tr","?"),
            xp=xp, bonus="",
            difficulty=diff_label, description=desc.strip()))

    lines.append(t("tasks.footer"))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /complete
# ═══════════════════════════════════════════
async def cmd_complete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t = _t(lang)
    takim = await db.takim_getir(user.id)
    if not takim:
        await update.message.reply_text(t("errors.not_registered")); return
    if len(ctx.args) < 2:
        await update.message.reply_text(t("complete.usage"), parse_mode=ParseMode.MARKDOWN); return
    gorev_id, kanit = ctx.args[0], ctx.args[1]

    # Görevi DB'den doğrula — aktif senaryo kontrolü
    senaryo = await db.senaryo_durumu_getir()
    gorevler = await db.aktif_gorev_listesi()
    task = next((g for g in gorevler if str(g["id"]) == gorev_id), None)
    if not task:
        await update.message.reply_text(
            t("complete.invalid_task", id=gorev_id), parse_mode=ParseMode.MARKDOWN); return

    # Daha önce tamamlamış mı?
    tamamlananlar = await db.tamamlanan_gorev_idleri(user.id)
    if gorev_id in tamamlananlar:
        await update.message.reply_text(t("complete.already_done")); return

    onay_id = await db.onay_istegi_olustur(user.id, user.id, gorev_id, kanit)
    if not onay_id:
        await update.message.reply_text(t("errors.generic")); return

    title = task.get("title") or task.get("title_tr","?")
    # Admin bildirimi
    admin_msg = (
        f"📬 *Görev Onay İsteği #{onay_id}*\n\n"
        f"Takım: *{takim['ad']}*\nGörev: *{title}*\n"
        f"Tür: `{task.get('task_type','genel')}` · {task.get('difficulty','orta')}\n"
        f"Kanıt: {kanit}"
    )
    for aid in ADMIN_IDS:
        if aid == 0: continue
        try:
            await ctx.bot.send_message(aid, admin_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_onay_klavyesi(onay_id))
        except Exception as e:
            log.warning(f"Admin bildirim hatası: {e}")
    await update.message.reply_text(
        t("complete.submitted", title=title), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# Onay/Red callback
# ═══════════════════════════════════════════
async def cb_onay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS and ADMIN_IDS != [0]:
        await query.answer("Unauthorized.", show_alert=True); return

    action, oid = query.data.split("_", 1)
    onay_id = int(oid)
    istek = await db.onay_istegi_getir(onay_id)
    if not istek:
        await query.edit_message_text("İstek bulunamadı."); return

    takim_id = istek["takim_id"]
    takim = await db.takim_getir(istek.get("submitted_by") or takim_id)
    # Takımı takim_id ile de dene
    if not takim:
        async with db.conn() as c:
            r = await c.fetchrow("SELECT * FROM teams WHERE id=$1", takim_id)
            if r: takim = {"ad": r["name"], "id": r["id"], "xp": r["xp"]}
    if not takim:
        await query.edit_message_text("Takım bulunamadı."); return

    team_lang = await _lang(istek.get("submitted_by") or 0)
    t = _t(team_lang)
    title = istek.get("gorev_baslik") or istek.get("title_tr","?")

    if action == "onayla":
        senaryo = await db.senaryo_durumu_getir()
        sm = senaryo["xp_multiplier"] if senaryo else 1.0
        sp_reward = int((istek.get("sp_reward") or 300) * sm)

        await db.gorev_onayla(
            onay_id, takim_id,
            istek.get("submitted_by") or 0,
            str(istek.get("task_id","")),
            sp_reward)

        # Güncel takım BP
        async with db.conn() as c:
            team_row = await c.fetchrow("SELECT xp FROM teams WHERE id=$1", takim_id)
            team_bp = team_row["xp"] if team_row else sp_reward

        msg = t("approval.approved",
                title=title, xp=sp_reward, bonus="", team_bp=f"{team_bp:,}")

        # RPG nitelik değişimleri varsa göster
        attr_rewards = istek.get("attribute_rewards") or {}
        if isinstance(attr_rewards, str):
            try: attr_rewards = json.loads(attr_rewards)
            except: attr_rewards = {}
        if attr_rewards:
            changes_str = engine.format_attr_changes(attr_rewards)
            if changes_str:
                msg += t("approval.attr_changes", changes=changes_str)

        # Takıma bildirim
        tg_gid = takim.get("telegram_group_id")
        if istek.get("submitted_by"):
            try:
                await ctx.bot.send_message(
                    istek["submitted_by"], msg, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                log.warning(f"Üye bildirim: {e}")
        if tg_gid:
            try:
                await ctx.bot.send_message(tg_gid,
                    t("approval.group_announce",
                      team=takim["ad"], title=title, xp=sp_reward),
                    parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                log.warning(f"Grup bildirim: {e}")

        await query.edit_message_text(
            f"✅ *{takim['ad']}* → +{sp_reward} BP onaylandı",
            parse_mode=ParseMode.MARKDOWN)

        # Senaryo tamamlama kontrolü
        try:
            ev = await db.event_active()
            eid = ev["id"] if ev else None
            if eid:
                sc_res = await db.check_scenario_completion(
                    istek.get("task_id"), takim_id, eid)
                if sc_res and sc_res.get("triggered"):
                    await _broadcast_all_groups(ctx,
                        f"🏁 *{sc_res['team_name']}* — *{sc_res['scenario_name']}* "
                        f"tamamladı! #{sc_res['rank']} +{sc_res['bonus_sp']} BP")
        except Exception as e:
            log.warning(f"Senaryo tamamlama kontrol: {e}")

    else:
        await db.gorev_reddet(onay_id)
        if istek.get("submitted_by"):
            try:
                await ctx.bot.send_message(
                    istek["submitted_by"],
                    t("approval.rejected", title=title),
                    parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                log.warning(f"Red bildirimi: {e}")
        await query.edit_message_text(
            f"❌ Reddedildi — *{takim['ad']}*", parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /score — BP tablosu, seviye yok, üye BP'leri
# ═══════════════════════════════════════════
async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    lang  = await _lang(user.id)
    t     = _t(lang)
    takimlar = await db.liderlik_tablosu(10)
    if not takimlar:
        await update.message.reply_text(t("score.empty")); return
    madalya = ["🥇","🥈","🥉"] + ["🔷"]*7
    lines = [t("score.header_global", brand=cfg.brand.name)]
    for i, tm in enumerate(takimlar):
        bp = tm.get("bp") or tm.get("xp") or 0
        rol_adi = tm.get("rol_adi") or tm.get("rol") or "?"
        rol_emoji = tm.get("rol_emoji") or "⚔️"
        bar = _format_bp_bar(bp)
        lines.append(t("score.row",
            medal=madalya[i], team=tm["ad"],
            role=f"{rol_emoji} {rol_adi}",
            bar=bar, bp=f"{bp:,}"))

        # Üye BP'lerini al
        uyeler = await db.uye_bp_listesi(tm["id"])
        for uye in uyeler:
            uye_bp = uye.get("bp") or 0
            if uye_bp > 0:
                uye_adi = uye.get("display_name") or uye.get("username") or "?"
                uye_rol = f"{uye.get('rol_emoji','') or ''} {uye.get('rol_adi','?')}".strip()
                lines.append(f"   └ `{uye_adi}` · {uye_rol} · *{uye_bp} BP*")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /profile
# ═══════════════════════════════════════════
async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    lang  = await _lang(user.id)
    t     = _t(lang)
    takim = await db.takim_getir(user.id)
    if not takim:
        await update.message.reply_text(t("profile.not_registered")); return

    bp = takim.get("xp", 0)
    bar = _format_bp_bar(bp)
    stats = _stats(takim)
    tamamlananlar = await db.tamamlanan_gorev_idleri(user.id)
    rozetler = await db.takim_rozetleri(user.id)
    gorevler = await db.aktif_gorev_listesi()
    rol_adi = takim.get("rol_adi") or takim.get("rol","?")
    rol_emoji = takim.get("rol_emoji","⚔️")

    msg = t("profile.header",
            team=takim["ad"],
            role=f"{rol_emoji} {rol_adi}",
            bar=bar, bp=f"{bp:,}",
            done=len(tamamlananlar),
            total=len(gorevler),
            stats=engine.format_stats(stats) if stats else "—")

    # Takım üye BP listesi
    uyeler = await db.uye_bp_listesi(takim["id"])
    if uyeler:
        uye_lines = ["\n\n👥 *Üye BP Dağılımı:*"]
        for uye in uyeler:
            uye_bp = uye.get("bp") or 0
            uye_adi = uye.get("display_name") or uye.get("username") or "?"
            uye_rol = f"{uye.get('rol_emoji','') or ''} {uye.get('rol_adi','?')}".strip()
            uye_lines.append(f"  {uye_adi} · {uye_rol} · *{uye_bp} BP*")
        msg += "\n".join(uye_lines)

    if rozetler:
        msg += f"\n\n🏅 *Rozetler:* {' '.join(rozetler)}"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /duel
# ═══════════════════════════════════════════
async def cmd_duel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    lang  = await _lang(user.id)
    t     = _t(lang)
    takim = await db.takim_getir(user.id)
    if not takim:
        await update.message.reply_text(t("errors.not_registered")); return
    if not ctx.args:
        await update.message.reply_text(t("duel.usage"), parse_mode=ParseMode.MARKDOWN); return
    rakip = await db.takim_ada_gore(" ".join(ctx.args))
    if not rakip:
        await update.message.reply_text(
            t("duel.not_found", name=" ".join(ctx.args)), parse_mode=ParseMode.MARKDOWN); return
    if rakip["id"] == takim["id"]:
        await update.message.reply_text(t("duel.self")); return
    cs = _stats(takim); ds = _stats(rakip)
    result = engine.resolve_duel(takim["id"], takim.get("xp",0), cs,
                                  rakip["id"], rakip.get("xp",0), ds)
    await db.xp_ekle(result.winner_id, result.sp_reward, "Duel victory")
    winner_name = takim["ad"] if result.winner_id == takim["id"] else rakip["ad"]
    attr_str = engine.format_attr_changes(result.winner_attr_changes)
    await update.message.reply_text(
        t("duel.result",
          challenger=takim["ad"], defender=rakip["ad"],
          c_score=result.challenger_score, d_score=result.defender_score,
          winner=winner_name, xp=result.sp_reward, attr=attr_str),
        parse_mode=ParseMode.MARKDOWN)
    if GROUP_ID:
        try:
            await ctx.bot.send_message(GROUP_ID,
                t("duel.group_announce",
                  challenger=takim["ad"], defender=rakip["ad"], winner=winner_name),
                parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            log.warning(f"Grup düello: {e}")


# ═══════════════════════════════════════════
# /events — Aktif senaryo + görev özeti
# ═══════════════════════════════════════════
async def cmd_events(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    sd   = await db.senaryo_durumu_getir()
    lines = [t("events.header")]
    if sd:
        gorevler = await db.aktif_gorev_listesi()
        done_count = 0
        takim = await db.takim_getir(user.id)
        if takim:
            tamamlananlar = await db.tamamlanan_gorev_idleri(user.id)
            done_count = sum(1 for g in gorevler if str(g["id"]) in tamamlananlar)
        lines.append(t("events.scenario_active",
            name=sd["name"],
            stage=sd.get("stage_name") or ("—"),
            mult=sd.get("xp_multiplier",1.0)))
        lines.append(t("events.task_count",
            done=done_count))
    else:
        lines.append(t("events.no_scenario"))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /language
# ═══════════════════════════════════════════
async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cur_lang = await _lang(user.id)
    if not ctx.args or not i18n.is_supported(ctx.args[0]):
        t = _t(cur_lang)
        await update.message.reply_text(t("language.usage"), parse_mode=ParseMode.MARKDOWN)
        return
    new_lang = ctx.args[0]
    await db.kullanici_dil_ayarla(user.id, new_lang)
    t = _t(new_lang)
    await update.message.reply_text(t("language.changed"), parse_mode=ParseMode.MARKDOWN)
    await _set_commands_for_user(ctx.bot, user.id, new_lang)


# ═══════════════════════════════════════════
# /score_jury
# ═══════════════════════════════════════════
async def cmd_score_jury(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    if len(ctx.args) < 3:
        await update.message.reply_text(t("jury.usage", criteria="—"),
                                         parse_mode=ParseMode.MARKDOWN); return
    takim_adi = " ".join(ctx.args[:-2]); crit_id = ctx.args[-2]; score_str = ctx.args[-1]
    try: score = float(score_str)
    except ValueError:
        await update.message.reply_text(t("errors.generic")); return
    takim = await db.takim_ada_gore(takim_adi)
    if not takim:
        await update.message.reply_text(t("jury.team_not_found", name=takim_adi),
                                         parse_mode=ParseMode.MARKDOWN); return
    await db.jury_puan_kaydet(takim["id"], user.id, crit_id, score)
    await update.message.reply_text(
        t("jury.saved", team=takim["ad"], emoji="⭐", criterion=crit_id, score=score),
        parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /jury_result
# ═══════════════════════════════════════════
async def cmd_jury_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(t("admin.unauthorized")); return
    takimlar = await db.liderlik_tablosu(20)
    lines = [t("jury.results_header")]
    has_any = False
    for tm in takimlar:
        avg = await db.jury_ortalama_puan(tm["id"])
        if not avg: continue
        scores_str = "\n".join(f"  ⭐ {k}: *{v}*" for k,v in avg.items())
        total = round(sum(avg.values())/max(1,len(avg)),1)
        lines.append(t("jury.results_row",
                       team=tm["ad"], total=total, scores=scores_str))
        has_any = True
    if not has_any:
        lines.append(t("jury.results_empty"))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# Admin komutları
# ═══════════════════════════════════════════
async def cmd_xp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(t("admin.unauthorized")); return
    if len(ctx.args) < 2:
        await update.message.reply_text(t("admin.xp_usage"), parse_mode=ParseMode.MARKDOWN); return
    try:
        m = int(ctx.args[-1]); ad = " ".join(ctx.args[:-1])
    except ValueError:
        await update.message.reply_text(t("errors.generic")); return
    takim = await db.takim_ada_gore(ad)
    if not takim:
        await update.message.reply_text(t("admin.xp_not_found")); return
    await db.xp_ekle(takim["id"], m, "Admin bonus")
    await update.message.reply_text(
        t("admin.xp_success",
          team=takim["ad"], sign="+" if m >= 0 else "", amount=abs(m)),
        parse_mode=ParseMode.MARKDOWN)

async def cmd_announce(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(t("admin.unauthorized")); return
    if not ctx.args:
        await update.message.reply_text(t("admin.announce_usage"), parse_mode=ParseMode.MARKDOWN); return
    text = f"📢 *{cfg.brand.name}*\n\n" + " ".join(ctx.args)
    await _broadcast_all_groups(ctx, text)
    await update.message.reply_text(t("admin.announce_sent"))

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = await _lang(user.id)
    t    = _t(lang)
    await update.message.reply_text(
        t("help.text", brand=cfg.brand.name), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# Ana çalıştırıcı
# ═══════════════════════════════════════════
async def main():
    await db.init_pool()
    await db.init_schema()
    await db.init_lang_schema()

    app = Application.builder().token(BOT_TOKEN).build()

    handlers = [
        ("start",      cmd_start),
        ("register",   cmd_register),
        ("tasks",      cmd_tasks),
        ("complete",   cmd_complete),
        ("events",     cmd_events),
        ("score",      cmd_score),
        ("profile",    cmd_profile),
        ("duel",       cmd_duel),
        ("score_jury", cmd_score_jury),
        ("jury_result",cmd_jury_result),
        ("xp",         cmd_xp),
        ("announce",   cmd_announce),
        ("language",   cmd_language),
        ("help",       cmd_help),
    ]
    for name, handler in handlers:
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(CallbackQueryHandler(cb_rol_sec, pattern=r"^rol_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_onay, pattern=r"^(onayla|reddet)_"))

    for lang in ["tr","en"]:
        t = i18n.t(lang); cmds_dict = t.commands()
        await app.bot.set_my_commands([
            BotCommand("start",      cmds_dict.get("start","Start")),
            BotCommand("register",   cmds_dict.get("register","Register")),
            BotCommand("tasks",      cmds_dict.get("tasks","Tasks")),
            BotCommand("complete",   cmds_dict.get("complete","Complete")),
            BotCommand("events",     cmds_dict.get("events","Events")),
            BotCommand("score",      cmds_dict.get("score","Score")),
            BotCommand("profile",    cmds_dict.get("profile","Profile")),
            BotCommand("duel",       cmds_dict.get("duel","Duel")),
            BotCommand("language",   cmds_dict.get("language","Language")),
            BotCommand("help",       cmds_dict.get("help","Help")),
        ], language_code=lang)

    log.info(f"{cfg.brand.name} başlatılıyor — PostgreSQL tabanlı bot")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    asyncio.run(main())
