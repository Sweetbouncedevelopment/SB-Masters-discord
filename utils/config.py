# utils/config.py
import json, discord
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path("guild_config.json")
DEFAULTS = {
    "channel_id": None,         # verification embed channel
    "role_id": None,            # verified role
    "log_channel_id": None,     # audit logs
    "cooldown_seconds": 60,     # verification attempt cooldown
    "rank_role_map": {},        # {"GUILDMASTER": 1234567890, "OFFICER": 2345, "MEMBER": 3456}
}

def _read() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}

def _write(data: Dict[str, Any]):
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def load_cfg() -> Dict[str, Any]:
    return _read()

def save_cfg(cfg: Dict[str, Any]):
    _write(cfg)

def get_guild_cfg(guild_id: int) -> Dict[str, Any]:
    data = _read()
    g = data.get(str(guild_id), {})
    for k, v in DEFAULTS.items():
        g.setdefault(k, v)
    return g

def set_guild_cfg(guild_id: int, **updates):
    data = _read()
    g = data.get(str(guild_id), {})
    g.update(updates)
    for k, v in DEFAULTS.items():
        g.setdefault(k, v)
    data[str(guild_id)] = g
    _write(data)

def norm(s: str | None) -> str:
    return (s or "").strip().casefold()

def candidate_discord_names(member: discord.Member) -> list[str]:
    parts: list[str] = []
    uname = getattr(member, "name", None)
    gname = getattr(member, "global_name", None)
    dname = getattr(member, "display_name", None)
    disc = getattr(member, "discriminator", None)
    if uname: parts.append(uname)
    if gname: parts.append(gname)
    if dname: parts.append(dname)
    if uname and disc and disc != "0":
        parts.append(f"{uname}#{disc}")
    parts += [f"@{x}" for x in list({p for p in parts})]
    return list({ norm(p) for p in parts if p })
