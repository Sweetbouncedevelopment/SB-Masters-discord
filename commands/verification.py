# commands/verification.py
# Slash commands to post/reset the verification embed and manage settings.

import os
import discord
from discord import app_commands
from utils.config import set_guild_cfg, get_guild_cfg
from views.verification_view import VerifyView

# ===== Allowed staff roles from .env =====
# Example: ADMIN_ROLES_IDS=123456789012345678,987654321098765432
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
    @tree.command(name="verification_setup", description="Post the verification embed with the persistent button")
    async def verification_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        verified_role: discord.Role | None = None,
        title: str = "Verification required",
        description: str = (
            "Click the button below to verify your Minecraft username "
            "with your Hypixel-linked Discord."
        )
    ):
        set_guild_cfg(
            interaction.guild_id,
            channel_id=channel.id,
            role_id=(verified_role.id if verified_role else None)
        )
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Hypixel verification")
        view = VerifyView()
        msg = await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"✅ Verification message posted in {channel.mention} (message ID: {msg.id}).",
            ephemeral=True
        )

    @app_commands.default_permissions(manage_guild=True)
    @has_admin_roles()
    @tree.command(name="verification_reset", description="Re-post the verification embed to the configured channel")
    async def verification_reset(
        interaction: discord.Interaction,
        title: str = "Verification required",
        description: str = (
            "Click the button below to verify your Minecraft username "
            "with your Hypixel-linked Discord."
        )
    ):
        cfg = get_guild_cfg(interaction.guild_id) or {}
        channel_id = cfg.get("channel_id")
        if not channel_id:
            return await interaction.response.send_message(
                "No verification channel configured yet. Run `/verification_setup` first.",
                ephemeral=True
            )

        channel = interaction.guild.get_channel(int(channel_id)) if interaction.guild else None
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Configured channel is invalid or not found. Re-run `/verification_setup`.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Hypixel verification")
        view = VerifyView()
        msg = await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"🔁 Verification message re-posted in {channel.mention} (message ID: {msg.id}).",
            ephemeral=True
        )

    @app_commands.default_permissions(manage_guild=True)
    @has_admin_roles()
    @tree.command(name="verification_settings", description="View or change verification settings")
    async def verification_settings(
        interaction: discord.Interaction,
        log_channel: discord.TextChannel | None = None,
        cooldown_seconds: app_commands.Range[int, 0, 3600] | None = None
    ):
        updates = {}
        if log_channel is not None:
            updates["log_channel_id"] = log_channel.id
        if cooldown_seconds is not None:
            updates["cooldown_seconds"] = int(cooldown_seconds)

        if updates:
            set_guild_cfg(interaction.guild_id, **updates)

        cfg = get_guild_cfg(interaction.guild_id) or {}
        ch = interaction.guild.get_channel(int(cfg.get("channel_id") or 0)) if cfg.get("channel_id") else None
        log = interaction.guild.get_channel(int(cfg.get("log_channel_id") or 0)) if cfg.get("log_channel_id") else None
        role = interaction.guild.get_role(int(cfg.get("role_id") or 0)) if cfg.get("role_id") else None

        embed = discord.Embed(title="Verification Settings", color=discord.Color.blurple())
        embed.add_field(name="Verification Channel", value=(ch.mention if ch else "Not set"), inline=False)
        embed.add_field(name="Verified Role", value=(role.mention if role else "Not set"), inline=False)
        embed.add_field(name="Log Channel", value=(log.mention if log else "Not set"), inline=False)
        embed.add_field(name="Cooldown (s)", value=str(cfg.get("cooldown_seconds", 0)), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Public health check
    @tree.command(name="verification_ping", description="Health check for the verification module")
    async def verification_ping(interaction: discord.Interaction):
        await interaction.response.send_message("Pong! ✅", ephemeral=True)
