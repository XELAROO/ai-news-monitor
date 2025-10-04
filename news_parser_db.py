#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_parser_db.py
Парсер новостных сайтов по конфигу sites.json.
Особенности:
 - Парсер использует items_xpath как ЯКОРЬ (anchor).
 - title_xpath и date_xpath должны содержать {news_index} (подставляется 1,2,3...).
 - НЕТ fallback: если anchor не найден — сайт пропускается.
 - Поддержка режимов: static (requests + lxml) и selenium.
 - Создаёт news.db и лог news_parser.log в корне.
 - Отправляет Telegram-уведомление на TELEGRAM_USER_ID (использует TELEGRAM_BOT_TOKEN).
"""

import os
import json
import time
import logging
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from lxml import html

# Selenium optional
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False

# ----------------- Настройки -----------------
BASE_DIR = os.getcwd()
SITES_FILE = os.path.join(BASE_DIR, "sites.json")
DB_FILE = os.path.join(BASE_DIR, "news.db")
LOG_FILE = os.path.join(BASE_DIR, "news_parser.log")

DEFAULT_MAX_ITEMS = 100
DEFAULT_CONSECUTIVE_MISS_BREAK = 3
SELENIUM_WAIT_DEFAULT = 10  # seconds для загрузки страницы

# ----------------- Логирование -----------------
logger = logging.getLogger("news_parser")
logger.setLevel(logging.DEBUG)
# Файловый хэндлер
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(fmt)
logger.addHandler(fh)
# Консоль
sh = logging.StreamHandler()
sh.setFormatter(fmt)
logger.addHandler(sh)

# ----------------- Работа с БД -----------------
class NewsDB:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT,
                title TEXT,
                link TEXT,
                pub_date TEXT,
                parsed_date TEXT,
                fingerprint TEXT UNIQUE,
                status TEXT DEFAULT 'new'
            )
            """
        )
        self.conn.commit()

    def fingerprint(self, title: str, link: str) -> str:
        h = hashlib.sha1()
        h.update((title + "|" + (link or "")).encode("utf-8"))
        return h.hexdigest()

    def add_article(self, site: str, title: str, link: str, pub_date: str) -> bool:
        fp = self.fingerprint(title, link)
        parsed_date = datetime.utcnow().isoformat()
        try:
            self.conn.execute(
                "INSERT INTO news (site, title, link, pub_date, parsed_date, fingerprint, status) VALUES (?, ?, ?, ?, ?, ?, 'new')",
                (site, title, link, pub_date, parsed_date, fp),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

# ----------------- Утилиты -----------------
def safe_int(v, default):
    try:
        return int(v)
    except Exception:
        return default

def normalize_date(raw: str, site: str = None) -> str:
    """Простейшая нормализация дат — расширяем при необходимости."""
    if not raw:
        return None
    s = raw.strip()
    # Попытка ISO
    try:
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        pass
    # Пример: 'October 1, 2025'
    try:
        dt = datetime.strptime(s, "%B %d, %Y")
        return dt.isoformat()
    except Exception:
        pass
    # Простая обработка '5 hours ago', '2 minutes ago'
    try:
        low = s.lower()
        if "hour" in low:
            num = int(''.join([c for c in low.split()[0] if c.isdigit()]) or 0)
            return (datetime.utcnow() - timedelta(hours=num)).isoformat()
        if "minute" in low:
            num = int(''.join([c for c in low.split()[0] if c.isdigit()] ) or 0)
            return (datetime.utcnow() - timedelta(minutes=num)).isoformat()
        if "today" in low:
            return datetime.utcnow().date().isoformat()
    except Exception:
        pass
    # fallback — возвращаем оригинал (строку)
    return s

def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Отправляет сообщение в Telegram. Возвращает True если ok."""
    if not bot_token or not chat_id:
        logger.warning("Telegram: credentials missing -> skip send")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            logger.info("Telegram: message sent")
            return True
        else:
            logger.warning(f"Telegram: send failed status={r.status_code} resp={r.text}")
            return False
    except Exception as e:
        logger.exception(f"Telegram send exception: {e}")
        return False

def anchor_xpath_for_selenium(xpath: str) -> str:
    """Если xpath кончается '/text()', Selenium не сможет найти текст-нод — убираем текстовую часть."""
    if not xpath:
        return xpath
    s = xpath.strip()
    if s.endswith("/text()"):
        return s[: s.rfind("/text()")]
    return s

# ----------------- Основная логика парсера -----------------
class NewsParser:
    def __init__(self, sites_file=SITES_FILE):
        self.sites_file = sites_file
        self.db = NewsDB()
        self.sites = self.load_sites()
        # Telegram из окружения
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_user = os.getenv("TELEGRAM_USER_ID", "").strip()  # сюда отправляем статус парсинга
        # counters
        self.counters = {
            "found_total": 0,
            "added_total": 0,
            "duplicates": 0,
            "per_site": {}
        }
        self.errors = []

    def load_sites(self):
        if not os.path.exists(self.sites_file):
            logger.error(f"Sites config not found: {self.sites_file}")
            return {}
        try:
            with open(self.sites_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.exception(f"Error loading sites.json: {e}")
            return {}

    def setup_selenium_driver(self):
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available (module import failed)")
            return None
        try:
            options = Options()
            # modern headless flag
            try:
                options.add_argument("--headless=new")
            except Exception:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            logger.exception(f"Selenium driver setup failed: {e}")
            return None

    def parse_site_static(self, site_name: str, cfg: dict):
        """Парсинг через requests + lxml. Строго anchor + indexed xpaths."""
        logger.info(f"[{site_name}] static parse: {cfg.get('url')}")
        url = cfg.get("url")
        title_t = cfg.get("title_xpath", "")
        date_t = cfg.get("date_xpath", "")
        items_xpath = cfg.get("items_xpath", "")
        max_items = safe_int(cfg.get("max_items"), DEFAULT_MAX_ITEMS)
        miss_break = safe_int(cfg.get("consecutive_miss_break"), DEFAULT_CONSECUTIVE_MISS_BREAK)

        # валидация: require items_xpath и title_xpath с {news_index}
        if not items_xpath:
            msg = f"[{site_name}] CONFIG ERROR: items_xpath is missing"
            logger.error(msg)
            self.errors.append(msg)
            return

        if "{news_index}" not in title_t:
            msg = f"[{site_name}] CONFIG ERROR: title_xpath must contain '{{news_index}}'"
            logger.error(msg)
            self.errors.append(msg)
            return

        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            resp.raise_for_status()
            tree = html.fromstring(resp.content)
        except Exception as e:
            msg = f"[{site_name}] HTTP/REQUEST error: {e}"
            logger.exception(msg)
            self.errors.append(msg)
            return

        anchors = tree.xpath(items_xpath)
        if not anchors:
            msg = f"[{site_name}] Anchor (items_xpath) NOT FOUND on page (static)."
            logger.error(msg)
            self.errors.append(msg)
            return

        # начинаем нумеровать новости от 1
        consecutive_miss = 0
        idx = 1
        while idx <= max_items:
            t_xpath = title_t.format(news_index=idx)
            d_xpath = date_t.format(news_index=idx) if date_t else None
            try:
                t_nodes = tree.xpath(t_xpath)
            except Exception as e:
                logger.warning(f"[{site_name}] invalid title xpath at index {idx}: {e}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    break
                idx += 1
                continue

            if not t_nodes:
                logger.debug(f"[{site_name}] title not found index={idx}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    logger.info(f"[{site_name}] reached consecutive miss break ({miss_break}), stop")
                    break
                idx += 1
                continue

            # нашли заголовок
            consecutive_miss = 0
            tnode = t_nodes[0]
            # извлекаем текст заголовка
            try:
                title = tnode.text_content().strip()
            except Exception:
                title = str(tnode).strip()

            # извлекаем ссылку
            link = None
            try:
                if getattr(tnode, "tag", None) == "a" and tnode.get("href"):
                    link = tnode.get("href")
                else:
                    a = tnode.xpath(".//a")
                    if a and getattr(a[0], "get", None):
                        link = a[0].get("href")
                    else:
                        # поднимаемся к родителю <a>, если такой есть
                        parent = tnode.getparent()
                        while parent is not None:
                            if parent.tag == "a" and parent.get("href"):
                                link = parent.get("href")
                                break
                            parent = parent.getparent()
            except Exception:
                link = None

            if link:
                link = urljoin(url, link)

            # дата
            raw_date = ""
            if d_xpath:
                try:
                    d_nodes = tree.xpath(d_xpath)
                    if d_nodes:
                        # d_nodes может вернуть элемент или текст
                        if hasattr(d_nodes[0], "text_content"):
                            raw_date = d_nodes[0].text_content().strip()
                        else:
                            raw_date = str(d_nodes[0]).strip()
                except Exception:
                    raw_date = ""

            pub_date = normalize_date(raw_date, site_name)

            # добавление в БД
            if title and link:
                added = self.db.add_article(site_name, title, link, pub_date)
                self.counters["found_total"] += 1
                if added:
                    self.counters["added_total"] += 1
                    self.counters["per_site"][site_name] = self.counters["per_site"].get(site_name, 0) + 1
                else:
                    self.counters["duplicates"] += 1
            else:
                logger.debug(f"[{site_name}] skip entry idx={idx} (title/link missing)")

            idx += 1

    def parse_site_selenium(self, site_name: str, cfg: dict):
        """Парсинг через Selenium (динамические сайты)."""
        logger.info(f"[{site_name}] selenium parse: {cfg.get('url')}")
        url = cfg.get("url")
        title_t = cfg.get("title_xpath", "")
        date_t = cfg.get("date_xpath", "")
        items_xpath = cfg.get("items_xpath", "")
        max_items = safe_int(cfg.get("max_items"), DEFAULT_MAX_ITEMS)
        miss_break = safe_int(cfg.get("consecutive_miss_break"), DEFAULT_CONSECUTIVE_MISS_BREAK)
        wait = safe_int(cfg.get("wait"), SELENIUM_WAIT_DEFAULT)

        if not items_xpath:
            msg = f"[{site_name}] CONFIG ERROR: items_xpath is missing"
            logger.error(msg)
            self.errors.append(msg)
            return

        if "{news_index}" not in title_t:
            msg = f"[{site_name}] CONFIG ERROR: title_xpath must contain '{{news_index}}'"
            logger.error(msg)
            self.errors.append(msg)
            return

        driver = self.setup_selenium_driver()
        if not driver:
            msg = f"[{site_name}] Selenium driver init failed"
            logger.error(msg)
            self.errors.append(msg)
            return

        try:
            driver.get(url)
            time.sleep(wait)
        except Exception as e:
            msg = f"[{site_name}] Selenium navigation error: {e}"
            logger.exception(msg)
            self.errors.append(msg)
            try:
                driver.quit()
            except Exception:
                pass
            return

        # корректируем items_xpath для selenium, если он заканчивался на /text()
        anchor_xpath = anchor_xpath_for_selenium(items_xpath)
        anchors = []
        try:
            anchors = driver.find_elements(By.XPATH, anchor_xpath)
        except Exception as e:
            logger.warning(f"[{site_name}] anchor xpath search failed in selenium: {e}")
            anchors = []

        if not anchors:
            msg = f"[{site_name}] Anchor (items_xpath) NOT FOUND on page (selenium)."
            logger.error(msg)
            self.errors.append(msg)
            try:
                driver.quit()
            except Exception:
                pass
            return

        # перебираем индексы
        idx = 1
        consecutive_miss = 0
        while idx <= max_items:
            t_xpath = title_t.format(news_index=idx)
            d_xpath = date_t.format(news_index=idx) if date_t else None
            try:
                title_elems = driver.find_elements(By.XPATH, t_xpath)
            except Exception as e:
                logger.warning(f"[{site_name}] invalid title xpath at index {idx} in selenium: {e}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    break
                idx += 1
                continue

            if not title_elems:
                logger.debug(f"[{site_name}] selenium: title not found index={idx}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    logger.info(f"[{site_name}] reached consecutive miss break ({miss_break}) in selenium, stop")
                    break
                idx += 1
                continue

            consecutive_miss = 0
            te = title_elems[0]
            try:
                title = te.text.strip()
            except Exception:
                title = ""

            link = None
            try:
                if te.tag_name.lower() == "a":
                    link = te.get_attribute("href")
                else:
                    a = te.find_elements(By.XPATH, ".//a")
                    if a:
                        link = a[0].get_attribute("href")
                    else:
                        # пробуем подняться по DOM к родителю <a>
                        parent = te
                        for i in range(5):
                            try:
                                parent = parent.find_element(By.XPATH, "..")
                            except Exception:
                                parent = None
                            if parent is None:
                                break
                            try:
                                if parent.tag_name.lower() == "a":
                                    link = parent.get_attribute("href")
                                    break
                            except Exception:
                                pass
            except Exception:
                link = None

            if link:
                link = urljoin(url, link)

            raw_date = ""
            if d_xpath:
                try:
                    date_elems = driver.find_elements(By.XPATH, d_xpath)
                    if date_elems:
                        raw_date = date_elems[0].text.strip()
                except Exception:
                    raw_date = ""

            pub_date = normalize_date(raw_date, site_name)

            if title and link:
                added = self.db.add_article(site_name, title, link, pub_date)
                self.counters["found_total"] += 1
                if added:
                    self.counters["added_total"] += 1
                    self.counters["per_site"][site_name] = self.counters["per_site"].get(site_name, 0) + 1
                else:
                    self.counters["duplicates"] += 1
            else:
                logger.debug(f"[{site_name}] selenium skip entry idx={idx}: title/link missing")

            idx += 1

        try:
            driver.quit()
        except Exception:
            pass

    def run(self):
        """Главная точка: перебираем сайты из конфигa и парсим."""
        start_ts = time.time()
        if not self.sites:
            logger.error("No sites to parse (sites.json empty or missing)")
            return self._finalize_and_report(start_ts)

        for site_name, cfg in self.sites.items():
            cfg = dict(cfg)  # копия
            # задаём значения по умолчанию
            if "max_items" not in cfg:
                cfg["max_items"] = DEFAULT_MAX_ITEMS
            if "consecutive_miss_break" not in cfg:
                cfg["consecutive_miss_break"] = DEFAULT_CONSECUTIVE_MISS_BREAK

            mode = cfg.get("mode", "selenium")
            try:
                if mode == "static":
                    self.parse_site_static(site_name, cfg)
                elif mode == "selenium":
                    self.parse_site_selenium(site_name, cfg)
                else:
                    msg = f"[{site_name}] Unknown parsing mode: {mode}"
                    logger.error(msg)
                    self.errors.append(msg)
            except Exception as e:
                msg = f"[{site_name}] top-level parse exception: {e}"
                logger.exception(msg)
                self.errors.append(msg)

        elapsed = int(time.time() - start_ts)
        return self._finalize_and_report(start_ts)

    def _finalize_and_report(self, start_ts):
        elapsed = int(time.time() - start_ts)
        found = self.counters.get("found_total", 0)
        added = self.counters.get("added_total", 0)
        dups = self.counters.get("duplicates", 0)
        per_site = self.counters.get("per_site", {})

        # Сформируем сообщение для Telegram (первое, что видно — количество новых)
        lines = []
        lines.append(f"🚀 {added} новостей — <b>Парсинг завершён</b>")
        lines.append(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
        lines.append(f"Время работы скрипта: {elapsed} сек.")
        lines.append(f"Новые новости: {added}")
        if per_site:
            for s, c in per_site.items():
                lines.append(f"- {s}: {c}")
        lines.append(f"ВСЕГО: {found} (дубликатов: {dups})")
        if self.errors:
            lines.append("")
            lines.append("<b>Ошибки парсинга:</b>")
            for e in self.errors:
                lines.append(f"- {e}")
        # Информация о Telegram-отправке
        telegram_sent = False
        if self.telegram_token and self.telegram_user:
            text = "\n".join(lines)
            telegram_sent = send_telegram(self.telegram_token, self.telegram_user, text)
        else:
            logger.warning("TELEGRAM_BOT_TOKEN или TELEGRAM_USER_ID не заданы. Пропускаем отправку Telegram.")
            self.errors.append("Telegram credentials missing or empty.")
        # Лог финального результата
        logger.info(f"Found total: {found}, Added new: {added}, Duplicates: {dups}, Per site: {per_site}, Errors: {len(self.errors)}, Telegram sent: {telegram_sent}, Elapsed: {elapsed}s")

        # Вернём структуру результатов (можно использовать в workflow)
        result = {
            "found_total": found,
            "added_total": added,
            "duplicates": dups,
            "per_site": per_site,
            "errors": len(self.errors),
            "telegram_sent": bool(telegram_sent),
            "elapsed": elapsed
        }
        return result

# ----------------- CLI -----------------
if __name__ == "__main__":
    parser = NewsParser()
    res = parser.run()
    # Логируем JSON-результат (чтобы Actions мог легче прочитать)
    try:
        import json as _json
        with open(os.path.join(BASE_DIR, "parser_run_result.json"), "w", encoding="utf-8") as fh:
            fh.write(_json.dumps(res, ensure_ascii=False, indent=2))
    except Exception:
        pass
    # Закрываем БД
    try:
        parser.db.close()
    except Exception:
        pass
    # exit
    logger.info("Parser finished.")

