from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from web.auth import get_admin
import core.db as db

router = APIRouter(tags=["events"])

@router.get("")
async def list_events(_=Depends(get_admin)):
    return await db.event_list()

@router.post("")
async def create_event(request: Request, _=Depends(get_admin)):
    d = await request.json()
    if not d.get("slug") or not d.get("name"):
        return JSONResponse({"ok":False,"error":"slug ve name gerekli"},400)
    r = await db.event_create(d)
    return {"ok":True,"event":r}

@router.get("/{eid}")
async def get_event(eid:int,_=Depends(get_admin)):
    e=await db.event_get(eid)
    if not e: return JSONResponse({"error":"bulunamadı"},404)
    return e

@router.put("/{eid}")
async def update_event(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.event_update(eid,d)
    return {"ok":bool(r),"event":r}

@router.delete("/{eid}")
async def delete_event(eid:int,_=Depends(get_admin)):
    await db.event_delete(eid)
    return {"ok":True}

@router.post("/{eid}/activate")
async def activate_event(eid:int,_=Depends(get_admin)):
    # Diğer aktif etkinlikleri pasifleştir
    events=await db.event_list()
    for e in events:
        if e["id"]!=eid and e["status"]=="active":
            await db.event_update(e["id"],{**e,"status":"paused"})
    r=await db.event_update(eid,{**(await db.event_get(eid)),"status":"active"})
    return {"ok":True,"event":r}

# ─── Nitelikler ─────────────────────────────
@router.get("/{eid}/attributes")
async def list_attrs(eid:int,_=Depends(get_admin)):
    return await db.attr_list(eid)

@router.post("/{eid}/attributes")
async def save_attr(eid:int,request:Request,_=Depends(get_admin)):
    try:
        d=await request.json()
        r=await db.attr_save(eid,d)
        return {"ok":True,"attr":r}
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"attr_save: {e}",exc_info=True)
        return JSONResponse({"ok":False,"error":str(e)},500)

@router.delete("/{eid}/attributes/{aid}")
async def del_attr(eid:int,aid:int,_=Depends(get_admin)):
    await db.attr_delete(aid)
    return {"ok":True}

# ─── Roller ─────────────────────────────────
@router.get("/{eid}/roles")
async def list_roles(eid:int,_=Depends(get_admin)):
    return await db.role_list(eid)

@router.post("/{eid}/roles")
async def save_role(eid:int,request:Request,_=Depends(get_admin)):
    try:
        d=await request.json()
        r=await db.role_save(eid,d)
        return {"ok":True,"role":r}
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"role_save: {e}",exc_info=True)
        return JSONResponse({"ok":False,"error":str(e)},500)

@router.delete("/{eid}/roles/{rid}")
async def del_role(eid:int,rid:int,_=Depends(get_admin)):
    await db.role_delete(rid)
    return {"ok":True}

# ─── Jüri kriterleri ────────────────────────
@router.get("/{eid}/jury-criteria")
async def list_jury_criteria(eid:int,_=Depends(get_admin)):
    return await db.jury_criteria_list(eid)

@router.post("/{eid}/jury-criteria")
async def save_jury_criterion(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.jury_criteria_save(eid,d)
    return {"ok":True,"criterion":r}

@router.delete("/{eid}/jury-criteria/{cid}")
async def del_jury_criterion(eid:int,cid:int,_=Depends(get_admin)):
    await db.jury_criteria_delete(cid)
    return {"ok":True}
