"""
core/config_loader.py — ALEV v2 Config Yükleyici
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

CONFIG_DIR = Path(os.getenv("ALEV_CONFIG_DIR", "config"))

def _load(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# ── Brand ─────────────────────────────────────────────────
@dataclass
class BrandConfig:
    name: str; full_name: str; tagline_tr: str; tagline_en: str
    version: str; color_primary: str; color_secondary: str; color_accent: str
    repo_url: str; docs_url: str; support_email: str
    projection_ticker_tr: str; projection_ticker_en: str
    bot_description_tr: str; bot_description_en: str

    def tagline(self, lang="tr"): return self.tagline_tr if lang=="tr" else self.tagline_en

# ── Roles ─────────────────────────────────────────────────
@dataclass
class RoleConfig:
    key: str; display_name: str; emoji: str; description: str; color: str
    bonus_task_types: list[str]; bonus_multiplier: float
    stats: dict[str,int]; max_members: int; unlocks_at_level: int

@dataclass
class LevelingConfig:
    xp_per_level: int; max_level: int; level_rewards: dict[int,int]

# ── Tasks ─────────────────────────────────────────────────
@dataclass
class TaskConfig:
    id: str; title: str; description: str; type: str; difficulty: str
    xp_reward: int; badge_reward: str|None; stat_rewards: dict[str,int]
    proof_type: str; active: bool; starts_at: str|None; ends_at: str|None
    task_set: str = "default"

# ── Events ────────────────────────────────────────────────
@dataclass
class EventConfig:
    id: str; title: str; type: str; description: str; scheduled_at: str
    duration_minutes: int; announcement_channel: bool; xp_reward: int
    bonus_task_type: str|None = None; bonus_multiplier: float = 1.0

# ── Attributes & Badges ───────────────────────────────────
@dataclass
class AttributeConfig:
    key: str; display_name: str; emoji: str; description: str
    min: int; max: int; default: int

@dataclass
class BadgeConfig:
    key: str; display_name: str; emoji: str; description: str; rarity: str

# ── Groups ────────────────────────────────────────────────
@dataclass
class TeamGroupConfig:
    id: str; chat_id: int; name: str; bot_token_env: str
    task_set: str; leaderboard_scope: str; active: bool

    @property
    def bot_token(self): return os.getenv(self.bot_token_env, "")

@dataclass
class GroupEcosystem:
    org_chat_id: int; org_name: str; org_bot_token_env: str
    jury_chat_id: int; jury_name: str; jury_bot_token_env: str
    team_groups: list[TeamGroupConfig]
    global_leaderboard: bool; local_leaderboard: bool; cross_group_duel: bool

    def get_group(self, gid): return next((g for g in self.team_groups if g.id==gid), None)
    def active_groups(self): return [g for g in self.team_groups if g.active]

    @property
    def org_bot_token(self): return os.getenv(self.org_bot_token_env, "")
    @property
    def jury_bot_token(self): return os.getenv(self.jury_bot_token_env, "")

# ── Actions ───────────────────────────────────────────────
@dataclass
class ActionEffect:
    action_type: str; description: str
    global_effects: dict[str,int]
    by_task_type: dict[str,dict[str,int]]
    base_score: int = 50; scale: float = 0.1

@dataclass
class UnlockRule:
    id: str; description: str; condition: dict; unlocks: dict

    def is_satisfied(self, stats: dict[str,int]) -> bool:
        c = self.condition
        if "all_attributes_min" in c:
            return all(v >= c["all_attributes_min"] for v in stats.values())
        attr = c.get("attribute"); op = c.get("operator",">="); val = c.get("value",0)
        cur = stats.get(attr, 0)
        return {">=":cur>=val,">":cur>val,"==":cur==val,"<=":cur<=val,"<":cur<val}.get(op,False)

@dataclass
class ActionConfig:
    effects: dict[str,ActionEffect]; unlock_rules: list[UnlockRule]

    def get_effects(self, action_type: str, task_type: str = "") -> dict[str,int]:
        result: dict[str,int] = {}
        ae = self.effects.get(action_type)
        if not ae: return result
        for k,v in ae.global_effects.items(): result[k] = result.get(k,0) + v
        if task_type and task_type in ae.by_task_type:
            for k,v in ae.by_task_type[task_type].items(): result[k] = result.get(k,0) + v
        return result

    def check_unlocks(self, stats: dict[str,int]) -> list[UnlockRule]:
        return [r for r in self.unlock_rules if r.is_satisfied(stats)]

# ── Scenarios ─────────────────────────────────────────────
@dataclass
class StageConfig:
    id: str; name: str; description: str; order: int; duration_minutes: int
    starts_at: str|None; task_set: str; xp_multiplier: float
    completion_message_tr: str; completion_message_en: str
    unlock_next_on: str; is_final: bool = False

    def completion_message(self, lang="tr"):
        return self.completion_message_tr if lang=="tr" else self.completion_message_en

@dataclass
class ScenarioConfig:
    id: str; name: str; description: str; active: bool
    auto_advance: bool; announce_to_all_groups: bool
    stages: list[StageConfig]

    def stage(self, sid): return next((s for s in self.stages if s.id==sid), None)
    def next_stage(self, current_id):
        cur = self.stage(current_id)
        if not cur: return None
        return next((s for s in self.stages if s.order==cur.order+1), None)

# ── Jury ──────────────────────────────────────────────────
@dataclass
class JuryCriterion:
    id: str; name_tr: str; name_en: str; weight: float; emoji: str
    def name(self, lang="tr"): return self.name_tr if lang=="tr" else self.name_en

@dataclass
class JuryConfig:
    enabled: bool; xp_weight: float; jury_weight: float
    members: list[int]; criteria: list[JuryCriterion]
    score_min: int; score_max: int; allow_update: bool; anonymous: bool

    def criterion(self, cid): return next((c for c in self.criteria if c.id==cid), None)
    def weighted_score(self, scores: dict[str,float]) -> float:
        return round(sum(scores.get(c.id,0)*c.weight for c in self.criteria), 2)

# ── Ana GameConfig ────────────────────────────────────────
@dataclass
class GameConfig:
    brand: BrandConfig; roles: dict[str,RoleConfig]; leveling: LevelingConfig
    tasks: list[TaskConfig]; events: list[EventConfig]
    team_attributes: dict[str,AttributeConfig]; member_attributes: dict[str,AttributeConfig]
    badges: dict[str,BadgeConfig]; rarity_colors: dict[str,str]
    groups: GroupEcosystem; actions: ActionConfig
    scenarios: list[ScenarioConfig]; jury: JuryConfig

    def get_brand(self): return self.brand
    def role(self, key): return self.roles.get(key)
    def task(self, tid): return next((t for t in self.tasks if t.id==tid), None)
    def active_tasks(self, task_set="default"):
        return [t for t in self.tasks if t.active and (t.task_set==task_set or t.task_set=="default")]
    def event(self, eid): return next((e for e in self.events if e.id==eid), None)
    def badge(self, key): return self.badges.get(key)
    def scenario(self, sid): return next((s for s in self.scenarios if s.id==sid), None)
    def active_scenario(self): return next((s for s in self.scenarios if s.active), None)
    def level_for_xp(self, xp): return max(1, min(xp//self.leveling.xp_per_level+1, self.leveling.max_level))
    def xp_for_next_level(self, level): return level * self.leveling.xp_per_level
    def default_team_stats(self, role_key):
        role = self.role(role_key)
        if role: return dict(role.stats)
        return {k: v.default for k,v in self.team_attributes.items()}

# ── Parser'lar ────────────────────────────────────────────
def _parse_brand(data):
    b = data.get("brand", {})
    return BrandConfig(**{f: b.get(f, "") for f in BrandConfig.__dataclass_fields__})

def _parse_roles(data):
    roles = {k: RoleConfig(key=k, **{f: r[f] for f in RoleConfig.__dataclass_fields__ if f!="key"})
             for k,r in data.get("roles",{}).items()}
    lv = data.get("leveling",{})
    return roles, LevelingConfig(
        xp_per_level=lv.get("xp_per_level",400),
        max_level=lv.get("max_level",20),
        level_rewards={int(k):v for k,v in lv.get("level_rewards",{}).items()},
    )

def _parse_tasks(data):
    return [TaskConfig(
        id=t["id"], title=t["title"], description=t["description"],
        type=t["type"], difficulty=t["difficulty"], xp_reward=t["xp_reward"],
        badge_reward=t.get("badge_reward"), stat_rewards=t.get("stat_rewards",{}),
        proof_type=t.get("proof_type","link"), active=t.get("active",True),
        starts_at=t.get("starts_at"), ends_at=t.get("ends_at"),
        task_set=t.get("task_set","default"),
    ) for t in data.get("tasks",[])]

def _parse_events(data):
    return [EventConfig(
        id=e["id"], title=e["title"], type=e["type"],
        description=e["description"], scheduled_at=e["scheduled_at"],
        duration_minutes=e["duration_minutes"],
        announcement_channel=e.get("announcement_channel",False),
        xp_reward=e.get("xp_reward",0),
        bonus_task_type=e.get("bonus_task_type"),
        bonus_multiplier=e.get("bonus_multiplier",1.0),
    ) for e in data.get("events",[])]

def _parse_attributes(data):
    def pb(block): return {k: AttributeConfig(key=k,**v) for k,v in block.items()}
    return (
        pb(data.get("team_attributes",{})),
        pb(data.get("member_attributes",{})),
        {k: BadgeConfig(key=k,**v) for k,v in data.get("badges",{}).items()},
        data.get("rarity_colors",{}),
    )

def _parse_groups(data):
    eco = data.get("ecosystem",{}); org = eco.get("org_group",{}); jury = eco.get("jury_group",{})
    scoring = data.get("scoring",{})
    return GroupEcosystem(
        org_chat_id=org.get("chat_id",0), org_name=org.get("name","Org"),
        org_bot_token_env=org.get("bot_token_env","ALEV_BOT_TOKEN"),
        jury_chat_id=jury.get("chat_id",0), jury_name=jury.get("name","Jüri"),
        jury_bot_token_env=jury.get("bot_token_env","ALEV_JURY_BOT_TOKEN"),
        team_groups=[TeamGroupConfig(
            id=g["id"], chat_id=g.get("chat_id",0), name=g["name"],
            bot_token_env=g.get("bot_token_env","ALEV_BOT_TOKEN"),
            task_set=g.get("task_set","default"),
            leaderboard_scope=g.get("leaderboard_scope","local"),
            active=g.get("active",True),
        ) for g in eco.get("team_groups",[])],
        global_leaderboard=scoring.get("global_leaderboard",True),
        local_leaderboard=scoring.get("local_leaderboard",True),
        cross_group_duel=scoring.get("cross_group_duel",True),
    )

def _int_delta(v) -> int:
    if v == "scaled": return 0
    return int(str(v).replace("+",""))

def _parse_actions(data):
    effects = {}
    for atype, adef in data.get("action_effects",{}).items():
        raw = adef.get("effects",{}); glob = adef.get("global",{})
        if raw: glob = raw
        by_task = adef.get("by_task_type",{})
        effects[atype] = ActionEffect(
            action_type=atype, description=adef.get("description",""),
            global_effects={k:_int_delta(v) for k,v in glob.items() if v!="scaled"},
            by_task_type={tt:{k:_int_delta(v) for k,v in te.items()} for tt,te in by_task.items()},
            base_score=adef.get("base_score",50), scale=adef.get("scale",0.1),
        )
    return ActionConfig(
        effects=effects,
        unlock_rules=[UnlockRule(id=r["id"],description=r["description"],
            condition=r["condition"],unlocks=r["unlocks"]) for r in data.get("unlock_rules",[])]
    )

def _parse_scenarios(data):
    result = []
    for s in data.get("scenarios",[]):
        stages = sorted([StageConfig(
            id=st["id"], name=st["name"], description=st["description"],
            order=st["order"], duration_minutes=st["duration_minutes"],
            starts_at=st.get("starts_at"), task_set=st.get("task_set","default"),
            xp_multiplier=st.get("xp_multiplier",1.0),
            completion_message_tr=st.get("completion_message_tr","").strip(),
            completion_message_en=st.get("completion_message_en","").strip(),
            unlock_next_on=st.get("unlock_next_on","manual"),
            is_final=st.get("is_final",False),
        ) for st in s.get("stages",[])], key=lambda x: x.order)
        result.append(ScenarioConfig(
            id=s["id"], name=s["name"], description=s["description"],
            active=s.get("active",False), auto_advance=s.get("auto_advance",False),
            announce_to_all_groups=s.get("announce_to_all_groups",True), stages=stages,
        ))
    return result

def _parse_jury(data):
    j = data.get("jury",{}); scoring = j.get("scoring",{})
    return JuryConfig(
        enabled=j.get("enabled",False),
        xp_weight=j.get("xp_weight",60)/100,
        jury_weight=j.get("jury_weight",40)/100,
        members=j.get("members",[]),
        criteria=[JuryCriterion(id=c["id"],name_tr=c["name_tr"],name_en=c["name_en"],
            weight=c["weight"],emoji=c["emoji"]) for c in j.get("criteria",[])],
        score_min=scoring.get("min",0), score_max=scoring.get("max",100),
        allow_update=scoring.get("allow_update",True), anonymous=scoring.get("anonymous",False),
    )

def load_config() -> GameConfig:
    return GameConfig(
        brand=_parse_brand(_load("brand.yaml")),
        **dict(zip(["roles","leveling"], _parse_roles(_load("roles.yaml")))),
        tasks=_parse_tasks(_load("tasks.yaml")),
        events=_parse_events(_load("events.yaml")),
        **dict(zip(["team_attributes","member_attributes","badges","rarity_colors"],
                   _parse_attributes(_load("attributes.yaml")))),
        groups=_parse_groups(_load("groups.yaml")),
        actions=_parse_actions(_load("actions.yaml")),
        scenarios=_parse_scenarios(_load("scenarios.yaml")),
        jury=_parse_jury(_load("jury.yaml")),
    )
