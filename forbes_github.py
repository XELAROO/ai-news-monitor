import os
import json
import hashlib
import time
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Сохраняем в корень репозитория (относительно src/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAST_NEWS_FILE = os.path.join(BASE_DIR, 'last_news.json')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
NEWS_COUNT_FILE = os.path.join(BASE_DIR, 'news_count.txt')

def ensure_dirs():
    """Создает директории если их нет"""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"📁 Results dir: {RESULTS_DIR}")
    print(f"📁 Results dir exists: {os.path.exists(RESULTS_DIR)}")
    print(f"📁 Results dir absolute path: {os.path.abspath(RESULTS_DIR)}")

def generate_fingerprint(title, url):
    return hashlib.md5(f"{title}|{url}".encode()).hexdigest()

def load_last_news():
    if os.path.exists(LAST_NEWS_FILE):
        try:
            with open(LAST_NEWS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error loading last_news: {e}")
            return None
    return None

def save_last_news(news_item):
    news_item['fingerprint'] = generate_fingerprint(news_item['title'], news_item['link'])
    news_item['last_updated'] = datetime.now().isoformat()
    with open(LAST_NEWS_FILE, 'w', encoding='utf-8') as f:
        json.dump(news_item, f, ensure_ascii=False, indent=2)
    print(f"💾 Last news saved to: {LAST_NEWS_FILE}")

def is_same_news(news1, news2):
    if not news1 or not news2:
        return False
    if news1.get('fingerprint') and news2.get('fingerprint'):
        if news1['fingerprint'] == news2['fingerprint']:
            return True
    if news1['link'] == news2['link']:
        return True
    title1 = news1['title'].lower().strip()
    title2 = news2['title'].lower().strip()
    if title1 == title2:
        return True
    words1 = set(title1.split())
    words2 = set(title2.split())
    if words1 and words2:
        similarity = len(words1.intersection(words2)) / max(len(words1), len(words2))
        return similarity > 0.7
    return False

def setup_selenium():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')
    
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ Chrome error: {e}")
        try:
            options.binary_location = '/usr/bin/google-chrome'
            return webdriver.Chrome(options=options)
        except:
            return None

def parse_forbes_ai():
    print("🚀 Starting parser with precise XPath...")
    
    if not SELENIUM_AVAILABLE:
        return []
    
    last_news = load_last_news()
    if last_news:
        print(f"📖 Last known: {last_news['title'][:60]}...")
    else:
        print("📖 No previous news")
    
    driver = None
    try:
        driver = setup_selenium()
        if not driver:
            return []
        
        print("📄 Loading Forbes AI...")
        driver.get("https://www.forbes.com/ai/")
        time.sleep(8)
        
        articles = []
        all_articles = []  # Для отладки - все найденные статьи
        
        print("🔍 Finding news using precise XPath...")
        
        # Проверяем, что заголовок "More From AI" существует
        try:
            more_from_ai = driver.find_element(By.XPATH, '//*[@id="row-2"]/div/div/div/div[1]/div[1]/h2')
            print("✅ Found 'More From AI' section")
        except:
            print("❌ 'More From AI' section not found")
            return []
        
        # Сначала соберем ВСЕ статьи для анализа
        news_index = 1
        while True:
            try:
                # XPath для времени новости
                time_xpath = f'//*[@id="row-2"]/div/div/div/div[1]/div[2]/div[{news_index}]/div/div/div[2]/div[1]/time'
                time_elem = driver.find_element(By.XPATH, time_xpath)
                date_text = time_elem.text.strip()
                
                # XPath для заголовка новости
                title_xpath = f'//*[@id="row-2"]/div/div/div/div[1]/div[2]/div[{news_index}]/div/div/div[2]/h3'
                title_elem = driver.find_element(By.XPATH, title_xpath)
                title_link = title_elem.find_element(By.TAG_NAME, "a")
                title = title_link.text.strip()
                href = title_link.get_attribute('href')
                
                if title and href and len(title) > 10:
                    current_article = {
                        'date': date_text,
                        'title': title,
                        'link': href,
                        'fingerprint': generate_fingerprint(title, href)
                    }
                    
                    all_articles.append(current_article)
                    print(f"📰 Found article {news_index}: {title[:50]}...")
                    
                news_index += 1
                
            except Exception as e:
                # Если не нашли элемент - значит новости закончились
                print(f"📭 No more news found (index {news_index}), total found: {len(all_articles)}")
                break
        
        # Теперь определим, какие статьи являются новыми
        if last_news:
            print(f"\n🔍 Looking for last known news: {last_news['title'][:50]}...")
            last_news_index = -1
            
            # Найдем индекс последней известной новости
            for i, article in enumerate(all_articles):
                if is_same_news(article, last_news):
                    last_news_index = i
                    print(f"✅ Found last known news at position {i+1}")
                    break
            
            if last_news_index >= 0:
                # Все статьи ДО последней известной - это новые статьи
                articles = all_articles[:last_news_index]
                print(f"🎯 New articles found: {len(articles)} (positions 1-{last_news_index})")
            else:
                # Если последняя известная новость не найдена, берем все статьи
                articles = all_articles
                print(f"⚠️ Last known news not found, taking all {len(articles)} articles")
        else:
            # Если нет предыдущих новостей, берем все
            articles = all_articles
            print(f"📝 No previous news, taking all {len(articles)} articles")
        
        # Сохраняем самую свежую новость как маркер для следующего парсинга
        if all_articles:
            save_last_news(all_articles[0])
            print(f"💾 New last news saved: {all_articles[0]['title'][:60]}...")
        
        return articles
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def force_file_sync(filename):
    """Принудительная синхронизация файла с файловой системой"""
    try:
        # Синхронизируем конкретный файл
        with open(filename, 'a') as f:
            os.fsync(f.fileno())
        print(f"🔄 File synced: {filename}")
    except Exception as e:
        print(f"⚠️ File sync warning: {e}")

def save_results(articles):
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(RESULTS_DIR, f"github_{timestamp}.txt")
    
    print(f"📝 Creating file: {filename}")
    print(f"📝 Absolute file path: {os.path.abspath(filename)}")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("FORBES AI - GITHUB PARSER\n")
            f.write("=" * 50 + "\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"New articles: {len(articles)}\n\n")
            
            for i, article in enumerate(articles, 1):
                f.write(f"{i}. DATE: {article['date']}\n")
                f.write(f"   TITLE: {article['title']}\n")
                f.write(f"   LINK: {article['link']}\n")
                f.write("-" * 50 + "\n")
        
        # 🔥 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Принудительная синхронизация
        force_file_sync(filename)
        
        # Проверяем, что файл действительно создался
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"✅ File successfully created: {filename}")
            print(f"✅ File size: {file_size} bytes")
            print(f"✅ File exists: {os.path.exists(filename)}")
            
            # Дополнительная проверка - читаем содержимое
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"✅ File content verified, length: {len(content)} chars")
        else:
            print(f"❌ File was not created: {filename}")
            return None
            
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return None
    
    # Сохраняем количество новостей
    try:
        with open(NEWS_COUNT_FILE, 'w', encoding='utf-8') as f:
            f.write(str(len(articles)))
        
        # Синхронизируем news_count.txt
        force_file_sync(NEWS_COUNT_FILE)
        
        print(f"💾 News count saved to: {NEWS_COUNT_FILE}")
        print(f"💾 News count value: {len(articles)}")
        
        # Проверяем записанное значение
        with open(NEWS_COUNT_FILE, 'r', encoding='utf-8') as f:
            saved_count = f.read().strip()
            print(f"💾 News count verified: {saved_count}")
            
    except Exception as e:
        print(f"❌ Error saving news count: {e}")
    
    return filename

def check_results_directory():
    """Проверяет и выводит содержимое папки results"""
    print(f"\n🔍 CHECKING RESULTS DIRECTORY:")
    print(f"📁 Path: {RESULTS_DIR}")
    print(f"📁 Exists: {os.path.exists(RESULTS_DIR)}")
    
    if os.path.exists(RESULTS_DIR):
        files = os.listdir(RESULTS_DIR)
        print(f"📁 Number of files: {len(files)}")
        for file in sorted(files, reverse=True):  # Сортируем по убыванию (новые сначала)
            file_path = os.path.join(RESULTS_DIR, file)
            file_size = os.path.getsize(file_path)
            print(f"   📄 {file} ({file_size} bytes)")
    else:
        print("❌ Results directory does not exist!")

def main():
    print("=" * 60)
    print("🎯 FORBES AI - GITHUB PARSER")
    print("=" * 60)
    
    articles = parse_forbes_ai()
    
    if articles:
        print(f"\n✅ SUCCESS! Found: {len(articles)} new articles")
        
        print("📋 New articles list:")
        for i, article in enumerate(articles, 1):
            print(f"   {i}. {article['title'][:60]}...")
        
        filename = save_results(articles)
        
        if filename and os.path.exists(filename):
            print(f"💾 All files saved successfully")
            
            # Показываем содержимое папки results
            check_results_directory()
            
        else:
            print(f"❌ File was not created successfully")
            
    else:
        print("📭 No new news found")
        # Все равно сохраняем 0 в news_count.txt
        try:
            with open(NEWS_COUNT_FILE, 'w', encoding='utf-8') as f:
                f.write("0")
            
            # Синхронизируем
            force_file_sync(NEWS_COUNT_FILE)
            
            print(f"💾 News count saved: 0")
        except Exception as e:
            print(f"❌ Error saving news count: {e}")
    
    # Финальная проверка директории
    print(f"\n🎯 FINAL DIRECTORY CHECK:")
    check_results_directory()

if __name__ == "__main__":
    main()
