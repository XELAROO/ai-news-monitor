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
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            logging.info(f"Конфигурация загружена из {config_path}")
            return config
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            return {}
    
    def setup_logging(self):
        log_config = self.config.get('logging', {})
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format=log_config.get('format', '%(asctime)s - %(levelname)s - %(message)s'),
            handlers=[
                logging.FileHandler(self.config['paths']['log_file']),
                logging.StreamHandler()
            ]
        )
        logging.info("=== Начало выполнения скрипта ===")
        logging.info(f"Время запуска: {datetime.now()}")
    
    def get_run_count(self):
        """Получение счетчика запусков из файла состояния"""
        try:
            with open('script_state.txt', 'r') as f:
                count = int(f.read().strip())
            logging.info(f"Текущий счетчик запусков: {count}")
            return count
        except FileNotFoundError:
            logging.info("Файл состояния не найден, это первый запуск")
            return 0
    
    def update_run_count(self):
        """Обновление счетчика запусков"""
        self.run_count += 1
        with open('script_state.txt', 'w') as f:
            f.write(str(self.run_count))
        logging.info(f"Счетчик запусков обновлен: {self.run_count}")
    
    def create_folder(self):
        folder_name = self.config['paths']['folder_name']
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            logging.info(f"Создана папка: {folder_name}")
        else:
            logging.info(f"Папка уже существует: {folder_name}")
        return folder_name
    
    def create_files(self, folder_name):
        files_created = []
        
        # Всегда создаем новый файл с текущей датой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_file_path = os.path.join(folder_name, f"file_{timestamp}.txt")
        
        with open(new_file_path, 'w', encoding='utf-8') as f:
            f.write(f"Файл создан при запуске №{self.run_count + 1}\n")
            f.write(f"Время создания: {datetime.now()}\n")
            f.write(f"Это тестовое содержимое файла\n")
        
        files_created.append(new_file_path)
        logging.info(f"Создан файл: {new_file_path}")
        
        # Удаляем самый старый файл, если файлов больше 2
        files = sorted([f for f in os.listdir(folder_name) if f.startswith('file_')])
        if len(files) > 2:
            oldest_file = files[0]
            os.remove(os.path.join(folder_name, oldest_file))
            logging.info(f"Удален старый файл: {oldest_file}")
        
        return files_created
    
    def list_folder_contents(self, folder_name):
        logging.info("=== Содержимое папки ===")
        for item in sorted(os.listdir(folder_name)):
            item_path = os.path.join(folder_name, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                with open(item_path, 'r') as f:
                    content_preview = f.read(100)  # Первые 100 символов
                logging.info(f"Файл: {item} ({size} байт)")
                logging.info(f"Содержимое: {content_preview}...")
    
    def run(self):
        try:
            logging.info(f"Запуск №{self.run_count + 1}")
            
            folder_name = self.create_folder()
            files_created = self.create_files(folder_name)
            self.list_folder_contents(folder_name)
            self.update_run_count()
            
            logging.info(f"Скрипт успешно выполнен. Создано файлов: {len(files_created)}")
            
        except Exception as e:
            logging.error(f"Ошибка выполнения скрипта: {e}")
            raise

def main():
    script = GitTestScript()
    script.run()

if __name__ == "__main__":
    main()
