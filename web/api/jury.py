from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
import core.db as db

router = APIRouter(tags=["jury"])

@router.post("/score")
async def save_score(request: Request):
    d = await request.json()
    jury_user = int(d.get("jury_user") or 0)
    if not jury_user:
        return JSONResponse({"ok": False, "error": "jury_user gerekli"}, 400)
    
    criterion = d.get("criterion","")
    if not criterion:
        return JSONResponse({"ok": False, "error": "criterion gerekli"}, 400)

    r = await db.jury_score_save(
        int(d["event_id"]), int(d["team_id"]), criterion,
        float(d["score"]), jury_user, d.get("note", ""))
    
    # Tüm nitelikler puanlanınca Telegram bildirimi
    try:
        attrs = await db.attr_list(int(d["event_id"]))
        all_scores = await db.jury_scores(int(d["event_id"]))
        team_scores = {
            s["criterion"]: s["score"]
            for s in all_scores
            if s["team_id"] == int(d["team_id"]) and s["jury_user"] == jury_user
        }
        if attrs and len(team_scores) >= len(attrs):
            total = round(sum(team_scores.values()) / max(len(team_scores), 1), 1)
            team = await db.team_get(int(d["team_id"]))
            if team:
                await db.jury_notify_telegram(
                    int(d["event_id"]), team["name"], team_scores, total)
    except Exception:
        pass
    
    return {"ok": True, "score": r}

@router.get("/event/{eid}")
async def get_scores(eid: int):
    return await db.jury_scores(eid)

@router.post("/session/login")
async def jury_login(request: Request):
    """Jüri üyesi Telegram ID ile giriş yapar, session token alır."""
    d = await request.json()
    eid = d.get("event_id")
    tgid = int(d.get("telegram_id", 0))
    name = d.get("name", "")
    if not eid or not tgid:
        return JSONResponse({"ok": False, "error": "event_id ve telegram_id gerekli"}, 400)
    
    # Jüri üyesi mi kontrol et
    members = await db.jury_member_list(eid)
    is_member = any(m["telegram_id"] == tgid for m in members)
    if not is_member and members:  # Üye listesi boşsa herkese izin ver
        return JSONResponse({"ok": False, "error": "Jüri üyesi değilsiniz"}, 403)
    
    # Üye yoksa ekle
    if not is_member:
        await db.jury_member_save(eid, tgid, name)
    
    token = await db.jury_session_create(eid, tgid, name or f"Jüri {tgid}")
    return {"ok": True, "token": token, "name": name}

@router.get("/session/verify")
async def verify_session(request: Request):
    token = request.cookies.get("jury_token") or request.query_params.get("token")
    if not token:
        return {"ok": False}
    session = await db.jury_session_verify(token)
    return {"ok": bool(session), "session": session}

@router.post("/members")
async def add_jury_member(request: Request):
    d = await request.json()
    r = await db.jury_member_save(d["event_id"], int(d["telegram_id"]), d.get("name", ""))
    return {"ok": True, "member": r}

@router.delete("/members/{jid}")
async def del_jury_member(jid: int):
    await db.jury_member_delete(jid)
    return {"ok": True}
