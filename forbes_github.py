import os
import json
import hashlib
import time
import logging
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

# Конфигурация путей
BASE_DIR = os.getcwd()
LAST_NEWS_FILE = os.path.join(BASE_DIR, 'last_news.json')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
NEWS_COUNT_FILE = os.path.join(BASE_DIR, 'news_count.txt')
LOG_FILE = os.path.join(BASE_DIR, 'forbes_parser.log')

class ForbesParser:
    def __init__(self):
        self.setup_logging()
        self.run_count = self.get_run_count()
        
    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        logging.info("=== FORBES AI PARSER STARTED ===")
        logging.info(f"Start time: {datetime.now()}")
    
    def get_run_count(self):
        """Получение счетчика запусков из файла состояния"""
        state_file = os.path.join(BASE_DIR, 'parser_state.txt')
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                count = int(f.read().strip())
            logging.info(f"Current run count: {count}")
            return count
        except FileNotFoundError:
            logging.info("State file not found, this is first run")
            return 0
        except Exception as e:
            logging.warning(f"Error reading counter: {e}. Starting from 0.")
            return 0
    
    def update_run_count(self):
        """Обновление счетчика запусков"""
        state_file = os.path.join(BASE_DIR, 'parser_state.txt')
        self.run_count += 1
        with open(state_file, 'w', encoding='utf-8') as f:
            f.write(str(self.run_count))
        logging.info(f"Run counter updated: {self.run_count}")
    
    def ensure_dirs(self):
        """Создает директории если их нет"""
        if not os.path.exists(RESULTS_DIR):
            os.makedirs(RESULTS_DIR)
            logging.info(f"Created directory: {RESULTS_DIR}")
        else:
            logging.info(f"Directory already exists: {RESULTS_DIR}")
        return RESULTS_DIR

    def generate_fingerprint(self, title, url):
        return hashlib.md5(f"{title}|{url}".encode()).hexdigest()

    def load_last_news(self):
        if os.path.exists(LAST_NEWS_FILE):
            try:
                with open(LAST_NEWS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading last_news: {e}")
                return None
        return None

    def save_last_news(self, news_item):
        news_item['fingerprint'] = self.generate_fingerprint(news_item['title'], news_item['link'])
        news_item['last_updated'] = datetime.now().isoformat()
        with open(LAST_NEWS_FILE, 'w', encoding='utf-8') as f:
            json.dump(news_item, f, ensure_ascii=False, indent=2)
        logging.info(f"Last news saved: {LAST_NEWS_FILE}")

    def is_same_news(self, news1, news2):
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

    def setup_selenium(self):
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
            logging.error(f"Chrome error: {e}")
            try:
                options.binary_location = '/usr/bin/google-chrome'
                return webdriver.Chrome(options=options)
            except:
                return None

    def parse_forbes_ai(self):
        logging.info("Starting parser with precise XPath...")
        
        if not SELENIUM_AVAILABLE:
            return []
        
        last_news = self.load_last_news()
        if last_news:
            logging.info(f"Last known: {last_news['title'][:60]}...")
        else:
            logging.info("No previous news")
        
        driver = None
        try:
            driver = self.setup_selenium()
            if not driver:
                return []
            
            logging.info("Loading Forbes AI...")
            driver.get("https://www.forbes.com/ai/")
            time.sleep(8)
            
            articles = []
            all_articles = []
            
            logging.info("Finding news using precise XPath...")
            
            # Проверяем, что заголовок "More From AI" существует
            try:
                more_from_ai = driver.find_element(By.XPATH, '//*[@id="row-2"]/div/div/div/div[1]/div[1]/h2')
                logging.info("Found 'More From AI' section")
            except:
                logging.error("'More From AI' section not found")
                return []
            
            # Собираем все статьи
            news_index = 1
            while True:
                try:
                    time_xpath = f'//*[@id="row-2"]/div/div/div/div[1]/div[2]/div[{news_index}]/div/div/div[2]/div[1]/time'
                    time_elem = driver.find_element(By.XPATH, time_xpath)
                    date_text = time_elem.text.strip()
                    
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
                            'fingerprint': self.generate_fingerprint(title, href)
                        }
                        
                        all_articles.append(current_article)
                        logging.info(f"Found article {news_index}: {title[:50]}...")
                    
                    news_index += 1
                    
                except Exception as e:
                    logging.info(f"No more news found (index {news_index}), total found: {len(all_articles)}")
                    break
            
            # Определяем, какие статьи являются новыми
            if last_news:
                logging.info(f"Looking for last known news: {last_news['title'][:50]}...")
                last_news_index = -1
                
                for i, article in enumerate(all_articles):
                    if self.is_same_news(article, last_news):
                        last_news_index = i
                        logging.info(f"Found last known news at position {i+1}")
                        break
                
                if last_news_index >= 0:
                    articles = all_articles[:last_news_index]
                    logging.info(f"New articles found: {len(articles)} (positions 1-{last_news_index})")
                else:
                    articles = all_articles
                    logging.info(f"Last known news not found, taking all {len(articles)} articles")
            else:
                articles = all_articles
                logging.info(f"No previous news, taking all {len(articles)} articles")
            
            # Сохраняем самую свежую новость как маркер
            if all_articles:
                self.save_last_news(all_articles[0])
                logging.info(f"New last news saved: {all_articles[0]['title'][:60]}...")
            
            return articles
            
        except Exception as e:
            logging.error(f"Parser error: {e}")
            return []
        finally:
            if driver:
                driver.quit()

    def save_results(self, articles):
        """Создание и управление файлами результатов"""
        folder_name = self.ensure_dirs()
        files_created = []
        
        # Создаем новый файл с текущей датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_file_path = os.path.join(folder_name, f"github_{timestamp}.txt")
        
        # Содержимое файла
        content = f"""FORBES AI - GITHUB PARSER
{'=' * 50}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Run count: {self.run_count + 1}
New articles: {len(articles)}

"""
        for i, article in enumerate(articles, 1):
            content += f"{i}. DATE: {article['date']}\n"
            content += f"   TITLE: {article['title']}\n"
            content += f"   LINK: {article['link']}\n"
            content += "-" * 50 + "\n\n"
        
        with open(new_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        files_created.append(new_file_path)
        logging.info(f"Created file: {new_file_path}")
        
        # Управление файлами - удаляем старые, если файлов больше 5
        try:
            files = [f for f in os.listdir(folder_name) 
                    if f.startswith('github_') and f.endswith('.txt')]
            files.sort()  # Сортируем по имени (старые сначала)
            
            # Удаляем самые старые файлы, если файлов больше 5
            if len(files) > 5:
                files_to_remove = files[:-5]  # Все кроме последних 5
                for old_file in files_to_remove:
                    old_file_path = os.path.join(folder_name, old_file)
                    os.remove(old_file_path)
                    logging.info(f"Removed old file: {old_file}")
                    
        except Exception as e:
            logging.error(f"Error managing files: {e}")
        
        # Сохраняем количество новостей
        try:
            with open(NEWS_COUNT_FILE, 'w', encoding='utf-8') as f:
                f.write(str(len(articles)))
            logging.info(f"News count saved: {len(articles)}")
        except Exception as e:
            logging.error(f"Error saving news count: {e}")
        
        return files_created

    def list_folder_contents(self, folder_name):
        """Вывод содержимого папки"""
        logging.info("=== FOLDER CONTENTS ===")
        try:
            items = os.listdir(folder_name)
            if not items:
                logging.info("Folder is empty")
                return
                
            for item in sorted(items, reverse=True):  # Новые файлы сначала
                item_path = os.path.join(folder_name, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    logging.info(f"File: {item} ({size} bytes)")
                else:
                    logging.info(f"Subdirectory: {item}")
        except Exception as e:
            logging.error(f"Error reading folder: {e}")

    def run(self):
        """Основной метод выполнения скрипта"""
        try:
            logging.info(f"Run #{self.run_count + 1}")
            
            # Парсинг новостей
            articles = self.parse_forbes_ai()
            
            if articles:
                logging.info(f"SUCCESS! Found: {len(articles)} new articles")
                
                # Сохраняем результаты
                files_created = self.save_results(articles)
                
                # Показываем содержимое папки
                self.list_folder_contents(RESULTS_DIR)
                
                logging.info(f"Script completed successfully. Files created: {len(files_created)}")
            else:
                logging.info("No new news found")
                # Сохраняем 0 в news_count.txt
                try:
                    with open(NEWS_COUNT_FILE, 'w', encoding='utf-8') as f:
                        f.write("0")
                    logging.info("News count saved: 0")
                except Exception as e:
                    logging.error(f"Error saving news count: {e}")
            
            # Обновляем счетчик запусков
            self.update_run_count()
            
            return True
            
        except Exception as e:
            logging.error(f"Script execution error: {e}")
            return False

def main():
    """Основная функция"""
    parser = ForbesParser()
    success = parser.run()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
