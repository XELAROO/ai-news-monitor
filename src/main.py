import os
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta, timezone
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

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
                        "text": "Ты - профессиональный редактор новостного канала об ИИ. Создавай краткие, информативные новости на русском."
                    },
                    {
                        "role": "user", 
                        "text": prompt
                    }
                ]
            }

            logger.info(f"🔍 Отправка асинхронного запроса ({len(prompt)} символов)")
            
            async with self.session.post(
                self.api_url, 
                headers=self.headers, 
                json=data, 
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    if 'result' in result and 'alternatives' in result['result']:
                        content = result['result']['alternatives'][0]['message']['text']
                        
                        # Примерный подсчет токенов
                        estimated_tokens = len(content) // 4 + len(prompt) // 4
                        self.token_usage += estimated_tokens
                        
                        cost = (estimated_tokens / 1000) * 0.60
                        logger.info(f"✅ Ответ получен ({len(content)} символов, ~{estimated_tokens} токенов, {cost:.2f} руб)")
                        
                        return content
                    else:
                        logger.error(f"❌ Неверный формат ответа")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка API: {response.status} - {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут запроса к YandexGPT")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка вызова YandexGPT: {e}")
            return None

    async def search_ai_news(self, hour):
        """Поиск новостей для конкретного часа"""
        time_contexts = {
            6: "утренние", 7: "утренние", 8: "утренние",
            9: "дневные", 10: "дневные", 11: "дневные", 
            12: "обеденные", 13: "дневные", 14: "дневные",
            15: "дневные", 16: "вечерние", 17: "вечерние", 18: "вечерние"
        }
        
        context = time_contexts.get(hour, "последние")
        
        prompt = f"""
        Найди САМУЮ интересную новость за последние 1-2 часа в сфере искусственного интеллекта.
        
        Критерии:
        - Новости от Google, Microsoft, OpenAI, Meta, Yandex, Apple, Amazon, DeepSeek
        - Технические прорывы, крупные обновления, исследования
        - Практическая значимость
        
        Формат для Telegram (ОЧЕНЬ ВАЖНО - соблюдай точно!):
        
        🚀 [Интересный заголовок с эмодзи]
        
        📝 [Суть новости: 3-4 предложения. Будь конкретным! Упоминай технологии, цифры, даты]
        
        💡 [Практическое значение: 1-2 предложения]
        
        🔗 [Ссылка на официальный источник]
        
        🔖 [3-5 релевантных хештегов на русском/английском]
        
        НИЧЕГО не пиши перед заголовком и после хештегов!
        Заголовок должен начинаться сразу с 🚀
        """
        
        return await self.yandex_gpt_call(prompt)

async def send_to_telegram_async(message, session):
    """Асинхронная отправка в Telegram с отключенными превью"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True  # Отключаем превью ссылок
        }
        
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logger.info("✅ Сообщение отправлено в Telegram!")
                return True
            else:
                error_text = await response.text()
                logger.error(f"❌ Ошибка Telegram: {response.status} - {error_text}")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

async def publish_hourly_news(hour):
    """Публикация новости для конкретного часа"""
    logger.info(f"📅 Запуск публикации для {hour:02d}:00...")
    start_time = time.time()
    
    async with AsyncYandexGPTMonitor() as monitor:
        async with aiohttp.ClientSession() as telegram_session:
            # Получаем новость
            news_content = await monitor.search_ai_news(hour)
            
            if news_content:
                # ОЧИЩАЕМ текст - убираем всё перед 🚀 и после хештегов
                lines = news_content.split('\n')
                cleaned_content = []
                start_adding = False
                stop_adding = False
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Начинаем добавлять с заголовка 🚀
                    if line.startswith('🚀'):
                        start_adding = True
                    
                    if start_adding and not stop_adding:
                        if line.startswith('🔖') or line.startswith('#'):
                            cleaned_content.append(line)
                            stop_adding = True  # Стоп после хештегов
                        else:
                            cleaned_content.append(line)
                
                cleaned_text = '\n'.join(cleaned_content)
                
                # Форматируем финальное сообщение (БЕЗ верхних двух строк)
                telegram_message = f"{cleaned_text}"
                
                if await send_to_telegram_async(telegram_message, telegram_session):
                    execution_time = time.time() - start_time
                    logger.info(f"🎉 Новость для {hour:02d}:00 опубликована! ({execution_time:.1f} сек)")
                    
                    # Сохраняем лог
                    log_entry = f"{datetime.now()}: {hour:02d}:00 - {execution_time:.1f} сек, ~{monitor.token_usage} токенов\n"
                    with open("news_log.txt", "a", encoding="utf-8") as f:
                        f.write(log_entry)
                else:
                    logger.error(f"❌ Ошибка публикации для {hour:02d}:00")
            else:
                logger.error(f"❌ Не удалось получить новость для {hour:02d}:00")

async def main():
    """Основная асинхронная функция"""
    logger.info("🚀 Запуск асинхронного AI News Monitor")
    logger.info("⏰ Расписание: 6:00-18:00 МСК (12 публикаций в день)")
    logger.info("💳 Баланс: 3,980 руб • Срок: 4-5 месяцев")
    logger.info("📊 GitHub Actions: 60 мин/день • 1800 мин/мес (в пределах лимита 2000 мин)")
    
    # Определяем текущий час по МСК
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    current_hour = msk_time.hour
    
    # Публикуем только в рабочие часы 6-18
    if 6 <= current_hour <= 18:
        await publish_hourly_news(current_hour)
    else:
        logger.info(f"⏸️ Вне рабочего времени ({current_hour:02d}:00). Ожидаем 6:00 МСК")

if __name__ == "__main__":
    # Проверка переменных
    required_vars = {
        'YANDEX_API_KEY': YANDEX_API_KEY,
        'YANDEX_FOLDER_ID': YANDEX_FOLDER_ID,
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'TELEGRAM_CHANNEL_ID': TELEGRAM_CHANNEL_ID
    }
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logger.error(f"❌ Отсутствуют переменные: {', '.join(missing_vars)}")
        exit(1)
    
    # Запуск асинхронного приложения
    asyncio.run(main())
