# views/promotion_view.py
import re
import discord
from utils.config import get_guild_cfg

IGN_PATTERN = re.compile(r"IGN:\s*\*\*(.+?)\*\*", re.IGNORECASE)
RANK_PATTERN = re.compile(r"Target Rank:\s*\*\*(.+?)\*\*", re.IGNORECASE)

class PersistentPromotionApproveView(discord.ui.View):
    """
    Persistent approval view: parses IGN + target rank from the embed,
    and target member from the message mention. Works across bot restarts.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Approve Promotion",
        style=discord.ButtonStyle.success,
        custom_id="promo:approve"
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Permission check
        perms = interaction.user.guild_permissions
        if not (perms.manage_roles or perms.administrator):
            return await interaction.response.send_message(
                "You need **Manage Roles** to approve promotions.", ephemeral=True
            )

        msg = interaction.message
        if not msg or not msg.embeds:
            return await interaction.response.send_message("No embed found on this message.", ephemeral=True)

        embed = msg.embeds[0]
        desc = embed.description or ""
        m_ign = IGN_PATTERN.search(desc)
        m_rank = RANK_PATTERN.search(desc)
        if not m_ign or not m_rank:
            return await interaction.response.send_message("Missing IGN or target rank in the embed.", ephemeral=True)

        ign = m_ign.group(1).strip()
        role_name = m_rank.group(1).strip()

        if not msg.mentions:
            return await interaction.response.send_message("No target member mention found.", ephemeral=True)
        target_member = msg.mentions[0]

        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            return await interaction.response.send_message(
                f"Role **{role_name}** not found in this server.", ephemeral=True
            )

        me = interaction.guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await interaction.response.send_message("I need **Manage Roles** permission.", ephemeral=True)
        if role >= me.top_role:
            return await interaction.response.send_message(
                "Target role is higher than my top role. Adjust role hierarchy.", ephemeral=True
            )

        # Assign role
        try:
            if role not in target_member.roles:
                await target_member.add_roles(role, reason=f"Promotion approved by {interaction.user} (IGN {ign})")
        except discord.Forbidden:
            return await interaction.response.send_message("I don't have permission to edit that member.", ephemeral=True)

        # Log
        cfg = get_guild_cfg(interaction.guild_id)
        log_ch = interaction.guild.get_channel(int(cfg.get("log_channel_id") or 0))
        if log_ch:
            await log_ch.send(
                f"✅ **Promotion Approved** — {target_member.mention} → **{role.name}** "
                f"(IGN **{ign}**, by {interaction.user.mention}) • "
                f"[Jump]({msg.jump_url})"
            )

        await interaction.response.send_message(
            f"✅ Approved. Promoted {target_member.mention} to **{role.name}** (IGN **{ign}**).",
            ephemeral=False
        )

    @discord.ui.button(
        label="Reject",
        style=discord.ButtonStyle.danger,
        custom_id="promo:reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        perms = interaction.user.guild_permissions
        if not (perms.manage_roles or perms.administrator):
            return await interaction.response.send_message(
                "You need **Manage Roles** to reject promotions.", ephemeral=True
            )

        # Log
        cfg = get_guild_cfg(interaction.guild_id)
        log_ch = interaction.guild.get_channel(int(cfg.get("log_channel_id") or 0))
        msg = interaction.message
        embed = msg.embeds[0] if (msg and msg.embeds) else None
        ign = None
        role_name = None
        if embed:
            desc = embed.description or ""
            ig = IGN_PATTERN.search(desc)
            rk = RANK_PATTERN.search(desc)
            ign = ig.group(1).strip() if ig else None
            role_name = rk.group(1).strip() if rk else None

        if log_ch:
            await log_ch.send(
                f"❌ **Promotion Rejected** — IGN **{ign or 'Unknown'}**, "
                f"target rank **{role_name or 'Unknown'}** • by {interaction.user.mention} • "
                f"[Jump]({msg.jump_url if msg else ''})"
            )

        await interaction.response.send_message("❌ Promotion request rejected.", ephemeral=True)
