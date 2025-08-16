# ===== Imports =====
import os
import logging
import importlib
import inspect
import discord
from dotenv import load_dotenv
from discord import app_commands
from utils.checks import ADMIN_ROLE_IDS

# ===== .env =====
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing in .env")

# ===== Logging =====
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logger.addHandler(file_handler)

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.dm_messages = True
intents.message_content = True

# ===== Client =====
class Client(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 1) Auto-load persistent views
        for fname in os.listdir("./views"):
            if fname.endswith(".py") and not fname.startswith("__"):
                modname = f"views.{fname[:-3]}"
                module = importlib.import_module(modname)
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, discord.ui.View) and obj is not discord.ui.View:
                        try:
                            self.add_view(obj())
                            print(f"✅ Loaded view: {obj.__name__}")
                        except Exception as e:
                            print(f"⚠ Failed to load view {obj.__name__}: {e}")

        # 2) Load commands and events
        for pkg in ("commands", "events"):
            for fname in os.listdir(f"./{pkg}"):
                if fname.endswith(".py") and not fname.startswith("__"):
                    modname = f"{pkg}.{fname[:-3]}"
                    module = importlib.import_module(modname)
                    if hasattr(module, "setup"):
                        await module.setup(self)

        # 3) Sync commands globally
        synced = await self.tree.sync()
        print(f"🔁 Global sync -> {len(synced)} commands")
        print(len(self.tree.get_commands()), [cmd.name for cmd in self.tree.get_commands()])


        # 4) Update visibility for admin-only commands
        admin_only_cmds = {
            "verification_setup",
            "verification_reset",
            "verification_settings",
            "setuplogs",
            "logtest",
            "sync"
        }
        for guild in self.guilds:
            for cmd in synced:
                if cmd.name in admin_only_cmds:
                    perms = []
                    for rid in ADMIN_ROLE_IDS:
                        perms.append(app_commands.CommandPermission(
                            id=rid, type=1, permission=True
                        ))
                    perms.append(app_commands.CommandPermission(
                        id=guild.default_role.id, type=1, permission=False
                    ))
                    try:
                        await self.tree.set_command_permissions(guild.id, cmd.id, perms)
                        print(f"✅ Set permissions for '{cmd.name}' in {guild.name}")
                    except Exception as e:
                        print(f"⚠ Could not set permissions for '{cmd.name}' in {guild.name}: {e}")

    async def on_ready(self):
        print(f"Logged on as {self.user}! (ID: {self.user.id})")

client = Client(intents=intents)

if __name__ == "__main__":
    client.run(TOKEN)
