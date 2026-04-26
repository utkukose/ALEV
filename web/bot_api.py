"""
web/bot_api.py — Bot Yönetim API'si

FastAPI router olarak web/app.py'ye eklenir:
    from web.bot_api import bot_router
    app.include_router(bot_router, prefix="/admin/bots")

Endpoint'ler:
  GET  /admin/bots              — Tüm botların listesi + durumu
  POST /admin/bots              — Yeni bot kayıt (token yapıştır)
  GET  /admin/bots/{group_id}   — Tek bot detayı
  POST /admin/bots/{group_id}/setup   — Otomatik kurulum
  GET  /admin/bots/{group_id}/groups  — Bot'un üye olduğu gruplar
  POST /admin/bots/{group_id}/verify  — Token doğrula
  DELETE /admin/bots/{group_id}       — Bot kaydını sil
"""
from __future__ import annotations
import dataclasses
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.bot_registry import registry, BotInfo
import core.db as db

bot_router = APIRouter(tags=["bot-management"])


from web.auth import get_admin

def _get_admin_dep():
    return get_admin


def _info_to_dict(info: BotInfo) -> dict:
    return dataclasses.asdict(info)


# ── Tüm botları listele ───────────────────
@bot_router.get("")
async def list_bots(request: Request, _=Depends(get_admin)):
    """
    Tüm kayıtlı botları + konfigürasyonsuz grupları listeler.
    Her bot için anlık durum kontrolü yapılır.
    """
    from core.config_loader import load_config
    cfg = load_config()
    groups = cfg.groups.active_groups()

    # DB'deki kayıtlı tokenlar
    db_tokens = {r["group_id"]: r for r in await db.bot_token_listesi()}

    result = []
    for g in groups:
        has_token = g.id in db_tokens or bool(g.bot_token)
        entry = {
            "group_id": g.id,
            "group_name": g.name,
            "token_env_key": g.bot_token_env,
            "chat_id": g.chat_id,
            "task_set": g.task_set,
            "has_token": has_token,
            "in_db": g.id in db_tokens,
            "status": "unconfigured",
            "bot_username": "",
            "bot_id": 0,
            "webhook_url": "",
        }
        if g.id in db_tokens:
            entry["bot_id"] = db_tokens[g.id].get("bot_id", 0)
        result.append(entry)

    # Org ve jüri grubu da göster
    result.append({
        "group_id": "__org__",
        "group_name": cfg.groups.org_name,
        "token_env_key": cfg.groups.org_bot_token_env,
        "chat_id": cfg.groups.org_chat_id,
        "task_set": "—",
        "has_token": bool(cfg.groups.org_bot_token),
        "in_db": "__org__" in db_tokens,
        "status": "unconfigured",
        "bot_username": "",
        "bot_id": 0,
        "webhook_url": "",
        "is_org": True,
    })

    return result


# ── Durum kontrolü ────────────────────────
@bot_router.get("/{group_id}/status")
async def bot_status(group_id: str, _=Depends(get_admin)):
    """Anlık durum kontrolü — getMe + getWebhookInfo."""
    info = await registry.check_status(group_id)
    if not info:
        return {"status": "unconfigured", "group_id": group_id}
    return _info_to_dict(info)


@bot_router.get("/status/all")
async def all_statuses(_=Depends(get_admin)):
    """Tüm grupların durumunu paralel kontrol eder."""
    from core.config_loader import load_config
    cfg = load_config()
    group_ids = [g.id for g in cfg.groups.active_groups()]
    group_ids.append("__org__")
    statuses = await registry.check_all_statuses(group_ids)
    return {gid: _info_to_dict(info) for gid, info in statuses.items()}


# ── Token kayıt ───────────────────────────
@bot_router.post("")
async def register_bot(request: Request, _=Depends(get_admin)):
    """
    Yeni bot kaydet.
    Body: {group_id, token_env_key, raw_token}
    """
    body = await request.json()
    group_id = body.get("group_id", "").strip()
    token_env_key = body.get("token_env_key", "ALEV_BOT_TOKEN").strip()
    raw_token = body.get("raw_token", "").strip()

    if not group_id or not raw_token:
        raise HTTPException(400, "group_id ve raw_token gerekli")

    # Token formatı kontrolü (basit)
    if ":" not in raw_token or len(raw_token) < 30:
        raise HTTPException(400, "Geçersiz token formatı — BotFather'dan aldığınız token'ı yapıştırın")

    info = await registry.register_bot(group_id, token_env_key, raw_token)

    if info.status == "error":
        return JSONResponse({"ok": False, "error": info.error_msg}, status_code=400)

    return JSONResponse({
        "ok": True,
        "bot_id": info.bot_id,
        "username": info.username,
        "first_name": info.first_name,
        "supports_inline": info.supports_inline_queries,
    })


# ── Token doğrula ─────────────────────────
@bot_router.post("/{group_id}/verify")
async def verify_token(group_id: str, request: Request, _=Depends(get_admin)):
    """Mevcut token'ın hâlâ geçerli olup olmadığını kontrol eder."""
    body = await request.json()
    raw_token = body.get("raw_token", "").strip()
    if raw_token:
        # Yeni token doğrulanıyor
        from core.bot_registry import TelegramClient
        client = TelegramClient(raw_token)
        me = await client.get_me()
        if me:
            return {"ok": True, "bot_id": me["id"],
                    "username": me.get("username", "")}
        return JSONResponse({"ok": False, "error": "Token geçersiz"}, status_code=400)
    # DB'deki token doğrulanıyor
    info = await registry.check_status(group_id)
    if info and info.status == "online":
        return {"ok": True, "username": info.username}
    return JSONResponse({"ok": False, "error": "Bot offline veya token hatalı"}, status_code=400)


# ── Otomatik kurulum ──────────────────────
@bot_router.post("/{group_id}/setup")
async def setup_bot(group_id: str, request: Request, _=Depends(get_admin)):
    """
    Tam otomatik kurulum:
    - Komut menüleri (TR + EN)
    - Bot açıklaması
    - Webhook (HTTPS varsa)
    - Mini App butonu
    """
    from core.config_loader import load_config
    cfg = load_config()
    body = await request.json()

    webhook_url  = body.get("webhook_url",  os.getenv("ALEV_WEB_APP_URL", ""))
    web_app_url  = body.get("web_app_url",  os.getenv("ALEV_WEB_APP_URL", ""))
    desc_tr = body.get("description_tr", cfg.brand.bot_description_tr or cfg.brand.tagline_tr)
    desc_en = body.get("description_en", cfg.brand.bot_description_en or cfg.brand.tagline_en)

    results = await registry.setup_bot(
        group_id=group_id,
        langs=["tr", "en"],
        webhook_url=webhook_url,
        web_app_url=web_app_url,
        bot_description_tr=desc_tr,
        bot_description_en=desc_en,
    )
    return JSONResponse({"ok": True, "results": results})


# ── Bot gruplarını listele ─────────────────
@bot_router.get("/{group_id}/groups")
async def bot_groups(group_id: str, request: Request, _=Depends(get_admin)):
    """Bot'un üye olduğu grupları Telegram API'den doğrulayarak listeler."""
    from core.config_loader import load_config
    cfg = load_config()
    # Config'deki bilinen chat_id'leri topla
    known_ids = [g.chat_id for g in cfg.groups.active_groups() if g.chat_id]
    if cfg.groups.org_chat_id:
        known_ids.append(cfg.groups.org_chat_id)
    groups = await registry.get_bot_groups(group_id, known_ids)
    return groups


# ── Bot kaydını sil ───────────────────────
@bot_router.delete("/{group_id}")
async def delete_bot(group_id: str, _=Depends(get_admin)):
    """DB'deki token kaydını siler (botu durdurmaz)."""
    await db.bot_token_sil(group_id)
    return JSONResponse({"ok": True})
