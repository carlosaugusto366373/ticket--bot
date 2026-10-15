import asyncio
import http.server
import os
import threading
import discord
from discord.ext import commands

import config
import database as db


# --- Servidor Web Nativo (Usa apenas o Python padrão, sem instalar nada) ---
class SimpleHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Discord online!")

    def log_message(self, format, *args):
        # Desativa os logs de requisição no terminal para ficar limpo
        pass


def run_web():
    port = int(os.environ.get("PORT", 10000))
    server_address = ("0.0.0.0", port)
    httpd = http.server.HTTPServer(server_address, SimpleHandler)
    httpd.serve_forever()


# --- Configuração do Bot do Discord ---
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
    # Inicia o servidor web em segundo plano para o Render ver a porta aberta
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

    # Inicia o bot do Discord normalmente
    bot = TicketBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
