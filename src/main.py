import os
import requests
import sys

print("=" * 50)
print("🚀 AI News Monitor - ПОЛНАЯ ВЕРСИЯ")
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
            print("✅ Сообщение отправлено в Telegram!")
            return True
        else:
            print(f"❌ Ошибка Telegram API: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def deepseek_api_call(prompt):
    """Вызов DeepSeek API с детальным логированием"""
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
        print(f"URL: {url}")
        print(f"Заголовки: Authorization: Bearer ***{DEEPSEEK_API_KEY[-10:] if DEEPSEEK_API_KEY else 'NO_KEY'}")  # Показываем только последние 10 символов
        print(f"Длина промпта: {len(prompt)} символов")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"📡 Статус ответа: {response.status_code}")
        print(f"📨 Заголовки ответа: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Формат ответа корректный")
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                print(f"📝 Длина ответа: {len(content)} символов")
                return content
            else:
                print("❌ Неверный формат ответа от DeepSeek")
                print(f"Полный ответ: {result}")
                return None
        else:
            print(f"❌ Ошибка HTTP: {response.status_code}")
            print(f"Текст ошибки: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ Таймаут запроса к DeepSeek API (30 секунд)")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка подключения к DeepSeek API")
        return None
    except Exception as e:
        print(f"❌ Исключение при вызове DeepSeek API: {e}")
        return None

def monitor_news():
    """Основная функция мониторинга"""
    print("📰 Запускаем поиск новостей через DeepSeek...")
    
    # Промпт для поиска новостей
    search_prompt = """
    Найди 2-3 самые интересные новости за последние 24 часа в сфере искусственного интеллекта 
    от компаний: Google, Microsoft, OpenAI, DeepSeek, Meta.
    
    Верни ответ в формате:
    
    🚀 [Интересный заголовок на русском]
    
    📝 [Краткое описание на русском, 2-3 предложения]
    
    🔗 [Ссылка на источник]
    
    🔖 [#AI #ИИ #Новости]
    
    Будь краток и информативен!
    """
    
    response = deepseek_api_call(search_prompt)
    
    if response:
        print("✅ Новости получены от DeepSeek!")
        print("=" * 50)
        print(response)
        print("=" * 50)
        
        # Отправляем в Telegram
        telegram_message = f"""
🤖 <b>Свежие новости AI от DeepSeek</b>

{response}

<b>✅ Автоматический мониторинг работает!</b>
        """
        
        if send_to_telegram(telegram_message):
            print("🎉 Новости успешно опубликованы!")
        else:
            print("❌ Не удалось отправить новости в Telegram")
    else:
        # Если DeepSeek не ответил, отправляем сообщение об ошибке
        error_message = """
🤖 <b>AI News Monitor - Технические работы</b>

⚠️ <b>Временная проблема с получением новостей</b>

🔧 <b>Статус:</b>
• Telegram: ✅ РАБОТАЕТ
• DeepSeek: ❌ ВРЕМЕННО НЕДОСТУПЕН
• Система: 🔄 В РЕЖИМЕ ОЖИДАНИЯ

💡 <i>Следующая попытка через 24 часа</i>

🔖 #AI #Техработы #Обновление
        """
        
        if send_to_telegram(error_message):
            print("📢 Отправлено уведомление о технических работах")

def publish_news():
    """Функция публикации тестового сообщения"""
    print("📤 Отправляем тестовое сообщение...")
    
    test_message = """
🤖 <b>AI News Monitor - Тест системы</b>

✅ <b>Все компоненты проверены:</b>
• Telegram: ✅ РАБОТАЕТ
• GitHub Actions: ✅ РАБОТАЕТ
• DeepSeek: 🔄 ПРОВЕРКА

🎯 <b>Система готова к автоматической работе!</b>

⏰ <b>Расписание:</b>
Ежедневно в 09:00, 12:00, 15:00, 18:00, 21:00 по МСК

🔖 #AI #Тест #Готово #Автоматизация
    """
    
    if send_to_telegram(test_message):
        print("✅ Тестовое сообщение отправлено!")
    else:
        print("❌ Не удалось отправить тестовое сообщение")

# Главная функция
if __name__ == "__main__":
    # Проверяем обязательные переменные
    if not TELEGRAM_BOT_TOKEN:
        print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
        
    if not TELEGRAM_CHANNEL_ID:
        print("❌ ОШИБКА: TELEGRAM_CHANNEL_ID не найден")
        sys.exit(1)

    if not DEEPSEEK_API_KEY:
        print("❌ ОШИБКА: DEEPSEEK_API_KEY не найден")
        print("💡 Решение: Добавьте корректный API ключ в Secrets")
        # Но продолжаем работу в тестовом режиме
        test_message = """
🤖 <b>AI News Monitor - Требуется настройка</b>

❌ <b>Проблема:</b> Не настроен DEEPSEEK_API_KEY

💡 <b>Решение:</b>
1. Зайдите в Settings → Secrets → Actions
2. Добавьте DEEPSEEK_API_KEY с вашим ключом от platform.deepseek.com

🔖 #AI #Настройка #Помощь
        """
        send_to_telegram(test_message)
        sys.exit(1)

    # Определяем действие
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        publish_news()
    else:
        monitor_news()
    
    print("=" * 50)
    print("🏁 Работа завершена!")
    print("=" * 50)
