
import discord
from discord import ui

CATEGORIES = [
    ("Suporte Técnico", "Problemas técnicos, bugs e erros", "🛠️"),
    ("Dúvidas Gerais", "Perguntas sobre o servidor", "❓"),
    ("Reportar Usuário", "Denúncias e reports", "🚨"),
    ("Pagamentos", "Compras, doações e cobranças", "💳"),
    ("Outros", "Qualquer outro assunto", "📩"),
]


class CategorySelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=name,
                description=desc,
                emoji=emoji
            )
            for name, desc, emoji in CATEGORIES
        ]

        super().__init__(
            placeholder="📂 Selecione a categoria do atendimento",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        from cogs.tickets import create_ticket_channel
        await create_ticket_channel(interaction, self.values[0])


class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CategorySelect())


class TicketControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Assumir atendimento",
        style=discord.ButtonStyle.primary,
        emoji="🙋",
        custom_id="ticket_claim",
        row=0,
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: ui.Button
    ):
        from cogs.tickets import handle_claim
        await handle_claim(interaction)

    @ui.button(
        label="Fechar ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket_close",
        row=0,
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: ui.Button
    ):
        from cogs.tickets import handle_close
        await handle_close(interaction)
