# views/verification_view.py
import os
import aiohttp
import discord
from utils.config import get_guild_cfg, candidate_discord_names
from utils.hypixel_api import username_to_uuid

HYPIXEL_API_KEY = os.getenv("HYPIXEL_API_KEY")
HYPIXEL_BASE = "https://api.hypixel.net/v2"

VERIFY_BUTTON_CUSTOM_ID = "verify:open"

def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()

async def _fetch_linked_discord_tag(uuid: str) -> str | None:
    """Fetch the player's linked Discord tag from Hypixel /player."""
    if not HYPIXEL_API_KEY:
        raise RuntimeError("HYPIXEL_API_KEY not set")
    headers = {"API-Key": HYPIXEL_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{HYPIXEL_BASE}/player", params={"uuid": uuid}, headers=headers, timeout=15) as resp:
            data = await resp.json()
            if resp.status == 200 and data.get("success"):
                player = data.get("player") or {}
                links = ((player.get("socialMedia") or {}).get("links") or {})
                return links.get("DISCORD")
            raise RuntimeError(f"Hypixel API /player error ({resp.status}): {data}")

class VerifyModal(discord.ui.Modal, title="Hypixel Verification"):
    def __init__(self):
        super().__init__(timeout=300)
        self.mc_name = discord.ui.TextInput(
            label="Minecraft Username",
            placeholder="Your exact IGN (case-insensitive)",
            min_length=1,
            max_length=16
        )
        self.add_item(self.mc_name)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Run verification inside a server.", ephemeral=True)

        cfg = get_guild_cfg(guild.id)
        verified_role_id = cfg.get("role_id")
        log_channel_id = cfg.get("log_channel_id")

        ign = self.mc_name.value.strip()
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Step 1 - Username -> UUID
        try:
            uuid = await username_to_uuid(ign)
        except Exception as e:
            return await interaction.followup.send(f"Error talking to Mojang: {e}", ephemeral=True)
        if not uuid:
            return await interaction.followup.send(f"❌ Could not find Minecraft user **{ign}**.", ephemeral=True)

        # Step 2 - Linked Discord from Hypixel
        try:
            linked_tag = await _fetch_linked_discord_tag(uuid)
        except Exception as e:
            return await interaction.followup.send(f"Error talking to Hypixel: {e}", ephemeral=True)

        candidates = candidate_discord_names(interaction.user)
        linked_norm = _norm(linked_tag)

        # No linked Discord
        if not linked_tag or linked_norm == "":
            try:
                await interaction.user.send(
                    "No Discord is linked to your Hypixel account.\n"
                    "Use `/social` in Hypixel to link your Discord, then re-run verification."
                )
            except discord.Forbidden:
                pass
            return await interaction.followup.send(
                "⚠ No Discord linked to that account. Instructions sent in DM.", ephemeral=True
            )

        # Linked to a different Discord
        if linked_norm not in candidates:
            try:
                await interaction.user.send(
                    f"⚠ Verification blocked: IGN **{ign}** is already linked, "
                    "which does not match your Discord."
                )
            except discord.Forbidden:
                pass
            return await interaction.followup.send(
                "❌ That IGN is linked to another Discord account. DM sent with details.", ephemeral=True
            )

        # Step 3 - Set nickname
        updated_nick = False
        nick_error = None
        member = guild.get_member(interaction.user.id)
        me = guild.me
        if member and me and me.guild_permissions.manage_nicknames:
            try:
                if member.nick != ign:
                    await member.edit(nick=ign, reason="Verified via Hypixel")
                updated_nick = True
            except discord.Forbidden:
                nick_error = "Missing permission to change nickname"
            except Exception as e:
                nick_error = str(e)

        # Step 4 - Grant role
        granted_role = None
        role_error = None
        if verified_role_id and member:
            role = guild.get_role(int(verified_role_id))
            if role and me and me.top_role > role and guild.me.guild_permissions.manage_roles:
                try:
                    if role not in member.roles:
                        await member.add_roles(role, reason="Verified via Hypixel")
                        granted_role = role
                except discord.Forbidden:
                    role_error = "Missing permission to add role"
                except Exception as e:
                    role_error = str(e)
            else:
                role_error = "Verified role is higher or equal to bot's"

        # Step 5 - Logging
        if log_channel_id:
            ch = guild.get_channel(int(log_channel_id))
            if isinstance(ch, discord.TextChannel):
                await ch.send(embed=discord.Embed(
                    title="Verification Success",
                    description=(
                        f"User: {interaction.user.mention}\n"
                        f"IGN: **{ign}**\n"
                        f"Linked Discord: **{linked_tag}**\n"
                        f"Nickname set: {updated_nick} ({nick_error or 'OK'})\n"
                        f"Role granted: {granted_role.mention if granted_role else 'None'} ({role_error or 'OK'})"
                    ),
                    color=discord.Color.green()
                ))

        # Step 6 - Acknowledge
        parts = [f"✅ Verified **{ign}** (linked to your Discord)."]
        if updated_nick:
            parts.append("Nickname updated.")
        elif nick_error:
            parts.append(f"Nickname not updated: {nick_error}.")
        if granted_role:
            parts.append(f"Granted role {granted_role.mention}.")
        elif role_error:
            parts.append(f"Role not granted: {role_error}.")

        await interaction.followup.send(" ".join(parts), ephemeral=True)

class VerifyView(discord.ui.View):
    """Persistent view for the Verify button."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.primary,
        custom_id=VERIFY_BUTTON_CUSTOM_ID
    )
    async def open_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Send modal dynamically — modals are never persistent
        await interaction.response.send_modal(VerifyModal())
