import telebot
import random
from collections import defaultdict, Counter
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = ""
bot = telebot.TeleBot(BOT_TOKEN)

games = {}


# =========================================================
# РОЛИ И ФРАКЦИИ
# =========================================================

ROLE_DESCRIPTIONS = {
    "Шериф": "Ночью проверяет одного игрока на фракцию.",
    "Сержант": "Если Шериф умирает, получает его функционал.",
    "Куртизанка": "Ночью блокирует цель и сама блокируется.",
    "Доктор": "Ночью лечит игрока. Два лечения за игру.",
    "Журналист": "Ночью сравнивает двух игроков по принадлежности к кланам.",
    "Бомж": "Ночью следит за игроком и узнаёт убийцу, если цель умрёт.",
    "Почтальон": "Ночью отправляет анонимную проверку одного игрока другому.",
    "Тюремщик": "Ночью сажает двух игроков в тюрьму.",
    "Стрелок": "Днём может стрелять. Нельзя стрелять в первый день.",
    "Амур": "В первую ночь связывает двух влюблённых.",
    "Судья": "После голосования решает судьбу подозреваемых.",
    "Ветеран": "Может встать в боевую готовность и убить посетителя.",
    "Маньяк": "Ночью убивает одного игрока.",
    "Путана": "Заражает чумой. Заражение распространяется через визиты.",
    "Ведьма": "Контролирует цель, узнаёт её роль, имеет одноразовый барьер.",
    "Босс Мафии": "Мафия-убийца.",
    "Киллер Мафии": "Мафия-убийца.",
    "Подручный Мафии": "Мафия.",
    "Босс Якудзы": "Якудза-убийца.",
    "Ниндзя": "Якудза.",
    "Подручный Якудзы": "Якудза."
}

FACTIONS = {
    "мирный": ["Шериф", "Сержант", "Куртизанка", "Доктор", "Журналист", "Бомж", "Почтальон", "Тюремщик", "Стрелок", "Амур", "Судья", "Ветеран"],
    "мафия": ["Босс Мафии", "Киллер Мафии", "Подручный Мафии"],
    "якудза": ["Босс Якудзы", "Ниндзя", "Подручный Якудзы"],
    "нейтрал": ["Маньяк", "Путана", "Ведьма"]
}

ALL_ROLES = list(ROLE_DESCRIPTIONS.keys())


def sheriff_view(role):
    if role in FACTIONS["мафия"] or role in FACTIONS["якудза"]:
        return "мафия"
    if role in ["Путана", "Ведьма"]:
        return "нейтрал"
    return "мирный"


def journalist_view(role):
    if role in ["Маньяк", "Путана", "Ведьма"]:
        return "нейтрал"
    if role in FACTIONS["мафия"] or role in FACTIONS["якудза"]:
        return "бандиты"
    return "мирный"


def safe_int(v):
    try:
        return int(v)
    except Exception:
        return None


# =========================================================
# МОДЕЛЬ ИГРОКА
# =========================================================

class Player:
    def __init__(self, user_id, username, first_name):
        self.id = user_id
        self.username = username or first_name or str(user_id)
        self.first_name = first_name or str(user_id)
        self.role = None
        self.is_alive = True

        self.is_blocked = False
        self.is_healed = False
        self.is_jailed = False
        self.is_on_alert = False

        self.night_target = None
        self.night_target2 = None
        self.night_action_done = False

        self.in_love_with = None
        self.is_infected = False
        self.witch_barrier = True
        self.courtesan_client = None

        self.doctor_heal_charges = 0
        self.vet_charges = 3
        self.shot_charges = 1

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


# =========================================================
# ИГРА
# =========================================================

class Game:
    def __init__(self, chat_id, gm_id, gm_name):
        self.chat_id = chat_id
        self.gm_id = gm_id
        self.gm_name = gm_name
        self.players = {}
        self.state = "LOBBY"
        self.registration_open = False
        self.day = 0
        self.vote_open = False
        self.votes = defaultdict(set)
        self.allowed_roles = ALL_ROLES[:]
        self.custom_roles = []
        self.postal_used_pairs = set()
        self.pending_judge = []

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

    def summary_text(self):
        text = (
            f"Фаза: {self.state}\n"
            f"День: {self.day}\n"
            f"Регистрация: {'открыта' if self.registration_open else 'закрыта'}\n"
            f"Голосование: {'открыто' if self.vote_open else 'закрыто'}\n"
            f"Ведущий: {self.gm_name}\n"
            f"Живы:\n"
        )
        for p in self.alive_players():
            text += f"- {p.tag}\n"
        return text

    def assign_roles(self):
        n = len(self.players)

        if self.custom_roles:
            if len(self.custom_roles) != n:
                raise ValueError(
                    f"Количество заданных ролей ({len(self.custom_roles)}) не совпадает с количеством игроков ({n}).")
            roles = self.custom_roles[:]
        else:
            roles = self.allowed_roles[:]
            random.shuffle(roles)
            if len(roles) < n:
                raise ValueError("Недостаточно ролей.")
            roles = roles[:n]
            random.shuffle(roles)

        ids = list(self.players.keys())
        random.shuffle(ids)

        for pid, role in zip(ids, roles):
            p = self.players[pid]
            p.role = role
            if role == "Доктор":
                p.doctor_heal_charges = 2
            try:
                bot.send_message(
                    p.id,
                    f"Игра началась!\nВаша роль: {role}\n{ROLE_DESCRIPTIONS.get(role, '')}"
                )
            except Exception as e:
                print(f"Не смог отправить роль игроку {p.id}: {e}")

        self.send_team_messages()
        self.state = "NIGHT"
        self.day = 1
        self.open_night_actions()

    def send_team_messages(self):
        mafia = [p.tag for p in self.players.values() if p.role in FACTIONS["мафия"]]
        yakudza = [p.tag for p in self.players.values() if p.role in FACTIONS["якудза"]]

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
            p.night_action_done = False
            if p.role in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии",
                          "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Ветеран", "Куртизанка",
                          "Тюремщик", "Журналист", "Почтальон", "Амур", "Ведьма"]:
                send_night_prompt(p)

    def current_suspects(self):
        counter = Counter()
        for _, targets in self.votes.items():
            for t in targets:
                counter[t] += 1
        if not counter:
            return []
        mx = max(counter.values())
        return [pid for pid, c in counter.items() if c == mx and c > 0]

    def process_votes(self):
        suspects = self.current_suspects()
        if not suspects:
            bot.send_message(self.chat_id, "По итогам голосования никто не был казнён.")
            return []

        judge = next((p for p in self.alive_players() if p.role == "Судья"), None)

        if judge and judge.id in suspects:
            judge.is_alive = False
            bot.send_message(self.chat_id, f"Судья {judge.tag} был среди подозреваемых и автоматически казнён.")
            return [judge]

        if judge:
            self.pending_judge = suspects
            kb = InlineKeyboardMarkup()
            for pid in suspects:
                pl = self.get_player(pid)
                if pl and pl.is_alive:
                    kb.add(InlineKeyboardButton(f"Казнить {pl.tag}", callback_data=f"judge:execute:{pid}"))
            kb.add(InlineKeyboardButton("Помиловать всех", callback_data="judge:pardon:all"))
            try:
                bot.send_message(judge.id, "Вы Судья. Выберите решение.", reply_markup=kb)
            except Exception:
                pass
            bot.send_message(self.chat_id, "Судье отправлено решение.")
            return []

        victim = self.get_player(suspects[0])
        if victim:
            victim.is_alive = False
            bot.send_message(self.chat_id, f"По итогам голосования казнён {victim.tag}.")
            return [victim]
        return []

    def end_night_and_start_day(self):
        self.resolve_night()
        self.state = "DAY"
        self.vote_open = False
        bot.send_message(self.chat_id, f"Наступил день {self.day}. Голосование пока закрыто. Ведущий может открыть его командой /startvote.")

    def end_day_and_start_night(self):
        if self.vote_open:
            self.process_votes()
        self.votes.clear()
        self.vote_open = False
        self.state = "NIGHT"
        self.day += 1
        self.open_night_actions()
        roles_now = set(p.role for p in self.alive_players())
        bot.send_message(self.chat_id, f"Наступила ночь {self.day}. Активные роли: {', '.join(sorted(roles_now))}")

    def resolve_night(self):
        public_log = []
        private_logs = defaultdict(list)
        deaths = set()
        doomed = []

        cupid = next((p for p in self.alive_players() if p.role == "Амур"), None)
        if self.day == 1 and cupid and cupid.night_target and cupid.night_target2:
            a = self.get_player(cupid.night_target)
            b = self.get_player(cupid.night_target2)
            if a and b and a.id != b.id:
                a.in_love_with = b.id
                b.in_love_with = a.id
                public_log.append("Амур связал двух влюблённых.")

        for p in self.alive_players():
            if p.role == "Ведьма" and p.night_target and p.night_target2:
                target = self.get_player(p.night_target)
                forced = self.get_player(p.night_target2)
                if target and forced:
                    private_logs[p.id].append(f"Роль цели {target.tag}: {target.role}")
                    private_logs[target.id].append("Вами управляла Ведьма этой ночью.")
                    target.night_target = forced.id

        for p in self.alive_players():
            if p.role == "Путана" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    tgt.is_infected = True

        for p in self.alive_players():
            if p.role == "Куртизанка" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    tgt.is_blocked = True
                    p.is_blocked = True
                    tgt.courtesan_client = p.id

        for p in self.alive_players():
            if p.role == "Тюремщик" and p.night_target and p.night_target2:
                a = self.get_player(p.night_target)
                b = self.get_player(p.night_target2)
                if a:
                    a.is_jailed = True
                if b:
                    b.is_jailed = True

        for p in self.alive_players():
            if p.role == "Доктор" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt and p.doctor_heal_charges > 0:
                    tgt.is_healed = True
                    p.doctor_heal_charges -= 1

        for p in self.alive_players():
            if p.role in ["Шериф", "Сержант"] and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    private_logs[p.id].append(f"Проверка {tgt.tag}: {sheriff_view(tgt.role)}")

        for p in self.alive_players():
            if p.role == "Журналист" and p.night_target and p.night_target2:
                if p.courtesan_client is not None:
                    private_logs[p.id].append("Проверка отменена: вы клиент Куртизанки.")
                else:
                    a = self.get_player(p.night_target)
                    b = self.get_player(p.night_target2)
                    if a and b:
                        ga = journalist_view(a.role)
                        gb = journalist_view(b.role)
                        ans = "одинаковые" if ((ga == "бандиты" and gb == "бандиты") or ga == gb) else "разные"
                        private_logs[p.id].append(f"{a.tag} и {b.tag} — {ans}")

        for p in self.alive_players():
            if p.role == "Почтальон" and p.night_target and p.night_target2:
                sender = self.get_player(p.night_target)
                receiver = self.get_player(p.night_target2)
                if sender and receiver:
                    pair = (sender.id, receiver.id)
                    if pair in self.postal_used_pairs:
                        private_logs[p.id].append("Этой парой письмо уже отправлялось.")
                    else:
                        self.postal_used_pairs.add(pair)
                        private_logs[receiver.id].append(f"Анонимное письмо от имени {sender.tag}: 'Проверка доставлена.'")

        for p in self.alive_players():
            if p.role == "Бомж" and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt:
                    private_logs[p.id].append(f"Вы следили за {tgt.tag}.")

        killers = ["Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы"]
        for p in self.alive_players():
            if p.role in killers and p.night_target:
                tgt = self.get_player(p.night_target)
                if tgt and tgt.is_alive:
                    if tgt.is_on_alert:
                        deaths.add(p.id)
                    else:
                        deaths.add(tgt.id)

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
            doomed.append(pl)

        for pl in list(doomed):
            if pl.in_love_with:
                lover = self.get_player(pl.in_love_with)
                if lover and lover.is_alive:
                    lover.is_alive = False
                    doomed.append(lover)

        for pid, logs in private_logs.items():
            try:
                bot.send_message(pid, "\n".join(logs))
            except Exception:
                pass

        if public_log:
            bot.send_message(self.chat_id, "\n".join(public_log))

        if doomed:
            bot.send_message(self.chat_id, "Погибли:\n" + "\n".join([f"{p.tag} ({p.role})" for p in doomed]))
        else:
            bot.send_message(self.chat_id, "Этой ночью никто не умер.")

        if not any(p.is_alive and p.role == "Шериф" for p in self.players.values()):
            ser = next((p for p in self.players.values() if p.is_alive and p.role == "Сержант"), None)
            if ser:
                ser.role = "Шериф"
                bot.send_message(ser.id, "Шериф умер. Теперь вы получили его функционал.")

        self.reset_night_states()

    def reset_night_states(self):
        for p in self.players.values():
            p.reset_night_state()


def get_game(chat_id):
    return games.get(chat_id)

def ensure_game(chat_id, gm_id=None, gm_name=None):
    if chat_id not in games:
        games[chat_id] = Game(chat_id, gm_id or chat_id, gm_name or "Неизвестно")
    return games[chat_id]


# =========================================================
# HELP
# =========================================================

PLAYER_HELP = (
    "Команды игрока:\n"
    "/join — войти в лобби\n"
    "/leave — выйти из лобби\n"
    "/status — посмотреть состояние игры\n"
    "/vote <id> — проголосовать, если голосование открыто\n"
    "/help — эта справка"
)

GM_HELP = (
    "Команды ведущего:\n"
    "/newgame — создать новую сессию\n"
    "/roletoggle <роль> — включить/выключить роль\n"
    "/roles — показать текущие разрешённые роли\n"
    "/startgame — начать игру\n"
    "/startvote — открыть голосование\n"
    "/closevote — закрыть голосование\n"
    "/day — начать день\n"
    "/night — начать ночь\n"
    "/endgame — завершить игру\n"
    "/status — текущее состояние\n"
    "/help — эта справка"
)


# =========================================================
# КОМАНДЫ
# =========================================================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "Мафия-бот запущен.\n"
        "Чтобы создать сессию, ведущий должен написать /newgame.\n"
        "Игроки: /join /leave /status /vote /help\n"
        "Ведущий: /startgame /startvote /closevote /day /night /endgame /help"
    )

@bot.message_handler(commands=["newgame"])
def cmd_newgame(message):
    if message.chat.type not in ["group", "supergroup"]:
        bot.send_message(message.chat.id, "Сессию лучше создавать в группе.")
        return
    games[message.chat.id] = Game(message.chat.id, message.from_user.id, message.from_user.first_name)
    games[message.chat.id].registration_open = True
    bot.send_message(
        message.chat.id,
        f"Новая сессия создана. Ведущий: {message.from_user.first_name}\n"
        f"Регистрация открыта. Игроки могут вступать командой /join"
    )

@bot.message_handler(commands=["roletoggle"])
def cmd_roletoggle(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Сессия не создана.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может менять роли.")
        return
    if game.state != "LOBBY":
        bot.send_message(message.chat.id, "Настройка ролей возможна только в лобби.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, "Используйте: /roletoggle <название_роли>")
        return
    role = args[1].strip()
    if role not in ALL_ROLES:
        bot.send_message(message.chat.id, f"Роль '{role}' не найдена.")
        return

    if role in game.allowed_roles:
        game.allowed_roles.remove(role)
        bot.send_message(message.chat.id, f"Роль '{role}' отключена.")
    else:
        game.allowed_roles.append(role)
        bot.send_message(message.chat.id, f"Роль '{role}' включена.")

@bot.message_handler(commands=["roles"])
def cmd_roles(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Сессия не создана.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может смотреть роли.")
        return
    roles_text = "\n".join(game.allowed_roles)
    bot.send_message(message.chat.id, f"Разрешённые роли:\n{roles_text}")

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "Команды бота:\n\n"
        "/start — Запустить бота и получить инструкции\n"
        "/newgame — Создать новую игру (только ведущий)\n"
        "/join — Присоединиться к игре\n"
        "/leave — Выйти из игры\n"
        "/setrolesconfig — Настроить список ролей для партии (только ведущий)\n"
        "/setroles — Назначить роли игрокам и начать игру (только ведущий)\n"
        "/day — Начать день после ночи\n"
        "/skip — Пропустить ход\n"
        "/endgame — Завершить игру\n\n"
        "Подробно о новых командах:\n\n"
        "/setrolesconfig\n"
        "Ведущий может выбрать, какие роли будут доступны в текущей игре. Получите список ролей с кнопками \"включить/выключить\", настройте состав по своему вкусу. Рекомендуется делать это до начала игры.\n\n"
        "/setroles\n"
        "Назначить роли из выбранного ведущим набора и начать игру. После запуска роли будет невозможно менять. Игроки получат свои роли в личных сообщениях и смогут делать ночные ходы.\n\n"
        "Если нужна помощь или инструкции — пиши /help"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=["setroles"])
def cmd_setroles(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Сессия не создана.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может задавать роли.")
        return
    if game.state != "LOBBY":
        bot.send_message(message.chat.id, "Роли можно задавать только до старта игры.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, "Использование: /setroles Роль1 Роль2 Роль3 ...")
        return

    roles = args[1].split()

    for r in roles:
        if r not in ALL_ROLES:
            bot.send_message(message.chat.id, f"Неизвестная роль: {r}")
            return

    if len(roles) != len(game.players):
        bot.send_message(message.chat.id, f"Нужно ролей ровно столько же, сколько игроков: {len(game.players)}")
        return

    game.custom_roles = roles[:]
    bot.send_message(message.chat.id, "Роли на партию заданы:\n" + "\n".join(game.custom_roles))


@bot.message_handler(commands=['setrolesconfig'])
def roles_config(message):
    game = games.get(message.chat.id)
    if not game:
        bot.reply_to(message, "Игра в этом чате не найдена.")
        return
    if message.from_user.id != game.gm_id:
        bot.reply_to(message, "Только ведущий может управлять настройками ролей.")
        return

    if not hasattr(game, 'enabled_roles'):
        game.enabled_roles = ALL_ROLES.copy()

    kb = InlineKeyboardMarkup(row_width=3)
    for role in ALL_ROLES:
        symbol = "✅" if role in game.enabled_roles else "❌"
        kb.add(InlineKeyboardButton(f"{symbol} {role}", callback_data=f"role_toggle:{role}"))

    bot.send_message(game.chat_id, "Выберите роли для включения/отключения:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("role_toggle:"))
def toggle_role_callback(call):
    game = games.get(call.message.chat.id)
    if not game or call.from_user.id != game.gm_id:
        bot.answer_callback_query(call.id, "Только ведущий может менять роли.")
        return

    role = call.data[len("role_toggle:"):]
    if not hasattr(game, 'enabled_roles'):
        game.enabled_roles = ALL_ROLES.copy()

    if role in game.enabled_roles:
        game.enabled_roles.remove(role)
    else:
        game.enabled_roles.append(role)

    # Обновляем кнопку
    kb = InlineKeyboardMarkup(row_width=3)
    for r in ALL_ROLES:
        symbol = "✅" if r in game.enabled_roles else "❌"
        kb.add(InlineKeyboardButton(f"{symbol} {r}", callback_data=f"role_toggle:{r}"))
    try:
        bot.edit_message_reply_markup(game.chat_id, call.message.message_id, reply_markup=kb)
    except Exception:
        pass
    bot.answer_callback_query(call.id, f"Роль {role} {'включена' if role in game.enabled_roles else 'отключена'}.")

@bot.message_handler(commands=["join"])
def cmd_join(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Сначала ведущий должен создать сессию командой /newgame")
        return
    if game.state != "LOBBY" or not game.registration_open:
        bot.send_message(message.chat.id, "Регистрация закрыта.")
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

@bot.message_handler(commands=["status"])
def cmd_status(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Игры нет.")
        return
    bot.send_message(message.chat.id, game.summary_text())

@bot.message_handler(commands=["startgame"])
def cmd_startgame(message):
    game = get_game(message.chat.id)
    if not game:
        bot.send_message(message.chat.id, "Игры нет.")
        return
    if message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Только ведущий может начать.")
        return
    if game.state != "LOBBY":
        bot.send_message(message.chat.id, "Игра уже запущена.")
        return
    if len(game.players) < 4:
        bot.send_message(message.chat.id, "Слишком мало игроков.")
        return

    game.registration_open = False

    try:
        game.assign_roles()
        bot.send_message(message.chat.id, "Игра началась. Ночь 1.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при старте игры: {e}")

@bot.message_handler(commands=["startvote"])
def cmd_startvote(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Недоступно.")
        return
    if game.state != "DAY":
        bot.send_message(message.chat.id, "Голосование можно открыть только днём.")
        return
    game.vote_open = True
    bot.send_message(message.chat.id, "Голосование открыто. Используйте /vote <id>.")

@bot.message_handler(commands=["closevote"])
def cmd_closevote(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Недоступно.")
        return
    if game.state != "DAY":
        bot.send_message(message.chat.id, "Голосование можно закрыть только днём.")
        return
    if not game.vote_open:
        bot.send_message(message.chat.id, "Голосование уже закрыто.")
        return
    game.vote_open = False
    game.process_votes()
    game.votes.clear()
    bot.send_message(message.chat.id, "Голосование закрыто и итог обработан.")

@bot.message_handler(commands=["day"])
def cmd_day(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Недоступно.")
        return
    if game.state != "NIGHT":
        bot.send_message(message.chat.id, "Сейчас не ночь.")
        return
    game.end_night_and_start_day()

@bot.message_handler(commands=["night"])
def cmd_night(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Недоступно.")
        return
    if game.state != "DAY":
        bot.send_message(message.chat.id, "Сейчас не день.")
        return
    game.end_day_and_start_night()

@bot.message_handler(commands=["endgame"])
def cmd_endgame(message):
    game = get_game(message.chat.id)
    if not game or message.from_user.id != game.gm_id:
        bot.send_message(message.chat.id, "Недоступно.")
        return
    game.state = "ENDED"
    game.vote_open = False
    bot.send_message(message.chat.id, "Игра завершена.")

@bot.message_handler(commands=["vote"])
def cmd_vote(message):
    game = get_game(message.chat.id)
    if not game or game.state != "DAY":
        bot.send_message(message.chat.id, "Сейчас не день.")
        return
    if not game.vote_open:
        bot.send_message(message.chat.id, "Голосование закрыто.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "Использование: /vote <id>")
        return
    target_id = safe_int(args[1])
    target = game.get_player(target_id)
    voter = game.get_player(message.from_user.id)
    if not target or not target.is_alive:
        bot.send_message(message.chat.id, "Неверная цель.")
        return
    if not voter or not voter.is_alive:
        bot.send_message(message.chat.id, "Вы не участвуете.")
        return
    for t in list(game.votes.keys()):
        game.votes[t].discard(message.from_user.id)
    game.votes[target_id].add(message.from_user.id)
    bot.send_message(message.chat.id, f"Голос за {target.tag} принят.")


# =========================================================
# CALLBACKS
# =========================================================

def send_night_prompt(player):
    game = None
    for g in games.values():
        if player.id in g.players:
            game = g
            break
    if not game:
        return

    kb = InlineKeyboardMarkup()

    def add_targets(prefix, exclude_self=True):
        for p in game.alive_players():
            if exclude_self and p.id == player.id:
                continue
            kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:{prefix}:{p.id}"))

    if player.role in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы"]:
        add_targets("target")
        bot.send_message(player.id, f"Ночь {game.day}. Ваша роль: {player.role}", reply_markup=kb)

    elif player.role == "Куртизанка":
        add_targets("target")
        bot.send_message(player.id, f"Ночь {game.day}. Выберите цель.", reply_markup=kb)

    elif player.role == "Тюремщик":
        add_targets("target1")
        bot.send_message(player.id, f"Ночь {game.day}. Выберите первого заключённого.", reply_markup=kb)

    elif player.role == "Журналист":
        add_targets("target1")
        bot.send_message(player.id, f"Ночь {game.day}. Выберите первого игрока.", reply_markup=kb)

    elif player.role == "Почтальон":
        add_targets("target1")
        bot.send_message(player.id, f"Ночь {game.day}. Выберите имя-отправителя.", reply_markup=kb)

    elif player.role == "Амур" and game.day == 1:
        add_targets("target1")
        bot.send_message(player.id, "Первая ночь. Выберите первого влюблённого.", reply_markup=kb)

    elif player.role == "Ведьма":
        add_targets("target1")
        bot.send_message(player.id, f"Ночь {game.day}. Выберите цель для контроля.", reply_markup=kb)

    elif player.role == "Ветеран":
        kb.add(InlineKeyboardButton("Встать на готовность", callback_data="act:alert:0"))
        add_targets("target")
        bot.send_message(player.id, f"Ночь {game.day}.", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    try:
        data = call.data or ""
        print("CALLBACK:", data, "FROM:", call.from_user.id)

        game = None
        for g in games.values():
            if call.from_user.id in g.players:
                game = g
                break

        if not game:
            bot.answer_callback_query(call.id, "Игры нет.")
            return

        player = game.get_player(call.from_user.id)
        if not player or not player.is_alive:
            bot.answer_callback_query(call.id, "Вы не в игре.")
            return

        if game.state != "NIGHT":
            bot.answer_callback_query(call.id, "Сейчас не ночь.")
            return

        if player.night_action_done:
            bot.answer_callback_query(call.id, "Вы уже сделали ход этой ночью.")
            return

        parts = data.split(":")
        if len(parts) < 2:
            bot.answer_callback_query(call.id, "Ошибка кнопки.")
            return

        action_type = parts[1]
        value = parts[2] if len(parts) > 2 else None

        # --- Ветеран ---
        if player.role == "Ветеран":
            if action_type == "alert":
                if player.vet_charges <= 0:
                    bot.answer_callback_query(call.id, "Заряды закончились.")
                    return
                player.is_on_alert = True
                player.vet_charges -= 1
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Готовность активирована.")
                return

            if action_type == "target":
                target = safe_int(value)
                player.night_target = target
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Цель выбрана.")
                return

        # --- Одношаговые роли ---
        if player.role in ["Шериф", "Сержант", "Доктор", "Бомж", "Путана", "Маньяк", "Босс Мафии", "Киллер Мафии", "Подручный Мафии", "Босс Якудзы", "Ниндзя", "Подручный Якудзы", "Куртизанка"]:
            if action_type == "target":
                target = safe_int(value)
                player.night_target = target
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Цель выбрана.")
                return

        # --- Журналист ---
        if player.role == "Журналист":
            if action_type == "target1":
                player.night_target = safe_int(value)
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != player.id and p.id != player.night_target:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:target2:{p.id}"))
                bot.edit_message_text("Выберите второго игрока.", call.message.chat.id, call.message.message_id, reply_markup=kb)
                bot.answer_callback_query(call.id, "Первая цель выбрана.")
                return

            if action_type == "target2":
                player.night_target2 = safe_int(value)
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Цели выбраны.")
                return

        # --- Почтальон ---
        if player.role == "Почтальон":
            if action_type == "target1":
                player.night_target = safe_int(value)
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != player.id and p.id != player.night_target:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:target2:{p.id}"))
                bot.edit_message_text("Выберите получателя.", call.message.chat.id, call.message.message_id, reply_markup=kb)
                bot.answer_callback_query(call.id, "Имя-отправитель выбрано.")
                return

            if action_type == "target2":
                player.night_target2 = safe_int(value)
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Письмо готово.")
                return

        # --- Амур ---
        if player.role == "Амур":
            if action_type == "target1":
                player.night_target = safe_int(value)
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != player.id and p.id != player.night_target:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:target2:{p.id}"))
                bot.edit_message_text("Выберите второго влюблённого.", call.message.chat.id, call.message.message_id, reply_markup=kb)
                bot.answer_callback_query(call.id, "Первая цель выбрана.")
                return

            if action_type == "target2":
                player.night_target2 = safe_int(value)
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Влюблённые выбраны.")
                return

        # --- Ведьма ---
        if player.role == "Ведьма":
            if action_type == "target1":
                player.night_target = safe_int(value)
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != player.id and p.id != player.night_target:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:target2:{p.id}"))
                bot.edit_message_text("Выберите цель контроля.", call.message.chat.id, call.message.message_id, reply_markup=kb)
                bot.answer_callback_query(call.id, "Первая цель выбрана.")
                return

            if action_type == "target2":
                player.night_target2 = safe_int(value)
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Контроль выбран.")
                return

        # --- Тюремщик ---
        if player.role == "Тюремщик":
            if action_type == "target1":
                player.night_target = safe_int(value)
                kb = InlineKeyboardMarkup()
                for p in game.alive_players():
                    if p.id != player.id and p.id != player.night_target:
                        kb.add(InlineKeyboardButton(p.tag, callback_data=f"act:target2:{p.id}"))
                bot.edit_message_text("Выберите второго заключённого.", call.message.chat.id, call.message.message_id, reply_markup=kb)
                bot.answer_callback_query(call.id, "Первая цель выбрана.")
                return

            if action_type == "target2":
                player.night_target2 = safe_int(value)
                player.night_action_done = True
                bot.answer_callback_query(call.id, "Заключённые выбраны.")
                return

        bot.answer_callback_query(call.id, "Не обработано.")

    except Exception as e:
        print("CALLBACK ERROR:", e)
        try:
            bot.answer_callback_query(call.id, "Ошибка.")
        except:
            pass


if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
