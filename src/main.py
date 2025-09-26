import os
import requests
import json
import time
from datetime import datetime

print("🚀 AI News Monitor запущен!")

# Получаем ключи из переменных окружения
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

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
        print("✅ Сообщение отправлено в Telegram")
        return True
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
            "max_tokens": 2000
        }
        
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        
        if 'choices' in result:
            return result['choices'][0]['message']['content']
        else:
            print("❌ Ошибка в ответе DeepSeek:", result)
            return None
            
    except Exception as e:
        print(f"❌ Ошибка вызова DeepSeek API: {e}")
        return None

def monitor_news():
    """Основная функция мониторинга"""
    print("🔍 Ищем свежие новости...")
    
    # Промпт для поиска новостей
    search_prompt = """
    Найди 3 самые интересные новости за последние 24 часа в сфере искусственного интеллекта 
    от компаний: Google, Microsoft, OpenAI, DeepSeek, Meta, Apple.
    
    Верни в формате:
    
    🚀 ЗАГОЛОВОК: [интересный заголовок на русском]
    
    📝 ОПИСАНИЕ: [2-3 предложения на русском]
    
    🔖 ХЕШТЕГИ: [#AI #ИИ #Новости]
    
    🔗 ССЫЛКА: [URL на источник]
    
    ---
    
    Только самые важные и интересные новости!
    """
    
    response = deepseek_api_call(search_prompt)
    
    if response:
        print("✅ Новости найдены!")
        print("📰 Пример новости:")
        print(response)
        
        # Отправляем в Telegram
        if send_to_telegram(response):
            print("🎉 Все готово! Новость опубликована.")
    else:
        print("❌ Не удалось получить новости")

def publish_news():
    """Функция публикации"""
    print("📤 Публикуем новости...")
    
    # Тестовое сообщение для проверки
    test_message = """
🤖 <b>Добро пожаловать в AI News Monitor!</b>

✅ Система успешно настроена и готова к работе!

🎯 <i>Каждый день в 09:00, 12:00, 15:00, 18:00 и 21:00 по МСК здесь будут появляться свежие новости из мира искусственного интеллекта</i>

📊 <b>Отслеживаем:</b> Google, Microsoft, OpenAI, DeepSeek, Meta, Apple

🔖 #AI #ИИ #Новости #Автоматизация
    """
    
    if send_to_telegram(test_message):
        print("✅ Тестовое сообщение отправлено!")

# Главная функция
if __name__ == "__main__":
    import sys
    
    # Проверяем только необходимые ключи
    if not DEEPSEEK_API_KEY:
        print("❌ Ошибка: DEEPSEEK_API_KEY не установлен")
        print("Добавьте его в Secrets GitHub репозитория")
        
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен")
        
    if not TELEGRAM_CHANNEL_ID:
        print("❌ Ошибка: TELEGRAM_CHANNEL_ID не установлен")
    
    # Если нет критических ключей - выходим
    if not all([DEEPSEEK_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        print("❌ Завершаем работу: не все обязательные переменные установлены")
        exit(1)
    
    # Определяем действие
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        publish_news()
    else:
        monitor_news()
