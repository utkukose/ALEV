from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from web.auth import get_admin
import core.db as db

router = APIRouter(tags=["teams"])

@router.get("/event/{eid}")
async def list_teams(eid:int,_=Depends(get_admin)):
    return await db.team_list(eid)

@router.post("/event/{eid}")
async def create_team(eid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    if not d.get("name"):
        return JSONResponse({"ok":False,"error":"Ad gerekli"},400)
    r=await db.team_create(eid,d)
    return {"ok":True,"team":r}

@router.get("/{tid}")
async def get_team(tid:int,_=Depends(get_admin)):
    t=await db.team_get(tid)
    if not t: return JSONResponse({"error":"bulunamadi"},404)
    t["history"]=await db.completion_history(tid)
    return t

@router.put("/{tid}")
async def update_team(tid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    r=await db.team_update(tid,d)
    return {"ok":bool(r),"team":r}

@router.delete("/{tid}")
async def delete_team(tid:int,_=Depends(get_admin)):
    await db.team_delete(tid)
    return {"ok":True}

@router.post("/{tid}/xp")
async def add_xp(tid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    xp=int(d.get("xp",0))
    reason=d.get("reason","Admin düzenleme")
    if xp==0: return JSONResponse({"ok":False,"error":"Miktar 0 olamaz"},400)
    if xp>0:
        await db.team_add_xp(tid,xp,None)
    else:
        # Negatif: BP çıkar
        async with db.conn() as c:
            await c.execute(
                "UPDATE teams SET xp=GREATEST(0,xp+$1) WHERE id=$2", xp, tid)
    return {"ok":True,"bp_change":xp,"reason":reason}

@router.get("/{tid}/members")
async def list_members(tid:int, request:Request):
    # Admin veya o takımın profil oturumu açık olan kullanıcı erişebilir
    from web.auth import verify_token
    admin_token = request.cookies.get("admin_token")
    profile_teamid = int(request.cookies.get("profile_teamid","0") or 0)
    is_admin = admin_token and verify_token(admin_token)
    is_own_team = profile_teamid == tid
    if not is_admin and not is_own_team:
        from fastapi.responses import JSONResponse as _JR
        return _JR({"ok": False, "error": "Yetkisiz"}, 403)
    return await db.member_list(tid)

@router.post("/{tid}/members")
async def add_member(tid:int,request:Request):
    d=await request.json()
    if not d.get("telegram_id"):
        return JSONResponse({"ok":False,"error":"telegram_id gerekli"},400)
    # Zaten üye mi kontrol et
    team=await db.team_get(tid)
    if not team:
        return JSONResponse({"ok":False,"error":"Takım bulunamadı"},404)
    existing=await db.member_list(tid)
    already=[m for m in existing if m.get("telegram_id")==int(d["telegram_id"])]
    if already:
        return JSONResponse({"ok":False,"error":"Bu Telegram ID zaten bu takımda kayıtlı.","error_en":"This Telegram ID is already a member of this team."},409)
    r=await db.member_add(tid,d)
    return {"ok":True,"member":r}

@router.delete("/{tid}/members/{tgid}")
async def remove_member(tid:int,tgid:int,_=Depends(get_admin)):
    await db.member_remove(tid,tgid)
    return {"ok":True}

@router.post("/{tid}/regen-code")
async def regen_code(tid:int,_=Depends(get_admin)):
    code=await db.team_regen_code(tid)
    return {"ok":True,"invite_code":code}

@router.get("/{tid}/qr")
async def get_qr(tid:int,request:Request,_=Depends(get_admin)):
    t=await db.team_get(tid)
    if not t: return JSONResponse({"ok":False},404)
    try:
        import qrcode,io,base64
        url=str(request.base_url).rstrip("/")+"/onboard?code="+t["invite_code"]
        qr=qrcode.make(url)
        buf=io.BytesIO(); qr.save(buf,format="PNG")
        data="data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
        return {"ok":True,"url":url,"qr_data":data}
    except Exception as e:
        return JSONResponse({"ok":False,"error":str(e)},500)

@router.post("/completions/{cid}/review")
async def review_completion(cid:int,request:Request,_=Depends(get_admin)):
    d=await request.json()
    # completion_review SP, rol bonusu ve RPG'yi halleder
    r=await db.completion_review(cid,d["status"],"admin",d.get("note",""))
    if not r:
        return JSONResponse({"ok":False,"error":"Completion bulunamadı"},404)

    if d["status"]=="approved":
        # Limit aşıldıysa bildir
        if r.get("rejected_reason")=="limit_exceeded":
            return {"ok":False,"error":"Kişi başı görev limitine ulaşıldı","result":r}

        submitter_tgid=r.get("submitted_by")
        total_sp=r.get("total_sp") or r.get("sp_reward") or 0
        bonus_sp=r.get("bonus_sp") or 0
        attrs=r.get("attribute_rewards") or {}
        if not isinstance(attrs,dict): attrs={}

        # Takım ve görev bilgisi
        team=await db.team_get(r["team_id"])
        task=await db.task_get(r["task_id"])

        # Telegram bildirimleri
        await _notify_own_team(team,task,r,total_sp,attrs,1.0,"","",submitter_tgid,bonus_sp)
        await _notify_other_teams(team,task,r)

        # Senaryo tamamlama kontrolü
        try:
            eid=r.get("event_id")
            if not eid and task: eid=task.get("event_id")
            if eid:
                sc_result=await db.check_scenario_completion(r["task_id"],r["team_id"],eid)
                if sc_result and sc_result.get("triggered"):
                    await _notify_scenario_bonus(sc_result,eid)
        except Exception as se:
            import logging; logging.getLogger(__name__).warning("Senaryo: "+str(se))

    # Senaryo tamamlama bildirimi
    if d["status"] == "approved":
        try:
            sc_result = r.get("_sc_result") if r else None
        except Exception:
            pass

    # Görev red bildirimi — submit eden kullanıcıya bildir
    if d["status"] == "rejected":
        try:
            submitter_tgid = r.get("submitted_by") if r else None
            if submitter_tgid:
                tok = await _get_token_and_send(r["team_id"])
                if tok:
                    task2 = await db.task_get(r["task_id"]) if r else None
                    title2 = (task2 or {}).get("title_tr") or "?"
                    note2 = d.get("note","")
                    lang2 = "tr"
                    try:
                        ev2 = await db.event_get((task2 or {}).get("event_id",0))
                        lang2 = (ev2 or {}).get("language","tr") or "tr"
                    except Exception:
                        pass
                    from core.bot_handler import notify_rejection
                    await notify_rejection(tok, submitter_tgid, title2, note2, lang2)
        except Exception as re2:
            import logging; logging.getLogger(__name__).warning(f"Red bildirimi: {re2}")

    return {"ok":True,"result":r}


async def _get_token_and_send(team_id):
    """Takım grubuna göndermek için token ve group_id döndür."""
    team=await db.team_get(team_id)
    if not team or not team.get("telegram_group_id"):
        return None,None,None
    tokens=await db.bot_token_list()
    if not tokens:
        return None,None,None
    from core.bot_registry import TokenCipher
    from core.bot_handler import send
    import os
    cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
    tok=cipher.decrypt(tokens[0]["encrypted_token"])
    tgid=team["telegram_group_id"]
    if isinstance(tgid,str): tgid=int(tgid)
    return tok,tgid,team


async def _notify_own_team(team,task,r,xp,attrs,role_mult,role_name,role_emoji,submitter_tgid,bonus_sp=0):
    """Kendi takım grubuna detaylı bildirim."""
    try:
        if not team or not team.get("telegram_group_id"): return
        tokens=await db.bot_token_list()
        if not tokens: return
        from core.bot_registry import TokenCipher
        from core.bot_handler import send
        import os
        cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
        tok=cipher.decrypt(tokens[0]["encrypted_token"])
        tgid=team["telegram_group_id"]
        if isinstance(tgid,str): tgid=int(tgid)

        # Gönderen üyeyi bul
        members=await db.member_list(team["id"])
        submitter=next((m for m in members if m.get("telegram_id")==submitter_tgid),None)
        submitter_name=submitter.get("display_name","?") if submitter else "?"

        task_title=task.get("title_tr","Gorev") if task else "Gorev"

        # Nitelik kazanımları
        attr_lines=[]
        for k,v in attrs.items():
            if v and v>0:
                earned=int(v*role_mult)
                if role_mult!=1.0:
                    attr_lines.append(f"  +{earned} {k} ({v}x{role_mult:.1f})")
                else:
                    attr_lines.append(f"  +{earned} {k}")

        new_team=await db.team_get(team["id"])
        new_xp=new_team["xp"] if new_team else team["xp"]

        lines=[
            f"GOREV ONAYLANDI!",
            f"Gorev: {task_title}",
            f"Tamamlayan: {submitter_name}" +
            (f" ({role_emoji} {role_name})" if role_name else ""),
            f"+{xp} BP",
        ]
        if attr_lines:
            lines.append("Nitelik kazanimlari:")
            lines.extend(attr_lines)
        lines.append(f"Takim toplam BP: {new_xp:,}")

        await send(tok,tgid,"\n".join(lines))
    except Exception as e:
        import logging; logging.getLogger(__name__).warning("own_notify: "+str(e))


async def _notify_other_teams(team,task,r):
    """Diğer takımlara kısa bildirim."""
    try:
        if not team: return
        tokens=await db.bot_token_list()
        if not tokens: return
        from core.bot_registry import TokenCipher
        from core.bot_handler import send
        import os
        cipher=TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
        tok=cipher.decrypt(tokens[0]["encrypted_token"])

        eid=r.get("event_id") or team.get("event_id")
        if not eid: return
        all_teams=await db.team_list(eid)
        task_title=task.get("title_tr","Gorev") if task else "Gorev"
        msg=f"{team['name']} takimi '{task_title}' gorevini tamamladi!"

        for t in all_teams:
            if t["id"]==team["id"]: continue
            if not t.get("telegram_group_id"): continue
            try:
                tgid=t["telegram_group_id"]
                if isinstance(tgid,str): tgid=int(tgid)
                await send(tok,tgid,msg)
            except Exception:
                pass
    except Exception as e:
        import logging; logging.getLogger(__name__).warning("other_notify: "+str(e))


async def _notify_scenario_bonus(sc, eid):
    """Senaryo tamamlanınca kendi grubuna + diğerlerine bildir."""
    try:
        tokens = await db.bot_token_list()
        if not tokens: return
        from core.bot_registry import TokenCipher
        from core.bot_handler import notify_scenario_complete, send as bot_send
        import os
        cipher = TokenCipher(os.getenv("TOKEN_ENCRYPTION_KEY",""))
        tok = cipher.decrypt(tokens[0]["encrypted_token"])
        team = await db.team_get(sc["team_id"])
        if not team: return
        # Dil
        lang = "tr"
        try:
            ev = await db.event_get(eid)
            lang = (ev or {}).get("language","tr") or "tr"
        except Exception:
            pass
        bp = "BP" if lang=="tr" else "SP"
        rank = sc["rank"]
        bonus = sc["bonus_sp"]
        badge = sc.get("badge","")
        scenario_name = sc.get("scenario_name","")
        # Kendi grubuna detaylı bildirim
        tg_gid = team.get("telegram_group_id")
        if tg_gid:
            if isinstance(tg_gid, str): tg_gid = int(tg_gid)
            await notify_scenario_complete(tok, tg_gid, scenario_name, rank, bonus, badge, lang)
        # Diğer takımların gruplarına kısa duyuru
        all_teams = await db.team_list(eid)
        for other in all_teams:
            if other["id"] == team["id"]: continue
            other_gid = other.get("telegram_group_id")
            if other_gid:
                if isinstance(other_gid, str): other_gid = int(other_gid)
                await bot_send(tok, other_gid,
                    f"🏆 <b>{team['name']}</b> — <b>{scenario_name}</b> senaryosunu tamamladı! "
                    f"(#{rank}. tamamlayan)")
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"notify_scenario_bonus: {e}")

async def edit_team(tid:int, request:Request, _=Depends(get_admin)):
    import logging; _log = logging.getLogger(__name__)
    d = await request.json()
    _log.info(f"[EDIT TEAM] tid={tid} data={d}")
    name = d.get("name","").strip()
    if not name:
        return JSONResponse({"ok":False,"error":"name gerekli"},400)
    tgid = d.get("telegram_group_id")
    if tgid is not None:
        try: tgid = int(tgid)
        except: tgid = None
    tgname = d.get("telegram_group_name") or None
    _log.info(f"[EDIT TEAM] tgid={tgid} tgname={tgname}")
    async with db.conn() as c:
        await c.execute(
            "UPDATE teams SET name=$2, telegram_group_id=$3, telegram_group_name=$4 WHERE id=$1",
            tid, name, tgid, tgname
        )
    return {"ok":True}

@router.patch("/{tid}/telegram-group")
async def update_tg_group(tid:int, request:Request, _=Depends(get_admin)):
    d = await request.json()
    gid = d.get("telegram_group_id")
    if not gid:
        return JSONResponse({"ok":False,"error":"telegram_group_id gerekli"},400)
    async with db.conn() as c:
        await c.execute(
            "UPDATE teams SET telegram_group_id=$1 WHERE id=$2",
            int(gid), tid)
    return {"ok":True}

# ─── Completions ─────────────────────────────────────────
@router.get("/event/{eid}/completions")
async def list_completions(eid:int, status:str="pending", _=Depends(get_admin)):
    async with db.conn() as c:
        rows = await c.fetch(
            "SELECT tc.id, tc.status, tc.submitted_by, tc.sp_awarded,"
            " tc.submitted_at, tc.proof_url,"
            " COALESCE(t.title_tr,t.title_en,'') as title,"
            " tm.name as team_name, tm.id as team_id"
            " FROM task_completions tc"
            " JOIN tasks t ON tc.task_id=t.id"
            " JOIN teams tm ON tc.team_id=tm.id"
            " WHERE t.event_id=$1 AND tc.status=$2"
            " ORDER BY tc.submitted_at DESC",
            eid, status)
        return [db._safe_dict(r) for r in rows]

@router.get("/event/{eid}/pending-count")
async def pending_count(eid:int, _=Depends(get_admin)):
    async with db.conn() as c:
        cnt = await c.fetchval(
            "SELECT COUNT(*) FROM task_completions tc"
            " JOIN tasks t ON tc.task_id=t.id"
            " WHERE t.event_id=$1 AND tc.status='pending'",
            eid)
        return {"count": cnt or 0}

# ─── Aksiyon Logu ────────────────────────────────────────
@router.get("/log")
async def team_log(event_id: int, team_id: int | None = None, _=Depends(get_admin)):
    """Görev tamamlama loglarını döndürür."""
    
    async with db.conn() as c:
        q = """
            SELECT tc.id, tc.status, tc.submitted_by, tc.sp_awarded,
                   tc.submitted_at, tc.reviewed_at, tc.review_note,
                   COALESCE(t.title_tr, t.title_en, '') as task_title,
                   tm.name as team_name, tm.id as team_id
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            JOIN teams tm ON tc.team_id = tm.id
            WHERE t.event_id = $1
        """
        params = [event_id]
        if team_id:
            q += " AND tc.team_id = $2"
            params.append(team_id)
        q += " ORDER BY tc.submitted_at DESC LIMIT 100"
        rows = await c.fetch(q, *params)
        return [db._safe_dict(r) for r in rows]


@router.post("/completions/{cid}/cancel")
async def cancel_completion(cid: int, _=Depends(get_admin)):
    """Onaylanmış bir tamamlamayı iptal eder ve BP'yi geri alır."""
    
    async with db.conn() as c:
        tc = await c.fetchrow("""
            SELECT tc.*, t.sp_reward FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            WHERE tc.id = $1
        """, cid)
        if not tc:
            return JSONResponse({"ok": False, "error": "Bulunamadı"}, 404)
        was_approved = tc["status"] == "approved"
        await c.execute(
            "UPDATE task_completions SET status='cancelled', reviewed_at=NOW() WHERE id=$1", cid)
        if was_approved and tc.get("sp_awarded"):
            await c.execute(
                "UPDATE teams SET xp=GREATEST(0,xp-$1) WHERE id=$2",
                tc["sp_awarded"], tc["team_id"])
            # Üye BP log'undaki ilgili kayıtları da geri al
            await c.execute("""
                UPDATE team_members SET bp=GREATEST(0,bp-(
                    SELECT COALESCE(SUM(bp_earned),0) FROM member_bp_log
                    WHERE completion_id=$1 AND member_id=team_members.id
                )) WHERE team_id=$2
            """, cid, tc["team_id"])
            await c.execute(
                "DELETE FROM member_bp_log WHERE completion_id=$1", cid)
        return {"ok": True, "bp_reclaimed": tc.get("sp_awarded", 0) if was_approved else 0}
