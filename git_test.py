import os
import logging
import subprocess
import datetime
import uuid

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("git_test.log"),
        logging.StreamHandler()
    ]
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, 'test_git_folder')

def setup_logging():
    logging.info("Starting script execution")
    logging.info(f"Base directory: {BASE_DIR}")
    logging.info(f"Test directory: {TEST_DIR}")

def create_test_directory():
    try:
        os.makedirs(TEST_DIR, exist_ok=True)
        logging.info(f"Directory created: {TEST_DIR}")
        return True
    except Exception as e:
        logging.error(f"Failed to create directory: {e}")
        return False

def create_file(filename, content):
    file_path = os.path.join(TEST_DIR, filename)
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        logging.info(f"File created: {file_path}")
        return file_path
    except Exception as e:
        logging.error(f"Failed to create file: {e}")
        return None

def delete_file(file_path):
    try:
        os.remove(file_path)
        logging.info(f"File deleted: {file_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to delete file: {e}")
        return False

def git_operations(file_path):
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'add', file_path], check=True)
        subprocess.run(['git', 'commit', '-m', f'Added file {os.path.basename(file_path)}'], check=True)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        logging.info(f"Git operations successful for: {file_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git error: {e}")
    except Exception as e:
        logging.error(f"Error during Git operations: {e}")

def main():
    setup_logging()
    
    if not create_test_directory():
        logging.error("Failed to create test directory, exiting")
        return
    
    # Создаем первый файл
    file1 = create_file("file1.txt", "Это содержимое первого файла")
    if file1:
        git_operations(file1)
    
    # Создаем пустой файл
    empty_file = create_file("empty_file.txt", "")
    if empty_file:
        git_operations(empty_file)
    
    # Ждем 5 секунд для имитации повторного запуска
    logging.info("Simulating second run...")
    time.sleep(5)
    
    # Создаем второй файл
    file2 = create_file("file2.txt", "Это содержимое второго файла")
    if file2:
        git_operations(file2)
    
    # Создаем третий файл
    file3 = create_file("file3.txt", f"Случайное содержимое: {uuid.uuid4()}")
    if file3:
        git_operations(file3)
    
    # Удаляем пустой файл
    if empty_file:
        delete_file(empty_file)
        git_operations(empty_file)  # Попытка коммита удаленного файла
    
    logging.info("Script execution finished")

if __name__ == "__main__":
    try:
        main()
        print("✅ Script executed successfully")
    except Exception as e:
        logging.error(f"Critical error: {e}")
        print(f"❌ Script failed with error: {e}")
        raise
