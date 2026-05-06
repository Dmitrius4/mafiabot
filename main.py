import telebot
import random
from collections import defaultdict, Counter
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

BOT_TOKEN = "YOUR_SUPER_SECRET_BOT_TOKEN"
bot = telebot.TeleBot(BOT_TOKEN)

games = {}

# =========================
# РОЛИ И ФРАКЦИИ
# =========================

ROLE_DESCRIPTIONS = {
    "Шериф": "Ночью проверяет одного игрока на фракцию.",
    "Сержант": "Если Шериф умирает, получает его функционал.",
    "Куртизанка": "Ночью блокирует цель и сама блокируется.",
    "Доктор": "Ночью лечит игрока. Два лечения за игру.",
    "Журналист": "Ночью сравнивает двух игроков по принадлежности к кланам.",
    "Бомж": "Ночью следит за игроком и узнаёт убийцу, если цель умрёт.",
    "Почтальон": "Ночью отправляет анонимную проверку одного игрока другому.",
    "Тюремщик": "Ночью сажает двух игроков в тюрьму. Упрощённая логика.",
    "Стрелок": "Днём может стрелять, кроме первого дня. Заготовка.",
    "Амур": "В первую ночь связывает двух влюблённых.",
    "Судья": "Днём решает судьбу обвиняемых. Заготовка.",
    "Ветеран": "Может встать в режим готовности и убить посетителя.",
    "Маньяк": "Ночью убивает одного игрока.",
    "Путана": "Заражает чумой. Заражение распространяется через визиты.",
    "Ведьма": "Контролирует цель и узнаёт её роль. Имеет одноразовый барьер.",
    "Босс Мафии": "Мафия-убийца.",
    "Киллер Мафии": "Мафия-убийца.",
    "Подручный Мафии": "Мафия.",
    "Босс Якудзы": "Якудза-убийца.",
    "Ниндзя": "Якудза, но для Шерифа выглядит мирным.",
    "Подручный Якудзы": "Якудза."
}

FACTIONS = {
    "мирный": ["Шериф", "Сержант", "Куртизанка", "Доктор", "Журналист", "Бомж", "Почтальон", "Тюремщик", "Стрелок", "Амур", "Судья", "Ветеран"],
    "мафия": ["Босс Мафии", "Киллер Мафии", "Подручный Мафии"],
    "якудза": ["Босс Якудзы", "Ниндзя", "Подручный Якудзы"],
    "нейтрал": ["Маньяк", "Путана", "Ведьма"]
}

ALL_ROLES = list(ROLE_DESCRIPTIONS.keys())


def get_faction(role: str) -> str:
    if role in FACTIONS["мафия"]:
        return "мафия"
    if role in FACTIONS["якудза"]:
        return "якудза"
    if role in FACTIONS["нейтрал"]:
        return "нейтрал"
    if role in FACTIONS["мирный"]:
        return "мирный"
    return "неизвестно"


def sheriff_result_for_target(target_role: str) -> str:
    if target_role in FACTIONS["мафия"] or target_role in FACTIONS["якудза"]:
        return "мафия"
    if target_role in ["Путана", "Ведьма"]:
        return "нейтрал"
    return "мирный"


def journalist_group(player_role: str) -> str:
    if player_role in ["Маньяк", "Путана", "Ведьма"]:
        return "нейтрал"
    if player_role in FACTIONS["мафия"] or player_role in FACTIONS["якудза"]:
        return "бандиты"
    return "мирный"


# =========================
# МОДЕЛЬ ИГРОКА
# =========================

class Player:
    def __init__(self, user_id, username, first_name):
        self.id = user_id
        self.username = username or first_name or str(user_id)
        self.first_name = first_name or str(user_id)
        self.role = None
        self.is_alive = True

        # ночные статусы
        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False
        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False

        # доп. состояния
        self.voted_for = None
        self.in_love_with = None
        self.is_infected = False
        self.witch_barrier = True
        self.courtesan_client = None
        self.revealed_as_shooter = False

        # заряды
        self.doctor_heal_charges = 0
        self.vet_charges = 3
        self.shot_charges = 3

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


# =========================
# ИГРА
# =========================

class Game:
    def __init__(self, chat_id, gm_id):
        self.chat_id = chat_id
        self.gm_id = gm_id
        self.players = {}
        self.state = "LOBBY"  # LOBBY / NIGHT / DAY / ENDED
        self.day = 0
        self.votes = defaultdict(set)
        self.pending_judge_ids = set()
        self.allowed_roles = ALL_ROLES[:]
        self.vote_in_progress = False
        self.postal_used_pairs = set()

    def add_player(self, user):
        if user.id in self.players:
            return False
        self.players[user.id] = Player(user.id, user.username, user.first_name)
        return True

    def remove_player(self, user_id):
        return self.players.pop(user_id, None) is not None

    def get_player(self, player_id):
        return self.players.get(player_id)

    def alive_players(self):
        return [p for p in self.players.values() if p.is_alive]

    def alive_ids(self):
        return [p.id for p in self.alive_players()]

    def role_buttons(self, role_name, target_id=None, target2_id=None):
        kb = InlineKeyboardMarkup()
        if role_name in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Ветеран", "Стрелок"]:
            for p in self.alive_players():
                if p.id != target_id:
                    kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:{role_name}:{p.id}"))
            if role_name == "Ветеран":
                kb.add(InlineKeyboardButton("Встать на готовность", callback_data=f"act:{role_name}:alert"))
        elif role_name in ["Куртизанка", "Тюремщик", "Ведьма"]:
            for p in self.alive_players():
                if p.id != target_id:
                    if role_name == "Ведьма":
                        kb.add(InlineKeyboardButton(f"Выбрать {p.tag} как цель", callback_data=f"act:{role_name}:t1:{p.id}"))
                    else:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:{role_name}:{p.id}"))
        elif role_name == "Журналист":
            for p in self.alive_players():
                kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:{role_name}:j1:{p.id}"))
        elif role_name == "Почтальон":
            for p in self.alive_players():
                kb.add(InlineKeyboardButton(f"Как имя отправителя: {p.tag}", callback_data=f"act:{role_name}:s:{p.id}"))
        elif role_name == "Амур":
            for p in self.alive_players():
                kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:{role_name}:c1:{p.id}"))
        return kb

    def assign_roles(self):
        n = len(self.players)
        roles = self.allowed_roles[:]
        random.shuffle(roles)
        if len(roles) < n:
            raise ValueError("Недостаточно ролей для всех игроков.")
        roles = roles[:n]
        random.shuffle(roles)

        ids = list(self.players.keys())
        random.shuffle(ids)

        for pid, role in zip(ids, roles):
            pl = self.players[pid]
            pl.role = role
            if role == "Доктор":
                pl.doctor_heal_charges = 2

            try:
                bot.send_message(
                    pl.id,
                    f"Игра началась!\nВаша роль: {role}\n{ROLE_DESCRIPTIONS.get(role, '')}"
                )
            except Exception:
                pass

        self.send_team_messages()
        self.state = "NIGHT"
        self.day = 1
        self.open_night_actions()

    def send_team_messages(self):
        mafia = [p.tag for p in self.players.values() if p.role in FACTIONS["mafia"]]
        yakudza = [p.tag for p in self.players.values() if p.role in FACTIONS["yakudza"]]

        for p in self.players.values():
            if p.role in FACTIONS["мафия"]:
                try:
                    bot.send_message(p.id, "Ваша команда мафии: " + ", ".join(mafia))
                except Exception:
                    pass
            if p.role in FACTIONS["якудза"]:
                try:
                    bot.send_message(p.id, "Ваша команда якудзы: " + ", ".join(yakudza))
                except Exception:
                    pass

    def open_night_actions(self):
        for p in self.alive_players():
            if p.role in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Ветеран", "Куртизанка", "Тюремщик"]:
                text = f"Ночь {self.day}. Ваша роль: {p.role}"
                try:
                    if p.role == "Ветеран":
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton("Встать на готовность", callback_data=f"act:Ветеран:alert"))
                        for target in self.alive_players():
                            if target.id != p.id:
                                kb.add(InlineKeyboardButton(target.tag, callback_data=f"act:Ветеран:{target.id}"))
                        bot.send_message(p.id, text, reply_markup=kb)
                    elif p.role == "Журналист":
                        kb = InlineKeyboardMarkup()
                        for target in self.alive_players():
                            kb.add(InlineKeyboardButton(target.tag, callback_data=f"act:Журналист:j1:{target.id}"))
                        bot.send_message(p.id, text + "\nВыберите первую цель.", reply_markup=kb)
                    elif p.role == "Почтальон":
                        kb = InlineKeyboardMarkup()
                        for target in self.alive_players():
                            kb.add(InlineKeyboardButton(f"Имя-отправитель: {target.tag}", callback_data=f"act:Почтальон:s:{target.id}"))
                        bot.send_message(p.id, text + "\nСначала выберите имя отправителя.", reply_markup=kb)
                    elif p.role == "Амур" and self.day == 1:
                        kb = InlineKeyboardMarkup()
                        for target in self.alive_players():
                            kb.add(InlineKeyboardButton(target.tag, callback_data=f"act:Амур:c1:{target.id}"))
                        bot.send_message(p.id, text + "\nВыберите первого влюблённого.", reply_markup=kb)
                    else:
                        kb = InlineKeyboardMarkup()
                        for target in self.alive_players():
                            if target.id != p.id:
                                kb.add(InlineKeyboardButton(target.tag, callback_data=f"act:{p.role}:{target.id}"))
                        bot.send_message(p.id, text, reply_markup=kb)
                except Exception:
                    pass

    def current_suspects(self):
        counter = Counter()
        for voter_id, targets in self.votes.items():
            for t in targets:
                counter[t] += 1
        if not counter:
            return []
        mx = max(counter.values())
        return [pid for pid, c in counter.items() if c == mx and c > 0]

    def process_votes(self):
        suspects = self.current_suspects()
        if not suspects:
            bot.send_message(self.chat_id, "Сегодня никто не был осуждён.")
            return []

        judge = next((p for p in self.alive_players() if p.role == "Судья"), None)
        self.pending_judge_ids = set(suspects)

        if judge and judge.id in suspects:
            judge.is_alive = False
            bot.send_message(self.chat_id, f"Судья {judge.tag} был под подозрением и автоматически казнён.")
            return [judge]

        if judge:
            kb = InlineKeyboardMarkup()
            for pid in suspects:
                pl = self.get_player(pid)
                if pl:
                    kb.add(InlineKeyboardButton(f"Казнить {pl.tag}", callback_data=f"judge:execute:{pid}"))
            kb.add(InlineKeyboardButton("Помиловать всех", callback_data="judge:pardon:all"))
            try:
                bot.send_message(judge.id, "Вы судья. Выберите решение по подозреваемым.", reply_markup=kb)
            except Exception:
                pass
            bot.send_message(self.chat_id, "Судья получил право вынести решение.")
            self.vote_in_progress = True
            return []

        victim_id = suspects[0]
        victim = self.get_player(victim_id)
        if victim:
            victim.is_alive = False
            bot.send_message(self.chat_id, f"По итогам голосования казнён игрок: {victim.tag}")
            return [victim]
        return []

    def resolve_night(self):
        public_log = []
        private_logs = defaultdict(list)
        deaths = set()

        # амур
        if self.day == 1:
            for p in self.alive_players():
                if p.role == "Амур" and p.night_target and p.night_target2:
                    a = self.get_player(p.night_target)
                    b = self.get_player(p.night_target2)
                    if a and b and a.id != b.id:
                        a.in_love_with = b.id
                        b.in_love_with = a.id
                        public_log.append("Амур связал двух влюблённых.")

        # ведьма
        for p in self.alive_players():
            if p.role == "Ведьма" and p.night_target and p.night_target2:
                target = self.get_player(p.night_target)
                forced = self.get_player(p.night_target2)
                if target and forced:
                    private_logs[p.id].append(f"Вы узнали роль цели {target.tag}: {target.role}")
                    private_logs[target.id].append("Вами управляла Ведьма этой ночью.")
                    target.night_target = forced.id

        # путана
        for p in self.alive_players():
            if p.role == "Путана" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    tgt.is_infected = True

        # куртизанка
        for p in self.alive_players():
            if p.role == "Куртизанка" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    tgt.is_blocked = True
                    p.is_blocked = True
                    tgt.courtesan_client = p.id

        # тюремщик
        for p in self.alive_players():
            if p.role == "Тюремщик" and p.night_target and p.night_target2:
                a = self.get_player(p.night_target)
                b = self.get_player(p.night_target2)
                if a:
                    a.is_jailed = True
                if b:
                    b.is_jailed = True

        # доктор
        for p in self.alive_players():
            if p.role == "Доктор" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt and p.doctor_heal_charges > 0:
                    tgt.is_healed = True
                    p.doctor_heal_charges -= 1
                    if tgt.is_infected and tgt.role != "Путана":
                        tgt.is_infected = False

        # шериф/сержант/журналист/почтальон/бомж
        for p in self.alive_players():
            if p.role in ["Шериф", "Сержант"] and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    res = sheriff_result_for_target(tgt.role)
                    private_logs[p.id].append(f"Проверка {tgt.tag}: {res}")

            if p.role == "Журналист" and p.night_target and p.night_target2:
                if p.courtesan_client is not None:
                    private_logs[p.id].append("Проверка отменена: вы клиент Куртизанки.")
                else:
                    a = self.get_player(p.night_target)
                    b = self.get_player(p.night_target2)
                    if a and b:
                        ga = journalist_group(a.role)
                        gb = journalist_group(b.role)
                        if (ga == "бандиты" and gb == "бандиты") or ga == gb:
                            ans = "одинаковые"
                        else:
                            ans = "разные"
                        private_logs[p.id].append(f"{a.tag} и {b.tag} — {ans}")

            if p.role == "Почтальон" and p.night_target and p.night_target2:
                sender = self.get_player(p.night_target)
                receiver = self.get_player(p.night_target2)
                if sender and receiver:
                    pair = (sender.id, receiver.id)
                    if pair in self.postal_used_pairs:
                        private_logs[p.id].append("Этой парой письмо уже отправлялось.")
                    else:
                        self.postal_used_pairs.add(pair)
                        private_logs[receiver.id].append(f"Анонимное письмо от имени {sender.tag}: 'Привет!'")

            if p.role == "Бомж" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    private_logs[p.id].append(f"Вы следили за {tgt.tag}.")

        # убийства
        killers = ["Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы"]
        for p in self.alive_players():
            if p.role in killers and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt and tgt.is_alive:
                    if tgt.is_on_alert:
                        deaths.add(p.id)
                    else:
                        deaths.add(tgt.id)

        # обработка смертей
        dead_now = []
        for pid in list(deaths):
            pl = self.get_player(pid)
            if not pl or not pl.is_alive:
                continue
            if pl.is_jailed or pl.is_healed:
                continue
            if pl.role == "Ведьма" and pl.witch_barrier:
                pl.witch_barrier = False
                continue
            pl.is_alive = False
            dead_now.append(pl)

        # любовь
        for pl in list(dead_now):
            if pl.in_love_with:
                lover = self.get_player(pl.in_love_with)
                if lover and lover.is_alive:
                    lover.is_alive = False
                    dead_now.append(lover)

        # уведомления
        for pid, logs in private_logs.items():
            try:
                bot.send_message(pid, "\n".join(logs))
            except Exception:
                pass

        if dead_now:
            summary = "Этой ночью погибли:\n" + "\n".join([f"{p.tag} ({p.role})" for p in dead_now])
        else:
            summary = "Этой ночью никто не умер."

        if public_log:
            summary = "\n".join(public_log) + "\n\n" + summary

        bot.send_message(self.chat_id, summary)

        # сержант
        if not any(p.is_alive and p.role == "Шериф" for p in self.players.values()):
            ser = next((p for p in self.players.values() if p.is_alive and p.role == "Сержант"), None)
            if ser:
                ser.role = "Шериф"
                bot.send_message(ser.id, "Шериф умер. Теперь вы получаете его функционал.")

        self.reset_night_states()

    def reset_night_states(self):
        for p in self.players.values():
            p.reset_night_state()

    def summary_text(self):
        alive = [p for p in self.alive_players()]
        return "Живы:\n" + "\n".join([f"{p.tag} — {p.role}" for p in alive])


# =========================
# УТИЛИТЫ
# =========================

def get_game(chat_id):
    return games.get(chat_id)


def ensure_game(chat_id, gm_id=None):
    if chat_id not in games:
        games[chat_id] = Game(chat_id, gm_id or chat_id)
    return games[chat_id]


def parse_int(x):
    try:
        return int(x)
    except Exception:
        return None


# =========================
# КОМАНДЫ
# =========================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "Мафия-бот запущен.\n"
        "Команды:\n"
        "/join — вступить в игру\n"
        "/leave — выйти из игры\n"
        "/begin — начать игру (для ведущего)\n"
        "/endnight — завершить ночь (для ведущего)\n"
        "/status — состояние игры"
    )


@bot.message_handler(commands=["join"])
def cmd_join(message):
    game = ensure_game(message.chat.id, message.from_user.id)
    if game.state != "LOBBY":
        bot.send_message(message.chat.id, "Игра уже началась.")
        return
    if game.add_player(message.from_user):
        bot.send_message(message.chat.id, f"{message.from_user.first_name} вошёл в игру.")
    else:
        bot.send_message(message.chat.id, "Вы уже в игре.")


@bot.message_handler(commands=["leave"])
def cmd_leave(message):
    game = get_game(message.chat.id)
    if not game or game.state != "LOBBY":
        bot.send_message(message.chat.id, "Сейчас нельзя выйти.")
        return
    if game.remove_player(message.from_user.id):
        bot.send_message(message.chat.id, "Вы вышли из игры.")
    else:
        bot.send_message(message.chat.id, "Вы не были в игре.")


@bot.message_handler(commands=["begin"])
def cmd_begin(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Игры нет.")
        return
    if game.state != "LOBBY":
        bot.send_message(message.chat.id, "Игра уже началась.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может начать игру.")
        return
    if len(game.players) < 4:
        bot.send_message(message.chat.id, "Слишком мало игроков.")
        return
    try:
        game.assign_roles()
        bot.send_message(message.chat.id, "Игра началась. Наступила ночь.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка старта: {e}")


@bot.message_handler(commands=["endnight"])
def cmd_endnight(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Игры нет.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может завершить ночь.")
        return
    if game.state != "NIGHT":
        bot.send_message(message.chat.id, "Сейчас не ночная фаза.")
        return
    game.resolve_night()
    game.state = "DAY"
    game.day += 1
    bot.send_message(message.chat.id, "Наступил день. Голосуйте /vote <id>.")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Игры нет.")
        return
    bot.send_message(message.chat.id, game.summary_text())


@bot.message_handler(commands=["vote"])
def cmd_vote(message):
    game = get_game(message.chat.id)
    if not game or game.state != "DAY":
        bot.send_message(message.chat.id, "Сейчас не день.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "Использование: /vote <id>")
        return
    target_id = parse_int(args[1])
    if target_id is None or target_id not in game.players or not game.get_player(target_id).is_alive:
        bot.send_message(message.chat.id, "Неверная цель.")
        return

    voter = game.get_player(message.from_user.id)
    if not voter or not voter.is_alive:
        bot.send_message(message.chat.id, "Вы не участвуете.")
        return

    for t in list(game.votes.keys()):
        if message.from_user.id in game.votes[t]:
            game.votes[t].remove(message.from_user.id)

    game.votes[target_id].add(message.from_user.id)
    bot.send_message(message.chat.id, f"Ваш голос за {game.get_player(target_id).tag} принят.")


@bot.message_handler(commands=["lynch"])
def cmd_lynch(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        return
    if game.state != "DAY":
        bot.send_message(message.chat.id, "Сейчас не день.")
        return
    dead = game.process_votes()
    if dead:
        for p in dead:
            if p.role == "Стрелок":
                pass
    game.votes.clear()
    game.state = "NIGHT"
    bot.send_message(message.chat.id, "Наступила ночь.")


# =========================
# CALLBACKS
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    game = get_game(call.message.chat.id)
    if not game:
        bot.answer_callback_query(call.id, "Игры нет.")
        return

    data = call.data.split(":")
    if not data:
        bot.answer_callback_query(call.id, "Ошибка.")
        return

    # judge
    if data[0] == "judge":
        if call.from_user.id != game.gm_id and not any(p.id == call.from_user.id and p.role == "Судья" for p in game.players.values()):
            bot.answer_callback_query(call.id, "Недоступно.")
            return
        action = data[1]
        if action == "execute":
            pid = parse_int(data[2])
            target = game.get_player(pid)
            if target and target.is_alive:
                target.is_alive = False
                bot.send_message(game.chat_id, f"Судья приговорил {target.tag} к казни.")
                game.vote_in_progress = False
        elif action == "pardon":
            bot.send_message(game.chat_id, "Судья помиловал всех.")
            game.vote_in_progress = False
        bot.answer_callback_query(call.id, "Решение принято.")
        return

    if data[0] != "act":
        bot.answer_callback_query(call.id, "Неизвестное действие.")
        return

    role = data[1]
    player = game.get_player(call.from_user.id)
    if not player or not player.is_alive:
        bot.answer_callback_query(call.id, "Вы не в игре.")
        return

    if game.state != "NIGHT":
        bot.answer_callback_query(call.id, "Сейчас не ночь.")
        return

    # выбор цели
    if role == "Ветеран":
        if len(data) == 3 and data[2] == "alert":
            if player.vet_charges <= 0:
                bot.answer_callback_query(call.id, "У вас закончились заряды.")
                return
            player.is_on_alert = True
            player.vet_charges -= 1
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Вы встали на готовность.")
            return
        pid = parse_int(data[2])
        if pid:
            player.night_target = pid
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Цель выбрана.")
            return

    if role == "Журналист":
        stage = data[2]
        pid = parse_int(data[3])
        if stage == "j1":
            player.night_target = pid
            player.night_action_done = False
            kb = InlineKeyboardMarkup()
            for p in game.alive_players():
                if p.id != pid:
                    kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:Журналист:j2:{p.id}"))
            bot.edit_message_text(
                "Выберите вторую цель.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb
            )
            bot.answer_callback_query(call.id, "Первая цель выбрана.")
            return
        if stage == "j2":
            player.night_target2 = pid
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Цели выбраны.")
            return

    if role == "Почтальон":
        stage = data[2]
        pid = parse_int(data[3])
        if stage == "s":
            player.night_target = pid
            kb = InlineKeyboardMarkup()
            for p in game.alive_players():
                if p.id != pid:
                    kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:Почтальон:r:{p.id}"))
            bot.edit_message_text(
                "Кому отправить проверку?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb
            )
            bot.answer_callback_query(call.id, "Отправитель выбран.")
            return
        if stage == "r":
            player.night_target2 = pid
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Письмо подготовлено.")
            return

    if role == "Амур":
        stage = data[2]
        pid = parse_int(data[3])
        if stage == "c1":
            player.night_target = pid
            kb = InlineKeyboardMarkup()
            for p in game.alive_players():
                if p.id != pid and p.id != player.id:
                    kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:Амур:c2:{p.id}"))
            bot.edit_message_text(
                "Выберите второго влюблённого.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb
            )
            bot.answer_callback_query(call.id, "Первая цель выбрана.")
            return
        if stage == "c2":
            player.night_target2 = pid
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Влюблённые выбраны.")
            return

    if role == "Ведьма":
        stage = data[2]
        pid = parse_int(data[3])
        if stage == "t1":
            player.night_target = pid
            kb = InlineKeyboardMarkup()
            for p in game.alive_players():
                if p.id != pid:
                    kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:Ведьма:t2:{p.id}"))
            bot.edit_message_text(
                "Выберите действие/цель, на которую направить контроль.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=kb
            )
            bot.answer_callback_query(call.id, "Первая цель выбрана.")
            return
        if stage == "t2":
            player.night_target2 = pid
            player.night_action_done = True
            bot.answer_callback_query(call.id, "Контроль выбран.")
            return

    if role == "Тюремщик":
        pid = parse_int(data[2])
        if pid:
            if player.night_target is None:
                player.night_target = pid
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != pid:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:Тюремщик:{p.id}"))
                bot.edit_message_text(
                    "Выберите второго заключённого.",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=kb
                )
                bot.answer_callback_query(call.id, "Первая цель выбрана.")
                return
            else:
                player.night_target2 = pid
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Оба заключённых выбраны.")
                return

    # остальные роли: одна цель
    pid = parse_int(data[-1])
    if pid is None:
        bot.answer_callback_query(call.id, "Ошибка цели.")
        return

    if role in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы"]:
        player.night_target = pid
        player.night_action_done = True
        bot.answer_callback_query(call.id, "Цель выбрана.")
        return

    bot.answer_callback_query(call.id, "Для этой роли действие не настроено.")


# =========================
# СООБЩЕНИЯ-ХЕНДЛЕРЫ ДЛЯ ТИПОВЫХ СЛУЧАЕВ
# =========================

@bot.message_handler(content_types=["text"])
def text_handler(message):
    game = get_game(message.chat.id)
    if not game:
        return
    if message.text.startswith("/"):
        return

    # Если нужно, можно здесь добавить обработку приватных дневных сообщений,
    # например для судьи или стрелка. Сейчас основная логика через команды/кнопки.
    pass


if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
