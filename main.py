import asyncio
import discord
from discord.ext import commands

import config
import database as db


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True
            ),
        )

    async def setup_hook(self):
        await db.init_db()
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.ai_handler")

        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self):
        print(f"[bot] logado como {self.user} (ID {self.user.id})")


async def main():
    bot = TicketBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())