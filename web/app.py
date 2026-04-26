"""
web/app.py — ALEV v2.0 Ana Uygulama
Hiyerarşi: Etkinlik → Senaryo → Görev → Takım → Üye → RPG
"""
from __future__ import annotations
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

import core.db as db
from web.auth import create_token, get_admin
from web.i18n import available_langs, get_lang, get_t

log = logging.getLogger(__name__)
pwd_ctx = CryptContext(schemes=["bcrypt"])

# ── Brand config ────────────────────────────────────────────
def load_brand():
    cfg_dir = os.getenv("ALEV_CONFIG_DIR", "config")
    with open(f"{cfg_dir}/brand.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["brand"]

# ── WebSocket broadcast ──────────────────────────────────────
_ws_clients: dict[str, set] = {}

async def broadcast(channel: str, msg: dict):
    for ws in list(_ws_clients.get(channel, set())):
        try:
            await ws.send_json(msg)
        except Exception:
            _ws_clients[channel].discard(ws)

# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await db.init_schema()
    await db.init_lang_schema()
    log.info("ALEV v2 web hazır")
    yield
    await db.close_pool()

app = FastAPI(title="ALEV v2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")
templates.env.auto_reload = True

# ── Router'lar ───────────────────────────────────────────────
from web.auth import get_admin  # noqa
from web.api.events import router as events_router
from web.api.teams  import router as teams_router
from web.api.content import router as content_router
from web.api.bot    import router as bot_router
from web.api.jury   import router as jury_router

app.include_router(events_router,  prefix="/api/events")
app.include_router(teams_router,   prefix="/api/teams")
app.include_router(content_router, prefix="/api/content")
app.include_router(bot_router,     prefix="/api/bot")
app.include_router(jury_router,    prefix="/api/jury")

# ── Jinja2 context helper ────────────────────────────────────
def ctx(request: Request, **kw):
    brand = load_brand()
    lang  = get_lang(request)
    t     = get_t(request)
    return {
        "request": request, "brand": brand, "lang": lang,
        "langs": available_langs(), "t": t,
        **kw
    }

# ════════════════════════════════════════════
# ADMIN AUTH
# ════════════════════════════════════════════
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", ctx(request))

@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    uname = form.get("username","")
    pwd   = form.get("password","")
    admin_u = os.getenv("ADMIN_USERNAME","admin")
    admin_p = os.getenv("ADMIN_PASSWORD","alev2026")
    if uname == admin_u and pwd == admin_p:
        token = create_token({"sub": uname, "role": "admin"})
        resp  = RedirectResponse("/admin", status_code=302)
        resp.set_cookie("admin_token", token, httponly=True, max_age=3600*8)
        return resp
    return templates.TemplateResponse("admin/login.html",
        ctx(request, error="Kullanıcı adı veya şifre hatalı"), status_code=401)

@app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse("/admin/login", status_code=302)
    resp.delete_cookie("admin_token")
    return resp

# ════════════════════════════════════════════
# ADMIN SAYFALAR
# ════════════════════════════════════════════
@app.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request, _=Depends(get_admin)):
    events = await db.event_list()
    active = await db.event_active()
    return templates.TemplateResponse("admin/index.html",
        ctx(request, events=events, active_event=active))

@app.get("/admin/events/{event_id}", response_class=HTMLResponse)
async def admin_event(request: Request, event_id: int, _=Depends(get_admin)):
    event = await db.event_get(event_id)
    if not event:
        raise HTTPException(404)
    attrs    = await db.attr_list(event_id)
    roles    = await db.role_list(event_id)
    scenarios_raw = await db.scenario_list(event_id)
    # Her senaryo için aşamalarını ekle
    scenarios = []
    for sc in scenarios_raw:
        sc_dict = dict(sc)
        sc_dict['stages'] = await db.stage_list(sc['id'])
        scenarios.append(sc_dict)
    teams    = await db.team_list(event_id)
    tasks    = await db.task_list(event_id)
    pending  = await db.completion_pending(event_id)
    jury_c   = await db.jury_criteria_list(event_id)
    return templates.TemplateResponse("admin/event.html", ctx(
        request, event=event, attrs=attrs, roles=roles,
        scenarios=scenarios, teams=teams, tasks=tasks,
        pending=pending, jury_criteria=jury_c))

@app.get("/admin/events/{event_id}/teams", response_class=HTMLResponse)
async def admin_teams(request: Request, event_id: int, _=Depends(get_admin)):
    event = await db.event_get(event_id)
    teams = await db.team_list(event_id)
    roles = await db.role_list(event_id)
    return templates.TemplateResponse("admin/teams.html",
        ctx(request, event=event, teams=teams, roles=roles))

@app.get("/admin/events/{event_id}/scenario/{sid}", response_class=HTMLResponse)
async def admin_scenario(request: Request, event_id: int, sid: int, _=Depends(get_admin)):
    event    = await db.event_get(event_id)
    scenario = await db.scenario_get(sid)
    if not event or not scenario:
        raise HTTPException(404, "Etkinlik veya senaryo bulunamadi")
    stages   = await db.stage_list(sid)
    tasks    = await db.task_list(event_id)
    # Bonus alanlari yoksa varsayilan ekle
    if "min_tasks_required" not in scenario:
        scenario["min_tasks_required"] = 1
        scenario["bonus_sp"] = 500
        scenario["first_bonus_sp"] = 1000
        scenario["bonus_badge"] = ""
    return templates.TemplateResponse("admin/scenario.html",
        ctx(request, event=event, scenario=scenario, stages=stages, tasks=tasks))

@app.get("/admin/bots", response_class=HTMLResponse)
async def admin_bots(request: Request, _=Depends(get_admin)):
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/admin/bot_manager", status_code=302)

@app.get("/admin/bot_manager", response_class=HTMLResponse)
async def admin_bot_manager(request: Request, _=Depends(get_admin)):
    """Bot yönetim sayfası — token listesi + JS ile canlı durum sorgusu."""
    tokens = await db.bot_token_list()
    events = await db.event_list()
    # Bots: her token bir bot kartı
    bots = []
    for tok in tokens:
        gid = tok.get("group_id","")
        bots.append({
            "group_id":      gid,
            "group_name":    tok.get("bot_username") or f"Bot ({gid})",
            "has_token":     True,
            "bot_username":  tok.get("bot_username",""),
            "bot_id":        tok.get("bot_id"),
            "event_id":      tok.get("event_id"),
            "token_env_key": tok.get("token_env_key","ALEV_BOT_TOKEN"),
            "status":        "checking",
            "webhook_url":   "",
            "is_org":        False,
        })
    # Hiç token yoksa placeholder kart göster (kullanıcı ekleyebilsin)
    if not bots:
        bots.append({
            "group_id":      "new",
            "group_name":    "Bot #1",
            "has_token":     False,
            "bot_username":  "",
            "bot_id":        None,
            "event_id":      None,
            "token_env_key": "ALEV_BOT_TOKEN",
            "status":        "unconfigured",
            "webhook_url":   "",
            "is_org":        False,
        })
    return templates.TemplateResponse("admin/bot_manager.html",
        ctx(request, bots=bots, events=events))

# ════════════════════════════════════════════
# KULLANICI SAYFALAR
# ════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    active = await db.event_active()
    if not active:
        return templates.TemplateResponse("user/no_event.html", ctx(request))
    lb = await db.leaderboard(active["id"])
    for team in lb:
        team["members"] = await db.member_list(team["id"])
        attrs_raw = team.get("attributes") or {}
        if isinstance(attrs_raw, str):
            import json as _j
            try: attrs_raw = _j.loads(attrs_raw)
            except: attrs_raw = {}
        team["attributes"] = attrs_raw
    attrs = await db.attr_list(active["id"])
    rpg_rankings = {}
    for a in attrs:
        key = a.get("key","")
        rpg_rankings[key] = sorted(
            [(tm["name"], tm.get("attributes",{}).get(key,0) or 0, tm.get("role_emoji",""))
             for tm in lb],
            key=lambda x: x[1], reverse=True)
    return templates.TemplateResponse("user/leaderboard.html",
        ctx(request, event=active, teams=lb, attrs=attrs, rpg_rankings=rpg_rankings))

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request, event_id: int | None = None):
    if event_id:
        event = await db.event_get(event_id)
    else:
        event = await db.event_active()
    if not event:
        return templates.TemplateResponse("user/no_event.html", ctx(request))
    lb = await db.leaderboard(event["id"])
    # Her takım için üye SP listesini de ekle
    for team in lb:
        team["members"] = await db.member_list(team["id"])
        # attributes dict olarak parse et
        attrs_raw = team.get("attributes") or {}
        if isinstance(attrs_raw, str):
            import json as _j
            try: attrs_raw = _j.loads(attrs_raw)
            except: attrs_raw = {}
        team["attributes"] = attrs_raw
    attrs = await db.attr_list(event["id"])
    events = await db.event_list()
    # RPG sıralaması: her nitelik için takımları sırala
    rpg_rankings = {}
    for a in attrs:
        key = a.get("key","")
        sorted_by_attr = sorted(
            [(tm["name"], tm.get("attributes",{}).get(key,0) or 0, tm.get("role_emoji",""))
             for tm in lb],
            key=lambda x: x[1], reverse=True)
        rpg_rankings[key] = sorted_by_attr
    return templates.TemplateResponse("user/leaderboard.html",
        ctx(request, event=event, teams=lb, attrs=attrs,
            rpg_rankings=rpg_rankings, all_events=events))


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    active = await db.event_active()
    if not active:
        return templates.TemplateResponse("user/no_event.html", ctx(request))

    all_teams = await db.team_list(active["id"])

    # Cookie'den oturum bilgisi al
    tgid     = int(request.cookies.get("profile_tgid", "0") or 0)
    team_id  = int(request.cookies.get("profile_teamid", "0") or 0)

    if not tgid or not team_id:
        # Giriş yapılmamış — login ekranı göster
        return templates.TemplateResponse("user/profile.html", ctx(
            request, event=active, all_teams=all_teams,
            team=None, members=[], history=[], attrs=[], tasks=[],
            current_member=None, tg_id=0, logged_in=False))

    team = await db.team_get(team_id)
    if not team:
        return templates.TemplateResponse("user/profile.html", ctx(
            request, event=active, all_teams=all_teams,
            team=None, members=[], history=[], attrs=[], tasks=[],
            current_member=None, tg_id=0, logged_in=False))

    members = await db.member_list(team["id"])
    history = await db.completion_history(team["id"])
    attrs   = await db.attr_list(active["id"])
    tasks   = await db.task_list(active["id"], active_only=True)
    member  = next((m for m in members if m["telegram_id"]==tgid), None)

    return templates.TemplateResponse("user/profile.html", ctx(
        request, event=active, team=team, members=members,
        history=history, attrs=attrs, tasks=tasks, all_teams=all_teams,
        current_member=member, tg_id=tgid, logged_in=True))


@app.post("/profile/login")
async def profile_login(request: Request):
    d = await request.json()
    invite_code = (d.get("invite_code") or "").strip().upper()
    username    = (d.get("username") or "").strip().lower().replace("@","")
    lang        = request.cookies.get("lang","tr")

    if not invite_code or not username:
        return JSONResponse({"ok": False, "error": "Eksik bilgi" if lang=="tr" else "Missing fields"}, 400)

    active = await db.event_active()
    if not active:
        return JSONResponse({"ok": False, "error": "Aktif etkinlik yok" if lang=="tr" else "No active event"}, 404)

    teams = await db.team_list(active["id"])
    team  = next((t for t in teams if (t.get("invite_code") or "").upper() == invite_code), None)
    if not team:
        return JSONResponse({"ok": False, "error": "Davet kodu hatalı" if lang=="tr" else "Invalid invite code"}, 404)

    members = await db.member_list(team["id"])
    member  = next((m for m in members
                    if (m.get("username") or "").lower().replace("@","") == username
                    or (m.get("display_name") or "").lower() == username), None)
    if not member:
        return JSONResponse({"ok": False,
            "error": "Kullanıcı adı bu takımda bulunamadı" if lang=="tr" else "Username not found in this team"}, 404)

    resp = JSONResponse({"ok": True})
    resp.set_cookie("profile_tgid",   str(member["telegram_id"]), max_age=3600*8, httponly=True)
    resp.set_cookie("profile_teamid", str(team["id"]),            max_age=3600*8, httponly=True)
    return resp


@app.get("/profile/logout")
async def profile_logout():
    resp = RedirectResponse("/profile", status_code=302)
    resp.delete_cookie("profile_tgid")
    resp.delete_cookie("profile_teamid")
    return resp

@app.get("/jury", response_class=HTMLResponse)
async def jury_page(request: Request, event_id: int | None = None):
    if event_id:
        event = await db.event_get(event_id)
    else:
        event = await db.event_active()
    if not event:
        return templates.TemplateResponse("user/no_event.html", ctx(request))
    teams    = await db.team_list(event["id"])
    attrs    = await db.attr_list(event["id"])
    scores   = await db.jury_scores(event["id"])
    members  = await db.jury_member_list(event["id"])
    return templates.TemplateResponse("jury/panel.html", ctx(
        request, event=event, teams=teams, attrs=attrs,
        scores=scores, jury_members=members))

# ════════════════════════════════════════════
# DİL
# ════════════════════════════════════════════
@app.get("/set-lang")
async def set_lang(request: Request, lang: str = "tr"):
    referer = request.headers.get("referer", "/")
    resp = RedirectResponse(referer, status_code=302)
    resp.set_cookie("lang", lang, max_age=3600*24*365, httponly=False)
    return resp


# ════════════════════════════════════════════
# Telegram Webhook
# ════════════════════════════════════════════
@app.post("/webhook/{group_id}")
async def telegram_webhook(group_id: str, request: Request):
    """Telegram'dan gelen güncellemeleri işle."""
    try:
        update = await request.json()
    except Exception:
        return {"ok": False}
    
    token_row = await db.bot_token_get(group_id)
    if not token_row:
        return {"ok": False}
    
    from core.bot_registry import TokenCipher
    import os
    cipher = TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY", ""))
    token = cipher.decrypt(token_row["encrypted_token"])
    
    event_id = token_row.get("event_id")
    if not event_id:
        # Aktif etkinliği bul
        active = await db.event_active()
        if active:
            event_id = active["id"]
    
    if event_id:
        from core.bot_handler import handle_update
        import asyncio
        asyncio.create_task(handle_update(update, token, event_id))
        

    
    return {"ok": True}

# ════════════════════════════════════════════
# Bot — Duyuru gönder (iç API)
# ════════════════════════════════════════════
@app.post("/api/bot/broadcast")
async def bot_broadcast(request: Request, _=Depends(get_admin)):
    """Tüm takım gruplarına duyuru gönder."""
    d = await request.json()
    log.info(f"[BROADCAST] istek: {d}")
    event_id = d.get("event_id")
    message  = d.get("message", "").strip()
    ann_type = d.get("ann_type", "info")
    title    = d.get("title", "")
    if not message:
        return JSONResponse({"ok": False, "error": "message gerekli"}, 400)
    if not event_id:
        ev = await db.event_active()
        event_id = ev["id"] if ev else None
    if not event_id:
        return JSONResponse({"ok": False, "error": "Aktif etkinlik yok"}, 400)

    teams  = await db.team_list(int(event_id))
    tokens = await db.bot_token_list()

    from core.bot_handler import send
    from core.bot_registry import TokenCipher
    import os
    cipher = TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY", ""))

    # Ann type emoji
    ann_emoji = {"info":"ℹ️","success":"✅","warning":"⚠️","error":"❌"}.get(ann_type,"📢")
    full_msg = f"{ann_emoji}"
    if title: full_msg += f" <b>{title}</b>\n"
    full_msg += f"\n{message}"

    # Kullanılacak tokenları topla — event_id eşleşen + env token
    active_tokens = []
    for tok_row in tokens:
        tok_eid = tok_row.get("event_id")
        # event_id eşleşen ya da event_id boş olan tokenları kullan
        if tok_eid is None or str(tok_eid) == str(event_id):
            raw = cipher.decrypt(tok_row.get("encrypted_token",""))
            if raw and raw != "TOKEN_BURAYA":
                active_tokens.append(raw)
    # .env token da ekle (DB'de yoksa)
    env_tok = os.getenv("ALEV_BOT_TOKEN","")
    if env_tok and env_tok != "TOKEN_BURAYA" and env_tok not in active_tokens:
        active_tokens.append(env_tok)

    log.info(f"[BROADCAST] tokens DB'de: {len(tokens)}, active: {len(active_tokens)}, teams: {len(teams)}")
    for t in teams:
        log.info(f"[BROADCAST] takim={t['name']} tg_group_id={t.get('telegram_group_id')}")
    if not active_tokens:
        log.warning("[BROADCAST] Aktif token yok")
        return JSONResponse({"ok": False,
            "error": "Kayıtlı bot token yok. Bot yönetiminden token ekleyin."}, 400)

    results = []
    no_group = []
    for raw_tok in active_tokens:
        for team in teams:
            tg_gid = team.get("telegram_group_id")
            if not tg_gid:
                no_group.append(team["name"])
                continue
            try:
                if isinstance(tg_gid, str): tg_gid = int(tg_gid)
                await send(raw_tok, tg_gid, full_msg)
                results.append({"team": team["name"], "ok": True})
            except Exception as e:
                results.append({"team": team["name"], "ok": False, "error": str(e)})

    sent = sum(1 for r in results if r["ok"])
    msg_out = {"ok": True, "results": results, "sent": sent,
               "total_teams": len(teams), "tokens_used": len(active_tokens)}
    if no_group:
        msg_out["warning"] = f"Telegram grubu tanımlı olmayan takımlar atlandı: {', '.join(set(no_group))}"
    return msg_out

# ════════════════════════════════════════════
# WebSocket
# ════════════════════════════════════════════

@app.get("/onboard")
async def onboard_page(request: Request, code: str = ""):
    event = await db.event_active()
    return templates.TemplateResponse("user/onboard.html",
        ctx(request, event=event, invite_code=code.upper()))

@app.get("/api/teams/check-code/{code}")
async def check_invite_code(code: str):
    """Davet kodunu doğrula ve takım bilgisini döndür."""
    team = await db.team_by_code(code.upper())
    if not team:
        return JSONResponse({"ok": False, "error": "Geçersiz davet kodu"}, 400)
    event = await db.event_get(team["event_id"])
    if not event or event["status"] not in ("active", "paused"):
        return JSONResponse({"ok": False, "error": "Etkinlik aktif değil"}, 400)
    members = await db.member_list(team["id"])
    max_m = event.get("max_members_per_team", 6)
    if len(members) >= max_m:
        return JSONResponse({"ok": False, "error": "Takım dolu"}, 400)
    return {"ok": True, "team": {
        "id": team["id"], "name": team["name"],
        "event_id": team["event_id"],
        "role_emoji": team.get("role_emoji", "⚔"),
        "member_count": len(members),
        "max_members": max_m
    }}

@app.get("/api/events/{eid}/roles")
async def event_roles(eid: int):
    """Etkinliğin karakter listesini döndür."""
    roles = await db.role_list(eid)
    return roles


@app.post("/internal/new-completion")
async def internal_new_completion(request: Request):
    """Bot handler'dan gelen anlık completion bildirimi → WebSocket ile admin'e ilet."""
    # Sadece aynı host'tan (bot_handler) gelen isteklere izin ver
    client_host = request.client.host if request.client else ""
    allowed = {"127.0.0.1", "::1", "localhost"}
    # Docker ağında bot container IP'si 172.x.x.x olabilir, env'den de alınabilir
    internal_secret = os.getenv("INTERNAL_SECRET", "")
    req_secret = request.headers.get("X-Internal-Secret", "")
    if client_host not in allowed:
        if not internal_secret or req_secret != internal_secret:
            return JSONResponse({"ok": False}, 403)
    try:
        d = await request.json()
        await broadcast("admin", {
            "type": "new_completion",
            "event_id": d.get("event_id"),
            "task_title": d.get("task_title"),
            "team_id": d.get("team_id")
        })
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/bot/auto-setup")
async def bot_auto_setup(request: Request, _=Depends(get_admin)):
    """Token al, webhook'u otomatik kur, bot'u kaydet."""
    import httpx
    d = await request.json()
    token = d.get("token","").strip()
    group_id = d.get("group_id","main").strip()
    event_id = d.get("event_id")
    
    if not token:
        return JSONResponse({"ok":False,"error":"Token gerekli"},400)
    
    # 1. Token'ı doğrula - bot bilgisini al
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            info = r.json()
        if not info.get("ok"):
            return JSONResponse({"ok":False,"error":"Geçersiz token: "+info.get("description","")},400)
        bot_info = info["result"]
    except Exception as e:
        return JSONResponse({"ok":False,"error":"Telegram bağlantı hatası: "+str(e)},400)
    
    # 2. Ngrok URL'ini bul (çalışan ngrok varsa)
    webhook_url = ""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            ng = await client.get("http://localhost:4040/api/tunnels")
            tunnels = ng.json().get("tunnels",[])
            for t in tunnels:
                if t.get("proto") == "https":
                    webhook_url = t["public_url"] + f"/webhook/{group_id}"
                    break
    except Exception:
        pass
    
    # 3. Webhook kur (ngrok varsa)
    webhook_set = False
    if webhook_url:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                wr = await client.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
                webhook_set = wr.json().get("ok", False)
        except Exception:
            pass
    
    # 4. Token'ı kaydet
    from core.bot_registry import registry
    reg_info = await registry.register_bot(group_id, "ALEV_BOT_TOKEN", token)
    if reg_info.status == "error":
        return JSONResponse({"ok":False,"error":reg_info.error_msg},400)
    
    if event_id:
        async with db.conn() as c:
            await c.execute("UPDATE bot_tokens SET event_id=$1 WHERE group_id=$2",
                int(event_id), group_id)
    
    return {
        "ok": True,
        "bot_username": bot_info.get("username",""),
        "bot_name": bot_info.get("first_name",""),
        "webhook_url": webhook_url,
        "webhook_set": webhook_set,
        "group_id": group_id,
    }


@app.get("/api/teams/event/{eid}/pending-count")
async def pending_count(eid:int,_=Depends(get_admin)):
    pending=await db.completion_pending(eid)
    return {"count":len(pending)}

@app.post("/api/bot/{gid}/set-webhook")
async def bot_set_webhook(gid:str,request:Request,_=Depends(get_admin)):
    import httpx
    d=await request.json()
    webhook_url=d.get("webhook_url","")
    tok_row=await db.bot_token_get(gid)
    if not tok_row: return JSONResponse({"ok":False,"error":"Bot bulunamadi"},404)
    from core.bot_registry import TokenCipher
    import os
    cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
    tok=cipher.decrypt(tok_row["encrypted_token"])
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r=await client.get(f"https://api.telegram.org/bot{tok}/setWebhook?url={webhook_url}")
            data=r.json()
        if data.get("ok"): return {"ok":True,"webhook_url":webhook_url}
        return JSONResponse({"ok":False,"error":data.get("description","")},400)
    except Exception as e:
        return JSONResponse({"ok":False,"error":str(e)},500)

@app.get("/api/badges")
async def list_badges(_=Depends(get_admin)):
    import os
    badge_dir="web/static/badges"
    badges=[]
    if os.path.exists(badge_dir):
        for f in sorted(os.listdir(badge_dir)):
            if f.endswith(('.svg','.png','.jpg')):
                badges.append({"name":f.rsplit('.',1)[0],"url":f"/static/badges/{f}"})
    return badges


@app.websocket("/ws/{channel}")
async def websocket_endpoint(ws: WebSocket, channel: str):
    await ws.accept()
    _ws_clients.setdefault(channel, set()).add(ws)
    try:
        active = await db.event_active()
        if active:
            lb = await db.leaderboard(active["id"])
            await ws.send_json({
                "event": "init",
                "teams": [{"id":t["id"],"name":t["name"],"xp":t["xp"],
                           "level":t["level"],"role":t.get("role_name",""),
                           "role_emoji":t.get("role_emoji",""),
                           "member_count":t.get("member_count",0)} for t in lb]
            })
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.get(channel, set()).discard(ws)

# ════════════════════════════════════════════
# API — Leaderboard (public)
# ════════════════════════════════════════════
@app.get("/api/leaderboard")
async def api_leaderboard(event_id: int | None = None):
    if event_id:
        event = await db.event_get(event_id)
    else:
        event = await db.event_active()
    if not event:
        return []
    return await db.leaderboard(event["id"])
