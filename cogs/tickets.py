import discord
from discord.ext import commands

import config
import database as db
from utils.views import PanelView, TicketControlView, TicketModeView
from utils.transcript import build_transcript_html

OWNER_ID = 875751530584748132
BRAND_IMAGE = "https://i.imgur.com/xOUSKMD.png"
RED = discord.Color.from_rgb(255, 0, 0)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def owner_overwrite():
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        manage_channels=True,
        manage_messages=True,
        attach_files=True,
        embed_links=True,
    )


async def owner_only(interaction: discord.Interaction) -> bool:
    if is_owner(interaction.user.id):
        return True

    message = "❌ Você não tem permissão para utilizar esta função."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

    return False


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(PanelView())
        self.bot.add_view(TicketControlView())
        self.bot.add_view(TicketModeView())
        print(f"[tickets] pronto — {self.bot.user}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Bloqueia áudio e vídeo antes mesmo de chamar a IA
        if message.flags.voice or any(
            a.content_type and (a.content_type.startswith("audio/") or a.content_type.startswith("video/")) 
            for a in message.attachments
        ):
            return

        ticket = await db.get_ticket_by_channel(message.channel.id)

        if not ticket or ticket["status"] == "closed":
            return

        await db.log_message(
            ticket["id"],
            message.author.id,
            message.content
        )

        if (
            ticket["status"] == "claimed"
            or message.author.id != ticket["user_id"]
        ):
            return

        # Converte o aiosqlite.Row para dict para podermos usar .get() sem erro
        ticket_dict = dict(ticket)
        
        # Só chama a IA se o cliente tiver clicado no botão "Falar com a IA"
        if ticket_dict.get("ticket_type") != "ai":
            return

        ai_cog = self.bot.get_cog("AIHandler")

        if not ai_cog:
            return

        async with message.channel.typing():
            reply = await ai_cog.generate_reply(
                ticket["id"],
                message.content,
                ticket["category"]
            )

        await db.log_message(
            ticket["id"],
            self.bot.user.id,
            reply,
            is_bot=True
        )

        await message.channel.send(reply)

    @commands.hybrid_command(
        name="painel",
        description="Envia o painel de abertura de tickets."
    )
    async def painel(self, ctx: commands.Context):
        if not is_owner(ctx.author.id):
            await ctx.reply(
                "❌ Você não tem permissão para utilizar esta função.",
                mention_author=False,
                ephemeral=ctx.interaction is not None
            )
            return

        embed = discord.Embed(
            title="🎫・CENTRAL DE ATENDIMENTO",
            description=(
                "Bem-vindo à **QZZ Community**!\n\n"
                "Abra seu atendimento selecionando uma categoria abaixo.\n\n"
                "📌 **Como funciona?**\n"
                "・Escolha a categoria correta.\n"
                "・Explique seu problema detalhadamente.\n"
                "・Aguarde a resposta do atendimento.\n\n"
                "🔒 Seus tickets são privados."
            ),
            color=RED
        )

        embed.set_image(url=BRAND_IMAGE)
        embed.set_footer(
            text="QZZ COMMUNITY • Atendimento oficial",
            icon_url=self.bot.user.display_avatar.url
        )

        await ctx.send(embed=embed, view=PanelView())

    @painel.error
    async def painel_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.CheckFailure):
            await ctx.reply(
                "❌ Você não tem permissão para utilizar esta função.",
                mention_author=False
            )
            return

        raise error


async def setup(bot):
    await bot.add_cog(Tickets(bot))


async def create_ticket_channel(
    interaction: discord.Interaction,
    category: str
):
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message(
            "❌ Este recurso só funciona dentro do servidor.",
            ephemeral=True
        )
        return

    for ch in guild.text_channels:
        if not ch.name.startswith("ticket-"):
            continue

        current = await db.get_ticket_by_channel(ch.id)

        if (
            current
            and current["user_id"] == user.id
            and current["status"] != "closed"
        ):
            await interaction.response.send_message(
                f"⚠️ Você já tem um ticket aberto: {ch.mention}",
                ephemeral=True
            )
            return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        bot_member = guild.me or guild.get_member(interaction.client.user.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
        }

        owner = guild.get_member(OWNER_ID)
        if owner:
            overwrites[owner] = owner_overwrite()

        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )

        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )

        staff_role_id = getattr(config, "STAFF_ROLE_ID", None)
        if staff_role_id:
            staff_role = guild.get_role(int(staff_role_id))
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )

        category_ch = None
        category_id = getattr(config, "CATEGORY_ID", None)
        if category_id:
            fetched = guild.get_channel(int(category_id))
            if isinstance(fetched, discord.CategoryChannel):
                category_ch = fetched

        safe_name = "".join(
            c for c in user.name.lower()
            if c.isalnum() or c in "-_"
        )[:80] or "user"

        channel = await guild.create_text_channel(
            name=f"ticket-{safe_name}",
            category=category_ch,
            overwrites=overwrites,
            topic=f"Ticket de {user} ({user.id}) — {category}",
            reason=f"Ticket aberto por {user} ({user.id})"
        )

    except Exception as exc:
        print(f"[tickets] ERRO ao criar canal: {type(exc).__name__}: {exc}")
        await interaction.followup.send(
            "❌ Não consegui criar o ticket. Verifique as permissões do bot.",
            ephemeral=True
        )
        return

    ticket_id = await db.create_ticket(channel.id, user.id, category)

    embed = discord.Embed(
        title=f"🎫・ATENDIMENTO #{ticket_id}",
        description=(
            f"Olá, {user.mention}! Seu atendimento foi criado.\n\n"
            "**Como podemos ajudar?**\n"
            "Descreva sua situação em uma mensagem.\n\n"
            "🔒 **Canal privado**\n"
            "Somente você, o responsável autorizado e os cargos configurados podem visualizar este canal."
        ),
        color=RED,
        timestamp=discord.utils.utcnow()
    )

    embed.set_author(
        name="QZZ Community • Suporte",
        icon_url=(guild.icon.url if guild.icon else interaction.client.user.display_avatar.url)
    )

    embed.add_field(name="👤 Aberto por", value=user.mention, inline=True)
    embed.add_field(name="📂 Categoria", value=category, inline=True)
    embed.add_field(name="📌 Status", value="🟢 Em aberto", inline=True)

    embed.set_image(url=BRAND_IMAGE)
    embed.set_footer(
        text=f"QZZ COMMUNITY • Ticket #{ticket_id}",
        icon_url=interaction.client.user.display_avatar.url
    )

    await channel.send(embed=embed, view=TicketControlView())

    # Pergunta inicial (IA ou Humano)
    await channel.send(
        "⚠️ **Antes de começar:**\nSeu atendimento necessita de uma staff ou quer tentar conversar com nosso atendimento de IA 24h?",
        view=TicketModeView()
    )

    await interaction.followup.send(
        f"✅ Seu ticket foi aberto: {channel.mention}",
        ephemeral=True
    )


async def handle_claim(interaction: discord.Interaction):
    if not await owner_only(interaction):
        return

    ticket = await db.get_ticket_by_channel(interaction.channel.id)

    if not ticket or ticket["status"] == "closed":
        await interaction.response.send_message(
            "⚠️ Este ticket não está aberto.",
            ephemeral=True
        )
        return

    if ticket["status"] == "claimed":
        await interaction.response.send_message(
            "ℹ️ Este atendimento já foi assumido.",
            ephemeral=True
        )
        return

    await db.claim_ticket(interaction.channel.id, interaction.user.id)

    embed = discord.Embed(
        title="🙋 Atendimento assumido",
        description=(
            f"{interaction.user.mention} assumiu este ticket.\n"
            "O atendimento automático foi pausado neste canal."
        ),
        color=RED,
        timestamp=discord.utils.utcnow()
    )

    await interaction.response.send_message(embed=embed)


async def handle_close(interaction: discord.Interaction):
    if not await owner_only(interaction):
        return

    ticket = await db.get_ticket_by_channel(interaction.channel.id)

    if not ticket:
        await interaction.response.send_message(
            "❌ Este canal não está registrado como ticket.",
            ephemeral=True
        )
        return

    if ticket["status"] == "closed":
        await interaction.response.send_message(
            "ℹ️ Este ticket já foi fechado.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🔒 Fechando ticket e gerando o transcript...",
        ephemeral=True
    )

    await db.close_ticket(interaction.channel.id)

    messages = await db.get_all_messages(ticket["id"])

    buf = build_transcript_html(ticket, messages, interaction.guild.name)

    log_channel_id = getattr(config, "LOG_CHANNEL_ID", None)
    log_ch = (
        interaction.guild.get_channel(int(log_channel_id))
        if log_channel_id else None
    )

    if log_ch:
        log_embed = discord.Embed(
            title=f"🔒 Ticket #{ticket['id']} encerrado",
            description="O atendimento foi fechado e o transcript foi gerado.",
            color=RED,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="👤 Usuário", value=f"<@{ticket['user_id']}>", inline=True)
        log_embed.add_field(name="📂 Categoria", value=ticket["category"], inline=True)
        log_embed.add_field(name="🛡️ Fechado por", value=interaction.user.mention, inline=True)

        await log_ch.send(
            embed=log_embed,
            file=discord.File(buf, filename=f"ticket-{ticket['id']}.html")
        )

    await interaction.channel.delete(
        reason=f"Ticket #{ticket['id']} fechado por {interaction.user} ({interaction.user.id})"
    )
