import discord
from discord.ext import commands
import httpx
import config
import database as db

OWNER_ID = 875751530584748132

class AdminTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        # Trava de segurança: só o dono pode usar esses comandos
        return ctx.author.id == OWNER_ID

    @commands.command(name="status")
    async def status(self, ctx, member: discord.Member):
        """Puxa os cargos e o histórico de tickets do cliente."""
        try:
            await ctx.message.delete() # Apaga o comando pra ficar limpo no ticket
        except discord.Forbidden:
            pass
        
        # Puxa tickets do banco
        tickets = await db.get_user_tickets(member.id)
        
        # Puxa cargos (ignorando o cargo padrão @everyone)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Nenhum cargo"

        embed = discord.Embed(
            title=f"🕵️ Status de {member.display_name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=False)
        embed.add_field(name="🛡️ Cargos", value=roles_str, inline=False)
        
        if not tickets:
            embed.add_field(name="📦 Compras / Tickets", value="Nenhum ticket ou compra registrada.", inline=False)
        else:
            compras = []
            for t in tickets[:5]: # Mostra os 5 últimos
                data = t["created_at"][:10] if t["created_at"] else "Sem data"
                status_icone = "🟢" if t["status"] == "open" else "🔴"
                
                # Converte a Row para dict para pegar o ticket_type com segurança
                t_dict = dict(t)
                tipo_raw = t_dict.get("ticket_type")
                
                if tipo_raw == "ai":
                    tipo = "IA"
                elif tipo_raw == "human":
                    tipo = "Humano"
                else:
                    tipo = "Pendente"
                    
                compras.append(f"{status_icone} `#{t['id']}` - {t['category']} ({tipo}) - {data}")
            
            embed.add_field(name="📦 Últimos Tickets / Compras", value="\n".join(compras), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="ban")
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Banido pelo proprietário."):
        """Bane o cliente do servidor."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        
        if member.id == OWNER_ID:
            return await ctx.send("❌ Você não pode banir a si mesmo.", delete_after=5)
            
        try:
            await member.ban(reason=reason)
            await ctx.send(f"🔨 **{member.mention} foi banido.**\n**Motivo:** {reason}", delete_after=10)
        except discord.Forbidden:
            await ctx.send("❌ Não tenho permissão para banir este usuário.", delete_after=5)

    @commands.command(name="dragon")
    async def dragon(self, ctx, member: discord.Member):
        """Analisa o histórico do cliente pra ver se ele está mentindo."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        
        msg = await ctx.send(f"🐉 **Dragon analisando o histórico de {member.mention}...**")

        # Puxa os dados do banco
        tickets = await db.get_user_tickets(member.id)
        msgs = await db.get_user_messages(member.id, limit=30)
        
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        
        # Monta o contexto pra IA analisar
        contexto = f"O usuário se chama {member.name} e possui os cargos: {', '.join(roles) if roles else 'Nenhum'}.\n\n"
        
        contexto += "--- HISTÓRICO DE TICKETS ---\n"
        if not tickets:
            contexto += "O usuário nunca abriu um ticket.\n"
        else:
            for t in tickets[:5]:
                contexto += f"Ticket #{t['id']} | Categoria: {t['category']} | Status: {t['status']}\n"
        
        contexto += "\n--- ÚLTIMAS MENSAGENS DO USUÁRIO NOS TICKETS ---\n"
        if not msgs:
            contexto += "Nenhuma mensagem registrada.\n"
        else:
            for m in reversed(msgs):
                data_msg = m['created_at'][:16] if m['created_at'] else "Sem data"
                contexto += f"[{data_msg}] {m['content']}\n"

        # Prompt pra IA analisar
        prompt = (
            "Você é o 'Dragon', um auditor frio e analítico de um servidor de vendas. "
            "Sua função é analisar o histórico de um cliente e verificar se ele está tentando aplicar um golpe (ex: dizendo que comprou algo mas não recebeu, quando não há registro), "
            "se está sendo desrespeitoso com o dono do servidor, ou se está mentindo no suporte.\n\n"
            f"Aqui estão os dados do cliente:\n{contexto}\n\n"
            "Com base nisso, faça um veredito em até 2 parágrafos. "
            "Diga se o cliente é CONFIAVEL, SUSPEITO ou MENTIROSO/DESRESPEITOSO. "
            "Explique o motivo usando as evidências acima. "
            "Se o cliente estiver reclamando de compra, verifique se os cargos e o histórico de tickets batem com a reclamação dele."
        )

        try:
            # Chama a API da Groq diretamente
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{config.GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": config.GROQ_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 500
                    },
                    timeout=30.0
                )
                
                # Verifica se a API retornou erro
                if resp.status_code != 200:
                    raise Exception(f"Erro na API da Groq: HTTP {resp.status_code} - {resp.text}")
                    
                data = resp.json()
                analise = data["choices"][0]["message"]["content"]

            embed = discord.Embed(
                title=f"🐉 Julgamento do Dragon",
                description=analise,
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Alvo: {member.name} | ID: {member.id}")
            await msg.edit(content=None, embed=embed)

        except Exception as e:
            await msg.edit(content=f"❌ Erro ao analisar: `{e}`")

async def setup(bot):
    await bot.add_cog(AdminTools(bot))
