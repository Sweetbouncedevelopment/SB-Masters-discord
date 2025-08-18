# commands/setuppromotions.py
import os
import discord
from discord import app_commands
from utils.config import set_guild_cfg, get_guild_cfg

# Read allowed role IDs from .env (e.g., ADMIN_ROLES_IDS=123,456)
_raw = os.getenv("ADMIN_ROLES_IDS", "").strip()
ADMIN_ROLE_IDS = {int(x) for x in _raw.split(",") if x.strip().isdigit()}

def has_admin_roles():
    """Allow if user has Manage Guild/Admin OR has any role in ADMIN_ROLES_IDS."""
    async def predicate(interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Guild member context required.")
        perms = interaction.user.guild_permissions
        if perms.manage_guild or perms.administrator:
            return True
        if ADMIN_ROLE_IDS:
            user_role_ids = {r.id for r in interaction.user.roles}
            if user_role_ids & ADMIN_ROLE_IDS:
                return True
        raise app_commands.CheckFailure("You don't have permission to use this command.")
    return app_commands.check(predicate)

async def setup(client: discord.Client):
    tree = client.tree

    @app_commands.default_permissions(manage_guild=True)  # hidden from non-admins by default
    @has_admin_roles()  # execution gate: admins OR roles in ADMIN_ROLES_IDS
    @tree.command(
        name="setuppromotions",
        description="Set the channel where promotion approval requests will be sent (admin only)"
    )
    async def setuppromotions(interaction: discord.Interaction, channel: discord.TextChannel):
        set_guild_cfg(interaction.guild_id, promotion_channel_id=channel.id)

        embed = discord.Embed(
            title="Promotion Queue Channel Set",
            description=f"Promotion requests will be sent to {channel.mention}.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Change anytime with /setuppromotions")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    @has_admin_roles()
    @tree.command(
        name="promotionchannel",
        description="View the currently configured promotion channel"
    )
    async def promotionchannel(interaction: discord.Interaction):
        cfg = get_guild_cfg(interaction.guild_id)
        ch = interaction.guild.get_channel(int(cfg.get("promotion_channel_id") or 0))
        if ch:
            await interaction.response.send_message(
                f"📌 Current promotion channel: {ch.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠ No promotion channel set. Use `/setuppromotions #channel`.", ephemeral=True
            )
