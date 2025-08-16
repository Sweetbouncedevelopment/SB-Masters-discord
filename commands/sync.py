# commands/sync.py
import discord
from discord import app_commands
from utils.checks import is_guild_admin

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(
        name="sync",
        description="Force-sync application commands in this server"
    )
    @app_commands.default_permissions(administrator=True)  # Hide from non-admins
    @is_guild_admin()
    async def sync_cmd(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message(
                "Run this command inside a server.",
                ephemeral=True
            )

        # Copy global commands into this guild and sync for instant availability
        client.tree.copy_global_to(guild=interaction.guild)
        synced = await client.tree.sync(guild=interaction.guild)
        await interaction.response.send_message(
            f"✅ Synced **{len(synced)}** commands to this server.",
            ephemeral=True
        )
