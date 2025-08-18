# events/on_member_join.py
import asyncio
import discord
from discord.errors import HTTPException, Forbidden
from utils.config import get_guild_cfg

# --- Global DM throttle (per process) ---
# Send at most ~1 DM per 1.2s; brief backoff on 40003
_DM_LOCK = asyncio.Lock()
_LAST_DM_TS = 0.0
DM_INTERVAL = 1.2           # seconds between DM opens (tune 1.0–2.0)
DM_BACKOFF_40003 = 3.0      # extra sleep when we hit 40003
DM_MAX_RETRIES = 2          # attempts per member on 40003

WELCOME_TEXT = (
    "Welcome! Please verify by clicking the **Verify me** button in the server.\n"
    "If you can’t find it, check the verification channel."
)

async def _safe_dm(member: discord.Member, content: str) -> bool:
    """Open a DM to member with global throttling and limited retries."""
    global _LAST_DM_TS
    for attempt in range(1, DM_MAX_RETRIES + 2):  # first try + retries
        # Rate limit DM opens globally
        async with _DM_LOCK:
            now = asyncio.get_running_loop().time()
            wait = max(0.0, (_LAST_DM_TS + DM_INTERVAL) - now)
            if wait:
                await asyncio.sleep(wait)
            try:
                await member.send(content)
                _LAST_DM_TS = asyncio.get_running_loop().time()
                return True
            except Forbidden:
                # DMs disabled or blocked
                return False
            except HTTPException as e:
                # 40003 = opening DMs too fast; small backoff then retry
                if e.code == 40003 and attempt <= DM_MAX_RETRIES:
                    _LAST_DM_TS = asyncio.get_running_loop().time() + DM_BACKOFF_40003
                    await asyncio.sleep(DM_BACKOFF_40003)
                    continue
                # Other HTTP errors: give up, fall back to public message
                return False

    return False

async def on_member_join(member: discord.Member):
    # Try DM first
    dm_ok = await _safe_dm(member, WELCOME_TEXT)
    if dm_ok:
        return

    # Fall back: post in verification or system channel
    cfg = get_guild_cfg(member.guild.id) or {}
    # Prefer your verification channel id if you store it; fallback to log/system
    verification_channel_id = cfg.get("channel_id") or cfg.get("verification_channel_id")
    log_channel_id = cfg.get("log_channel_id")
    channel = None

    if verification_channel_id:
        channel = member.guild.get_channel(int(verification_channel_id))
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        channel = member.guild.get_channel(int(log_channel_id)) if log_channel_id else None
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        channel = member.guild.system_channel  # final fallback

    if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(
                f"Welcome {member.mention}! Please verify by clicking the **Verify me** button above."
            )
        except Exception:
            pass  # don’t let welcome errors crash the event
