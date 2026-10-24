import discord
from discord.ext import commands
import httpx
import config
import database as db

OWNER_ID = 875751530584748132
CANAL_COMPRAS_ID = 1541783356700631071

class AdminTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        # Trava de segurança: só o dono pode usar esses comandos
        return ctx.author.id == OWNER_ID

    @commands.command(name="sync")
    async def sync_compras(self, ctx, limit: int = 500):
        """Lê o canal de compras e salva no banco (apenas o dono)."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        canal = self.bot.get_channel(CANAL_COMPRAS_ID)
        if not canal:
            return await ctx.send("❌ Não achei o canal de compras. Verifique o ID.", delete_after=10)

        msg = await ctx.send(f"🔄 Lendo as últimas {limit} mensagens do canal de compras...")

        # Limpa as compras antigas pra não duplicar no banco
        async with db.aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("DELETE FROM purchases")
            await conn.commit()

        count = 0
        async for message in canal.history(limit=limit):
            if message.author.bot:
                continue
            
            # Tenta achar menção de usuário na mensagem
            if message.mentions:
                user = message.mentions[0]
                # Pega o texto da mensagem, limpa a menção e pega o resto como nome do produto
                texto_limpo = message.content.replace(f"<@{user.id}>", "").replace(f"<@!{user.id}>", "").strip()
                
                # Se sobrou texto, salva como produto
                if texto_limpo:
                    await db.add_purchase(user.id, texto_limpo[:100])
                    count += 1

        await msg.edit(content=f"✅ Sincronização concluída! **{count} compras** registradas no banco.")

    @commands.command(name="compras")
    async def ver_compras(self, ctx):
        """Mostra quantas compras foram registradas no banco."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        total = await db.get_total_purchases()
        
        embed = discord.Embed(
            title="🛒 Total de Compras Registradas",
            description=f"O bot tem **{total}** compras sincronizadas no banco de dados.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Use !sync para atualizar a lista se necessário.")
        
        await ctx.send(embed=embed)

    @commands.command(name="status")
    async def status(self, ctx, member: discord.Member):
        """Puxa os cargos, histórico de tickets e compras do cliente."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        
        tickets = await db.get_user_tickets(member.id)
        purchases = await db.get_user_purchases(member.id)
        
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
        
        # Adiciona as compras puxadas do canal
        if not purchases:
            embed.add_field(name="🛒 Compras Registradas", value="Nenhuma compra registrada no canal.", inline=False)
        else:
            compras_str = []
            for p in purchases[:5]: # 5 últimas
                data = p["purchase_date"][:10] if p["purchase_date"] else ""
                compras_str.append(f"• **{p['product_name']}** ({data})")
            embed.add_field(name="🛒 Compras Registradas", value="\n".join(compras_str), inline=False)

        if not tickets:
            embed.add_field(name="📦 Tickets", value="Nenhum ticket aberto.", inline=False)
        else:
            compras_tickets = []
            for t in tickets[:3]:
                data = t["created_at"][:10] if t["created_at"] else ""
                status_icone = "🟢" if t["status"] == "open" else "🔴"
                compras_tickets.append(f"{status_icone} `#{t['id']}` - {t['category']} - {data}")
            embed.add_field(name="📦 Últimos Tickets", value="\n".join(compras_tickets), inline=False)

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

        tickets = await db.get_user_tickets(member.id)
        msgs = await db.get_user_messages(member.id, limit=30)
        purchases = await db.get_user_purchases(member.id)
        
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        
        contexto = f"O usuário se chama {member.name} e possui os cargos: {', '.join(roles) if roles else 'Nenhum'}.\n"
        if purchases:
            prods = [p['product_name'] for p in purchases]
            contexto += f"Compras registradas dele: {', '.join(prods)}.\n"
        else:
            contexto += "Nenhuma compra registrada no sistema.\n"
            
        contexto += "\n--- HISTÓRICO DE TICKETS ---\n"
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
                data_msg = m['created_at'][:16] if m['created_at'] else ""
                contexto += f"[{data_msg}] {m['content']}\n"

        prompt = (
            "Você é o 'Dragon', um auditor frio e analítico de um servidor de vendas. "
            "Sua função é analisar o histórico de um cliente e verificar se ele está tentando aplicar um golpe (ex: dizendo que comprou algo mas não recebeu, quando não há registro), "
            "se está sendo desrespeitoso com o dono do servidor, ou se está mentindo no suporte.\n\n"
            f"Aqui estão os dados do cliente:\n{contexto}\n\n"
            "Com base nisso, faça um veredito em até 2 parágrafos. "
            "Diga se o cliente é CONFIAVEL, SUSPEITO ou MENTIROSO/DESRESPEITOSO. "
            "Explique o motivo usando as evidências acima. "
            "Se o cliente estiver reclamando de compra, verifique se os cargos e o histórico de compras batem com a reclamação dele."
        )

        try:
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
                
                if resp.status_code != 200:
                    raise Exception(f"Erro na API: HTTP {resp.status_code}")
                    
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
