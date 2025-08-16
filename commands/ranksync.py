# commands/ranksync.py
import os, discord
from discord import app_commands
from utils.config import get_guild_cfg, set_guild_cfg
from utils.hypixel_api import username_to_uuid, hypixel_guild_by_player

# Hypixel rank names you commonly see in guilds. You can extend this list.
KNOWN_GUILD_RANKS = ["Guild Master", "Admin", "Masters", "Dominus", "Legatus", "Primus"]

async def setup(client: discord.Client):
    tree = client.tree

    # ===== User command: /ranksync =====
    @tree.command(name="ranksync", description="Sync your Hypixel Guild rank to the mapped Discord role")
    async def ranksync(interaction: discord.Interaction, minecraft_username: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        api_key = os.getenv("HYPIXEL_API_KEY")
        if not api_key:
            return await interaction.followup.send("Configuration error: HYPIXEL_API_KEY missing.", ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Run this command in a server.", ephemeral=True)

        # 1) username -> uuid
        uuid = await username_to_uuid(minecraft_username)
        if not uuid:
            return await interaction.followup.send(f"I couldn't find **{minecraft_username}** on Mojang.", ephemeral=True)

        # 2) guild lookup by player
        guild = await hypixel_guild_by_player(uuid, api_key)
        if not guild:
            return await interaction.followup.send("You are not in a Hypixel Guild.", ephemeral=True)

        # 3) find member entry for this uuid
        members = guild.get("members") or []
        me = next((m for m in members if (m.get("uuid") or "").replace("-", "") == uuid), None)
        if not me:
            return await interaction.followup.send("Could not locate you in the guild member list.", ephemeral=True)

        hyp_rank = (me.get("rank") or "").strip().upper()
        if not hyp_rank:
            return await interaction.followup.send("Your guild rank could not be determined.", ephemeral=True)

        # 4) map to Discord role via config
        cfg = get_guild_cfg(interaction.guild_id)
        mapping: dict = cfg.get("rank_role_map") or {}
        role_id = mapping.get(hyp_rank)
        if not role_id:
            # Suggest the closest configured ranks
            available = ", ".join(sorted(mapping.keys())) or "none configured"
            return await interaction.followup.send(
                f"No role is mapped for your guild rank **{hyp_rank}**.\n"
                f"Ask an admin to map it with `/ranksync_map`.\n"
                f"Currently configured: {available}.",
                ephemeral=True
            )

        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.followup.send("The mapped Discord role no longer exists. Ask an admin to remap.", ephemeral=True)

        # 5) apply role (and optionally remove other mapped roles)
        # ensure bot can manage the role
        if not interaction.guild.me.guild_permissions.manage_roles:  # type: ignore
            return await interaction.followup.send("I need **Manage Roles** permission.", ephemeral=True)
        if role >= interaction.guild.me.top_role:  # type: ignore
            return await interaction.followup.send("The target role is higher than my top role. Adjust role hierarchy.", ephemeral=True)

        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return await interaction.followup.send("Could not fetch your member object.", ephemeral=True)

        # Remove any other roles that are part of the mapping to keep things clean
        mapped_role_ids = set(int(v) for v in mapping.values() if v)
        roles_to_remove = [r for r in member.roles if r.id in mapped_role_ids and r.id != int(role_id)]

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="RankSync cleanup")
            if role not in member.roles:
                await member.add_roles(role, reason=f"RankSync: {hyp_rank}")
        except discord.Forbidden:
            return await interaction.followup.send("I don't have permission to edit your roles.", ephemeral=True)

        removed_str = ", ".join(r.name for r in roles_to_remove) if roles_to_remove else "none"
        await interaction.followup.send(
            f"✅ Rank synced: **{hyp_rank}** → {role.mention} (removed: {removed_str}).",
            ephemeral=True
        )

    # ===== Admin: map a Hypixel guild rank to a Discord role =====
    @tree.command(name="ranksync_map", description="Map a Hypixel Guild rank to a Discord role (admin)")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(hypixel_guild_rank="Exact rank text as shown by Hypixel (case-insensitive)")
    async def ranksync_map(
        interaction: discord.Interaction,
        hypixel_guild_rank: str,
        role: discord.Role
    ):
        hyp_rank = hypixel_guild_rank.strip().upper()
        cfg = get_guild_cfg(interaction.guild_id)
        mapping = dict(cfg.get("rank_role_map") or {})
        mapping[hyp_rank] = role.id
        set_guild_cfg(interaction.guild_id, rank_role_map=mapping)
        await interaction.response.send_message(
            f"Mapped Hypixel rank **{hyp_rank}** → {role.mention}.", ephemeral=True
        )

    # (optional) autocomplete common ranks
    @ranksync_map.autocomplete("hypixel_guild_rank")  # type: ignore
    async def ac_rank(interaction: discord.Interaction, current: str):
        current_up = (current or "").upper()
        choices = [app_commands.Choice(name=r, value=r) for r in KNOWN_GUILD_RANKS if current_up in r]
        return choices[:25]

    # ===== Admin: show / clear mappings =====
    @tree.command(name="ranksync_show", description="Show current guild rank → role mappings")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def ranksync_show(interaction: discord.Interaction):
        cfg = get_guild_cfg(interaction.guild_id)
        mapping: dict = cfg.get("rank_role_map") or {}
        if not mapping:
            return await interaction.response.send_message("No mappings configured.", ephemeral=True)
        lines = []
        for k, v in sorted(mapping.items()):
            role = interaction.guild.get_role(int(v))
            lines.append(f"**{k}** → {role.mention if role else f'`{v}` (missing)'}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tree.command(name="ranksync_clear", description="Remove a mapping for a Hypixel guild rank (admin)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def ranksync_clear(interaction: discord.Interaction, hypixel_guild_rank: str):
        hyp_rank = hypixel_guild_rank.strip().upper()
        cfg = get_guild_cfg(interaction.guild_id)
        mapping: dict = dict(cfg.get("rank_role_map") or {})
        if hyp_rank in mapping:
            mapping.pop(hyp_rank)
            set_guild_cfg(interaction.guild_id, rank_role_map=mapping)
            return await interaction.response.send_message(f"Removed mapping for **{hyp_rank}**.", ephemeral=True)
        await interaction.response.send_message("No mapping found for that rank.", ephemeral=True)
