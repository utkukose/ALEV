"""
web/yaml_api.py — YAML Yönetim API'si

FastAPI router olarak web/app.py'ye dahil edilir:
    from web.yaml_api import yaml_router
    app.include_router(yaml_router, prefix="/admin/yaml")

Tüm endpoint'ler admin auth gerektirir.
Başarılı yazma sonrası config hot-reload tetiklenir.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Any

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import yaml_manager as ym
from web.auth import get_admin

yaml_router = APIRouter(tags=["yaml-management"])


def _get_admin_dep():
    return get_admin


# ══════════════════════════════════════════
# GÖREVLER
# ══════════════════════════════════════════
@yaml_router.get("/tasks")
async def list_tasks(_=Depends(get_admin)):
    return ym.get_tasks()

@yaml_router.get("/tasks/{task_id}")
async def get_task(task_id: str, _=Depends(get_admin)):
    t = ym.get_task(task_id)
    if not t: raise HTTPException(404, "Görev bulunamadı")
    return t

@yaml_router.post("/tasks")
async def create_task(request: Request, _=Depends(get_admin)):
    task = await request.json()
    if not task.get("id"): raise HTTPException(400, "id gerekli")
    if ym.get_task(task["id"]): raise HTTPException(409, "Bu ID zaten var")
    task.setdefault("active", True)
    task.setdefault("task_set", "default")
    task.setdefault("stat_rewards", {})
    ok = ym.save_task(task)
    return JSONResponse({"ok": ok, "id": task["id"]})

@yaml_router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: Request, _=Depends(get_admin)):
    task = await request.json()
    task["id"] = task_id
    ok = ym.save_task(task)
    return JSONResponse({"ok": ok})

@yaml_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, _=Depends(get_admin)):
    ok = ym.delete_task(task_id)
    return JSONResponse({"ok": ok})

@yaml_router.patch("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, request: Request, _=Depends(get_admin)):
    body = await request.json()
    ok = ym.toggle_task(task_id, body.get("active", True))
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# ROLLER
# ══════════════════════════════════════════
@yaml_router.get("/roles")
async def list_roles(_=Depends(get_admin)):
    roles = ym.get_roles()
    return [{"key": k, **v} for k, v in roles.items()]

@yaml_router.put("/roles/{role_key}")
async def update_role(role_key: str, request: Request, _=Depends(get_admin)):
    role = await request.json()
    role.pop("key", None)
    ok = ym.save_role(role_key, role)
    return JSONResponse({"ok": ok})

@yaml_router.post("/roles")
async def create_role(request: Request, _=Depends(get_admin)):
    body = await request.json()
    key = body.pop("key")
    if not key: raise HTTPException(400, "key gerekli")
    ok = ym.save_role(key, body)
    return JSONResponse({"ok": ok, "key": key})

@yaml_router.delete("/roles/{role_key}")
async def delete_role(role_key: str, _=Depends(get_admin)):
    ok = ym.delete_role(role_key)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# SENARYOLAR
# ══════════════════════════════════════════
@yaml_router.get("/scenarios")
async def list_scenarios(_=Depends(get_admin)):
    return ym.get_scenarios()

@yaml_router.get("/scenarios/{sid}")
async def get_scenario(sid: str, _=Depends(get_admin)):
    s = ym.get_scenario(sid)
    if not s: raise HTTPException(404)
    return s

@yaml_router.post("/scenarios")
async def create_scenario(request: Request, _=Depends(get_admin)):
    s = await request.json()
    if not s.get("id"): raise HTTPException(400, "id gerekli")
    s.setdefault("active", False)
    s.setdefault("auto_advance", False)
    s.setdefault("announce_to_all_groups", True)
    s.setdefault("stages", [])
    ok = ym.save_scenario(s)
    return JSONResponse({"ok": ok})

@yaml_router.put("/scenarios/{sid}")
async def update_scenario(sid: str, request: Request, _=Depends(get_admin)):
    s = await request.json(); s["id"] = sid
    ok = ym.save_scenario(s)
    return JSONResponse({"ok": ok})

@yaml_router.patch("/scenarios/{sid}/activate")
async def activate_scenario(sid: str, _=Depends(get_admin)):
    ok = ym.set_active_scenario(sid)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# QUIZler
# ══════════════════════════════════════════
@yaml_router.get("/quizzes")
async def list_quizzes(_=Depends(get_admin)):
    return ym.get_quiz_sets()

@yaml_router.post("/quizzes")
async def create_quiz(request: Request, _=Depends(get_admin)):
    qs = await request.json()
    if not qs.get("id"): raise HTTPException(400, "id gerekli")
    qs.setdefault("questions", [])
    qs.setdefault("cooldown_minutes", 60)
    ok = ym.save_quiz_set(qs)
    return JSONResponse({"ok": ok})

@yaml_router.put("/quizzes/{qsid}")
async def update_quiz(qsid: str, request: Request, _=Depends(get_admin)):
    qs = await request.json(); qs["id"] = qsid
    ok = ym.save_quiz_set(qs)
    return JSONResponse({"ok": ok})

@yaml_router.delete("/quizzes/{qsid}")
async def delete_quiz(qsid: str, _=Depends(get_admin)):
    ok = ym.delete_quiz_set(qsid)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# KONUM GÖREVLERİ
# ══════════════════════════════════════════
@yaml_router.get("/location-tasks")
async def list_location_tasks(_=Depends(get_admin)):
    return ym.get_location_tasks()

@yaml_router.post("/location-tasks")
async def create_location_task(request: Request, _=Depends(get_admin)):
    lt = await request.json()
    if not lt.get("task_id"): raise HTTPException(400, "task_id gerekli")
    lt.setdefault("radius_meters", 100)
    ok = ym.save_location_task(lt)
    return JSONResponse({"ok": ok})

@yaml_router.put("/location-tasks/{task_id}")
async def update_location_task(task_id: str, request: Request, _=Depends(get_admin)):
    lt = await request.json(); lt["task_id"] = task_id
    ok = ym.save_location_task(lt)
    return JSONResponse({"ok": ok})

@yaml_router.delete("/location-tasks/{task_id}")
async def delete_location_task(task_id: str, _=Depends(get_admin)):
    ok = ym.delete_location_task(task_id)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# KARAR AĞACI
# ══════════════════════════════════════════
@yaml_router.get("/branching")
async def list_branching(_=Depends(get_admin)):
    return ym.get_branching_scenarios()

@yaml_router.post("/branching")
async def create_branching(request: Request, _=Depends(get_admin)):
    bs = await request.json()
    if not bs.get("id"): raise HTTPException(400, "id gerekli")
    bs.setdefault("nodes", [])
    ok = ym.save_branching_scenario(bs)
    return JSONResponse({"ok": ok})

@yaml_router.put("/branching/{sid}")
async def update_branching(sid: str, request: Request, _=Depends(get_admin)):
    bs = await request.json(); bs["id"] = sid
    ok = ym.save_branching_scenario(bs)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# JÜRİ
# ══════════════════════════════════════════
@yaml_router.get("/jury")
async def get_jury(_=Depends(get_admin)):
    return ym.get_jury_config()

@yaml_router.put("/jury")
async def update_jury(request: Request, _=Depends(get_admin)):
    jury = await request.json()
    ok = ym.save_jury_config(jury)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# GRUPLAR / BOT EKOSİSTEMİ
# ══════════════════════════════════════════
@yaml_router.get("/groups")
async def get_groups(_=Depends(get_admin)):
    return ym.get_groups_config()

@yaml_router.put("/groups")
async def update_groups(request: Request, _=Depends(get_admin)):
    groups = await request.json()
    ok = ym.save_groups_config(groups)
    return JSONResponse({"ok": ok})


# ══════════════════════════════════════════
# HOT-RELOAD
# ══════════════════════════════════════════
@yaml_router.post("/reload")
async def force_reload(_=Depends(get_admin)):
    """Tüm config'i yeniden yükle."""
    await ym._trigger_reload()
    return JSONResponse({"ok": True, "message": "Config yeniden yüklendi"})
