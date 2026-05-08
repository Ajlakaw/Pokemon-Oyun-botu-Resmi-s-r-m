import random
from typing import Optional

import discord
from discord.ext import commands

from config import token
from logic import (
    Pokemon,
    Wizard,
    Fighter,
    CARD_SHOP,
    transfer_money,
    transfer_card,
)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_LOADED = False


async def create_random_pokemon(owner_id, owner_name, register=True):
    selected_class = random.choice([Pokemon, Wizard, Fighter])
    pokemon = selected_class(str(owner_id), owner_name, register=register)

    await pokemon.fetch_data()

    return pokemon


def get_user_pokemon(user):
    return Pokemon.pokemons.get(str(user.id))


def make_pokemon_embed(pokemon, title="Pokémon Bilgisi"):
    embed = discord.Embed(
        title=title,
        description=pokemon.info(),
        color=0xF1C40F
    )

    if pokemon.sprite:
        embed.set_thumbnail(url=pokemon.sprite)

    return embed


class BattleView(discord.ui.View):
    def __init__(self, ctx, player, enemy, pve=True, opponent_user=None):
        super().__init__(timeout=120)

        self.ctx = ctx
        self.player = player
        self.enemy = enemy
        self.pve = pve
        self.opponent_user = opponent_user

        self.turn = player
        self.finished = False
        self.log = []
        self.message = None

    def get_target(self, actor):
        if actor == self.player:
            return self.enemy

        return self.player

    def battle_status(self):
        mode = "🤖 Vahşi Rakip" if self.pve else "👥 Arkadaş Savaşı"

        if self.finished:
            turn_text = "Savaş bitti."
        else:
            turn_text = f"Sıra: **{self.turn.pokemon_trainer}** / **{self.turn.name}**"

        log_text = "\n".join(self.log[-6:]) if self.log else "Savaş başladı. Hamleni seç."

        return (
            f"{mode}\n"
            f"{turn_text}\n\n"
            f"🟦 {self.player.short_status()}\n"
            f"🟥 {self.enemy.short_status()}\n\n"
            f"**Son Olaylar:**\n{log_text}"
        )

    async def interaction_check(self, interaction):
        if self.finished:
            await interaction.response.send_message(
                "Bu savaş zaten bitti.",
                ephemeral=True
            )
            return False

        current_user_id = self.turn.trainer_id

        if self.pve:
            allowed = interaction.user.id == self.ctx.author.id
        else:
            allowed = str(interaction.user.id) == str(current_user_id)

        if not allowed:
            await interaction.response.send_message(
                "Şu an sıra sende değil. 😄",
                ephemeral=True
            )
            return False

        return True

    async def start(self):
        self.message = await self.ctx.send(
            self.battle_status(),
            view=self
        )

    def disable_all_buttons(self):
        for item in self.children:
            item.disabled = True

    def finish_if_needed(self):
        if self.player.hp <= 0 or self.enemy.hp <= 0:
            self.finished = True

            winner = self.player if self.player.hp > 0 else self.enemy
            loser = self.enemy if winner == self.player else self.player

            winner.wins += 1
            loser.losses += 1

            if self.pve:
                coin_reward = 70 if winner == self.player else 35
                xp_reward = 35 if winner == self.player else 20
            else:
                coin_reward = 70
                xp_reward = 35

            winner.money += coin_reward

            self.log.append(
                f"🏆 **{winner.name}** kazandı! +{coin_reward} coin"
            )

            self.log.extend(winner.add_xp(xp_reward))

            self.disable_all_buttons()
            Pokemon.save_all()

            return True

        return False

    def switch_turn(self):
        if self.turn == self.player:
            self.turn = self.enemy
        else:
            self.turn = self.player

    async def enemy_auto_turn(self):
        if self.finished:
            return

        action_roll = random.random()

        if self.enemy.hp < self.enemy.max_hp * 0.35 and action_roll < 0.30:
            self.log.append(self.enemy.heal(18))

        elif action_roll < 0.45:
            self.log.append(self.enemy.defend())

        else:
            self.log.append(self.enemy.attack_target(self.player))

        self.finish_if_needed()
        self.turn = self.player

    async def run_action(self, interaction, action_name):
        actor = self.turn
        target = self.get_target(actor)

        if action_name == "attack":
            self.log.append(actor.attack_target(target))

        elif action_name == "defend":
            self.log.append(actor.defend())

        elif action_name == "power":
            _, text = actor.use_card("power", target)
            self.log.append(text)

        elif action_name == "heal":
            _, text = actor.use_card("heal", actor)
            self.log.append(text)

        elif action_name == "shield":
            _, text = actor.use_card("shield", actor)
            self.log.append(text)

        elif action_name == "rage":
            _, text = actor.use_card("rage", actor)
            self.log.append(text)

        elif action_name == "run":
            if not self.pve:
                self.log.append("❌ Arkadaş savaşından kaçamazsın.")
            else:
                self.finished = True
                self.log.append(f"🏃 **{actor.name}** savaştan kaçtı.")
                self.disable_all_buttons()
                Pokemon.save_all()

                await interaction.response.edit_message(
                    content=self.battle_status(),
                    view=self
                )
                return

        if not self.finish_if_needed():
            if self.pve:
                self.turn = self.enemy
                await self.enemy_auto_turn()
            else:
                self.switch_turn()

        Pokemon.save_all()

        await interaction.response.edit_message(
            content=self.battle_status(),
            view=self
        )

    @discord.ui.button(
        label="Saldır",
        emoji="⚔️",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def attack_button(self, interaction, button):
        await self.run_action(interaction, "attack")

    @discord.ui.button(
        label="Savun",
        emoji="🛡️",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def defend_button(self, interaction, button):
        await self.run_action(interaction, "defend")

    @discord.ui.button(
        label="Güç Kartı",
        emoji="🎴",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def power_card_button(self, interaction, button):
        await self.run_action(interaction, "power")

    @discord.ui.button(
        label="Can Kartı",
        emoji="❤️",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def heal_card_button(self, interaction, button):
        await self.run_action(interaction, "heal")

    @discord.ui.button(
        label="Kalkan",
        emoji="✨",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def shield_card_button(self, interaction, button):
        await self.run_action(interaction, "shield")

    @discord.ui.button(
        label="Öfke",
        emoji="🔥",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def rage_card_button(self, interaction, button):
        await self.run_action(interaction, "rage")

    @discord.ui.button(
        label="Kaç",
        emoji="🏃",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def run_button(self, interaction, button):
        await self.run_action(interaction, "run")

    async def on_timeout(self):
        if not self.finished:
            self.finished = True
            self.log.append("⌛ Savaş zaman aşımına uğradı.")
            self.disable_all_buttons()
            Pokemon.save_all()

            if self.message:
                try:
                    await self.message.edit(
                        content=self.battle_status(),
                        view=self
                    )
                except discord.HTTPException:
                    pass


async def send_help_message(ctx):
    text = """
📌 **Komutlar**

`!go` - Pokémon oluşturur.
`!info` - Kendi Pokémon bilgini gösterir.
`!info @kişi` - Başkasının Pokémon bilgisini gösterir.
`!feed` - Pokémon besler, XP verir.
`!heal` - Pokémonu biraz iyileştirir.
`!daily` - Günlük coin ödülü alır.

🛒 **Market ve Kartlar**
`!shop` - Kart marketini gösterir.
`!buy kart_id miktar` - Kart satın alır.
Örnek: `!buy heal 2`
`!cards` - Kartlarını gösterir.

⚔️ **Savaş**
`!battle` - Vahşi rakibe karşı savaş açar.
`!battle @kişi` - Arkadaşınla savaşır.

🤝 **Takas**
`!sendmoney @kişi miktar` - Para gönderir.
`!tradecard @kişi kart_id miktar` - Kart gönderir.

📌 Kart ID'leri:
`power`, `heal`, `shield`, `rage`
"""
    await ctx.send(text)


@bot.event
async def on_ready():
    global DATA_LOADED

    if not DATA_LOADED:
        Pokemon.load_all()
        DATA_LOADED = True

    print(f"Giriş yapıldı: {bot.user} | Kayıtlı oyuncu: {len(Pokemon.pokemons)}")

@bot.event
async def on_member_join(member):

    # Karşılama mesajı gönderme
    for channel in member.guild.text_channels:
        await channel.send(f'👋 Hoş geldiniz, {member.mention}!')

@bot.command()
async def go(ctx):
    if get_user_pokemon(ctx.author):
        await ctx.send("Zaten Pokémonun var! Bilgi için `!info` yaz.")
        return

    pokemon = await create_random_pokemon(
        ctx.author.id,
        ctx.author.display_name,
        register=True
    )

    Pokemon.save_all()

    await ctx.send(f"✅ Pokémonun oluşturuldu: **{pokemon.name}**")
    await ctx.send(embed=make_pokemon_embed(pokemon, "Yeni Pokémon"))


@bot.command()
async def info(ctx, member: Optional[discord.Member] = None):
    member = member or ctx.author
    pokemon = get_user_pokemon(member)

    if not pokemon:
        await ctx.send("Bu kişinin Pokémonu yok. Oluşturmak için `!go` yazmalı.")
        return

    await ctx.send(embed=make_pokemon_embed(pokemon, "Pokémon Bilgisi"))


@bot.command()
async def feed(ctx):
    pokemon = get_user_pokemon(ctx.author)

    if not pokemon:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    await ctx.send(pokemon.feed())
    Pokemon.save_all()


@bot.command()
async def heal(ctx):
    pokemon = get_user_pokemon(ctx.author)

    if not pokemon:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    await ctx.send(pokemon.heal(25))
    Pokemon.save_all()


@bot.command()
async def daily(ctx):
    pokemon = get_user_pokemon(ctx.author)

    if not pokemon:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    await ctx.send(pokemon.claim_daily())
    Pokemon.save_all()


@bot.command()
async def shop(ctx):
    lines = ["🛒 **Kart Marketi**"]

    for card_id, card in CARD_SHOP.items():
        lines.append(
            f"`{card_id}` - **{card['name']}** | "
            f"{card['price']} coin | {card['desc']}"
        )

    lines.append("\nSatın almak için: `!buy kart_id miktar`")
    lines.append("Örnek: `!buy heal 2`")

    await ctx.send("\n".join(lines))


@bot.command()
async def buy(ctx, card_id: str = None, amount: int = 1):
    pokemon = get_user_pokemon(ctx.author)

    if not pokemon:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    if card_id is None:
        await ctx.send("Kullanım: `!buy kart_id miktar` | Örnek: `!buy power 1`")
        return

    ok, text = pokemon.buy_card(card_id, amount)
    await ctx.send(text)

    if ok:
        Pokemon.save_all()


@bot.command()
async def cards(ctx):
    pokemon = get_user_pokemon(ctx.author)

    if not pokemon:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    await ctx.send(f"🎴 **Kartların:**\n{pokemon.inventory_text()}")


@bot.command()
async def battle(ctx, opponent: Optional[discord.Member] = None):
    player = get_user_pokemon(ctx.author)

    if not player:
        await ctx.send("Önce Pokémon oluştur: `!go`")
        return

    if player.hp <= 0:
        player.hp = max(1, player.max_hp // 2)

    if opponent is None:
        enemy = await create_random_pokemon(
            "npc",
            "Vahşi Rakip",
            register=False
        )

        view = BattleView(ctx, player, enemy, pve=True)
        await view.start()
        return

    if opponent.bot:
        await ctx.send("Botlarla arkadaş savaşı yapılamaz.")
        return

    if opponent.id == ctx.author.id:
        await ctx.send("Kendinle savaşamazsın. 😄")
        return

    enemy = get_user_pokemon(opponent)

    if not enemy:
        await ctx.send(f"{opponent.mention} kullanıcısının Pokémonu yok. Önce `!go` yazmalı.")
        return

    if enemy.hp <= 0:
        enemy.hp = max(1, enemy.max_hp // 2)

    view = BattleView(ctx, player, enemy, pve=False, opponent_user=opponent)

    await ctx.send(f"⚔️ {ctx.author.mention} ve {opponent.mention} arasında savaş başladı!")
    await view.start()


@bot.command()
async def sendmoney(ctx, member: discord.Member = None, amount: int = None):
    if member is None or amount is None:
        await ctx.send("Kullanım: `!sendmoney @kişi miktar` | Örnek: `!sendmoney @Emin 50`")
        return

    sender = get_user_pokemon(ctx.author)
    receiver = get_user_pokemon(member)

    if not sender or not receiver:
        await ctx.send("Para göndermek için iki kişinin de Pokémonu olmalı.")
        return

    ok, text = transfer_money(sender, receiver, amount)
    await ctx.send(text)

    if ok:
        Pokemon.save_all()


@bot.command()
async def tradecard(ctx, member: discord.Member = None, card_id: str = None, amount: int = 1):
    if member is None or card_id is None:
        await ctx.send("Kullanım: `!tradecard @kişi kart_id miktar` | Örnek: `!tradecard @Emin heal 1`")
        return

    sender = get_user_pokemon(ctx.author)
    receiver = get_user_pokemon(member)

    if not sender or not receiver:
        await ctx.send("Kart takası için iki kişinin de Pokémonu olmalı.")
        return

    ok, text = transfer_card(sender, receiver, card_id, amount)
    await ctx.send(text)

    if ok:
        Pokemon.save_all()


@bot.command(name="yardim")
async def yardim(ctx):
    await send_help_message(ctx)


@bot.command(name="commands")
async def commands_command(ctx):
    await send_help_message(ctx)


bot.run(token)