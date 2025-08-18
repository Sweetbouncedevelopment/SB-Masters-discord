# commands/getroles.py
import os
import aiohttp
import discord
from discord import app_commands, AllowedMentions
from discord.errors import HTTPException
from utils.checks import is_guild_admin
from utils.role_config import load_role_config
from utils.hypixel_api import get_sb_stats
from utils.config import get_guild_cfg
from views.promotion_view import PersistentPromotionApproveView  # MUST be timeout=None, has custom_ids

# Read mode/bridge from environment
PROMOTION_MODE = (os.getenv("PROMOTION_MODE") or "discord-only").strip().lower()
PROMOTION_BRIDGE_URL = os.getenv("PROMOTION_BRIDGE_URL")
PROMOTION_BRIDGE_TOKEN = os.getenv("PROMOTION_BRIDGE_TOKEN")  # optional

VALID_MODES = {"discord-only", "auto-mc"}
if PROMOTION_MODE not in VALID_MODES:
    PROMOTION_MODE = "discord-only"  # safe default

MAX_CONTENT = 2000


def _trim(s: str, limit: int) -> str:
    s = str(s)
    return s if len(s) <= limit else s[:limit - 1] + "…"


async def _send_with_log(op: str, coro, log_ch: discord.TextChannel | None):
    """Run a Discord API call; on failure, log status/code/text to log_ch."""
    try:
        return await coro
    except HTTPException as ex:
        if log_ch:
            status = getattr(ex, "status", "?")
            code = getattr(ex, "code", "?")
            text = getattr(ex, "text", str(ex))
            await log_ch.send(_trim(f"⚠ {op} failed — HTTP {status} / code {code}:\n{text}", MAX_CONTENT))
        return None


async def safe_queue_send(
    queue: discord.TextChannel,
    who: discord.abc.User,
    embed: discord.Embed,
    view: discord.ui.View | None,
    log_ch: discord.TextChannel | None
):
    """
    Send to queue safely: embed+view first (empty content), then tiny ping.
    Falls back to minimal message if Discord rejects. Logs details.
    """
    allowed = AllowedMentions(everyone=False, users=[who], roles=False, replied_user=False)

    msg = await _send_with_log(
        "queue.send(embed+view)",
        queue.send(content="", embed=embed, view=view, allowed_mentions=allowed),
        log_ch
    )
    if msg is None:
        # last-resort fallback: minimal text only
        note = _trim(f"{who.mention} Promotion request created (embed/view trimmed).", MAX_CONTENT)
        msg = await _send_with_log("queue.send(text-only)", queue.send(content=note, allowed_mentions=allowed), log_ch)

    # tiny separate ping (kept under 2k; okay to skip if it fails)
    await _send_with_log("queue.send(mention)", queue.send(content=who.mention, allowed_mentions=allowed), log_ch)
    return msg


async def setup(client: discord.Client):
    # ✅ Register the persistent view on startup so components are recognized by Discord
    # Your PersistentPromotionApproveView must set timeout=None and define explicit custom_id values.
    try:
        client.add_view(PersistentPromotionApproveView())
    except Exception:
        # If your view needs runtime params, consider registering a "blank" version here
        # and constructing per-message instances later.
        pass

    tree = client.tree

    @tree.command(
        name="promote",
        description="Evaluate requirements and request a promotion (discord-only or auto-mc depending on env)"
    )
    @is_guild_admin()
    async def promote(
        interaction: discord.Interaction,
        username: str,
        member: discord.Member | None = None
    ):
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

        # 4) Modes
        mode = PROMOTION_MODE

        if mode == "discord-only":
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

            # Build trimmed embed (stay within Discord limits)
            e = discord.Embed(
                title=_trim("Promotion Request", 256),
                description=_trim(f"IGN: **{username}**\nTarget Rank: **{role_name}**", 4096),
                color=discord.Color.green()
            )
            e.add_field(name="Masteries", value=_trim(str(mastery_count), 1024))
            e.add_field(name="SB Level", value=_trim(str(stats["sb_level"]), 1024))
            e.add_field(name="Skill Avg", value=_trim(str(stats["skill_avg"]), 1024))
            e.add_field(name="Cata", value=_trim(str(stats["cata_lvl"]), 1024))
            e.add_field(name="Slayer XP", value=_trim(f"{stats['slayer_xp']:,}", 1024))
            e.add_field(name="Networth", value=_trim(f"{stats['networth']:,}", 1024))
            e.add_field(name="Farm Weight", value=_trim(f"{stats['farm_weight']:,}", 1024))
            e.add_field(name="Rift Charms", value=_trim("All" if stats["rift_all_charms"] else "Incomplete", 1024))
            e.set_footer(text=_trim(f"Requested by {interaction.user}", 2048))

            # Create the view instance you want to attach (must use custom_id per item)
            view = PersistentPromotionApproveView()

            msg = await safe_queue_send(queue, who, e, view, log_ch)

            # Log queued request
            if log_ch and msg:
                await log_ch.send(
                    _trim(
                        f"📬 **Promotion Queued** — {who.mention} | IGN **{username}** → **{role_name}** • [Jump]({msg.jump_url})",
                        MAX_CONTENT
                    )
                )

            return await interaction.followup.send("✅ Queued promotion for approval.", ephemeral=True)

        elif mode == "auto-mc":
            bridge_url = PROMOTION_BRIDGE_URL
            if not bridge_url:
                return await interaction.followup.send(
                    "⚠ `PROMOTION_BRIDGE_URL` not set in environment.",
                    ephemeral=True
                )

            target_member = member or interaction.guild.get_member(interaction.user.id)

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

            if log_ch:
                log_body = (body[:1800] + "…") if len(body) > 1800 else body
                prefix = "🤖 **Auto-MC Promote**" if ok else "⚠ **Auto-MC Promote FAILED**"
                await log_ch.send(
                    _trim(
                        f"{prefix} — IGN **{username}** → **{role_name}** • requested by {interaction.user.mention}\n"
                        f"Bridge response: `{log_body}`",
                        MAX_CONTENT
                    )
                )

            if not ok:
                return await interaction.followup.send(
                    _trim(f"⚠ Auto-MC bridge error.\n```text\n{body[:1500]}\n```", MAX_CONTENT),
                    ephemeral=True
                )

            if target_role and target_member:
                try:
                    await target_member.add_roles(target_role, reason=f"Auto-MC promote to {role_name}")
                except discord.Forbidden:
                    if log_ch:
                        await log_ch.send(
                            _trim(
                                f"⚠ Could not assign Discord role **{role_name}** to {target_member.mention} "
                                f"(insufficient permissions).",
                                MAX_CONTENT
                            )
                        )

            await interaction.followup.send(
                _trim(f"✅ Auto-promoted **{username}** in Hypixel (target rank: **{role_name}**).", MAX_CONTENT),
                ephemeral=False
            )
            return

        else:
            return await interaction.followup.send(
                _trim(f"Unknown promotion mode in env: `{mode}`. Use `discord-only` or `auto-mc`.", MAX_CONTENT),
                ephemeral=True
            )
