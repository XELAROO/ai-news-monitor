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
    print("🚀 Starting parser...")
    
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
        time.sleep(10)
        
        articles = []
        found_known_news = False
        
        print("🔍 Finding news by structure...")
        
        # СПОСОБ 1: Ищем по структуре - div содержащие time и h3
        containers = driver.find_elements(By.XPATH, "//div[.//time and .//h3//a]")
        print(f"📦 Found structured containers: {len(containers)}")
        
        # Отладочная информация
        print("🔍 Debug structure:")
        for i, container in enumerate(containers[:3]):
            try:
                time_elem = container.find_element(By.TAG_NAME, "time")
                title_elem = container.find_element(By.XPATH, ".//h3//a")
                print(f"  Container {i}: time='{time_elem.text}', title='{title_elem.text[:30]}...'")
            except:
                print(f"  Container {i}: invalid structure")
        
        for container in containers:
            if found_known_news:
                break
                
            try:
                # Ищем время и заголовок ВНУТРИ контейнера
                time_elem = container.find_element(By.TAG_NAME, "time")
                date_text = time_elem.text.strip()
                if not date_text:
                    continue
                
                title_elem = container.find_element(By.XPATH, ".//h3//a")
                title = title_elem.text.strip()
                href = title_elem.get_attribute('href')
                
                if title and href and len(title) > 10:
                    current_article = {
                        'date': date_text,
                        'title': title,
                        'link': href,
                        'fingerprint': generate_fingerprint(title, href)
                    }
                    
                    # Проверяем на дубликаты
                    if any(a['link'] == href for a in articles):
                        continue
                    
                    if last_news and is_same_news(current_article, last_news):
                        print(f"🛑 Reached known news: {title[:60]}...")
                        found_known_news = True
                        break
                    
                    articles.append(current_article)
                    print(f"✅ {len(articles)}: {date_text} - {title[:50]}...")
                    
            except Exception as e:
                continue
        
        # СПОСОБ 2: Прямой поиск всех h3 с ссылками
        if len(articles) < 5:
            print("🔍 Alternative: direct h3 search...")
            h3_links = driver.find_elements(By.XPATH, "//h3//a")
            print(f"🔗 Found h3 links: {len(h3_links)}")
            
            for h3_link in h3_links:
                if found_known_news:
                    break
                    
                try:
                    title = h3_link.text.strip()
                    href = h3_link.get_attribute('href')
                    
                    if title and href and len(title) > 10:
                        # Ищем ближайший time элемент
                        time_elem = h3_link.find_element(By.XPATH, "./ancestor::div[1]//time")
                        date_text = time_elem.text.strip()
                        
                        current_article = {
                            'date': date_text,
                            'title': title,
                            'link': href,
                            'fingerprint': generate_fingerprint(title, href)
                        }
                        
                        if any(a['link'] == href for a in articles):
                            continue
                            
                        if last_news and is_same_news(current_article, last_news):
                            print(f"🛑 Reached known news: {title[:60]}...")
                            found_known_news = True
                            break
                        
                        articles.append(current_article)
                        print(f"✅ {len(articles)}: {date_text} - {title[:50]}...")
                        
                except Exception as e:
                    continue
        
        if articles:
            save_last_news(articles[0])
            print(f"💾 New last news: {articles[0]['title'][:60]}...")
        
        return articles
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def save_results(articles):
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(RESULTS_DIR, f"github_{timestamp}.txt")
    
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
    
    # Сохраняем количество новостей
    with open(NEWS_COUNT_FILE, 'w') as f:
        f.write(str(len(articles)))
    
    print(f"💾 Results saved to: {filename}")
    print(f"💾 News count saved to: {NEWS_COUNT_FILE}")
    
    return filename

def main():
    print("=" * 60)
    print("🎯 FORBES AI - GITHUB PARSER")
    print("=" * 60)
    
    articles = parse_forbes_ai()
    
    if articles:
        print(f"\n✅ SUCCESS! Found: {len(articles)} new articles")
        filename = save_results(articles)
        print(f"💾 All files saved successfully")
    else:
        print("📭 No new news found")
        with open(NEWS_COUNT_FILE, 'w') as f:
            f.write("0")

if __name__ == "__main__":
    ensure_dirs()
    main()
