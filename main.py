import telebot
import random
from collections import defaultdict
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = 'YOUR_SUPER_SECRET_BOT_TOKEN'
bot = telebot.TeleBot(BOT_TOKEN)
games = {}

ROLE_DESCRIPTIONS = {
    "Шериф": "Ночью проверяет одного игрока на принадлежность к мафии/якудзе.",
    "Сержант": "Мирный житель. Становится Шерифом, если оригинальный Шериф умирает.",
    "Куртизанка": "Ночью посещает одного игрока, блокируя его и своё действие.",
    "Доктор": "Ночью лечит одного игрока, 2 лечения за игру.",
    "Журналист": "Ночью выбирает двух игроков и узнает, принадлежат ли они к одной команде.",
    "Бомж": "Ночью следит за игроком, узнаёт убийцу если тот погибает.",
    "Почтальон": "Ночью отправляет анонимное письмо другому игроку.",
    "Тюремщик": "Пока отсутствует расширенная логика.",
    "Стрелок": "Пока отсутствует логика выстрела.",
    "Амур": "Первой ночью выбирает влюблённых, смерть одного — смерть второго.",
    "Судья": "Пока отсутствует.",
    "Ветеран": "Может стать на боевую готовность. Убивает любых посетителей.",
    "Маньяк": "Убивает одного игрока ночью.",
    "Путана": "Заражает чумой. Заражённые распространяют инфекцию.",
    "Ведьма": "Контролирует действия других по выбору двух целей, имеет магический барьер.",
    "Босс Мафии": "Убийца мафии.",
    "Киллер Мафии": "Убийца с 1 дополнительным выстрелом.",
    "Подручный Мафии": "",
    "Босс Якудзы": "Убийца якудзы.",
    "Ниндзя": "Для шерифа — мирный.",
    "Подручный Якудзы": "",
}

FACTIONS = {
    "мирный": ["Шериф", "Сержант", "Куртизанка", "Доктор", "Журналист", "Бомж", "Почтальон", "Тюремщик", "Стрелок", "Амур", "Судья", "Ветеран"],
    "мафия": ["Босс Мафии", "Киллер Мафии", "Подручный Мафии"],
    "якудза": ["Босс Якудзы", "Ниндзя", "Подручный Якудзы"],
    "нейтрал": ["Маньяк", "Путана", "Ведьма"]
}

ALL_ROLES = sorted(ROLE_DESCRIPTIONS.keys())

def get_faction(role):
    for faction, roles in FACTIONS.items():
        if role == "Ниндзя":
            return "якудза"
        if role in roles:
            return faction
    return "неизвестно"

def get_journalist_faction(player):
    if player.role in ["Маньяк", "Путана", "Ведьма"]:
        return 'нейтрал'
    if player.role in FACTIONS['мафия'] or player.role in FACTIONS['якудза']:
        return 'бандиты'
    return 'мирный'

class Player:
    def __init__(self, user_id, username, first_name):
        self.id = user_id
        self.username = username or first_name or str(user_id)
        self.first_name = first_name
        self.role = None
        self.is_alive = True
        self.voted_for = None

        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False
        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False

        self.in_love_with = None
        self.shot_charges = 3
        self.vet_charges = 3
        self.killer_shot_charge = 1
        self.doctor_heal_charges = 0
        self.is_infected = False
        self.is_witch_protected = True
        self.cursed_targets = []
        self.cursed_by_witch = False
        self.courtesan_client = None
        self.postal_messages_sent_to = set()

    @property
    def tag(self):
        return f"@{self.username}" if self.username else self.first_name

    def reset_night_state(self):
        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False
        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False
        self.cursed_targets = []
        self.cursed_by_witch = False
        self.postal_messages_sent_to.clear()

class Game:
    def __init__(self, chat_id, gm_id):
        self.chat_id = chat_id
        self.gm_id = gm_id
        self.players = {}
        self.state = 'LOBBY'
        self.day = 0
        self.votes = {}
        self.lovers = []
        self.initial_factions_count = defaultdict(int)
        self.allowed_roles = ALL_ROLES[:]
        self.role_config_mode = False

    def add_player(self, user):
        if user.id in self.players:
            return False
        self.players[user.id] = Player(user.id, user.username, user.first_name)
        return True

    def get_player(self, player_id):
        return self.players.get(player_id)

    def get_alive_players(self, exclude_ids=None):
        if exclude_ids is None:
            exclude_ids = []
        return [p for p in self.players.values() if p.is_alive and p.id not in exclude_ids]

    def assign_roles(self):
        player_count = len(self.players)
        allowed_roles = [r for r in ALL_ROLES if r in self.allowed_roles]

        if player_count > len(allowed_roles):
            raise ValueError("Недостаточно включённых ролей для раздачи всем игрокам.")

        base_roles = allowed_roles[:player_count]
        random.shuffle(base_roles)

        player_ids = list(self.players.keys())
        random.shuffle(player_ids)

        for player_id, role_name in zip(player_ids, base_roles):
            player = self.get_player(player_id)
            player.role = role_name
            if role_name == "Доктор":
                player.doctor_heal_charges = 2
            faction = get_faction(role_name)
            self.initial_factions_count[faction.capitalize()] += 1

            try:
                bot.send_message(
                    player.id,
                    f"Игра началась! Ваша роль: **{role_name}**\n_{ROLE_DESCRIPTIONS.get(role_name, '')}_",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Не удалось отправить роль игроку {player.tag}: {e}")

        self.introduce_teams()
        return True

    def introduce_teams(self):
        teams = defaultdict(list)
        for p in self.players.values():
            faction = get_faction(p.role)
            if faction in ['мафия', 'якудза']:
                teams[faction].append(p)

        for faction, players in teams.items():
            team_mates = ", ".join([p.tag for p in players])
            for p in players:
                try:
                    bot.send_message(p.id, f"Ваша команда ({faction.capitalize()}): {team_mates}")
                except Exception:
                    pass

    def check_sergeant_promotion(self):
        if not any(p.role == 'Шериф' and p.is_alive for p in self.players.values()):
            sergeant = next((p for p in self.players.values() if p.role == 'Сержант' and p.is_alive), None)
            if sergeant:
                sergeant.role = 'Шериф'
                bot.send_message(sergeant.id, "Шериф умер, теперь вы — новый Шериф! Вы можете проверять других игроков ночью.")

    def process_night(self):
        night_actions = defaultdict(dict)
        for p in self.get_alive_players():
            if p.night_action_done:
                night_actions[p.role][p.id] = {
                    'target': p.night_target,
                    'target2': p.night_target2,
                    'player': p
                }

        public_log = []
        private_logs = defaultdict(str)
        deaths = defaultdict(list)

        # Амур
        if self.day == 1:
            for _, action in night_actions.get('Амур', {}).items():
                try:
                    p1 = self.get_player(int(action['target']))
                    p2 = self.get_player(int(action['target2']))
                except Exception:
                    p1 = None
                    p2 = None
                if p1 and p2 and p1 != p2:
                    p1.in_love_with = p2.id
                    p2.in_love_with = p1.id
                    self.lovers = [p1.id, p2.id]
                    public_log.append("Амур нашел двух влюбленных...❤")

        # Ветеран
        for player_id, action in night_actions.get('Ветеран', {}).items():
            if action['target'] == 'alert':
                player = self.get_player(player_id)
                if player and player.vet_charges > 0:
                    player.is_on_alert = True
                    player.vet_charges -= 1
                    public_log.append("Ветеран в эту ночь был начеку.")

        # Ведьма (контроль и барьер)
        for player_id, action in night_actions.get('Ведьма', {}).items():
            witch = self.get_player(player_id)
            if not witch or witch.is_blocked or witch.is_jailed:
                continue
            if action['target'] is None or action['target2'] is None:
                continue
            target1 = self.get_player(int(action['target']))
            target2 = self.get_player(int(action['target2']))
            if not target1 or not target2:
                continue

            target1.night_target = target2.id
            target1.cursed_by_witch = True
            witch.cursed_targets.append(target1.id)
            private_logs[witch.id] += f"Вы контролировали {target1.tag}, роль: {target1.role}\n"

        # Куртизанка, Ведьма, Тюремщик блокируют цель/сажают в тюрьму
        for role in ['Куртизанка', 'Ведьма', 'Тюремщик']:
            for player_id, action in night_actions.get(role, {}).items():
                player = self.get_player(player_id)
                if not player or player.is_blocked or player.is_jailed:
                    continue
                target = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
                if not target:
                    continue

                if role == 'Тюремщик':
                    target.is_jailed = True
                    private_logs[player.id] += f"Вы посадили {target.tag} в тюрьму.\n"
                    private_logs[target.id] += "Вы в тюрьме, не можете делать способности и защищены от покушения.\n"
                else:
                    target.is_blocked = True
                    private_logs[player.id] += f"Вы заблокировали {target.tag}.\n"
                    private_logs[target.id] += "Ваше ночное действие было заблокировано.\n"
                    if role == 'Куртизанка':
                        player.is_blocked = True

        # Доктор
        for player_id, action in night_actions.get('Доктор', {}).items():
            player = self.get_player(player_id)
            if not player or player.is_blocked or player.is_jailed:
                continue

            if player.doctor_heal_charges <= 0:
                private_logs[player.id] += "У вас закончились лечения.\n"
                continue

            target = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
            if not target:
                continue

            target.is_healed = True
            player.doctor_heal_charges -= 1
            private_logs[player.id] += f"Вы лечили {target.tag}. Осталось лечений: {player.doctor_heal_charges}.\n"

            if target.is_infected and target.role != "Путана":
                target.is_infected = False
                private_logs[player.id] += f"{target.tag} вылечен от заражения.\n"

        # Путана заражение
        for player_id, action in night_actions.get('Путана', {}).items():
            player = self.get_player(player_id)
            if not player or player.is_blocked or player.is_jailed:
                continue

            target = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
            if not target:
                continue

            if target != player:
                target.is_infected = True

        # Распространение заражения путаны через посещения
        for p in self.get_alive_players():
            if p.is_blocked or p.is_jailed:
                continue
            nt = p.night_target
            if nt in self.players:
                target = self.get_player(nt)
                if target and p.is_infected and not target.is_infected:
                    target.is_infected = True
                if target and target.is_infected and not p.is_infected:
                    p.is_infected = True

        # Шериф и Сержант
        for player_id, action in night_actions.get('Шериф', {}).items():
            sheriff = self.get_player(player_id)
            if not sheriff or sheriff.is_blocked or sheriff.is_jailed:
                continue
            if sheriff.role not in ("Шериф","Сержант"):
                continue

            target = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
            if not target:
                continue

            faction = get_faction(target.role)
            if faction in ['мафия', 'якудза']:
                result = "мафия"
            elif target.role in ["Путана", "Ведьма"]:
                result = "нейтрал"
            else:
                result = "мирный"

            private_logs[player_id] += f"Проверка {target.tag}: он **{result}**.\n"

        # Журналист
        for player_id, action in night_actions.get('Журналист', {}).items():
            journalist = self.get_player(player_id)
            if not journalist or journalist.is_blocked or journalist.is_jailed:
                continue

            if journalist.courtesan_client is not None:
                private_logs[player_id] += "Ваша проверка отменена, вы являетесь клиентом Куртизанки.\n"
                continue

            p1 = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
            p2 = self.get_player(int(action['target2'])) if isinstance(action['target2'], int) else None
            if not p1 or not p2:
                continue

            f1 = get_journalist_faction(p1)
            f2 = get_journalist_faction(p2)

            if f1 == "бандиты" and f2 == "бандиты":
                res = "одинаковыми"
            elif f1 == f2:
                res = "одинаковыми"
            else:
                res = "разными"

            private_logs[player_id] += f"Проверка {p1.tag} и {p2.tag}: они из **{res}**.\n"

        # Почтальон
        posted_targets = set()
        for player_id, action in night_actions.get('Почтальон', {}).items():
            sender = self.get_player(player_id)
            if not sender or sender.is_blocked or sender.is_jailed:
                continue

            msg_sender = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
            receiver = self.get_player(int(action['target2'])) if isinstance(action['target2'], int) else None
            if not msg_sender or not receiver:
                continue

            if receiver.id in posted_targets:
                private_logs[sender.id] += "Вы не можете послать письмо одному игроку дважды за ночь.\n"
                continue

            private_logs[receiver.id] += f"Вам пришло анонимное письмо от имени {msg_sender.tag}: 'Привет!'\n"
            posted_targets.add(receiver.id)

        # Обработка убийств и смертей
        killing_roles = ['Босс Мафии', 'Киллер Мафии', 'Босс Якудзы', 'Маньяк']
        for role in killing_roles:
            for player_id, action in night_actions.get(role, {}).items():
                killer = self.get_player(player_id)
                if not killer or killer.is_blocked or killer.is_jailed:
                    continue
                target = self.get_player(int(action['target'])) if isinstance(action['target'], int) else None
                if not target or not target.is_alive:
                    continue

                if target.is_on_alert:
                    deaths[killer.id].append(target)
                else:
                    deaths[target.id].append(killer)

        dead_this_night = []
        for target_id, killers in deaths.items():
            target = self.get_player(target_id)
            if not target or not target.is_alive:
                continue
            if target.is_jailed or target.is_blocked:
                public_log.append(f"Нападение на {target.tag} не удалось, он(а) был(а) под защитой.")
                continue
            if target.is_healed:
                public_log.append(f"{target.tag} был(а) атакован(а), но Доктор его спас!")
                continue

            if target.role == "Ведьма" and target.is_witch_protected:
                target.is_witch_protected = False
                public_log.append(f"{target.tag} была атакована, но магический барьер защитил её!")
                continue

            target.is_alive = False
            dead_this_night.append(target)

        for player in dead_this_night[:]:
            if player.in_love_with:
                lover = self.get_player(player.in_love_with)
                if lover and lover.is_alive:
                    lover.is_alive = False
                    dead_this_night.append(lover)
                    public_log.append(f"{lover.tag} не смог(ла) пережить смерть возлюбленного и умирает от горя.")

        for player_id, log in private_logs.items():
            try:
                bot.send_message(player_id, log, parse_mode="Markdown")
            except Exception:
                pass

        summary = f"**Итоги ночи №{self.day}:**\n" + "\n".join(public_log)
        if dead_this_night:
            dead_roles = ", ".join([f"{p.tag} (был {p.role})" for p in dead_this_night])
            summary += f"\n\nЭтой ночью город покинули: {dead_roles}."
        else:
            summary += "\n\nЭтой ночью никто не умер."

        bot.send_message(self.chat_id, summary, parse_mode="Markdown")

        self.check_sergeant_promotion()

# Команды и хендлеры следует интегрировать из предыдущих версий, внеся дополнения к новым ролям.

if __name__ == '__main__':
    print("Бот Мафия запущен...")
    bot.infinity_polling()
