import os
import sys
import zipfile
import shutil
from pathlib import Path
from urllib.request import urlretrieve
from transformers import AutoTokenizer, AutoModelForCausalLM

# Конфигурация
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
MODEL_DIR = Path("models") / "vosk"
TEMP_DIR = Path("temp_vosk_extract")

def download_model():
    """Загрузка и распаковка модели Vosk"""
    try:
        # Создаем целевую папку для модели
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Проверка существования модели
        if any(MODEL_DIR.iterdir()):
            return True
            
        # Создаем временную папку для распаковки
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = TEMP_DIR / "model.zip"
        
        # Скачивание модели
        urlretrieve(MODEL_URL, zip_path)
        
        # Распаковка архива во временную папку
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(TEMP_DIR)
        
        # Удаление временного zip-файла
        zip_path.unlink()
        
        # Поиск основной папки с моделью
        model_folders = list(TEMP_DIR.glob("vosk-model-small-ru-*"))
        if not model_folders:
            raise FileNotFoundError("Не найдена папка с моделью в архиве")
            
        source_dir = model_folders[0]
        
        # Перенос содержимого в целевую директорию
        for item in source_dir.iterdir():
            dest = MODEL_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        
        # Удаление временных файлов
        shutil.rmtree(TEMP_DIR)
        
        return True
        
    except Exception as e:
        # Удаление временных файлов при ошибке
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR)
        print(f"Ошибка: {str(e)}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if download_model():
        sys.exit(0)
    else:
        sys.exit(1)
