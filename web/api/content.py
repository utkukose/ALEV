from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from web.auth import get_admin
import core.db as db

router = APIRouter(tags=["content"])

# ─── Senaryolar ──────────────────────────────
@router.get("/events/{eid}/scenarios")
async def list_scenarios(eid:int,_=Depends(get_admin)):
    return await db.scenario_list(eid)

@router.post("/events/{eid}/scenarios")
async def create_scenario(eid:int,request:Request,_=Depends(get_admin)):
    try:
        d=await request.json()
        r=await db.scenario_create(eid,d)
        return {"ok":True,"scenario":r}
    except Exception as e:
        return JSONResponse({"ok":False,"error":str(e)},500)

@router.put("/scenarios/{sid}")
async def update_scenario(sid:int,request:Request,_=Depends(get_admin)):
    try:
        d=await request.json()
        r=await db.scenario_update(sid,d)
        return {"ok":True,"scenario":r}
    except Exception as e:
        return JSONResponse({"ok":False,"error":str(e)},500)

@router.put("/scenarios/{sid}")
async def update_scenario(sid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.scenario_update(sid,d)
    return {"ok":bool(r),"scenario":r}

@router.delete("/scenarios/{sid}")
async def delete_scenario(sid:int,_=Depends(get_admin)):
    await db.scenario_delete(sid)
    return {"ok":True}

@router.post("/scenarios/{sid}/activate")
async def activate_scenario(sid:int,_=Depends(get_admin)):
    sc=await db.scenario_get(sid)
    if not sc: return JSONResponse({"error":"bulunamadı"},404)
    await db.scenario_activate(sc["event_id"],sid)
    return {"ok":True}

@router.post("/scenarios/{sid}/deactivate")
async def deactivate_scenario(sid:int,_=Depends(get_admin)):
    async with db.conn() as c:
        await c.execute("UPDATE scenarios SET status='inactive' WHERE id=$1",sid)
    return {"ok":True}

@router.post("/scenarios/{sid}/advance")
async def advance_scenario(sid:int,_=Depends(get_admin)):
    nxt=await db.scenario_advance(sid)
    if not nxt: return JSONResponse({"error":"Son aşama"},400)
    # Telegram'a aşama başladı bildirimi
    try:
        sc=await db.scenario_get(sid)
        if sc and nxt.get("unlock_message_tr"):
            teams=await db.team_list(sc["event_id"])
            tokens=await db.bot_token_list()
            if tokens and teams:
                from core.bot_registry import TokenCipher
                from core.bot_handler import send
                import os
                cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
                tok=cipher.decrypt(tokens[0]["encrypted_token"])
                msg=f"🎯 <b>Yeni Aşama: {nxt['name']}</b>\n{nxt.get('unlock_message_tr','')}"
                for team in teams:
                    if team.get("telegram_group_id"):
                        try: await send(tok,team["telegram_group_id"],msg)
                        except: pass
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"TG aşama bildirimi: {e}")
    return {"ok":True,"stage":nxt}

# ─── Aşamalar ────────────────────────────────
@router.get("/scenarios/{sid}/stages")
async def list_stages(sid:int,_=Depends(get_admin)):
    return await db.stage_list(sid)

@router.post("/scenarios/{sid}/stages")
async def save_stage(sid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.stage_save(sid,d)
    return {"ok":True,"stage":r}

@router.delete("/stages/{stage_id}")
async def delete_stage(stage_id:int,_=Depends(get_admin)):
    await db.stage_delete(stage_id)
    return {"ok":True}

# ─── Görevler ────────────────────────────────
@router.get("/events/{eid}/tasks")
async def list_tasks(eid:int,_=Depends(get_admin)):
    return await db.task_list(eid)

@router.post("/events/{eid}/tasks")
async def create_task(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.task_save(eid,d)
    return {"ok":True,"task":r}

@router.put("/tasks/{tid}")
async def update_task(tid:int,request:Request,_=Depends(get_admin)):
    d=await request.json(); d["id"]=tid
    task=await db.task_get(tid)
    if not task: return JSONResponse({"error":"bulunamadı"},404)
    r=await db.task_save(task["event_id"],d)
    return {"ok":True,"task":r}

@router.delete("/tasks/{tid}")
async def delete_task(tid:int,_=Depends(get_admin)):
    await db.task_delete(tid)
    return {"ok":True}

@router.patch("/tasks/{tid}/toggle")
async def toggle_task(tid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    await db.task_toggle(tid,d.get("active",True))
    return {"ok":True}

# ─── Duyurular ───────────────────────────────
@router.get("/events/{eid}/announcements")
async def list_ann(eid:int,_=Depends(get_admin)):
    return await db.announcement_list(eid)

@router.post("/events/{eid}/announcements")
async def create_ann(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.announcement_create(eid,d)
    return {"ok":True,"announcement":r}

# ─── Quizler ─────────────────────────────────
@router.get("/events/{eid}/quizzes")
async def list_quizzes(eid:int,_=Depends(get_admin)):
    return await db.quiz_list(eid)

@router.post("/events/{eid}/quizzes")
async def save_quiz(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.quiz_save(eid,d)
    return {"ok":True,"quiz":r}

@router.delete("/quizzes/{qid}")
async def delete_quiz(qid:int,_=Depends(get_admin)):
    await db.quiz_delete(qid)
    return {"ok":True}
