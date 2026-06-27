import os
import sys
import json
import subprocess
import shutil
import threading
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog, messagebox, scrolledtext
import tkinterdnd2 as tkdnd

class VideoToTextGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video to Text Converter")
        self.root.geometry("950x900")  # Увеличил высоту еще больше
        self.root.minsize(850, 850)
        
        # Основные директории
        self.base_dir = Path(__file__).parent
        self.input_dir = self.base_dir / "input"
        self.output_dir = self.base_dir / "output"
        
        # Создаем директории если их нет
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Получаем информацию о процессоре
        self.cpu_info = self.get_cpu_info()
        
        # Определяем безопасные ограничения для GUI
        self.max_parallel_gui = max(1, self.cpu_info['physical'] - 1)
        self.min_parallel_gui = 1
        
        # Переменные для хранения состояния
        self.models = []
        self.processing = False
        self.default_drop_bg = "#d9d9d9"  # Цвет по умолчанию для Drag-and-Drop
        
        # Настройка стиля
        self.setup_styles()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Загружаем модели при старте
        self.load_models()
        
        # Настраиваем Drag-and-Drop
        self.setup_drag_and_drop()
        
        # Обновляем список файлов
        self.update_file_list()
    
    def get_cpu_info(self):
        """Получение информации о CPU"""
        try:
            # Количество логических ядер (потоков)
            logical_cores = os.cpu_count() or 1
            
            # Попытка определить физические ядра
            physical_cores = logical_cores
            
            # Для Linux можно попробовать определить через /proc/cpuinfo
            if sys.platform == "linux":
                try:
                    with open('/proc/cpuinfo', 'r') as f:
                        cpuinfo = f.read()
                    # Подсчитываем уникальные physical id
                    physical_ids = set()
                    for line in cpuinfo.split('\n'):
                        if 'physical id' in line:
                            physical_ids.add(line.strip())
                    if physical_ids:
                        physical_cores = len(physical_ids)
                except:
                    pass
            
            # Эмпирическое правило для гипертрединга
            if logical_cores % 2 == 0 and logical_cores > 1:
                physical_cores = logical_cores // 2
            
            # Для одноядерных процессоров
            if physical_cores <= 1:
                max_recommended = 1
            else:
                # Оставляем одно ядро для системы
                max_recommended = physical_cores - 1
            
            return {
                'logical': logical_cores,
                'physical': physical_cores,
                'max_recommended': max_recommended,
                'has_hyperthreading': logical_cores > physical_cores
            }
        except:
            # Консервативные значения по умолчанию
            return {
                'logical': 4,
                'physical': 2,
                'max_recommended': 1,
                'has_hyperthreading': False
            }
    
    def setup_styles(self):
        """Настройка стилей виджетов"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Цветовая схема
        self.bg_color = "#f0f0f0"
        self.frame_bg = "#ffffff"
        self.accent_color = "#0078d7"
        
        self.root.configure(bg=self.bg_color)
    
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        
        # Главный контейнер
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(N, S, E, W))
        
        # Настройка веса строк и столбцов
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)  # Строка с логами будет расширяться
        
        # 1. Заголовок
        title_label = ttk.Label(
            main_frame, 
            text="Video to Text Converter", 
            font=("Segoe UI", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 15), sticky=W)
        
        # 2. Область для Drag-and-Drop
        drop_frame = ttk.LabelFrame(main_frame, text="Файлы для обработки", padding="10")
        drop_frame.grid(row=1, column=0, sticky=(E, W), pady=(0, 15))
        drop_frame.columnconfigure(0, weight=1)
        
        # Инструкция для Drag-and-Drop
        drop_label = ttk.Label(
            drop_frame,
            text="Перетащите видео файлы сюда\nили используйте кнопку 'Выбрать файлы'",
            font=("Segoe UI", 10),
            anchor=CENTER,
            relief="ridge",
            padding=20,
            background=self.default_drop_bg
        )
        drop_label.grid(row=0, column=0, sticky=(E, W), pady=(0, 10))
        self.drop_label = drop_label
        
        # Кнопка выбора файлов
        btn_frame = ttk.Frame(drop_frame)
        btn_frame.grid(row=1, column=0, sticky=W)
        
        ttk.Button(
            btn_frame,
            text="Выбрать файлы",
            command=self.select_files
        ).pack(side=LEFT, padx=(0, 10))
        
        ttk.Button(
            btn_frame,
            text="Обновить список",
            command=self.update_file_list
        ).pack(side=LEFT, padx=(0, 10))
        
        ttk.Button(
            btn_frame,
            text="Очистить все",
            command=self.clear_all_files
        ).pack(side=LEFT)
        
        # Список выбранных файлов
        self.file_listbox = Listbox(
            drop_frame,
            height=5,
            selectmode=MULTIPLE,
            bg="white",
            relief="solid",
            borderwidth=1
        )
        self.file_listbox.grid(row=2, column=0, sticky=(E, W), pady=(10, 0))
        
        # Scrollbar для списка файлов
        scrollbar = Scrollbar(drop_frame, orient=VERTICAL)
        scrollbar.grid(row=2, column=1, sticky=(N, S), pady=(10, 0))
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Кнопки управления файлами
        file_btn_frame = ttk.Frame(drop_frame)
        file_btn_frame.grid(row=3, column=0, sticky=W, pady=(5, 0))
        
        ttk.Button(
            file_btn_frame,
            text="Удалить выбранные",
            command=self.delete_selected_files
        ).pack(side=LEFT, padx=(0, 10))
        
        ttk.Button(
            file_btn_frame,
            text="Открыть папку input",
            command=lambda: self.open_folder(self.input_dir)
        ).pack(side=LEFT)
        
        # 3. Панель параметров
        params_frame = ttk.LabelFrame(main_frame, text="Параметры обработки", padding="10")
        params_frame.grid(row=2, column=0, sticky=(E, W), pady=(0, 15))
        for i in range(4):
            params_frame.columnconfigure(i, weight=1)
        
        # Выбор модели
        ttk.Label(params_frame, text="Модель распознавания:").grid(
            row=0, column=0, sticky=W, pady=5
        )
        
        self.model_var = StringVar()
        self.model_combo = ttk.Combobox(
            params_frame,
            textvariable=self.model_var,
            state="readonly",
            width=35
        )
        self.model_combo.grid(row=0, column=1, sticky=(E, W), padx=(10, 10), pady=5)
        
        # Кнопка "Обновить модели" выровнена по правому краю
        ttk.Button(
            params_frame,
            text="Обновить модели",
            command=self.load_models,
            width=15
        ).grid(row=0, column=3, padx=(0, 0), pady=5, sticky=E)
        
        # Параллельные поток
        ttk.Label(params_frame, text="Параллельных потоков:").grid(
            row=1, column=0, sticky=W, pady=5
        )
        
        # Spinbox с безопасными пределами
        self.parallel_var = StringVar(value=str(self.min_parallel_gui))
        
        self.parallel_spin = Spinbox(
            params_frame,
            from_=self.min_parallel_gui,
            to=self.max_parallel_gui,
            textvariable=self.parallel_var,
            width=8,
            validate="key",
            validatecommand=(self.root.register(self.validate_parallel_gui), '%P')
        )
        self.parallel_spin.grid(row=1, column=1, sticky=W, padx=(10, 10), pady=5)
        
        # Информация о процессоре
        cpu_info_text = f"Процессор: {self.cpu_info['physical']} ядер"
        if self.cpu_info['has_hyperthreading']:
            cpu_info_text += f" ({self.cpu_info['logical']} потоков)"
        
        cpu_label = ttk.Label(
            params_frame,
            text=cpu_info_text,
            font=("Segoe UI", 8)
        )
        cpu_label.grid(row=1, column=2, sticky=W, padx=(5, 0), pady=5)
        
        # Кнопка "Рекомендованные" увеличена - ВЕРНУЛ КАК БЫЛО
        ttk.Button(
            params_frame,
            text="Рекомендованные настройки",
            command=self.apply_recommended_settings,
            width=25
        ).grid(row=1, column=3, padx=(5, 0), pady=5, sticky=E)
        
        # Формат вывода
        ttk.Label(params_frame, text="Формат вывода:").grid(
            row=2, column=0, sticky=W, pady=5
        )
        
        self.format_var = StringVar(value="txt")
        format_frame = ttk.Frame(params_frame)
        format_frame.grid(row=2, column=1, sticky=W, padx=(10, 0), pady=5)
        
        ttk.Radiobutton(
            format_frame,
            text="TXT",
            variable=self.format_var,
            value="txt"
        ).pack(side=LEFT, padx=(0, 10))
        
        ttk.Radiobutton(
            format_frame,
            text="SRT",
            variable=self.format_var,
            value="srt"
        ).pack(side=LEFT, padx=(0, 10))
        
        ttk.Radiobutton(
            format_frame,
            text="JSON",
            variable=self.format_var,
            value="json"
        ).pack(side=LEFT)
        
        # Кнопка "Открыть папку output" выровнена по правому краю
        ttk.Button(
            params_frame,
            text="Открыть папку output",
            command=lambda: self.open_folder(self.output_dir),
            width=20
        ).grid(row=2, column=2, columnspan=2, padx=(10, 0), pady=5, sticky=E)
        
        # 4. Кнопки управления (оставим как было - без центрирования)
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, sticky=W, pady=(15, 15))
        
        # Кнопка запуска обработки
        self.start_button = ttk.Button(
            control_frame,
            text="Запустить обработку",
            command=self.start_processing,
            style="Accent.TButton",
            width=20
        )
        self.start_button.pack(side=LEFT, padx=(0, 10))
        
        # Кнопка выхода
        self.exit_button = ttk.Button(
            control_frame,
            text="Выход",
            command=self.root.quit,
            width=10
        )
        self.exit_button.pack(side=LEFT)
        
        # 5. Область вывода логов
        log_frame = ttk.LabelFrame(main_frame, text="Лог обработки", padding="10")
        log_frame.grid(row=4, column=0, sticky=(N, S, E, W), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            width=80,
            height=20,  # Увеличил высоту логов еще больше
            bg="white",
            relief="solid",
            borderwidth=1
        )
        self.log_text.grid(row=0, column=0, sticky=(N, S, E, W))
        
        # 6. Прогресс-бар
        self.progress_var = DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100,
            mode='indeterminate'
        )
        self.progress_bar.grid(row=5, column=0, sticky=(E, W), pady=(0, 10))
        self.progress_bar.grid_remove()
        
        # 7. Статус
        self.status_var = StringVar(value="Готов к работе")
        status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief="sunken",
            padding=5
        )
        status_label.grid(row=6, column=0, sticky=(E, W))
        
        # После создания всех виджетов обновляем геометрию
        self.root.update_idletasks()
    
    def setup_drag_and_drop(self):
        """Настройка Drag-and-Drop функционала"""
        # Регистрируем поддержку перетаскивания
        self.drop_label.drop_target_register(tkdnd.DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self.on_drop)
        
        # Меняем внешний вид при наведении
        def on_drag_enter(event):
            self.drop_label.configure(background="#e3f2fd")
        
        def on_drag_leave(event):
            self.drop_label.configure(background=self.default_drop_bg)
        
        self.drop_label.bind('<Enter>', on_drag_enter)
        self.drop_label.bind('<Leave>', on_drag_leave)
    
    def validate_parallel_gui(self, new_value):
        """Валидация ввода количества потоков для GUI"""
        if new_value == "":
            return True
        
        try:
            value = int(new_value)
            
            # Жесткие ограничения для GUI
            if value < self.min_parallel_gui:
                return False
            
            if value > self.max_parallel_gui:
                # Показываем объяснение в логе
                if value > self.cpu_info['physical']:
                    self.log_message(
                        f"⚠️ В GUI ограничение: {self.max_parallel_gui} потоков "
                        f"(оставляем 1 ядро для системы). Используйте CLI для большего."
                    )
                return False
                
            return True
            
        except ValueError:
            return False
    
    def on_drop(self, event):
        """Обработка события перетаскивания файлов"""
        files = self.root.tk.splitlist(event.data)
        success_count = 0
        
        for file_path in files:
            if self.copy_file_to_input(file_path):
                success_count += 1
        
        if success_count > 0:
            self.update_file_list()
            self.log_message(f"Добавлено файлов: {success_count}")
    
    def copy_file_to_input(self, source_path):
        """Копирование файла в директорию input"""
        try:
            source = Path(source_path)
            if not source.exists():
                return False
            
            # Проверяем расширение
            valid_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', 
                               '.flv', '.webm', '.mpeg', '.mpg']
            if source.suffix.lower() not in valid_extensions:
                self.log_message(f"Пропущен {source.name}: неподдерживаемый формат")
                return False
            
            # Генерируем уникальное имя, если файл уже существует
            dest_path = self.input_dir / source.name
            counter = 1
            while dest_path.exists():
                name_parts = source.stem, source.suffix
                dest_path = self.input_dir / f"{name_parts[0]}_{counter}{name_parts[1]}"
                counter += 1
            
            # Копируем файл
            shutil.copy2(source, dest_path)
            return True
            
        except Exception as e:
            self.log_message(f"Ошибка копирования {source_path}: {str(e)}")
            return False
    
    def select_files(self):
        """Открытие диалога выбора файлов"""
        filetypes = [
            ("Видео файлы", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mpeg *.mpg"),
            ("Все файлы", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Выберите видео файлы",
            filetypes=filetypes
        )
        
        if files:
            success_count = 0
            for file_path in files:
                if self.copy_file_to_input(file_path):
                    success_count += 1
            
            if success_count > 0:
                self.update_file_list()
                self.log_message(f"Добавлено файлов: {success_count}")
    
    def update_file_list(self):
        """Обновление списка файлов в интерфейсе"""
        self.file_listbox.delete(0, END)
        
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', 
                           '.flv', '.webm', '.mpeg', '.mpg']
        
        for ext in video_extensions:
            for file in self.input_dir.glob(f"*{ext}"):
                self.file_listbox.insert(END, file.name)
            for file in self.input_dir.glob(f"*{ext.upper()}"):
                self.file_listbox.insert(END, file.name)
    
    def delete_selected_files(self):
        """Удаление выбранных файлов"""
        selected = self.file_listbox.curselection()
        if not selected:
            messagebox.showwarning("Внимание", "Не выбраны файлы для удаления")
            return
        
        if messagebox.askyesno("Подтверждение", 
                               f"Удалить {len(selected)} выбранных файлов?"):
            for index in reversed(selected):
                filename = self.file_listbox.get(index)
                file_path = self.input_dir / filename
                if file_path.exists():
                    try:
                        file_path.unlink()
                        self.file_listbox.delete(index)
                        self.log_message(f"Удален: {filename}")
                    except Exception as e:
                        messagebox.showerror("Ошибка", f"Не удалось удалить {filename}: {str(e)}")
    
    def clear_all_files(self):
        """Очистка всех файлов из input"""
        if not any(self.input_dir.iterdir()):
            return
        
        if messagebox.askyesno("Подтверждение", 
                               "Очистить всю директорию input?"):
            try:
                for file in self.input_dir.iterdir():
                    if file.is_file():
                        file.unlink()
                self.update_file_list()
                self.log_message("Директория input очищена")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось очистить директорию: {str(e)}")
    
    def open_folder(self, folder_path):
        """Открытие папки в файловом менеджере"""
        try:
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder_path])
            else:
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку: {str(e)}")
    
    def load_models(self):
        """Загрузка списка доступных моделей"""
        self.log_message("Загрузка списка моделей...")
        
        try:
            # Запускаем main.py для получения списка моделей
            result = subprocess.run(
                [sys.executable, "main.py", "--model"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                cwd=self.base_dir,
                timeout=10
            )
            
            self.models = []
            model_names = []
            
            # Парсим вывод
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('[') and ']' in line:
                    # Формат: "[0] vosk-model-small-ru-0.22"
                    parts = line.split(']', 1)
                    if len(parts) == 2:
                        index = parts[0].replace('[', '').strip()
                        name = parts[1].strip()
                        self.models.append((index, name))
                        model_names.append(f"[{index}] {name}")
            
            if not self.models:
                model_names = ["Модели не найдены. Запустите download_models.py"]
                self.models = [("0", "Модель не найдена")]
            
            # Обновляем ComboBox
            self.model_combo['values'] = model_names
            if model_names:
                self.model_combo.current(0)
            
            self.log_message(f"Загружено моделей: {len(self.models)}")
            
        except subprocess.TimeoutExpired:
            self.log_message("Ошибка: таймаут при загрузке моделей")
            self.model_combo['values'] = ["Ошибка загрузки"]
        except Exception as e:
            self.log_message(f"Ошибка загрузки моделей: {str(e)}")
            self.model_combo['values'] = ["Ошибка загрузки"]
    
    def apply_recommended_settings(self):
        """Применение рекомендованных настройек"""
        file_count = self.file_listbox.size()
        
        # Для одного файла - 1 поток
        if file_count == 0 or file_count == 1:
            recommended_parallel = 1
            self.log_message("Рекомендация: 1 поток (для одного видео)")
        else:
            # Для нескольких файлов: min(файлы, max_parallel_gui)
            recommended_parallel = min(file_count, self.max_parallel_gui)
            self.log_message(
                f"Рекомендация: {recommended_parallel} потоков "
                f"(на основе {file_count} файлов и {self.cpu_info['physical']} ядер)"
            )
        
        self.parallel_var.set(str(recommended_parallel))
        
        # Формат по умолчанию
        self.format_var.set("txt")
        
        self.log_message("Применены рекомендованные настройки")
    
    def log_message(self, message):
        """Добавление сообщения в лог"""
        self.log_text.insert(END, f"{message}\n")
        self.log_text.see(END)
        self.root.update_idletasks()
    
    def start_processing(self):
        """Запуск обработки видео"""
        if self.processing:
            return
        
        # Проверяем, есть ли файлы для обработки
        if self.file_listbox.size() == 0:
            messagebox.showwarning("Внимание", "Нет файлов для обработки!")
            return
        
        # Проверяем выбор модели
        if not self.models or self.models[0][1] == "Модель не найдена":
            messagebox.showwarning("Внимание", "Не выбрана модель распознавания!")
            return
        
        # Получаем параметры
        model_selection = self.model_combo.get()
        if not model_selection:
            messagebox.showwarning("Внимание", "Не выбрана модель!")
            return
        
        # Извлекаем индекс модели (формат: "[0] model-name")
        try:
            model_index = model_selection.split(']')[0].replace('[', '')
        except:
            model_index = "0"
        
        # Получаем количество потоков с учетом ограничений GUI
        try:
            parallel_text = self.parallel_var.get()
            if not parallel_text or parallel_text.strip() == "":
                parallel = self.min_parallel_gui
            else:
                parallel = int(parallel_text)
                
            # Принудительно ограничиваем значениями GUI
            if parallel < self.min_parallel_gui:
                parallel = self.min_parallel_gui
                self.parallel_var.set(str(parallel))
                
            if parallel > self.max_parallel_gui:
                parallel = self.max_parallel_gui
                self.parallel_var.set(str(parallel))
                self.log_message(
                    f"Автокоррекция: количество потоков ограничено {self.max_parallel_gui} "
                    f"(максимум для графического интерфейса)"
                )
                
        except ValueError:
            parallel = self.min_parallel_gui
            self.parallel_var.set(str(parallel))
        
        # Для одного видео всегда используем 1 поток (сообщаем пользователю)
        file_count = self.file_listbox.size()
        if file_count == 1 and parallel > 1:
            self.log_message(
                "Примечание: для одного видео программа использует 1 поток. "
                "Параллельная обработка актуальна только для нескольких файлов."
            )
            parallel = 1
            self.parallel_var.set("1")
        
        output_format = self.format_var.get()
        
        # Информация о системе
        self.log_message(f"Система: {self.cpu_info['physical']} ядер процессора")
        if self.cpu_info['has_hyperthreading']:
            self.log_message(f"Поддержка многопоточности: {self.cpu_info['logical']} потоков")
        self.log_message(f"Будет использовано: {parallel} параллельных потоков")
        
        # Подтверждение запуска
        if not messagebox.askyesno("Подтверждение", 
                                   f"Начать обработку {file_count} файлов?\n"
                                   f"Модель: {model_selection}\n"
                                   f"Потоков: {parallel}\n"
                                   f"Формат: {output_format}"):
            return
        
        # Запускаем обработку в отдельном потоке
        self.processing = True
        self.start_button.config(state=DISABLED)
        self.exit_button.config(state=DISABLED)
        self.progress_bar.grid()
        self.progress_bar.start()
        self.status_var.set("Обработка...")
        self.log_text.delete(1.0, END)
        
        thread = threading.Thread(
            target=self.run_conversion,
            args=(model_index, parallel, output_format),
            daemon=True
        )
        thread.start()
    
    def run_conversion(self, model_index, parallel, output_format):
        """Запуск конвертации в отдельном потоке"""
        try:
            # Формируем команду для CLI
            cmd = [sys.executable, "main.py"]
            
            if model_index:
                cmd.extend(["--model", str(model_index)])
            
            if parallel > 1:
                cmd.extend(["--parallel", str(parallel)])
            
            if output_format != "txt":
                cmd.extend(["--format", output_format])
            
            self.log_message("=" * 50)
            self.log_message("Запуск обработки...")
            self.log_message(f"Команда: {' '.join(cmd)}")
            self.log_message("=" * 50)
            
            # Запускаем процесс
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                universal_newlines=True,
                cwd=self.base_dir
            )
            
            # Читаем вывод в реальном времени
            for line in iter(process.stdout.readline, ''):
                self.root.after(0, self.log_message, line.strip())
            
            process.stdout.close()
            return_code = process.wait()
            
            self.root.after(0, self.on_processing_finished, return_code)
            
        except Exception as e:
            self.root.after(0, self.on_processing_error, str(e))
    
    def on_processing_finished(self, return_code):
        """Обработка завершения конвертации"""
        self.processing = False
        self.start_button.config(state=NORMAL)
        self.exit_button.config(state=NORMAL)
        self.progress_bar.stop()
        self.progress_bar.grid_remove()
        
        self.log_message("=" * 50)
        if return_code == 0:
            self.log_message("✅ Обработка успешно завершена!")
            self.status_var.set("Готово!")
            messagebox.showinfo("Успех", "Обработка видео завершена успешно!")
            
            # Обновляем список файлов (input должен быть пуст)
            self.update_file_list()
        else:
            self.log_message(f"❌ Обработка завершена с кодом ошибки: {return_code}")
            self.status_var.set("Ошибка!")
            messagebox.showerror("Ошибка", 
                               f"Обработка завершена с ошибкой (код: {return_code})")
    
    def on_processing_error(self, error_message):
        """Обработка ошибки при конвертации"""
        self.processing = False
        self.start_button.config(state=NORMAL)
        self.exit_button.config(state=NORMAL)
        self.progress_bar.stop()
        self.progress_bar.grid_remove()
        
        self.log_message("=" * 50)
        self.log_message(f"❌ Критическая ошибка: {error_message}")
        self.status_var.set("Ошибка!")
        messagebox.showerror("Ошибка", f"Критическая ошибка: {error_message}")

def main():
    """Точка входа в программу"""
    try:
        # Проверяем наличие основного скрипта
        if not Path("main.py").exists():
            messagebox.showerror(
                "Ошибка", 
                "Файл main.py не найден!\n"
                "Разместите gui.py в той же папке, что и main.py"
            )
            return
        
        # Создаем и запускаем GUI
        root = tkdnd.TkinterDnD.Tk()
        app = VideoToTextGUI(root)
        
        # Центрируем окно
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        root.mainloop()
        
    except ImportError as e:
        print(f"Ошибка импорта: {e}")
        print("Установите tkinterdnd2: pip install tkinterdnd2")
        print("Для Linux также может потребоваться: sudo apt-get install python3-tk")
    except Exception as e:
        messagebox.showerror("Критическая ошибка", f"Не удалось запустить GUI: {str(e)}")

if __name__ == "__main__":
    main()
