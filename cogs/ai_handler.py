import discord
from discord.ext import commands
from openai import AsyncOpenAI
import config
import database as db

client = AsyncOpenAI(
    api_key=config.GROQ_API_KEY,
    base_url=config.GROQ_BASE_URL,
)


class AIHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def generate_reply(self, ticket_id: int, user_message: str,
                             category: str) -> str:
        history = await db.get_history(ticket_id, limit=20)

        messages = [
            {"role": "system", "content": config.build_system_prompt()},
            {"role": "system", "content": f"Categoria do ticket: {category}"},
        ]

        for row in history:
            role = "assistant" if row["is_bot"] else "user"
            messages.append({"role": role, "content": row["content"]})

        if not messages or messages[-1]["content"] != user_message:
            messages.append({"role": "user", "content": user_message})

        try:
            resp = await client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=messages,
                temperature=0.6,
                max_tokens=600,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"⚠️ Erro ao consultar IA: `{e}`"

    async def first_contact(self, channel: discord.TextChannel,
                            category: str, opener: discord.Member):
        greeting = (
            f"Olá, {opener.mention}. Sou o atendente virtual do servidor. "
            f"Seu ticket foi aberto na categoria **{category}**. "
            f"Descreva sua situação e vou tentar ajudar. "
            f"Se for algo que precise de staff humana, é só pedir."
        )
        embed = discord.Embed(
            description=greeting,
            color=config.EMBED_COLOR,
        )
        embed.set_author(name="Atendimento Automático", icon_url=self.bot.user.display_avatar.url)
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AIHandler(bot))