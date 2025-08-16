# commands/setuplogs.py
import discord
from discord import app_commands
from utils.config import set_guild_cfg, get_guild_cfg
from utils.checks import is_guild_admin

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(
        name="setuplogs",
        description="Choose the channel where verification audit logs will be posted"
    )
    @app_commands.default_permissions(administrator=True)  # Hide from non-admins
    @is_guild_admin()
    async def setuplogs(
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        # Save the log channel for this guild
        set_guild_cfg(interaction.guild_id, log_channel_id=channel.id)

        # Quick confirm embed
        embed = discord.Embed(
            title="Logs channel set",
            description=f"Audit logs will be posted in {channel.mention}.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="You can change this anytime with /setuplogs")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(
        name="logtest",
        description="Post a test message to the configured logs channel"
    )
    @app_commands.default_permissions(administrator=True)
    @is_guild_admin()
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
