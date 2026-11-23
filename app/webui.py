# -*- coding: utf-8 -*-
"""Новый интерфейс: окно с веб-страницей (pywebview) и Python за ним.

Backend держит состояние программы (телефон, логи, история, обновление) и отдаёт странице
готовые к показу данные — уже переведённые. Страница (app/web) только рисует.
Связь: в программе — pywebview (window.pywebview.api), в тестах — HTTP (tools/webui_dev.py).
Если веб-окно недоступно (например, нет WebView2 на старой Windows), запускается прежнее окно (gui.py).
"""

import os
import queue
import subprocess
import sys
import threading
import urllib.parse
from collections import Counter
from datetime import datetime

import core
import i18n
import report_pdf
import themes
import updater
import views
from core import APP_TITLE, build_verdict, collect_files, parse_log, parse_pasted, parts_table
from device import DeviceWatcher, device_support
from history import History, phone_key
from i18n import _, plural
from knowledge_base import CATEGORIES, KB, PRODUCTS

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
WEB_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "web")

IACTIVATOR_URL = "https://github.com/mr1garik/iActivator"
IACTIVATOR_DOWNLOAD = "https://github.com/mr1garik/iActivator/releases/latest"
DONATE_ADDRESS = "TQKtZpsdz7pm9cuXWPE3ZQEboPHva4Uuas"   # USDT, сеть TRC20 (Tron)
DONATE_NETWORK = "USDT · TRC20 (Tron)"
ISSUES_URL = "https://github.com/mr1garik/ios-panic-reader/issues/new?"

# Где искать на плате: сторона/зона (для схемы) и что проверить. Общие подсказки по узлам,
# без номеров микросхем конкретной модели — их смотрите по схеме своей платы.
BOARD = {
    "battery": ("battery", _("Аккумулятор и его разъём на плате"),
                _("Разъём аккумулятора, сам аккумулятор, контроллер аккумулятора (на шлейфе аккумулятора).")),
    "charge_flex": ("bottom", _("Низ телефона: шлейф зарядки и его разъём на плате"),
                    _("Шлейф зарядки (нижний микрофон, барометр), разъём шлейфа на плате, следы влаги у разъёма.")),
    "top_flex": ("top", _("Верх телефона: верхний шлейф (датчики, фронтальная камера, микрофон)"),
                 _("Верхний шлейф и его разъём на плате, датчик приближения, фронтальный микрофон.")),
    "display": ("screen", _("Дисплей и тач: разъёмы дисплея на плате"),
                _("Разъёмы дисплея и тача, сам дисплей (проверка заведомо рабочим).")),
    "camera": ("top", _("Верх платы: разъёмы камер"),
               _("Основная и фронтальная камеры, их разъёмы, цепи питания камер.")),
    "biometry": ("top", _("Face ID / Touch ID и их разъём"),
                 _("Модуль Face ID или кнопка Touch ID и шлейф, разъём на плате, Secure Enclave в процессоре.")),
    "baseband": ("board", _("Модемная часть платы"),
                 _("Модем и его питание, антенны, SIM-лоток и eSIM.")),
    "wifi": ("board", _("Модуль Wi-Fi / Bluetooth на плате"),
             _("Модуль Wi-Fi/Bluetooth, его антенны и питание.")),
    "audio": ("bottom", _("Аудиокодек и динамики"),
              _("Аудиокодек, полифонический динамик, разговорный динамик.")),
    "usb": ("bottom", _("Разъём зарядки, контроллер зарядки и USB"),
            _("Разъём зарядки, контроллер USB (Tristar/Hydra), контроллер зарядки.")),
    "board": ("board", _("Системная плата: питание, память, процессор"),
              _("Контроллер питания (PMU), память (NAND), процессор; у «бутербродных» плат — связь половин.")),
    "software": ("none", _("Программная часть"), _("Обновите или восстановите iOS; если не помогло — проверьте питание.")),
}


def _ui_strings():
    """Подписи интерфейса на текущем языке (страница не знает переводов)."""
    return {
        "phone": _("Телефон"), "parts": _("Детали"), "logs": _("Все логи"), "history": _("История"), "kb": _("Поиск ошибок"),
        "about": _("О программе"), "theme": _("Цветовая тема"), "lang": _("Язык"),
        "wait_t": _("Подключите iPhone кабелем"), "wait_s": _("Логи снимутся сами, и программа скажет, что не так."),
        "trust_t": _("Нажмите «Доверять» на iPhone"), "trust_s": _("Разблокируйте телефон и подтвердите подключение."),
        "unlock_t": _("Разблокируйте iPhone"), "unlock_s": _("Введите код-пароль на телефоне."),
        "reading_t": _("Снимаю логи…"), "reading_s": _("Не отключайте телефон."),
        "denied_t": _("Доступ запрещён"), "denied_s": _("Переподключите кабель и нажмите «Доверять»."),
        "error_t": _("Не удалось прочитать iPhone"), "nodriver_t": _("Не найден драйвер Apple"),
        "nodriver_s": _("Установите «Apple Devices» из Microsoft Store (или iTunes) и переподключите телефон."),
        "open_file": _("Открыть файл лога…"), "open_folder": _("Открыть папку…"), "paste": _("Из буфера"),
        "again": _("Попробовать снова"), "other_phone": _("Подключить другой телефон"),
        "mark_repair": _("Отметить ремонт"), "pdf": _("PDF для клиента"), "txt": _("Отчёт .txt"),
        "show_logs": _("Посмотреть логи"), "folder": _("Папка с логами"), "erase": _("Очистить логи на телефоне…"),
        "erase_note": _("Копия уже сохранена на компьютере"),
        "found_none": _("ПРОБЛЕМ НЕ НАЙДЕНО"), "phone_ok": _("Телефон в порядке"),
        "how": _("Как ведёт себя"), "why": _("Почему"), "fix": _("Что делать"), "where": _("Где искать на плате"),
        "important": _("ВАЖНО"), "not_urgent": _("НЕ СРОЧНО"), "part_logs": _("Показать логи этой детали →"),
        "probability": _("Вероятность по деталям"), "probability_hint": _("Доля паник, которые указывают на деталь. Нажмите, чтобы увидеть почему."),
        "groups": _("Группы ошибок"), "chart": _("Паники по дням"), "other": _("Что ещё нашлось в логах"),
        "prev": _("ЭТОТ ТЕЛЕФОН УЖЕ БЫЛ"), "battery": _("Аккумулятор"), "cycles": _("Циклы"), "panics": _("Паник"),
        "network": _("Сеть / IMEI"), "search": _("Поиск"), "only_panics": _("Только паники"), "raw": _("Исходный текст лога"),
        "suggest": _("Предложить для базы"), "no_logs": _("Логов нет. Подключите телефон или откройте файл лога."),
        "phones_seen": _("Телефоны, которые подключали"), "workshop": _("Мастерская (для PDF)"), "save": _("Сохранить"),
        "note": _("Заметка"), "save_note": _("Сохранить заметку"), "visits": _("Визиты"), "repairs": _("Ремонты"),
        "open_logs": _("Открыть логи"), "delete_phone": _("Удалить из истории"), "pick_phone": _("Выберите телефон слева"),
        "kb_hint": _("Код ошибки, слово, датчик, процесс или строка из паники. Например: 4013, mic1, перезагружается, SEP, i2c3, SpringBoard"),
        "scope_base": _("Только база"), "scope_logs": _("База + открытые логи"), "scope_all": _("База + все логи в архиве"),
        "model": _("Модель"), "all_models": _("Все модели"), "nothing": _("Ничего не найдено. Попробуйте другое слово или код."),
        "parts_title": _("Детали — состояние и сбои"), "part": _("Деталь"), "data": _("Данные с телефона"),
        "fails": _("Сбои в логах"), "status": _("Статус"), "st_green": _("в порядке"), "st_orange": _("подозрение"), "st_red": _("проблема"),
        "cnt_green": _("без сбоев"), "cnt_orange": _("есть подозрения"), "cnt_red": _("есть проблемы"),
        "cancel": _("Отмена"), "ok": _("OK"), "close": _("Закрыть"), "later": _("Позже"), "update_now": _("Обновить сейчас"),
        "download": _("Скачать"), "skip": _("Не напоминать об этой версии"), "whats_new": _("ЧТО НОВОГО"),
        "check_updates": _("Проверить обновления"), "all_versions": _("Все версии"), "auto_update": _("Проверять обновления при запуске"),
        "data_dir": _("Ваши данные (история, логи, заметки) хранятся отдельно от программы и при обновлении не удаляются:"),
        "other_projects": _("ДРУГИЕ ПРОЕКТЫ"), "iact_desc": _("Активация и настройка iPhone в один клик: активация, язык, регион, Wi-Fi и пропуск экранов настройки. Windows и macOS, бесплатно."),
        "iact_dl": _("Скачать iActivator"), "project": _("О проекте"), "support": _("ПОДДЕРЖАТЬ ПРОЕКТ"),
        "support_desc": _("Программа бесплатная. Если она помогает в работе, можно поддержать автора:"),
        "copy_addr": _("Скопировать адрес"), "copied": _("Адрес скопирован"),
        "usdt_only": _("Отправляйте только USDT и только в сети TRC20 — перевод в другой сети пропадёт."),
        "repair_title": _("Отметить ремонт"), "repair_desc": _("С этого момента программа будет показывать только новые сбои — так видно, помог ли ремонт. Подключите телефон после ремонта ещё раз."),
        "repair_what": _("Что сделано"), "repair_erase": _("Стереть старые логи на телефоне (копия останется на компьютере)"),
        "mark": _("Отметить"), "erase_title": _("Очистить логи на телефоне?"),
        "erase_desc": _("На телефоне будут удалены все логи сбоев (паники, вылеты программ). Копия уже сохранена на компьютере, в папке с логами. После ремонта на телефоне появятся только новые логи — так проще проверить, что всё исправлено."),
        "erase_this": _("Очистить на этом телефоне"), "paste_title": _("Разобрать текст паники"),
        "paste_desc": _("Вставьте текст паники (из Настройки → Конфиденциальность → Аналитика или из сообщения клиента)."),
        "analyze": _("Разобрать"), "suggest_desc": _("Так база пополняется реальными случаями. Из лога убраны серийный номер, IMEI, UDID, почта и пути к файлам. Ниже — ровно то, что будет отправлено; можно поправить или дописать, какая деталь оказалась неисправной. Откроется страница GitHub — отправляете вы сами."),
        "open_github": _("Открыть на GitHub"), "copy": _("Скопировать"), "downloading": _("Загрузка версии {0}"),
        "connecting": _("Подключение…"), "installing": _("Файл проверен. Устанавливаю — программа перезапустится…"),
        "restart_q": _("Изменение вступит после перезапуска программы. Перезапустить сейчас?"), "restart": _("Перезапустить"),
        "found_in": _("В базе ошибок"), "in_logs": _("В логах"), "model_profile": _("Профиль модели"),
        "show_all": _("Показать все логи"), "only_after": _("Только после ремонта"), "zoom": _("Масштаб"),
        "board_hint": _("Схема — ориентир: точное место смотрите по схеме своей платы."),
        "erase_all": _("На всех подключённых ({0})"), "update_t": _("Доступна новая версия {0}"),
        "installed": _("Установлена версия {0}. Ваши данные при обновлении не изменятся."),
    }


def _when(s, fmt="%d.%m.%Y %H:%M"):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime(fmt)
    except (TypeError, ValueError):
        return str(s or "")[:16]


def _highlights(l):
    """Что подсветить в исходном тексте лога: найденные строки, датчики, процесс."""
    out = set(l["missing_sensors"])
    for e, hit in l["findings"]:
        if isinstance(hit, str) and 2 < len(hit) < 120:
            out.add(hit)
    for k in ("process", "exception"):
        if l.get(k) and len(l[k]) < 80:
            out.add(l[k])
    return sorted(out, key=len, reverse=True)[:30]


class Backend:
    """Состояние программы и все действия. Методы без «_» вызывает страница."""

    def __init__(self, with_device=True):
        self.history = History()
        self.logs, self.known = [], set()
        self.dev = None
        self.prev_visit = None
        self.after_repair = True
        self.phone_state = "nodriver" if not device_support() else "start"
        self.error_text = ""
        self.connected, self.udid_names = set(), {}
        self.events = queue.Queue()
        self.notices = []                  # сообщения для страницы (тосты, окна)
        self.version_seen = 0              # растёт при каждом изменении — страница перерисовывается
        self.update_info = None
        self.update_progress = None        # {"done", "total", "state": downloading|installing|failed, "error"}
        self._cancel = None
        self.archive, self.archive_busy = None, False
        self.window = None                 # окно pywebview (для диалогов)
        self.watcher = None
        if with_device and device_support():
            self.watcher = DeviceWatcher(self.events)
            self.watcher.start()

    # ------------------------------------------------------------------ служебное
    def _changed(self):
        self.version_seen += 1

    def _notice(self, kind, text, title=""):
        self.notices.append({"kind": kind, "text": text, "title": title})
        self._changed()

    def _data_dir(self):
        return os.path.dirname(core.logs_root())

    def _repair(self):
        return self.history.last_repair(phone_key(self.dev)) if self.dev else None

    def _view_logs(self):
        r = self._repair()
        if r and self.after_repair:
            return core.logs_since(self.logs, r[0])
        return self.logs

    def _load(self, paths):
        new = []
        for f in collect_files(paths):
            if f in self.known:
                continue
            self.known.add(f)
            try:
                new.append(parse_log(f))
            except Exception:
                pass
        self.logs.extend(new)
        self.logs.sort(key=lambda l: str(l["date"]), reverse=True)
        self._changed()
        return new

    def _device_lines(self):
        d = self.dev
        if not d:
            ls = [l for l in self.logs if l["product"]]
            if ls:
                return [(_("Устройство"), core.device_label(ls[0])), ("iOS", ls[0]["os"] or "—"),
                        (_("Источник"), _("файлы логов"))]
            return []
        out = [(_("Модель"), f"{d['model']} ({d['product']})"), ("iOS", f"{d['ios']} ({d['build']})"),
               (_("Серийный номер"), d.get("serial") or "—"), ("IMEI", d.get("imei") or _("не прочитан"))]
        if d.get("battery_health") is not None:
            out.append((_("Аккумулятор"), _("{0}% ({1}), {2} циклов", d['battery_health'],
                                            d.get('battery_mah', ''), d.get('battery_cycles', '?'))))
        return out

    def _dialog(self, kind, **kw):
        """Окно выбора файла/папки pywebview; в тестах — None."""
        if not self.window:
            return None
        import webview
        mode = {"open": webview.OPEN_DIALOG, "folder": webview.FOLDER_DIALOG, "save": webview.SAVE_DIALOG}[kind]
        return self.window.create_file_dialog(mode, **kw)

    # ------------------------------------------------------------------ события
    def poll(self):
        """Страница спрашивает раз в полсекунды: что изменилось."""
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            self._event(ev)
        notices, self.notices = self.notices, []
        return {"v": self.version_seen, "state": self.phone_state, "notices": notices,
                "update": self.update_progress, "update_info": self.update_info and {
                    "version": self.update_info["version"],
                    "notes": self.update_info["notes"],
                    "can_self": bool(updater.can_self_update() and self.update_info["asset"])}}

    def _event(self, ev):
        kind = ev[0]
        if kind == "state":
            if not (ev[1] == "wait" and self.phone_state == "result"):
                self.phone_state, self.error_text = ev[1], ev[2]
        elif kind == "info":
            self.dev = ev[1]
            self.phone_state = "reading"
        elif kind == "pulled":
            self.dev = ev[1]
            self.logs.clear()
            self.known.clear()
            self.after_repair = True
            self.archive = None
            self._load([self.dev["dir"]])
            self.prev_visit = self.history.add_visit(self.dev, build_verdict(self._view_logs(), self.dev),
                                                     self._view_logs())
            self._write_phone_report()
            self.connected.add(self.dev.get("udid"))
            self.udid_names[self.dev.get("udid")] = self.dev.get("model") or "iPhone"
            self.phone_state = "result"
        elif kind == "disconnected":
            self.connected.discard(ev[1])
            if self.phone_state != "result":
                self.phone_state = "wait"
        elif kind == "erased":
            ok, failed = ev[1], ev[2]
            if ok and not failed:
                self._notice("ok", _("Старые логи на телефоне стёрты ({0}). Копия осталась в папке с логами на компьютере.", len(ok)))
            elif failed:
                self._notice("error", _("Стёрто на {0} из {1}. Не удалось:\n", len(ok), len(ok) + len(failed)) +
                             "\n".join(f"• {self.udid_names.get(u, u[:8])}: {why}" for u, why in failed))
        elif kind == "archive_ready":
            self.archive, self.archive_busy = ev[1], False
        self._changed()

    def _write_phone_report(self):
        if not self.dev or not self.dev.get("dir"):
            return
        try:
            with open(os.path.join(self.dev["dir"], core.REPORT_FILE), "w", encoding="utf-8") as fh:
                fh.write(core.build_text_report(self._view_logs(), self.dev, self._device_lines()))
        except OSError:
            pass

    # ------------------------------------------------------------------ общие сведения
    def app_info(self):
        theme = self.history.setting("theme", "neon")
        key, pal = themes.resolve(theme)
        return {
            "version": updater.current_version(), "lang": i18n.LANG, "langs": i18n.LANGS,
            "theme": theme, "theme_key": key, "themes": {k: _(v) for k, v in themes.NAMES.items()},
            "palette": pal, "dark": key in themes.DARK_THEMES, "zoom": self.history.setting("zoom", 1.0), "t": _ui_strings(),
            "mod": "⌘" if IS_MAC else "Ctrl", "data_dir": self._data_dir(),
            "auto_update": self.history.setting("auto_update", True), "has_device": bool(self.watcher),
            "donate": {"address": DONATE_ADDRESS, "network": DONATE_NETWORK},
            "workshop": self.history.setting("workshop", "") or "",
            "categories": [["Все", _("Все")], ["Симптомы телефона", _("Симптомы")]] +
                          [[c, _({"Паника ядра": "Паники", "Датчики (Missing sensor)": "Датчики",
                                  "Вылет приложения": "Приложения", "Ошибка iTunes / восстановления": "Ошибки iTunes",
                                  "Логи и версии iOS": "Логи и iOS"}.get(c, c))]
                           for c in CATEGORIES if c != "Симптомы телефона"] + [[_("Шины I2C"), _("Шины I2C")]],
            "models": [[n, c] for n, c in core.model_choices()],
        }

    # ------------------------------------------------------------------ экран «Телефон»
    def phone(self):
        st = self.phone_state
        if st != "result" and not self.logs:
            texts = {"nodriver": ("nodriver_t", "nodriver_s"), "error": ("error_t", None)}
            return {"state": st, "error": self.error_text, "dev": self._dev_view()}
        logs = self._view_logs()
        d = self.dev
        panics = core.phone_panics(logs)
        problems = build_verdict(logs, d)
        repair = self._repair()
        out = {"state": "result", "dev": self._dev_view(), "has_dev": bool(d), "chips": self._chips(), "stats": self._stats(panics),
               "connected": bool(self.watcher and d and d.get("udid") in self.connected),
               "dir": (d or {}).get("dir"), "prev": None, "repair": None,
               "problems": [], "probability": [], "groups": [], "chart": None, "other": []}
        if self.prev_visit:
            v = self.prev_visit
            out["prev"] = {"date": _when(v["date"]), "text": ", ".join(v["problems"]) or _("проблем не было"),
                           "level": v.get("level", "green"),
                           "battery": _("Аккумулятор тогда: {0}%", v["battery"]) if v.get("battery") is not None else ""}
        if repair:
            when, rnote = repair
            if self.after_repair:
                text = (_("После ремонта снова {0} {1} — проблема не устранена или есть другая.", len(panics),
                          plural(len(panics), 'паника', 'паники', 'паник')), "red") if panics else \
                    (_("После ремонта паник нет ✓  Показаны только новые сбои."), "green")
            else:
                text = (_("Показаны все логи, включая те, что были до ремонта."), "muted")
            out["repair"] = {"title": _("Ремонт отмечен {0}", f"{when:%d.%m.%Y %H:%M}") + (f": {rnote}" if rnote else ""),
                             "text": text[0], "level": text[1], "after": self.after_repair}
        for p in problems:
            board = BOARD.get(p["part"])
            out["problems"].append({
                "level": p["level"], "part": p["part"], "title": p["title"], "how": p["how"], "why": p["why"],
                "fix": [f.rstrip(".") for f in p["fix"]], "note": p["note"], "count": p.get("count", 0),
                "board": board and {"zone": board[0], "title": board[1], "text": board[2]}})
        if not problems:
            msg = (_("После ремонта не было ни одной паники ядра.") if not panics else
                   _("После ремонта паники единичные и не указывают на конкретную деталь.")) if repair and self.after_repair \
                else (_("В логах нет ни одной паники ядра.") if not panics else
                      _("Паники единичные и не указывают на конкретную деталь."))
            if d and d.get("battery_health") is not None:
                msg += _(" Аккумулятор: {0}%.", d['battery_health'])
            out["ok_text"] = msg
        # вероятность по деталям: доля паник, указывающих на деталь
        if panics:
            parts = Counter(core.panic_part(p) for p in panics)
            for part, n in parts.most_common():
                if part is None:
                    continue
                causes = Counter(core.main_cause(p) for p in panics if core.panic_part(p) == part)
                out["probability"].append({
                    "part": part, "title": core.PART_NAMES[part], "pct": round(n * 100 / len(panics)),
                    "n": n, "total": len(panics),
                    "why": _("{0} из {1} {2} указывают на эту деталь. Причины в логах: {3}.", n, len(panics),
                             plural(len(panics), 'паники', 'паник', 'паник'),
                             "; ".join(f"{c} ({k})" for c, k in causes.most_common(3)))})
        # группы ошибок
        groups = Counter()
        for l in logs:
            groups[(views.log_level(l), views.log_title(l))] += 1
        out["groups"] = [{"level": lvl, "title": t, "n": n, "total": len(logs)}
                         for (lvl, t), n in sorted(groups.items(), key=lambda kv: (kv[0][0] != "red", -kv[1]))[:8]]
        if any(l["is_panic"] for l in self.logs):
            data = core.panics_by_day(self.logs, 30)
            if not any(n for _d, n in data):
                last = max((core.log_local_dt(l) for l in self.logs if l["is_panic"] and core.log_local_dt(l)),
                           default=None)
                data = core.panics_by_day(self.logs, 30, last) if last else []
            if data:
                out["chart"] = {"days": [[f"{day:%d.%m}", n] for day, n in data],
                                "repair": f"{repair[0]:%d.%m}" if repair else None,
                                "title": _("Паники по дням · {0} – {1} · всего {2}", f"{data[0][0]:%d.%m}",
                                           f"{data[-1][0]:%d.%m}", sum(n for _d, n in data))}
        crashes = [l for l in logs if not l["is_panic"] and l["exception"]]
        jetsam = [l for l in logs if "Jetsam" in l["kind"] or l["bug_type"] == "298"]
        if crashes:
            apps = Counter(l["process"] or "?" for l in crashes)
            top = ", ".join(f"{a} ({n})" for a, n in apps.most_common(4))
            out["other"].append(("orange", _("{0} {1} {2}: {3} — ошибки приложений, с железом не связано", len(crashes),
                                             plural(len(crashes), 'вылет', 'вылета', 'вылетов'),
                                             'приложения' if len(crashes) == 1 else 'приложений', top)))
        if jetsam:
            out["other"].append(("gray", _("{0} раз не хватило памяти (Jetsam) — это нормально", len(jetsam))))
        return out

    def _dev_view(self):
        d = self.dev
        if d:
            return {"model": d.get("model"), "sub": f"iOS {d.get('ios', '')} · {d.get('serial', '')}",
                    "imei": d.get("imei") or ""}
        first = next((l for l in self.logs if l["product"]), None)
        return {"model": first["model"] if first else _("Логи из файлов"),
                "sub": (first["os"] if first else "") or _("телефон не подключён"), "imei": ""}

    def _chips(self):
        d = self.dev or {}
        product = d.get("product") or next((l["product"] for l in self.logs if l["product"]), "")
        chips = []
        if product:
            chips.append(("model", f"{PRODUCTS.get(product, product)} · {product}"))
        os_ = d.get("ios") or next((l["os"] for l in self.logs if l["os"]), "")
        if os_:
            chips.append(("ios", os_ if str(os_).startswith("iOS") or "OS" in str(os_) else f"iOS {os_}"))
        f = core.model_family(product) if product else None
        if f:
            chips.append(("port", "USB-C" if f >= 15 else "Lightning"))
            chips.append(("bio", "Face ID" if f >= 10 else "Touch ID"))
        if d.get("battery_health") is not None:
            chips.append(("battery", f"{d['battery_health']}% · {d.get('battery_cycles', '?')} " + _("циклов")))
        return [{"kind": k, "text": t} for k, t in chips]

    def _stats(self, panics):
        d = self.dev or {}
        out = []
        if d.get("battery_health") is not None:
            h = d["battery_health"]
            out.append(("battery", f"{h}%", "green" if h >= 85 else ("orange" if h >= 80 else "red")))
        if d.get("battery_cycles") is not None:
            out.append(("cycles", str(d["battery_cycles"]), None))
        out.append(("panics", str(len(panics)), "green" if not panics else ("orange" if len(panics) < 3 else "red")))
        if d.get("is_iphone"):
            out.append(("network", "OK" if d.get("imei") else _("нет"), "green" if d.get("imei") else "red"))
        return [{"key": k, "value": v, "level": lvl} for k, v, lvl in out]

    # ------------------------------------------------------------------ экран «Детали»
    def parts(self):
        rows = parts_table(self._view_logs(), self.dev)
        title = (self.dev or {}).get("model") or next((l["model"] for l in self.logs if l["model"]), _("телефона"))
        return {"title": _("Детали {0} — состояние и сбои", title),
                "rows": [{"name": n, "data": d, "fails": f, "level": lvl, "part": None} for n, d, f, lvl in rows],
                "counts": {k: sum(r[3] == k for r in rows) for k in ("green", "orange", "red")},
                "original": _("Посмотреть, какие детали заменены, можно на самом iPhone: Настройки → Основные → Об этом устройстве → «История деталей и обслуживания» (iOS 15.2+, iPhone XS и новее). Там будет «Оригинальная деталь Apple» или «Неизвестная деталь». Автоматическая проверка в программе появится после тестов на реальных телефонах."),
                "original_t": _("Оригинальность деталей")}

    # ------------------------------------------------------------------ экран «Все логи»
    def logs_list(self, q="", only_panic=False, part=None):
        q = (q or "").strip().lower()
        out = []
        for i, l in enumerate(self.logs):
            if only_panic and not l["is_panic"]:
                continue
            if part and core.panic_part(l) != part:
                continue
            title = views.log_title(l)
            if q and q not in (title + l["panic"] + l["process"] + os.path.basename(l["file"])).lower():
                continue
            out.append({"id": i, "title": title, "date": str(l["date"])[:16], "kind": core.tkind(l["kind"]),
                        "level": views.log_level(l)})
        return {"items": out, "part_title": core.PART_NAMES.get(part) if part else None}

    def log_detail(self, i):
        l = self.logs[int(i)]
        raw = l.get("raw") or ""
        if not raw:
            try:
                raw = core._read_text(l["file"]) if os.path.isfile(l["file"]) else l.get("panic", "")
            except Exception:
                raw = l.get("panic", "")
        return {"parts": views.log_parts(l), "raw": raw[:200000], "highlights": _highlights(l),
                "suggest": core.report_for_database(l)}

    # ------------------------------------------------------------------ экран «История»
    def history_list(self, q=""):
        q = (q or "").strip().lower()
        rows = []
        items = sorted(self.history.phones.items(),
                       key=lambda kv: (kv[1]["visits"][-1]["date"] if kv[1]["visits"] else ""), reverse=True)
        for key, p in items:
            v = p["visits"][-1] if p["visits"] else {}
            result = ", ".join(v.get("problems", [])) or _("в порядке")
            hay = " ".join([p.get("model", ""), p.get("serial", key), p.get("imei", ""), p.get("note", ""), result]).lower()
            if q and q not in hay:
                continue
            rows.append({"key": key, "model": p.get("model", "?"), "serial": p.get("serial", key),
                         "date": _when(v.get("date", "")), "result": result, "level": v.get("level", "green")})
        return rows

    def phone_history(self, key):
        p = self.history.get(key)
        if not p:
            return None
        return {"key": key, "model": p.get("model", "?"),
                "sub": _("Серийный {0}", p.get('serial', key)) + (f" · IMEI {p['imei']}" if p.get("imei") else ""),
                "note": p.get("note", ""),
                "repairs": [{"date": _when(r["date"]), "note": r.get("note") or _("без описания")}
                            for r in reversed(p.get("repairs", []))],
                "visits": [{"date": _when(v["date"]) + f" · iOS {v.get('ios', '?')}", "level": v.get("level", "green"),
                            "text": (", ".join(v.get("problems", [])) or _("проблем не найдено")) + " · " +
                            ", ".join(([_("аккумулятор {0}%", v['battery'])] if v.get("battery") is not None else []) +
                                      [_("паник {0}", v.get('panics', 0))])}
                           for v in reversed(p.get("visits", []))],
                "has_logs": bool(views.phone_folder(p.get("serial", key)))}

    def set_note(self, key, note):
        self.history.set_note(key, note)
        return True

    def delete_phone(self, key):
        self.history.delete(key)
        self._changed()
        return True

    def set_workshop(self, name):
        self.history.set_setting("workshop", name or "")
        return True

    def open_history_logs(self, key):
        p = self.history.get(key) or {}
        folder = views.phone_folder(p.get("serial", key))
        if not folder:
            return False
        self.dev, self.prev_visit = None, None
        self.logs.clear()
        self.known.clear()
        self._load([folder])
        self.phone_state = "result"
        return True

    def history_report(self, key):
        p = self.history.get(key) or {}
        folder = views.phone_folder(p.get("serial", key))
        if not folder:
            return None
        logs = []
        for f in collect_files([folder]):
            try:
                logs.append(parse_log(f))
            except Exception:
                pass
        logs.sort(key=lambda l: str(l["date"]), reverse=True)
        last = (p.get("visits") or [{}])[-1]
        lines = [(_("Модель"), p.get("model", "?")), ("iOS", last.get("ios") or "—"),
                 (_("Серийный номер"), p.get("serial") or "—"), ("IMEI", p.get("imei") or "—")]
        if last.get("battery") is not None:
            lines.append((_("Аккумулятор"), f"{last['battery']}%"))
        if p.get("note"):
            lines.append((_("Заметка"), p["note"]))
        return self._save_text(core.build_text_report(logs, None, lines),
                               _("Отчёт {0} {1}.txt", p.get("model", _("телефон")), f"{datetime.now():%Y-%m-%d}"))

    # ------------------------------------------------------------------ экран «Поиск ошибок»
    def kb(self, q="", cat="Все", scope="base_logs", model=""):
        product = dict(core.model_choices()).get(model) if model else None
        rows = views.kb_rows((q or "").strip(), cat, product)
        groups = []
        if product:
            groups.append({"title": _("Профиль модели: {0}", model), "items": [
                {"id": f"model:{product}", "title": _("Профиль модели: {0}", model), "where": "", "level": "blue"}]})
        groups.append({"title": _("В базе ошибок ({0})", len(rows)),
                       "items": [{"id": f"{typ}:{key}", "title": title, "where": _(c), "level": ""}
                                 for typ, key, title, c in rows[:800]]})
        q = (q or "").strip()
        if q and scope != "base":
            pool = self.logs
            if scope == "all":
                arch = self._archive()
                if arch is None:
                    groups.append({"title": _("В логах: читаю архив…"), "items": [], "busy": True})
                    return groups
                known = {l["file"] for l in pool}
                pool = pool + [l for l in arch if l["file"] not in known]
            found = sorted(core.search_logs(pool, q), key=lambda l: str(l["date"]), reverse=True)[:500]
            self._kb_logs = found
            groups.append({"title": _("В логах ({0})", len(found)), "items": [
                {"id": f"klog:{n}", "title": f"{str(l['date'])[:16]}  {views.log_title(l)}",
                 "where": os.path.basename(os.path.dirname(l["file"])) if scope == "all" else (l["model"] or ""),
                 "level": views.log_level(l)} for n, l in enumerate(found)]})
        return groups

    def _archive(self):
        if self.archive is not None:
            return self.archive
        if not self.archive_busy:
            self.archive_busy = True

            def work():
                logs = []
                for f in collect_files([core.logs_root()]):
                    try:
                        logs.append(parse_log(f))
                    except Exception:
                        pass
                self.events.put(("archive_ready", logs))
            threading.Thread(target=work, daemon=True).start()
        return None

    def kb_item(self, item_id):
        typ, key = item_id.split(":", 1)
        if typ == "sensor":
            return {"parts": views.sensor_parts(key)}
        if typ == "i2c":
            return {"parts": views.i2c_parts(int(key))}
        if typ == "model":
            return {"parts": views.model_parts(key)}
        if typ == "klog":
            l = self._kb_logs[int(key)]
            return {"parts": views.log_parts(l)}
        return {"parts": views.entry_parts(KB[int(key)], self.logs)}

    # ------------------------------------------------------------------ действия
    def open_files(self):
        fs = self._dialog("open", allow_multiple=True,
                          file_types=(_("Логи iOS") + " (*.ips;*.panic;*.log;*.txt;*.synced;*.crash)",
                                      _("Все файлы") + " (*.*)"))
        if not fs:
            return False
        return self._open(list(fs))

    def open_folder(self):
        d = self._dialog("folder", directory=core.logs_root())
        if not d:
            return False
        return self._open([d[0] if isinstance(d, (list, tuple)) else d])

    def load_paths(self, paths):
        """Открыть файлы/папки по путям (перетаскивание, тесты)."""
        return self._open(paths)

    def _open(self, paths):
        new = self._load(paths)
        if not new:
            self._notice("info", _("Новых логов не найдено."))
            return False
        self.phone_state = "result"
        return True

    def paste(self, text):
        if not (text or "").strip():
            return False
        info = parse_pasted(text)
        self.logs.insert(0, info)
        self.phone_state = "result"
        self._changed()
        return True

    def again(self):
        if self.watcher:
            self.watcher.manual.put("*")
        self.phone_state, self.dev, self.prev_visit = "wait", None, None
        self._changed()
        return True

    def toggle_after_repair(self):
        self.after_repair = not self.after_repair
        self._changed()
        return self.after_repair

    def mark_repair(self, note, erase=False):
        if not self.dev:
            return False
        self.history.add_repair(self.dev, (note or "").strip())
        if erase and self.watcher:
            self.watcher.erase.put(self.dev["udid"])
        self.after_repair = True
        self._changed()
        return True

    def erase_phone(self, all_connected=False):
        if not self.watcher or not self.dev:
            return False
        for u in (sorted(self.connected) if all_connected else [self.dev["udid"]]):
            self.watcher.erase.put(u)
        self._notice("info", _("Очищаю логи на телефоне…"))
        return True

    def connected_count(self):
        return len(self.connected)

    def open_path(self, path):
        try:
            if IS_WIN:
                os.startfile(path)
            elif IS_MAC:
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            return False
        return True

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)
        return True

    def open_dir(self):
        return self.open_path((self.dev or {}).get("dir") or core.logs_root())

    def suggest_send(self, i, text):
        l = self.logs[int(i)]
        title = f"[log] {l['model'] or l['product'] or 'iPhone'}: " + (core.panic_part(l) or l["kind"])
        return self.open_url(ISSUES_URL + urllib.parse.urlencode({"title": title, "body": (text or "")[:6000]}))

    def _save_text(self, text, name):
        f = self._dialog("save", save_filename=name, file_types=(_("Текст") + " (*.txt)",))
        if not f:
            return None
        f = f[0] if isinstance(f, (list, tuple)) else f
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(text)
        self._notice("ok", _("Отчёт сохранён: ") + f)
        return f

    def save_txt(self):
        name = (self.dev or {}).get("model", _("телефон"))
        return self._save_text(core.build_text_report(self._view_logs(), self.dev, self._device_lines()),
                               _("Отчёт {0} {1}.txt", name, f"{datetime.now():%Y-%m-%d}"))

    def save_pdf(self):
        if not report_pdf.available():
            self._notice("info", _("PDF недоступен (нет модуля reportlab или шрифта). Сохраню текстовый отчёт."))
            return self.save_txt()
        name = (self.dev or {}).get("model", _("телефон"))
        f = self._dialog("save", save_filename=_("Диагностика {0} {1}.pdf", name, f"{datetime.now():%Y-%m-%d}"),
                         file_types=("PDF (*.pdf)",))
        if not f:
            return None
        f = f[0] if isinstance(f, (list, tuple)) else f
        note = (self.history.get(phone_key(self.dev)) or {}).get("note", "") if self.dev else ""
        rep = self._repair() if self.after_repair else None
        try:
            report_pdf.build_pdf(f, self._view_logs(), self.dev, self._device_lines(),
                                 self.history.setting("workshop", "") or "", rep, note)
        except Exception as e:
            self._notice("error", _("Не удалось сохранить PDF:\n{0}", e))
            return None
        self._notice("ok", _("PDF сохранён: ") + f)
        self.open_path(f)
        return f

    # ------------------------------------------------------------------ настройки
    def set_setting(self, key, value):
        if key in ("theme", "lang", "zoom", "auto_update", "skip_version"):
            self.history.set_setting(key, value)
            if key == "lang":
                i18n.set_lang(value)
            return True
        return False

    def restart(self):
        cmd = [sys.executable] if getattr(sys, "frozen", False) else \
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ios_panic_reader.py")]
        try:
            if IS_MAC and getattr(sys, "frozen", False):
                subprocess.Popen(["/bin/sh", "-c", f'sleep 1; open "{updater.install_target()}"'], start_new_session=True)
            elif IS_WIN:
                subprocess.Popen(cmd, creationflags=0x00000200)
            else:
                subprocess.Popen(cmd, start_new_session=True)
        except Exception:
            return False
        self._close()
        return True

    def _close(self):
        self.history.save()
        if self.window:
            threading.Timer(0.3, self.window.destroy).start()

    # ------------------------------------------------------------------ обновление (как в 3uTools)
    def check_updates(self, manual=True):
        def work():
            try:
                info = updater.check_latest()
                skip = self.history.setting("skip_version", "")
                self.history.set_setting("update_checked", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                if updater.is_newer(info["version"], updater.current_version()) and (manual or info["version"] != skip):
                    self.update_info = info
                    if os.environ.get("IOSPR_TEST_AUTOUPDATE") == "1":    # сквозной тест: «нажать» «Обновить»
                        self.start_update()
                elif manual:
                    self._notice("info", _("У вас последняя версия ({0}).", updater.current_version()))
            except Exception as e:
                if manual:
                    self._notice("error", _("Не удалось проверить обновления.\nПроверьте интернет.\n\n") +
                                 f"{e.__class__.__name__}: {e}")
            self._changed()
        threading.Thread(target=work, daemon=True).start()
        return True

    def dismiss_update(self, skip=False):
        if skip and self.update_info:
            self.history.set_setting("skip_version", self.update_info["version"])
        self.update_info = None
        self._changed()
        return True

    def start_update(self):
        if self.phone_state == "reading":
            self._notice("info", _("Сейчас снимаются логи с телефона. Обновите после того, как программа закончит."))
            return False
        reason = updater.check_writable()
        if reason:
            self._notice("error", reason)
            return False
        info = self.update_info
        path = updater.downloaded_path(self._data_dir(), info["version"])
        self._cancel = threading.Event()
        self.update_progress = {"done": 0, "total": info["asset"].get("size") or 0, "state": "downloading",
                                "version": info["version"]}

        def progress(done, total):
            self.update_progress.update(done=done, total=total)

        def work():
            try:
                updater.download(info["asset"], path, progress, cancel=self._cancel)
                if self._cancel.is_set():
                    return
                self.update_progress["state"] = "installing"
                new = updater.prepare(path, self._data_dir())
                self.history.save()
                updater.launch_installer(new, self._data_dir(), updater.current_version(), relaunch=True)
                threading.Timer(0.8, self._close).start()
            except updater.Cancelled:
                self.update_progress = None
            except Exception as e:
                if not self._cancel.is_set():
                    self.update_progress = {"state": "failed", "error": f"{e.__class__.__name__}: {e}"}
            self._changed()
        threading.Thread(target=work, daemon=True).start()
        return True

    def cancel_update(self):
        if self._cancel:
            self._cancel.set()
        self.update_progress = None
        self._changed()
        return True

    # ------------------------------------------------------------------ для страницы: проверка шрифтов и окон
    def ping(self):
        return "pong"


def webview_available():
    """Есть ли движок для веб-окна. На Windows нужен WebView2 (Edge); на Mac — встроенный WebKit."""
    if os.environ.get("IOSPR_UI") == "classic":
        return False
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    if IS_WIN:
        try:
            import winreg
            guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
            for root, path in ((winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
                               (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
                               (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}")):
                try:
                    with winreg.OpenKey(root, path) as k:
                        v = winreg.QueryValueEx(k, "pv")[0]
                        if v and v != "0.0.0.0":
                            return True
                except OSError:
                    continue
        except Exception:
            pass
        return False
    return IS_MAC


def _window_rect():
    """Размер и место окна: как в прошлый раз, если помещается, иначе по рабочей области экрана."""
    import screen
    h = History()
    saved = h.setting("window_web", {}) or {}
    area = None
    try:
        if IS_WIN:
            area = screen._win_area((saved.get("x", 0) + 50, saved.get("y", 0) + 10)) if saved else None
            area = area or screen._win_area()
        elif IS_MAC:
            area = screen._mac_area()
    except Exception:
        area = None
    area = area or (0, 0, 1440, 900)
    deco = (16, 40) if IS_WIN else (0, 28)
    rect = (saved["w"], saved["h"], saved["x"], saved["y"]) if {"w", "h", "x", "y"} <= set(saved) else None
    return screen.fit_main(area, 1280, 840, deco, rect, min(900, area[2]), min(600, area[3]))


def _test_hooks(ui, close):
    """Только для автотестов: какой интерфейс запустился, и закрыть окно через N секунд."""
    report = os.environ.get("IOSPR_UI_REPORT")
    if report:
        try:
            with open(report, "w", encoding="utf-8") as f:
                f.write(ui)
        except OSError:
            pass
    secs = os.environ.get("IOSPR_TEST_EXIT_AFTER")
    if secs:
        threading.Timer(float(secs), close).start()


def run(initial_paths=()):
    import webview
    backend = Backend()
    if initial_paths:
        backend.load_paths(list(initial_paths))
    w, h, x, y = _window_rect()
    win = webview.create_window(APP_TITLE, url=os.path.join(WEB_DIR, "index.html"), js_api=backend,
                                width=w, height=h, x=x, y=y, min_size=(min(900, w), min(600, h)),
                                background_color="#0b1020", text_select=True)
    backend.window = win

    def remember():
        try:
            backend.history.set_setting("window_web", {"w": win.width, "h": win.height, "x": win.x, "y": win.y})
        except Exception:
            pass
    win.events.closing += remember
    _test_hooks("web", lambda: win.destroy())
    if backend.history.setting("auto_update", True):
        threading.Timer(3.0, lambda: backend.check_updates(manual=False)).start()
    webview.start(gui="edgechromium" if IS_WIN else None, debug=bool(os.environ.get("IOSPR_WEBDEBUG")))
