"""
Utility functions for fetching Minecraft and Hypixel SkyBlock stats.
- Mojang API to resolve username -> UUID
- Hypixel API to validate profiles / fetch guilds
- SkyHelper API (v2 with v1 fallback) for advanced SkyBlock stats
"""

import os
import re
import socket
import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# ===== API Keys & Base URLs =====
HYPIXEL_API_KEY = os.getenv("HYPIXEL_API_KEY")
if not HYPIXEL_API_KEY:
    raise RuntimeError("Missing HYPIXEL_API_KEY in environment variables")

HYPIXEL_BASE = "https://api.hypixel.net/v2"
MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/{username}"

# SkyHelper bases: comma-separated list in .env, first is primary
# e.g. SKYHELPER_API_URLS=https://api.altpapier.dev,https://your-mirror.example.com
_SKYHELPER_BASES: List[str] = [
    u.strip().rstrip("/") for u in os.getenv("SKYHELPER_API_URLS", "https://api.altpapier.dev").split(",") if u.strip()
]

# Optional SkyHelper auth (depending on your server config)
# If your SkyHelper server expects a query key (?key=...), set SKYHELPER_API_KEY
# If it expects a bearer header, set SKYHELPER_API_BEARER
_SKYHELPER_QS_KEY = os.getenv("SKYHELPER_API_KEY")
_SKYHELPER_BEARER = os.getenv("SKYHELPER_API_BEARER")

__all__ = ["username_to_uuid", "get_sb_stats", "hypixel_guild_by_player"]

# ---------- HTTP helpers (IPv4 + retries) ----------

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)

def _ipv4_session():
    # Force IPv4 to dodge Windows IPv6/DNS quirks that cause getaddrinfo errors
    return aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT, connector=aiohttp.TCPConnector(family=socket.AF_INET, ssl=None))

async def _fetch_json(url: str, *, headers: Optional[Dict[str, str]] = None, attempts: int = 3, backoff: float = 0.75) -> Dict[str, Any]:
    last_exc: Optional[Exception] = None
    async with _ipv4_session() as session:
        for i in range(attempts):
            try:
                async with session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                last_exc = e
                await asyncio.sleep(backoff * (2 ** i))
    assert last_exc is not None
    raise last_exc

def _add_qs_key(url: str) -> str:
    if not _SKYHELPER_QS_KEY:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}key={_SKYHELPER_QS_KEY}"

def _skyhelper_headers() -> Dict[str, str]:
    h: Dict[str, str] = {}
    if _SKYHELPER_BEARER:
        h["Authorization"] = f"Bearer {_SKYHELPER_BEARER}"
    return h

# ---------- Mojang ----------

async def username_to_uuid(username: str) -> Optional[str]:
    """Resolve a Minecraft username to a UUID (no dashes). Returns None if not found."""
    url = MOJANG_PROFILE.format(username=username)
    data = await _fetch_json(url, attempts=2)
    # Mojang returns {"id": "...", "name": "..."} or 204 if not found (handled by raise_for_status)
    return data.get("id")

# ---------- Hypixel: Guild ----------

async def hypixel_guild_by_player(user_or_uuid: str, api_key: Optional[str] = None) -> Optional[dict]:
    """
    Fetch the player's guild info from the Hypixel API.
    Accepts username or UUID (with/without dashes).
    Returns: guild dict if player is in a guild, else None.
    """
    key = api_key or HYPIXEL_API_KEY
    if not key:
        raise RuntimeError("Missing Hypixel API key (env HYPIXEL_API_KEY or parameter api_key).")

    # Determine if UUID or username
    if UUID_RE.match(user_or_uuid):
        uuid = user_or_uuid.replace("-", "")
    else:
        uuid = await username_to_uuid(user_or_uuid)
        if not uuid:
            raise ValueError(f"Username '{user_or_uuid}' not found.")

    url = f"{HYPIXEL_BASE}/guild?player={uuid}"
    data = await _fetch_json(url, headers={"API-Key": key})
    if not data.get("success", False):
        raise RuntimeError(f"Hypixel API error: {data}")
    return data.get("guild") or None

# ---------- SkyBlock stats (Hypixel + SkyHelper) ----------

async def _hypixel_selected_profile_uuid(username: str) -> str:
    """Return (uuid_no_dashes) and ensure they have at least one SkyBlock profile with member data."""
    uuid = await username_to_uuid(username)
    if not uuid:
        raise ValueError(f"Username '{username}' not found.")
    url = f"{HYPIXEL_BASE}/skyblock/profiles?uuid={uuid}"
    data = await _fetch_json(url, headers={"API-Key": HYPIXEL_API_KEY})
    if not data.get("success", False):
        raise RuntimeError(f"Hypixel API error: {data}")

    profiles = data.get("profiles") or []
    if not profiles:
        raise ValueError(f"No SkyBlock profiles found for {username}.")

    # Pick 'selected' profile if available; otherwise first
    profile = next((p for p in profiles if p.get("selected")), profiles[0])
    members = profile.get("members") or {}
    if uuid not in members:
        raise ValueError(f"No member data found for {username} in selected profile.")
    return uuid

def _pick_latest_profile(profiles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    latest = None
    latest_ts = -1
    for p in profiles:
        # try common keys
        last = (
            p.get("data", {}).get("last_save")
            or p.get("last_save")
            or p.get("member", {}).get("last_save")
        )
        try:
            ts = int(last) if last is not None else -1
        except Exception:
            ts = -1
        if ts > latest_ts:
            latest_ts = ts
            latest = p
    return latest

def _to_int(x: Any, default: int = 0) -> int:
    try: return int(x)
    except Exception: return default

def _to_float(x: Any, default: float = 0.0) -> float:
    try: return float(x)
    except Exception: return default

def _extract_fields(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map SkyHelper profile JSON into the fields /getroles expects:
      networth, sb_level, skill_avg, slayer_xp, cata_lvl, rift_all_charms, farm_weight, masteries
    Works with v2 & v1 shapes. Falls back safely if fields are missing.
    """
    d = profile.get("data", {}) if isinstance(profile.get("data"), dict) else profile

    networth = (
        d.get("networth", {}).get("total")
        or d.get("networth", {}).get("networth")
        or d.get("networth_total")
        or 0
    )

    sb_level = (
        d.get("player", {}).get("skyblock_level")
        or d.get("skyblock_level", {}).get("level")
        or d.get("leveling", {}).get("level")
        or 0
    )

    skill_avg = (
        d.get("skills", {}).get("average")
        or d.get("skills", {}).get("average_skill_level")
        or d.get("skills_average")
        or 0.0
    )

    # Slayer: total XP across bosses
    slayer = d.get("slayer", {}) or d.get("slayers", {}) or {}
    if isinstance(slayer, dict):
        if "total_xp" in slayer:
            slayer_xp = slayer.get("total_xp", 0)
        else:
            # assume shape { "revenant": {"xp": ...}, ... }
            slayer_xp = 0
            for v in slayer.values():
                if isinstance(v, dict):
                    slayer_xp += _to_int(v.get("xp", 0))
    else:
        slayer_xp = 0

    cata_lvl = (
        d.get("dungeons", {}).get("catacombs", {}).get("level")
        or d.get("dungeons", {}).get("catacombs", {}).get("level", {}).get("level")
        or d.get("dungeons_catacombs_level")
        or 0
    )

    rift_all_charms = bool(
        d.get("rift", {}).get("all_charms")
        or (d.get("rift", {}).get("charms", {}).get("completed", 0) >= d.get("rift", {}).get("charms", {}).get("total", 9999))
        or d.get("rift_charms_complete")
        or False
    )

    farm_weight = (
        d.get("farming", {}).get("weight")
        or d.get("weights", {}).get("farming")
        or 0
    )

    masteries = (
        d.get("masteries")
        or (len(d.get("masteries_list", [])) if isinstance(d.get("masteries_list", []), list) else 0)
        or 0
    )

    return {
        "networth": _to_int(networth, 0),
        "sb_level": _to_float(sb_level, 0.0),
        "skill_avg": _to_float(skill_avg, 0.0),
        "slayer_xp": _to_int(slayer_xp, 0),
        "cata_lvl": _to_float(cata_lvl, 0.0),
        "rift_all_charms": bool(rift_all_charms),
        "farm_weight": _to_int(farm_weight, 0),
        "masteries": _to_int(masteries, 0),
    }

async def _skyhelper_fetch_profiles(user_or_uuid: str) -> Dict[str, Any]:
    """
    Try v2 then v1 across all configured bases, returning the first success.
    Accepts username or UUID (no dashes or dashed).
    """
    # Try v2 first
    headers = _skyhelper_headers()
    last_exc: Optional[Exception] = None
    for base in _SKYHELPER_BASES:
        # Accept either username or uuid path; many servers accept both
        for path in (f"/v2/profiles/{user_or_uuid}", f"/v2/profiles/{user_or_uuid.replace('-', '')}"):
            try:
                url = _add_qs_key(f"{base}{path}")
                return await _fetch_json(url, headers=headers, attempts=2, backoff=0.6)
            except Exception as e:
                last_exc = e
                continue

    # Fallback to v1
    for base in _SKYHELPER_BASES:
        for path in (f"/v1/profiles/{user_or_uuid}", f"/v1/profiles/{user_or_uuid.replace('-', '')}"):
            try:
                url = _add_qs_key(f"{base}{path}")
                return await _fetch_json(url, headers=headers, attempts=2, backoff=0.6)
            except Exception as e:
                last_exc = e
                continue

    raise last_exc or RuntimeError("All SkyHelper mirrors failed")

async def get_sb_stats(username: str) -> Dict[str, Any]:
    """
    Returns:
        dict: {
            networth: int,
            sb_level: float,
            skill_avg: float,
            slayer_xp: int,
            cata_lvl: float,
            rift_all_charms: bool,
            farm_weight: int,
            masteries: int
        }
    Raises:
        ValueError: if username not found or no SkyBlock profile exists.
        RuntimeError: if an API call fails.
    """
    # Ensure Hypixel sees a valid profile for this user (also yields canonical uuid)
    uuid = await _hypixel_selected_profile_uuid(username)

    # Query SkyHelper by UUID (works on most deployments), fallback accepts name as well
    data = await _skyhelper_fetch_profiles(uuid)

    # Common shapes:
    # v2 -> { "status": 200, "data": { "profiles": [ ... ] } }
    # v1 -> { "status": 200, "profiles": [ ... ] } or similar
    container = data.get("data") if isinstance(data.get("data"), dict) else data
    profiles = container.get("profiles") if isinstance(container, dict) else None
    if not profiles:
        raise RuntimeError(f"SkyHelper API returned no profiles: {data}")

    latest = _pick_latest_profile(profiles)
    if not latest:
        raise RuntimeError("Could not select latest profile from SkyHelper")

    stats = _extract_fields(latest)
    return stats
