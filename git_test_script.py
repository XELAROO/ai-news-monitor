#!/usr/bin/env python3
"""
Скрипт для тестирования работы с Git репозиторием
Версия для GitHub Actions
"""

import os
import logging
import yaml
from datetime import datetime

class GitTestScript:
    def __init__(self, config_path="config.yaml"):
        self.config = self.load_config(config_path)
        self.setup_logging()
        self.run_count = self.get_run_count()
        
    def load_config(self, config_path):
        """Загрузка конфигурации из YAML файла"""
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            logging.info(f"Конфигурация загружена из {config_path}")
            return config
        except Exception as e:
            # Если конфиг не найден, используем значения по умолчанию
            logging.warning(f"Ошибка загрузки конфигурации: {e}. Использую значения по умолчанию.")
            return {
                'paths': {
                    'folder_name': 'test_results',
                    'log_file': 'script.log'
                },
                'logging': {
                    'level': 'INFO',
                    'format': '%(asctime)s - %(levelname)s - %(message)s'
                }
            }
    
    def setup_logging(self):
        """Настройка логирования"""
        log_config = self.config.get('logging', {})
        
        # Получаем путь к файлу логов
        log_file = self.config.get('paths', {}).get('log_file', 'script.log')
        
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format=log_config.get('format', '%(asctime)s - %(levelname)s - %(message)s'),
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logging.info("=== Начало выполнения скрипта ===")
        logging.info(f"Время запуска: {datetime.now()}")
    
    def get_run_count(self):
        """Получение счетчика запусков из файла состояния"""
        try:
            with open('script_state.txt', 'r', encoding='utf-8') as f:
                count = int(f.read().strip())
            logging.info(f"Текущий счетчик запусков: {count}")
            return count
        except FileNotFoundError:
            logging.info("Файл состояния не найден, это первый запуск")
            return 0
        except Exception as e:
            logging.warning(f"Ошибка чтения счетчика: {e}. Начинаем с 0.")
            return 0
    
    def update_run_count(self):
        """Обновление счетчика запусков"""
        self.run_count += 1
        with open('script_state.txt', 'w', encoding='utf-8') as f:
            f.write(str(self.run_count))
        logging.info(f"Счетчик запусков обновлен: {self.run_count}")
    
    def create_folder(self):
        """Создание папки если она не существует"""
        folder_name = self.config.get('paths', {}).get('folder_name', 'test_results')
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            logging.info(f"Создана папка: {folder_name}")
        else:
            logging.info(f"Папка уже существует: {folder_name}")
        return folder_name
    
    def create_files(self, folder_name):
        """Создание и управление файлами"""
        files_created = []
        
        # Создаем новый файл с текущей датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_file_path = os.path.join(folder_name, f"file_{timestamp}.txt")
        
        # Содержимое файла
        content = f"""Файл создан при запуске №{self.run_count + 1}
Время создания: {datetime.now()}
Это тестовое содержимое файла
Счетчик запусков: {self.run_count + 1}
"""
        with open(new_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        files_created.append(new_file_path)
        logging.info(f"Создан файл: {new_file_path}")
        
        # Получаем список всех файлов в папке
        try:
            files = [f for f in os.listdir(folder_name) 
                    if f.startswith('file_') and f.endswith('.txt')]
            files.sort()  # Сортируем по имени (включая timestamp)
            
            # Удаляем самый старый файл, если файлов больше 2
            if len(files) > 2:
                oldest_file = files[0]
                oldest_file_path = os.path.join(folder_name, oldest_file)
                os.remove(oldest_file_path)
                logging.info(f"Удален старый файл: {oldest_file}")
                
        except Exception as e:
            logging.error(f"Ошибка при управлении файлами: {e}")
        
        return files_created
    
    def list_folder_contents(self, folder_name):
        """Вывод содержимого папки"""
        logging.info("=== Содержимое папки ===")
        try:
            items = os.listdir(folder_name)
            if not items:
                logging.info("Папка пуста")
                return
                
            for item in sorted(items):
                item_path = os.path.join(folder_name, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    try:
                        with open(item_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        logging.info(f"Файл: {item} ({size} байт)")
                        logging.info(f"Содержимое: {content.strip()}")
                    except Exception as e:
                        logging.error(f"Ошибка чтения файла {item}: {e}")
                else:
                    logging.info(f"Папка: {item}")
        except Exception as e:
            logging.error(f"Ошибка чтения папки: {e}")
    
    def run(self):
        """Основной метод выполнения скрипта"""
        try:
            logging.info(f"Запуск №{self.run_count + 1}")
            
            # Создаем папку
            folder_name = self.create_folder()
            
            # Создаем/удаляем файлы
            files_created = self.create_files(folder_name)
            
            # Показываем содержимое папки
            self.list_folder_contents(folder_name)
            
            # Обновляем счетчик запусков
            self.update_run_count()
            
            logging.info(f"Скрипт успешно выполнен. Создано файлов: {len(files_created)}")
            return True
            
        except Exception as e:
            logging.error(f"Ошибка выполнения скрипта: {e}")
            return False

def main():
    """Основная функция"""
    script = GitTestScript()
    success = script.run()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
