import os
import requests
import sys

print("=" * 50)
print("🚀 AI News Monitor запущен!")
print("=" * 50)

# Получаем ключи из переменных окружения
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') 
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Выводим отладочную информацию
print("🔧 Проверка переменных окружения:")
print(f"DEEPSEEK_API_KEY: {'***установлен***' if DEEPSEEK_API_KEY else '❌ НЕ УСТАНОВЛЕН'}")
print(f"TELEGRAM_BOT_TOKEN: {'***установлен***' if TELEGRAM_BOT_TOKEN else '❌ НЕ УСТАНОВЛЕН'}")
print(f"TELEGRAM_CHANNEL_ID: {'***установлен***' if TELEGRAM_CHANNEL_ID else '❌ НЕ УСТАНОВЛЕН'}")
print("-" * 50)

def send_to_telegram(message):
    """Отправка сообщения в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Сообщение отправлено в Telegram")
            return True
        else:
            print(f"❌ Ошибка Telegram API: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def deepseek_api_call(prompt):
    """Вызов DeepSeek API"""
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        print("🔍 Отправляем запрос к DeepSeek API...")
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result:
                content = result['choices'][0]['message']['content']
                print("✅ Ответ от DeepSeek получен!")
                return content
            else:
                print("❌ Неверный формат ответа от DeepSeek")
                return None
        else:
            print(f"❌ Ошибка DeepSeek API: {response.status_code}")
            print(f"Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка вызова DeepSeek API: {e}")
        return None

def monitor_news():
    """Основная функция мониторинга"""
    print("📰 Запускаем поиск новостей...")
    
    # Простой промпт для теста
    search_prompt = """
    Найди одну самую интересную новость за последние 24 часа в сфере искусственного интеллекта.
    Верни краткий ответ в формате:
    
    🚀 Заголовок новости
    📝 Краткое описание (2 предложения)
    🔗 Ссылка на источник
    🔖 Хештеги: #AI #ИИ #Новости
    """
    
    response = deepseek_api_call(search_prompt)
    
    if response:
        print("✅ Новость найдена!")
        print("=" * 50)
        print(response)
        print("=" * 50)
        
        # Отправляем в Telegram
        telegram_message = f"""
🤖 <b>Тестовая новость от AI Monitor</b>

{response}

<b>✅ Система работает корректно!</b>
        """
        
        if send_to_telegram(telegram_message):
            print("🎉 Новость успешно опубликована!")
        else:
            print("❌ Не удалось отправить новость в Telegram")
    else:
        print("❌ Не удалось получить новости от DeepSeek")

def publish_news():
    """Функция публикации тестового сообщения"""
    print("📤 Отправляем тестовое сообщение...")
    
    test_message = """
🤖 <b>AI News Monitor - Тестовое сообщение</b>

✅ Система успешно настроена!

🎯 <b>Расписание работы:</b>
• 07:00 - Поиск новостей
• 09:00, 12:00, 15:00, 18:00, 21:00 - Публикация

🔍 <b>Отслеживаем:</b> Google, Microsoft, OpenAI, DeepSeek

🔖 #AI #ИИ #Новости #Тест #Автоматизация
    """
    
    if send_to_telegram(test_message):
        print("✅ Тестовое сообщение отправлено!")
    else:
        print("❌ Не удалось отправить тестовое сообщение")

# Главная функция
if __name__ == "__main__":
    # Проверяем обязательные переменные
    if not DEEPSEEK_API_KEY:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: DEEPSEEK_API_KEY не найден")
        print("💡 Решение: Добавьте DEEPSEEK_API_KEY в Secrets GitHub репозитория")
        print("   Settings → Secrets and variables → Actions → New repository secret")
        sys.exit(1)
        
    if not TELEGRAM_BOT_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
        
    if not TELEGRAM_CHANNEL_ID:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_CHANNEL_ID не найден")
        sys.exit(1)

    # Определяем действие
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        publish_news()
    else:
        monitor_news()
    
    print("=" * 50)
    print("🏁 Работа завершена!")
    print("=" * 50)
