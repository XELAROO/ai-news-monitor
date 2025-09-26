import os
import requests
import sys

print("=" * 50)
print("🚀 AI News Monitor - ТЕСТОВЫЙ РЕЖИМ")
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
        
        print(f"🔗 Отправляем запрос к Telegram...")
        print(f"URL: {url.split('/bot')[0]}/bot***hidden***/sendMessage")
        print(f"Chat ID: {TELEGRAM_CHANNEL_ID}")
        
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Сообщение отправлено в Telegram!")
            return True
        else:
            print(f"❌ Ошибка Telegram API: {response.status_code}")
            print(f"Подробности: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def publish_news():
    """Функция публикации тестового сообщения"""
    print("📤 Отправляем тестовое сообщение в Telegram...")
    
    test_message = """
🤖 <b>AI News Monitor - Тестовое сообщение</b>

🎯 <b>Проверка связи:</b> ✅ УСПЕШНО!

📊 <b>Статус системы:</b>
• Telegram: ✅ РАБОТАЕТ
• DeepSeek: 🔄 ПРОВЕРКА
• GitHub Actions: ✅ РАБОТАЕТ

🔍 <b>Следующий шаг:</b> Настроить DeepSeek API

🔖 #AI #Тест #Настройка #Работает
    """
    
    if send_to_telegram(test_message):
        print("🎉 Telegram работает корректно!")
        print("💡 Теперь нужно настроить DEEPSEEK_API_KEY")
    else:
        print("❌ Проблема с Telegram")

# Главная функция
if __name__ == "__main__":
    # Проверяем только Telegram для теста
    if not TELEGRAM_BOT_TOKEN:
        print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден")
        sys.exit(1)
        
    if not TELEGRAM_CHANNEL_ID:
        print("❌ ОШИБКА: TELEGRAM_CHANNEL_ID не найден")
        sys.exit(1)

    # Временно игнорируем ошибку DeepSeek для теста
    if not DEEPSEEK_API_KEY:
        print("⚠️  ПРЕДУПРЕЖДЕНИЕ: DEEPSEEK_API_KEY не найден")
        print("💡 Это нормально для теста Telegram")
    
    publish_news()
    
    print("=" * 50)
    print("🏁 Тест завершен!")
    print("=" * 50)
