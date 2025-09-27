import os
import aiohttp
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import List, Dict

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

# Круглосуточный режим - публикация каждый час
PUBLICATION_HOURS = list(range(24))  # 0-23 часа

class CompanyRotationManager:
    """Менеджер ротации компаний для круглосуточного режима"""
    
    def __init__(self):
        # Группировка компаний по уровню активности и времени суток
        self.companies_night = [  # 00-06 МСК - международные компании (активны в США)
            "OpenAI", "Anthropic", "Google", "Microsoft", "xAI", "Meta",
            "Apple", "Amazon", "NVIDIA", "Tesla"
        ]
        
        self.companies_morning = [  # 07-11 МСК - все компании
            "OpenAI", "Google", "Microsoft", "Meta", "xAI", "Anthropic",
            "Apple", "Amazon", "NVIDIA", "Tesla", "DeepSeek",
            "Yandex", "Midjourney", "Stability AI", "Hugging Face"
        ]
        
        self.companies_day = [  # 12-17 МСК - все компании
            "OpenAI", "Google", "Microsoft", "Meta", "xAI", "Anthropic", 
            "Apple", "Amazon", "NVIDIA", "Tesla", "DeepSeek",
            "Yandex", "Midjourney", "Stability AI", "Hugging Face"
        ]
        
        self.companies_evening = [  # 18-23 МСК - международные + российские
            "OpenAI", "Google", "Microsoft", "Meta", "xAI", "Anthropic",
            "Apple", "Amazon", "NVIDIA", "Tesla", "DeepSeek", "Yandex"
        ]
        
        self.all_companies = list(set(
            self.companies_night + self.companies_morning + 
            self.companies_day + self.companies_evening
        ))
        
        self.current_index = 0
        self.last_rotation_date = None
        
    def get_company_for_hour(self, hour: int) -> str:
        """Выбор компании для текущего часа с учетом времени суток"""
        today = datetime.now().date()
        
        # Сбрасываем индекс если сменился день
        if self.last_rotation_date != today:
            self.current_index = 0
            self.last_rotation_date = today
        
        # Выбор пула компаний в зависимости от времени суток
        if 0 <= hour <= 6:    # Ночь (00-06 МСК)
            companies_pool = self.companies_night
            time_slot = "ночь"
        elif 7 <= hour <= 11: # Утро (07-11 МСК)  
            companies_pool = self.companies_morning
            time_slot = "утро"
        elif 12 <= hour <= 17: # День (12-17 МСК)
            companies_pool = self.companies_day
            time_slot = "день"
        else:                 # Вечер (18-23 МСК)
            companies_pool = self.companies_evening
            time_slot = "вечер"
        
        # Циклическая ротация внутри выбранного пула
        company = companies_pool[self.current_index % len(companies_pool)]
        self.current_index += 1
        
        logger.info(f"🏢 Ротация: {hour:02d}:00 МСК ({time_slot}) -> {company}")
        return company
    
    def get_company_sources(self, company: str) -> Dict[str, str]:
        """Получение источников для конкретной компании"""
        sources_map = {
            "OpenAI": {
                "x": "https://x.com/OpenAI",
                "blog": "openai.com/blog",
                "official": "OpenAI официальный канал"
            },
            "Google": {
                "x": "https://x.com/Google", 
                "blog": "blog.google",
                "official": "Google AI блог"
            },
            "Microsoft": {
                "x": "https://x.com/Microsoft",
                "blog": "blogs.microsoft.com/ai",
                "official": "Microsoft AI блог"
            },
            "Meta": {
                "x": "https://x.com/Meta",
                "blog": "ai.meta.com",
                "official": "Meta AI блог"
            },
            "xAI": {
                "x": "https://x.com/xAI",
                "blog": "x.ai/blog",
                "official": "xAI официальный канал"
            },
            "Anthropic": {
                "x": "https://x.com/AnthropicAI", 
                "blog": "anthropic.com/news",
                "official": "Anthropic блог"
            },
            "Apple": {
                "x": "https://x.com/Apple",
                "blog": "developer.apple.com/machine-learning",
                "official": "Apple Machine Learning"
            },
            "Amazon": {
                "x": "https://x.com/Amazon",
                "blog": "aws.amazon.com/blogs/machine-learning",
                "official": "AWS AI блог"
            },
            "NVIDIA": {
                "x": "https://x.com/NVIDIA", 
                "blog": "blogs.nvidia.com",
                "official": "NVIDIA AI блог"
            },
            "Tesla": {
                "x": "https://x.com/Tesla",
                "blog": "tesla.com/AI",
                "official": "Tesla AI"
            },
            "DeepSeek": {
                "x": "https://x.com/DeepSeekAI",
                "blog": "deepseek.com",
                "official": "DeepSeek официальный"
            },
            "Yandex": {
                "x": "https://x.com/Yandex",
                "blog": "yandex.ru/blog/company/ai",
                "official": "Yandex AI блог"
            },
            "Midjourney": {
                "x": "https://x.com/Midjourney",
                "blog": "midjourney.com/news",
                "official": "Midjourney официальный"
            },
            "Stability AI": {
                "x": "https://x.com/StabilityAI", 
                "blog": "stability.ai/news",
                "official": "Stability AI блог"
            },
            "Hugging Face": {
                "x": "https://x.com/HuggingFace",
                "blog": "huggingface.co/blog",
                "official": "Hugging Face блог"
            }
        }
        
        return sources_map.get(company, {
            "x": f"https://x.com/search?q={company} AI",
            "blog": f"Поиск новостей {company}",
            "official": f"{company} официальные источники"
        })

class AsyncYandexGPTMonitor:
    def __init__(self):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        self.session = None
        self.token_usage = 0
        self.company_manager = CompanyRotationManager()
        
        # Доверенные домены для проверки достоверности
        self.trusted_domains = [
            'blog.google', 'blogs.microsoft.com', 'openai.com/blog', 
            'ai.meta.com', 'x.ai', 'anthropic.com', 'developer.apple.com',
            'aws.amazon.com', 'blogs.nvidia.com', 'tesla.com',
            'yandex.ru/blog', 'deepseek.com', 'midjourney.com',
            'stability.ai', 'huggingface.co',
            'techcrunch.com', 'theverge.com', 'wired.com', 'arstechnica.com',
            'reuters.com', 'bloomberg.com', 'cnbc.com', 'venturebeat.com',
            'arxiv.org', 'nature.com', 'science.org'
        ]

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

    async def search_ai_news(self, hour: int):
        """Поиск новостей с ротацией компаний"""
        target_company = self.company_manager.get_company_for_hour(hour)
        company_sources = self.company_manager.get_company_sources(target_company)
        
        # Контекст времени суток для промпта
        time_contexts = {
            **{h: "ночные" for h in range(0, 7)},
            **{h: "утренние" for h in range(7, 12)},
            **{h: "дневные" for h in range(12, 18)},
            **{h: "вечерние" for h in range(18, 24)}
        }
        
        context = time_contexts.get(hour, "текущие")
        
        prompt = f"""
        Найди САМУЮ интересную и ДОСТОВЕРНУЮ новость за последние 24 часа от компании {target_company}.
        Сейчас {hour:02d}:00 МСК ({context} часы).
        
        КОНКРЕТНЫЕ ИСТОЧНИКИ ДЛЯ {target_company.upper()}:
        - Официальный X (Twitter): {company_sources['x']}
        - Официальный блог: {company_sources['blog']}
        - Другие официальные каналы: {company_sources['official']}
        
        УЧТИ ВРЕМЯ СУТОК:
        - {hour:02d}:00 МСК соответствует разному времени в других часовых поясах
        - Новости могут появляться из США, Европы или Азии
        - Проверяй актуальность с учетом временных зон
        
        КРИТЕРИИ ДОСТОВЕРНОСТИ:
        ✅ **ВЫСОКИЙ ПРИОРИТЕТ:** Официальные анонсы, блог компании, пресс-релизы
        ✅ **ДОПУСТИМО:** Авторитетные издания (если цитируют официальные источники)
        ❌ **ИЗБЕГАТЬ:** Слухи, неподтвержденные утечки, соцсети (кроме официальных)
        
        ЕСЛИ НЕТ НОВОСТЕЙ ОТ {target_company.upper()}:
        - Можно найти новость о значимом партнерстве с участием {target_company}
        - Или важную новость от другой крупной ИИ-компании
        - Но в приоритете именно {target_company}
        
        Формат ответа (соблюдай точно!):
        
        🚀 {target_company}: [Конкретный заголовок с деталями]\n\n
        
        📝 [3-4 предложения с КОНКРЕТНЫМИ фактами о {target_company}]\n\n
        
        💡 [Практическое значение: 1-2 предложения]\n\n
        
        🔗 [Ссылка на ПРЯМОЙ ИСТОЧНИК от {target_company}]\n\n
        
        🔖 #{target_company.replace(' ', '')} #ИИ #НовостиИИ [еще 1-2 релевантных хештега]
        
        ВАЖНО: Приоритет достоверности над сенсационностью!
        """
        
        news_content = await self.yandex_gpt_call(prompt)
        return news_content, target_company

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

async def send_no_news_message(hour, session, company=None):
    """Отправка сообщения об отсутствии новостей"""
    if company:
        message = f"""
🚀 AI News Monitor • {hour:02d}:00 МСК

📝 За последние 24 часа не найдено значимых новостей от {company}.

💡 Следующий запрос в {(hour + 1) % 24:02d}:00 МСК будет о другой компании.

🔖 #{company.replace(' ', '')} #ИИ #Новости #Мониторинг
        """
    else:
        message = f"""
🚀 AI News Monitor • {hour:02d}:00 МСК

📝 За последние 2 часа не найдено значимых новостей.

💡 Система продолжает круглосуточный мониторинг.

🔖 #ИИ #Новости #Мониторинг
        """
    
    return await send_to_telegram_async(message, session)

async def publish_hourly_news(hour):
    """Публикация новости с ротацией компаний"""
    start_time = time.time()
    
    try:
        async with AsyncYandexGPTMonitor() as monitor:
            async with aiohttp.ClientSession() as telegram_session:
                news_content, target_company = await monitor.search_ai_news(hour)
                
                if news_content:
                    # Проверяем наличие ключевых фраз об отсутствии новостей
                    no_news_phrases = [
                        "нет новостей", "нет достоверных", "не найдено новостей",
                        "новостей нет", "пока нет новостей", "no news", "nothing found"
                    ]
                    
                    if any(phrase in news_content.lower() for phrase in no_news_phrases):
                        logger.info(f"ℹ️ {hour:02d}:00 - Нет новостей от {target_company}")
                        await send_no_news_message(hour, telegram_session, target_company)
                        return True
                    
                    # Очищаем и форматируем текст
                    lines = news_content.split('\n')
                    cleaned_content = []
                    start_adding = False
                    
                    for line in lines:
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
                    
                    # Добавляем пометку о времени и компании
                    time_note = f"\n\n<em>🕐 {hour:02d}:00 МСК • 🏢 {target_company}</em>"
                    telegram_message += time_note
                    
                    if await send_to_telegram_async(telegram_message, telegram_session):
                        execution_time = time.time() - start_time
                        logger.info(f"✅ {hour:02d}:00 - Опубликовано о {target_company} ({execution_time:.1f}сек)")
                        return True
                    else:
                        logger.error(f"❌ {hour:02d}:00 - Ошибка отправки в Telegram")
                        return False
                else:
                    logger.error(f"❌ {hour:02d}:00 - Не удалось получить новость о {target_company}")
                    await send_no_news_message(hour, telegram_session, target_company)
                    return False
                    
    except Exception as e:
        logger.error(f"❌ {hour:02d}:00 - Критическая ошибка: {e}")
        return False

async def main():
    """Основная функция"""
    # Текущее время по МСК
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    current_hour = msk_time.hour
    
    logger.info("=" * 60)
    logger.info("🚀 AI News Monitor - Круглосуточный режим 24/7")
    logger.info(f"⏰ Текущее время: {msk_time.strftime('%H:%M')} МСК")
    logger.info(f"📅 Режим: публикация каждый час")
    logger.info("=" * 60)
    
    # Всегда публикуем (каждый час)
    logger.info(f"🎯 Публикуем новость для {current_hour:02d}:00")
    success = await publish_hourly_news(current_hour)
    
    if success:
        logger.info(f"🎉 Успешно завершено для {current_hour:02d}:00")
    else:
        logger.warning(f"⚠️ Завершено с ошибками для {current_hour:02d}:00")

if __name__ == "__main__":
    # Проверка переменных
    if not all([YANDEX_API_KEY, YANDEX_FOLDER_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        logger.error("❌ Отсутствуют необходимые переменные окружения")
        exit(1)
    
    # Запуск
    asyncio.run(main())
