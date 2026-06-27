import os
import sys
import json
import wave
import shutil
import argparse
from pathlib import Path
from vosk import Model, KaldiRecognizer
import subprocess
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

class VideoToTextConverter:
    def __init__(self, model_index=None):
        self.base_dir = Path(__file__).parent
        self.input_dir = self.base_dir / "input"
        self.output_dir = self.base_dir / "output"
        self.models_dir = self.base_dir / "models" / "vosk"
        
        # Создаем директории если их нет
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Получаем доступные модели
        self.available_models = self.get_available_models()
        
        # Если передан индекс модели - используем её
        if model_index is not None:
            self.model_path = self.select_model_by_index(model_index)
            if not self.model_path:
                print(f"Модель с индексом {model_index} не найдена!")
                print("Доступные модели (индексы с 0):")
                self.print_models_list()
                sys.exit(1)
        else:
            # Иначе используем первую доступную модель (индекс 0)
            self.model_path = self.available_models[0] if self.available_models else None
        
        # Проверяем наличие модели
        if not self.model_path:
            print("Модели не найдены. Запустите программу с параметром --model для просмотра моделей.")
            sys.exit(1)
            
        # Загружаем модель
        print(f"Используется модель: {self.model_path.name}")
        self.model = Model(str(self.model_path))
    
    def get_available_models(self):
        """Получаем список доступных моделей Vosk"""
        models = []
        for item in self.models_dir.iterdir():
            if item.is_dir():
                # Проверяем, что это модель Vosk
                if (item / "am" / "final.mdl").exists() or (item / "graph" / "HCLG.fst").exists():
                    models.append(item)
                # Или просто папка с файлами модели
                elif any(file.suffix in ['.mdl', '.fst', '.conf'] for file in item.iterdir()):
                    models.append(item)
        return sorted(models, key=lambda x: x.name.lower())
    
    def print_models_list(self):
        """Выводим список доступных моделей с индексами (0-based)"""
        if not self.available_models:
            print("  Нет доступных моделей")
            print("\nДля скачивания моделей запустите: python download_models.py")
            return
        
        print("\nДоступные модели (индексы с 0):")
        print("-" * 40)
        for i, model in enumerate(self.available_models):
            print(f"  [{i}] {model.name}")
        print("-" * 40)
        print("\nПример использования:")
        print("  python main.py --model 0 --parallel 2 --format txt")
    
    def select_model_by_index(self, model_index):
        """Выбираем модель по индексу (0-based)"""
        try:
            if 0 <= model_index < len(self.available_models):
                return self.available_models[model_index]
            return None
        except (ValueError, TypeError):
            return None
    
    def extract_audio(self, video_path, audio_path):
        """Извлекаем аудио из видео в формате WAV (моно, 16kHz)"""
        try:
            # Используем ffmpeg для конвертации в нужный формат
            cmd = [
                'ffmpeg', '-i', str(video_path),
                '-ar', '16000',  # Частота дискретизации
                '-ac', '1',      # Моно
                '-c:a', 'pcm_s16le',  # 16-bit PCM
                '-y',            # Перезаписать если существует
                str(audio_path)
            ]
            
            # Проверяем есть ли ffmpeg
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Если ffmpeg нет, используем moviepy (менее эффективно)
                print("FFmpeg не найден, используем moviepy (может быть медленнее)...")
                from moviepy import VideoFileClip
                video = VideoFileClip(str(video_path))
                video.audio.write_audiofile(str(audio_path), fps=16000, nbytes=2, codec='pcm_s16le')
                video.close()
                
            return True
        except Exception as e:
            print(f"Ошибка при извлечении аудио: {e}")
            return False
    
    def transcribe_audio_with_timestamps(self, audio_path):
        """Транскрибируем аудио с помощью Vosk с сохранением временных меток"""
        try:
            wf = wave.open(str(audio_path), "rb")
            
            # Проверяем формат аудио
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() not in [8000, 16000]:
                print(f"Неподдерживаемый формат аудио: каналы={wf.getnchannels()}, "
                      f"размер сэмпла={wf.getsampwidth()}, частота={wf.getframerate()}")
                wf.close()
                return "", []
            
            recognizer = KaldiRecognizer(self.model, wf.getframerate())
            recognizer.SetWords(True)  # Получаем слова с временными метками
            
            results = []
            
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    if 'result' in result:
                        results.extend(result['result'])
            
            # Получаем финальный результат
            final_result = json.loads(recognizer.FinalResult())
            if 'result' in final_result:
                results.extend(final_result['result'])
            
            wf.close()
            
            # Формируем текст из результатов
            full_text = " ".join([word.get('word', '') for word in results])
            return full_text.strip(), results
            
        except Exception as e:
            print(f"Ошибка при транскрибации: {e}")
            return "", []
    
    def format_timedelta(self, seconds):
        """Форматирует секунды в строку для SRT (ЧЧ:ММ:СС,ммм)."""
        try:
            td = timedelta(seconds=float(seconds))
            total_seconds = int(td.total_seconds())
            milliseconds = int((td.microseconds / 1000))
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
        except:
            return "00:00:00,000"
    
    def save_as_srt(self, results, output_path, video_path=None):
        """Сохраняет результаты распознавания в формате SRT"""
        if not results:
            print("Нет данных для создания SRT")
            return
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Группируем слова в субтитры (максимум 3 секунды или 10 слов)
            subtitle_index = 1
            current_group = []
            group_start = None
            
            for i, word_data in enumerate(results):
                if not current_group:
                    group_start = word_data.get('start', 0)
                
                current_group.append(word_data)
                
                # Проверяем условия для завершения группы:
                # 1. Больше 10 слов в группе
                # 2. Разница между первым и последним словом больше 3 секунд
                # 3. Это последнее слово
                group_end = word_data.get('end', 0)
                
                if (len(current_group) >= 10 or 
                    (group_end - group_start) >= 3.0 or 
                    i == len(results) - 1):
                    
                    # Формируем текст группы
                    text = ' '.join([w.get('word', '') for w in current_group])
                    
                    # Записываем номер субтитра
                    f.write(f"{subtitle_index}\n")
                    
                    # Записываем временные метки
                    start_time = self.format_timedelta(group_start)
                    end_time = self.format_timedelta(group_end)
                    f.write(f"{start_time} --> {end_time}\n")
                    
                    # Записываем текст
                    f.write(f"{text}\n\n")
                    
                    # Подготавливаемся к следующей группе
                    subtitle_index += 1
                    current_group = []
                    group_start = None
        
        print(f"Создано {subtitle_index-1} субтитров")
    
    def process_video(self, video_path, output_format="txt"):
        """Обрабатываем одно видео"""
        print(f"Обработка: {video_path.name}")
        
        # Создаем временный файл для аудио
        temp_audio = self.base_dir / f"temp_audio_{video_path.name}.wav"
        
        try:
            # 1. Извлекаем аудио
            if not self.extract_audio(video_path, temp_audio):
                return False
            
            # 2. Транскрибируем аудио с временными метками
            text, word_results = self.transcribe_audio_with_timestamps(temp_audio)
            
            if not text or not word_results:
                print(f"Не удалось извлечь текст из {video_path.name}")
                return False
            
            # 3. Сохраняем результат
            output_file = self.output_dir / f"{video_path.stem}.{output_format}"
            
            if output_format == "txt":
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(text)
            elif output_format == "srt":
                self.save_as_srt(word_results, output_file, video_path)
            elif output_format == "json":
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump({"text": text, "words": word_results, "source": video_path.name}, 
                              f, ensure_ascii=False, indent=2)
            
            print(f"✓ Текст сохранен в: {output_file.name}")
            return True
            
        finally:
            # Удаляем временный аудио файл
            if temp_audio.exists():
                temp_audio.unlink()
    
    def list_video_files(self):
        """Получаем список видео файлов в директории input"""
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.mpeg', '.mpg']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(self.input_dir.glob(f"*{ext}"))
            video_files.extend(self.input_dir.glob(f"*{ext.upper()}"))
        
        return sorted(video_files)
    
    def clear_input_directory(self):
        """Очищаем директорию input после обработки"""
        try:
            for item in self.input_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            print("✓ Директория input очищена")
        except Exception as e:
            print(f"Ошибка при очистке директории input: {e}")
    
    def process_all_videos(self, parallel=1, output_format="txt"):
        """Обрабатываем все видео файлы в директории input"""
        video_files = self.list_video_files()
        
        if not video_files:
            print("В директории input нет видео файлов")
            print(f"Поддерживаемые форматы: .mp4, .avi, .mkv, .mov, .wmv, .flv, .webm, .mpeg, .mpg")
            return
        
        print(f"Найдено видео файлов: {len(video_files)}")
        
        # Обрабатываем видео
        successful = 0
        failed = 0
        
        if parallel > 1 and len(video_files) > 1:
            # Параллельная обработка
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_video = {
                    executor.submit(self.process_video, video, output_format): video 
                    for video in video_files
                }
                
                for future in as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        if future.result():
                            successful += 1
                        else:
                            failed += 1
                    except Exception as e:
                        print(f"Ошибка при обработке {video.name}: {e}")
                        failed += 1
        else:
            # Последовательная обработка
            for video in video_files:
                if self.process_video(video, output_format):
                    successful += 1
                else:
                    failed += 1
        
        # Очищаем директорию input
        if successful > 0:
            self.clear_input_directory()
        
        print(f"\nОбработка завершена:")
        print(f"  Успешно: {successful}")
        print(f"  Не удалось: {failed}")
        
        return successful, failed

def main():
    parser = argparse.ArgumentParser(
        description="Извлечение текста из видео с помощью Vosk",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py --model               # Показать список доступных моделей (индексы с 0)
  python main.py --model 0             # Использовать модель №0
  python main.py --model 1 --format srt  # Модель №1, сохранять в SRT
  python main.py --parallel 2          # Параллельная обработка (2 потока)
  python main.py --help                # Показать эту справку

Форматы вывода:
  txt   - обычный текстовый файл (по умолчанию)
  srt   - субтитры
  json  - JSON формат с метаданными
        """
    )
    
    parser.add_argument("--model", nargs='?', const='list', metavar='INDEX',
                       help="Показать список моделей (если без значения) или использовать модель по индексу")
    parser.add_argument("--parallel", type=int, default=1, 
                       help="Количество параллельных процессов (по умолчанию: 1)")
    parser.add_argument("--format", choices=["txt", "srt", "json"], default="txt",
                       help="Формат выходного файла (по умолчанию: txt)")
    
    args = parser.parse_args()
    
    # Специальная обработка параметра --model
    if args.model == 'list':
    # не создаём конвертер, просто выводим список
        models_dir = Path(__file__).parent / "models" / "vosk"
        models = sorted([d for d in models_dir.iterdir() if d.is_dir()])
        for i, m in enumerate(models):
            print(f"[{i}] {m.name}")
        return
    
    # Если указан индекс модели, проверяем его корректность
    model_index = None
    if args.model is not None:
        try:
            model_index = int(args.model)
            if model_index < 0:
                print("Ошибка: индекс модели должен быть неотрицательным числом")
                return
        except ValueError:
            print(f"Ошибка: '{args.model}' не является корректным индексом модели")
            print("Используйте '--model' без значения для просмотра списка моделей")
            return
    
    try:
        # Создаем конвертер
        converter = VideoToTextConverter(model_index)
        
        # Обрабатываем видео
        converter.process_all_videos(parallel=args.parallel, output_format=args.format)
        
    except KeyboardInterrupt:
        print("\nОбработка прервана пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Проверяем, установлены ли необходимые библиотеки
    try:
        import vosk
        from moviepy import VideoFileClip
    except ImportError as e:
        print(f"Не установлены необходимые библиотеки: {e}")
        print("Установите их командой: pip install vosk moviepy")
        if input("Установить сейчас? (y/n): ").lower() == 'y':
            import subprocess
            subprocess.run([sys.executable, "-m", "pip", "install", "vosk", "moviepy"])
        else:
            sys.exit(1)
    
    main()
