# commands/setuplogs.py
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
        name="setuplogs",
        description="Choose the channel where verification/promotion audit logs will be posted"
    )
    async def setuplogs(
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        set_guild_cfg(interaction.guild_id, log_channel_id=channel.id)

        embed = discord.Embed(
            title="Logs channel set",
            description=f"Audit logs will be posted in {channel.mention}.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="You can change this anytime with /setuplogs")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    @has_admin_roles()
    @tree.command(
        name="logtest",
        description="Post a test message to the configured logs channel"
    )
    async def logtest(interaction: discord.Interaction):
        cfg = get_guild_cfg(interaction.guild_id)
        log_id = cfg.get("log_channel_id")
        if not log_id:
            return await interaction.response.send_message(
                "No logs channel configured. Run `/setuplogs` first.", ephemeral=True
            )

        ch = interaction.guild.get_channel(int(log_id)) if interaction.guild else None
        if not isinstance(ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            return await interaction.response.send_message(
                "Configured logs channel is invalid or missing. Run `/setuplogs` again.",
                ephemeral=True
            )

        await ch.send(embed=discord.Embed(
            description=f"🧪 **Log test** by {interaction.user.mention}",
            color=discord.Color.green()
        ))
        await interaction.response.send_message("Sent a test log ✅", ephemeral=True)
