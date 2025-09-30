import os
import aiohttp
import asyncio
import json
import glob
import logging
import time
import base64
import hashlib
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
    
    def get_oldest_unsent_news(self):
        """Находит самую СТАРУЮ непрочитанную новость (снизу файлов)"""
        news_files = glob.glob(self.files_pattern)
        if not news_files:
            logger.info("📭 Файлы с новостями не найдены")
            return None
        
        # Сортируем файлы по дате создания (самый старый первый)
        news_files.sort(key=os.path.getctime)
        logger.info(f"📁 Найдено файлов: {len(news_files)}")
        
        # ОТЛАДКА: показываем очередь
        logger.info("📋 ОЧЕРЕДЬ ОБРАБОТКИ (старые файлы первыми):")
        for i, filepath in enumerate(news_files):
            file_time = datetime.fromtimestamp(os.path.getctime(filepath))
            logger.info(f"   {i+1}. {os.path.basename(filepath)} ({file_time.strftime('%d.%m %H:%M')})")
        
        for filepath in news_files:
            news_lines = self.parse_news_file(filepath)
            logger.info(f"📖 Чтение файла {os.path.basename(filepath)}: {len(news_lines)} новостей")
            
            if not news_lines:
                continue
                
            # Ищем непрочитанные новости в ОБРАТНОМ порядке (снизу файла)
            for i, news_line in enumerate(reversed(news_lines)):
                position_in_file = len(news_lines) - i  # Позиция снизу
                news_hash = hashlib.md5(news_line.encode('utf-8')).hexdigest()
                
                if news_hash not in self.sent_news:
                    title = news_line.split('|')[0].strip() if '|' in news_line else news_line[:50]
                    logger.info(f"🎯 НАЙДЕНА СЛЕДУЮЩАЯ НОВОСТЬ:")
                    logger.info(f"   Файл: {os.path.basename(filepath)}")
                    logger.info(f"   Позиция в файле: {position_in_file}/{len(news_lines)} (снизу)")
                    logger.info(f"   Заголовок: {title}")
                    return news_line, news_hash, filepath
                else:
                    logger.debug(f"   ✓ Уже отправлена: {news_line[:50]}...")
                            
            logger.info(f"   ✅ Все новости в файле уже отправлены")
        
        logger.info("✅ Все новости во всех файлах уже отправлены")
        return None

    def show_next_news(self):
        """Показывает какая новость будет следующей без отправки"""
        news_data = self.get_oldest_unsent_news()
        if news_data:
            news_line, news_hash, filepath = news_data
            title = news_line.split('|')[0].strip() if '|' in news_line else news_line
            print("🎯 СЛЕДУЮЩАЯ НОВОСТЬ ДЛЯ ОТПРАВКИ:")
            print(f"📁 Файл: {os.path.basename(filepath)}")
            print(f"📰 Заголовок: {title}")
            if '|' in news_line:
                url = news_line.split('|')[1].strip()
                print(f"🔗 URL: {url}")
            return True
        else:
            print("✅ Все новости отправлены")
            return False
    
    def mark_news_sent_and_cleanup(self, news_hash, news_line, filepath):
        """Помечает новость как отправленную и чистит файлы"""
        # Помечаем новость как отправленную
        self.sent_news.add(news_hash)
        self.save_sent_news()
        logger.info(f"✅ Новость помечена как отправленная: {news_line[:50]}...")
        
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
        """Упрощенное удаление блока новости из Forbes формата"""
        if '|' not in news_line_to_remove:
            return content
            
        # Извлекаем заголовок из news_line (формат: "заголовок | url")
        title_to_remove = news_line_to_remove.split('|')[0].strip()
        
        # Простой поиск по заголовку (без сложных сравнений URL)
        blocks = content.split('--------------------------------------------------')
        updated_blocks = []
        removed_count = 0
        
        for block in blocks:
            if 'TITLE:' in block and title_to_remove in block:
                logger.info(f"🗑️ Удаляю блок с заголовком: {title_to_remove}")
                removed_count += 1
                continue  # Пропускаем этот блок
            updated_blocks.append(block)
        
        logger.info(f"📊 Удалено блоков: {removed_count}")
        
        if removed_count == 0:
            logger.warning(f"⚠️ Не найден блок для удаления: {title_to_remove}")
        
        # Обновляем счетчик New articles
        result_content = '--------------------------------------------------'.join(updated_blocks)
        result_content = self.update_articles_count(result_content, removed_count)
        
        return result_content

    def update_articles_count(self, content, removed_count=1):
        """Обновляет счетчик New articles в Forbes формате"""
        try:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('New articles:'):
                    # Извлекаем текущее количество
                    current_count = int(line.split(':')[1].strip())
                    new_count = max(0, current_count - removed_count)
                    lines[i] = f"New articles: {new_count}"
                    logger.info(f"📊 Обновлен счетчик: {current_count} -> {new_count}")
                    break
            
            return '\n'.join(lines)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления счетчика: {e}")
            return content
    
    def remove_empty_file(self, filepath):
        """Удаляет файл если в нем нет новостей"""
        try:
            if not os.path.exists(filepath):
                return
                
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, есть ли в файле реальные новости
            if self.file_has_news(content):
                logger.info(f"📄 В файле {os.path.basename(filepath)} еще есть новости")
                return
            
            # Если новостей нет - удаляем файл
            os.remove(filepath)
            logger.info(f"🗑️ Удален пустой файл {os.path.basename(filepath)}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки файла {filepath}: {e}")

    def file_has_news(self, content):
        """Проверяет, есть ли в содержимом файла новости"""
        # Если это Forbes формат
        if 'FORBES AI - GITHUB PARSER' in content:
            # Проверяем, есть ли блоки с новостями (с TITLE и LINK)
            blocks = content.split('--------------------------------------------------')
            news_blocks = 0
            
            for block in blocks:
                if 'TITLE:' in block and 'LINK:' in block:
                    # Проверяем, что это реальная новость, а не заголовок
                    lines = block.strip().split('\n')
                    has_title = any('TITLE:' in line and len(line.replace('TITLE:', '').strip()) > 0 for line in lines)
                    has_link = any('LINK:' in line and len(line.replace('LINK:', '').strip()) > 0 for line in lines)
                    
                    if has_title and has_link:
                        news_blocks += 1
            
            logger.info(f"📊 В файле найдено блоков с новостей: {news_blocks}")
            return news_blocks > 0
        
        else:
            # Простой формат - проверяем наличие строк с разделителем |
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            news_lines = [line for line in lines if '|' in line]
            return len(news_lines) > 0

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

class AsyncYandexArtGenerator:
    def __init__(self):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
        self.headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_image(self, prompt):
        """Генерация изображения через Yandex ART"""
        try:
            data = {
                "modelUri": f"art://{YANDEX_FOLDER_ID}/yandex-art/latest",
                "generationOptions": {
                    "seed": int(time.time()) % 1000000
                },
                "messages": [
                    {
                        "weight": 1,
                        "text": prompt
                    }
                ]
            }

            logger.info(f"🎨 Запрос генерации изображения: {prompt}")
            
            # 1. Запуск генерации
            async with self.session.post(
                self.api_url, 
                headers=self.headers, 
                json=data, 
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    if 'id' in result:
                        task_id = result['id']
                        logger.info(f"🔄 Задача генерации создана: {task_id}")
                        
                        # 2. Ожидание завершения генерации
                        image_bytes = await self._wait_for_generation(task_id)
                        return image_bytes
                    else:
                        logger.error("❌ Неверный формат ответа генерации")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка API генерации: {response.status} - {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("❌ Таймаут генерации изображения (120 сек)")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}")
            return None

    async def _wait_for_generation(self, task_id, max_attempts=30, delay=5):
        """Ожидание завершения генерации изображения"""
        check_url = f"https://llm.api.cloud.yandex.net/operations/{task_id}"
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"⏳ Проверка генерации ({attempt + 1}/{max_attempts})...")
                
                async with self.session.get(
                    check_url, 
                    headers=self.headers, 
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        if result.get('done', False):
                            if 'response' in result:
                                # Декодируем base64 изображение
                                image_base64 = result['response']['image']
                                image_bytes = base64.b64decode(image_base64)
                                logger.info(f"✅ Изображение сгенерировано ({len(image_bytes)} байт)")
                                return image_bytes
                            else:
                                logger.error("❌ Ошибка в ответе генерации")
                                return None
                        else:
                            # Генерация еще не завершена
                            await asyncio.sleep(delay)
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка проверки генерации: {response.status}")
                        await asyncio.sleep(delay)
                        
            except Exception as e:
                logger.error(f"❌ Ошибка при проверке генерации: {e}")
                await asyncio.sleep(delay)
        
        logger.error("❌ Превышено время ожидания генерации")
        return None

async def send_photo_to_telegram(image_bytes, caption, session):
    """Асинхронная отправка фото в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        
        form_data = aiohttp.FormData()
        form_data.add_field('chat_id', TELEGRAM_CHANNEL_ID)
        form_data.add_field('photo', image_bytes, filename='news_image.jpg')
        form_data.add_field('caption', caption)
        form_data.add_field('parse_mode', 'HTML')
        
        async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                logger.info("✅ Фото отправлено в Telegram")
                return True
            else:
                error_text = await response.text()
                logger.error(f"❌ Ошибка отправки фото: {response.status} - {error_text}")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")
        return False

def remove_url_from_text(text):
    """Удаляет строку с ссылкой из текста"""
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if not line.strip().startswith('🔗'):
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

def extract_prompt_from_summary(summarized_news):
    """Извлекает заголовок для промпта генерации изображения"""
    lines = summarized_news.split('\n')
    for line in lines:
        if line.startswith('🚀'):
            # Берем заголовок без эмодзи и ограничиваем длину
            title = line.replace('🚀', '').strip()
            # Создаем промпт на английском для лучшей генерации
            prompt = f"News illustration: {title}, digital art, modern style, professional news image"
            return prompt[:200]  # Ограничиваем длину промпта
    return "Breaking news, digital art, modern style"

async def process_news_for_telegram():
    """Основная функция обработки новостей с генерацией изображения"""
    news_manager = ExistingFilesNewsManager("results/github_*.txt")
    
    # Получаем самую старую непрочитанную новость
    news_data = news_manager.get_oldest_unsent_news()
    
    if not news_data:
        logger.info("ℹ️ Нет новых новостей - пропускаем отправку")
        return True
    
    news_line, news_hash, filepath = news_data
    
    # Проверяем, не отправляли ли мы уже эту новость
    if news_hash in news_manager.sent_news:
        logger.warning(f"⚠️ Новость уже была отправлена, но все еще в файле: {news_line[:50]}...")
        news_manager.mark_news_sent_and_cleanup(news_hash, news_line, filepath)
        return True
    
    # Парсим новость
    if '|' in news_line:
        title, url = [part.strip() for part in news_line.split('|', 1)]
    else:
        title, url = news_line, ""

    logger.info(f"📨 Подготовка к отправке: {title}")

    # Создаем промпт для YandexGPT БЕЗ ссылки в формате
    prompt = f"""
ЗАДАЧА: Перевести на русский и создать краткий пересказ новости: {url}

ТРЕБОВАНИЯ К ФОРМАТУ БЛОКОВ:
1. Заголовок: краткий, привлекающий внимание
2. Текст: 3-5 предложения, только ключевые факты  
3. Вывод: практическая польза/значение
4. Ссылка: оригинальный URL без анкора
5. Хештеги: 3-5 релевантных тегов на русском
- Пустая строка: разделитель блоков 1,2,3,4,5
- Ничего лишнего, кроме указанного

ФОРМАТ БЛОКОВ (СОБЛЮДАЙ ТОЧНО!):

🚀 Переведенный заголовок на русском

📝 3-5 предложения пересказа на русском

💡 1 предложение о практическом значении

🔗 {url}

🔖 #[тематика] #[тематика] #[тематика] #[компания]

МЕЖДУ КАЖДЫМ БЛОКОМ - ПУСТАЯ СТРОКА!
"""
    
    # Получаем текст от YandexGPT
    async with AsyncYandexGPTMonitor() as monitor:
        summarized_news = await monitor.yandex_gpt_call(prompt)
    
    if summarized_news:
        # Удаляем ссылку из текста (если вдруг она есть)
        cleaned_text = remove_url_from_text(summarized_news)
        
        # Генерируем изображение
        image_prompt = extract_prompt_from_summary(cleaned_text)
        async with AsyncYandexArtGenerator() as art_generator:
            image_bytes = await art_generator.generate_image(image_prompt)
        
        # Отправляем в Telegram
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                # Отправляем фото с полным текстом как подписью
                success = await send_photo_to_telegram(image_bytes, cleaned_text, session)
            else:
                # Если изображение не сгенерировалось, отправляем только текст
                logger.warning("⚠️ Изображение не сгенерировано, отправляем только текст")
                success = await send_to_telegram_async(cleaned_text, session)
            
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

async def send_to_telegram_async(message, session):
    """Асинхронная отправка текста в Telegram (fallback)"""
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

async def show_news_queue():
    """Показывает очередь новостей для отправки"""
    news_manager = ExistingFilesNewsManager("results/github_*.txt")
    print("=" * 80)
    print("📋 ТЕКУЩАЯ ОЧЕРЕДЬ ОТПРАВКИ НОВОСТЕЙ")
    print("=" * 80)
    return news_manager.show_next_news()
        
async def main():
    """Основная функция"""
    msk_time = datetime.now(timezone(timedelta(hours=3)))
    
    logger.info("=" * 60)
    logger.info("🚀 AI News Monitor - Обработка новостей с генерацией изображений")
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
    
    # Проверяем аргументы командной строки
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "queue":
        # Показываем только очередь без отправки
        asyncio.run(show_news_queue())
    else:
        # Запуск обычной обработки
        asyncio.run(main())
