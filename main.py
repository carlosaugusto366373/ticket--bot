import asyncio
import http.server
import threading
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

import config
import database as db


# =========================
# CONFIGURAÇÕES DO SERVIDOR
# =========================

RATE_LIMIT_WINDOW = 60
MAX_REQUESTS_ALLOWED = 60
MAX_TRACKED_IPS = 10000
MAX_HTTP_THREADS = 32
CONNECTION_TIMEOUT = 5
REQUEST_QUEUE_SIZE = 64

ip_requests = defaultdict(deque)
rate_limit_lock = threading.Lock()


# =========================
# CONTROLE DE REQUISIÇÕES
# =========================

def get_client_ip(handler):
    """
    Obtém o IP informado pelo proxy ou o IP da conexão.
    X-Forwarded-For só deve ser confiável quando definido
    por um proxy confiável que controle esse cabeçalho.
    """
    forwarded_for = handler.headers.get("X-Forwarded-For", "")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return handler.client_address[0]


def is_rate_limited(client_ip):
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW

    with rate_limit_lock:
        # Remove registros antigos de todos os IPs.
        expired_ips = []

        for ip, timestamps in ip_requests.items():
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if not timestamps:
                expired_ips.append(ip)

        for ip in expired_ips:
            ip_requests.pop(ip, None)

        # Evita crescimento ilimitado do dicionário.
        if client_ip not in ip_requests:
            if len(ip_requests) >= MAX_TRACKED_IPS:
                return True

        timestamps = ip_requests[client_ip]

        if len(timestamps) >= MAX_REQUESTS_ALLOWED:
            return True

        timestamps.append(now)
        return False


# =========================
# SERVIDOR HTTP / UPTIMEROBOT
# =========================

class SimpleHandler(http.server.BaseHTTPRequestHandler):

    server_version = "HealthCheck"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(CONNECTION_TIMEOUT)

    def do_GET(self):
        self.handle_health_check(send_body=True)

    def do_HEAD(self):
        # HEAD retorna os mesmos cabeçalhos de GET,
        # mas não envia o corpo da resposta.
        self.handle_health_check(send_body=False)

    def handle_health_check(self, send_body):
        client_ip = get_client_ip(self)

        if is_rate_limited(client_ip):
            status = 429
            body = b"Too Many Requests"
        else:
            status = 200
            body = b"Bot Discord online!"

        self.respond(status, body, send_body)

    def respond(self, status, body, send_body=True):
        try:
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            if send_body:
                self.wfile.write(body)

        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            self.close_connection = True

    def log_message(self, format, *args):
        # Evita registrar cada requisição no log do Render.
        pass


# =========================
# LIMITE DE CONEXÕES HTTP
# =========================

class ProtectedHTTPServer(http.server.ThreadingHTTPServer):

    daemon_threads = True
    request_queue_size = REQUEST_QUEUE_SIZE

    def __init__(self, server_address, handler_class):
        self.connection_slots = threading.BoundedSemaphore(
            MAX_HTTP_THREADS
        )
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        # Não cria threads ilimitadas se houver excesso de conexões.
        if not self.connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return

        try:
            super().process_request(request, client_address)
        except Exception:
            self.connection_slots.release()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


def run_web():
    port = int(__import__("os").environ.get("PORT", "10000"))

    server = ProtectedHTTPServer(
        ("0.0.0.0", port),
        SimpleHandler
    )

    print(f"[web] Servidor HTTP ativo na porta {port}", flush=True)

    try:
        server.serve_forever()
    finally:
        server.server_close()


# =========================
# BOT DO DISCORD
# =========================

class TicketBot(commands.Bot):

    async def setup_hook(self):
        print("[bot] Inicializando banco de dados...", flush=True)

        await db.init_db()

        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.ai_handler")
        await self.load_extension("cogs.ticket_guard")
        await self.load_extension("cogs.admin_tools") # <--- ADICIONADO AQUI

        guild_id = int(config.GUILD_ID)
        guild = discord.Object(id=guild_id)

        # Sincroniza os comandos para o servidor configurado.
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        print("[bot] Cogs carregados e comandos sincronizados.", flush=True)

    async def on_ready(self):
        print(f"[bot] Logado como {self.user}", flush=True)


def create_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    return TicketBot(
        command_prefix="!",
        intents=intents
    )


# =========================
# INICIALIZAÇÃO
# =========================

async def main():
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )
    web_thread.start()

    bot = create_bot()

    try:
        await bot.start(config.DISCORD_TOKEN)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
