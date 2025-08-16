# events/on_member_join.py
import discord

async def setup(client: discord.Client):
    @client.event
    async def on_member_join(member: discord.Member):
        # Optional example: DM newcomers. Ignore failures when DMs are closed.
        try:
            await member.send("Welcome! Please verify by clicking the **Verify me** button in the server.")
        except discord.Forbidden:
            pass
