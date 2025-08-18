# ===== Imports =====
import os
import logging
import importlib
import inspect
import discord
from dotenv import load_dotenv
from discord import app_commands

# ===== .env =====
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
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
intents.members = True          # you use member join + role assignment
intents.dm_messages = True      # you DM users for verification
intents.message_content = True  # if you rely on message content anywhere else

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
                            # Views must have a no-arg __init__ to be persisted at startup
                            self.add_view(obj())
                            print(f"✅ Loaded view: {obj.__name__}")
                        except Exception as e:
                            print(f"⚠ Failed to load view {obj.__name__}: {e}")

        # 2) Load commands and events
        for pkg in ("commands", "events"):
            pkg_path = f"./{pkg}"
            if not os.path.isdir(pkg_path):
                continue
            for fname in os.listdir(pkg_path):
                if fname.endswith(".py") and not fname.startswith("__"):
                    modname = f"{pkg}.{fname[:-3]}"
                    module = importlib.import_module(modname)
                    if hasattr(module, "setup"):
                        try:
                            await module.setup(self)
                            print(f"✅ Loaded {pkg} module: {modname}")
                        except Exception as e:
                            print(f"⚠ Failed to load {pkg} module {modname}: {e}")

        # 3) (Optional) one-time reset if your command list got messy:
        #self.tree.clear_commands(guild=None)  # uncomment once if you need a clean republish

        # 4) Sync commands globally
        try:
            synced = await self.tree.sync()
            names = [cmd.name for cmd in self.tree.get_commands()]
            print(f"🔁 Global sync -> {len(synced)} commands")
            print(len(names), names)
        except Exception as e:
            print(f"⚠ Command sync failed: {e}")

        # NOTE: Old per-command permissions API removed. Use:
        # - @app_commands.default_permissions(...) on admin-only commands for default visibility
        # - Your own role checks in code for execution (e.g., ADMIN_ROLES_IDS)
        # - Server Settings → Integrations → Commands for UI role visibility overrides

    async def on_ready(self):
        print(f"Logged on as {self.user}! (ID: {self.user.id})")

client = Client(intents=intents)

if __name__ == "__main__":
    client.run(TOKEN)
