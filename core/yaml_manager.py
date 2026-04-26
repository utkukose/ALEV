"""
core/yaml_manager.py — YAML Yöneticisi

Admin panelinden yapılan değişiklikler YAML dosyalarına yazılır
ve config hot-reload tetiklenir — botu yeniden başlatmaya gerek yok.

Thread-safe yazma: dosyayı önce .tmp'ye yazar, sonra atomik rename.
"""
from __future__ import annotations
import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

log = logging.getLogger(__name__)
CONFIG_DIR = Path(os.getenv("ALEV_CONFIG_DIR", "config"))

# Reload callback'leri — app.py'de kaydedilir
_reload_callbacks: list[Callable] = []


def register_reload_callback(fn: Callable):
    _reload_callbacks.append(fn)


async def _trigger_reload():
    for fn in _reload_callbacks:
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()
        except Exception as e:
            log.error(f"Reload callback hatası: {e}")


def read_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(filename: str, data: dict, reload: bool = True) -> bool:
    """Atomik YAML yazma. Başarılıysa True döner."""
    path = CONFIG_DIR / filename
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True,
                      default_flow_style=False, sort_keys=False)
        shutil.move(str(tmp), str(path))
        log.info(f"YAML güncellendi: {filename}")
        if reload:
            asyncio.create_task(_trigger_reload())
        return True
    except Exception as e:
        log.error(f"YAML yazma hatası ({filename}): {e}")
        try: tmp.unlink(missing_ok=True)
        except: pass
        return False


# ══════════════════════════════════════════
# Görev CRUD
# ══════════════════════════════════════════
def get_tasks() -> list[dict]:
    return read_yaml("tasks.yaml").get("tasks", [])

def get_task(task_id: str) -> dict | None:
    return next((t for t in get_tasks() if t["id"] == task_id), None)

def save_task(task: dict) -> bool:
    data = read_yaml("tasks.yaml")
    tasks = data.get("tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["id"] == task["id"]), None)
    if idx is not None:
        tasks[idx] = task
    else:
        tasks.append(task)
    data["tasks"] = tasks
    return write_yaml("tasks.yaml", data)

def delete_task(task_id: str) -> bool:
    data = read_yaml("tasks.yaml")
    data["tasks"] = [t for t in data.get("tasks", []) if t["id"] != task_id]
    return write_yaml("tasks.yaml", data)

def toggle_task(task_id: str, active: bool) -> bool:
    data = read_yaml("tasks.yaml")
    for t in data.get("tasks", []):
        if t["id"] == task_id:
            t["active"] = active
    return write_yaml("tasks.yaml", data)


# ══════════════════════════════════════════
# Rol CRUD
# ══════════════════════════════════════════
def get_roles() -> dict:
    return read_yaml("roles.yaml").get("roles", {})

def save_role(role_key: str, role: dict) -> bool:
    data = read_yaml("roles.yaml")
    data.setdefault("roles", {})[role_key] = role
    return write_yaml("roles.yaml", data)

def delete_role(role_key: str) -> bool:
    data = read_yaml("roles.yaml")
    data.get("roles", {}).pop(role_key, None)
    return write_yaml("roles.yaml", data)


# ══════════════════════════════════════════
# Senaryo CRUD
# ══════════════════════════════════════════
def get_scenarios() -> list[dict]:
    return read_yaml("scenarios.yaml").get("scenarios", [])

def get_scenario(sid: str) -> dict | None:
    return next((s for s in get_scenarios() if s["id"] == sid), None)

def save_scenario(scenario: dict) -> bool:
    data = read_yaml("scenarios.yaml")
    scenarios = data.get("scenarios", [])
    idx = next((i for i, s in enumerate(scenarios) if s["id"] == scenario["id"]), None)
    if idx is not None:
        scenarios[idx] = scenario
    else:
        scenarios.append(scenario)
    data["scenarios"] = scenarios
    return write_yaml("scenarios.yaml", data)

def set_active_scenario(sid: str) -> bool:
    data = read_yaml("scenarios.yaml")
    for s in data.get("scenarios", []):
        s["active"] = (s["id"] == sid)
    return write_yaml("scenarios.yaml", data)


# ══════════════════════════════════════════
# Quiz CRUD
# ══════════════════════════════════════════
def get_quiz_sets() -> list[dict]:
    return read_yaml("quizzes.yaml").get("quiz_sets", [])

def save_quiz_set(qs: dict) -> bool:
    data = read_yaml("quizzes.yaml")
    sets = data.get("quiz_sets", [])
    idx = next((i for i, s in enumerate(sets) if s["id"] == qs["id"]), None)
    if idx is not None:
        sets[idx] = qs
    else:
        sets.append(qs)
    data["quiz_sets"] = sets
    return write_yaml("quizzes.yaml", data)

def delete_quiz_set(qsid: str) -> bool:
    data = read_yaml("quizzes.yaml")
    data["quiz_sets"] = [s for s in data.get("quiz_sets", []) if s["id"] != qsid]
    return write_yaml("quizzes.yaml", data)


# ══════════════════════════════════════════
# Konum Görevi CRUD
# ══════════════════════════════════════════
def get_location_tasks() -> list[dict]:
    return read_yaml("location_tasks.yaml").get("location_tasks", [])

def save_location_task(lt: dict) -> bool:
    data = read_yaml("location_tasks.yaml")
    tasks = data.get("location_tasks", [])
    idx = next((i for i, t in enumerate(tasks) if t["task_id"] == lt["task_id"]), None)
    if idx is not None:
        tasks[idx] = lt
    else:
        tasks.append(lt)
    data["location_tasks"] = tasks
    return write_yaml("location_tasks.yaml", data)

def delete_location_task(task_id: str) -> bool:
    data = read_yaml("location_tasks.yaml")
    data["location_tasks"] = [
        t for t in data.get("location_tasks", []) if t["task_id"] != task_id
    ]
    return write_yaml("location_tasks.yaml", data)


# ══════════════════════════════════════════
# Karar Ağacı CRUD
# ══════════════════════════════════════════
def get_branching_scenarios() -> list[dict]:
    return read_yaml("branching_scenarios.yaml").get("branching_scenarios", [])

def save_branching_scenario(bs: dict) -> bool:
    data = read_yaml("branching_scenarios.yaml")
    scenarios = data.get("branching_scenarios", [])
    idx = next((i for i, s in enumerate(scenarios) if s["id"] == bs["id"]), None)
    if idx is not None:
        scenarios[idx] = bs
    else:
        scenarios.append(bs)
    data["branching_scenarios"] = scenarios
    return write_yaml("branching_scenarios.yaml", data)


# ══════════════════════════════════════════
# Jüri CRUD
# ══════════════════════════════════════════
def get_jury_config() -> dict:
    return read_yaml("jury.yaml").get("jury", {})

def save_jury_config(jury: dict) -> bool:
    data = read_yaml("jury.yaml")
    data["jury"] = jury
    return write_yaml("jury.yaml", data)


# ══════════════════════════════════════════
# Grup/Bot ekosistemi CRUD
# ══════════════════════════════════════════
def get_groups_config() -> dict:
    return read_yaml("groups.yaml")

def save_groups_config(groups: dict) -> bool:
    return write_yaml("groups.yaml", groups)
