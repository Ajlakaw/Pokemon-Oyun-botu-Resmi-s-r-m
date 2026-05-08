import aiohttp
import json
import os
import random
from datetime import datetime, date

DATA_FILE = "pokemon_save.json"

CARD_SHOP = {
    "power": {
        "name": "Güç Kartı",
        "price": 40,
        "desc": "Rakibe ekstra +18 hasar verir."
    },
    "heal": {
        "name": "Can Kartı",
        "price": 35,
        "desc": "Pokémonunun canını +35 iyileştirir."
    },
    "shield": {
        "name": "Kalkan Kartı",
        "price": 30,
        "desc": "1 tur gelen hasarı çok azaltır."
    },
    "rage": {
        "name": "Öfke Kartı",
        "price": 60,
        "desc": "Sonraki normal saldırına +22 güç ekler."
    }
}


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


class Pokemon:
    pokemons = {}

    def __init__(self, pokemon_trainer, trainer_name=None, register=True, pokemon_number=None):
        self.trainer_id = str(pokemon_trainer)
        self.pokemon_trainer = trainer_name or str(pokemon_trainer)
        self.kind = self.__class__.__name__

        if pokemon_number is None:
            chance = random.randint(1, 100)
            if chance <= 7:
                self.pokemon_number = random.randint(800, 1000)
                self.is_rare = True
            else:
                self.pokemon_number = random.randint(1, 500)
                self.is_rare = False
        else:
            self.pokemon_number = int(pokemon_number)
            self.is_rare = self.pokemon_number >= 800

        self.name = "Bilinmeyen"
        self.height = 0
        self.weight = 0
        self.types = []
        self.abilities = []
        self.stats = {}
        self.sprite = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png"

        self.level = 1
        self.xp = 0
        self.hunger = 100
        self.money = 100
        self.wins = 0
        self.losses = 0
        self.last_daily = ""

        self.max_hp = 100
        self.hp = self.max_hp
        self.attack_power = 15
        self.defense = 8
        self.speed = 8

        self.is_defending = False
        self.shield_turns = 0
        self.buff_power = 0

        self.inventory = {
            "power": 1,
            "heal": 1,
            "shield": 1,
            "rage": 0
        }

        if register:
            Pokemon.pokemons[self.trainer_id] = self

    async def fetch_data(self):
        url = f"https://pokeapi.co/api/v2/pokemon/{self.pokemon_number}"
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise RuntimeError("PokeAPI cevap vermedi")

                    data = await response.json()

                    self.name = data.get("name", "pikachu").title()
                    self.height = data.get("height", 0)
                    self.weight = data.get("weight", 0)

                    self.types = [
                        t["type"]["name"]
                        for t in data.get("types", [])
                    ]

                    self.abilities = [
                        a["ability"]["name"]
                        for a in data.get("abilities", [])
                    ]

                    self.stats = {
                        stat["stat"]["name"]: stat["base_stat"]
                        for stat in data.get("stats", [])
                    }

                    self.sprite = (
                        data.get("sprites", {}).get("front_default")
                        or "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png"
                    )

        except Exception:
            self.name = "Pikachu"
            self.types = ["electric"]
            self.abilities = ["static"]
            self.stats = {
                "hp": 35,
                "attack": 55,
                "defense": 40,
                "speed": 90
            }
            self.sprite = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png"

        self.recalculate_stats(keep_hp=False)

    def recalculate_stats(self, keep_hp=True):
        old_max_hp = max(1, self.max_hp)
        old_hp = self.hp

        base_hp = self.stats.get("hp", 50)
        base_attack = self.stats.get("attack", 50)
        base_defense = self.stats.get("defense", 50)
        base_speed = self.stats.get("speed", 50)

        self.max_hp = 80 + (base_hp // 2) + (self.level * 8)
        self.attack_power = 10 + (base_attack // 6) + (self.level * 2)
        self.defense = 5 + (base_defense // 8) + self.level
        self.speed = 5 + (base_speed // 10) + self.level

        if self.kind == "Wizard":
            self.max_hp += 25
            self.defense += 3

        elif self.kind == "Fighter":
            self.max_hp += 10
            self.attack_power += 7

        if self.is_rare:
            self.max_hp += 12
            self.attack_power += 3
            self.defense += 2

        if keep_hp:
            hp_ratio = old_hp / old_max_hp
            self.hp = clamp(int(self.max_hp * hp_ratio), 1, self.max_hp)
        else:
            self.hp = self.max_hp

    def receive_damage(self, raw_damage):
        damage = max(1, int(raw_damage))
        detail = ""

        if self.is_defending:
            damage = max(1, damage // 2)
            detail += " 🛡️ Savunma hasarı yarıya düşürdü."
            self.is_defending = False

        if self.shield_turns > 0:
            damage = max(1, int(damage * 0.4))
            self.shield_turns -= 1
            detail += " ✨ Kalkan kartı hasarı azalttı."

        self.hp = clamp(self.hp - damage, 0, self.max_hp)
        return damage, detail

    def attack_target(self, other):
        base_damage = self.attack_power - (other.defense // 2)
        base_damage += random.randint(-2, 3)

        if self.buff_power > 0:
            base_damage += self.buff_power
            buff_text = f" 🔥 Öfke bonusu +{self.buff_power}!"
            self.buff_power = 0
        else:
            buff_text = ""

        crit_chance = 0.10 + min(0.12, self.speed / 300)
        is_critical = random.random() < crit_chance

        if is_critical:
            base_damage = int(base_damage * 1.7)

        damage, defense_text = other.receive_damage(max(1, base_damage))
        crit_text = " 💥 Kritik!" if is_critical else ""

        return (
            f"⚔️ **{self.name}**, **{other.name}** adlı rakibe **{damage}** hasar verdi."
            f"{crit_text}{buff_text}{defense_text}"
        )

    def defend(self):
        self.is_defending = True
        return f"🛡️ **{self.name}** savunmaya geçti. Bir sonraki hasar yarıya inecek."

    def heal(self, amount=25):
        if self.hp <= 0:
            self.hp = 1

        old_hp = self.hp
        self.hp = clamp(self.hp + amount, 0, self.max_hp)
        gained = self.hp - old_hp

        return f"❤️ **{self.name}** iyileşti. +{gained} HP | HP: {self.hp}/{self.max_hp}"
        


    def feed(self):
        if not hasattr(self, "last_feed_time"):
            self.last_feed_time = ""

        if not hasattr(self, "feed_combo"):
            self.feed_combo = 0

        now = datetime.now()

        if self.last_feed_time:
            try:
                last_feed = datetime.fromisoformat(self.last_feed_time)
            except Exception:
                last_feed = None
        else:
            last_feed = None


        if last_feed is None:
            self.feed_combo = 1

        else:
            seconds_passed = (now - last_feed).total_seconds()

   
            if seconds_passed >= 120:
                self.feed_combo = 1

            else:

                if self.feed_combo == 1:
                    self.feed_combo = 2

                else:
                    remaining = int(120 - seconds_passed)

                    minutes = remaining // 60
                    seconds = remaining % 60

                    return (
                        f"⏳ Bi bekle azımdakileri bitireyim.\n"
                        f"Tekrar beslemek için: {minutes}dk {seconds}sn bekle."
                    )

        self.last_feed_time = now.isoformat()

        self.hunger = clamp(self.hunger + 20, 0, 100)

        messages = [
            f"🍎 **{self.name}** beslendi. Açlık: {self.hunger}/100"
        ]

        messages.extend(self.add_xp(10))

        return "\n".join(messages)


    def add_xp(self, amount):
        self.xp += amount
        messages = [f"⭐ +{amount} XP kazandı."]

        leveled = False

        while self.xp >= self.level * 50:
            self.xp -= self.level * 50
            self.level += 1
            leveled = True
            messages.append(f"🎉 Seviye atladı! Yeni level: {self.level}")

        if leveled:
            self.recalculate_stats(keep_hp=False)
            messages.append(f"💪 Statlar yenilendi. HP tamamen doldu: {self.hp}/{self.max_hp}")

        return messages

    def use_card(self, card_id, target=None):
        card_id = card_id.lower().strip()

        if card_id not in CARD_SHOP:
            return False, "❌ Böyle bir kart yok."

        if self.inventory.get(card_id, 0) <= 0:
            return False, f"❌ Elinde **{CARD_SHOP[card_id]['name']}** yok."

        if card_id == "power":
            if target is None:
                return False, "❌ Bu kart için hedef gerekli."

            damage, defense_text = target.receive_damage(18 + self.level)
            text = (
                f"🎴 **{self.name}**, Güç Kartı kullandı. "
                f"**{target.name}** {damage} hasar aldı.{defense_text}"
            )

        elif card_id == "heal":
            text = "🎴 Can Kartı kullanıldı. " + self.heal(35)

        elif card_id == "shield":
            self.shield_turns += 1
            text = f"🎴 **{self.name}**, Kalkan Kartı kullandı. Gelen hasar 1 tur çok azalacak."

        elif card_id == "rage":
            self.buff_power += 22
            text = f"🎴 **{self.name}**, Öfke Kartı kullandı. Sonraki saldırısı +22 güçlenecek."

        else:
            return False, "❌ Kart çalıştırılamadı."

        self.inventory[card_id] -= 1
        return True, text

    def buy_card(self, card_id, amount=1):
        card_id = card_id.lower().strip()
        amount = int(amount)

        if amount <= 0:
            return False, "❌ Miktar 1 veya daha fazla olmalı."

        if card_id not in CARD_SHOP:
            return False, "❌ Böyle bir kart markette yok."

        total_price = CARD_SHOP[card_id]["price"] * amount

        if self.money < total_price:
            return False, f"❌ Paran yetmiyor. Gerekli: {total_price} coin | Sende: {self.money} coin"

        self.money -= total_price
        self.inventory[card_id] = self.inventory.get(card_id, 0) + amount

        return True, f"✅ {amount} adet **{CARD_SHOP[card_id]['name']}** aldın. Kalan para: {self.money} coin"

    def claim_daily(self):
        today = date.today().isoformat()

        if self.last_daily == today:
            return "⏳ Bugünkü günlük ödülünü zaten aldın."

        reward = random.randint(60, 110)
        self.money += reward
        self.last_daily = today

        return f"🎁 Günlük ödül alındı: +{reward} coin | Toplam para: {self.money} coin"

    def short_status(self):
        return (
            f"**{self.name}** | Lv.{self.level} | HP: {self.hp}/{self.max_hp} | "
            f"ATK: {self.attack_power} | DEF: {self.defense} | SPD: {self.speed}"
        )

    def inventory_text(self):
        lines = []

        for card_id, card in CARD_SHOP.items():
            lines.append(
                f"`{card_id}` - {card['name']}: {self.inventory.get(card_id, 0)} adet"
            )

        return "\n".join(lines)

    def info(self):
        type_text = ", ".join(self.types) if self.types else "bilinmiyor"
        ability_text = ", ".join(self.abilities[:3]) if self.abilities else "bilinmiyor"

        return (
            f"👤 Eğitmen: **{self.pokemon_trainer}**\n"
            f"🐾 Pokémon: **{self.name}**\n"
            f"🧬 Sınıf: **{self.kind}**\n"
            f"⭐ Level: **{self.level}** | XP: **{self.xp}/{self.level * 50}**\n"
            f"❤️ HP: **{self.hp}/{self.max_hp}**\n"
            f"⚔️ Saldırı: **{self.attack_power}**\n"
            f"🛡️ Savunma: **{self.defense}**\n"
            f"💨 Hız: **{self.speed}**\n"
            f"🍗 Açlık: **{self.hunger}/100**\n"
            f"💰 Para: **{self.money} coin**\n"
            f"🏆 Galibiyet: **{self.wins}** | Mağlubiyet: **{self.losses}**\n"
            f"💎 Nadir: **{'Evet' if self.is_rare else 'Hayır'}**\n"
            f"🌈 Türler: **{type_text}**\n"
            f"✨ Yetenekler: **{ability_text}**"
        )

    def to_dict(self):
        return {
            "trainer_id": self.trainer_id,
            "pokemon_trainer": self.pokemon_trainer,
            "kind": self.kind,
            "pokemon_number": self.pokemon_number,
            "is_rare": self.is_rare,
            "name": self.name,
            "height": self.height,
            "weight": self.weight,
            "types": self.types,
            "abilities": self.abilities,
            "stats": self.stats,
            "sprite": self.sprite,
            "level": self.level,
            "xp": self.xp,
            "hunger": self.hunger,
            "money": self.money,
            "wins": self.wins,
            "losses": self.losses,
            "last_daily": self.last_daily,
            "max_hp": self.max_hp,
            "hp": self.hp,
            "attack_power": self.attack_power,
            "defense": self.defense,
            "speed": self.speed,
            "inventory": self.inventory,
            "saved_at": datetime.now().isoformat(timespec="seconds")
        }

    @classmethod
    def from_dict(cls, data):
        kind = data.get("kind", "Pokemon")

        class_map = {
            "Pokemon": Pokemon,
            "Wizard": Wizard,
            "Fighter": Fighter
        }

        selected_class = class_map.get(kind, Pokemon)

        obj = selected_class(
            data.get("trainer_id"),
            data.get("pokemon_trainer"),
            register=False,
            pokemon_number=data.get("pokemon_number", 25)
        )

        obj.kind = kind
        obj.is_rare = data.get("is_rare", False)
        obj.name = data.get("name", "Pikachu")
        obj.height = data.get("height", 0)
        obj.weight = data.get("weight", 0)
        obj.types = data.get("types", [])
        obj.abilities = data.get("abilities", [])
        obj.stats = data.get("stats", {})
        obj.sprite = data.get("sprite", obj.sprite)

        obj.level = data.get("level", 1)
        obj.xp = data.get("xp", 0)
        obj.hunger = data.get("hunger", 100)
        obj.money = data.get("money", 100)
        obj.wins = data.get("wins", 0)
        obj.losses = data.get("losses", 0)
        obj.last_daily = data.get("last_daily", "")

        obj.max_hp = data.get("max_hp", 100)
        obj.hp = data.get("hp", obj.max_hp)
        obj.attack_power = data.get("attack_power", 15)
        obj.defense = data.get("defense", 8)
        obj.speed = data.get("speed", 8)

        obj.inventory = data.get(
            "inventory",
            {
                "power": 1,
                "heal": 1,
                "shield": 1,
                "rage": 0
            }
        )

        obj.is_defending = False
        obj.shield_turns = 0
        obj.buff_power = 0

        Pokemon.pokemons[obj.trainer_id] = obj
        return obj

    @classmethod
    def save_all(cls):
        data = {
            trainer_id: pokemon.to_dict()
            for trainer_id, pokemon in cls.pokemons.items()
        }

        temp_file = DATA_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        os.replace(temp_file, DATA_FILE)

    @classmethod
    def load_all(cls):
        cls.pokemons = {}

        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)

            for _, pokemon_data in data.items():
                cls.from_dict(pokemon_data)

        except Exception:
            cls.pokemons = {}


class Wizard(Pokemon):
    def attack_target(self, other):
        if random.random() < 0.25:
            raw_damage = self.attack_power + random.randint(4, 10)
            damage, defense_text = other.receive_damage(raw_damage)

            return (
                f"🔮 **{self.name}** büyülü saldırı yaptı! "
                f"**{other.name}** {damage} hasar aldı.{defense_text}"
            )

        return super().attack_target(other)

    def info(self):
        return (
            "🔮 Bu Pokémon **Sihirbaz** sınıfında. Bazen büyülü saldırı yapar.\n"
            + super().info()
        )



class Fighter(Pokemon):
    def attack_target(self, other):
        if random.random() < 0.25:
            raw_damage = int(self.attack_power * 1.9) + random.randint(0, 6)
            damage, defense_text = other.receive_damage(raw_damage)

            return (
                f"🥊 **{self.name}** özel dövüş hamlesi yaptı! "
                f"**{damage}** hasar!{defense_text}"
            )

        return super().attack_target(other)

    def info(self):
        return (
            "🥊 Bu Pokémon **Dövüşçü** sınıfında. Bazen çok güçlü vurur.\n"
            + super().info()
        )


def transfer_money(sender, receiver, amount):
    try:
        amount = int(amount)
    except ValueError:
        return False, "❌ Para miktarı sayı olmalı."

    if amount <= 0:
        return False, "❌ Miktar 1 veya daha fazla olmalı."

    if sender.money < amount:
        return False, f"❌ Yeterli paran yok. Sende {sender.money} coin var."

    sender.money -= amount
    receiver.money += amount

    return True, f"✅ {sender.pokemon_trainer}, {receiver.pokemon_trainer} kişisine {amount} coin gönderdi."


def transfer_card(sender, receiver, card_id, amount=1):
    card_id = card_id.lower().strip()

    try:
        amount = int(amount)
    except ValueError:
        return False, "❌ Kart miktarı sayı olmalı."

    if card_id not in CARD_SHOP:
        return False, "❌ Böyle bir kart yok."

    if amount <= 0:
        return False, "❌ Miktar 1 veya daha fazla olmalı."

    if sender.inventory.get(card_id, 0) < amount:
        return False, f"❌ Elinde yeterli **{CARD_SHOP[card_id]['name']}** yok."

    sender.inventory[card_id] -= amount
    receiver.inventory[card_id] = receiver.inventory.get(card_id, 0) + amount

    return True, f"✅ {amount} adet **{CARD_SHOP[card_id]['name']}** takas edildi."