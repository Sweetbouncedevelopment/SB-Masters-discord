# commands/setuppromotions.py
import discord
from discord import app_commands
from utils.checks import is_guild_admin
from utils.config import set_guild_cfg, get_guild_cfg

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(
        name="setuppromotions",
        description="Set the channel where promotion approval requests will be sent (admin only)"
    )
    @is_guild_admin()
    async def setuppromotions(interaction: discord.Interaction, channel: discord.TextChannel):
        set_guild_cfg(interaction.guild_id, promotion_channel_id=channel.id)

        embed = discord.Embed(
            title="Promotion Queue Channel Set",
            description=f"Promotion requests will be sent to {channel.mention}.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Change anytime with /setuppromotions")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(
        name="promotionchannel",
        description="View the currently configured promotion channel"
    )
    @is_guild_admin()
    async def promotionchannel(interaction: discord.Interaction):
        cfg = get_guild_cfg(interaction.guild_id)
        ch = interaction.guild.get_channel(int(cfg.get("promotion_channel_id", 0)))
        if ch:
            await interaction.response.send_message(
                f"📌 Current promotion channel: {ch.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠ No promotion channel set. Use `/setuppromotions #channel`.", ephemeral=True
            )
