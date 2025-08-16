# events/on_ready.py
import discord

async def setup(client: discord.Client):
    @client.event
    async def on_ready():
        # Keep this lightweight; heavy work should go in setup_hook.
        print(f"✅logged in as {client.user} (ID: {client.user.id})")
