
import asyncio
import http.server
import os
import threading
import time
import socket
from collections import deque
from ipaddress import ip_address

import discord
from discord.ext import commands

import config
import database as db


# ==========================================
# CONFIGURAÇÕES DO SERVIDOR WEB - RENDER
# ==========================================

RATE_LIMIT_WINDOW = 60
MAX_REQUESTS_ALLOWED = 60

MAX_HTTP_THREADS = 32
CONNECTION_TIMEOUT = 5
MAX_TRACKED_IPS = 10000

ip_requests = {}
rate_limit_lock = threading.Lock()


def get_client_ip(handler):
    """
    O Render fica atrás de um proxy.
    Usa X-Forwarded-For quando disponível.
    """

    forwarded_for = handler.headers.get("X-Forwarded-For")

    if forwarded_for:
        # O cabeçalho deve ser confiável somente quando
        # a origem da requisição é um proxy confiável.
        candidate = forwarded_for.split(",")[0].strip()

        try:
            return str(ip_address(candidate))
        except ValueError:
            pass

    return handler.client_address[0]


def is_rate_limited(client_ip):
    now = time.monotonic()

    with rate_limit_lock:
        requests = ip_requests.get(client_ip)

        if requests is None:
            # Evita crescimento ilimitado do dicionário.
            if len(ip_requests) >= MAX_TRACKED_IPS:
                expired_before = now - RATE_LIMIT_WINDOW

                for ip in list(ip_requests):
                    history = ip_requests[ip]

                    while history and history[0] <= expired_before:
                        history.popleft()

                    if not history:
                        del ip_requests[ip]

                    if len(ip_requests) < MAX_TRACKED_IPS:
                        break

                # Se ainda estiver cheio, não armazena
                # um novo IP. A infraestrutura também
                # deve proteger o serviço contra abuso.
                if len(ip_requests) >= MAX_TRACKED_IPS:
                    return True

            requests = deque()
            ip_requests[client_ip] = requests

        cutoff = now - RATE_LIMIT_WINDOW

        while requests and requests[0] <= cutoff:
            requests.popleft()

        if len(requests) >= MAX_REQUESTS_ALLOWED:
            return True

        requests.append(now)
        return False


class SimpleHandler(http.server.BaseHTTPRequestHandler):

    server_version = "HealthCheck"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(CONNECTION_TIMEOUT)

    def do_GET(self):
        client_ip = get_client_ip(self)

        if is_rate_limited(client_ip):
            self.respond(
                429,
                b"Muitas requisicoes. Tente novamente mais tarde."
            )
            return

        self.respond(200, b"Bot Discord online!")

    def respond(self, status, body):
        try:
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close_connection = True

    def log_message(self, format, *args):
        pass


class ProtectedHTTPServer(http.server.ThreadingHTTPServer):
    """
    Limita a quantidade de threads HTTP simultâneas.
    """

    daemon_threads = True
    request_queue_size = 64

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.thread_slots = threading.BoundedSemaphore(
            MAX_HTTP_THREADS
        )

    def process_request(self, request, client_address):
        if not self.thread_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return

        try:
            super().process_request(request, client_address)
        except Exception:
            self.thread_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.thread_slots.release()


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    server_address = ("0.0.0.0", port)

    try:
        with ProtectedHTTPServer(
            server_address, SimpleHandler
        ) as httpd:
            print(f"[web] Servidor HTTP ativo na porta {port}")
            httpd.serve_forever(poll_interval=0.5)

    except Exception as error:
        print(f"[web] Erro no servidor HTTP: {error}")
        raise


# ==========================================
# CONFIGURAÇÃO DO BOT DISCORD
# ==========================================

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
                everyone=False,
                roles=False,
                users=True
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
        print(
            f"[bot] logado como {self.user} "
            f"(ID {self.user.id})"
        )


async def main():
    web_thread = threading.Thread(
        target=run_web,
        name="render-health-server",
        daemon=True
    )
    web_thread.start()

    bot = TicketBot()

    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
