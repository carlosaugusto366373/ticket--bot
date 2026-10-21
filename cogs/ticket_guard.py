# cogs/ticket_guard.py
import discord
from discord.ext import commands
from config import CATEGORY_ID

BLOCKED_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus",
    ".mp4", ".mov", ".webm", ".mkv", ".avi",
}

MSG_AVISO = "Áudio não é permitido em tickets. Descreva sua dúvida por texto, por favor."

class TicketAudioGuard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_ticket(self, channel: discord.abc.GuildChannel) -> bool:
        # Verifica se o canal está na categoria de tickets configurada no .env
        return getattr(channel, "category_id", None) == CATEGORY_ID

    def _has_blocked_attachment(self, message: discord.Message) -> bool:
        for att in message.attachments:
            name = (att.filename or "").lower()
            ctype = (att.content_type or "").lower()

            if ctype.startswith("audio/") or ctype.startswith("video/"):
                return True
            if any(name.endswith(ext) for ext in BLOCKED_EXTENSIONS):
                return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora DMs, bots e o próprio bot
        if message.guild is None or message.author.bot:
            return

        # Se não for ticket, ignora
        if not self._is_ticket(message.channel):
            return

        # Verifica se é áudio (mensagem de voz do Discord ou anexo de áudio/vídeo)
        is_voice = message.flags and message.flags.voice
        is_file = self._has_blocked_attachment(message)

        if not (is_voice or is_file):
            return

        # Tenta apagar a mensagem
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass  # Se não tiver permissão, apenas ignora

        # Manda o aviso (que some em 8 segundos pra não sujar o ticket)
        try:
            await message.channel.send(
                f"{message.author.mention} {MSG_AVISO}",
                delete_after=8
            )
        except discord.HTTPException:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketAudioGuard(bot))
