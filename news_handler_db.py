#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import aiohttp
import base64
import json
import logging
import sqlite3
import time
import math
from datetime import datetime, timedelta

# ---------- Конфигурация ----------
BASE_DIR = os.getcwd()
DB_PATH = os.path.join(BASE_DIR, "news.db")
LOG_FILE = os.path.join(BASE_DIR, "news_handler.log")

# ENV
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("news-handler")

# ---------- Утилиты ----------
def estimate_tokens(text: str) -> int:
    if not text:
        return 1
    return max(1, math.ceil(len(text) / 4.0))

async def send_photo_to_telegram(image_bytes: bytes, caption: str, token: str, chat_id: str, session: aiohttp.ClientSession):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    form = aiohttp.FormData()
    form.add_field("chat_id", chat_id)
    form.add_field("photo", image_bytes, filename="news.jpg", content_type="image/jpeg")
    form.add_field("caption", caption)
    form.add_field("parse_mode", "HTML")
    try:
        async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if resp.status == 200:
                logger.info("Telegram photo sent")
                return True
            else:
                logger.error(f"Telegram sendPhoto failed: {resp.status} {text}")
                return False
    except Exception as e:
        logger.error(f"Telegram sendPhoto exception: {e}")
        return False

async def send_text_to_telegram(text: str, token: str, chat_id: str, session: aiohttp.ClientSession):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            text_resp = await resp.text()
            if resp.status == 200:
                logger.info("Telegram text sent")
                return True
            else:
                logger.error(f"Telegram sendMessage failed: {resp.status} {text_resp}")
                return False
    except Exception as e:
        logger.error(f"Telegram sendText exception: {e}")
        return False

# ---------- Yandex clients (async) ----------
class AsyncYandexGPTMonitor:
    def __init__(self, api_key: str, folder_id: str):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}
        self.folder_id = folder_id
        self.session = None
        self.token_usage = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def yandex_gpt_call(self, prompt: str, max_tokens: int = 2000):
        if not self.headers["Authorization"] or not self.folder_id:
            logger.error("Yandex GPT key/folder missing")
            return None
        data = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
            "completionOptions": {"stream": False, "temperature": 0.7, "maxTokens": max_tokens},
            "messages": [
                {"role": "system", "text": "Ты — профессиональный редактор AI-новостей."},
                {"role": "user", "text": prompt}
            ]
        }
        try:
            async with self.session.post(self.api_url, headers=self.headers, json=data, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    try:
                        content = res['result']['alternatives'][0]['message']['text']
                    except Exception:
                        content = json.dumps(res)[:1000]
                    estimated_tokens = (len(content) + len(prompt)) // 4
                    self.token_usage += estimated_tokens
                    logger.info(f"YandexGPT OK (~{estimated_tokens} tokens)")
                    return content
                else:
                    text = await resp.text()
                    logger.error(f"YandexGPT error: {resp.status} {text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("YandexGPT timeout")
            return None
        except Exception as e:
            logger.error(f"YandexGPT exception: {e}")
            return None

class AsyncYandexArtGenerator:
    def __init__(self, api_key: str, folder_id: str):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
        self.headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}
        self.folder_id = folder_id
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def generate_image(self, prompt: str, max_attempts: int = 30, delay: int = 4):
        if not self.headers["Authorization"] or not self.folder_id:
            logger.warning("Yandex ART keys not set")
            return None
        data = {
            "modelUri": f"art://{self.folder_id}/yandex-art/latest",
            "generationOptions": {"seed": int(time.time()) % 1000000},
            "messages": [{"weight": 1, "text": prompt}]
        }
        try:
            async with self.session.post(self.api_url, headers=self.headers, json=data, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    task_id = res.get("id")
                    if not task_id:
                        logger.error("No task id from art start")
                        return None
                    for attempt in range(max_attempts):
                        check_url = f"https://llm.api.cloud.yandex.net/operations/{task_id}"
                        async with self.session.get(check_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)) as cresp:
                            if cresp.status == 200:
                                cres = await cresp.json()
                                if cres.get("done"):
                                    try:
                                        image_b64 = cres['response']['image']
                                        img_bytes = base64.b64decode(image_b64)
                                        logger.info(f"Art generated ({len(img_bytes)} bytes)")
                                        return img_bytes
                                    except Exception as e:
                                        logger.error(f"Art decode error: {e}")
                                        return None
                        await asyncio.sleep(delay)
                    logger.error("Art generation timed out")
                    return None
                else:
                    text = await resp.text()
                    logger.error(f"Art start error: {resp.status} {text}")
                    return None
        except Exception as e:
            logger.error(f"Art generation exception: {e}")
            return None

# ---------- DB helpers ----------
def get_next_article(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT * FROM news WHERE status='new' ORDER BY pub_date ASC, parsed_date ASC LIMIT 1")
    return cur.fetchone()

def mark_article_posted(conn: sqlite3.Connection, id_):
    cur = conn.cursor()
    cur.execute("UPDATE news SET status='posted' WHERE id = ?", (id_,))
    conn.commit()

# ---------- Processing one article ----------
async def process_one_article():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram TOKEN/CHAT not set in env")
        return {"ok": False, "reason": "telegram not set"}

    if not os.path.exists(DB_PATH):
        logger.info("DB not found. Парсер, возможно, не запускался.")
        return {"ok": True, "sent": 0, "reason": "db missing"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    row = get_next_article(conn)
    if not row:
        logger.info("Нет новых статей для отправки.")
        conn.close()
        return {"ok": True, "sent": 0}

    article_id = row["id"]
    site = row["site"]
    title = row["title"]
    link = row["link"]
    pub_date = row["pub_date"]

    logger.info(f"Processing id={article_id}, site={site}, title={title[:100]}")

    prompt = f"""
ЗАДАЧА: Перевести на русский и создать краткий пересказ новости: {link}

ТРЕБОВАНИЯ:
1. Заголовок: краткий, привлекающий внимание
2. Текст: 5-7 предложений, только ключевые факты
3. Вывод: практическая польза (1 предложение)
4. Ссылка: оригинальный URL
5. Хештеги: 3 релевантных тега (русский)

ФОРМАТ:
🚀 <Заголовок>

📝 <5-7 предложений>

💡 <Польза>

🔗 {link}

🔖 #тег1 #тег2 #тег3
"""

    # GPT
    async with AsyncYandexGPTMonitor(YANDEX_API_KEY, YANDEX_FOLDER_ID) as gpt:
        summary = await gpt.yandex_gpt_call(prompt)
    if not summary:
        logger.error("YandexGPT не вернул результат")
        conn.close()
        return {"ok": False, "reason": "gpt failed"}

    # Image
    img_prompt = f"News illustration: {title}, digital art, modern news style, professional"
    async with AsyncYandexArtGenerator(YANDEX_API_KEY, YANDEX_FOLDER_ID) as artgen:
        image_bytes = await artgen.generate_image(img_prompt)

    # Send to Telegram
    async with aiohttp.ClientSession() as session:
        sent_ok = False
        if image_bytes:
            sent_ok = await send_photo_to_telegram(image_bytes, summary, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, session)
        if not sent_ok:
            sent_ok = await send_text_to_telegram(summary, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, session)

    if sent_ok:
        mark_article_posted(conn, article_id)
        tokens_est = estimate_tokens(summary)
        logger.info(f"Posted id={article_id}. Tokens est: ~{tokens_est}")
        conn.close()
        return {"ok": True, "sent": 1, "id": article_id, "tokens_est": tokens_est}
    else:
        logger.error("Failed to send to Telegram")
        conn.close()
        return {"ok": False, "reason": "send failed"}

# ---------- main sync ----------
def main_sync():
    res = asyncio.run(process_one_article())
    print("=== NEWS HANDLER RESULT ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return res

if __name__ == "__main__":
    main_sync()
