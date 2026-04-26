"""core/game_engine.py — ALEV v2 Oyun Motoru"""
from __future__ import annotations
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from core.config_loader import GameConfig, TaskConfig, ScenarioConfig, StageConfig

@dataclass
class XPResult:
    base_xp:int; final_xp:int; bonus_applied:bool; bonus_multiplier:float
    level_before:int; level_after:int; leveled_up:bool; level_reward_xp:int
    badge_earned:str|None; attr_changes:dict; unlocked_tasks:list; unlocked_badges:list; unlocked_features:list

@dataclass
class DuelResult:
    challenger_id:int; defender_id:int; winner_id:int; loser_id:int
    challenger_score:float; defender_score:float; sp_reward:int; badge_earned:str|None
    winner_attr_changes:dict; loser_attr_changes:dict

@dataclass
class JuryScoreResult:
    team_id:int; total_score:float; criterion_scores:dict; xp_equivalent:int; attr_changes:dict

@dataclass
class StageAdvanceResult:
    scenario_id:str; from_stage:StageConfig|None; to_stage:StageConfig|None
    is_final:bool; announcement_tr:str; announcement_en:str; xp_bonus:int

class AttributeEngine:
    def __init__(self, cfg:GameConfig): self.cfg=cfg

    def apply_action(self, action_type:str, current_stats:dict, task_type:str="", jury_score:float=0.0, stage_mult:float=1.0) -> dict:
        new = dict(current_stats)
        if action_type=="jury_score":
            ae = self.cfg.actions.effects.get("jury_score")
            if ae:
                d = int((jury_score - ae.base_score)*ae.scale*stage_mult)
                for a in self.cfg.team_attributes: new[a] = new.get(a,0)+d
        else:
            raw = self.cfg.actions.get_effects(action_type, task_type)
            for attr,delta in raw.items():
                ac = self.cfg.team_attributes.get(attr)
                if ac:
                    v = new.get(attr,ac.default)+int(delta*stage_mult)
                    new[attr] = max(ac.min, min(ac.max, v))
        return new

    def compute_changes(self, old:dict, new:dict) -> dict:
        return {k:new[k]-old.get(k,0) for k in new if new[k]!=old.get(k,0)}

    def check_unlocks(self, stats:dict): return self.cfg.actions.check_unlocks(stats)

    def radar_data(self, stats:dict) -> list:
        return [{"key":k,"label":a.display_name,"emoji":a.emoji,"value":stats.get(k,a.default),
                 "max":a.max,"pct":round((stats.get(k,a.default)/a.max)*100) if a.max else 0}
                for k,a in self.cfg.team_attributes.items()]

class ScenarioEngine:
    def __init__(self, cfg:GameConfig): self.cfg=cfg

    def current_multiplier(self, stage_id:str|None) -> float:
        sc=self.cfg.active_scenario()
        if not sc or not stage_id: return 1.0
        s=sc.stage(stage_id); return s.xp_multiplier if s else 1.0

    def advance_stage(self, scenario_id:str, current_stage_id:str|None) -> StageAdvanceResult:
        sc=self.cfg.scenario(scenario_id)
        if not sc:
            return StageAdvanceResult(scenario_id,None,None,True,"Senaryo yok.","No scenario.",0)
        from_s=sc.stage(current_stage_id) if current_stage_id else None
        to_s=sc.next_stage(current_stage_id) if current_stage_id else (sc.stages[0] if sc.stages else None)
        if to_s:
            atr=f"🔥 *{to_s.name}* başladı!\n{to_s.description.strip()}"
            ate=f"🔥 *{to_s.name}* started!\n{to_s.description.strip()}"; xpb=100
        elif from_s and from_s.is_final:
            atr=from_s.completion_message_tr; ate=from_s.completion_message_en; xpb=200
        else:
            atr="Aşamalar tamamlandı."; ate="All stages complete."; xpb=0
        return StageAdvanceResult(scenario_id,from_s,to_s,to_s is None,atr,ate,xpb)

class JuryEngine:
    def __init__(self, cfg:GameConfig): self.cfg=cfg; self.jury=cfg.jury

    def is_jury_member(self, uid:int) -> bool: return uid in self.jury.members

    def calculate_score(self, team_id:int, team_xp:int, team_stats:dict, jury_scores:dict) -> JuryScoreResult:
        weighted=self.jury.weighted_score(jury_scores)
        xp_n=min(100,(team_xp/5000)*100)
        final=xp_n*self.jury.xp_weight+weighted*self.jury.jury_weight
        xp_eq=max(0,int(weighted*5))
        d=int((weighted-50)/10)
        attr_ch={"guc":d,"cevre_puani":max(0,d)} if d else {}
        return JuryScoreResult(team_id,round(final,2),jury_scores,xp_eq,attr_ch)

    def format_scores(self, scores:dict, lang="tr") -> str:
        return "\n".join(f"{c.emoji} {c.name(lang)}: *{scores.get(c.id,'—')}*" for c in self.jury.criteria)

class GameEngine:
    def __init__(self, cfg:GameConfig):
        self.cfg=cfg; self.attr=AttributeEngine(cfg)
        self.scenario=ScenarioEngine(cfg); self.jury_engine=JuryEngine(cfg)

    def calculate_xp(self, task:TaskConfig, role_key:str, current_xp:int,
                     current_stats:dict, event_mult:float=1.0, stage_mult:float=1.0) -> XPResult:
        role=self.cfg.role(role_key); base=task.sp_reward; mult=event_mult*stage_mult; bonus=False
        if role and task.type in role.bonus_task_types: mult*=role.bonus_multiplier; bonus=True
        if mult!=1.0: bonus=True
        final=int(base*mult)
        lb=self.cfg.level_for_xp(current_xp); new_xp=current_xp+final; la=self.cfg.level_for_xp(new_xp)
        lu=la>lb; lrew=self.cfg.leveling.level_rewards.get(la,0) if lu else 0
        new_s=self.attr.apply_action("task_complete",current_stats,task.type,stage_mult=stage_mult)
        changes=self.attr.compute_changes(current_stats,new_s)
        unlocked=self.attr.check_unlocks(new_s)
        return XPResult(base,final,bonus,mult,lb,la,lu,lrew,task.badge_reward,changes,
            [tid for r in unlocked for tid in r.unlocks.get("task_ids",[])],
            [bid for r in unlocked for bid in r.unlocks.get("badge_ids",[])],
            [r.unlocks["feature"] for r in unlocked if "feature" in r.unlocks])

    def resolve_duel(self, cid:int, cxp:int, cst:dict, did:int, dxp:int, dst:dict, win_xp:int=100) -> DuelResult:
        cs=cxp*0.6+random.random()*cxp*0.4; ds=dxp*0.6+random.random()*dxp*0.4
        wid=cid if cs>=ds else did; lid=did if wid==cid else cid
        ws=cst if wid==cid else dst; ls=dst if wid==cid else cst
        wn=self.attr.apply_action("duel_win",ws); ln=self.attr.apply_action("duel_lose",ls)
        return DuelResult(cid,did,wid,lid,round(cs,1),round(ds,1),win_xp,
            "duel_sampiyon" if wid==cid else None,
            self.attr.compute_changes(ws,wn),self.attr.compute_changes(ls,ln))

    def get_active_event_multiplier(self, task_type:str) -> float:
        now=datetime.now(timezone.utc); best=1.0
        for e in self.cfg.events:
            if e.type!="bonus_sp" or e.bonus_task_type!=task_type: continue
            try:
                s=datetime.fromisoformat(e.scheduled_at).astimezone(timezone.utc)
                if s.timestamp()<=now.timestamp()<=s.timestamp()+e.duration_minutes*60:
                    best=max(best,e.bonus_multiplier)
            except: pass
        return best

    def format_xp_bar(self, xp:int, width:int=10) -> str:
        lv=self.cfg.level_for_xp(xp); nx=self.cfg.xp_for_next_level(lv)
        px=(lv-1)*self.cfg.leveling.xp_per_level; p=(xp-px)/max(1,nx-px)
        f=int(p*width); return "█"*f+"░"*(width-f)

    def format_stats(self, stats:dict) -> str:
        lines=[]
        for k,v in stats.items():
            a=self.cfg.team_attributes.get(k)
            if a: lines.append(f"{a.emoji} {a.display_name}: `{'▰'*min(v,10)+'▱'*max(0,10-v)}` {v}/{a.max}")
        return "\n".join(lines)

    def format_role(self, role_key:str) -> str:
        r=self.cfg.role(role_key); return f"{r.emoji} {r.display_name}" if r else "?"

    def format_attr_changes(self, changes:dict) -> str:
        if not changes: return ""
        parts=[]
        for k,d in changes.items():
            a=self.cfg.team_attributes.get(k)
            if a: parts.append(f"{a.emoji} {'+' if d>=0 else ''}{d}")
        return " · ".join(parts)
