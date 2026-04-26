"""
core/db.py — ALEV v2.0 Veritabanı Katmanı
asyncpg connection pool + tüm CRUD operasyonları
Hiyerarşi: Etkinlik → Senaryo → Görev → Takım → Üye → RPG
"""
from __future__ import annotations
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None


import datetime as _dt_mod

def _safe_dict(row) -> dict:
    import json as _json
    if row is None:
        return None
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, (_dt_mod.datetime, _dt_mod.date)):
            out[k] = v.isoformat()
        elif isinstance(v, _dt_mod.timedelta):
            out[k] = str(v)
        elif isinstance(v, str) and len(v) > 0 and v[0] in ('{', '['):
            try:
                out[k] = _json.loads(v)
            except Exception:
                out[k] = v
        else:
            out[k] = v
    return out

def _safe_json(val) -> dict:
    """DB'den gelen JSON string veya dict'i güvenle parse eder."""
    if not val: return {}
    if isinstance(val, dict): return val
    if isinstance(val, str):
        import json as _jj
        try: return _jj.loads(val)
        except: return {}
    return {}

async def init_pool():
    global _pool
    dsn = os.getenv("DATABASE_URL","postgresql://alev:alev_secret@db:5432/alev")
    _pool = await asyncpg.create_pool(
        dsn, min_size=3, max_size=30,
        max_inactive_connection_lifetime=300.0, command_timeout=30)
    log.info("DB pool hazır")

async def close_pool():
    if _pool: await _pool.close()

@asynccontextmanager
async def conn():
    async with _pool.acquire() as c:
        yield c

async def init_schema():
    sql = (Path(__file__).parent / "schema.sql").read_text()
    async with conn() as c:
        await c.execute(sql)
    log.info("Şema başlatıldı")

def _j(d): return json.dumps(d) if isinstance(d, dict) else (d or "{}")

def _dt(v):
    """String tarihi datetime'a çevir, None veya datetime ise dokunma."""
    if not v:
        return None
    if hasattr(v, 'date'):
        return v
    from datetime import datetime
    try:
        # "2026-04-23T23:23" veya "2026-04-23T23:23:00" formatları
        v = str(v).strip()
        if len(v) == 16:  # "2026-04-23T23:23"
            return datetime.fromisoformat(v + ":00")
        return datetime.fromisoformat(v)
    except Exception:
        return None

# ─── ETKİNLİK ──────────────────────────────────────────────
async def event_create(d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO events(slug,name,description,status,start_at,end_at,
                max_teams,max_members_per_team,join_mode,settings)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
            d["slug"],d["name"],d.get("description"),d.get("status","draft"),
            _dt(d.get("start_at")),_dt(d.get("end_at")),d.get("max_teams",20),
            d.get("max_members_per_team",6),d.get("join_mode","code"),_j(d.get("settings",{})))
        return _safe_dict(r)

async def event_list()->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT e.*,
                   COUNT(DISTINCT t.id) as team_count,
                   COUNT(DISTINCT sc.id) as scenario_count
            FROM events e
            LEFT JOIN teams t ON t.event_id=e.id
            LEFT JOIN scenarios sc ON sc.event_id=e.id
            GROUP BY e.id
            ORDER BY e.created_at DESC""")]

async def event_get(eid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM events WHERE id=$1",eid)
        return _safe_dict(r)

async def event_get_slug(slug:str)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM events WHERE slug=$1",slug)
        return _safe_dict(r)

async def event_update(eid:int,d:dict)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("""
            UPDATE events SET name=$2,description=$3,status=$4,start_at=$5,
                end_at=$6,max_teams=$7,max_members_per_team=$8,join_mode=$9,
                settings=$10,max_tasks_per_member=$11,language=$12,updated_at=NOW() WHERE id=$1 RETURNING *""",
            eid,d.get("name"),d.get("description"),d.get("status","draft"),
            _dt(d.get("start_at")),_dt(d.get("end_at")),d.get("max_teams",20),
            d.get("max_members_per_team",6),d.get("join_mode","code"),
            _j(d.get("settings",{})),int(d.get("max_tasks_per_member") or 0),
            d.get("language","tr") or "tr")
        return _safe_dict(r)

async def event_delete(eid:int):
    async with conn() as c: await c.execute("DELETE FROM events WHERE id=$1",eid)

async def event_active()->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM events WHERE status='active' ORDER BY created_at DESC LIMIT 1")
        return _safe_dict(r)

# ─── NİTELİKLER ────────────────────────────────────────────
async def attr_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT *,COALESCE(name_tr,name_en,'') as name,COALESCE(description_tr,description_en,'') as description FROM event_attributes WHERE event_id=$1 ORDER BY sort_order",eid)]

async def attr_save(eid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO event_attributes(event_id,key,name_tr,name_en,
                description_tr,description_en,emoji,min_val,max_val,default_val,color,sort_order)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT(event_id,key) DO UPDATE SET
                name_tr=$3,name_en=$4,description_tr=$5,description_en=$6,
                emoji=$7,min_val=$8,max_val=$9,default_val=$10,color=$11,sort_order=$12
            RETURNING *""",
            eid,d["key"],d["name_tr"],d.get("name_en",d["name_tr"]),
            d.get("description_tr"),d.get("description_en"),
            d.get("emoji","⭐"),d.get("min_val",0),d.get("max_val",20),
            d.get("default_val",5),d.get("color","amber"),d.get("sort_order",0))
        return _safe_dict(r)

async def attr_delete(aid:int):
    async with conn() as c: await c.execute("DELETE FROM event_attributes WHERE id=$1",aid)

# ─── ROLLER ─────────────────────────────────────────────────
async def role_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT *,COALESCE(name_tr,name_en,'') as name,COALESCE(description_tr,description_en,'') as description FROM event_roles WHERE event_id=$1 ORDER BY id",eid)]

async def role_save(eid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO event_roles(event_id,key,name_tr,name_en,description_tr,
                description_en,emoji,color,
                base_attributes)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT(event_id,key) DO UPDATE SET
                name_tr=$3,name_en=$4,description_tr=$5,description_en=$6,
                emoji=$7,color=$8,
                base_attributes=EXCLUDED.base_attributes
            RETURNING *""",
            eid,d["key"],d["name_tr"],d.get("name_en",d["name_tr"]),
            d.get("description_tr"),d.get("description_en"),
            d.get("emoji","⚔️"),d.get("color","amber"),
            _j(d.get("base_attributes",{})))
        return _safe_dict(r)

async def role_delete(rid:int):
    async with conn() as c: await c.execute("DELETE FROM event_roles WHERE id=$1",rid)

# ─── SENARYOLAR ─────────────────────────────────────────────
async def scenario_list(eid:int)->list:
    async with conn() as c:
        rows = await c.fetch("""
            SELECT s.*,
                   COUNT(t.id) as task_count
            FROM scenarios s
            LEFT JOIN tasks t ON t.scenario_id=s.id
            WHERE s.event_id=$1
            GROUP BY s.id
            ORDER BY s.id""", eid)
        return [_safe_dict(r) for r in rows]

async def scenario_get(sid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM scenarios WHERE id=$1",sid)
        return _safe_dict(r)

async def scenario_create(eid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO scenarios(event_id,name,description,auto_advance,settings,
                min_tasks_required,bonus_sp,first_bonus_sp,bonus_badge,bonus_attrs)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
            eid,d["name"],d.get("description"),
            d.get("auto_advance",False),_j(d.get("settings",{})),
            d.get("min_tasks_required",1),d.get("bonus_sp",500),
            d.get("first_bonus_sp",1000),d.get("bonus_badge",""),
            _j(d.get("bonus_attrs",{})))
        return _safe_dict(r)

async def scenario_update(sid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            UPDATE scenarios SET name=$2,description=$3,auto_advance=$4,
                min_tasks_required=$5,bonus_sp=$6,first_bonus_sp=$7,
                bonus_badge=$8,bonus_attrs=$9
            WHERE id=$1 RETURNING *""",
            sid,d.get("name",""),d.get("description"),d.get("auto_advance",False),
            d.get("min_tasks_required",1),d.get("bonus_sp",500),
            d.get("first_bonus_sp",1000),d.get("bonus_badge",""),
            _j(d.get("bonus_attrs",{})))
        return _safe_dict(r)



async def scenario_delete(sid:int):
    async with conn() as c: await c.execute("DELETE FROM scenarios WHERE id=$1",sid)

async def scenario_activate(eid:int,sid:int):
    async with conn() as c:
        await c.execute("UPDATE scenarios SET status='inactive' WHERE event_id=$1",eid)
        await c.execute("UPDATE scenarios SET status='active' WHERE id=$1",sid)

# ─── AŞAMALAR ───────────────────────────────────────────────
async def stage_list(sid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT * FROM scenario_stages WHERE scenario_id=$1 ORDER BY stage_order",sid)]

async def stage_save(sid:int,d:dict)->dict:
    async with conn() as c:
        if d.get("id"):
            r=await c.fetchrow("""
                UPDATE scenario_stages SET stage_order=$2,name=$3,description=$4,
                    duration_minutes=$5,xp_multiplier=$6,task_filter=$7,
                    unlock_message_tr=$8,unlock_message_en=$9,is_final=$10
                WHERE id=$1 RETURNING *""",
                d["id"],d.get("stage_order",1),d["name"],d.get("description"),
                d.get("duration_minutes",60),d.get("xp_multiplier",1.0),
                _j(d.get("task_filter",{})),d.get("unlock_message_tr"),
                d.get("unlock_message_en"),d.get("is_final",False))
        else:
            r=await c.fetchrow("""
                INSERT INTO scenario_stages(scenario_id,stage_order,name,description,
                    duration_minutes,xp_multiplier,task_filter,
                    unlock_message_tr,unlock_message_en,is_final)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
                sid,d.get("stage_order",1),d["name"],d.get("description"),
                d.get("duration_minutes",60),d.get("xp_multiplier",1.0),
                _j(d.get("task_filter",{})),d.get("unlock_message_tr"),
                d.get("unlock_message_en"),d.get("is_final",False))
        return _safe_dict(r)

async def stage_delete(stage_id:int):
    async with conn() as c: await c.execute("DELETE FROM scenario_stages WHERE id=$1",stage_id)

async def scenario_advance(sid:int)->dict|None:
    async with conn() as c:
        sc=await c.fetchrow("SELECT * FROM scenarios WHERE id=$1",sid)
        if not sc: return None
        stages=await c.fetch(
            "SELECT * FROM scenario_stages WHERE scenario_id=$1 ORDER BY stage_order",sid)
        if not stages: return None
        cur=sc["current_stage_id"]
        if not cur: nxt=stages[0]
        else:
            cur_ord=next((s["stage_order"] for s in stages if s["id"]==cur),0)
            nxt=next((s for s in stages if s["stage_order"]>cur_ord),None)
        if not nxt: return None
        await c.execute("UPDATE scenarios SET current_stage_id=$1 WHERE id=$2",nxt["id"],sid)
        return dict(nxt)

# ─── GÖREVLER ───────────────────────────────────────────────
async def task_list(eid:int,active_only:bool=False)->list:
    async with conn() as c:
        q=("""SELECT t.*,
              COALESCE(t.title_tr,t.title_en,'') as title,
              COALESCE(t.description_tr,t.description_en,'') as description,
              ss.name as stage_name,
              sc.name as scenario_name,
              sc.status as scenario_status
              FROM tasks t
              LEFT JOIN scenario_stages ss ON t.stage_id=ss.id
              LEFT JOIN scenarios sc ON COALESCE(t.scenario_id,ss.scenario_id)=sc.id
              WHERE t.event_id=$1""" +
           ("" if not active_only else " AND t.active=TRUE") +
           " ORDER BY t.sort_order,t.id")
        return [_safe_dict(r) for r in await c.fetch(q,eid)]

async def task_get(tid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM tasks WHERE id=$1",tid)
        return _safe_dict(r)

async def task_save(eid:int,d:dict)->dict:
    sid = int(d["scenario_id"]) if d.get("scenario_id") else None
    stid = int(d["stage_id"]) if d.get("stage_id") else None
    async with conn() as c:
        if d.get("id"):
            r=await c.fetchrow("""
                UPDATE tasks SET title_tr=$2,title_en=$3,description_tr=$4,
                    description_en=$5,task_type=$6,difficulty=$7,sp_reward=$8,
                    attribute_rewards=$9,proof_type=$10,stage_id=$11,active=$12,
                    max_completions=$13,badge_id=$14,sort_order=$15,scenario_id=$16,
                    rpg_attr_switches=$17
                WHERE id=$1 RETURNING *""",
                int(d["id"]),d["title_tr"],d.get("title_en",d["title_tr"]),
                d.get("description_tr"),d.get("description_en"),
                d.get("task_type","general"),d.get("difficulty","orta"),
                int(d.get("sp_reward",300)),_j(d.get("attribute_rewards",{})),
                d.get("proof_type","link"),stid,
                d.get("active",True),int(d.get("max_completions",1)),
                d.get("badge_id"),int(d.get("sort_order",0)),sid,
                _j(d.get("rpg_attr_switches",{})))
        else:
            r=await c.fetchrow("""
                INSERT INTO tasks(event_id,title_tr,title_en,description_tr,
                    description_en,task_type,difficulty,sp_reward,attribute_rewards,
                    proof_type,stage_id,active,max_completions,badge_id,sort_order,scenario_id,
                    rpg_attr_switches)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) RETURNING *""",
                eid,d["title_tr"],d.get("title_en",d["title_tr"]),
                d.get("description_tr"),d.get("description_en"),
                d.get("task_type","general"),d.get("difficulty","orta"),
                int(d.get("sp_reward",300)),_j(d.get("attribute_rewards",{})),
                d.get("proof_type","link"),stid,
                d.get("active",True),int(d.get("max_completions",1)),
                d.get("badge_id"),int(d.get("sort_order",0)),sid,
                _j(d.get("rpg_attr_switches",{})))
        return _safe_dict(r)

async def task_delete(tid:int):
    async with conn() as c: await c.execute("DELETE FROM tasks WHERE id=$1",tid)

async def task_toggle(tid:int,active:bool):
    async with conn() as c: await c.execute("UPDATE tasks SET active=$1 WHERE id=$2",active,tid)

# ─── TAKIMLAR ───────────────────────────────────────────────
def _gen_code()->str:
    import random,string
    return ''.join(random.choices(string.ascii_uppercase+string.digits,k=6))

async def team_create(eid:int,d:dict)->dict:
    while True:
        code=_gen_code()
        async with conn() as c:
            if not await c.fetchval("SELECT id FROM teams WHERE invite_code=$1",code): break
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO teams(event_id,name,role_id,telegram_group_id,
                telegram_group_name,invite_code,attributes)
            VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
            eid,d["name"],d.get("role_id"),d.get("telegram_group_id"),
            d.get("telegram_group_name"),code,_j(d.get("attributes",{})))
        return _safe_dict(r)

async def team_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT t.*,r.name_tr as role_name,r.emoji as role_emoji,
                   r.color as role_color,COUNT(m.id) as member_count
            FROM teams t
            LEFT JOIN event_roles r ON t.role_id=r.id
            LEFT JOIN team_members m ON m.team_id=t.id
            WHERE t.event_id=$1
            GROUP BY t.id,r.name_tr,r.emoji,r.color
            ORDER BY t.xp DESC,t.id""",eid)]

async def team_get(tid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("""
            SELECT t.*,r.name_tr as role_name,r.name_en as role_name_en,
                   r.emoji as role_emoji,r.color as role_color
            FROM teams t LEFT JOIN event_roles r ON t.role_id=r.id
            WHERE t.id=$1""",tid)
        return _safe_dict(r)

async def team_by_code(code:str)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM teams WHERE invite_code=$1",code.upper())
        return _safe_dict(r)

async def team_by_tg(tgid:int,eid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("""
            SELECT t.* FROM teams t JOIN team_members m ON m.team_id=t.id
            WHERE m.telegram_id=$1 AND t.event_id=$2""",tgid,eid)
        return _safe_dict(r)

async def team_update(tid:int,d:dict)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("""
            UPDATE teams SET name=$2,role_id=$3,telegram_group_id=$4,
                telegram_group_name=$5,status=$6,attributes=$7
            WHERE id=$1 RETURNING *""",
            tid,d["name"],d.get("role_id"),d.get("telegram_group_id"),
            d.get("telegram_group_name"),d.get("status","active"),
            _j(d.get("attributes",{})))
        return _safe_dict(r)

async def team_delete(tid:int):
    async with conn() as c: await c.execute("DELETE FROM teams WHERE id=$1",tid)

async def team_add_xp(tid:int,xp:int,attr_rewards:dict|None=None):
    async with conn() as c:
        await c.execute("UPDATE teams SET xp=xp+$1 WHERE id=$2",xp,tid)
        if attr_rewards and isinstance(attr_rewards,dict) and any(v for v in attr_rewards.values() if v):
            try:
                t=await c.fetchrow("SELECT attributes FROM teams WHERE id=$1",tid)
                raw=t["attributes"] if t and t["attributes"] else {}
                attrs=dict(raw) if raw else {}
                for k,v in attr_rewards.items():
                    if isinstance(v,(int,float)) and v>0:
                        attrs[k]=attrs.get(k,0)+v
                await c.execute("UPDATE teams SET attributes=$1 WHERE id=$2",_j(attrs),tid)
            except Exception as _ae:
                import logging; logging.getLogger(__name__).warning("attr_xp: "+str(_ae))
        await c.execute(
            "UPDATE teams SET level=GREATEST(1,(xp/1000)+1) WHERE id=$1",tid)

async def team_regen_code(tid:int)->str:
    while True:
        code=_gen_code()
        async with conn() as c:
            if not await c.fetchval("SELECT id FROM teams WHERE invite_code=$1",code):
                await c.execute("UPDATE teams SET invite_code=$1 WHERE id=$2",code,tid)
                return code

# ─── ÜYELER ─────────────────────────────────────────────────
async def member_add(tid:int,d:dict)->dict:
    async with conn() as c:
        # Üyenin kendi rolü varsa onun base_attributes'ını al, yoksa takım rolünü kullan
        role_id = d.get("role_id")
        if role_id:
            role_row = await c.fetchrow("SELECT base_attributes FROM event_roles WHERE id=$1", role_id)
        else:
            role_row = await c.fetchrow(
                "SELECT r.base_attributes FROM teams t JOIN event_roles r ON t.role_id=r.id WHERE t.id=$1",tid)
        raw=role_row["base_attributes"] if role_row else {}
        if isinstance(raw,str):
            import json as _json
            try: raw=_json.loads(raw)
            except: raw={}
        base=dict(raw or {})
        r=await c.fetchrow("""
            INSERT INTO team_members(team_id,telegram_id,username,display_name,role,role_id,role_name,attributes)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(team_id,telegram_id) DO UPDATE SET 
                username=$3,display_name=$4,role_id=$6,role_name=$7
            RETURNING *""",
            tid,d["telegram_id"],d.get("username"),d.get("display_name"),
            d.get("role","member"),role_id,d.get("role_name") or d.get("character_name"),
            _j(d.get("attributes",base)))
        return _safe_dict(r)

async def member_list(tid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT m.*,
                   COALESCE(r.name_tr,r.name_en,'') as char_role_name,
                   r.emoji as char_role_emoji,r.color as char_role_color
            FROM team_members m
            LEFT JOIN event_roles r ON m.role_id=r.id
            WHERE m.team_id=$1 ORDER BY m.role DESC,m.joined_at""",tid)]

async def member_remove(tid:int,tgid:int):
    async with conn() as c:
        await c.execute("DELETE FROM team_members WHERE team_id=$1 AND telegram_id=$2",tid,tgid)

async def member_find(tgid:int)->dict|None:
    async with conn() as c:
        r=await c.fetchrow(
            "SELECT m.*,t.name as team_name,t.event_id FROM team_members m "
            "JOIN teams t ON m.team_id=t.id WHERE m.telegram_id=$1 LIMIT 1",tgid)
        return _safe_dict(r)

# ─── GÖREV TAMAMLAMA ────────────────────────────────────────
async def completion_submit(task_id:int,team_id:int,tgid:int,proof:str)->dict:
    async with conn() as c:
        # Üyenin rolü var mı kontrol et
        member = await c.fetchrow(
            "SELECT role_id FROM team_members WHERE telegram_id=$1 AND team_id=$2",
            tgid, team_id)
        if not member or not member["role_id"]:
            return {"error": "no_role", "message": "Görev göndermeden önce rol seçmelisiniz."}
        r=await c.fetchrow("""
            INSERT INTO task_completions(task_id,team_id,submitted_by,proof_url,status)
            VALUES($1,$2,$3,$4,'pending') RETURNING *""",task_id,team_id,tgid,proof)
        return _safe_dict(r)

async def completion_pending(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT tc.*,
                   COALESCE(t.title_tr,t.title_en,'') as title,
                   t.title_tr,t.title_en,t.sp_reward,t.attribute_rewards,
                   tm.name as team_name,
                   tm.telegram_group_id
            FROM task_completions tc
            JOIN tasks t ON tc.task_id=t.id
            JOIN teams tm ON tc.team_id=tm.id
            WHERE t.event_id=$1 AND tc.status='pending'
            ORDER BY tc.submitted_at""",eid)]

async def completion_review(cid:int,status:str,reviewer:str,note:str="")->dict|None:
    """
    Görev onay/red işlemi.

    Onaylanınca:
    1. Kişi başı görev limiti kontrolü (max_tasks_per_member)
    2. Temel SP hesabı: task.sp_reward
    3. Rol bonusu: attribute_rewards ile role.base_attributes eşleşmesi
       - Her eşleşen nitelik için: bonus = base_sp * (role_attr / max_attr)
       - Maksimum bonus: +%100 (2x)
    4. Takım SP güncelle, Takım RPG nitelikleri güncelle
    5. Üye kişisel SP logu (member_bp_log)
    """
    import json as _j2, logging as _log
    _logger = _log.getLogger(__name__)
    MAX_ATTR_VALUE = 20  # Rol nitelik maksimum değeri (normalleştirme için)

    async with conn() as c:
        r = await c.fetchrow("""
            UPDATE task_completions SET status=$2,reviewed_by=$3,
                review_note=$4,reviewed_at=NOW() WHERE id=$1 RETURNING *""",
            cid, status, reviewer, note)
        if not r:
            return None

        if status != "approved":
            return _safe_dict(r)

        # ── Görev ve etkinlik bilgilerini al ──────────────────────────
        task = await c.fetchrow("""
            SELECT t.*, e.max_tasks_per_member
            FROM tasks t
            JOIN events e ON t.event_id = e.id
            WHERE t.id = $1
        """, r["task_id"])
        if not task:
            return _safe_dict(r)

        # ── 1. Kişi başı görev limiti kontrolü ───────────────────────
        max_per_member = task["max_tasks_per_member"] or 0
        if max_per_member > 0 and r["submitted_by"]:
            done_count = await c.fetchval("""
                SELECT COUNT(*) FROM task_completions tc
                JOIN tasks t ON tc.task_id = t.id
                WHERE tc.team_id = $1
                  AND tc.submitted_by = $2
                  AND tc.status = 'approved'
                  AND t.event_id = $3
                  AND tc.id != $4
            """, r["team_id"], r["submitted_by"], task["event_id"], cid)
            if done_count >= max_per_member:
                # Limiti aşıyor - onayı iptal et, reddolarak işaretle
                await c.execute("""
                    UPDATE task_completions
                    SET status='rejected', review_note='Kişi başı görev limitine ulaşıldı'
                    WHERE id=$1
                """, cid)
                _logger.warning(f"[SP] Görev limiti aşıldı: completion={cid} member={r['submitted_by']}")
                result = _safe_dict(r)
                result["rejected_reason"] = "limit_exceeded"
                return result

        # ── 2. Temel SP ───────────────────────────────────────────────
        base_sp = task["sp_reward"] or 300

        # ── 3. Rol bonusu hesapla ─────────────────────────────────────
        attr_raw = _safe_json(task["attribute_rewards"])

        bonus_sp = 0
        role_key = None
        member_id = None
        role_attrs = {}

        if r["submitted_by"] and attr_raw:
            member = await c.fetchrow("""
                SELECT m.id, er.key as role_key, er.base_attributes as role_attrs
                FROM team_members m
                LEFT JOIN event_roles er ON m.role_id = er.id
                WHERE m.telegram_id = $1 AND m.team_id = $2
                LIMIT 1
            """, r["submitted_by"], r["team_id"])

            if member and member["role_key"] and member["role_attrs"]:
                member_id = member["id"]
                role_key = member["role_key"]
                role_attrs = _safe_json(member["role_attrs"])

                # Her eşleşen nitelik için oransal bonus
                # bonus_ratio = role_attr / MAX_ATTR_VALUE
                # bonus_sp += base_sp * bonus_ratio (nitelik başına)
                for attr_key, task_attr_val in attr_raw.items():
                    if not isinstance(task_attr_val, (int, float)) or task_attr_val <= 0:
                        continue
                    role_val = role_attrs.get(attr_key, 0)
                    if role_val <= 0:
                        continue
                    ratio = min(role_val / MAX_ATTR_VALUE, 1.0)
                    bonus_sp += int(base_sp * ratio)

        # Toplam SP (max 2x base_sp)
        total_sp = min(base_sp + bonus_sp, base_sp * 2)
        _logger.info(f"[SP] completion={cid} base={base_sp} bonus={bonus_sp} total={total_sp} role={role_key}")

        # ── 4. Completion güncelle ────────────────────────────────────
        await c.execute("""
            UPDATE task_completions SET sp_awarded=$1 WHERE id=$2
        """, total_sp, cid)

        # ── 5. Takıma SP ekle ─────────────────────────────────────────
        await c.execute("UPDATE teams SET xp=xp+$1 WHERE id=$2", total_sp, r["team_id"])

        # ── 6. Takım RPG nitelikleri güncelle ─────────────────────────
        if attr_raw:
            t_row = await c.fetchrow("SELECT attributes FROM teams WHERE id=$1", r["team_id"])
            cur_attrs = _safe_json(t_row["attributes"] if t_row else None)
            for k, v in attr_raw.items():
                if isinstance(v, (int, float)) and v > 0:
                    cur_attrs[k] = cur_attrs.get(k, 0) + v
            await c.execute("UPDATE teams SET attributes=$1 WHERE id=$2", _j(cur_attrs), r["team_id"])

        # ── 7. Üye kişisel SP logu ────────────────────────────────────
        if member_id and role_key:
            try:
                for attr_key, task_attr_val in attr_raw.items():
                    if not isinstance(task_attr_val, (int, float)) or task_attr_val <= 0:
                        continue
                    role_val = role_attrs.get(attr_key, 0)
                    if role_val <= 0:
                        continue
                    ratio = min(role_val / MAX_ATTR_VALUE, 1.0)
                    attr_bonus = int(base_sp * ratio)
                    await c.execute("""
                        INSERT INTO member_bp_log
                          (member_id,team_id,task_id,completion_id,role_key,attr_key,bp_earned,note)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                    """, member_id, r["team_id"], r["task_id"], cid,
                        role_key, attr_key, attr_bonus, f"Rol bonusu ({attr_key})")
            except Exception as _e:
                _logger.warning(f"[SP] member_bp_log hatası: {_e}")
            # Üye toplam SP güncelle (base + bonus)
            await c.execute("""
                UPDATE team_members SET bp=COALESCE(bp,0)+$1 WHERE id=$2
            """, total_sp, member_id)

        result = _safe_dict(r)
        result["sp_reward"] = base_sp
        result["bonus_sp"] = bonus_sp
        result["total_sp"] = total_sp
        result["attribute_rewards"] = attr_raw
        result["task_id"] = r["task_id"]
        result["team_id"] = r["team_id"]
        return result

async def completion_history(tid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT tc.*,t.title_tr,t.title_en,t.sp_reward
            FROM task_completions tc JOIN tasks t ON tc.task_id=t.id
            WHERE tc.team_id=$1 ORDER BY tc.submitted_at DESC""",tid)]

# ─── JÜRİ ───────────────────────────────────────────────────
async def jury_criteria_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT *,COALESCE(name_tr,name_en,'') as name FROM jury_criteria WHERE event_id=$1 ORDER BY id",eid)]

async def jury_criteria_save(eid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO jury_criteria(event_id,key,name_tr,name_en,emoji,weight,min_score,max_score)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(event_id,key) DO UPDATE SET
                name_tr=$3,name_en=$4,emoji=$5,weight=$6,min_score=$7,max_score=$8
            RETURNING *""",
            eid,d["key"],d["name_tr"],d.get("name_en",d["name_tr"]),
            d.get("emoji","⭐"),d.get("weight",1.0),d.get("min_score",0),d.get("max_score",100))
        return _safe_dict(r)

async def jury_criteria_delete(cid:int):
    async with conn() as c: await c.execute("DELETE FROM jury_criteria WHERE id=$1",cid)

async def jury_score_save(eid:int,tid:int,criterion:str,score:float,jury_user:int,note:str="")->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO jury_scores(event_id,team_id,criterion,score,jury_user,note)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT(event_id,team_id,criterion,jury_user) DO UPDATE SET
                score=$4,note=$6,scored_at=NOW()
            RETURNING *""",eid,tid,criterion,score,jury_user,note)
        return _safe_dict(r)

async def jury_scores(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT js.*,tm.name as team_name FROM jury_scores js
            JOIN teams tm ON js.team_id=tm.id
            WHERE js.event_id=$1 ORDER BY js.team_id,js.criterion""",eid)]

async def jury_member_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT * FROM jury_members WHERE event_id=$1",eid)]

async def jury_member_save(eid:int,tgid:int,name:str)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO jury_members(event_id,telegram_id,name)
            VALUES($1,$2,$3) ON CONFLICT(event_id,telegram_id) DO UPDATE SET name=$3
            RETURNING *""",eid,tgid,name)
        return _safe_dict(r)


async def check_scenario_completion(task_id:int, team_id:int, event_id:int):
    """Görev onaylandıktan sonra senaryo tamamlama kontrolü yap."""
    import json as _j3
    async with conn() as c:
        # Bu görevin bağlı olduğu stage ve senaryo
        task = await c.fetchrow("""
            SELECT t.*
            FROM tasks t
            WHERE t.id=$1""", task_id)
        if not task or not task["scenario_id"]:
            return None  # Senaryoya bağlı değil

        sc_id = task["scenario_id"]
        sc = await c.fetchrow("SELECT * FROM scenarios WHERE id=$1", sc_id)
        if not sc:
            return None

        min_req = sc["min_tasks_required"] or 1

        # Bu senaryo için takımın tamamlanan görev sayısını bul
        completed = await c.fetchrow("""
            SELECT COUNT(DISTINCT tc.task_id) as cnt
            FROM task_completions tc
            JOIN tasks t ON tc.task_id=t.id
            WHERE t.scenario_id=$1 AND tc.team_id=$2 AND tc.status='approved'
        """, sc_id, team_id)

        cnt = completed["cnt"] if completed else 0
        if cnt < min_req:
            return None  # Henüz yeterli görev tamamlanmadı

        # Daha önce tamamlamış mı?
        already = await c.fetchrow(
            "SELECT id FROM scenario_completions WHERE scenario_id=$1 AND team_id=$2",
            sc_id, team_id)
        if already:
            return None  # Zaten tamamlamış

        # Kaçıncı tamamlayan?
        rank_row = await c.fetchrow(
            "SELECT COUNT(*)+1 as rnk FROM scenario_completions WHERE scenario_id=$1",
            sc_id)
        rank = rank_row["rnk"] if rank_row else 1

        # Bonus XP hesapla
        if rank == 1:
            bonus = sc["first_bonus_sp"] or 1000
        else:
            bonus = sc["bonus_sp"] or 500

        badge = sc["bonus_badge"] or ""

        # Kaydet
        await c.execute("""
            INSERT INTO scenario_completions(scenario_id,team_id,event_id,rank,bonus_sp,badge)
            VALUES($1,$2,$3,$4,$5,$6)
        """, sc_id, team_id, event_id, rank, bonus, badge)

        # XP ekle
        await c.execute(
            "UPDATE teams SET xp=xp+$1 WHERE id=$2",
            bonus, team_id)

        # Badge ekle (teams.badges dizisine)
        if badge:
            await c.execute(
                "UPDATE teams SET badges=array_append(badges,$1) WHERE id=$2 AND NOT ($1=ANY(badges))",
                badge, team_id)

        team = await c.fetchrow("SELECT name FROM teams WHERE id=$1", team_id)
        return {
            "triggered": True,
            "scenario_name": sc["name"],
            "rank": rank,
            "bonus_sp": bonus,
            "badge": badge,
            "team_name": team["name"] if team else "",
            "team_id": team_id,
        }

async def jury_notify_telegram(eid:int,team_name:str,scores:dict,total:float):
    try:
        team_rows=await team_list(eid)
        tokens=await bot_token_list()
        if not tokens: return
        from core.bot_registry import TokenCipher
        from core.bot_handler import send
        import os
        cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
        tok=cipher.decrypt(tokens[0]["encrypted_token"])
        team=next((t for t in team_rows if t["name"]==team_name),None)
        if team and team.get("telegram_group_id"):
            lines="; ".join(f"{k}:{v}" for k,v in scores.items())
            msg=f"Juri: {team_name} | {lines} | Toplam:{total:.1f}"
            await send(tok,team["telegram_group_id"],msg)
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"Juri TG: {e}")

async def jury_session_create(eid:int,tgid:int,name:str)->str:
    import secrets
    token=secrets.token_urlsafe(24)
    async with conn() as c:
        await c.execute("""
            INSERT INTO jury_sessions(event_id,telegram_id,token,name)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(event_id,telegram_id) DO UPDATE SET token=$3,name=$4
        """,eid,tgid,token,name)
    return token

async def jury_session_verify(token:str)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM jury_sessions WHERE token=$1",token)
        return _safe_dict(r)

async def jury_member_delete(jid:int):
    async with conn() as c: await c.execute("DELETE FROM jury_members WHERE id=$1",jid)

# ─── DUYURULAR ──────────────────────────────────────────────
async def announcement_create(eid:int,d:dict)->dict:
    async with conn() as c:
        r=await c.fetchrow("""
            INSERT INTO announcements(event_id,title_tr,title_en,message_tr,message_en,ann_type)
            VALUES($1,$2,$3,$4,$5,$6) RETURNING *""",
            eid,d.get("title_tr"),d.get("title_en"),
            d["message_tr"],d.get("message_en",d["message_tr"]),d.get("ann_type","info"))
        return _safe_dict(r)

async def announcement_list(eid:int,limit:int=20)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT * FROM announcements WHERE event_id=$1 ORDER BY created_at DESC LIMIT $2",
            eid,limit)]

# ─── BOT TOKEN ──────────────────────────────────────────────
async def bot_token_save(group_id:str,env_key:str,enc_token:str,bot_id:int,
                         bot_username:str="",event_id:int|None=None):
    async with conn() as c:
        await c.execute("""
            INSERT INTO bot_tokens(group_id,token_env_key,encrypted_token,bot_id,bot_username,event_id,updated_at)
            VALUES($1,$2,$3,$4,$5,$6,NOW())
            ON CONFLICT(group_id) DO UPDATE SET
                token_env_key=$2,encrypted_token=$3,bot_id=$4,bot_username=$5,event_id=$6,updated_at=NOW()""",
            group_id,env_key,enc_token,bot_id,bot_username,event_id)

async def bot_token_get(group_id:str)->dict|None:
    async with conn() as c:
        r=await c.fetchrow("SELECT * FROM bot_tokens WHERE group_id=$1",group_id)
        return _safe_dict(r)

async def bot_token_list()->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("SELECT * FROM bot_tokens ORDER BY group_id")]

async def bot_token_delete(group_id:str):
    async with conn() as c: await c.execute("DELETE FROM bot_tokens WHERE group_id=$1",group_id)

# ─── LEADERBOARD ────────────────────────────────────────────
async def leaderboard(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch("""
            SELECT t.id,t.name,t.xp,t.level,t.attributes,t.badges,
                   t.invite_code,t.telegram_group_name,
                   r.name_tr as role_name,r.name_en as role_name_en,
                   r.emoji as role_emoji,r.color as role_color,
                   COUNT(DISTINCT m.id) as member_count,
                   COUNT(DISTINCT CASE WHEN tc.status='approved' THEN tc.id END) as completed_tasks
            FROM teams t
            LEFT JOIN event_roles r ON t.role_id=r.id
            LEFT JOIN team_members m ON m.team_id=t.id
            LEFT JOIN task_completions tc ON tc.team_id=t.id
            WHERE t.event_id=$1 AND t.status='active'
            GROUP BY t.id,r.name_tr,r.name_en,r.emoji,r.color
            ORDER BY t.xp DESC,t.id""",eid)]

# ─── QUIZLer ────────────────────────────────────────────────
async def quiz_list(eid:int)->list:
    async with conn() as c:
        return [_safe_dict(r) for r in await c.fetch(
            "SELECT q.*,ss.name as stage_name FROM quizzes q "
            "LEFT JOIN scenario_stages ss ON q.stage_id=ss.id "
            "WHERE q.event_id=$1 ORDER BY q.id",eid)]

async def quiz_get(qid:int)->dict|None:
    async with conn() as c:
        q=await c.fetchrow("SELECT * FROM quizzes WHERE id=$1",qid)
        if not q: return None
        qs=await c.fetch("SELECT * FROM quiz_questions WHERE quiz_id=$1 ORDER BY sort_order",qid)
        return dict(q)|{"questions":[_safe_dict(r) for r in qs]}

async def quiz_save(eid:int,d:dict)->dict:
    async with conn() as c:
        if d.get("id"):
            r=await c.fetchrow("""
                UPDATE quizzes SET title_tr=$2,title_en=$3,stage_id=$4,
                    cooldown_minutes=$5,sp_reward=$6,active=$7
                WHERE id=$1 RETURNING *""",
                d["id"],d["title_tr"],d.get("title_en",d["title_tr"]),
                d.get("stage_id"),d.get("cooldown_minutes",60),
                d.get("sp_reward",100),d.get("active",True))
        else:
            r=await c.fetchrow("""
                INSERT INTO quizzes(event_id,title_tr,title_en,stage_id,cooldown_minutes,sp_reward,active)
                VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
                eid,d["title_tr"],d.get("title_en",d["title_tr"]),
                d.get("stage_id"),d.get("cooldown_minutes",60),
                d.get("sp_reward",100),d.get("active",True))
        return _safe_dict(r)

async def quiz_delete(qid:int):
    async with conn() as c: await c.execute("DELETE FROM quizzes WHERE id=$1",qid)

# ─── ESKİ UYUMLULUK (v1.3.x API'leri için) ──────────────────
async def init_v2_schema(): await init_schema()
async def init_bot_token_schema(): pass  # schema.sql içinde
async def bot_token_kaydet(g,e,t,b): await bot_token_save(g,e,t,b)
async def bot_token_getir(g): return await bot_token_get(g)
async def bot_token_listesi(): return await bot_token_list()
async def bot_token_sil(g): await bot_token_delete(g)

# ═══════════════════════════════════════════════════════════
# BOT BRIDGE FONKSIYONLARI — PostgreSQL tabanlı
# (bot.py'nin kullandığı legacy API'yi karşılar)
# ═══════════════════════════════════════════════════════════

async def init_lang_schema():
    """Dil tablosunu başlat."""
    async with conn() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS user_lang (
                telegram_id BIGINT PRIMARY KEY,
                lang TEXT DEFAULT 'tr',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

async def kullanici_dil_getir(tgid: int) -> str:
    async with conn() as c:
        r = await c.fetchrow("SELECT lang FROM user_lang WHERE telegram_id=$1", tgid)
        return r["lang"] if r else "tr"

async def kullanici_dil_ayarla(tgid: int, lang: str):
    async with conn() as c:
        await c.execute("""
            INSERT INTO user_lang(telegram_id,lang) VALUES($1,$2)
            ON CONFLICT(telegram_id) DO UPDATE SET lang=$2,updated_at=NOW()
        """, tgid, lang)

async def takim_getir(tgid: int) -> dict | None:
    """Telegram kullanıcısının takım bilgisini döndürür (bot formatı)."""
    ev = await event_active()
    if not ev:
        async with conn() as c:
            ev_row = await c.fetchrow("SELECT id FROM events ORDER BY id DESC LIMIT 1")
            if not ev_row: return None
            eid = ev_row["id"]
    else:
        eid = ev["id"]
    async with conn() as c:
        r = await c.fetchrow("""
            SELECT t.id, t.name as ad, t.xp, t.attributes as stats, t.badges,
                   t.invite_code, t.telegram_group_id,
                   COALESCE(m.role,'member') as rol,
                   m.id as uye_id, m.telegram_id,
                   m.bp as uye_bp, m.role_id,
                   r.key as rol_key, r.name_tr as rol_adi,
                   r.emoji as rol_emoji,
                   r.base_attributes as rol_stats
            FROM team_members m
            JOIN teams t ON m.team_id=t.id
            LEFT JOIN event_roles r ON m.role_id=r.id
            WHERE m.telegram_id=$1 AND t.event_id=$2
            LIMIT 1
        """, tgid, eid)
        if not r: return None
        d = _safe_dict(r)
        # stats JSON parse
        s = d.get("stats") or {}
        if isinstance(s, str):
            try: import json as _j2; s = _j2.loads(s)
            except: s = {}
        d["stats"] = s
        d["xp"] = d.get("xp") or 0
        return d

async def takim_ada_gore(ad: str) -> dict | None:
    ev = await event_active()
    if not ev:
        async with conn() as c:
            ev_row = await c.fetchrow("SELECT id FROM events ORDER BY id DESC LIMIT 1")
            if not ev_row: return None
            eid = ev_row["id"]
    else:
        eid = ev["id"]
    async with conn() as c:
        r = await c.fetchrow("""
            SELECT t.id, t.name as ad, t.xp, t.attributes as stats, t.badges,
                   COALESCE(r.key,'') as rol, r.emoji as rol_emoji
            FROM teams t LEFT JOIN event_roles r ON t.role_id=r.id
            WHERE lower(t.name)=lower($1) AND t.event_id=$2
        """, ad, eid)
        if not r: return None
        d = _safe_dict(r)
        s = d.get("stats") or {}
        if isinstance(s, str):
            try: import json as _j2; s = _j2.loads(s)
            except: s = {}
        d["stats"] = s
        d["xp"] = d.get("xp") or 0
        return d

async def takim_olustur(tgid: int, username: str, ad: str, stats: dict) -> dict:
    """Takım oluştur ve kullanıcıyı lider olarak ekle."""
    ev = await event_active()
    if not ev:
        async with conn() as c:
            ev_row = await c.fetchrow("SELECT id FROM events ORDER BY id DESC LIMIT 1")
            eid = ev_row["id"] if ev_row else None
    else:
        eid = ev["id"]
    if not eid: return {}
    team = await team_create(eid, {"name": ad})
    await member_add(team["id"], {
        "telegram_id": tgid,
        "username": username,
        "display_name": username,
        "role": "leader",
    })
    return team

async def takim_gruba_ekle(tgid: int, group_key: str):
    """Takımı Telegram grubuna bağlar (group_key = config grubu id'si, şimdilik no-op)."""
    pass

async def rol_guncelle(tgid: int, rol_key: str, stats: dict):
    """Kullanıcının rolünü ve başlangıç niteliklerini güncelle."""
    ev = await event_active()
    eid = ev["id"] if ev else None
    async with conn() as c:
        # role bul
        if eid:
            role_row = await c.fetchrow(
                "SELECT id FROM event_roles WHERE key=$1 AND event_id=$2", rol_key, eid)
            role_id = role_row["id"] if role_row else None
        else:
            role_row = await c.fetchrow("SELECT id FROM event_roles WHERE key=$1", rol_key)
            role_id = role_row["id"] if role_row else None
        # üye güncelle
        if role_id:
            await c.execute("""
                UPDATE team_members SET role_id=$1
                WHERE telegram_id=$2
            """, role_id, tgid)
        # takım stats güncelle
        member = await c.fetchrow(
            "SELECT team_id FROM team_members WHERE telegram_id=$1 LIMIT 1", tgid)
        if member:
            await c.execute(
                "UPDATE teams SET attributes=$1 WHERE id=$2",
                _j(stats), member["team_id"])

async def stats_guncelle(takim_id: int, stats: dict):
    async with conn() as c:
        await c.execute("UPDATE teams SET attributes=$1 WHERE id=$2", _j(stats), takim_id)

async def xp_ekle(takim_id: int, miktar: int, sebep: str = ""):
    await team_add_xp(takim_id, miktar)

async def rozet_ver(takim_id: int, rozet_key: str):
    async with conn() as c:
        await c.execute(
            "UPDATE teams SET badges=array_append(badges,$1) WHERE id=$2 AND NOT ($1=ANY(badges))",
            rozet_key, takim_id)

async def takim_rozetleri(tgid: int) -> list:
    async with conn() as c:
        r = await c.fetchrow("""
            SELECT t.badges FROM teams t
            JOIN team_members m ON m.team_id=t.id
            WHERE m.telegram_id=$1 LIMIT 1
        """, tgid)
        return list(r["badges"] or []) if r else []

async def tamamlanan_gorev_idleri(identifier) -> set:
    """Tamamlanan görev ID'lerini döndürür. identifier: telegram_id veya team_id."""
    async with conn() as c:
        # Önce team_id olarak dene
        rows = await c.fetch("""
            SELECT DISTINCT tc.task_id::text as gid FROM task_completions tc
            JOIN team_members m ON m.team_id=tc.team_id
            WHERE m.telegram_id=$1 AND tc.status='approved'
        """, int(identifier))
        if rows:
            return {r["gid"] for r in rows}
        # team_id olarak dene
        rows2 = await c.fetch("""
            SELECT DISTINCT task_id::text as gid FROM task_completions
            WHERE team_id=$1 AND status='approved'
        """, int(identifier))
        return {r["gid"] for r in rows2}

async def senaryo_durumu_getir() -> dict | None:
    """Aktif senaryonun durumunu döndürür."""
    ev = await event_active()
    if not ev: return None
    async with conn() as c:
        sc = await c.fetchrow(
            "SELECT * FROM scenarios WHERE event_id=$1 AND status='active' LIMIT 1", ev["id"])
        if not sc: return None
        stage = None
        if sc["current_stage_id"]:
            stage = await c.fetchrow(
                "SELECT * FROM scenario_stages WHERE id=$1", sc["current_stage_id"])
        return {
            "scenario_id": str(sc["id"]),
            "name": sc["name"],
            "current_stage": str(sc["current_stage_id"]) if sc["current_stage_id"] else None,
            "stage_name": stage["name"] if stage else None,
            "xp_multiplier": stage["xp_multiplier"] if stage else 1.0,
            "min_tasks": sc.get("min_tasks_required", 1),
        }

async def onay_istegi_olustur(tgid: int, uye_tgid: int, gorev_id_str: str, kanit: str) -> int:
    """Görev tamamlama isteği oluşturur. gorev_id_str → DB task id veya slug."""
    async with conn() as c:
        # Görev bul — önce int dene, sonra title match
        task = None
        try:
            task = await c.fetchrow("SELECT * FROM tasks WHERE id=$1", int(gorev_id_str))
        except (ValueError, TypeError):
            pass
        if not task:
            task = await c.fetchrow(
                "SELECT * FROM tasks WHERE lower(title_tr)=lower($1) OR lower(title_en)=lower($1)",
                gorev_id_str)
        if not task: return 0
        # Takım bul
        team = await c.fetchrow("""
            SELECT t.id FROM teams t
            JOIN team_members m ON m.team_id=t.id
            WHERE m.telegram_id=$1 LIMIT 1
        """, tgid)
        if not team: return 0
        r = await c.fetchrow("""
            INSERT INTO task_completions(task_id,team_id,submitted_by,proof_url,status)
            VALUES($1,$2,$3,$4,'pending') RETURNING id
        """, task["id"], team["id"], tgid, kanit)
        return r["id"] if r else 0

async def onay_istegi_getir(onay_id: int) -> dict | None:
    async with conn() as c:
        r = await c.fetchrow("""
            SELECT tc.*,
                   COALESCE(t.title_tr,t.title_en,'') as gorev_baslik,
                   t.id as gorev_db_id,
                   t.title_tr, t.title_en, t.sp_reward,
                   t.task_type, t.difficulty,
                   t.attribute_rewards,
                   t.rpg_attr_switches,
                   t.scenario_id as task_scenario_id,
                   tm.id as takim_id, tm.name as takim_adi
            FROM task_completions tc
            JOIN tasks t ON tc.task_id=t.id
            JOIN teams tm ON tc.team_id=tm.id
            WHERE tc.id=$1
        """, onay_id)
        if not r: return None
        d = _safe_dict(r)
        d["gorev_id"] = str(d.get("gorev_db_id") or d.get("task_id"))
        return d

async def gorev_onayla(onay_id: int, takim_id: int, uye_tgid: int,
                        task_id_str: str, xp: int):
    """Bot tarafı onay — merkezi completion_review fonksiyonunu kullanır."""
    result = await completion_review(onay_id, "approved", "bot", "")
    return result
async def gorev_reddet(onay_id: int):
    async with conn() as c:
        await c.execute("""
            UPDATE task_completions SET status='rejected', reviewed_at=NOW()
            WHERE id=$1
        """, onay_id)

async def duel_kaydet(cid: int, did: int, wid: int, cs: float, ds: float, xp: int):
    pass  # Opsiyonel log

async def jury_puan_kaydet(takim_id: int, jury_tgid: int, kriter: str, puan: float):
    ev = await event_active()
    eid = ev["id"] if ev else 1
    await jury_score_save(eid, takim_id, kriter, puan, jury_tgid)

async def jury_ortalama_puan(takim_id: int) -> dict:
    async with conn() as c:
        rows = await c.fetch("""
            SELECT criterion, AVG(score) as avg_score
            FROM jury_scores WHERE team_id=$1
            GROUP BY criterion
        """, takim_id)
        return {r["criterion"]: round(r["avg_score"], 1) for r in rows}

async def liderlik_tablosu(limit: int = 10) -> list:
    """BP bazlı liderlik tablosu — bot formatı."""
    ev = await event_active()
    if not ev:
        async with conn() as c:
            ev_row = await c.fetchrow("SELECT id FROM events ORDER BY id DESC LIMIT 1")
            eid = ev_row["id"] if ev_row else None
    else:
        eid = ev["id"]
    if not eid: return []
    async with conn() as c:
        rows = await c.fetch("""
            SELECT t.id, t.name as ad, t.xp as bp, t.xp,
                   t.attributes as stats, t.badges,
                   COALESCE(r.key,'') as rol,
                   r.emoji as rol_emoji, r.name_tr as rol_adi,
                   COUNT(DISTINCT m.id) as uye_sayisi,
                   COUNT(DISTINCT CASE WHEN tc.status='approved' THEN tc.id END) as tamamlanan
            FROM teams t
            LEFT JOIN event_roles r ON t.role_id=r.id
            LEFT JOIN team_members m ON m.team_id=t.id
            LEFT JOIN task_completions tc ON tc.team_id=t.id
            WHERE t.event_id=$1 AND t.status='active'
            GROUP BY t.id,r.key,r.emoji,r.name_tr
            ORDER BY t.xp DESC LIMIT $2
        """, eid, limit)
        return [_safe_dict(r) for r in rows]

async def grup_takimlari(group_key: str) -> list:
    """Grup scope için liderlik — şimdilik global döndür."""
    return await liderlik_tablosu(10)

async def uye_bp_listesi(takim_id: int) -> list:
    """Takım üyelerinin rol bazlı BP özetini döndürür."""
    async with conn() as c:
        rows = await c.fetch("""
            SELECT m.telegram_id, m.display_name, m.username,
                   COALESCE(r.name_tr,'?') as rol_adi,
                   r.emoji as rol_emoji,
                   COALESCE(m.bp,0) as bp,
                   COALESCE(SUM(bl.bp_earned),0) as toplam_katki
            FROM team_members m
            LEFT JOIN event_roles r ON m.role_id=r.id
            LEFT JOIN member_bp_log bl ON bl.member_id=m.id
            WHERE m.team_id=$1
            GROUP BY m.id, r.name_tr, r.emoji
            ORDER BY COALESCE(m.bp,0) DESC
        """, takim_id)
        return [_safe_dict(r) for r in rows]

async def aktif_gorev_listesi(eid: int | None = None) -> list:
    """Aktif senaryo + aktif görevleri döndürür (bot /tasks için)."""
    if not eid:
        ev = await event_active()
        if not ev:
            async with conn() as c:
                ev_row = await c.fetchrow("SELECT id FROM events ORDER BY id DESC LIMIT 1")
                eid = ev_row["id"] if ev_row else None
        else:
            eid = ev["id"]
    if not eid: return []
    async with conn() as c:
        # Aktif senaryo var mı?
        active_sc = await c.fetchrow(
            "SELECT id FROM scenarios WHERE event_id=$1 AND status='active' LIMIT 1", eid)
        if active_sc:
            # Sadece bu senaryoya bağlı aktif görevler
            rows = await c.fetch("""
                SELECT t.*, COALESCE(t.title_tr,t.title_en,'') as title,
                       COALESCE(t.description_tr,t.description_en,'') as description,
                       sc.name as senaryo_adi
                FROM tasks t
                JOIN scenarios sc ON t.scenario_id=sc.id
                WHERE t.event_id=$1 AND t.scenario_id=$2 AND t.active=TRUE
                ORDER BY t.sort_order, t.id
            """, eid, active_sc["id"])
        else:
            # Senaryosuz ya da tüm aktif görevler
            rows = await c.fetch("""
                SELECT t.*, COALESCE(t.title_tr,t.title_en,'') as title,
                       COALESCE(t.description_tr,t.description_en,'') as description
                FROM tasks t
                WHERE t.event_id=$1 AND t.active=TRUE
                ORDER BY t.sort_order, t.id
            """, eid)
        return [_safe_dict(r) for r in rows]
