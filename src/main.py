import os
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
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
        self.token_usage = 0  # Счетчик токенов для мониторинга затрат

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
                        
                        # Примерный подсчет токенов (1 токен ≈ 4 символа на русском)
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
        # Разные промпты для разного времени суток
        time_contexts = {
            6: "утренние",
            7: "утренние", 
            8: "утренние",
            9: "дневные",
            10: "дневные",
            11: "дневные", 
            12: "обеденные",
            13: "дневные",
            14: "дневные",
            15: "дневные",
            16: "вечерние",
            17: "вечерние",
            18: "вечерние"
        }
        
        context = time_contexts.get(hour, "последние")
        
        prompt = f"""
        Найди САМУЮ интересную новость за последние 1-2 часа в сфере искусственного интеллекта.
        Время суток: {context}.
        
        Критерии:
        - Новости от Google, Microsoft, OpenAI, Meta, Yandex, Apple, Amazon, DeepSeek
        - Технические прорывы, крупные обновления, исследования
        - Практическая значимость
        
        Формат для Telegram:
        
        🕐 {hour:02d}:00 • {context.capitalize()} обновление
        
        🚀 [Заголовок с эмодзи]
        
        📝 [Суть новости: 3-4 предложения. Будь конкретным!]
        
        💡 [Значение для отрасли: 1-2 предложения]
        
        🔗 [Ссылка на источник]
        
        🔖 [3-5 хештегов]
        
        Будь кратким и информативным!
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
            "disable_web_page_preview": False
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
    
    async with AsyncYandexGPTMonitor() as monitor:
        async with aiohttp.ClientSession() as telegram_session:
            # Получаем новость
            news_content = await monitor.search_ai_news(hour)
            
            if news_content:
                # Форматируем сообщение
                telegram_message = f"""
🤖 <b>СВЕЖАЯ НОВОСТЬ ИИ</b> • {hour:02d}:00 МСК

{news_content}

<em>💎 Асинхронный режим • YandexGPT 5.1 Pro</em>
<em>💳 Токены использовано: ~{monitor.token_usage}</em>
                """
                
                if await send_to_telegram_async(telegram_message, telegram_session):
                    logger.info(f"🎉 Новость для {hour:02d}:00 опубликована!")
                    
                    # Сохраняем лог
                    log_entry = f"{datetime.now()}: {hour:02d}:00 - Успех (~{monitor.token_usage} токенов)\n"
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
    logger.info(f"💳 Баланс: 3,980 руб • Расчетный срок: 4-5 месяцев")
    
    # Определяем текущий час по МСК
    from datetime import timezone
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
