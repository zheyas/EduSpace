# database/seed.py
from datetime import datetime, timedelta
import random
from faker import Faker
import sqlite3
import hashlib
import os
import sys

# Добавляем путь к модулю с DatabaseConnection
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Импортируем ваш оригинальный код
try:
    from database.models import (
        DatabaseConnection, User, Course, Module, Test, Question, Answer,
        ProgressCourse, ProgressModule, TestResult, UserAnswer, LearningMaterial,
        MaterialProgress,  # Добавляем MaterialProgress
        generate_id, parse_id, UserRole, QuestionType, EnrollmentStatus, ProgressStatus
    )
except ImportError:
    # Альтернативный импорт если database пакет не найден
    from models import (
        DatabaseConnection, User, Course, Module, Test, Question, Answer,
        ProgressCourse, ProgressModule, TestResult, UserAnswer, LearningMaterial,
        MaterialProgress,
        generate_id, parse_id, UserRole, QuestionType, EnrollmentStatus, ProgressStatus
    )


# Функция для хэширования паролей
def hash_password(password: str) -> str:
    """Простая хэш-функция для демонстрации"""
    return hashlib.sha256(password.encode()).hexdigest()


class LearningDataSeeder:
    def __init__(self, db_path: str = "educational_platform.db", clear_existing: bool = True):
        self.db_path = db_path
        self.fake = Faker('ru_RU')  # Русские данные

        # Инициализируем базу данных
        self.db = DatabaseConnection(db_path)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        if clear_existing:
            self.clear_existing_data()
        else:
            self.create_tables()

        # Список для хранения учетных данных
        self.credentials = {
            "admins": [],
            "teachers": [],
            "students": []
        }

        # Кэш для хранения ID созданных записей
        self.cache = {
            "users": {"students": [], "teachers": [], "admins": []},
            "courses": [],
            "modules": [],
            "materials": [],
            "tests": [],
            "questions": [],
            "answers": [],
            "progress_courses": [],
            "progress_modules": [],
            "material_progress": [],
            "test_results": [],
            "user_answers": []
        }

    def clear_existing_data(self):
        """Очистка существующих данных"""
        print("Очистка существующих данных...")

        # Отключаем проверку внешних ключей
        self.cursor.execute("PRAGMA foreign_keys = OFF")

        # Удаляем таблицы в правильном порядке
        tables = [
            "user_answers",
            "material_progress",
            "test_results",
            "progress_modules",
            "progress_courses",
            "answers",
            "questions",
            "tests",
            "learning_materials",
            "modules",
            "courses",
            "demo_credentials",
            "users"
        ]

        for table in tables:
            try:
                self.cursor.execute(f"DROP TABLE IF EXISTS {table}")
                print(f"  Удалена таблица: {table}")
            except Exception as e:
                print(f"  Не удалось удалить таблицу {table}: {e}")

        # Включаем проверку внешних ключей обратно
        self.cursor.execute("PRAGMA foreign_keys = ON")

        # Пересоздаем структуру базы данных
        self.create_tables()

        print("Очистка данных завершена.\n")

    def create_tables(self):
        """Создание всех необходимых таблиц"""
        # Создаем таблицы из оригинального DatabaseConnection
        self.db._init_db()

        # Создаем таблицу demo_credentials если её нет
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS demo_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            password_plain TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')

        # Создаем индекс
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_demo_credentials_email ON demo_credentials(email)')

        print("Таблицы успешно созданы/проверены.")

    def seed_all(self):
        """Заполнение всех таблиц тестовыми данными"""
        print("=" * 60)
        print("ЗАПОЛНЕНИЕ БАЗЫ ДАННЫХ ТЕСТОВЫМИ ДАННЫМИ")
        print("=" * 60)

        # Создаем пользователей
        self.seed_users(admins=3, teachers=5, students=20)

        # Создаем курсы
        self.seed_courses(min_records=5)

        # Создаем модули
        self.seed_modules(min_records=15)

        # Создаем учебные материалы
        self.seed_learning_materials(min_records=50)

        # Создаем прогресс по материалам
        self.seed_material_progress(min_records=100)

        # Создаем тесты
        self.seed_tests(min_records=15)

        # Создаем вопросы
        self.seed_questions(min_records=50)

        # Создаем ответы
        self.seed_answers(min_records=150)

        # Создаем прогресс по курсам
        self.seed_progress_courses(min_records=50)

        # Создаем прогресс по модулям
        self.seed_progress_modules(min_records=100)

        # Создаем результаты тестов
        self.seed_test_results(min_records=30)

        # Создаем незавершенные тесты для демонстрации
        self.seed_unfinished_tests()

        # Создаем ответы пользователей
        self.seed_user_answers(min_records=150)

        # Сохраняем учетные данные в БД
        self.save_credentials_to_db()

        self.conn.commit()

        # Выводим учетные данные
        self.print_credentials()

    def seed_users(self, admins: int = 3, teachers: int = 5, students: int = 20):
        """Создание тестовых пользователей"""
        print(f"\nСоздание пользователей...")

        # Создаем 3 обязательных пользователя
        mandatory_users = [
            {"email": "test_s@example.com", "password": "test_s", "role": "student", "first_name": "Студент",
             "last_name": "Тестовый"},
            {"email": "test_t@example.com", "password": "test_t", "role": "teacher", "first_name": "Преподаватель",
             "last_name": "Тестовый"},
            {"email": "test_a@example.com", "password": "test_a", "role": "admin", "first_name": "Админ",
             "last_name": "Тестовый"}
        ]

        for i, user_data in enumerate(mandatory_users):
            user_id = generate_id("USR", i + 1)

            self.cursor.execute('''
                INSERT INTO users (id, last_name, first_name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                user_data["last_name"],
                user_data["first_name"],
                user_data["email"],
                hash_password(user_data["password"]),
                user_data["role"],
                datetime.now().isoformat()
            ))

            role_key = f"{user_data['role']}s"
            self.cache["users"][role_key].append(user_id)
            self.credentials[role_key].append({
                "id": user_id,
                "name": f"{user_data['first_name']} {user_data['last_name']}",
                "email": user_data["email"],
                "password": user_data["password"],
                "role": user_data["role"]
            })

        # Создаем дополнительных пользователей
        start_seq = 4
        # Админы
        for i in range(max(0, admins - 1)):
            seq_num = start_seq + i
            user_id = generate_id("USR", seq_num)
            first_name = self.fake.first_name_male() if i % 2 == 0 else self.fake.first_name_female()
            last_name = self.fake.last_name_male() if i % 2 == 0 else self.fake.last_name_female()
            email = f"admin{i + 2}@example.com"
            password = f"admin{i + 2}"

            self.cursor.execute('''
                INSERT INTO users (id, last_name, first_name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                last_name,
                first_name,
                email,
                hash_password(password),
                UserRole.ADMIN.value,
                datetime.now().isoformat()
            ))

            self.cache["users"]["admins"].append(user_id)
            self.credentials["admins"].append({
                "id": user_id,
                "name": f"{first_name} {last_name}",
                "email": email,
                "password": password,
                "role": "admin"
            })

        # Преподаватели
        start_seq += max(0, admins - 1)
        for i in range(max(0, teachers - 1)):
            seq_num = start_seq + i
            user_id = generate_id("USR", seq_num)
            first_name = self.fake.first_name_male() if i % 2 == 0 else self.fake.first_name_female()
            last_name = self.fake.last_name_male() if i % 2 == 0 else self.fake.last_name_female()
            email = f"teacher{i + 2}@example.com"
            password = f"teacher{i + 2}"

            self.cursor.execute('''
                INSERT INTO users (id, last_name, first_name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                last_name,
                first_name,
                email,
                hash_password(password),
                UserRole.TEACHER.value,
                datetime.now().isoformat()
            ))

            self.cache["users"]["teachers"].append(user_id)
            self.credentials["teachers"].append({
                "id": user_id,
                "name": f"{first_name} {last_name}",
                "email": email,
                "password": password,
                "role": "teacher"
            })

        # Студенты
        start_seq += max(0, teachers - 1)
        for i in range(max(0, students - 1)):
            seq_num = start_seq + i
            user_id = generate_id("USR", seq_num)
            first_name = self.fake.first_name_male() if i % 2 == 0 else self.fake.first_name_female()
            last_name = self.fake.last_name_male() if i % 2 == 0 else self.fake.last_name_female()
            email = f"student{i + 2}@example.com"
            password = f"student{i + 2}"

            self.cursor.execute('''
                INSERT INTO users (id, last_name, first_name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                last_name,
                first_name,
                email,
                hash_password(password),
                UserRole.STUDENT.value,
                datetime.now().isoformat()
            ))

            self.cache["users"]["students"].append(user_id)
            self.credentials["students"].append({
                "id": user_id,
                "name": f"{first_name} {last_name}",
                "email": email,
                "password": password,
                "role": "student"
            })

        print(f"Создано: {len(self.credentials['admins'])} админов, "
              f"{len(self.credentials['teachers'])} преподавателей, "
              f"{len(self.credentials['students'])} студентов")

    def seed_courses(self, min_records: int = 5):
        """Создание тестовых курсов"""
        print(f"\nСоздание курсов...")

        course_titles = [
            "Основы программирования на Python",
            "Веб-разработка на Django",
            "Анализ данных с Pandas",
            "Машинное обучение для начинающих",
            "Базы данных и SQL"
        ]

        created_count = 0
        for i in range(max(min_records, len(course_titles))):
            course_id = generate_id("CRS", i + 1)
            title = course_titles[i % len(course_titles)]

            # Используем test_t@example.com как автора курса
            self.cursor.execute("SELECT id FROM users WHERE email = 'test_t@example.com'")
            teacher = self.cursor.fetchone()
            author_id = teacher['id'] if teacher else random.choice(self.cache["users"]["teachers"])

            # Случайные даты
            now = datetime.now()
            six_months_ago = now - timedelta(days=180)
            start_date = self.fake.date_time_between(start_date=six_months_ago, end_date=now)
            end_date = start_date + timedelta(days=random.randint(90, 180))

            self.cursor.execute('''
                INSERT INTO courses (id, title, short_description, description, author_id, 
                                   start_date, end_date, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                course_id,
                title,
                f"Краткое описание курса '{title}'",
                f"Подробное описание курса '{title}'. Этот курс поможет вам освоить все необходимые навыки.",
                author_id,
                start_date.isoformat(),
                end_date.isoformat(),
                True,
                start_date.isoformat()
            ))

            self.cache["courses"].append(course_id)
            created_count += 1

        print(f"Создано {created_count} курсов")

    def seed_modules(self, min_records: int = 15):
        """Создание тестовых модулей"""
        print(f"\nСоздание модулей...")

        module_count = 0
        module_titles = [
            "Введение",
            "Основные понятия",
            "Практическая часть",
            "Продвинутые темы",
            "Проектная работа"
        ]

        for course_id in self.cache["courses"]:
            # У каждого курса 3-5 модулей
            num_modules = random.randint(3, 5)
            for i in range(num_modules):
                module_id = generate_id("MOD", module_count + 1)
                title = f"{module_titles[i % len(module_titles)]} - Модуль {i + 1}"

                self.cursor.execute('''
                    INSERT INTO modules (id, course_id, title, short_description, module_order, 
                                       estimated_duration, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    module_id,
                    course_id,
                    title,
                    f"Краткое описание модуля '{title}'",
                    i + 1,
                    random.randint(60, 240),  # 1-4 часа
                    datetime.now().isoformat()
                ))

                self.cache["modules"].append(module_id)
                module_count += 1

        print(f"Создано {module_count} модулей")

    def seed_learning_materials(self, min_records: int = 50):
        """Создание учебных материалов"""
        print(f"\nСоздание учебных материалов...")

        material_count = 0
        content_types = ["text", "video", "pdf", "link"]

        for module_id in self.cache["modules"]:
            # Для каждого модуля создаем 2-5 материалов
            num_materials = random.randint(2, 5)
            for i in range(num_materials):
                material_id = generate_id("LMT", material_count + 1)
                content_type = random.choice(content_types)

                # Выбираем тему
                topic = f"Тема {i + 1} модуля"

                # Генерируем контент в зависимости от типа
                if content_type == "text":
                    content = f"""
                    <h2>{topic}</h2>
                    <p>Это учебный материал по теме <strong>{topic}</strong>.</p>
                    <p>{self.fake.paragraph(nb_sentences=5)}</p>
                    <p>{self.fake.paragraph(nb_sentences=3)}</p>
                    <h3>Ключевые моменты:</h3>
                    <ul>
                        <li>{self.fake.sentence()}</li>
                        <li>{self.fake.sentence()}</li>
                        <li>{self.fake.sentence()}</li>
                    </ul>
                    """
                elif content_type == "video":
                    content = f"https://www.youtube.com/watch?v={self.fake.sha1()[:11]}"
                elif content_type == "pdf":
                    content = f"/materials/pdf/{self.fake.file_name(extension='pdf')}"
                else:  # link
                    content = f"https://example.com/tutorial/{topic.lower().replace(' ', '_')}.html"

                self.cursor.execute('''
                    INSERT INTO learning_materials (id, module_id, title, content, content_type, material_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    material_id,
                    module_id,
                    topic,
                    content,
                    content_type,
                    i + 1,
                    datetime.now().isoformat()
                ))

                self.cache["materials"].append(material_id)
                material_count += 1

        print(f"Создано {material_count} учебных материалов")

    def seed_material_progress(self, min_records: int = 100):
        """Создание прогресса по материалам"""
        print(f"\nСоздание прогресса по материалам...")

        progress_count = 0

        # Для тестового студента создаем прогресс по материалам
        self.cursor.execute("SELECT id FROM users WHERE email = 'test_s@example.com'")
        test_student = self.cursor.fetchone()

        if test_student:
            student_id = test_student['id']

            # Для тестового студента создаем прогресс по нескольким материалам
            for i in range(10):
                if not self.cache["materials"] or i >= len(self.cache["materials"]):
                    break

                material_id = self.cache["materials"][i]

                # Получаем module_id для материала
                self.cursor.execute("SELECT module_id FROM learning_materials WHERE id = ?", (material_id,))
                material_data = self.cursor.fetchone()
                if not material_data:
                    continue

                module_id = material_data['module_id']

                progress_id = generate_id("MPR", progress_count + 1)

                # Для первых 5 материалов - completed, для остальных - in_progress
                if i < 5:
                    status = ProgressStatus.COMPLETED.value
                    completed_at = datetime.now() - timedelta(days=random.randint(1, 30))
                    time_spent = random.randint(300, 1800)  # 5-30 минут
                else:
                    status = ProgressStatus.IN_PROGRESS.value
                    completed_at = None
                    time_spent = random.randint(60, 600)  # 1-10 минут

                self.cursor.execute('''
                    INSERT INTO material_progress (id, user_id, material_id, module_id, status, 
                                                 completed_at, time_spent_sec, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    progress_id,
                    student_id,
                    material_id,
                    module_id,
                    status,
                    completed_at.isoformat() if completed_at else None,
                    time_spent,
                    datetime.now().isoformat()
                ))

                self.cache["material_progress"].append(progress_id)
                progress_count += 1

        # Для остальных студентов создаем случайный прогресс
        for student_id in self.cache["users"]["students"]:
            # Пропускаем тестового студента
            self.cursor.execute("SELECT email FROM users WHERE id = ?", (student_id,))
            student_email = self.cursor.fetchone()['email']
            if student_email == "test_s@example.com":
                continue

            # Случайное количество материалов для прогресса
            num_materials = random.randint(1, 5)
            for i in range(num_materials):
                if not self.cache["materials"]:
                    break

                material_id = random.choice(self.cache["materials"])

                # Проверяем, не создан ли уже прогресс
                self.cursor.execute('''
                    SELECT id FROM material_progress WHERE user_id = ? AND material_id = ?
                ''', (student_id, material_id))
                if self.cursor.fetchone():
                    continue

                # Получаем module_id для материала
                self.cursor.execute("SELECT module_id FROM learning_materials WHERE id = ?", (material_id,))
                material_data = self.cursor.fetchone()
                if not material_data:
                    continue

                module_id = material_data['module_id']
                progress_id = generate_id("MPR", progress_count + 1)

                # Случайный статус
                status = random.choice([ProgressStatus.COMPLETED.value, ProgressStatus.IN_PROGRESS.value])

                if status == ProgressStatus.COMPLETED.value:
                    completed_at = datetime.now() - timedelta(days=random.randint(1, 30))
                    time_spent = random.randint(300, 1800)
                else:
                    completed_at = None
                    time_spent = random.randint(60, 600)

                self.cursor.execute('''
                    INSERT INTO material_progress (id, user_id, material_id, module_id, status, 
                                                 completed_at, time_spent_sec, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    progress_id,
                    student_id,
                    material_id,
                    module_id,
                    status,
                    completed_at.isoformat() if completed_at else None,
                    time_spent,
                    datetime.now().isoformat()
                ))

                self.cache["material_progress"].append(progress_id)
                progress_count += 1

        print(f"Создано {progress_count} записей прогресса по материалам")

    def seed_tests(self, min_records: int = 15):
        """Создание тестовых тестов"""
        print(f"\nСоздание тестов...")

        test_count = 0
        test_titles = [
            "Входное тестирование",
            "Промежуточный тест",
            "Итоговый экзамен"
        ]

        for module_id in self.cache["modules"]:
            # Для каждого модуля 1 тест
            test_id = generate_id("TST", test_count + 1)
            title = random.choice(test_titles)

            # Получаем course_id из модуля
            self.cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
            module_data = self.cursor.fetchone()
            course_id = module_data['course_id'] if module_data else None

            self.cursor.execute('''
                INSERT INTO tests (id, module_id, course_id, title, description, 
                                 time_limit, max_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                test_id,
                module_id,
                course_id,
                title,
                f"Описание теста '{title}'",
                random.choice([30, 45, 60]),
                100,
                datetime.now().isoformat()
            ))

            self.cache["tests"].append(test_id)
            test_count += 1

        print(f"Создано {test_count} тестов")

    def seed_questions(self, min_records: int = 50):
        """Создание тестовых вопросов"""
        print(f"\nСоздание вопросов...")

        question_count = 0
        python_questions = [
            "Что такое Python?",
            "Как объявить переменную в Python?",
            "Какие типы данных есть в Python?",
            "Как работает оператор if?",
            "Что такое цикл for?",
            "Как объявить функцию?",
            "Что такое список (list)?",
            "Как работает словарь (dict)?",
            "Что такое класс?",
            "Как обрабатывать исключения?"
        ]

        for test_id in self.cache["tests"]:
            # Для каждого теста 5-10 вопросов
            num_questions = random.randint(5, 10)
            for i in range(num_questions):
                question_id = generate_id("QST", question_count + 1)
                question_type = random.choice([QuestionType.SINGLE.value, QuestionType.MULTIPLE.value])

                question_text = python_questions[i % len(python_questions)]

                self.cursor.execute('''
                    INSERT INTO questions (id, test_id, text, type, question_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    question_id,
                    test_id,
                    question_text,
                    question_type,
                    i + 1,
                    datetime.now().isoformat()
                ))

                self.cache["questions"].append(question_id)
                question_count += 1

        print(f"Создано {question_count} вопросов")

    def seed_answers(self, min_records: int = 150):
        """Создание тестовых ответов"""
        print(f"\nСоздание ответов...")

        answer_count = 0

        python_answers = {
            "Что такое Python?": [
                ("Язык программирования", True),
                ("Змея", False),
                ("Операционная система", False),
                ("База данных", False)
            ],
            "Как объявить переменную в Python?": [
                ("x = 5", True),
                ("var x = 5", False),
                ("let x = 5", False),
                ("int x = 5", False)
            ],
            "Какие типы данных есть в Python?": [
                ("int, float, str, bool", True),
                ("list, dict, tuple, set", True),
                ("number, text, logic", False),
                ("Только числа и строки", False)
            ],
            "Как работает оператор if?": [
                ("Проверяет условие", True),
                ("Выполняет код если условие истинно", True),
                ("Создает переменную", False),
                ("Импортирует модуль", False)
            ],
            "Что такое цикл for?": [
                ("Выполняет код для каждого элемента последовательности", True),
                ("Повторяет выполнение кода", True),
                ("Проверяет условие", False),
                ("Создает функцию", False)
            ],
            "Как объявить функцию?": [
                ("def function_name():", True),
                ("function function_name() {}", False),
                ("func function_name():", False),
                ("function_name() = def", False)
            ],
            "Что такое список (list)?": [
                ("Упорядоченная изменяемая коллекция", True),
                ("Хранит элементы в квадратных скобках", True),
                ("Неупорядоченная коллекция", False),
                ("Хранит только уникальные элементы", False)
            ],
            "Как работает словарь (dict)?": [
                ("Хранит пары ключ-значение", True),
                ("Ключи должны быть уникальными", True),
                ("Хранит только значения", False),
                ("Автоматически сортирует элементы", False)
            ],
            "Что такое класс?": [
                ("Шаблон для создания объектов", True),
                ("Определяет атрибуты и методы", True),
                ("То же самое, что функция", False),
                ("Тип данных для чисел", False)
            ],
            "Как обрабатывать исключения?": [
                ("С помощью try-except", True),
                ("Используя блок finally", True),
                ("Через оператор if", False),
                ("С помощью цикла while", False)
            ]
        }

        for question_id in self.cache["questions"]:
            # Получаем текст вопроса
            self.cursor.execute("SELECT text FROM questions WHERE id = ?", (question_id,))
            question_data = self.cursor.fetchone()
            question_text = question_data['text'] if question_data else "Вопрос"

            # Проверяем, есть ли предопределенные ответы
            if question_text in python_answers:
                answers_data = python_answers[question_text]
                for i, (answer_text, is_correct) in enumerate(answers_data):
                    answer_id = generate_id("ANS", answer_count + 1)
                    self.cursor.execute('''
                        INSERT INTO answers (id, question_id, text, is_correct, answer_order, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        answer_id,
                        question_id,
                        answer_text,
                        is_correct,
                        i + 1,
                        datetime.now().isoformat()
                    ))
                    answer_count += 1
            else:
                # Создаем случайные ответы
                num_answers = 4
                num_correct = random.randint(1, 2)
                correct_indices = random.sample(range(num_answers), num_correct)

                for i in range(num_answers):
                    answer_id = generate_id("ANS", answer_count + 1)
                    is_correct = i in correct_indices
                    answer_text = self.fake.sentence()[:50]

                    self.cursor.execute('''
                        INSERT INTO answers (id, question_id, text, is_correct, answer_order, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        answer_id,
                        question_id,
                        answer_text,
                        is_correct,
                        i + 1,
                        datetime.now().isoformat()
                    ))
                    answer_count += 1

        print(f"Создано {answer_count} вариантов ответов")

    def seed_progress_courses(self, min_records: int = 50):
        """Создание записей прогресса по курсам"""
        print(f"\nСоздание прогресса по курсам...")

        progress_count = 0

        # Для тестового студента записываемся на 2 курса
        self.cursor.execute("SELECT id FROM users WHERE email = 'test_s@example.com'")
        test_student = self.cursor.fetchone()

        if test_student and len(self.cache["courses"]) >= 2:
            student_id = test_student['id']
            selected_courses = self.cache["courses"][:2]

            for j, course_id in enumerate(selected_courses):
                progress_id = generate_id("PCR", progress_count + 1)

                if j == 0:
                    # Первый курс - завершен
                    status = EnrollmentStatus.COMPLETED.value
                    now = datetime.now()
                    enrolled_at = now - timedelta(days=90)
                    finished_at = enrolled_at + timedelta(days=60)
                    progress_percent = 100.0
                    final_score = random.uniform(85, 95)
                else:
                    # Второй курс - в процессе
                    status = EnrollmentStatus.ACTIVE.value
                    now = datetime.now()
                    enrolled_at = now - timedelta(days=45)
                    finished_at = None
                    progress_percent = random.uniform(65, 85)
                    final_score = None

                self.cursor.execute('''
                    INSERT INTO progress_courses (id, user_id, course_id, enrolled_at, status, 
                                                progress_percent, final_score, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    progress_id,
                    student_id,
                    course_id,
                    enrolled_at.isoformat(),
                    status,
                    round(progress_percent, 2),
                    round(final_score, 2) if final_score else None,
                    finished_at.isoformat() if finished_at else None
                ))

                self.cache["progress_courses"].append(progress_id)
                progress_count += 1

        # Для остальных студентов
        for student_id in self.cache["users"]["students"]:
            self.cursor.execute("SELECT email FROM users WHERE id = ?", (student_id,))
            student_email = self.cursor.fetchone()['email']
            if student_email == "test_s@example.com":
                continue

            if not self.cache["courses"]:
                break

            num_courses = random.randint(1, min(3, len(self.cache["courses"])))
            selected_courses = random.sample(self.cache["courses"], num_courses)

            for course_id in selected_courses:
                progress_id = generate_id("PCR", progress_count + 1)

                status = random.choices(
                    [EnrollmentStatus.ACTIVE.value, EnrollmentStatus.COMPLETED.value],
                    weights=[0.7, 0.3]
                )[0]

                now = datetime.now()
                six_months_ago = now - timedelta(days=180)
                enrolled_at = self.fake.date_time_between(start_date=six_months_ago, end_date=now)

                if status == EnrollmentStatus.COMPLETED.value:
                    finished_at = enrolled_at + timedelta(days=random.randint(30, 120))
                    progress_percent = 100.0
                    final_score = random.uniform(70, 100)
                else:
                    finished_at = None
                    progress_percent = random.uniform(20, 95)
                    final_score = None

                self.cursor.execute('''
                    INSERT INTO progress_courses (id, user_id, course_id, enrolled_at, status, 
                                                progress_percent, final_score, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    progress_id,
                    student_id,
                    course_id,
                    enrolled_at.isoformat(),
                    status,
                    round(progress_percent, 2),
                    round(final_score, 2) if final_score else None,
                    finished_at.isoformat() if finished_at else None
                ))

                self.cache["progress_courses"].append(progress_id)
                progress_count += 1

        print(f"Создано {progress_count} записей прогресса по курсам")

    def seed_progress_modules(self, min_records: int = 100):
        """Создание записей прогресса по модулям"""
        print(f"\nСоздание прогресса по модулям...")

        progress_count = 0

        for progress_id in self.cache["progress_courses"]:
            self.cursor.execute("SELECT user_id, course_id FROM progress_courses WHERE id = ?", (progress_id,))
            progress_data = self.cursor.fetchone()

            if not progress_data:
                continue

            user_id = progress_data['user_id']
            course_id = progress_data['course_id']

            self.cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
            student_email = self.cursor.fetchone()['email']
            is_test_student = student_email == "test_s@example.com"

            self.cursor.execute("SELECT id FROM modules WHERE course_id = ?", (course_id,))
            modules = self.cursor.fetchall()

            for module_data in modules:
                module_id = module_data['id']
                progress_module_id = generate_id("PMD", progress_count + 1)

                if is_test_student:
                    self.cursor.execute("SELECT module_order FROM modules WHERE id = ?", (module_id,))
                    module_order_result = self.cursor.fetchone()
                    module_order = module_order_result['module_order'] if module_order_result else 1

                    if module_order == 1:
                        status = ProgressStatus.COMPLETED.value
                        progress_percent = 100.0
                    else:
                        status = ProgressStatus.IN_PROGRESS.value
                        progress_percent = random.uniform(30, 90)
                else:
                    status = random.choices(
                        [ProgressStatus.NOT_STARTED.value, ProgressStatus.IN_PROGRESS.value,
                         ProgressStatus.COMPLETED.value],
                        weights=[0.1, 0.4, 0.5]
                    )[0]

                if status == ProgressStatus.COMPLETED.value:
                    progress_percent = 100.0
                    now = datetime.now()
                    started_at = now - timedelta(days=random.randint(30, 90))
                    finished_at = started_at + timedelta(days=random.randint(1, 14))
                elif status == ProgressStatus.IN_PROGRESS.value:
                    progress_percent = random.uniform(10, 90)
                    now = datetime.now()
                    started_at = now - timedelta(days=random.randint(1, 30))
                    finished_at = None
                else:
                    progress_percent = 0.0
                    started_at = None
                    finished_at = None

                self.cursor.execute('''
                    INSERT INTO progress_modules (id, enrollment_id, module_id, status, 
                                                progress_percent, started_at, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    progress_module_id,
                    progress_id,
                    module_id,
                    status,
                    round(progress_percent, 2),
                    started_at.isoformat() if started_at else None,
                    finished_at.isoformat() if finished_at else None
                ))

                progress_count += 1

        print(f"Создано {progress_count} записей прогресса по модулям")

    def seed_test_results(self, min_records: int = 30):
        """Создание результатов тестов"""
        print(f"\nСоздание результатов тестов...")

        result_count = 0

        # Для тестового студента
        self.cursor.execute("SELECT id FROM users WHERE email = 'test_s@example.com'")
        test_student = self.cursor.fetchone()

        if test_student:
            student_id = test_student['id']

            for i in range(5):
                if not self.cache["tests"]:
                    break

                test_id = self.cache["tests"][i % len(self.cache["tests"])]

                self.cursor.execute("SELECT COUNT(*) as count FROM test_results WHERE user_id = ? AND test_id = ?",
                                    (student_id, test_id))
                attempts_result = self.cursor.fetchone()
                attempts = attempts_result['count'] if attempts_result else 0

                if attempts >= 3:
                    continue

                result_id = generate_id("TRS", result_count + 1)

                self.cursor.execute("SELECT max_score FROM tests WHERE id = ?", (test_id,))
                test_data = self.cursor.fetchone()
                max_score = test_data['max_score'] if test_data else 100

                score = random.uniform(max_score * 0.75, max_score)

                now = datetime.now()
                started_at = now - timedelta(days=random.randint(1, 60))
                duration = random.randint(600, 1800)
                finished_at = started_at + timedelta(seconds=duration)

                self.cursor.execute('''
                    INSERT INTO test_results (id, user_id, test_id, score, max_score, 
                                            started_at, finished_at, duration_sec, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    result_id,
                    student_id,
                    test_id,
                    round(score, 2),
                    max_score,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    duration,
                    finished_at.isoformat()
                ))

                self.cache["test_results"].append(result_id)
                result_count += 1

        # Для других студентов
        for i in range(25):
            if not self.cache["users"]["students"] or not self.cache["tests"]:
                break

            student_id = random.choice(self.cache["users"]["students"])
            test_id = random.choice(self.cache["tests"])

            self.cursor.execute("SELECT email FROM users WHERE id = ?", (student_id,))
            user_email_result = self.cursor.fetchone()
            if user_email_result and user_email_result['email'] == 'test_s@example.com':
                continue

            self.cursor.execute("SELECT COUNT(*) as count FROM test_results WHERE user_id = ? AND test_id = ?",
                                (student_id, test_id))
            attempts_result = self.cursor.fetchone()
            attempts = attempts_result['count'] if attempts_result else 0

            if attempts >= 3:
                continue

            result_id = generate_id("TRS", result_count + 1)

            self.cursor.execute("SELECT max_score FROM tests WHERE id = ?", (test_id,))
            test_data = self.cursor.fetchone()
            max_score = test_data['max_score'] if test_data else 100

            score = random.uniform(max_score * 0.5, max_score)

            now = datetime.now()
            started_at = now - timedelta(days=random.randint(1, 60))
            duration = random.randint(600, 1800)
            finished_at = started_at + timedelta(seconds=duration)

            self.cursor.execute('''
                INSERT INTO test_results (id, user_id, test_id, score, max_score, 
                                        started_at, finished_at, duration_sec, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result_id,
                student_id,
                test_id,
                round(score, 2),
                max_score,
                started_at.isoformat(),
                finished_at.isoformat(),
                duration,
                finished_at.isoformat()
            ))

            self.cache["test_results"].append(result_id)
            result_count += 1

        print(f"Создано {result_count} результатов тестов")

    def seed_unfinished_tests(self):
        """Создание незавершенных тестов для демонстрации"""
        print(f"\nСоздание незавершенных тестов...")

        self.cursor.execute("SELECT id FROM users WHERE email = 'test_s@example.com'")
        test_student = self.cursor.fetchone()

        if not test_student:
            print("  Ошибка: тестовый студент не найден")
            return

        student_id = test_student['id']
        unfinished_count = 0

        for i in range(2):
            if not self.cache["tests"]:
                break

            test_id = self.cache["tests"][(i + 3) % len(self.cache["tests"])]
            result_id = generate_id("TRS", 1000 + i)

            self.cursor.execute("SELECT max_score FROM tests WHERE id = ?", (test_id,))
            test_data = self.cursor.fetchone()
            max_score = test_data['max_score'] if test_data else 100

            started_at = datetime.now() - timedelta(minutes=10)

            self.cursor.execute('''
                INSERT INTO test_results (id, user_id, test_id, score, max_score, 
                                        started_at, finished_at, duration_sec, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result_id,
                student_id,
                test_id,
                0.0,
                max_score,
                started_at.isoformat(),
                None,
                600,
                started_at.isoformat()
            ))

            self.cursor.execute("SELECT id FROM questions WHERE test_id = ? LIMIT 3", (test_id,))
            questions = self.cursor.fetchall()

            for j, question_data in enumerate(questions):
                question_id = question_data['id']
                answer_user_id = generate_id("UAS", 5000 + unfinished_count * 10 + j)

                self.cursor.execute("SELECT id FROM answers WHERE question_id = ? LIMIT 1", (question_id,))
                answer_result = self.cursor.fetchone()

                if answer_result:
                    answer_id = answer_result['id']

                    self.cursor.execute('''
                        INSERT INTO user_answers (id, test_result_id, question_id, answer_id, 
                                                text_answer, is_correct, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        answer_user_id,
                        result_id,
                        question_id,
                        answer_id,
                        None,
                        True,
                        started_at.isoformat()
                    ))

            unfinished_count += 1
            self.cache["test_results"].append(result_id)

        print(f"Создано {unfinished_count} незавершенных тестов")

    def seed_user_answers(self, min_records: int = 150):
        """Создание ответов пользователей"""
        print(f"\nСоздание ответов пользователей...")

        answer_count = 0

        for result_id in self.cache["test_results"]:
            self.cursor.execute("SELECT finished_at, user_id FROM test_results WHERE id = ?", (result_id,))
            result_data = self.cursor.fetchone()

            if not result_data or not result_data['finished_at']:
                continue

            user_id = result_data['user_id']

            self.cursor.execute("SELECT test_id FROM test_results WHERE id = ?", (result_id,))
            result_test_data = self.cursor.fetchone()

            if not result_test_data:
                continue

            test_id = result_test_data['test_id']

            self.cursor.execute("SELECT id, type FROM questions WHERE test_id = ?", (test_id,))
            questions = self.cursor.fetchall()

            for question_data in questions:
                question_id = question_data['id']
                answer_user_id = generate_id("UAS", answer_count + 1)

                self.cursor.execute("SELECT id, is_correct FROM answers WHERE question_id = ?", (question_id,))
                answers = self.cursor.fetchall()

                if answers:
                    self.cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
                    user_res = self.cursor.fetchone()
                    user_email = user_res['email'] if user_res else ""

                    if user_email == "test_s@example.com" and random.random() < 0.9:
                        correct_answers = [a for a in answers if a['is_correct']]
                        if correct_answers:
                            selected_answer = random.choice(correct_answers)
                        else:
                            selected_answer = random.choice(answers)
                    else:
                        if random.random() < 0.7:
                            correct_answers = [a for a in answers if a['is_correct']]
                            if correct_answers:
                                selected_answer = random.choice(correct_answers)
                            else:
                                selected_answer = random.choice(answers)
                        else:
                            selected_answer = random.choice(answers)

                    answer_id = selected_answer['id']
                    text_answer = None
                    is_correct = selected_answer['is_correct']
                else:
                    continue

                self.cursor.execute('''
                    INSERT INTO user_answers (id, test_result_id, question_id, answer_id, 
                                            text_answer, is_correct, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    answer_user_id,
                    result_id,
                    question_id,
                    answer_id,
                    text_answer,
                    is_correct,
                    datetime.now().isoformat()
                ))

                answer_count += 1

        print(f"Создано {answer_count} ответов пользователей")

    def save_credentials_to_db(self):
        """Сохранение учетных данных в таблицу demo_credentials"""
        print(f"\nСохранение учетных данных в базу данных...")

        for role_type in ["admins", "teachers", "students"]:
            for user_data in self.credentials[role_type]:
                self.cursor.execute('''
                    INSERT INTO demo_credentials (user_id, email, password_plain, role, full_name, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    user_data["id"],
                    user_data["email"],
                    user_data["password"],
                    user_data["role"],
                    user_data["name"],
                    datetime.now().isoformat()
                ))

        print(f"Сохранено учетных данных в БД: "
              f"{len(self.credentials['admins'])} админов, "
              f"{len(self.credentials['teachers'])} преподавателей, "
              f"{len(self.credentials['students'])} студентов")

    def print_credentials(self):
        """Вывод учетных данных для входа"""
        print("\n" + "=" * 60)
        print("УЧЕТНЫЕ ДАННЫЕ ДЛЯ ВХОДА")
        print("=" * 60)

        print("\n--- ОБЯЗАТЕЛЬНЫЕ ПОЛЬЗОВАТЕЛИ ---")
        print("Администратор: test_a@example.com / test_a")
        print("Преподаватель: test_t@example.com / test_t")
        print("Студент: test_s@example.com / test_s")
        print("-" * 40)

        print("\n--- ДОПОЛНИТЕЛЬНЫЕ ПОЛЬЗОВАТЕЛИ ---")
        for role in ["admins", "teachers", "students"]:
            if role == "admins":
                print(f"\nАдминистраторы:")
            elif role == "teachers":
                print(f"\nПреподаватели:")
            else:
                print(f"\nСтуденты (первые 5):")

            users = self.credentials[role]
            if role == "students":
                users = users[:5]

            for user in users:
                if user["email"] not in ["test_a@example.com", "test_t@example.com", "test_s@example.com"]:
                    print(f"  {user['email']} / {user['password']} ({user['name']})")

        print("\n" + "=" * 60)
        print("СТАТИСТИКА БАЗЫ ДАННЫХ")
        print("=" * 60)

        tables = [
            ("users", "Пользователи"),
            ("courses", "Курсы"),
            ("modules", "Модули"),
            ("learning_materials", "Учебные материалы"),
            ("material_progress", "Прогресс по материалам"),
            ("tests", "Тесты"),
            ("questions", "Вопросы"),
            ("answers", "Варианты ответов"),
            ("progress_courses", "Прогресс по курсам"),
            ("progress_modules", "Прогресс по модулям"),
            ("test_results", "Результаты тестов"),
            ("user_answers", "Ответы пользователей"),
            ("demo_credentials", "Учетные данные (демо)")
        ]

        for table_name, table_desc in tables:
            try:
                self.cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                result = self.cursor.fetchone()
                count = result['count'] if result else 0
                print(f"{table_desc}: {count} записей")
            except Exception as e:
                print(f"{table_desc}: ошибка - {str(e)[:50]}...")

        print("\n" + "=" * 60)
        print("ДЛЯ ВХОДА В СИСТЕМУ ИСПОЛЬЗУЙТЕ:")
        print("=" * 60)
        print("Администратор: test_a@example.com / test_a")
        print("Преподаватель: test_t@example.com / test_t")
        print("Студент: test_s@example.com / test_s")
        print("=" * 60)

        print("\n" + "=" * 60)
        print("ИНФОРМАЦИЯ ДЛЯ ДЕМОНСТРАЦИИ")
        print("=" * 60)
        print("Тестовый студент (test_s@example.com) имеет:")
        print("1. Завершенные материалы (зеленые галочки)")
        print("2. Незавершенные материалы (серые точки)")
        print("3. Завершенные тесты (хорошие результаты)")
        print("4. Незавершенные тесты (в процессе)")
        print("5. Прогресс по курсам и модулям")
        print("=" * 60)

    def close(self):
        """Закрытие соединения с базой данных"""
        if self.conn:
            self.conn.close()


# Главная функция для запуска
def main():
    """Основная функция для заполнения базы данных"""
    print("Начинаю заполнение базы данных тестовыми данными...")

    # Создаем сидер
    seeder = LearningDataSeeder("educational_platform.db", clear_existing=True)

    try:
        seeder.seed_all()

        print("\n" + "=" * 60)
        print("БАЗА ДАННЫХ УСПЕШНО ЗАПОЛНЕНА!")
        print("Теперь вы можете использовать систему обучения:")
        print("1. Войдите как студент (test_s@example.com / test_s)")
        print("2. Запишитесь на курсы")
        print("3. Начните изучение модулей")
        print("4. Изучайте материалы и проходите тесты")
        print("=" * 60)

    except Exception as e:
        print(f"Ошибка при заполнении базы данных: {e}")
        import traceback
        traceback.print_exc()
    finally:
        seeder.close()


if __name__ == "__main__":
    main()