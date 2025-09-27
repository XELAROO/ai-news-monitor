import os
import aiohttp
import asyncio
import json
import re
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
        
        # Доверенные домены для проверки достоверности
        self.trusted_domains = [
            # Официальные блоги компаний
            'blog.google', 'blogs.microsoft.com', 'openai.com/blog', 
            'ai.meta.com', 'x.ai', 'anthropic.com', 'developer.apple.com',
            'aws.amazon.com', 'blogs.nvidia.com', 'tesla.com',
            'yandex.ru/blog', 'deepseek.com',
            
            # Авторитетные издания
            'techcrunch.com', 'theverge.com', 'wired.com', 'arstechnica.com',
            'reuters.com', 'bloomberg.com', 'cnbc.com', 'venturebeat.com',
            
            # Научные источники
            'arxiv.org', 'nature.com', 'science.org'
        ]
        
        # Индикаторы сомнительного контента
        self.suspicious_indicators = [
            'слухи', 'утечки', 'инсайдеры', 'неподтвержденно',
            'возможно', 'вероятно', 'предположительно', 'сообщают',
            'революция', 'прорыв века', 'изменит всё', 'кардинально'
        ]

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def validate_news_source(self, news_content):
        """Проверка достоверности источника новости"""
        if not news_content:
            return "empty"
            
        # Проверка домена в ссылке
        url_match = re.search(r'🔗\s*(http[^\s]+)', news_content)
        if url_match:
            url = url_match.group(1)
            if any(domain in url for domain in self.trusted_domains):
                return "trusted"
            else:
                return "unverified"
        
        # Проверка на спекулятивные формулировки
        content_lower = news_content.lower()
        if any(indicator in content_lower for indicator in self.suspicious_indicators):
            return "suspicious"
            
        return "unknown"

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
                        "text": """Ты - профессиональный редактор новостного канала об ИИ. 
                        Соблюдай строгие критерии достоверности:
                        - Приоритет официальным источникам и авторитетным изданиям
                        - Избегай слухов, утечек и неподтвержденной информации
                        - Конкретные факты важнее общих фраз
                        - Если нет достоверных новостей - лучше сообщи об их отсутствии"""
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
        """Поиск новостей с проверкой достоверности"""
        time_contexts = {
            7: "утренние", 8: "утренние", 9: "утренние",
            10: "дневные", 11: "дневные", 12: "обеденные",
            13: "дневные", 14: "дневные", 15: "дневные",
            16: "вечерние", 17: "вечерние", 18: "вечерние", 19: "поздние вечерние"
        }
        
        context = time_contexts.get(hour, "текущие")
        
        prompt = f"""
        Найди САМУЮ интересную и ДОСТОВЕРНУЮ новость за последние 24 часа в сфере ИИ.
        Сейчас {hour:02d}:00 МСК ({context} часы).
        
        КРИТЕРИИ ДОСТОВЕРНОСТИ (ОБЯЗАТЕЛЬНО):
        
        ✅ **ВЫСОКИЙ ПРИОРИТЕТ - официальные источники:**
        - Каналы компаний в X: (Google: https://x.com/Google, Microsoft: https://x.com/Microsoft, OpenAI: https://x.com/OpenAI, Meta: https://x.com/Meta, xAI: https://x.com/xAI, Anthropic: https://x.com/AnthropicAI, Apple: https://x.com/Apple, Amazon: https://x.com/Amazon, NVIDIA: https://x.com/NVIDIA, Tesla: https://x.com/Tesla, DeepSeek: https://x.com/DeepSeekAI, Yandex: https://x.com/Yandex, Midjourney: https://x.com/Midjourney, Stability AI: https://x.com/StabilityAI, Hugging Face: https://x.com/HuggingFace)
        - Блоги компаний: blog.google, blogs.microsoft.com, openai.com/blog, ai.meta.com
        - Авторитетные издания: TechCrunch, The Verge, Reuters, Bloomberg
        - Научные публикации: arXiv, Nature, Science
        
        ⚠️ **ПРОВЕРЯТЬ КРИТИЧЕСКИ:**
        - Соцсети (кроме официальных аккаунтов)
        - Малые блоги без репутации
        - Новости без четких источников
        
        ❌ **ИЗБЕГАТЬ:**
        - Слухи, утечки, неподтвержденная информация
        - Преувеличенные заголовки ("революция", "прорыв века")
        - Новости без конкретных деталей и цифр
        
        Критерии отбора по компаниям (приоритет):
        1. OpenAI, Google, Microsoft, Meta, xAI, Anthropic
        2. Apple, Amazon, NVIDIA, Tesla, DeepSeek
        3. Yandex, Midjourney, Stability AI, Hugging Face
        
        ТРЕБОВАНИЯ К КАЧЕСТВУ НОВОСТИ:
        - ✅ Конкретные факты: даты, версии продуктов, цифры, имена моделей
        - ✅ Прямые ссылки на официальные источники
        - ✅ Технические детали вместо общих фраз
        - ✅ Практическая значимость для отрасли
        
        ЕСЛИ НЕТ ДОСТОВЕРНЫХ НОВОСТЕЙ - лучше верни сообщение о том, что значимых новостей нет.
        
        Формат ответа (соблюдай точно!):
        
        🚀 [Заголовок с указанием компании и конкретных деталей]\n\n
        
        📝 [3-4 предложения с КОНКРЕТНЫМИ фактами. Пример: "Google представила Gemini 2.0 с 512K контекстом, доступную с 15 января"]\n\n
        
        💡 [Практическое значение: 1-2 предложения]\n\n
        
        🔗 [Ссылка на ПРЯМОЙ ИСТОЧНИК]\n\n
        
        🔖 [3-5 релевантных хештегов]
        
        ВАЖНО: 
        - Добавляй пустую строку между каждым блоком!
        - Ничего не пиши перед 🚀 и после 🔖!
        - Приоритет достоверности над сенсационностью!
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

async def send_no_news_message(hour, session, reason="нет достоверных новостей"):
    """Отправка сообщения об отсутствии новостей"""
    no_news_message = f"""
🚀 AI News Monitor • {hour:02d}:00 МСК

📝 За последние 2 часа не найдено значимых новостей от отслеживаемых компаний.

💡 Система отдает приоритет достоверным источникам и официальным анонсам.

🔖 #ИИ #Новости #Мониторинг
    """
    
    return await send_to_telegram_async(no_news_message, session)

async def publish_hourly_news(hour):
    """Публикация новости с проверкой достоверности"""
    start_time = time.time()
    
    try:
        async with AsyncYandexGPTMonitor() as monitor:
            async with aiohttp.ClientSession() as telegram_session:
                news_content = await monitor.search_ai_news(hour)
                
                if news_content:
                    # Проверяем достоверность источника
                    source_quality = monitor.validate_news_source(news_content)
                    
                    if source_quality == "suspicious":
                        logger.warning(f"❌ {hour:02d}:00 - Новость помечена как сомнительная")
                        await send_no_news_message(hour, telegram_session, "сомнительный источник")
                        return False
                    elif "нет новостей" in news_content.lower() or "нет достоверных" in news_content.lower():
                        logger.info(f"ℹ️ {hour:02d}:00 - YandexGPT сообщает об отсутствии новостей")
                        await send_no_news_message(hour, telegram_session)
                        return True
                    
                    # Очищаем и форматируем текст
                    lines = news_content.split('\n')
                    cleaned_content = []
                    start_adding = False
                    
                    for i, line in enumerate(lines):
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith('🚀'):
                            start_adding = True
                        
                        if start_adding:
                            cleaned_content.append(line)
                            if line.startswith('🔖'):
                                break
                    
                    telegram_message = '\n'.join(cleaned_content)
                    
                    # Добавляем пометку о качестве источника
                    quality_emoji = "✅" if source_quality == "trusted" else "⚠️"
                    source_note = f"\n\n<em>{quality_emoji} Источник: {source_quality}</em>"
                    telegram_message += source_note
                    
                    if await send_to_telegram_async(telegram_message, telegram_session):
                        execution_time = time.time() - start_time
                        logger.info(f"✅ {hour:02d}:00 - Опубликовано ({execution_time:.1f}сек, {source_quality})")
                        return True
                    else:
                        logger.error(f"❌ {hour:02d}:00 - Ошибка отправки в Telegram")
                        return False
                else:
                    logger.error(f"❌ {hour:02d}:00 - Не удалось получить новость")
                    await send_no_news_message(hour, telegram_session, "ошибка получения")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ {hour:02d}:00 - Критическая ошибка: {e}")
        return False

async def main():
    """Основная функция"""
    # Текущее время по МСК
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    current_hour = msk_time.hour
    
    logger.info("=" * 50)
    logger.info("🚀 AI News Monitor - С проверкой достоверности")
    logger.info(f"⏰ Текущее время: {msk_time.strftime('%H:%M')} МСК")
    logger.info(f"📅 Публикации: {len(PUBLICATION_HOURS)} раз/день (07:00-19:00)")
    logger.info("🛡️ Режим: Приоритет достоверным источникам")
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
