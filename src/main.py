import os
import requests
import json
import time
from datetime import datetime, timedelta
import schedule
import threading

print("=" * 60)
print("🚀 AI News Monitor с YandexGPT 5.1 Pro")
print("=" * 60)

# Конфигурация
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Проверка конфигурации
print("🔧 Проверка конфигурации:")
print(f"YANDEX_API_KEY: {'***установлен***' if YANDEX_API_KEY else '❌ НЕТ'}")
print(f"YANDEX_FOLDER_ID: {'***установлен***' if YANDEX_FOLDER_ID else '❌ НЕТ'}")
print(f"TELEGRAM_BOT_TOKEN: {'***установлен***' if TELEGRAM_BOT_TOKEN else '❌ НЕТ'}")
print(f"TELEGRAM_CHANNEL_ID: {'***установлен***' if TELEGRAM_CHANNEL_ID else '❌ НЕТ'}")
print("-" * 60)

class YandexGPTMonitor:
    def __init__(self):
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
    def yandex_gpt_call(self, prompt, max_tokens=2000):
        """Вызов YandexGPT API"""
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
                        "text": "Ты - профессиональный редактор новостного канала об искусственном интеллекте. Создавай краткие, информативные и engaging новости на русском языке."
                    },
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }
            
            print(f"🔍 Отправляем запрос к YandexGPT ({len(prompt)} символов)...")
            response = requests.post(self.api_url, headers=self.headers, json=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if 'result' in result and 'alternatives' in result['result']:
                    content = result['result']['alternatives'][0]['message']['text']
                    print(f"✅ Ответ получен ({len(content)} символов)")
                    return content
                else:
                    print(f"❌ Неверный формат ответа: {result}")
                    return None
            else:
                print(f"❌ Ошибка API: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка вызова YandexGPT: {e}")
            return None

    def search_ai_news(self):
        """Поиск и обработка новостей об ИИ"""
        prompt = """
        Найди САМУЮ интересную и важную новость за последние 2-3 часа в сфере искусственного интеллекта.
        
        Критерии отбора:
        - Новости от ведущих компаний: Google, Microsoft, OpenAI, Meta, Yandex, Apple, Amazon
        - Прорывные исследования или крупные обновления
        - Практическая значимость для отрасли
        
        Формат ответа для Telegram:
        
        🚀 [Эмоциональный заголовок на русском с эмодзи]
        
        📝 [Суть новости: 3-4 предложения на русском. Будь конкретным - упоминай цифры, технологии, последствия]
        
        💡 [Почему это важно: 1-2 предложения о значении для отрасли]
        
        🔗 [Ссылка на официальный источник или авторитетное издание]
        
        🔖 [3-5 релевантных хештегов на русском и английском]
        
        Пример:
        🚀 Google представила Gemini Ultra 2.0!
        
        📝 Новая модель демонстрирует 95% точность в тестах, превосходя GPT-4. 
        Поддерживает 50 языков и работает в 2 раза быстрее предыдущей версии.
        Доступна для разработчиков с сегодняшнего дня.
        
        💡 Это может изменить ландшафт AI-индустрии и ускорить внедрение ИИ в бизнесе.
        
        🔗 https://blog.google/technology/ai/gemini-ultra-2
        
        🔖 #Google #Gemini #ИИ #AI #Прорыв
        """
        
        return self.yandex_gpt_call(prompt)

def send_to_telegram(message):
    """Отправка сообщения в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Сообщение отправлено в Telegram!")
            return True
        else:
            print(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def publish_daily_news():
    """Публикация одной новости"""
    print(f"\n📅 Запуск публикации в {datetime.now().strftime('%H:%M')}...")
    
    monitor = YandexGPTMonitor()
    
    # Получаем новость от YandexGPT
    news_content = monitor.search_ai_news()
    
    if news_content:
        # Форматируем для Telegram
        telegram_message = f"""
🤖 <b>СВЕЖАЯ НОВОСТЬ ИИ</b> • {datetime.now().strftime('%H:%M')}

{news_content}

<em>📊 Автоматический мониторинг: YandexGPT 5.1 Pro</em>
        """
        
        if send_to_telegram(telegram_message):
            print("🎉 Новость успешно опубликована!")
            
            # Логируем успех
            log_entry = f"{datetime.now()}: Успешная публикация\n"
            with open("news_log.txt", "a", encoding="utf-8") as f:
                f.write(log_entry)
        else:
            print("❌ Ошибка публикации в Telegram")
    else:
        print("❌ Не удалось получить новость от YandexGPT")
        
        # Резервное сообщение
        backup_message = """
🤖 <b>AI NEWS MONITOR</b> • {datetime.now().strftime('%H:%M')}

⚠️ <b>Временные технические трудности</b>

📡 Не удалось получить свежие новости от системы мониторинга. 
Попробуем снова через час!

💡 <i>Система использует YandexGPT 5.1 Pro для поиска и анализа новостей</i>

🔖 #ИИ #Новости #Техработы
        """
        send_to_telegram(backup_message)

def schedule_news():
    """Расписание публикаций (каждый час с 09:00 до 21:00 по МСК)"""
    publication_times = [
        "09:00", "10:00", "11:00", "12:00", "13:00", "14:00",
        "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00"
    ]
    
    for time_str in publication_times:
        schedule.every().day.at(time_str).do(publish_daily_news)
        print(f"⏰ Запланирована публикация на {time_str}")

def run_scheduler():
    """Запуск планировщика"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверка каждую минуту

if __name__ == "__main__":
    # Проверка обязательных переменных
    required_vars = {
        'YANDEX_API_KEY': YANDEX_API_KEY,
        'YANDEX_FOLDER_ID': YANDEX_FOLDER_ID, 
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'TELEGRAM_CHANNEL_ID': TELEGRAM_CHANNEL_ID
    }
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        print(f"❌ Отсутствуют переменные: {', '.join(missing_vars)}")
        exit(1)
    
    print("✅ Все переменные окружения установлены")
    print("⏰ Настраиваем расписание публикаций...")
    
    # Настраиваем расписание
    schedule_news()
    
    # Тестовая публикация при запуске
    print("\n🧪 Тестовая публикация...")
    publish_daily_news()
    
    print("\n🎯 Система запущена! Расписание:")
    print("• 09:00 - 21:00: публикация каждый час")
    print("• Всего 13 публикаций в день")
    print("• Мониторинг через YandexGPT 5.1 Pro")
    print("\n🔄 Ожидаем следующей публикации...")
    
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Бесконечный цикл основного потока
    try:
        while True:
            time.sleep(3600)  # Спим 1 час
    except KeyboardInterrupt:
        print("\n🛑 Система остановлена")
