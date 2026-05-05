import telebot
import random
from collections import defaultdict
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ВАЖНО: Вставьте сюда свой токен
BOT_TOKEN = '8543815916:AAEvjpxHjsjfJKBCjAOnvh-2of4aIoFDtdY'

bot = telebot.TeleBot(BOT_TOKEN)
games = {}

# --- Конфигурация ролей и баланса ---

# Описание ролей для игроков
ROLE_DESCRIPTIONS = {
    "Шериф": "Ночью проверяет одного игрока на принадлежность к мафии/якудзе.",
    "Сержант": "Мирный житель. Становится Шерифом, если оригинальный Шериф умирает.",
    "Куртизанка": "Ночью посещает одного игрока, блокируя его и своё действие. Если к цели придет убийца, он останется жив.",
    "Доктор": "Ночью лечит одного игрока, спасая его от одного убийства.",
    "Журналист": "Ночью выбирает двух игроков и узнает, принадлежат ли они к одной команде.",
    "Бомж": "Ночью следит за одним игроком. Если этого игрока убьют, Бомж узнает роль убийцы.",
    "Почтальон": "Ночью отправляет анонимное сообщение одному игроку от имени другого.",
    "Тюремщик": "Ночью сажает одного игрока в тюрьму, блокируя его действие и защищая от атак.",
    "Стрелок": "Днём может сделать выстрел в любого игрока. Имеет 3 патрона на игру.",
    "Амур": "В первую ночь выбирает двух 'влюбленных'. Если один из них умирает, второй умирает от горя.",
    "Судья": "Днём после голосования может отменить казнь или подтвердить её.",
    "Ветеран": "Ночью может встать в боевую готовность (3 раза за игру). Любой, кто посетит его в эту ночь, умрет.",
    "Маньяк": "Одиночка, который каждую ночь убивает одного игрока. Побеждает, если остается один на один с кем-либо.",
    "Путана": "Ночью заражает игрока чумой. Зараженные могут заражать других. Побеждает, если все живые заражены.",
    "Ведьма": "Ночью может заблокировать действие одного игрока.",
    "Босс Мафии": "Глава мафии. Выбирает цель для убийства от имени всей мафии.",
    "Киллер Мафии": "Член мафии. Может сделать один дополнительный выстрел за игру.",
    "Подручный Мафии": "Рядовой член мафии.",
    "Босс Якудзы": "Глава якудзы. Выбирает цель для убийства.",
    "Ниндзя": "Член якудзы. Для Шерифа выглядит как мирный.",
    "Подручный Якудзы": "Рядовой член якудзы.",
}

# Правила распределения ролей по количеству игроков
ROLE_BALANCE = {
    4: ["Босс Мафии", "Шериф", "Доктор", "Судья"],
    6: ["Босс Мафии", "Киллер Мафии", "Шериф", "Доктор", "Судья", "Куртизанка"],
    8: ["Босс Мафии", "Киллер Мафии", "Маньяк", "Шериф", "Доктор", "Судья", "Куртизанка", "Журналист"],
    10: ["Босс Мафии", "Киллер Мафии", "Босс Якудзы", "Ниндзя", "Шериф", "Сержант", "Доктор", "Судья", "Куртизанка",
         "Стрелок"],
    12: ["Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Маньяк", "Шериф", "Сержант",
         "Доктор", "Судья", "Куртизанка", "Журналист"],
    15: ["Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Маньяк",
         "Ведьма", "Шериф", "Сержант", "Доктор", "Судья", "Куртизанка", "Журналист", "Тюремщик"],
    21: ["Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Маньяк",
         "Путана", "Ведьма", "Шериф", "Сержант", "Куртизанка", "Доктор", "Журналист", "Бомж", "Почтальон", "Тюремщик",
         "Стрелок", "Амур", "Судья", "Ветеран"],
    30: [
        "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Подручный Мафии", "Подручный Мафии",
        "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Подручный Якудзы", "Подручный Якудзы",
        "Маньяк", "Маньяк", "Путана", "Ведьма",
        "Шериф", "Шериф", "Сержант", "Куртизанка", "Доктор", "Доктор", "Журналист", "Бомж", "Почтальон",
        "Тюремщик", "Стрелок", "Стрелок", "Амур", "Судья", "Судья", "Ветеран"
    ]
}

# Фракции для проверки
FACTIONS = {
    "мирный": ["Шериф", "Сержант", "Куртизанка", "Доктор", "Журналист", "Бомж", "Почтальон", "Тюремщик", "Стрелок",
               "Амур", "Судья", "Ветеран"],
    "мафия": ["Босс Мафии", "Киллер Мафии", "Подручный Мафии"],
    "якудза": ["Босс Якудзы", "Ниндзя", "Подручный Якудзы"],
    "нейтрал": ["Маньяк", "Путана", "Ведьма"]
}


def get_faction(role):
    for faction, roles in FACTIONS.items():
        if role in roles:
            return faction
    return "неизвестно"


# --- Классы Игрока и Игры ---

class Player:
    def __init__(self, user_id, username, first_name):
        self.id = user_id
        self.username = username or first_name or str(user_id)
        self.first_name = first_name
        self.role = None
        self.is_alive = True
        self.voted_for = None

        # Состояния на ночь
        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False  # Ветеран
        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False

        # Другие состояния
        self.in_love_with = None
        self.shot_charges = 3  # для Стрелка
        self.vet_charges = 3  # для Ветерана
        self.killer_shot_charge = 1  # для Киллера

    @property
    def tag(self):
        return f"@{self.username}" if self.username else self.first_name

    def __str__(self):
        return self.tag

    def reset_night_state(self):
        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False
        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False
        self.voted_for = None


class Game:
    def __init__(self, chat_id, gm_id):
        self.chat_id = chat_id
        self.gm_id = gm_id
        self.players = {}
        self.state = 'LOBBY'
        self.day = 0
        self.votes = defaultdict(list)
        self.lovers = []
        self.initial_factions_count = defaultdict(int)  # Для /startvote

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

        available_configs = sorted(ROLE_BALANCE.keys())
        chosen_config_key = available_configs[0]
        for key in available_configs:
            if player_count >= key:
                chosen_config_key = key
            else:
                break

        roles_to_assign = ROLE_BALANCE[chosen_config_key][:]

        while len(roles_to_assign) > player_count:
            roles_to_assign.pop()

        random.shuffle(roles_to_assign)

        player_ids = list(self.players.keys())
        random.shuffle(player_ids)

        for player_id, role_name in zip(player_ids, roles_to_assign):
            player = self.get_player(player_id)
            player.role = role_name
            faction = get_faction(role_name)
            self.initial_factions_count[faction.capitalize()] += 1

            try:
                bot.send_message(player.id,
                                 f"Игра началась! Ваша роль: **{role_name}**\n_{ROLE_DESCRIPTIONS.get(role_name, '')}_",
                                 parse_mode="Markdown")
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

    def process_night(self):
        night_actions = defaultdict(dict)
        for p in self.get_alive_players():
            if p.night_action_done:
                night_actions[p.role][p.id] = {'target': p.night_target, 'target2': p.night_target2, 'player': p}

        public_log = []
        private_logs = defaultdict(str)
        deaths = defaultdict(list)

        # --- ПОРЯДОК ХОДОВ ---

        # 1. Амур (только в 1-ю ночь)
        if self.day == 1:
            for player_id, action in night_actions.get('Амур', {}).items():
                p1 = self.get_player(action['target'])
                p2 = self.get_player(action['target2'])
                if p1 and p2:
                    p1.in_love_with = p2.id
                    p2.in_love_with = p1.id
                    self.lovers = [p1.id, p2.id]
                    public_log.append("Амур нашел двух влюбленных...❤")

        # 2. Ветеран
        for player_id, action in night_actions.get('Ветеран', {}).items():
            if action['target'] == 'alert':
                player = self.get_player(player_id)
                player.is_on_alert = True
                player.vet_charges -= 1
                public_log.append("Ветеран в эту ночь был начеку.")

        # 3. Ведьма, 4. Тюремщик, 5. Куртизанка (Блокировщики)
        for role in ['Ведьма', 'Тюремщик', 'Куртизанка']:
            for player_id, action in night_actions.get(role, {}).items():
                player = self.get_player(player_id)
                target = self.get_player(action['target'])
                if not target: continue

                if player.is_blocked or player.is_jailed: continue

                if role == 'Тюремщик':
                    target.is_jailed = True
                    private_logs[player.id] += f"Вы посадили {target.tag} в тюрьму.\n"
                    private_logs[target.id] += "Вы провели ночь в тюрьме и были защищены.\n"
                else:
                    target.is_blocked = True
                    private_logs[player.id] += f"Вы заблокировали {target.tag}.\n"
                    private_logs[target.id] += "Ваше ночное действие было заблокировано.\n"
                    if role == 'Куртизанка':
                        player.is_blocked = True

        # 9. Доктор
        for player_id, action in night_actions.get('Доктор', {}).items():
            player = self.get_player(player_id)
            target = self.get_player(action['target'])
            if not target or player.is_blocked or player.is_jailed: continue
            target.is_healed = True
            private_logs[player.id] += f"Вы лечили {target.tag}.\n"

        # 10. Мафия, 11. Якудза, 12. Маньяк (Убийцы)
        killing_roles = ['Босс Мафии', 'Киллер Мафии', 'Босс Якудзы', 'Маньяк']
        for role in killing_roles:
            for player_id, action in night_actions.get(role, {}).items():
                killer = self.get_player(player_id)
                target = self.get_player(action['target'])
                if not target or killer.is_blocked or killer.is_jailed: continue

                if target.is_on_alert:
                    deaths[killer.id].append(target)
                else:
                    deaths[target.id].append(killer)

        # --- Обработка последствий ---
        dead_this_night = []
        for target_id, killers in deaths.items():
            target = self.get_player(target_id)
            if not target or not target.is_alive: continue

            if target.is_jailed or target.is_blocked:
                public_log.append(f"Нападение на {target.tag} не удалось, он(а) был(а) под защитой.")
                continue
            if target.is_healed:
                public_log.append(f"{target.tag} был(а) атакован(а), но Доктор его спас!")
                continue

            target.is_alive = False
            dead_this_night.append(target)

        # --- Проверки и отправка результатов в ЛС ---
        # 6. Почтальон
        for player_id, action in night_actions.get('Почтальон', {}).items():
            sender = self.get_player(player_id)
            msg_sender = self.get_player(int(action['target']))
            receiver = self.get_player(int(action['target2']))
            if sender.is_blocked or sender.is_jailed or not msg_sender or not receiver: continue
            private_logs[receiver.id] += f"Вам пришло анонимное письмо от имени {msg_sender.tag}: 'Привет!'\n"

        # 7. Журналист
        for player_id, action in night_actions.get('Журналист', {}).items():
            p1 = self.get_player(int(action['target']))
            p2 = self.get_player(int(action['target2']))
            if self.get_player(player_id).is_blocked or self.get_player(
                player_id).is_jailed or not p1 or not p2: continue
            f1 = get_faction(p1.role)
            f2 = get_faction(p2.role)
            result = "одной команды" if f1 == f2 else "разных команд"
            private_logs[player_id] += f"Проверка {p1.tag} и {p2.tag}: они из **{result}**.\n"

        # 8. Шериф
        for player_id, action in night_actions.get('Шериф', {}).items():
            target = self.get_player(int(action['target']))
            if self.get_player(player_id).is_blocked or self.get_player(player_id).is_jailed or not target: continue
            faction = get_faction(target.role)
            result = "не мафия"
            if faction in ['мафия', 'якудза'] and target.role != 'Ниндзя':
                result = "мафия"
            private_logs[player_id] += f"Проверка {target.tag}: он **{result}**.\n"

        # 14. Бомж
        for player_id, action in night_actions.get('Бомж', {}).items():
            target = self.get_player(int(action['target']))
            if self.get_player(player_id).is_blocked or self.get_player(player_id).is_jailed or not target: continue
            if target in dead_this_night:
                killers_of_target = deaths.get(target.id, [])
                if killers_of_target:
                    killer_role = killers_of_target[0].role
                    private_logs[player_id] += f"Вы видели, как {target.tag} был убит. Убийца - **{killer_role}**.\n"
            else:
                private_logs[player_id] += f"Ночью у {target.tag} никто не был.\n"

        # --- Смерть влюбленных ---
        for player in dead_this_night[:]:
            if player.in_love_with:
                lover = self.get_player(player.in_love_with)
                if lover and lover.is_alive:
                    lover.is_alive = False
                    dead_this_night.append(lover)
                    public_log.append(f"{lover.tag} не смог(ла) пережить смерть возлюбленного и умирает от горя.")

        # --- Отправка всех логов ---
        for player_id, log in private_logs.items():
            try:
                bot.send_message(player_id, log, parse_mode="Markdown")
            except Exception:
                pass

        # --- Финальный итог ночи ---
        summary = f"**Итоги ночи №{self.day}:**\n" + "\n".join(public_log)
        if dead_this_night:
            dead_roles = ", ".join([f"{p.tag} (был {p.role})" for p in dead_this_night])
            summary += f"\n\nЭтой ночью город покинули: {dead_roles}."
        else:
            summary += "\n\nЭтой ночью никто не умер."

        bot.send_message(self.chat_id, summary, parse_mode="Markdown")

    def check_win_condition(self):
        pass

    def resolve_vote(self):
        if not self.votes:
            bot.send_message(self.chat_id, "Голосование пропущено, так как никто не голосовал.")
            return

        vote_counts = defaultdict(int)
        for voter_id in self.players:
            player = self.get_player(voter_id)
            if player.voted_for is not None:
                vote_counts[player.voted_for] += 1

        if not vote_counts:
            bot.send_message(self.chat_id, "Никто не проголосовал.")
            return

        max_votes = max(vote_counts.values())
        candidates = [pid for pid, count in vote_counts.items() if count == max_votes]

        result_text = "Результаты голосования:\n"
        for pid, count in vote_counts.items():
            voters = [self.get_player(voter_id).tag for voter_id in self.players if
                      self.get_player(voter_id).voted_for == pid]
            result_text += f"- За {self.get_player(pid).tag}: {count} голос(а) ({', '.join(voters)})\n"

        if len(candidates) > 1:
            result_text += "\nНичья. Никто не казнен."
            bot.send_message(self.chat_id, result_text)
            return

        candidate = self.get_player(candidates[0])
        candidate.is_alive = False
        result_text += f"\nБольшинством голосов казнен(а) **{candidate.tag}**. Его/её роль была: **{candidate.role}**."
        bot.send_message(self.chat_id, result_text, parse_mode="Markdown")


# --- Команды бота ---

@bot.message_handler(commands=['help'])
def show_help(message):
    game = games.get(message.chat.id)
    user_id = message.from_user.id

    gm_help_text = """
**Команды для Ведущего (GM):**
**/newgame** - Создать новую игру в чате.
**/startgame** - Начать игру после того, как все присоединились.
**/endnight** - Завершить ночь и подвести итоги.
**/endvote** - Завершить голосование и объявить результат.
**/startnight** - Начать следующую ночь (используется после дневного обсуждения).
**/endgame** - Принудительно завершить текущую игру.
**/status** - Показать текущий статус игры и список живых игроков.
    """

    player_help_text = """
**Как играть:**
1.  Используйте **/join**, чтобы войти в игру, пока идет набор.
2.  Когда начнется ночь, вы получите в **личные сообщения** от бота кнопки для выполнения вашего ночного действия.
3.  Днём в общем чате появятся кнопки для голосования против одного из игроков.
4.  Обсуждайте, вычисляйте мафию и побеждайте!

**Общие команды:**
**/status** - Показать текущий статус игры и список живых игроков.
**/help** - Показать это сообщение.
    """

    no_game_help_text = "Сейчас нет активной игры. Создайте новую командой **/newgame**."

    if not game:
        bot.reply_to(message, no_game_help_text, parse_mode="Markdown")
        return

    if user_id == game.gm_id:
        bot.reply_to(message, gm_help_text, parse_mode="Markdown")
    else:
        bot.reply_to(message, player_help_text, parse_mode="Markdown")


@bot.message_handler(commands=['status'])
def show_status(message):
    game = games.get(message.chat.id)
    if not game:
        bot.reply_to(message, "Нет активной игры.")
        return

    alive_players = game.get_alive_players()
    alive_tags = ", ".join([p.tag for p in alive_players]) if alive_players else "Никого не осталось"

    text = (f"**Статус игры**\n"
            f"Состояние: `{game.state}`\n"
            f"День: `{game.day}`\n"
            f"Живые игроки ({len(alive_players)}): {alive_tags}")

    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['newgame'])
def new_game(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "Игру можно создавать только в групповом чате.")
        return
    if message.chat.id in games:
        bot.reply_to(message, "Игра в этом чате уже идет. Завершите её командой /endgame.")
        return

    games[message.chat.id] = Game(message.chat.id, message.from_user.id)
    bot.send_message(message.chat.id, f"Новая игра создана! Ведущий: {message.from_user.first_name}.\n"
                                      f"Игроки, жмите /join, чтобы присоединиться.")


@bot.message_handler(commands=['join'])
def join_game(message):
    game = games.get(message.chat.id)
    if not game or game.state != 'LOBBY':
        bot.reply_to(message, "Сейчас нельзя присоединиться к игре.")
        return
    if game.add_player(message.from_user):
        bot.send_message(message.chat.id, f"{message.from_user.first_name} присоединился к игре.")
        players_list = ", ".join([p.tag for p in game.players.values()])
        bot.send_message(game.chat_id, f"Текущие игроки ({len(game.players)}): {players_list}")
    else:
        bot.reply_to(message, "Вы уже в игре.")


@bot.message_handler(commands=['startgame'])
def start_game(message):
    game = games.get(message.chat.id)
    if not game or game.gm_id != message.from_user.id:
        return
    if game.state != 'LOBBY':
        bot.reply_to(message, "Игра уже началась.")
        return
    if len(game.players) < 4:
        bot.reply_to(message, "Недостаточно игроков для начала (минимум 4).")
        return

    game.state = 'GAME'
    game.assign_roles()
    bot.send_message(game.chat_id,
                     "Роли розданы! Начинается первая ночь. Проверьте личные сообщения от бота, чтобы сделать ход.")
    start_night(message)


def start_night(message):
    game = games.get(message.chat.id)
    if not game: return
    game.state = 'NIGHT'
    game.day += 1
    for p in game.players.values():
        p.reset_night_state()

    bot.send_message(game.chat_id,
                     f"🌙 Наступила ночь №{game.day}. Город засыпает... Игроки делают ходы в личных сообщениях.")
    for p in game.get_alive_players():
        send_action_keyboard(p, game)


def send_action_keyboard(player, game):
    role = player.role
    text = f"Ваша роль: {role}. Выберите действие:"
    markup = InlineKeyboardMarkup()

    if role in ['Шериф', 'Доктор', 'Куртизанка', 'Тюремщик', 'Маньяк', 'Бомж', 'Ведьма', 'Босс Мафии', 'Босс Якудзы',
                'Киллер Мафии']:
        exclude = [] if role == 'Доктор' else [player.id]
        buttons = [InlineKeyboardButton(text=p.tag, callback_data=f"act:target:{p.id}") for p in
                   game.get_alive_players(exclude_ids=exclude)]
        markup.add(*buttons, row_width=2)
    elif role in ['Амур', 'Журналист', 'Почтальон']:
        text = f"Ваша роль: {role}. Выберите ПЕРВОГО игрока:"
        buttons = [InlineKeyboardButton(text=p.tag, callback_data=f"act:target1:{p.id}") for p in
                   game.get_alive_players(exclude_ids=[player.id])]
        markup.add(*buttons, row_width=2)
    elif role == 'Ветеран' and player.vet_charges > 0:
        markup.add(InlineKeyboardButton(text="🚨 Встать на охрану", callback_data="act:target:alert"))
        markup.add(InlineKeyboardButton(text="💤 Спать спокойно", callback_data="act:target:pass"))
    else:
        text = f"Ваша роль: {role}. У вас нет активного ночного действия."

    try:
        bot.send_message(player.id, text, reply_markup=markup)
    except Exception as e:
        print(f"Не удалось отправить клавиатуру игроку {player.tag}: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('act:'))
def handle_action_callback(call):
    user_id = call.from_user.id
    game = next((g for g in games.values() if user_id in g.players), None)
    if not game or game.state != 'NIGHT':
        bot.answer_callback_query(call.id, "Сейчас не время для хода.")
        return

    player = game.get_player(user_id)
    if not player or not player.is_alive or player.night_action_done:
        bot.answer_callback_query(call.id, "Вы не можете сделать ход.")
        return

    parts = call.data.split(':')
    action_type = parts[1]
    value = parts[2]

    if action_type == 'target':
        player.night_target = value if value in ['alert', 'pass'] else int(value)
        player.night_action_done = True
        target_player = game.get_player(int(value)) if value.isdigit() else None
        chosen = target_player.tag if target_player else "свой выбор"
        bot.edit_message_text(f"Ваш выбор принят: {chosen}.", call.message.chat.id, call.message.message_id)

    elif action_type == 'target1':
        player.night_target = int(value)
        target1_player = game.get_player(int(value))
        markup = InlineKeyboardMarkup()
        buttons = [InlineKeyboardButton(text=p.tag, callback_data=f"act:target2:{p.id}") for p in
                   game.get_alive_players(exclude_ids=[player.id, player.night_target])]
        markup.add(*buttons, row_width=2)
        bot.edit_message_text(f"Первый выбор: {target1_player.tag}. Теперь выберите второго игрока:",
                              call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif action_type == 'target2':
        player.night_target2 = int(value)
        player.night_action_done = True
        target1_player = game.get_player(player.night_target)
        target2_player = game.get_player(player.night_target2)
        bot.edit_message_text(f"Ваш выбор принят: {target1_player.tag} и {target2_player.tag}.", call.message.chat.id,
                              call.message.message_id)

    bot.answer_callback_query(call.id, "Ход принят!")


@bot.message_handler(commands=['endnight'])
def end_night(message):
    game = games.get(message.chat.id)
    if not game or game.gm_id != message.from_user.id or game.state != 'NIGHT':
        return

    game.state = 'DAY'
    game.process_night()
    game.check_win_condition()
    start_vote(message)


def start_vote(message):
    game = games.get(message.chat.id)
    if not game: return
    game.state = 'VOTE'
    game.votes.clear()

    for p in game.players.values():
        p.voted_for = None

    alive_players = game.get_alive_players()
    faction_info = ", ".join([f"{name}: {count}" for name, count in game.initial_factions_count.items()])

    bot.send_message(game.chat_id, f"☀️ Наступил день! Время для голосования.\n"
                                   f"Изначальный расклад: {faction_info}\n"
                                   f"Живые игроки ({len(alive_players)}): {', '.join([p.tag for p in alive_players])}\n"
                                   "Используйте кнопки ниже, чтобы проголосовать за казнь.",
                     reply_markup=get_vote_keyboard(game))


def get_vote_keyboard(game):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=p.tag, callback_data=f"vote:{p.id}") for p in game.get_alive_players()]
    markup.add(*buttons)
    return markup


@bot.callback_query_handler(func=lambda call: call.data.startswith('vote:'))
def handle_vote_callback(call):
    user_id = call.from_user.id
    game = next((g for g in games.values() if user_id in g.players), None)
    if not game or game.state != 'VOTE':
        bot.answer_callback_query(call.id, "Сейчас не время для голосования.")
        return

    player = game.get_player(user_id)
    if not player or not player.is_alive:
        bot.answer_callback_query(call.id, "Вы не можете голосовать.")
        return

    if player.voted_for:
        bot.answer_callback_query(call.id, "Вы уже проголосовали.")
        return

    target_id = int(call.data.split(':')[1])
    target = game.get_player(target_id)
    if not target: return

    player.voted_for = target_id
    bot.answer_callback_query(call.id, f"Вы проголосовали за {target.tag}.")
    bot.send_message(game.chat_id, f"{player.tag} голосует за {target.tag}.")


@bot.message_handler(commands=['endvote'])
def end_vote(message):
    game = games.get(message.chat.id)
    if not game or game.gm_id != message.from_user.id or game.state != 'VOTE':
        return

    game.state = 'DAY_RESULT'
    game.resolve_vote()
    game.check_win_condition()
    bot.send_message(game.chat_id, "Голосование завершено. Ведущий, начинайте ночь командой /startnight.")


@bot.message_handler(commands=['startnight'])
def gm_start_night(message):
    game = games.get(message.chat.id)
    if not game or game.gm_id != message.from_user.id: return
    start_night(message)


@bot.message_handler(commands=['endgame'])
def end_game(message):
    game = games.get(message.chat.id)
    if game and game.gm_id == message.from_user.id:
        del games[message.chat.id]
        bot.reply_to(message, "Игра принудительно завершена.")


if __name__ == '__main__':
    print("Бот Мафия запущен...")
    bot.infinity_polling()