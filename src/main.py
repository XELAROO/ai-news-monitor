import os
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta, timezone
import logging
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Расписание публикаций (13 раз в день с 07:00 до 19:00 МСК)
PUBLICATION_HOURS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]

class AsyncYandexGPTMonitor:
    def __init__(self):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        self.session = None
        self.token_usage = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def yandex_gpt_call(self, prompt, max_tokens=2000):
        """Асинхронный вызов YandexGPT API"""
        try:
            data = {
                "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": max_tokens
                },
                "messages": [
                    {
                        "role": "system",
                        "text": "Ты - профессиональный редактор новостного канала об ИИ. Создавай краткие, информативные новости на русском. Максимум 3-4 предложения. Добавляй пустые строки между блоками для лучшей читаемости."
                    },
                    {
                        "role": "user", 
                        "text": prompt
                    }
                ]
            }

            logger.info(f"🔍 Запрос к YandexGPT ({len(prompt)} символов)")
            
            async with self.session.post(
                self.api_url, 
                headers=self.headers, 
                json=data, 
                timeout=aiohttp.ClientTimeout(total=90)
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    if 'result' in result and 'alternatives' in result['result']:
                        content = result['result']['alternatives'][0]['message']['text']
                        
                        # Подсчет токенов
                        estimated_tokens = len(content) // 4 + len(prompt) // 4
                        self.token_usage += estimated_tokens
                        
                        cost = (estimated_tokens / 1000) * 0.60
                        logger.info(f"✅ Ответ ({len(content)} символов, ~{estimated_tokens} ткн, {cost:.2f} руб)")
                        
                        return content
                    else:
                        logger.error(f"❌ Неверный формат ответа")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка API: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут запроса (90 сек)")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None

    async def search_ai_news(self, hour):
        """Поиск новостей для конкретного часа"""
        time_contexts = {
            7: "утренние", 8: "утренние", 9: "утренние",
            10: "дневные", 11: "дневные", 12: "обеденные",
            13: "дневные", 14: "дневные", 15: "дневные",
            16: "вечерние", 17: "вечерние", 18: "вечерние", 19: "поздние вечерние"
        }
        
        context = time_contexts.get(hour, "текущие")
        
        prompt = f"""
        Найди ОДНУ самую интересную новость за последние 1-2 часа в сфере ИИ.
        Сейчас {hour:02d}:00 МСК ({context} часы).
        
        Критерии:
        - Google, Microsoft, OpenAI, Meta, Yandex, Apple, Amazon, DeepSeek
        - Технические прорывы, обновления, исследования
        - Практическая значимость
        
        Формат (соблюдай точно!):
        
        🚀 Заголовок с эмодзи
        
        📝 3-4 предложения сути новости. Будь конкретным!
        
        💡 1-2 предложения о значении
        
        🔗 Ссылка на источник
        
        🔖 3-5 хештегов
        
        ВАЖНО: Добавляй пустую строку между каждым блоком!
        Ничего не пиши перед 🚀 и после 🔖!
        """
        
        return await self.yandex_gpt_call(prompt)

async def send_to_telegram_async(message, session):
    """Асинхронная отправка в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as response:
            if response.status == 200:
                return True
            else:
                return False
    except Exception:
        return False

async def publish_hourly_news(hour):
    """Публикация новости для конкретного часа"""
    start_time = time.time()
    
    try:
        async with AsyncYandexGPTMonitor() as monitor:
            async with aiohttp.ClientSession() as telegram_session:
                news_content = await monitor.search_ai_news(hour)
                
                if news_content:
                    # Дополнительная обработка для гарантии пробелов
                    lines = news_content.split('\n')
                    cleaned_content = []
                    
                    for i, line in enumerate(lines):
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Добавляем текущую строку
                        cleaned_content.append(line)
                        
                        # Добавляем пустую строку после блоков (кроме последнего)
                        if (line.startswith('🚀') or line.startswith('📝') or 
                            line.startswith('💡') or line.startswith('🔗')) and i < len(lines) - 1:
                            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                            if next_line and not next_line.startswith('🔖'):
                                cleaned_content.append('')
                    
                    telegram_message = '\n'.join(cleaned_content)
                    
                    if await send_to_telegram_async(telegram_message, telegram_session):
                        execution_time = time.time() - start_time
                        logger.info(f"✅ {hour:02d}:00 - {execution_time:.1f}сек, ~{monitor.token_usage}ткн")
                        return True
                    else:
                        logger.error(f"❌ {hour:02d}:00 - Ошибка Telegram")
                        return False
                else:
                    logger.error(f"❌ {hour:02d}:00 - Нет новости")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ {hour:02d}:00 - Ошибка: {e}")
        return False

async def main():
    """Основная функция"""
    # Текущее время по МСК
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    current_hour = msk_time.hour
    
    logger.info("=" * 50)
    logger.info("🚀 AI News Monitor - Исправленная версия с пробелами")
    logger.info(f"⏰ Текущее время: {msk_time.strftime('%H:%M')} МСК")
    logger.info("=" * 50)
    
    # Проверяем, нужно ли публиковать в этот час
    if current_hour in PUBLICATION_HOURS:
        logger.info(f"🎯 Публикуем новость для {current_hour:02d}:00")
        success = await publish_hourly_news(current_hour)
        
        if success:
            logger.info(f"🎉 Успешно завершено для {current_hour:02d}:00")
        else:
            logger.warning(f"⚠️ Завершено с ошибками для {current_hour:02d}:00")
    else:
        logger.info(f"⏸️ {current_hour:02d}:00 - не время публикации")

if __name__ == "__main__":
    # Быстрая проверка переменных
    if not all([YANDEX_API_KEY, YANDEX_FOLDER_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        logger.error("❌ Отсутствуют необходимые переменные окружения")
        exit(1)
    
    # Запуск
    asyncio.run(main())
