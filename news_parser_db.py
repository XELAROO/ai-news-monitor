#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import hashlib
import time
import json
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from lxml import html
from urllib.parse import urljoin
import math

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False

# ---------- Конфигурация ----------
BASE_DIR = os.getcwd()
DB_PATH = os.path.join(BASE_DIR, "news.db")
LOG_FILE = os.path.join(BASE_DIR, "news_parser.log")
SITES_FILE = os.path.join(BASE_DIR, "sites.json")

# Telegram: токены из окружения (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "")

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("news-parser")

# ---------- Утилиты ----------
def estimate_tokens(text: str) -> int:
    if not text:
        return 1
    return max(1, math.ceil(len(text) / 4.0))

def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        logger.warning("TELEGRAM_BOT_TOKEN или TELEGRAM_USER_ID не заданы. Пропускаем отправку Telegram.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_USER_ID, "text": text}
    try:
        resp = requests.post(url, data=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram send exception: {e}")
        return False

# ---------- Класс работы с БД ----------
class NewsDB:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        q = """
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            pub_date TEXT NOT NULL,
            parsed_date TEXT NOT NULL,
            fingerprint TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'new'
        );
        """
        self.conn.execute(q)
        self.conn.commit()

    def add_article(self, site, title, link, pub_date):
        fingerprint = hashlib.md5(f"{title}|{link}".encode("utf-8")).hexdigest()
        parsed_date = datetime.now().isoformat()
        try:
            self.conn.execute(
                """
                INSERT INTO news (site, title, link, pub_date, parsed_date, fingerprint, status)
                VALUES (?, ?, ?, ?, ?, ?, 'new')
                """,
                (site, title, link, pub_date, parsed_date, fingerprint),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_posted(self, ids):
        if not ids:
            return
        q = f"UPDATE news SET status='posted' WHERE id IN ({','.join('?'*len(ids))})"
        self.conn.execute(q, ids)
        self.conn.commit()

    def mark_posted_one(self, id_):
        self.conn.execute("UPDATE news SET status='posted' WHERE id = ?", (id_,))
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except:
            pass

# ---------- Парсер ----------
class NewsParser:
    def __init__(self):
        self.db = NewsDB()
        self.sites = self.load_sites()

    def load_sites(self):
        if not os.path.exists(SITES_FILE):
            logger.error(f"Sites config not found at: {SITES_FILE}")
            return {}
        try:
            with open(SITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading sites.json: {e}")
            return {}

    def setup_selenium(self):
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available")
            return None
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        try:
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.error(f"Error creating Chrome webdriver: {e}")
            return None

    def normalize_date(self, date_str, site="generic"):
        now = datetime.now()
        if not date_str:
            return now.isoformat()
        try:
            s = date_str.lower()
            # hours e.g. "5 hours ago" or "5h"
            if "hour" in s or (s.endswith("h") and s[:-1].isdigit()):
                parts = s.split()
                num = None
                for p in parts:
                    if p.isdigit():
                        num = int(p); break
                    if p.endswith("h") and p[:-1].isdigit():
                        num = int(p[:-1]); break
                if num is None:
                    num = 1
                return (now - timedelta(hours=num)).isoformat()
            if "minute" in s or (s.endswith("m") and s[:-1].isdigit()):
                parts = s.split()
                num = None
                for p in parts:
                    if p.isdigit():
                        num = int(p); break
                    if p.endswith("m") and p[:-1].isdigit():
                        num = int(p[:-1]); break
                if num is None:
                    num = 1
                return (now - timedelta(minutes=num)).isoformat()
            if "yesterday" in s:
                return (now - timedelta(days=1)).isoformat()
            # try parse "Sep 30, 2025"
            try:
                return datetime.strptime(date_str, "%b %d, %Y").isoformat()
            except Exception:
                return now.isoformat()
        except Exception:
            return now.isoformat()

    def parse_static(self, site_name, config, counters, errors):
        logger.info(f"[{site_name}] static parse: {config.get('url')}")
        added = []
        try:
            resp = requests.get(config["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            tree = html.fromstring(resp.content)

            title_nodes = tree.xpath(config["title_xpath"])
            date_nodes = tree.xpath(config["date_xpath"])

            counters["found_total"] += max(len(title_nodes), len(date_nodes))
            for idx, tnode in enumerate(title_nodes):
                title = tnode.text_content().strip() if tnode is not None else ""
                link = None
                try:
                    link = tnode.get("href")
                except Exception:
                    link = None
                if not link:
                    try:
                        a = tnode.xpath(".//a")
                        if a and hasattr(a[0], "get"):
                            link = a[0].get("href")
                    except Exception:
                        link = None
                if link:
                    link = urljoin(config["url"], link)
                raw_date = date_nodes[idx].text_content().strip() if idx < len(date_nodes) else ""
                pub_date = self.normalize_date(raw_date, site=site_name)
                if title and link:
                    is_new = self.db.add_article(site_name, title, link, pub_date)
                    if is_new:
                        counters["added_total"] += 1
                        counters["per_site"][site_name] = counters["per_site"].get(site_name, 0) + 1
                        added.append({"site": site_name, "title": title, "link": link})
                    else:
                        counters["duplicates"] += 1
        except Exception as e:
            err = f"{site_name} static error: {e}"
            logger.error(err)
            errors.append(err)
        return added

    def parse_selenium(self, site_name, config, counters, errors):
        logger.info(f"[{site_name}] selenium parse: {config.get('url')}")
        added = []
        driver = None
        try:
            driver = self.setup_selenium()
            if not driver:
                errors.append(f"{site_name} selenium: webdriver init failed")
                return added
            driver.get(config["url"])
            time.sleep(config.get("wait", 8))

            title_elems = driver.find_elements(By.XPATH, config["title_xpath"])
            date_elems = driver.find_elements(By.XPATH, config["date_xpath"])

            counters["found_total"] += max(len(title_elems), len(date_elems))
            for idx, te in enumerate(title_elems):
                try:
                    title = te.text.strip()
                    link = te.get_attribute("href")
                    if not link:
                        try:
                            a = te.find_element(By.XPATH, ".//a")
                            link = a.get_attribute("href")
                        except:
                            link = None
                    if link:
                        link = urljoin(config["url"], link)
                    raw_date = date_elems[idx].text.strip() if idx < len(date_elems) else ""
                    pub_date = self.normalize_date(raw_date, site=site_name)
                    if title and link:
                        is_new = self.db.add_article(site_name, title, link, pub_date)
                        if is_new:
                            counters["added_total"] += 1
                            counters["per_site"][site_name] = counters["per_site"].get(site_name, 0) + 1
                            added.append({"site": site_name, "title": title, "link": link})
                        else:
                            counters["duplicates"] += 1
                except Exception as e_item:
                    logger.warning(f"[{site_name}] item parse warning: {e_item}")
        except Exception as e:
            err = f"{site_name} selenium error: {e}"
            logger.error(err)
            errors.append(err)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        return added

    def run(self):
        start_ts = time.time()
        start_dt = datetime.now()
        counters = {"found_total": 0, "added_total": 0, "duplicates": 0, "per_site": {}}
        errors = []
        all_added = []

        for site_name, cfg in self.sites.items():
            mode = cfg.get("mode", "selenium")
            if mode == "static":
                added = self.parse_static(site_name, cfg, counters, errors)
            elif mode == "selenium":
                added = self.parse_selenium(site_name, cfg, counters, errors)
            elif mode == "api":
                logger.info(f"[{site_name}] API mode not implemented yet")
                added = []
            else:
                logger.warning(f"[{site_name}] Unknown mode: {mode}")
                added = []
            all_added.extend(added)

        elapsed = int(time.time() - start_ts)
        added_total = counters["added_total"]
        found_total = counters["found_total"]
        duplicates = counters["duplicates"]
        per_site = counters["per_site"]

        # Telegram message
        per_site_lines = [f"- {s}: {per_site.get(s, 0)}" for s in sorted(self.sites.keys())]
        status_line = "✅ Парсинг завершён" if not errors else "⚠️ Парсинг завершён (есть ошибки)"
        now_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

        msg_lines = []
        msg_lines.append(f"📰 Новые новости: {added_total} — {status_line}")
        msg_lines.append(f"🗓 Дата и время: {now_str}")
        msg_lines.append(f"⏱ Время работы скрипта: {elapsed} секунд")
        msg_lines.append(f"Найдено (в DOM): {found_total}")
        msg_lines.append(f"Новые новости: {added_total}")
        msg_lines.extend(per_site_lines)
        msg_lines.append(f"Дубликаты: {duplicates}")
        msg_lines.append(f"ВСЕГО: {added_total}")
        if errors:
            msg_lines.append("")
            msg_lines.append("Ошибки:")
            for err in errors:
                msg_lines.append(f"- {err}")
        message_text = "\n".join(msg_lines)
        tokens_est = estimate_tokens(message_text)
        message_text += f"\n\n[Токены в сообщении (approx): ~{tokens_est}]"

        sent = send_telegram_message(message_text)
        if sent:
            logger.info("Telegram: message sent")
        else:
            logger.warning("Telegram: message NOT sent")

        # Логирование в файл уже производится через logger
        logger.info(f"Found total: {found_total}, Added new: {added_total}, Duplicates: {duplicates}")
        logger.info(f"Per site: {per_site}")
        logger.info(f"Elapsed: {elapsed}s")

        return {
            "found_total": found_total,
            "added_total": added_total,
            "duplicates": duplicates,
            "per_site": per_site,
            "errors": errors,
            "telegram_sent": sent,
            "message_tokens_est": tokens_est,
            "elapsed": elapsed
        }

# ---------- main ----------
def main():
    parser = NewsParser()
    result = parser.run()
    parser.db.close()
    # Краткое резюме для логов Actions
    print("=== PARSER RESULT ===")
    print(json.dumps({
        "found_total": result["found_total"],
        "added_total": result["added_total"],
        "duplicates": result["duplicates"],
        "per_site": result["per_site"],
        "errors": len(result["errors"]),
        "telegram_sent": result["telegram_sent"],
        "message_tokens_est": result["message_tokens_est"],
        "elapsed": result["elapsed"]
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
