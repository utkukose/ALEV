from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from web.auth import get_admin
from core.bot_registry import registry
import core.db as db

router = APIRouter(tags=["bot"])

@router.get("")
async def list_bots(_=Depends(get_admin)):
    tokens = await db.bot_token_list()
    result = []
    for t in tokens:
        result.append({
            "group_id":      t.get("group_id",""),
            "group_name":    t.get("bot_username") or t.get("group_id",""),
            "has_token":     True,
            "bot_username":  t.get("bot_username",""),
            "bot_id":        t.get("bot_id"),
            "event_id":      t.get("event_id"),
            "token_env_key": t.get("token_env_key","ALEV_BOT_TOKEN"),
            "webhook_url":   "",        # status endpoint'ten alınır
            "status":        "checking",
            "is_org":        False,
        })
    # Eğer hiç token yoksa bir placeholder göster
    if not result:
        result.append({
            "group_id":      "default",
            "group_name":    "Bot #1",
            "has_token":     False,
            "bot_username":  "",
            "bot_id":        None,
            "event_id":      None,
            "token_env_key": "ALEV_BOT_TOKEN",
            "webhook_url":   "",
            "status":        "unconfigured",
            "is_org":        False,
        })
    return result

@router.post("")
async def register_bot(request:Request,_=Depends(get_admin)):
    d=await request.json()
    gid=d.get("group_id","").strip()
    env=d.get("token_env_key","ALEV_BOT_TOKEN").strip()
    tok=d.get("raw_token","").strip()
    if not gid or not tok:
        return JSONResponse({"ok":False,"error":"group_id ve token gerekli"},400)
    info=await registry.register_bot(gid,env,tok)
    if info.status=="error":
        return JSONResponse({"ok":False,"error":info.error_msg},400)
    # event_id kaydet
    event_id=d.get("event_id")
    if event_id:
        async with db.conn() as c:
            await c.execute("UPDATE bot_tokens SET event_id=$1 WHERE group_id=$2",
                int(event_id),gid)
    # Not: Polling bot_runner.py servisi tarafından yönetilir.
    # Token DB'ye kaydedildi — bot servisi yeniden başladığında otomatik polling başlar.
    return {"ok":True,"bot_id":info.bot_id,"username":info.username,"first_name":info.first_name}

@router.get("/{gid}/status")
async def bot_status(gid:str,_=Depends(get_admin)):
    import dataclasses,httpx,os
    from core.bot_registry import TokenCipher
    info=await registry.check_status(gid)
    tok_row=await db.bot_token_get(gid)
    if not info and not tok_row:
        return {"status":"unconfigured","group_id":gid,"token_exists":False,"webhook_url":"","mode":"none"}
    result={}
    if info:
        result=dataclasses.asdict(info)
    result["token_exists"]=bool(tok_row)
    result["webhook_url"]=""
    result["webhook_pending"]=0
    result["mode"]="unknown"
    if tok_row:
        result["bot_id"]=tok_row.get("bot_id")
        result["bot_username"]=tok_row.get("bot_username","")
        result["event_id"]=tok_row.get("event_id")
        try:
            cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
            tok=cipher.decrypt(tok_row["encrypted_token"])
            async with httpx.AsyncClient(timeout=6) as client:
                wr=await client.get(f"https://api.telegram.org/bot{tok}/getWebhookInfo")
                winfo=wr.json().get("result",{})
                wh_url=winfo.get("url","")
                result["webhook_url"]=wh_url
                result["webhook_pending"]=winfo.get("pending_update_count",0)
                result["webhook_error"]=winfo.get("last_error_message","")
                if wh_url:
                    result["mode"]="webhook"
                    result["status"]="online"
                else:
                    result["mode"]="polling"
                    result["status"]="polling"
        except Exception as e:
            result["status"]="offline"
            result["mode"]="error"
            result["webhook_error"]=str(e)
    return result

@router.post("/{gid}/setup")
async def bot_setup(gid:str,request:Request,_=Depends(get_admin)):
    d=await request.json()
    results=await registry.setup_bot(
        gid,langs=["tr","en"],
        webhook_url=d.get("webhook_url",""),
        web_app_url=d.get("web_app_url",""),
        bot_description_tr=d.get("description_tr",""),
        bot_description_en=d.get("description_en",""))
    return {"ok":True,"results":results}

@router.delete("/{gid}")
async def delete_bot(gid:str,_=Depends(get_admin)):
    await db.bot_token_delete(gid)
    return {"ok":True}

@router.get("/{gid}/groups")
async def bot_groups(gid: str, _=Depends(get_admin)):
    """Bot'un üye olduğu Telegram gruplarını döndürür."""
    import os, httpx
    from core.bot_registry import TokenCipher
    tok_row = await db.bot_token_get(gid)
    if not tok_row:
        return []
    cipher = TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
    tok = cipher.decrypt(tok_row["encrypted_token"])
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            # getUpdates ile bot'un üye olduğu grupları bul
            r = await client.get(
                f"https://api.telegram.org/bot{tok}/getUpdates",
                params={"limit": 100, "timeout": 0}
            )
            updates = r.json().get("result", [])
            seen = {}
            for u in updates:
                chat = (u.get("message") or u.get("my_chat_member", {}) or {}).get("chat", {})
                if chat.get("type") in ("group", "supergroup"):
                    cid = chat["id"]
                    if cid not in seen:
                        # Bot admin mi kontrol et
                        try:
                            mem = await client.get(
                                f"https://api.telegram.org/bot{tok}/getChatMember",
                                params={"chat_id": cid, "user_id": tok_row.get("bot_id",0)}
                            )
                            is_admin = mem.json().get("result",{}).get("status") in ("administrator","creator")
                        except Exception:
                            is_admin = False
                        seen[cid] = {"chat_id": cid, "title": chat.get("title",""), "is_admin": is_admin}
            return list(seen.values())
    except Exception as e:
        return [{"error": str(e)}]
