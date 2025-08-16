# commands/verification.py
# Slash commands to post/reset the verification embed and manage settings.

import discord
from discord import app_commands
from utils.config import set_guild_cfg, get_guild_cfg
from views.verification_view import VerifyView
from utils.checks import is_guild_admin

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(name="verification_setup", description="Post the verification embed with the persistent button")
    @app_commands.default_permissions(administrator=True)  # Hide from normal players
    @is_guild_admin()
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

    @tree.command(name="verification_reset", description="Re-post the verification embed to the configured channel")
    @app_commands.default_permissions(administrator=True)
    @is_guild_admin()
    async def verification_reset(
        interaction: discord.Interaction,
        title: str = "Verification required",
        description: str = (
            "Click the button below to verify your Minecraft username "
            "with your Hypixel-linked Discord."
        )
    ):
        cfg = get_guild_cfg(interaction.guild_id)
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

    @tree.command(name="verification_settings", description="View or change verification settings")
    @app_commands.default_permissions(administrator=True)
    @is_guild_admin()
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

        cfg = get_guild_cfg(interaction.guild_id)
        ch = interaction.guild.get_channel(int(cfg["channel_id"])) if cfg["channel_id"] else None
        log = interaction.guild.get_channel(int(cfg["log_channel_id"])) if cfg["log_channel_id"] else None
        role = interaction.guild.get_role(int(cfg["role_id"])) if cfg["role_id"] else None

        embed = discord.Embed(title="Verification Settings", color=discord.Color.blurple())
        embed.add_field(name="Verification Channel", value=(ch.mention if ch else "Not set"), inline=False)
        embed.add_field(name="Verified Role", value=(role.mention if role else "Not set"), inline=False)
        embed.add_field(name="Log Channel", value=(log.mention if log else "Not set"), inline=False)
        embed.add_field(name="Cooldown (s)", value=str(cfg["cooldown_seconds"]), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="verification_ping", description="Health check for the verification module")
    async def verification_ping(interaction: discord.Interaction):
        await interaction.response.send_message("Pong! ✅", ephemeral=True)
