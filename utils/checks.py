# utils/checks.py
import os
from typing import Set
from discord import app_commands, Interaction

def _parse_ids(env_val: str | None) -> Set[int]:
    if not env_val:
        return set()
    return {int(x) for x in env_val.split(",") if x.strip().isdigit()}

ADMIN_ROLE_IDS = _parse_ids(os.getenv("ADMIN_ROLE_IDS"))

def is_guild_admin():
    """Check: user must have ADMIN_ROLE_IDS role OR Administrator perm."""
    async def predicate(interaction: Interaction) -> bool:
        if not interaction.guild or not interaction.user:
            return False
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        if ADMIN_ROLE_IDS and any(r.id in ADMIN_ROLE_IDS for r in member.roles):
            return True
        return member.guild_permissions.administrator
    return app_commands.check(predicate)
