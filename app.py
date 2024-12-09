from tkinter import font
import tkinter as tk
from tkinter import ttk
import psycopg2
import json
import os
import schedule
import time
import threading
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw, ImageTk
from plyer import notification
from tkcalendar import Calendar
from datetime import datetime
import re
import tkinter.messagebox as messagebox
import logging
import psycopg2

# === Импорт конфигурации базы данных ===
from db_config import DB_CONFIG
from config import ICON_PATH

# === Настройка логирования ===
logging.basicConfig(
    filename="app.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.info("Приложение запущено.")

# === Путь к конфигурационному файлу ===
CONFIG_FILE = "window_config.json"

# === Функции работы с БД ===
def init_db():
    try:
        conn = psycopg2.connect(connect_timeout=10, **DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task TEXT NOT NULL,
                time VARCHAR(5) NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                completed BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()
        logging.info("База данных инициализирована успешно.")
    except Exception as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        cursor.close()
        conn.close()

def convert_date_for_db(date):
    try:
        return datetime.strptime(date, "%m/%d/%y").strftime("%Y-%m-%d")
    except ValueError:
        return None

def add_task_to_db(task, time, date, description=None):
    date = convert_date_for_db(date)
    if date:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (task, time, date, description) VALUES (%s, %s, %s, %s)",
                (task, time, date, description)
            )
            conn.commit()
            logging.info(f"Добавлена задача: {task} на {date} в {time}.")
        except Exception as e:
            logging.error(f"Ошибка при добавлении задачи: {e}")
        finally:
            cursor.close()
            conn.close()
    else:
        logging.warning("Некорректная дата задачи.")

def toggle_task_completion(task, date, completed):
    date = convert_date_for_db(date)
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET completed = %s WHERE task = %s AND date = %s",
        (completed, task, date)
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_tasks_from_db(date):
    date = convert_date_for_db(date)
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT task, time, completed, description FROM tasks WHERE date = %s ORDER BY time", (date,))
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return tasks

def delete_task_from_db(task, date):
    date = convert_date_for_db(date)
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE task = %s AND date = %s", (task, date))
    conn.commit()
    cursor.close()
    conn.close()

# === Уведомления ===
def notify(task):
    notification.notify(
        title="Напоминание",
        message=task,
        app_name="Ежедневник",
        timeout=10
    )

def check_tasks():
    tasks = get_tasks_from_db()
    current_time = time.strftime("%H:%M")
    for task in tasks:
        if task[1] == current_time:
            notify(task[0])

def schedule_checker():
    while True:
        schedule.run_pending()
        time.sleep(1)

# === Конфигурация окна ===
def save_window_config(x, y):
    config = {"x": x, "y": y}
    with open(CONFIG_FILE, "w") as file:
        json.dump(config, file)

def load_window_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as file:
            return json.load(file)
    return {"x": 100, "y": 100}

# === Виджет ===
class PlannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ежедневник")
        self.geometry("550x700")
        self.overrideredirect(True)
        self.configure(bg="#1E1E2F")  # Фон окна

        # Темная тема для элементов
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#112031",
            foreground="#00ffcc",
            fieldbackground="#112031",
            font=("Arial", 12)
        )
        style.configure(
            "Treeview.Heading",
            background="#0b0e23",
            foreground="#00f7ff",
            font=("Arial", 14, "bold")
        )
        style.configure(
            "TButton",
            background="#112031",
            foreground="#00ffcc",
            font=("Arial", 10, "bold"),
            relief="flat"
        )
        style.map("TButton", background=[("active", "#00a8a8")])

        style.configure(
            "Custom2.TButton",
            background="#69b7a8",
            foreground="#000000",
            font=("Arial", 10, "bold"),
            relief="flat"
        )
        style.map("Custom2.TButton", background=[("active", "#5aa096")])

        # Верхняя панель (заголовок)
        self.header = tk.Frame(self, bg="#0b0e23", relief="raised", bd=2)
        self.header.pack(fill=tk.X, pady=2)

        self.move_button = ttk.Button(self.header, text="🔒", command=self.enable_movement, width=2)
        self.move_button.pack(side=tk.LEFT, padx=10)

        tk.Label(
            self.header,
            text="Ежедневник",
            bg="#0b0e23",
            fg="#00ffcc",
            font=("Arial", 20, "bold")
        ).pack(side=tk.LEFT, padx=10)

        close_btn = ttk.Button(self.header, text="⨉", command=self.minimize_to_tray)
        close_btn.pack(side=tk.RIGHT, padx=10)

        self.confirm_button = ttk.Button(self.header, text="✔", command=self.confirm_new_position, width=2)
        self.confirm_button.pack(side=tk.LEFT, padx=5)
        self.confirm_button.pack_forget()

        # Календарь
        today = datetime.today()
        self.calendar = Calendar(
            self,
            selectmode="day",
            year=today.year,
            month=today.month,
            day=today.day,
            background="#112031",
            foreground="#00ffcc",
            headersbackground="#0b0e23",
            headersforeground="#00f7ff",
            font=("Arial", 12),
            weekendbackground="#0b0e23",
            selectbackground="#00ffcc",
        )
        self.calendar.pack(pady=10, padx=10)
        self.calendar.bind("<<CalendarSelected>>", self.on_date_select)

        # Таблица задач
        self.tree = ttk.Treeview(self, columns=("time", "task", "completed"), show="headings")
        self.tree.heading("time", text="Время")
        self.tree.heading("task", text="Задача")
        self.tree.heading("completed", text="Статус")
        self.tree.column("time", width=55)
        self.tree.column("task", width=350)
        self.tree.column("completed", width=60)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        self.tree.bind("<ButtonRelease-1>", self.on_toggle_task_completion)
        self.tree.bind("<Double-1>", self.on_task_double_click)

        # Форма ввода
        button_frame = tk.Frame(self, bg="#1E1E2F")
        button_frame.pack(fill=tk.X, padx=5, pady=5)

# Создаем контейнер для центровки кнопок
        button_container = tk.Frame(button_frame, bg="#1E1E2F")
        button_container.pack(anchor="center")

        add_task_button = ttk.Button(button_container, text="Добавить задачу", command=self.open_task_creation_window, style="Custom2.TButton")
        add_task_button.pack(side=tk.LEFT, padx=10, pady=5)

        delete_button = ttk.Button(button_container, text="Удалить", command=self.delete_task, style="Custom2.TButton")
        delete_button.pack(side=tk.LEFT, padx=10, pady=5)

        # Загрузка задач для выбранной даты
        self.selected_date = self.calendar.get_date()
        self.update_task_list()

        # Перемещение окна
        self.start_x = 0
        self.start_y = 0
        self.can_move = False
        
    def enable_movement(self):
        self.can_move = True
        self.confirm_button.pack(side=tk.LEFT, padx=5)
        self.move_button.config(state=tk.DISABLED)
        self.header.bind("<ButtonPress-1>", self.start_move)
        self.header.bind("<B1-Motion>", self.do_move)

    def confirm_new_position(self):
        self.can_move = False
        self.confirm_button.pack_forget()
        self.move_button.config(state=tk.NORMAL)
        self.header.unbind("<ButtonPress-1>")
        self.header.unbind("<B1-Motion>")
        x = self.winfo_x()
        y = self.winfo_y()
        save_window_config(x, y)

    def on_date_select(self, event):
        self.selected_date = self.calendar.get_date()
        logging.info(f"Выбрана дата: {self.selected_date}")
        self.update_task_list()

    def add_task(self):
        task = self.task_entry.get().strip()
        time_str = self.time_entry.get().strip()
        date = self.selected_date

        if task and time_str and date:
            try:
                add_task_to_db(task, time_str, date)
                logging.info(f"Пользователь добавил задачу: {task} на {date} в {time_str}.")
            except Exception as e:
                logging.error(f"Ошибка при добавлении задачи через интерфейс: {e}")
            self.update_task_list()
        else:
            logging.warning("Попытка добавить задачу с неполными данными.")

    def delete_task(self):
        selected_item = self.tree.selection()
        if selected_item:
            task = self.tree.item(selected_item[0], "values")[1]
            date = self.selected_date
            delete_task_from_db(task, date)
            self.update_task_list()

    def update_task_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        tasks = get_tasks_from_db(self.selected_date)
        completed_font = font.Font(family="Helvetica", size=18, weight="normal")  # Настроим шрифт вручную
        completed_font.config(overstrike=True)        
        for task in tasks:
            completed_text = "✔" if task[2] else "✘"
            self.tree.insert("", tk.END, values=(task[1], task[0], completed_text), tags=("completed" if task[2] else "not_completed"))        
        self.tree.tag_configure("completed", font=completed_font)
        self.tree.tag_configure("not_completed", font=("Helvetica", 18))  # Устанавливаем обычный шрифт для невыполненных задач

    def on_toggle_task_completion(self, event):
        selected_item = self.tree.selection()
        if selected_item:
        # Получаем координаты клика
            region = self.tree.identify("region", event.x, event.y)
            if region == "cell":  # Проверяем, что клик был по ячейке
            # Проверяем, что нажата колонка "completed" (✔ или ✘)
                column = self.tree.identify_column(event.x)
                if column == "#3":  # Колонка "completed" третья
                    item = self.tree.item(selected_item[0], "values")
                    task, date = item[1], self.selected_date
                    current_state = item[2] == "✔"
                    new_state = not current_state  # Инвертируем состояние
                    toggle_task_completion(task, date, new_state)
                    self.update_task_list()

    def open_task_creation_window(self):
        """Открывает модальное окно для создания новой задачи."""
        task_window = tk.Toplevel(self)
        task_window.overrideredirect(True)
        task_window.title("Добавить задачу")
        task_window.geometry("400x400")
        task_window.configure(bg="#0b0e23")  # Сохранение фона окна, как в основном окне

        # Создание области для захвата и перетаскивания окна
        title_bar = tk.Frame(task_window, bg="#0b0e23", height=30)  # Заголовок окна в цвет основной темы
        title_bar.pack(fill=tk.X)

        offset_x = 0
        offset_y = 0

        # Функция для перемещения окна
        def on_drag(event):
            task_window.geometry(f'+{event.x_root - offset_x}+{event.y_root - offset_y}')

        def on_button_press(event):
            nonlocal offset_x, offset_y
            offset_x = event.x
            offset_y = event.y

        # Привязка событий для захвата окна
        title_bar.bind("<ButtonPress-1>", on_button_press)
        title_bar.bind("<B1-Motion>", on_drag)

        # Добавляем элементы ввода для времени, задачи и описания
        tk.Label(task_window, text="Время (чч:мм):", bg="#0b0e23", fg="#00f7ff", font=("Arial", 12)).pack(pady=5)
        time_entry = tk.Entry(task_window, width=8, bg="#112031", fg="#00ffcc", font=("Arial", 12), insertbackground="#00ffcc")
        time_entry.pack(pady=5)

        tk.Label(task_window, text="Задача:", bg="#0b0e23", fg="#00f7ff", font=("Arial", 12)).pack(pady=5)
        task_entry = tk.Entry(task_window, bg="#112031", fg="#00ffcc", font=("Arial", 12), insertbackground="#00ffcc")
        task_entry.pack(fill=tk.X, padx=10)

        tk.Label(task_window, text="Описание:", bg="#0b0e23", fg="#00f7ff", font=("Arial", 12)).pack(pady=5)
        description_entry = tk.Text(task_window, height=5, bg="#112031", fg="#00ffcc", font=("Arial", 12))
        description_entry.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def save_task():
            task = task_entry.get().strip()
            time_str = time_entry.get().strip()
            description = description_entry.get("1.0", tk.END).strip()
            date = self.selected_date
            time_pattern = r"^(2[0-3]|[01]?[0-9]):([0-5]?[0-9])$"
            if not re.match(time_pattern, time_str):
                messagebox.showerror("Ошибка", "Введите время в формате чч:мм (например, 14:30).")
                return

            if task and time_str and date:
                add_task_to_db(task, time_str, date, description if description else None)
                self.update_task_list()
                task_window.destroy()

        # Панель с кнопками
        button_frame = tk.Frame(task_window, bg="#0b0e23")
        button_frame.pack(pady=10)

        # Кнопка сохранения
        save_button = ttk.Button(button_frame, text="Сохранить", command=save_task, style="Custom2.TButton")
        save_button.pack(side=tk.LEFT, padx=5)

        # Кнопка отмены
        cancel_button = ttk.Button(button_frame, text="Отмена", command=task_window.destroy, style="Custom2.TButton")
        cancel_button.pack(side=tk.LEFT, padx=5)

    def on_task_double_click(self, event):
        """Обработчик двойного клика по задаче для отображения полной информации."""
        selected_item = self.tree.selection()
        if selected_item:
            # Получаем данные задачи
            task_data = self.tree.item(selected_item[0], "values")
            task = task_data[1]
            time = task_data[0]

            # Получаем описание задачи из базы данных
            description = self.get_task_description_from_db(task)

            # Открываем новое окно с информацией о задаче
            self.open_task_info_window(task, time, description)

    def get_task_description_from_db(self, task):
        """Получаем описание задачи из базы данных."""
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT description FROM tasks WHERE task = %s", (task,))
        description = cursor.fetchone()
        cursor.close()
        conn.close()
        return description[0] if description else "Описание отсутствует."

    def open_task_info_window(self, task, time, description):
        """Открывает окно с полной информацией о задаче."""
        info_window = tk.Toplevel(self)
        info_window.overrideredirect(True)
        info_window.title("Информация о задаче")
        info_window.geometry("400x350")
        info_window.configure(bg="#1E1E2F")

        title_bar = tk.Frame(info_window, bg="#00f7ff", height=20)  # Это будет заголовок окна
        title_bar.pack(fill=tk.X)

        offset_x = 0
        offset_y = 0

        # Функция для перемещения окна
        def on_drag(event):
            info_window.geometry(f'+{event.x_root - offset_x}+{event.y_root - offset_y}')

        def on_button_press(event):
            nonlocal offset_x, offset_y
            offset_x = event.x
            offset_y = event.y

        # Привязка событий для захвата окна
        info_window.bind("<ButtonPress-1>", on_button_press)
        info_window.bind("<B1-Motion>", on_drag)

        tk.Label(info_window, text="Задача:", bg="#1E1E2F", fg="#00ffcc", font=("Arial", 14)).pack(pady=10)
        tk.Label(info_window, text=task, bg="#1E1E2F", fg="#00ffcc", font=("Arial", 12)).pack(pady=5)

        tk.Label(info_window, text="Время:", bg="#1E1E2F", fg="#00ffcc", font=("Arial", 14)).pack(pady=10)
        tk.Label(info_window, text=time, bg="#1E1E2F", fg="#00ffcc", font=("Arial", 12)).pack(pady=5)

        tk.Label(info_window, text="Описание:", bg="#1E1E2F", fg="#00ffcc", font=("Arial", 14)).pack(pady=10)
        tk.Label(info_window, text=description, bg="#1E1E2F", fg="#00ffcc", font=("Arial", 12), wraplength=350).pack(pady=5)

        # Кнопка закрытия окна
        close_button = ttk.Button(info_window, text="Закрыть", command=info_window.destroy, style="Custom2.TButton")
        close_button.pack(pady=10)


    def minimize_to_tray(self):
        self.withdraw()
        self.icon = create_tray_icon()
        self.icon.run()

    def start_move(self, event):
        if self.can_move:
            self.start_x = event.x
            self.start_y = event.y

    def do_move(self, event):
        if self.can_move:
            x = self.winfo_x() + event.x - self.start_x
            y = self.winfo_y() + event.y - self.start_y
            self.geometry(f"+{x}+{y}")


def create_tray_icon(): 
    # Загружаем изображение из файла icon.png 
    if not os.path.exists(ICON_PATH): 
        raise FileNotFoundError(f"Файл {ICON_PATH} не найден. Проверьте путь.") 
    image = Image.open(ICON_PATH).convert("RGBA") 

    def show_tasks(icon, item): 
        tasks = get_tasks_from_db(time.strftime("%m/%d/%y")) 
        task_list = "\n".join([f"{task[1]}: {task[0]}" for task in tasks]) 
        if not task_list: 
            task_list = "Нет задач на сегодня." 
        icon.notify(task_list) 

    def show_app(icon, item): 
        app.deiconify() # Показать основное окно 
        icon.stop() # Остановить иконку трея 

    def exit_app(icon, item): 
        icon.stop() # Остановить иконку трея 
        app.destroy() # Уничтожить приложение 

    menu = Menu(MenuItem("Открыть", show_app), MenuItem("Показать задачи", show_tasks), MenuItem("Выход", exit_app)) 
    return Icon("Daily Planner", image, menu=menu)    

def update_tray_task_list():
    threading.Thread(target=create_tray_icon, daemon=True).start()

if __name__ == "__main__":
    init_db()
    app = PlannerApp()

    # Запуск проверки расписания в отдельном потоке
    threading.Thread(target=schedule_checker, daemon=True).start()
    app.mainloop()