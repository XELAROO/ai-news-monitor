import os
import aiohttp
import asyncio
import json
import glob
import logging
import time
from datetime import datetime, timezone, timedelta

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

class ExistingFilesNewsManager:
    def __init__(self, files_pattern="results/github_*.txt", sent_file="sent_news.json"):
        self.files_pattern = files_pattern
        self.sent_file = sent_file
        self.sent_news = self.load_sent_news()
    
    def load_sent_news(self):
        """Загружает отправленные новости"""
        if os.path.exists(self.sent_file):
            try:
                with open(self.sent_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки sent_news.json: {e}")
                return set()
        return set()
    
    def save_sent_news(self):
        """Сохраняет отправленные новости"""
        try:
            with open(self.sent_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.sent_news), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения sent_news.json: {e}")
    
    def parse_news_file(self, filepath):
        """Парсит файл в любом формате (Forbes или простом)"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Если это формат Forbes Parser
            if 'FORBES AI - GITHUB PARSER' in content:
                return self.parse_forbes_format(content)
            else:
                # Простой формат (одна новость на строку)
                return [line.strip() for line in content.split('\n') if line.strip() and '|' in line]
                
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла {filepath}: {e}")
            return []
    
    def parse_forbes_format(self, content):
        """Парсит специфический формат Forbes"""
        news_lines = []
        blocks = content.split('--------------------------------------------------')
        
        for block in blocks:
            if 'TITLE:' in block and 'LINK:' in block:
                lines = block.strip().split('\n')
                title = None
                link = None
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('TITLE:'):
                        title = line.replace('TITLE:', '').strip()
                    elif line.startswith('LINK:'):
                        link = line.replace('LINK:', '').strip()
                
                if title and link:
                    news_lines.append(f"{title} | {link}")
        
        logger.info(f"📰 Распаршено {len(news_lines)} новостей из Forbes формата")
        return news_lines
    
    def get_oldest_unsent_news(self):
        """Находит самую старую непрочитанную новость из всех файлов"""
        # Получаем все файлы по паттерну
        news_files = glob.glob(self.files_pattern)
        if not news_files:
            logger.info("📭 Файлы с новостями не найдены")
            return None
        
        # Сортируем файлы по дате создания (самый старый первый)
        news_files.sort(key=os.path.getctime)
        logger.info(f"📁 Найдено файлов: {len(news_files)}")
        
        for filepath in news_files:
            # Используем новый парсер вместо простого чтения
            news_lines = self.parse_news_file(filepath)
            
            logger.info(f"📖 Чтение файла {os.path.basename(filepath)}: {len(news_lines)} новостей")
            
            for news_line in news_lines:
                # Создаем уникальный идентификатор новости
                news_hash = hash(news_line)
                if news_hash not in self.sent_news:
                    logger.info(f"🎯 Найдена новая новость: {news_line[:50]}...")
                    return news_line, news_hash, filepath
                        
        logger.info("✅ Все новости уже отправлены")
        return None
    
    def mark_news_sent_and_cleanup(self, news_hash, news_line, filepath):
        """Помечает новость как отправленную и чистит файлы"""
        # Помечаем новость как отправленную
        self.sent_news.add(news_hash)
        self.save_sent_news()
        
        # Удаляем отправленную новость из файла
        self.remove_news_from_file(filepath, news_line)
        
        # Удаляем пустой файл если нужно
        self.remove_empty_file(filepath)
    
    def remove_news_from_file(self, filepath, news_line_to_remove):
        """Удаляет конкретную новость из файла"""
        try:
            # Читаем файл с помощью парсера для сохранения формата
            with open(filepath, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Если это Forbes формат, удаляем соответствующий блок
            if 'FORBES AI - GITHUB PARSER' in original_content:
                updated_content = self.remove_forbes_news_block(original_content, news_line_to_remove)
            else:
                # Простой формат - удаляем строку
                lines = original_content.split('\n')
                updated_lines = [line for line in lines if line.strip() != news_line_to_remove]
                updated_content = '\n'.join(updated_lines)
            
            # Перезаписываем файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(updated_content)
                
            logger.info(f"🗑️ Удалена отправленная новость из {os.path.basename(filepath)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления новости из файла: {e}")
    
    def remove_forbes_news_block(self, content, news_line_to_remove):
        """Удаляет блок новости из Forbes формата"""
        if '|' not in news_line_to_remove:
            return content
            
        # Извлекаем заголовок из news_line (формат: "заголовок | url")
        title_to_remove = news_line_to_remove.split('|')[0].strip()
        
        blocks = content.split('--------------------------------------------------')
        updated_blocks = []
        
        for block in blocks:
            if 'TITLE:' in block and title_to_remove in block:
                # Пропускаем блок с удаляемой новостью
                continue
            updated_blocks.append(block)
        
        return '--------------------------------------------------'.join(updated_blocks)
    
    def remove_empty_file(self, filepath):
        """Удаляет файл если он пустой"""
        try:
            if os.path.exists(filepath) and os.path.getsize(filepath) == 0:
                os.remove(filepath)
                logger.info(f"🗑️ Удален пустой файл {os.path.basename(filepath)}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления файла: {e}")

    def parse_forbes_format(self, content):
    """Парсит специфический формат Forbes и очищает URL"""
        news_lines = []
        blocks = content.split('--------------------------------------------------')
    
    for block in blocks:
        if 'TITLE:' in block and 'LINK:' in block:
            lines = block.strip().split('\n')
            title = None
            link = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('TITLE:'):
                    title = line.replace('TITLE:', '').strip()
                elif line.startswith('LINK:'):
                    link = line.replace('LINK:', '').strip()
                    # Очищаем URL от параметров ?ss=ai
                    link = self.clean_forbes_url(link)
            
            if title and link:
                news_lines.append(f"{title} | {link}")
    
    logger.info(f"📰 Распаршено {len(news_lines)} новостей из Forbes формата")
    return news_lines

    def clean_forbes_url(self, url):
        """Очищает Forbes URL от параметров ?ss=ai и других трекеров"""
        try:
            # Удаляем параметры ?ss=ai и другие UTM-метки
            if '?' in url:
                base_url = url.split('?')[0]
                logger.info(f"🔗 Очищен URL: {url} -> {base_url}")
                return base_url
            return url
        except Exception as e:
            logger.error(f"❌ Ошибка очистки URL {url}: {e}")
            return url

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
                        "text": """Ты - профессиональный редактор AI-новостей."""
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
                error_text = await response.text()
                logger.error(f"❌ Ошибка Telegram API: {response.status} - {error_text}")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

async def process_news_for_telegram():
    """Основная функция обработки новостей - ТОЛЬКО если есть новости"""
    news_manager = ExistingFilesNewsManager("results/github_*.txt")
    
    # Получаем самую старую непрочитанную новость
    news_data = news_manager.get_oldest_unsent_news()
    
    if not news_data:
        logger.info("ℹ️ Нет новых новостей - пропускаем отправку")
        return True
    
    news_line, news_hash, filepath = news_data
    
    # Парсим новость (формат: "заголовок | URL")
    if '|' in news_line:
        title, url = [part.strip() for part in news_line.split('|', 1)]
    else:
        title, url = news_line, ""

    # Создаем промпт для YandexGPT с явным указанием форматирования
    prompt = f"""
ЗАДАЧА: Перевести на русский и создать краткий пересказ новости: {url}

ТРЕБОВАНИЯ К ФОРМАТУ БЛОКОВ:
1. Заголовок: краткий, привлекающий внимание
2. Текст: 3-5 предложения, только ключевые факты
3. Вывод: практическая польза/значение
4. Ссылка: оригинальный URL без анкора
5. Хештеги: 3-5 релевантных тегов на русском
- Пустая строка: разделитель болков 1,2,3,4
- Ничего лишнего, кроме указанного

ФОРМАТ БЛОКОВ (СОБЛЮДАЙ ТОЧНО!):

🚀 [Переведенный заголовок на русском]

📝 [3-5 предложения пересказа на русском]

💡 [1 предложение о практическом значении]

🔗 {url}

🔖 #[тематика] #[тематика] #[тематика] #[компания]

МЕЖДУ КАЖДЫМ БЛОКОМ - ПУСТАЯ СТРОКА!
"""
    
    # Отправляем в YandexGPT
    async with AsyncYandexGPTMonitor() as monitor:
        summarized_news = await monitor.yandex_gpt_call(prompt)
    
    if summarized_news:
        # Отправляем в Telegram
        async with aiohttp.ClientSession() as session:
            success = await send_to_telegram_async(summarized_news, session)
            
            if success:
                # Помечаем как отправленную и чистим файлы
                news_manager.mark_news_sent_and_cleanup(news_hash, news_line, filepath)
                logger.info("✅ Новость успешно отправлена и файлы очищены")
                return True
            else:
                logger.error("❌ Ошибка отправки в Telegram")
                return False
    else:
        logger.error("❌ Не удалось обработать новость через YandexGPT")
        return False
        
async def main():
    """Основная функция"""
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    current_hour = msk_time.hour
    
    logger.info("=" * 60)
    logger.info("🚀 AI News Monitor - Обработка новостей из файлов")
    logger.info(f"⏰ Текущее время: {msk_time.strftime('%H:%M')} МСК")
    logger.info("=" * 60)
    
    # Запускаем обработку
    success = await process_news_for_telegram()
    
    if success:
        logger.info("🎉 Скрипт завершил работу")
    else:
        logger.warning("⚠️ Скрипт завершил работу с ошибками")

if __name__ == "__main__":
    # Проверка переменных
    if not all([YANDEX_API_KEY, YANDEX_FOLDER_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        logger.error("❌ Отсутствуют необходимые переменные окружения")
        exit(1)
    
    # Запуск
    asyncio.run(main())
