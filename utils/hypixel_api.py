"""
Utility functions for fetching Minecraft and Hypixel SkyBlock stats.
Uses:
- Mojang API to resolve username -> UUID
- Hypixel API to validate profiles / fetch guilds
- SkyHelper API to fetch advanced SkyBlock stats (networth, skills, etc.)
"""

import os
import aiohttp
import re

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# ===== API Keys & Base URLs =====
HYPIXEL_API_KEY = os.getenv("HYPIXEL_API_KEY")
if not HYPIXEL_API_KEY:
    raise RuntimeError("Missing HYPIXEL_API_KEY in environment variables")

HYPIXEL_BASE = "https://api.hypixel.net/v2"
MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/{username}"
SKYHELPER_BASE = "https://skyhelperapi.dev/api/v1/profiles"

__all__ = ["username_to_uuid", "get_sb_stats", "hypixel_guild_by_player"]

# ===== Mojang API =====
async def username_to_uuid(username: str) -> str | None:
    """
    Resolve a Minecraft username to a UUID (no dashes).
    Returns None if the username does not exist.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(MOJANG_PROFILE.format(username=username), timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("id")
            return None


# ===== Hypixel: Guild =====
async def hypixel_guild_by_player(user_or_uuid: str, api_key: str | None = None) -> dict | None:
    """
    Fetch the player's guild info from the Hypixel API.
    Accepts username or UUID (with/without dashes).
    Works with: hypixel_guild_by_player(uuid, api_key)
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

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{HYPIXEL_BASE}/guild",
            params={"player": uuid},  # ✅ correct param name for Hypixel
            headers={"API-Key": key},
            timeout=15
        ) as resp:

            data = await resp.json()
            if not data.get("success"):
                raise RuntimeError(f"Hypixel API error: {data}")
            return data.get("guild") or None


# ===== Hypixel & SkyHelper Stats =====
async def get_sb_stats(username: str) -> dict:
    """
    Fetch SkyBlock stats for a player from Hypixel + SkyHelper APIs.

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
    uuid = await username_to_uuid(username)
    if not uuid:
        raise ValueError(f"Username '{username}' not found.")

    async with aiohttp.ClientSession() as session:
        # --- Hypixel API: validate SkyBlock profile exists ---
        async with session.get(
            f"{HYPIXEL_BASE}/skyblock/profiles",
            params={"uuid": uuid},
            headers={"API-Key": HYPIXEL_API_KEY},
            timeout=15
        ) as resp:
            data = await resp.json()
            if not data.get("success"):
                raise RuntimeError(f"Hypixel API error: {data}")

            profiles = data.get("profiles", [])
            if not profiles:
                raise ValueError(f"No SkyBlock profiles found for {username}.")

            # Pick selected profile (or first if none marked selected)
            profile = next((p for p in profiles if p.get("selected")), profiles[0])
            members = profile.get("members", {})
            if uuid not in members:
                raise ValueError(f"No member data found for {username} in selected profile.")

        # --- SkyHelper API: get detailed SkyBlock stats ---
        async with session.get(f"{SKYHELPER_BASE}/{uuid}", timeout=15) as resp:
            skyhelper_data = await resp.json()
            if not skyhelper_data.get("success"):
                raise RuntimeError(f"SkyHelper API error: {skyhelper_data}")

        # --- Parse stats ---
        stats = {
            "networth": int(skyhelper_data["data"]["networth"]["networth"]),
            "sb_level": float(skyhelper_data["data"]["skyblock_level"]["level"]),
            "skill_avg": float(skyhelper_data["data"]["skills"]["average_skill_level"]),
            "slayer_xp": sum(slayer["xp"] for slayer in skyhelper_data["data"]["slayers"].values()),
            "cata_lvl": float(skyhelper_data["data"]["dungeons"]["catacombs"]["level"]["level"]),
            "rift_all_charms": (
                skyhelper_data["data"]["rift"]["charms"]["completed"]
                >= skyhelper_data["data"]["rift"]["charms"]["total"]
            ),
            "farm_weight": int(skyhelper_data["data"]["farming"]["weight"]),
            "masteries": len(skyhelper_data["data"].get("masteries", []))
        }

        return stats
