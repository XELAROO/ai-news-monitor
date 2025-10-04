#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_parser_db.py — расширенная, полная версия парсера
- Парсит сайты по конфигу sites.json (каждый сайт задаётся: url, mode, items_xpath, title_xpath, date_xpath, ...)
- items_xpath выступает исключительно как ЯКОРЬ (anchor). Если anchor не найден — сайт пропускается.
- title_xpath и date_xpath должны содержать {news_index} — парсер подставляет 1,2,3...
- Поддерживает режимы:
    - static: requests + lxml
    - selenium: webdriver (поддержка динамики, прокрутки, WebDriverWait)
- Сохраняет новости в SQLite news.db (с уникальным fingerprint). Не удаляет/не перезаписывает существующие записи.
- Логирование в news_parser.log и вывод результата в parser_run_result.json
- Отправляет итоговое сообщение в Telegram (TELEGRAM_BOT_TOKEN и TELEGRAM_USER_ID в env).
"""

from __future__ import annotations
import os
import sys
import json
import time
import logging
import sqlite3
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urljoin
from typing import Optional, Dict

import requests
from lxml import html

# Selenium optional imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False

# ----------------- Настройки -----------------
BASE_DIR = os.getcwd()
SITES_FILE = os.path.join(BASE_DIR, "sites.json")
DB_FILE = os.path.join(BASE_DIR, "news.db")
LOG_FILE = os.path.join(BASE_DIR, "news_parser.log")
RESULT_JSON = os.path.join(BASE_DIR, "parser_run_result.json")

# defaults
DEFAULT_MAX_ITEMS = 200
DEFAULT_CONSECUTIVE_MISS_BREAK = 3
SELENIUM_WAIT_DEFAULT = 10  # seconds - базовое ожидание загрузки страницы
SELENIUM_SCROLL_INTERVAL = 1.2  # пауза между прокрутками
SELENIUM_MAX_SCROLLS = 6  # сколько раз пробуем прокрутить и подождать подгрузки

# ----------------- Логирование -----------------
logger = logging.getLogger("news_parser")
logger.setLevel(logging.DEBUG)

# Файловый лог (чтобы workflow мог взять этот файл как артефакт)
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(fmt)
logger.addHandler(fh)

# Консольный лог (для локального запуска и GitHub Actions вывода)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(fmt)
logger.addHandler(ch)

# ----------------- Работа с БД -----------------
class NewsDB:
    def __init__(self, path: str = DB_FILE):
        """
        Подключается к sqlite3 БД (создаёт файл, если не существует).
        Таблица news имеет уникальный индекс по fingerprint (чтобы не добавлять дубли).
        """
        self.path = path
        logger.debug(f"Opening DB at: {self.path}")
        # Режимы подключения: если не существует — создаём. Если существует — используем.
        self.conn = sqlite3.connect(self.path, timeout=30)
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
        # индекс на pub_date чтобы мог сортировать
        cur.execute("CREATE INDEX IF NOT EXISTS idx_news_pub_date ON news(pub_date)")
        self.conn.commit()

    @staticmethod
    def fingerprint(title: str, link: str) -> str:
        h = hashlib.sha1()
        h.update((title + "|" + (link or "")).encode("utf-8"))
        return h.hexdigest()

    def add_article(self, site: str, title: str, link: str, pub_date: Optional[str]) -> bool:
        fp = self.fingerprint(title or "", link or "")
        parsed_date = datetime.utcnow().isoformat()
        try:
            self.conn.execute(
                "INSERT INTO news (site, title, link, pub_date, parsed_date, fingerprint, status) VALUES (?, ?, ?, ?, ?, ?, 'new')",
                (site, title, link, pub_date, parsed_date, fp),
            )
            self.conn.commit()
            logger.debug(f"DB: inserted article {site} | {title[:80]}")
            return True
        except sqlite3.IntegrityError:
            logger.debug(f"DB: duplicate skipped (fingerprint exists) {site} | {title[:80]}")
            return False
        except Exception as e:
            logger.exception(f"DB: unexpected error on insert: {e}")
            return False

    def count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(1) FROM news")
        return cur.fetchone()[0]

    def close(self):
        try:
            self.conn.close()
        except Exception as e:
            logger.debug(f"DB close exception: {e}")

# ----------------- Утилиты -----------------
def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def normalize_date(raw: Optional[str], site: Optional[str] = None) -> Optional[str]:
    """
    Попытки нормализовать дату: ISO -> return, 'Month Day, Year' -> parse,
    '5 hours ago' -> convert to UTC ISO, 'today' -> today's date.
    Иначе возвращаем исходную строку.
    """
    if not raw:
        return None
    s = raw.strip()
    # 1) ISO
    try:
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        pass
    # 2) 'October 1, 2025'
    try:
        dt = datetime.strptime(s, "%B %d, %Y")
        return dt.isoformat()
    except Exception:
        pass
    # 3) relative '5 hours ago', '2 minutes ago', 'an hour ago'
    low = s.lower()
    try:
        import re
        m = re.search(r"(\d+)\s+hour", low)
        if m:
            hours = int(m.group(1))
            return (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        m = re.search(r"(\d+)\s+minute", low)
        if m:
            mins = int(m.group(1))
            return (datetime.utcnow() - timedelta(minutes=mins)).isoformat()
        if "an hour ago" in low or "one hour ago" in low:
            return (datetime.utcnow() - timedelta(hours=1)).isoformat()
        if "today" == low or "today" in low:
            return datetime.utcnow().date().isoformat()
    except Exception:
        pass
    # fallback: вернуть строку, чтобы сохранить оригинал (можно декорировать позже)
    return s

def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials missing -> skip sending")
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
    """
    Если items_xpath содержит /text() на конце — для Selenium лучше убрать /text().
    Возвращаем скорректированный xpath (или тот же).
    (ВАЖНО: не меняем items_xpath в конфиге — используем его только как якорь проверочного типа)
    """
    if not xpath:
        return xpath
    s = xpath.strip()
    if s.endswith("/text()"):
        return s[: s.rfind("/text()")]
    return s

# ----------------- Парсер сайтов -----------------
class NewsParser:
    def __init__(self, sites_file: str = SITES_FILE):
        self.sites_file = sites_file
        self.db = NewsDB(DB_FILE)
        self.sites = self._load_sites()
        # Telegram: парсер уведомляет пользователя (TELEGRAM_USER_ID)
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_user = os.getenv("TELEGRAM_USER_ID", "").strip()
        self.counters = {
            "found_total": 0,
            "added_total": 0,
            "duplicates": 0,
            "per_site": {}
        }
        self.errors = []

    def _load_sites(self) -> Dict:
        if not os.path.exists(self.sites_file):
            logger.error(f"sites.json not found at {self.sites_file}")
            return {}
        try:
            with open(self.sites_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(f"Loaded sites config: {list(data.keys())}")
                return data
        except Exception as e:
            logger.exception(f"Failed to load sites.json: {e}")
            return {}

    # ---------------- STATIC (requests + lxml) ----------------
    def parse_site_static(self, site_name: str, cfg: dict):
        """
        Парсинг статических страниц (requests + lxml).
        items_xpath — anchor (если не найден — пропускаем сайт).
        title_xpath/date_xpath — должны содержать {news_index}.
        """
        logger.info(f"[{site_name}] static parse -> {cfg.get('url')}")
        url = cfg.get("url")
        items_xpath = cfg.get("items_xpath", "")
        title_tpl = cfg.get("title_xpath", "")
        date_tpl = cfg.get("date_xpath", "")
        max_items = safe_int(cfg.get("max_items"), DEFAULT_MAX_ITEMS)
        miss_break = safe_int(cfg.get("consecutive_miss_break"), DEFAULT_CONSECUTIVE_MISS_BREAK)

        # config checks
        if not items_xpath:
            msg = f"[{site_name}] CONFIG ERROR: items_xpath is missing"
            logger.error(msg)
            self.errors.append(msg)
            return
        if "{news_index}" not in title_tpl:
            msg = f"[{site_name}] CONFIG ERROR: title_xpath must contain '{{news_index}}'."
            logger.error(msg)
            self.errors.append(msg)
            return

        # HTTP fetch
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            resp.raise_for_status()
            tree = html.fromstring(resp.content)
        except Exception as e:
            msg = f"[{site_name}] HTTP fetch error: {e}"
            logger.exception(msg)
            self.errors.append(msg)
            return

        # anchor search (anchor may return text nodes or elements)
        anchors = tree.xpath(items_xpath)
        logger.info(f"[{site_name}] anchor search result count (static): {len(anchors)}")
        if len(anchors) == 0:
            msg = f"[{site_name}] Anchor (items_xpath) NOT FOUND on static page."
            logger.error(msg)
            self.errors.append(msg)
            return

        # iterate by index
        idx = 1
        consecutive_miss = 0
        while idx <= max_items:
            title_xpath = title_tpl.format(news_index=idx)
            date_xpath = date_tpl.format(news_index=idx) if date_tpl else None

            try:
                t_nodes = tree.xpath(title_xpath)
            except Exception as e:
                logger.debug(f"[{site_name}] invalid title xpath at idx {idx}: {e}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    break
                idx += 1
                continue

            if not t_nodes:
                logger.debug(f"[{site_name}] static: no title at idx {idx}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    logger.info(f"[{site_name}] static: break after {miss_break} consecutive misses")
                    break
                idx += 1
                continue

            consecutive_miss = 0
            tnode = t_nodes[0]
            # title text
            try:
                title = tnode.text_content().strip()
            except Exception:
                title = str(tnode).strip()

            # link extraction - try node href, or find parent <a>
            link = None
            try:
                if getattr(tnode, "tag", None) == "a" and tnode.get("href"):
                    link = tnode.get("href")
                else:
                    a = tnode.xpath(".//a")
                    if a and hasattr(a[0], "get"):
                        link = a[0].get("href")
                    else:
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

            raw_date = ""
            if date_xpath:
                try:
                    d_nodes = tree.xpath(date_xpath)
                    if d_nodes:
                        if hasattr(d_nodes[0], "text_content"):
                            raw_date = d_nodes[0].text_content().strip()
                        else:
                            raw_date = str(d_nodes[0]).strip()
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
                logger.info(f"[{site_name}] static #{idx} => {'NEW' if added else 'DUP'}: {title[:80]}")
            else:
                logger.debug(f"[{site_name}] static skip idx {idx} (title/link missing)")

            idx += 1

    # ---------------- SELENIUM (dynamic) ----------------
    def _setup_selenium(self):
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium modules not available (import failed).")
            return None
        try:
            options = Options()
            # modern headless
            try:
                options.add_argument("--headless=new")
            except Exception:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(60)
            return driver
        except Exception as e:
            logger.exception(f"Selenium driver init failed: {e}")
            return None

    def parse_site_selenium(self, site_name: str, cfg: dict):
        """
        Парсинг через Selenium:
        - ждём появления anchor (items_xpath без /text())
        - делаем автопрокрутку до SELENIUM_MAX_SCROLLS для подгрузки lazy-load
        - затем пробегаем title_xpath с {news_index}
        """
        logger.info(f"[{site_name}] selenium parse -> {cfg.get('url')}")
        url = cfg.get("url")
        items_xpath_raw = cfg.get("items_xpath", "")
        title_tpl = cfg.get("title_xpath", "")
        date_tpl = cfg.get("date_xpath", "")
        max_items = safe_int(cfg.get("max_items"), DEFAULT_MAX_ITEMS)
        miss_break = safe_int(cfg.get("consecutive_miss_break"), DEFAULT_CONSECUTIVE_MISS_BREAK)
        wait = safe_int(cfg.get("wait"), SELENIUM_WAIT_DEFAULT)

        if not items_xpath_raw:
            msg = f"[{site_name}] CONFIG ERROR: items_xpath missing (selenium)"
            logger.error(msg)
            self.errors.append(msg)
            return
        if "{news_index}" not in title_tpl:
            msg = f"[{site_name}] CONFIG ERROR: title_xpath must contain '{{news_index}}' (selenium)"
            logger.error(msg)
            self.errors.append(msg)
            return

        # create driver
        driver = self._setup_selenium()
        if not driver:
            msg = f"[{site_name}] Selenium driver not available"
            logger.error(msg)
            self.errors.append(msg)
            return

        anchor_xpath = anchor_xpath_for_selenium(items_xpath_raw)

        try:
            driver.get(url)
        except Exception as e:
            logger.exception(f"[{site_name}] Selenium navigation to URL failed: {e}")
            try:
                driver.quit()
            except Exception:
                pass
            self.errors.append(f"{site_name} nav error: {e}")
            return

        logger.info(f"[{site_name}] Selenium: waiting up to {wait}s for anchor presence (anchor_xpath: {anchor_xpath})")
        try:
            WebDriverWait(driver, wait).until(EC.presence_of_all_elements_located((By.XPATH, anchor_xpath)))
        except Exception as e:
            # несмотря на ожидание, попробуем всё же найти элементы, но логируем ошибку
            logger.warning(f"[{site_name}] Selenium: anchor not found within {wait}s: {e}")

        # try to gather anchors and do a few scrolls to load lazy content
        try:
            anchors = driver.find_elements(By.XPATH, anchor_xpath)
            logger.info(f"[{site_name}] Selenium: initial anchors count: {len(anchors)}")
            if len(anchors) == 0:
                # возможно xpath указывает на текст node -> пусто. Но всё равно пробуем продолжить и проверять title_xpath
                logger.warning(f"[{site_name}] Selenium: anchor count is 0 — will still attempt per-index parsing (maybe anchor is text() node).")
        except Exception as e:
            logger.warning(f"[{site_name}] Selenium: anchors search failed: {e}")
            anchors = []

        # try progressive scroll to load more items (if page lazy-loads)
        prev_anchor_count = len(anchors)
        scroll_count = 0
        while scroll_count < SELENIUM_MAX_SCROLLS:
            # scroll to bottom
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            time.sleep(SELENIUM_SCROLL_INTERVAL)
            try:
                anchors = driver.find_elements(By.XPATH, anchor_xpath)
                curr = len(anchors)
                logger.debug(f"[{site_name}] Selenium scroll {scroll_count+1}: anchors now {curr}")
                if curr > prev_anchor_count:
                    prev_anchor_count = curr
                    # continue scrolling if new anchors appeared
                else:
                    # no increase -> maybe content loaded fully
                    break
            except Exception:
                break
            scroll_count += 1

        logger.info(f"[{site_name}] Selenium: final anchors count after scrolls: {len(anchors)} (scrolls: {scroll_count})")

        # Now iterate indices
        idx = 1
        consecutive_miss = 0
        while idx <= max_items:
            title_xpath = title_tpl.format(news_index=idx)
            date_xpath = date_tpl.format(news_index=idx) if date_tpl else None
            logger.debug(f"[{site_name}] Selenium: checking idx={idx} title_xpath={title_xpath}")

            try:
                title_elems = driver.find_elements(By.XPATH, title_xpath)
            except Exception as e:
                logger.debug(f"[{site_name}] Selenium invalid title xpath at idx {idx}: {e}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    logger.info(f"[{site_name}] Selenium: stopping after {miss_break} consecutive invalid/missing title xpaths")
                    break
                idx += 1
                continue

            if not title_elems:
                logger.debug(f"[{site_name}] Selenium: no title at idx {idx}")
                consecutive_miss += 1
                if consecutive_miss >= miss_break:
                    logger.info(f"[{site_name}] Selenium: reached {miss_break} consecutive misses — stop")
                    break
                idx += 1
                continue

            # found title element(s)
            consecutive_miss = 0
            te = title_elems[0]
            try:
                title = te.text.strip()
            except Exception:
                title = ""

            # link extraction
            link = None
            try:
                if te.tag_name.lower() == "a":
                    link = te.get_attribute("href")
                else:
                    a = te.find_elements(By.XPATH, ".//a")
                    if a:
                        link = a[0].get_attribute("href")
                    else:
                        # climb up parents to find enclosing <a>
                        parent = te
                        for climb in range(6):
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

            # date extraction
            raw_date = ""
            if date_xpath:
                try:
                    date_elems = driver.find_elements(By.XPATH, date_xpath)
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
                logger.info(f"[{site_name}] selenium #{idx} => {'NEW' if added else 'DUP'}: {title[:80]}")
            else:
                logger.debug(f"[{site_name}] selenium skip idx {idx} (title/link missing)")

            idx += 1

        try:
            driver.quit()
        except Exception:
            pass

    # ----------------- RUN ALL -----------------
    def run(self):
        start_ts = time.time()
        if not self.sites:
            msg = "No sites configured (sites.json missing or empty)"
            logger.error(msg)
            return self._finalize(start_ts)

        for site_name, cfg in self.sites.items():
            logger.info(f"=== Processing site: {site_name} ===")
            try:
                # fill defaults if not present
                cfg = dict(cfg)
                if "max_items" not in cfg:
                    cfg["max_items"] = DEFAULT_MAX_ITEMS
                if "consecutive_miss_break" not in cfg:
                    cfg["consecutive_miss_break"] = DEFAULT_CONSECUTIVE_MISS_BREAK

                mode = cfg.get("mode", "selenium")
                if mode == "static":
                    self.parse_site_static(site_name, cfg)
                elif mode == "selenium":
                    self.parse_site_selenium(site_name, cfg)
                else:
                    msg = f"[{site_name}] Unknown parsing mode: {mode}"
                    logger.error(msg)
                    self.errors.append(msg)
            except Exception as e:
                logger.exception(f"[{site_name}] top-level error: {e}")
                self.errors.append(f"{site_name} top error: {e}")

        return self._finalize(start_ts)

    def _finalize(self, start_ts: float):
        elapsed = int(time.time() - start_ts)
        found = self.counters.get("found_total", 0)
        added = self.counters.get("added_total", 0)
        dups = self.counters.get("duplicates", 0)
        per_site = self.counters.get("per_site", {})

        # Message format — первым показываем число новых новостей (как просили)
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

        telegram_sent = False
        if self.telegram_token and self.telegram_user:
            text = "\n".join(lines)
            telegram_sent = send_telegram(self.telegram_token, self.telegram_user, text)
        else:
            logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_USER_ID not set -> skip telegram send")
            # errors list kept for debug

        result = {
            "found_total": found,
            "added_total": added,
            "duplicates": dups,
            "per_site": per_site,
            "errors": len(self.errors),
            "telegram_sent": bool(telegram_sent),
            "elapsed": elapsed
        }

        # write JSON result for Actions to parse
        try:
            with open(RESULT_JSON, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
            logger.info(f"Wrote run result to {RESULT_JSON}")
        except Exception as e:
            logger.exception(f"Failed to write result JSON: {e}")

        logger.info(f"Found total: {found}, Added new: {added}, Duplicates: {dups}, Per site: {per_site}, Errors: {len(self.errors)}, Telegram sent: {telegram_sent}, Elapsed: {elapsed}s")
        return result

# ----------------- CLI -----------------
def main():
    parser = NewsParser()
    res = parser.run()
    try:
        parser.db.close()
    except Exception:
        pass
    logger.info("Parser finished.")
    # For CLI convenience print short JSON to stdout
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
