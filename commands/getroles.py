# commands/getroles.py
import aiohttp
import discord
from discord import app_commands
from utils.checks import is_guild_admin
from utils.role_config import load_role_config
from utils.hypixel_api import get_sb_stats
from utils.config import get_guild_cfg
from views.promotion_view import PersistentPromotionApproveView  # approval UI for discord-only mode

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(
        name="getroles",
        description="Evaluate requirements and promote (discord-only or auto-mc depending on config)"
    )
    @is_guild_admin()
    async def getroles(
        interaction: discord.Interaction,
        username: str,
        member: discord.Member | None = None
    ):
        """Check stats, decide rank, and either queue approval or auto-promote via bridge."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        cfg_data = load_role_config()
        mode = (cfg_data.get("mode") or "discord-only").strip().lower()
        reqs = cfg_data["requirements"]
        rank_thresholds = {int(k): v for k, v in cfg_data["mastery_ranks"].items()}

        # 1) Fetch SkyBlock stats
        try:
            stats = await get_sb_stats(username)
        except Exception as e:
            return await interaction.followup.send(f"Error fetching stats: {e}", ephemeral=True)

        # 2) Check requirements
        failed = []
        if stats["networth"] < reqs["networth"]: failed.append(f"Networth < {reqs['networth']:,}")
        if stats["sb_level"] < reqs["sb_level"]: failed.append(f"SB Level < {reqs['sb_level']}")
        if stats["skill_avg"] < reqs["skill_avg"]: failed.append(f"Skill Avg < {reqs['skill_avg']}")
        if stats["slayer_xp"] < reqs["slayer_xp"]: failed.append(f"Slayer XP < {reqs['slayer_xp']:,}")
        if stats["cata_lvl"] < reqs["cata_lvl"]: failed.append(f"Cata Lvl < {reqs['cata_lvl']}")
        if reqs["rift_charms"] == "all" and not stats["rift_all_charms"]: failed.append("Rift charms incomplete")
        if stats["farm_weight"] < reqs["farm_weight"]: failed.append(f"Farm Weight < {reqs['farm_weight']:,}")

        if failed:
            return await interaction.followup.send(
                "❌ Requirements not met:\n- " + "\n- ".join(failed),
                ephemeral=True
            )

        # 3) Determine mastery → rank
        mastery_count = stats["masteries"]
        role_name = None
        for threshold, rank in sorted(rank_thresholds.items(), reverse=True):
            if mastery_count >= threshold:
                role_name = rank
                break
        if not role_name:
            return await interaction.followup.send(
                "No rank mapping found for your mastery count.", ephemeral=True
            )

        # Resolve Discord role (optional in discord-only; used in auto-mc to mirror role)
        target_role = discord.utils.get(interaction.guild.roles, name=role_name)
        target_role_id = target_role.id if target_role else None

        # 4) Modes
        if mode == "discord-only":
            # Post approval card in the configured promotion queue channel
            gcfg = get_guild_cfg(interaction.guild_id)
            queue_id = gcfg.get("promotion_channel_id")
            if not queue_id:
                return await interaction.followup.send(
                    "No promotion queue channel set. Run `/setuppromotions #channel` first.",
                    ephemeral=True
                )
            queue = interaction.guild.get_channel(int(queue_id))
            if not isinstance(queue, discord.TextChannel):
                return await interaction.followup.send("Promotion channel invalid.", ephemeral=True)

            who = (member or interaction.user)
            e = discord.Embed(
                title="Promotion Request",
                description=f"IGN: **{username}**\nTarget Rank: **{role_name}**",
                color=discord.Color.green()
            )
            e.add_field(name="Masteries", value=str(mastery_count))
            e.add_field(name="SB Level", value=str(stats["sb_level"]))
            e.add_field(name="Skill Avg", value=str(stats["skill_avg"]))
            e.add_field(name="Cata", value=str(stats["cata_lvl"]))
            e.add_field(name="Slayer XP", value=f"{stats['slayer_xp']:,}")
            e.add_field(name="Networth", value=f"{stats['networth']:,}")
            e.add_field(name="Farm Weight", value=f"{stats['farm_weight']:,}")
            e.add_field(name="Rift Charms", value="All" if stats["rift_all_charms"] else "Incomplete")
            e.set_footer(text=f"Requested by {interaction.user}")

            # Mention the target Discord member so the Approve handler can grant role
            view = PersistentPromotionApproveView(ign=username, role_id=target_role_id)
            await queue.send(content=who.mention, embed=e, view=view)
            return await interaction.followup.send("✅ Queued promotion for approval.", ephemeral=True)

        elif mode == "auto-mc":
            # Call your bridge microservice to run /g promote IGN in-game (⚠ risky)
            bridge_url = cfg_data.get("bridge_url")
            if not bridge_url:
                return await interaction.followup.send("⚠ bridge_url not set in config.", ephemeral=True)

            # a) Call the bridge
            try:
                async with aiohttp.ClientSession() as session:
                    resp = await session.post(bridge_url, json={"ign": username}, timeout=10)
                    ok = (resp.status == 200)
                    body = await resp.text()
            except Exception as e:
                ok, body = False, f"{e}"

            if not ok:
                return await interaction.followup.send(
                    f"⚠ Auto-MC bridge error: {body}", ephemeral=True
                )

            # b) Mirror the Discord role locally (optional)
            if target_role:
                target_member = member or interaction.guild.get_member(interaction.user.id)
                try:
                    if target_member:
                        await target_member.add_roles(target_role, reason=f"Auto-MC promote to {role_name}")
                except discord.Forbidden:
                    pass

            await interaction.followup.send(
                f"✅ Auto-promoted **{username}** in Hypixel (target rank: **{role_name}**).",
                ephemeral=False
            )
            return

        else:
            return await interaction.followup.send(
                f"Unknown promotion mode: `{mode}`. Use `discord-only` or `auto-mc` in config.",
                ephemeral=True
            )
