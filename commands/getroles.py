# commands/getroles.py
import os
import aiohttp
import discord
from discord import app_commands
from utils.checks import is_guild_admin
from utils.role_config import load_role_config
from utils.hypixel_api import get_sb_stats
from utils.config import get_guild_cfg
from views.promotion_view import PersistentPromotionApproveView  # approval UI for discord-only mode

# Read mode/bridge from environment
PROMOTION_MODE = (os.getenv("PROMOTION_MODE") or "discord-only").strip().lower()
PROMOTION_BRIDGE_URL = os.getenv("PROMOTION_BRIDGE_URL")
PROMOTION_BRIDGE_TOKEN = os.getenv("PROMOTION_BRIDGE_TOKEN")  # optional

VALID_MODES = {"discord-only", "auto-mc"}
if PROMOTION_MODE not in VALID_MODES:
    PROMOTION_MODE = "discord-only"  # safe default

async def setup(client: discord.Client):
    tree = client.tree

    @tree.command(
        name="promote",  # change to "getroles" if you want to keep the old name
        description="Evaluate requirements and request a promotion (discord-only or auto-mc depending on env)"
    )
    @is_guild_admin()
    async def promote(
        interaction: discord.Interaction,
        username: str,
        member: discord.Member | None = None
    ):
        """Check stats, decide rank, and either queue approval or auto-promote via bridge."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        cfg_data = load_role_config()
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

        # For logs
        gcfg = get_guild_cfg(interaction.guild_id)
        log_ch = interaction.guild.get_channel(int(gcfg.get("log_channel_id") or 0))

        # 4) Modes (now from ENV)
        mode = PROMOTION_MODE

        if mode == "discord-only":
            # Post approval card in the configured promotion queue channel
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
            view = PersistentPromotionApproveView()  # as required by your view implementation:contentReference[oaicite:1]{index=1}
            msg = await queue.send(content=who.mention, embed=e, view=view)

            # Log queued request
            if log_ch:
                await log_ch.send(
                    f"📬 **Promotion Queued** — {who.mention} | IGN **{username}** → **{role_name}** • [Jump]({msg.jump_url})"
                )

            return await interaction.followup.send("✅ Queued promotion for approval.", ephemeral=True)

        elif mode == "auto-mc":
            bridge_url = PROMOTION_BRIDGE_URL
            if not bridge_url:
                return await interaction.followup.send(
                    "⚠ `PROMOTION_BRIDGE_URL` not set in environment.",
                    ephemeral=True
                )

            # Default target Discord member (for mirroring role)
            target_member = member or interaction.guild.get_member(interaction.user.id)

            # Bridge payload
            payload = {
                "action": "promote",
                "ign": username,
                "target_rank": role_name,
                "requested_by_discord_id": str(interaction.user.id),
                "requested_by_discord_tag": str(interaction.user),
                "guild_id": str(interaction.guild_id)
            }

            headers = {}
            if PROMOTION_BRIDGE_TOKEN:
                headers["Authorization"] = f"Bearer {PROMOTION_BRIDGE_TOKEN}"

            ok = False
            body = ""
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(bridge_url, json=payload, headers=headers, timeout=15) as resp:
                        body = await resp.text()
                        ok = (200 <= resp.status < 300)
            except Exception as e:
                body = f"{e}"

            # Log outcome to log channel
            if log_ch:
                if ok:
                    await log_ch.send(
                        f"🤖 **Auto-MC Promote** — IGN **{username}** → **{role_name}** • "
                        f"requested by {interaction.user.mention}\n"
                        f"Bridge response: `{(body[:1800] + '…') if len(body) > 1800 else body}`"
                    )
                else:
                    await log_ch.send(
                        f"⚠ **Auto-MC Promote FAILED** — IGN **{username}** → **{role_name}** • "
                        f"requested by {interaction.user.mention}\n"
                        f"Bridge response: `{(body[:1800] + '…') if len(body) > 1800 else body}`"
                    )

            if not ok:
                return await interaction.followup.send(
                    f"⚠ Auto-MC bridge error.\n```text\n{body[:1500]}\n```",
                    ephemeral=True
                )

            # Mirror the Discord role locally (optional)
            if target_role and target_member:
                try:
                    await target_member.add_roles(target_role, reason=f"Auto-MC promote to {role_name}")
                except discord.Forbidden:
                    if log_ch:
                        await log_ch.send(
                            f"⚠ Could not assign Discord role **{role_name}** to {target_member.mention} "
                            f"(insufficient permissions)."
                        )

            await interaction.followup.send(
                f"✅ Auto-promoted **{username}** in Hypixel (target rank: **{role_name}**).",
                ephemeral=False
            )
            return

        else:
            return await interaction.followup.send(
                f"Unknown promotion mode in env: `{mode}`. Use `discord-only` or `auto-mc`.",
                ephemeral=True
            )
