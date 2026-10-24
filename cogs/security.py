import discord
from discord.ext import commands
import time
from collections import defaultdict

OWNER_ID = 875751530584748132

# Dicionário pra contar os strikes: {user_id: [timestamp1, timestamp2, ...]}
strikes = defaultdict(list)

class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora DMs e bots
        if not message.guild or message.author.bot:
            return

        # Se a mensagem não começar com o prefixo do bot, ignora
        if not message.content.startswith(self.bot.command_prefix):
            return

        # Se for o dono, deixa passar e zera os strikes dele (por garantia)
        if message.author.id == OWNER_ID:
            strikes[message.author.id].clear()
            return

        # --- LÓGICA DE PUNIÇÃO ---
        now = time.time()
        user_strikes = strikes[message.author.id]

        # Limpa strikes antigos (só conta se tentou nos últimos 5 minutos)
        user_strikes = [t for t in user_strikes if now - t < 300]
        
        # Adiciona o strike novo
        user_strikes.append(now)
        strikes[message.author.id] = user_strikes

        # 1. Apaga a mensagem do meliante (se tiver permissão)
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # 2. Se insistiu 3 vezes em menos de 5 minutos = Castigo
        if len(user_strikes) >= 3:
            try:
                # Aplica um timeout de 24 horas (86400 segundos)
                from datetime import timedelta
                await message.author.timeout(timedelta(days=1), reason="Insistência em usar comandos sem permissão.")
                
                await message.channel.send(
                    f"🔇 {message.author.mention} foi silenciado por 24 horas por insistir em usar comandos sem permissão.",
                    delete_after=10
                )
                strikes[message.author.id].clear() # Reseta os strikes após o castigo
            except discord.Forbidden:
                await message.channel.send(
                    f"❌ {message.author.mention}, você não tem permissão para usar comandos. (Não consegui aplicar o castigo por falta de permissão de Hierarquia).",
                    delete_after=10
                )
            except discord.HTTPException:
                pass
        else:
            # 3. Aviso padrão
            await message.channel.send(
                f"❌ {message.author.mention}, você não tem permissão para usar comandos.",
                delete_after=5
            )

async def setup(bot):
    await bot.add_cog(Security(bot))
