# database/models.py
from datetime import datetime
from enum import Enum
import re
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
import json


# Вспомогательная функция для генерации ID
def generate_id(prefix: str, seq_num: int) -> str:
    """Генерация ID в формате PREFIX001"""
    return f"{prefix}{seq_num:03d}"


def parse_id(id_string: str) -> Tuple[Optional[str], Optional[int]]:
    """Парсинг ID для получения префикса и номера"""
    match = re.match(r'([A-Z]{3})(\d{3})', id_string)
    if match:
        return match.group(1), int(match.group(2))
    return None, None


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class QuestionType(str, Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    OPEN = "open"
    TEXT = "text"


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DatabaseConnection:
    """Класс для управления подключением к SQLite базе данных"""

    def __init__(self, db_path: str = "educational_platform.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Инициализация базы данных и создание таблиц - ИСПРАВЛЕНА"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Создание таблицы users
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Создание таблицы courses
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            short_description TEXT,
            description TEXT,
            author_id TEXT NOT NULL,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (author_id) REFERENCES users(id)
        )
        ''')

        # Создание таблицы modules
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS modules (
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            title TEXT NOT NULL,
            short_description TEXT,
            module_order INTEGER NOT NULL,
            estimated_duration INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
        ''')

        # Создание таблицы tests
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id TEXT PRIMARY KEY,
            module_id TEXT,
            course_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            time_limit INTEGER,
            max_score INTEGER DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (module_id) REFERENCES modules(id),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
        ''')

        # Создание таблицы questions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL,
    text TEXT NOT NULL,
    type TEXT NOT NULL,
    points INTEGER DEFAULT 1,  -- ДОБАВЬТЕ ЭТУ СТРОКУ
    question_order INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (test_id) REFERENCES tests(id)
)
        ''')

        # Создание таблицы answers
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL,
            text TEXT NOT NULL,
            is_correct BOOLEAN DEFAULT 0,
            answer_order INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        )
        ''')

        # Создание таблицы progress_courses
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress_courses (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            progress_percent REAL DEFAULT 0.0,
            final_score REAL,
            finished_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
        ''')

        # Создание таблицы progress_modules
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress_modules (
            id TEXT PRIMARY KEY,
            enrollment_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            status TEXT DEFAULT 'not_started',
            progress_percent REAL DEFAULT 0.0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (enrollment_id) REFERENCES progress_courses(id),
            FOREIGN KEY (module_id) REFERENCES modules(id)
        )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_results (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                test_id TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,  -- Может быть NULL!
                duration_sec INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (test_id) REFERENCES tests(id)
            )
            ''')

        # Создание таблицы user_answers
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_answers (
            id TEXT PRIMARY KEY,
            test_result_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            answer_id TEXT,
            text_answer TEXT,
            is_correct BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_result_id) REFERENCES test_results(id),
            FOREIGN KEY (question_id) REFERENCES questions(id),
            FOREIGN KEY (answer_id) REFERENCES answers(id)
        )
        ''')
        # Создание таблицы learning_materials
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_materials (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            content_type TEXT DEFAULT 'text',
            material_order INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS material_progress (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            material_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            status TEXT DEFAULT 'not_started',
            completed_at TIMESTAMP,
            time_spent_sec INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (material_id) REFERENCES learning_materials(id),
            FOREIGN KEY (module_id) REFERENCES modules(id),
            UNIQUE(user_id, material_id)
        )
        ''')

        # Создание индексов для ускорения запросов
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_material_progress_user_material ON material_progress(user_id, material_id)')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_material_progress_user_module ON material_progress(user_id, module_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_material_progress_status ON material_progress(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_author ON courses(author_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_modules_course ON modules(course_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_modules_order ON modules(course_id, module_order)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tests_module ON tests(module_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_user_course ON progress_courses(user_id, course_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_course_status ON progress_courses(course_id, status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_answers_test_result ON user_answers(test_result_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_test_results_user_test ON test_results(user_id, test_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_test_results_finished ON test_results(finished_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_test_results_started ON test_results(started_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_test_results_score ON test_results(score)')

        conn.commit()
        conn.close()

    def get_connection(self):
        """Получение подключения к базе данных"""
        return sqlite3.connect(self.db_path)

    def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False):
        """Выполнение SQL запроса"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row  # Для получения результатов в виде словаря
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)
            conn.commit()

            if fetch_one:
                result = cursor.fetchone()
                return dict(result) if result else None
            else:
                results = cursor.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def execute_many(self, query: str, params_list: List[tuple]):
        """Выполнение множественных запросов"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.executemany(query, params_list)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()


# Базовый класс для моделей
class BaseModel:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def to_dict(self):
        """Преобразование объекта в словарь"""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_') and key != 'db':
                # Преобразуем datetime в строку для JSON
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                else:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict, db: DatabaseConnection = None):
        """Создание объекта из словаря"""
        instance = cls(db) if db else cls(None)
        for key, value in data.items():
            if hasattr(instance, key):
                # Обработка специальных полей
                if key in ['created_at', 'enrolled_at', 'started_at', 'finished_at',
                           'start_date', 'end_date'] and value:
                    try:
                        value = datetime.fromisoformat(value)
                    except:
                        pass
                setattr(instance, key, value)
        return instance


class User(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.last_name = None
        self.first_name = None
        self.email = None
        self.password_hash = None
        self.role = None
        self.created_at = None

    def create(self, user_data: Dict[str, Any]) -> 'User':
        """Создание нового пользователя"""
        # Генерация ID
        query = "SELECT id FROM users ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        user_id = generate_id("USR", seq_num)

        query = """
        INSERT INTO users (id, last_name, first_name, email, password_hash, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            user_id,
            user_data['last_name'],
            user_data['first_name'],
            user_data['email'],
            user_data['password_hash'],
            user_data['role'],
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        # Получаем созданного пользователя
        return self.get_by_id(user_id)

    def get_by_id(self, user_id: str) -> Optional['User']:
        """Получение пользователя по ID"""
        query = "SELECT * FROM users WHERE id = ?"
        result = self.db.execute_query(query, (user_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_email(self, email: str) -> Optional['User']:
        """Получение пользователя по email"""
        query = "SELECT * FROM users WHERE email = ?"
        result = self.db.execute_query(query, (email,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_all(self, skip: int = 0, limit: int = 100) -> List['User']:
        """Получение всех пользователей"""
        query = "SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def get_by_role(self, role: UserRole, skip: int = 0, limit: int = 100) -> List['User']:
        """Получение пользователей по роли"""
        query = "SELECT * FROM users WHERE role = ? ORDER BY id LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (role, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, user_id: str, update_data: Dict[str, Any]) -> Optional['User']:
        """Обновление пользователя"""
        # Формируем SET часть запроса
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(user_id)

        query = f"UPDATE users SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(user_id)

    def delete(self, user_id: str) -> bool:
        """Удаление пользователя"""
        query = "DELETE FROM users WHERE id = ?"
        try:
            self.db.execute_query(query, (user_id,))
            return True
        except:
            return False

    # Специальные запросы
    def get_student_progress(self, student_id: str, start_date: datetime = None,
                             end_date: datetime = None) -> Dict[str, Any]:
        """
        Получение прогресса обучения конкретного студента за период
        """
        # Проверяем, что пользователь существует и является студентом
        student = self.get_by_id(student_id)
        if not student or student.role != UserRole.STUDENT.value:
            raise ValueError("Студент не найден")

        # Получаем все курсы студента
        query = """
        SELECT pc.*, c.title as course_title, c.description as course_description
        FROM progress_courses pc
        JOIN courses c ON pc.course_id = c.id
        WHERE pc.user_id = ?
        """

        params = [student_id]
        if start_date:
            query += " AND pc.enrolled_at >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND pc.enrolled_at <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY pc.enrolled_at DESC"

        course_progress = self.db.execute_query(query, tuple(params))

        result = {
            "student": {
                "id": student.id,
                "name": f"{student.first_name} {student.last_name}",
                "email": student.email
            },
            "total_courses": len(course_progress),
            "active_courses": 0,
            "completed_courses": 0,
            "average_score": 0,
            "courses": [],
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            }
        }

        total_score = 0
        completed_count = 0

        for progress in course_progress:
            # Подсчет статистики по статусам
            if progress['status'] == EnrollmentStatus.ACTIVE.value:
                result["active_courses"] += 1
            elif progress['status'] == EnrollmentStatus.COMPLETED.value:
                result["completed_courses"] += 1
                if progress['final_score']:
                    total_score += progress['final_score']
                    completed_count += 1

            # Получаем прогресс по модулям для этого курса
            module_query = """
            SELECT pm.*, m.title as module_title, m.module_order as module_order
            FROM progress_modules pm
            JOIN modules m ON pm.module_id = m.id
            WHERE pm.enrollment_id = ?
            ORDER BY m.module_order
            """
            module_progress = self.db.execute_query(module_query, (progress['id'],))

            # Получаем результаты тестов для этого курса
            test_query = """
            SELECT tr.*, t.title as test_title, t.max_score as test_max_score
            FROM test_results tr
            JOIN tests t ON tr.test_id = t.id
            JOIN modules m ON t.module_id = m.id
            WHERE tr.user_id = ? AND m.course_id = ?
            ORDER BY tr.finished_at DESC
            """
            test_results = self.db.execute_query(test_query, (student_id, progress['course_id']))

            course_data = {
                "course_id": progress['course_id'],
                "course_title": progress['course_title'],
                "status": progress['status'],
                "progress_percent": progress['progress_percent'],
                "final_score": progress['final_score'],
                "enrolled_at": progress['enrolled_at'],
                "finished_at": progress['finished_at'],
                "modules": [
                    {
                        "module_id": mp['module_id'],
                        "module_title": mp['module_title'],
                        "status": mp['status'],
                        "progress_percent": mp['progress_percent'],
                        "started_at": mp['started_at'],
                        "finished_at": mp['finished_at']
                    }
                    for mp in module_progress
                ],
                "test_results": [
                    {
                        "test_id": tr['test_id'],
                        "test_title": tr['test_title'],
                        "score": tr['score'],
                        "max_score": tr['max_score'],
                        "percentage": (tr['score'] / tr['max_score']) * 100 if tr['max_score'] > 0 else 0,
                        "finished_at": tr['finished_at']
                    }
                    for tr in test_results
                ]
            }

            result["courses"].append(course_data)

        # Рассчитываем средний балл
        if completed_count > 0:
            result["average_score"] = round(total_score / completed_count, 2)

        return result


class Course(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.title = None
        self.short_description = None
        self.description = None
        self.author_id = None
        self.start_date = None
        self.end_date = None
        self.is_active = None
        self.created_at = None

    def create(self, course_data: Dict[str, Any]) -> 'Course':
        """Создание нового курса"""
        # Генерация ID
        query = "SELECT id FROM courses ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        course_id = generate_id("CRS", seq_num)

        query = """
        INSERT INTO courses (id, title, short_description, description, author_id, 
                           start_date, end_date, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            course_id,
            course_data['title'],
            course_data.get('short_description'),
            course_data.get('description'),
            course_data['author_id'],
            course_data.get('start_date', datetime.now().isoformat()),
            course_data.get('end_date'),
            course_data.get('is_active', True),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(course_id)

    def get_by_id(self, course_id: str) -> Optional['Course']:
        """Получение курса по ID"""
        query = "SELECT * FROM courses WHERE id = ?"
        result = self.db.execute_query(query, (course_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_all(self, skip: int = 0, limit: int = 100, active_only: bool = True) -> List['Course']:
        """Получение всех курсов"""
        if active_only:
            query = "SELECT * FROM courses WHERE is_active = 1 ORDER BY title LIMIT ? OFFSET ?"
        else:
            query = "SELECT * FROM courses ORDER BY title LIMIT ? OFFSET ?"

        results = self.db.execute_query(query, (limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def get_by_author(self, author_id: str, skip: int = 0, limit: int = 100) -> List['Course']:
        """Получение курсов по автору"""
        query = "SELECT * FROM courses WHERE author_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (author_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, course_id: str, update_data: Dict[str, Any]) -> Optional['Course']:
        """Обновление курса"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(course_id)

        query = f"UPDATE courses SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(course_id)

    def delete(self, course_id: str) -> bool:
        """Удаление курса"""
        query = "DELETE FROM courses WHERE id = ?"
        try:
            self.db.execute_query(query, (course_id,))
            return True
        except:
            return False

    # Специальные запросы
    def get_top_students(self, course_id: str, start_date: datetime = None,
                         end_date: datetime = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Топ N лучших студентов выбранного курса за период
        """
        query = """
        SELECT pc.*, u.id as student_id, u.first_name, u.last_name, u.email
        FROM progress_courses pc
        JOIN users u ON pc.user_id = u.id
        WHERE pc.course_id = ? 
          AND u.role = 'student'
          AND pc.status = 'completed'
        """

        params = [course_id]

        if start_date:
            query += " AND pc.finished_at >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND pc.finished_at <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY pc.final_score DESC LIMIT ?"
        params.append(limit)

        results = self.db.execute_query(query, tuple(params))

        top_students = []
        for rank, progress in enumerate(results, 1):
            # Получаем детальную информацию о тестах для этого студента
            test_query = """
            SELECT tr.*, t.title as test_title
            FROM test_results tr
            JOIN tests t ON tr.test_id = t.id
            JOIN modules m ON t.module_id = m.id
            WHERE tr.user_id = ? AND m.course_id = ?
            """
            test_results = self.db.execute_query(test_query, (progress['student_id'], course_id))

            student_data = {
                "rank": rank,
                "student_id": progress['student_id'],
                "student_name": f"{progress['first_name']} {progress['last_name']}",
                "email": progress['email'],
                "final_score": progress['final_score'],
                "progress_percent": progress['progress_percent'],
                "finished_at": progress['finished_at'],
                "test_results": [
                    {
                        "test_id": tr['test_id'],
                        "score": tr['score'],
                        "max_score": tr['max_score'],
                        "percentage": round((tr['score'] / tr['max_score']) * 100, 2) if tr['max_score'] > 0 else 0,
                        "finished_at": tr['finished_at']
                    }
                    for tr in test_results
                ],
                "average_test_score": 0
            }

            # Рассчитываем средний балл по тестам
            if test_results:
                total_percentage = 0
                for tr in test_results:
                    if tr['max_score'] > 0:
                        total_percentage += (tr['score'] / tr['max_score']) * 100
                avg_score = total_percentage / len(test_results) if test_results else 0
                student_data["average_test_score"] = round(avg_score, 2)

            top_students.append(student_data)

        return top_students

    def get_completion_stats(self, course_id: str) -> Dict[str, Any]:
        """
        Статистика прохождения курса
        """
        # Общее количество студентов на курсе
        total_query = "SELECT COUNT(*) as count FROM progress_courses WHERE course_id = ?"
        total_result = self.db.execute_query(total_query, (course_id,), fetch_one=True)
        total_students = total_result['count'] if total_result else 0

        # Количество завершивших курс
        completed_query = """
        SELECT COUNT(*) as count FROM progress_courses 
        WHERE course_id = ? AND status = 'completed'
        """
        completed_result = self.db.execute_query(completed_query, (course_id,), fetch_one=True)
        completed_students = completed_result['count'] if completed_result else 0

        # Количество активных студентов
        active_query = """
        SELECT COUNT(*) as count FROM progress_courses 
        WHERE course_id = ? AND status = 'active'
        """
        active_result = self.db.execute_query(active_query, (course_id,), fetch_one=True)
        active_students = active_result['count'] if active_result else 0

        # Количество бросивших курс
        dropped_query = """
        SELECT COUNT(*) as count FROM progress_courses 
        WHERE course_id = ? AND status = 'dropped'
        """
        dropped_result = self.db.execute_query(dropped_query, (course_id,), fetch_one=True)
        dropped_students = dropped_result['count'] if dropped_result else 0

        # Средний прогресс по курсу
        avg_progress_query = """
        SELECT AVG(progress_percent) as avg_progress FROM progress_courses 
        WHERE course_id = ? AND status = 'active'
        """
        avg_progress_result = self.db.execute_query(avg_progress_query, (course_id,), fetch_one=True)
        avg_progress = avg_progress_result['avg_progress'] if avg_progress_result and avg_progress_result[
            'avg_progress'] else 0

        # Средний финальный балл
        avg_score_query = """
        SELECT AVG(final_score) as avg_score FROM progress_courses 
        WHERE course_id = ? AND status = 'completed' AND final_score IS NOT NULL
        """
        avg_score_result = self.db.execute_query(avg_score_query, (course_id,), fetch_one=True)
        avg_final_score = avg_score_result['avg_score'] if avg_score_result and avg_score_result['avg_score'] else 0

        return {
            "course_id": course_id,
            "total_students": total_students,
            "completed_students": completed_students,
            "active_students": active_students,
            "dropped_students": dropped_students,
            "completion_rate": round((completed_students / total_students * 100) if total_students > 0 else 0, 2),
            "dropout_rate": round((dropped_students / total_students * 100) if total_students > 0 else 0, 2),
            "average_progress": round(avg_progress, 2),
            "average_final_score": round(avg_final_score, 2)
        }


class Module(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.course_id = None
        self.title = None
        self.short_description = None
        self.module_order = None
        self.estimated_duration = None
        self.created_at = None

    def create(self, module_data: Dict[str, Any]) -> 'Module':
        """Создание нового модуля"""
        # Генерация ID
        query = "SELECT id FROM modules ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        module_id = generate_id("MOD", seq_num)

        query = """
        INSERT INTO modules (id, course_id, title, short_description, module_order, estimated_duration, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            module_id,
            module_data['course_id'],
            module_data['title'],
            module_data.get('short_description'),
            module_data['module_order'],
            module_data.get('estimated_duration'),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(module_id)

    def get_by_id(self, module_id: str) -> Optional['Module']:
        """Получение модуля по ID"""
        query = "SELECT * FROM modules WHERE id = ?"
        result = self.db.execute_query(query, (module_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_course(self, course_id: str, skip: int = 0, limit: int = 100) -> List['Module']:
        """Получение модулей курса"""
        query = "SELECT * FROM modules WHERE course_id = ? ORDER BY module_order LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (course_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, module_id: str, update_data: Dict[str, Any]) -> Optional['Module']:
        """Обновление модуля"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(module_id)

        query = f"UPDATE modules SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(module_id)

    def delete(self, module_id: str) -> bool:
        """Удаление модуля"""
        query = "DELETE FROM modules WHERE id = ?"
        try:
            self.db.execute_query(query, (module_id,))
            return True
        except:
            return False


class Test(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.module_id = None
        self.course_id = None
        self.title = None
        self.description = None
        self.time_limit = None
        self.max_score = None
        self.created_at = None

    def get_all(self, skip: int = 0, limit: int = 100) -> List['Test']:
        """Получение всех тестов"""
        query = "SELECT * FROM tests ORDER BY created_at DESC LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def create(self, test_data: Dict[str, Any]) -> 'Test':
        """Создание нового теста"""
        # Генерация ID
        query = "SELECT id FROM tests ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        test_id = generate_id("TST", seq_num)

        query = """
        INSERT INTO tests (id, module_id, course_id, title,
         description, time_limit, max_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            test_id,
            test_data.get('module_id'),
            test_data.get('course_id'),
            test_data['title'],
            test_data.get('description'),
            test_data.get('time_limit'),
            test_data.get('max_score', 100),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(test_id)

    def get_by_id(self, test_id: str) -> Optional['Test']:
        """Получение теста по ID"""
        query = "SELECT * FROM tests WHERE id = ?"
        result = self.db.execute_query(query, (test_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_module(self, module_id: str, skip: int = 0, limit: int = 100) -> List['Test']:
        """Получение тестов модуля"""
        query = "SELECT * FROM tests WHERE module_id = ? ORDER BY created_at LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (module_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def get_by_course(self, course_id: str, skip: int = 0, limit: int = 100) -> List['Test']:
        """Получение тестов курса"""
        query = "SELECT * FROM tests WHERE course_id = ? ORDER BY created_at LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (course_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, test_id: str, update_data: Dict[str, Any]) -> Optional['Test']:
        """Обновление теста"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(test_id)

        query = f"UPDATE tests SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(test_id)

    def delete(self, test_id: str) -> bool:
        """Удаление теста"""
        query = "DELETE FROM tests WHERE id = ?"
        try:
            self.db.execute_query(query, (test_id,))
            return True
        except:
            return False

    # Специальные запросы
    def get_completion_stats(self, test_id: str, start_date: datetime = None,
                             end_date: datetime = None) -> Dict[str, Any]:
        """
        Статистика прохождения теста за период
        """
        test = self.get_by_id(test_id)
        if not test:
            raise ValueError("Тест не найден")

        # Базовый запрос для результатов теста
        query = "SELECT * FROM test_results WHERE test_id = ?"
        params = [test_id]

        if start_date:
            query += " AND finished_at >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND finished_at <= ?"
            params.append(end_date.isoformat())

        results = self.db.execute_query(query, tuple(params))

        total_attempts = len(results)
        if total_attempts == 0:
            return {
                "test_id": test_id,
                "test_title": test.title,
                "total_attempts": 0,
                "average_score": 0,
                "pass_rate": 0,
                "score_distribution": {},
                "duration_stats": {}
            }

        # Рассчитываем средний балл
        total_score = sum(r['score'] for r in results)
        avg_score = total_score / total_attempts

        # Рассчитываем процент сдачи (если балл >= 60%)
        pass_threshold = test.max_score * 0.6
        passed_attempts = sum(1 for r in results if r['score'] >= pass_threshold)
        pass_rate = (passed_attempts / total_attempts) * 100

        # Распределение баллов
        score_distribution = {
            "0-20%": 0,
            "21-40%": 0,
            "41-60%": 0,
            "61-80%": 0,
            "81-100%": 0
        }

        for result in results:
            if test.max_score and test.max_score > 0:
                percentage = (result['score'] / test.max_score) * 100
            else:
                percentage = 0

            if percentage <= 20:
                score_distribution["0-20%"] += 1
            elif percentage <= 40:
                score_distribution["21-40%"] += 1
            elif percentage <= 60:
                score_distribution["41-60%"] += 1
            elif percentage <= 80:
                score_distribution["61-80%"] += 1
            else:
                score_distribution["81-100%"] += 1

        # Статистика по времени выполнения
        durations = [r['duration_sec'] for r in results if r['duration_sec']]
        if durations:
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
        else:
            avg_duration = min_duration = max_duration = 0

        return {
            "test_id": test_id,
            "test_title": test.title,
            "total_attempts": total_attempts,
            "unique_students": len(set(r['user_id'] for r in results)),
            "average_score": round(avg_score, 2),
            "average_percentage": round((avg_score / test.max_score) * 100,
                                        2) if test.max_score and test.max_score > 0 else 0,
            "pass_rate": round(pass_rate, 2),
            "score_distribution": score_distribution,
            "duration_stats": {
                "average_seconds": round(avg_duration, 2),
                "min_seconds": min_duration,
                "max_seconds": max_duration
            }
        }


class Question(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.test_id = None
        self.text = None
        self.type = None
        self.points = None
        self.question_order = None
        self.created_at = None

    def get_by_test(self, test_id: str) -> List['Question']:
        """Получение вопросов теста"""
        query = "SELECT * FROM questions WHERE test_id = ? ORDER BY question_order"
        results = self.db.execute_query(query, (test_id,))
        return [self.from_dict(row, self.db) for row in results]

    def get_by_id(self, question_id: str) -> Optional['Question']:
        """Получение вопроса по ID"""
        query = "SELECT * FROM questions WHERE id = ?"
        result = self.db.execute_query(query, (question_id,), fetch_one=True)
        if result:
            return self.from_dict(result, self.db)
        return None

    def create(self, question_data: Dict[str, Any]) -> 'Question':
        """Создание нового вопроса"""
        # Генерация ID
        query = "SELECT id FROM questions ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        question_id = generate_id("QUE", seq_num)

        query = """
        INSERT INTO questions (id, test_id, text, type, points, question_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            question_id,
            question_data['test_id'],
            question_data['text'],
            question_data.get('type', 'single'),
            question_data.get('points', 1),
            question_data.get('question_order', 1),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)
        return self.get_by_id(question_id)

    def update(self, question_id: str, update_data: Dict[str, Any]) -> Optional['Question']:
        """Обновление вопроса"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(question_id)

        query = f"UPDATE questions SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(question_id)

    def delete(self, question_id: str) -> bool:
        """Удаление вопроса"""
        query = "DELETE FROM questions WHERE id = ?"
        try:
            self.db.execute_query(query, (question_id,))
            return True
        except:
            return False


class Answer(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.question_id = None
        self.text = None
        self.is_correct = None
        self.answer_order = None
        self.created_at = None

    def create(self, answer_data: Dict[str, Any]) -> 'Answer':
        """Создание нового ответа"""
        # Генерация ID
        query = "SELECT id FROM answers ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        answer_id = generate_id("ANS", seq_num)

        query = """
        INSERT INTO answers (id, question_id, text, is_correct, answer_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            answer_id,
            answer_data['question_id'],
            answer_data['text'],
            answer_data.get('is_correct', False),
            answer_data.get('answer_order', 1),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(answer_id)

    def get_by_id(self, answer_id: str) -> Optional['Answer']:
        """Получение ответа по ID"""
        query = "SELECT * FROM answers WHERE id = ?"
        result = self.db.execute_query(query, (answer_id,), fetch_one=True)
        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_question(self, question_id: str) -> List['Answer']:
        """Получение ответов вопроса"""
        query = "SELECT * FROM answers WHERE question_id = ? ORDER BY answer_order"
        results = self.db.execute_query(query, (question_id,))
        return [self.from_dict(row, self.db) for row in results]

    def update(self, answer_id: str, update_data: Dict[str, Any]) -> Optional['Answer']:
        """Обновление ответа"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(answer_id)

        query = f"UPDATE answers SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        # Получаем обновленный ответ
        return self.get_by_id(answer_id)

    def delete(self, answer_id: str) -> bool:
        """Удаление ответа"""
        query = "DELETE FROM answers WHERE id = ?"
        try:
            self.db.execute_query(query, (answer_id,))
            return True
        except:
            return False

class ProgressCourse(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.user_id = None
        self.course_id = None
        self.enrolled_at = None  # Используется вместо started_at
        self.status = None
        self.progress_percent = None
        self.final_score = None
        self.finished_at = None

    def _create_object(self, row):
        """Создание объекта из строки БД"""
        progress = ProgressCourse(self.db)
        progress.id = row['id']
        progress.user_id = row['user_id']
        progress.course_id = row['course_id']
        progress.enrolled_at = row['enrolled_at']
        progress.status = row['status']
        progress.progress_percent = row['progress_percent']
        progress.final_score = row['final_score']
        progress.finished_at = row['finished_at']
        return progress

    def create(self, progress_data: Dict[str, Any]) -> 'ProgressCourse':
        """Создание новой записи прогресса по курсу"""
        # Генерация ID
        query = "SELECT id FROM progress_courses ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        progress_id = generate_id("PCR", seq_num)

        query = """
        INSERT INTO progress_courses (id, user_id, course_id, enrolled_at, status, 
                                    progress_percent, final_score, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            progress_id,
            progress_data['user_id'],
            progress_data['course_id'],
            progress_data.get('enrolled_at', datetime.now().isoformat()),
            progress_data.get('status', EnrollmentStatus.ACTIVE.value),
            progress_data.get('progress_percent', 0.0),
            progress_data.get('final_score'),
            progress_data.get('finished_at')
        )

        self.db.execute_query(query, params)

        return self.get_by_id(progress_id)

    def get_by_id(self, progress_id: str) -> Optional['ProgressCourse']:
        """Получение прогресса по ID"""
        query = "SELECT * FROM progress_courses WHERE id = ?"
        result = self.db.execute_query(query, (progress_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_user_and_course(self, user_id: str, course_id: str) -> Optional['ProgressCourse']:
        """Получение прогресса пользователя по курсу"""
        query = "SELECT * FROM progress_courses WHERE user_id = ? AND course_id = ?"
        result = self.db.execute_query(query, (user_id, course_id), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> List['ProgressCourse']:
        """Получение прогресса пользователя по всем курсам"""
        query = "SELECT * FROM progress_courses WHERE user_id = ? ORDER BY enrolled_at DESC LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (user_id, limit, skip))

        if results:
            return [self.from_dict(row, self.db) for row in results]
        return []

    def get_by_course(self, course_id: str, skip: int = 0, limit: int = 100) -> List['ProgressCourse']:
        """Получение прогресса всех пользователей по курсу"""
        query = "SELECT * FROM progress_courses WHERE course_id = ? ORDER BY enrolled_at DESC LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (course_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, progress_id: str, update_data: Dict[str, Any]) -> Optional['ProgressCourse']:
        """Обновление прогресса"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(progress_id)

        query = f"UPDATE progress_courses SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(progress_id)

    def delete(self, progress_id: str) -> bool:
        """Удаление прогресса"""
        query = "DELETE FROM progress_courses WHERE id = ?"
        try:
            self.db.execute_query(query, (progress_id,))
            return True
        except:
            return False

    def update_progress_percent(self, enrollment_id: str) -> Optional['ProgressCourse']:
        """
        Обновление процента прогресса по курсу на основе прогресса по модулям
        """
        progress = self.get_by_id(enrollment_id)
        if not progress:
            return None

        # Получаем все модули курса
        module_query = "SELECT COUNT(*) as count FROM modules WHERE course_id = ?"
        module_result = self.db.execute_query(module_query, (progress.course_id,), fetch_one=True)
        course_modules = module_result['count'] if module_result else 0

        if course_modules == 0:
            update_data = {"progress_percent": 0}
            return self.update(enrollment_id, update_data)

        # Получаем прогресс по всем модулям этого курса для данного пользователя
        progress_query = """
        SELECT pm.progress_percent 
        FROM progress_modules pm
        JOIN modules m ON pm.module_id = m.id
        WHERE pm.enrollment_id = ? AND m.course_id = ?
        """
        module_progress = self.db.execute_query(progress_query, (enrollment_id, progress.course_id))

        # Рассчитываем средний прогресс по модулям
        if module_progress:
            total_progress = sum(mp['progress_percent'] for mp in module_progress)
            avg_progress = total_progress / course_modules if course_modules > 0 else 0
        else:
            avg_progress = 0

        update_data = {"progress_percent": round(avg_progress, 2)}
        return self.update(enrollment_id, update_data)


class ProgressModule(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.enrollment_id = None
        self.module_id = None
        self.status = None
        self.progress_percent = None
        self.started_at = None
        self.finished_at = None

    def create(self, progress_data: Dict[str, Any]) -> 'ProgressModule':
        """Создание новой записи прогресса по модулю"""
        # Генерация ID
        query = "SELECT id FROM progress_modules ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        progress_id = generate_id("PMD", seq_num)

        query = """
        INSERT INTO progress_modules (id, enrollment_id, module_id, status, 
                                    progress_percent, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            progress_id,
            progress_data['enrollment_id'],
            progress_data['module_id'],
            progress_data.get('status', ProgressStatus.NOT_STARTED.value),
            progress_data.get('progress_percent', 0.0),
            progress_data.get('started_at'),
            progress_data.get('finished_at')
        )

        self.db.execute_query(query, params)

        return self.get_by_id(progress_id)

    def get_by_id(self, progress_id: str) -> Optional['ProgressModule']:
        """Получение прогресса по ID"""
        query = "SELECT * FROM progress_modules WHERE id = ?"
        result = self.db.execute_query(query, (progress_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_enrollment_and_module(self, enrollment_id: str, module_id: str) -> Optional['ProgressModule']:
        """Получение прогресса по enrollment и модулю"""
        query = "SELECT * FROM progress_modules WHERE enrollment_id = ? AND module_id = ?"
        result = self.db.execute_query(query, (enrollment_id, module_id), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def update(self, progress_id: str, update_data: Dict[str, Any]) -> Optional['ProgressModule']:
        """Обновление прогресса"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(progress_id)

        query = f"UPDATE progress_modules SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(progress_id)

    def delete(self, progress_id: str) -> bool:
        """Удаление прогресса"""
        query = "DELETE FROM progress_modules WHERE id = ?"
        try:
            self.db.execute_query(query, (progress_id,))
            return True
        except:
            return False

    def mark_as_completed(self, progress_id: str, progress_percent: float = 100.0) -> Optional['ProgressModule']:
        """
        Отметить модуль как завершенный
        """
        update_data = {
            "status": ProgressStatus.COMPLETED.value,
            "progress_percent": progress_percent,
            "finished_at": datetime.now().isoformat()
        }

        progress = self.get_by_id(progress_id)
        if progress and not progress.started_at:
            update_data["started_at"] = datetime.now().isoformat()

        return self.update(progress_id, update_data)


class TestResult(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.user_id = None
        self.test_id = None
        self.score = None
        self.max_score = None
        self.started_at = None
        self.finished_at = None  # Может быть NULL пока тест не завершен
        self.duration_sec = None
        self.created_at = None

    def get_all_completed(self):
        """Получить все завершенные результаты тестов"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM test_results 
            WHERE finished_at IS NOT NULL 
            ORDER BY finished_at DESC
        ''')
        rows = cursor.fetchall()
        return [TestResult.from_dict(row) for row in rows]

    def get_all(self):
        """Получить все результаты тестов (включая незавершенные)"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM test_results ORDER BY started_at DESC')
        rows = cursor.fetchall()
        return [TestResult.from_dict(row) for row in rows]

    def create(self, result_data: Dict[str, Any]) -> 'TestResult':
        """Создание нового результата теста - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
        try:
            # Генерация ID
            query = "SELECT id FROM test_results ORDER BY id DESC LIMIT 1"
            result = self.db.execute_query(query)

            seq_num = 1
            if result:
                last_id = result[0]['id']
                _, last_num = parse_id(last_id)
                if last_num:
                    seq_num = last_num + 1

            result_id = generate_id("TRS", seq_num)
            print(f"DEBUG: Генерируем ID результата теста: {result_id}")

            query = """
            INSERT INTO test_results (id, user_id, test_id, score, max_score, 
                                    started_at, finished_at, duration_sec, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            params = (
                result_id,
                result_data['user_id'],
                result_data['test_id'],
                result_data.get('score', 0.0),
                result_data.get('max_score', 100.0),
                result_data['started_at'],
                result_data.get('finished_at'),  # Может быть NULL
                result_data.get('duration_sec', 0),
                datetime.now().isoformat()
            )

            print(f"DEBUG: Вставляем результат теста: {params}")
            self.db.execute_query(query, params)
            print(f"DEBUG: Результат теста создан в БД: {result_id}")

            # Получаем созданный результат
            created_result = self.get_by_id(result_id)
            if created_result:
                print(f"DEBUG: Успешно получен созданный результат: {created_result.id}")
                return created_result
            else:
                print(f"DEBUG: ОШИБКА: Не удалось получить созданный результат из БД")
                return None

        except Exception as e:
            print(f"Ошибка при создании результата теста: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_by_id(self, result_id: str) -> Optional['TestResult']:
        """Получение результата по ID"""
        query = "SELECT * FROM test_results WHERE id = ?"
        result = self.db.execute_query(query, (result_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_user_and_test(self, user_id: str, test_id: str,
                             skip: int = 0, limit: int = 100) -> List['TestResult']:
        """Получение результатов пользователя по тесту"""
        query = """
        SELECT * FROM test_results 
        WHERE user_id = ? AND test_id = ? 
        ORDER BY finished_at DESC 
        LIMIT ? OFFSET ?
        """
        results = self.db.execute_query(query, (user_id, test_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def get_best_result(self, user_id: str, test_id: str) -> Optional['TestResult']:
        """Получение лучшего результата пользователя по тесту"""
        query = """
        SELECT * FROM test_results 
        WHERE user_id = ? AND test_id = ? 
        ORDER BY score DESC 
        LIMIT 1
        """
        result = self.db.execute_query(query, (user_id, test_id), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def update(self, result_id: str, update_data: Dict[str, Any]) -> Optional['TestResult']:
        """Обновление результата"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(result_id)

        query = f"UPDATE test_results SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(result_id)

    def delete(self, result_id: str) -> bool:
        """Удаление результата"""
        query = "DELETE FROM test_results WHERE id = ?"
        try:
            self.db.execute_query(query, (result_id,))
            return True
        except:
            return False


class UserAnswer(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.test_result_id = None
        self.question_id = None
        self.answer_id = None
        self.text_answer = None
        self.is_correct = None
        self.created_at = None

    def create(self, answer_data: Dict[str, Any]) -> 'UserAnswer':
        """Создание нового ответа пользователя"""
        # Генерация ID
        query = "SELECT id FROM user_answers ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        answer_id = generate_id("UAS", seq_num)

        query = """
        INSERT INTO user_answers (id, test_result_id, question_id, answer_id, 
                                text_answer, is_correct, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            answer_id,
            answer_data['test_result_id'],
            answer_data['question_id'],
            answer_data.get('answer_id'),
            answer_data.get('text_answer'),
            answer_data.get('is_correct'),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(answer_id)

    def get_by_id(self, answer_id: str) -> Optional['UserAnswer']:
        """Получение ответа по ID"""
        query = "SELECT * FROM user_answers WHERE id = ?"
        result = self.db.execute_query(query, (answer_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_test_result(self, test_result_id: str, skip: int = 0, limit: int = 100) -> List['UserAnswer']:
        """Получение ответов по результату теста"""
        query = "SELECT * FROM user_answers WHERE test_result_id = ? LIMIT ? OFFSET ?"
        results = self.db.execute_query(query, (test_result_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, answer_id: str, update_data: Dict[str, Any]) -> Optional['UserAnswer']:
        """Обновление ответа"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(answer_id)

        query = f"UPDATE user_answers SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(answer_id)

    def delete(self, answer_id: str) -> bool:
        """Удаление ответа"""
        query = "DELETE FROM user_answers WHERE id = ?"
        try:
            self.db.execute_query(query, (answer_id,))
            return True
        except:
            return False


# Сервис аналитики для сложных запросов
class AnalyticsService:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_course_completion_rate(self, course_id: str) -> Dict[str, Any]:
        """
        Получение процента завершения курса
        """
        course_model = Course(self.db)
        return course_model.get_completion_stats(course_id)

    def get_test_completion_stats(self, test_id: str,
                                  start_date: datetime = None,
                                  end_date: datetime = None) -> Dict[str, Any]:
        """
        Получение статистики прохождения теста
        """
        test_model = Test(self.db)
        return test_model.get_completion_stats(test_id, start_date, end_date)

    def get_top_performers(self, course_id: str,
                           start_date: datetime = None,
                           end_date: datetime = None,
                           limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получение топ-N лучших студентов курса за период
        """
        course_model = Course(self.db)
        return course_model.get_top_students(course_id, start_date, end_date, limit)

    def get_student_progress_detail(self, student_id: str,
                                    start_date: datetime = None,
                                    end_date: datetime = None) -> Dict[str, Any]:
        """
        Детальный прогресс обучения конкретного студента за период
        """
        user_model = User(self.db)
        return user_model.get_student_progress(student_id, start_date, end_date)

    def get_learning_trends(self, course_id: str,
                            start_date: datetime = None,
                            end_date: datetime = None) -> Dict[str, Any]:
        """
        Анализ трендов обучения на курсе
        """
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            # По умолчанию последние 30 дней
            from datetime import timedelta
            start_date = end_date - timedelta(days=30)

        # Группировка по дням
        enrollments_query = """
        SELECT DATE(enrolled_at) as date, COUNT(*) as count
        FROM progress_courses
        WHERE course_id = ? AND enrolled_at >= ? AND enrolled_at <= ?
        GROUP BY DATE(enrolled_at)
        ORDER BY date
        """

        enrollments_result = self.db.execute_query(
            enrollments_query,
            (course_id, start_date.isoformat(), end_date.isoformat())
        )

        completions_query = """
        SELECT DATE(finished_at) as date, COUNT(*) as count
        FROM progress_courses
        WHERE course_id = ? AND status = 'completed' 
          AND finished_at >= ? AND finished_at <= ?
        GROUP BY DATE(finished_at)
        ORDER BY date
        """

        completions_result = self.db.execute_query(
            completions_query,
            (course_id, start_date.isoformat(), end_date.isoformat())
        )

        # Конвертируем в словари
        enrollments_dict = {row['date']: row['count'] for row in enrollments_result}
        completions_dict = {row['date']: row['count'] for row in completions_result}

        return {
            "course_id": course_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "enrollments_by_date": enrollments_dict,
            "completions_by_date": completions_dict,
            "total_enrollments": sum(enrollments_dict.values()),
            "total_completions": sum(completions_dict.values()),
            "completion_rate_trend": {
                "daily": {
                    date: round((completions_dict.get(date, 0) / max(enrollments_dict.get(date, 1), 1) * 100), 2)
                    for date in enrollments_dict.keys()
                }
            }
        }


# Добавим модель для учебных материалов
class LearningMaterial(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.module_id = None
        self.title = None
        self.content = None
        self.content_type = None  # 'text', 'video', 'pdf', 'link', 'quiz'
        self.material_order = None
        self.created_at = None

    def create(self, material_data: Dict[str, Any]) -> 'LearningMaterial':
        """Создание нового учебного материала"""
        # Генерация ID
        query = "SELECT id FROM learning_materials ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        material_id = generate_id("LMT", seq_num)

        query = """
        INSERT INTO learning_materials (id, module_id, title, content, content_type, material_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            material_id,
            material_data['module_id'],
            material_data['title'],
            material_data.get('content'),
            material_data.get('content_type', 'text'),
            material_data['material_order'],
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(material_id)

    def get_by_id(self, material_id: str) -> Optional['LearningMaterial']:
        """Получение материала по ID"""
        query = "SELECT * FROM learning_materials WHERE id = ?"
        result = self.db.execute_query(query, (material_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_module(self, module_id: str, skip: int = 0, limit: int = 100) -> List['LearningMaterial']:
        """Получение материалов модуля"""
        query = """
        SELECT * FROM learning_materials 
        WHERE module_id = ? 
        ORDER BY material_order 
        LIMIT ? OFFSET ?
        """
        results = self.db.execute_query(query, (module_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def update(self, material_id: str, update_data: Dict[str, Any]) -> Optional['LearningMaterial']:
        """Обновление материала"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(material_id)

        query = f"UPDATE learning_materials SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(material_id)

    def delete(self, material_id: str) -> bool:
        """Удаление материала"""
        query = "DELETE FROM learning_materials WHERE id = ?"
        try:
            self.db.execute_query(query, (material_id,))
            return True
        except:
            return False


# Демонстрация работы
def demo():
    """Демонстрация работы с базой данных"""
    print("=" * 50)
    print("Демонстрация работы образовательной платформы")
    print("=" * 50)

    # Инициализация базы данных
    db_connection = DatabaseConnection("demo_educational_platform.db")
    print("База данных инициализирована")

    # Создание моделей
    user_model = User(db_connection)
    course_model = Course(db_connection)
    analytics = AnalyticsService(db_connection)

    # Создание преподавателя
    teacher_data = {
        "last_name": "Петров",
        "first_name": "Алексей",
        "email": "teacher@example.com",
        "password_hash": "hashed_password_teacher",
        "role": UserRole.TEACHER.value
    }

    try:
        # Создание преподавателя
        teacher = user_model.create(teacher_data)
        print(f"Создан преподаватель: {teacher.id} - {teacher.first_name} {teacher.last_name}")

        # Создание курса
        course_data = {
            "title": "Основы программирования на Python",
            "short_description": "Курс для начинающих программистов",
            "description": "Изучите основы Python: переменные, функции, ООП и многое другое",
            "author_id": teacher.id,
            "start_date": datetime.now().isoformat(),
            "end_date": (datetime.now().replace(year=datetime.now().year + 1)).isoformat(),
            "is_active": True
        }

        course = course_model.create(course_data)
        print(f"Создан курс: {course.id} - {course.title}")

        # Создание студента
        student_data = {
            "last_name": "Сидоров",
            "first_name": "Иван",
            "email": "student@example.com",
            "password_hash": "hashed_password_student",
            "role": UserRole.STUDENT.value
        }

        student = user_model.create(student_data)
        print(f"Создан студент: {student.id} - {student.first_name} {student.last_name}")

        # Создание модуля для курса
        module_model = Module(db_connection)
        module_data = {
            "course_id": course.id,
            "title": "Введение в Python",
            "short_description": "Первые шаги в программировании",
            "module_order": 1,
            "estimated_duration": 120
        }

        module = module_model.create(module_data)
        print(f"Создан модуль: {module.id} - {module.title}")

        # Создание теста
        test_model = Test(db_connection)
        test_data = {
            "module_id": module.id,
            "course_id": course.id,
            "title": "Тест по основам Python",
            "description": "Проверка знаний основ Python",
            "time_limit": 60,
            "max_score": 100
        }

        test = test_model.create(test_data)
        print(f"Создан тест: {test.id} - {test.title}")

        # Создание прогресса студента по курсу
        progress_course_model = ProgressCourse(db_connection)
        progress_data = {
            "user_id": student.id,
            "course_id": course.id,
            "status": EnrollmentStatus.ACTIVE.value,
            "progress_percent": 25.5,
            "final_score": None
        }

        progress = progress_course_model.create(progress_data)
        print(f"Создан прогресс по курсу: {progress.id}")

        # Получение статистики курса
        print("\nСтатистика курса:")
        stats = course_model.get_completion_stats(course.id)
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Получение прогресса студента
        print("\nПрогресс студента:")
        student_progress = user_model.get_student_progress(student.id)
        print(f"  Всего курсов: {student_progress['total_courses']}")
        print(f"  Активных курсов: {student_progress['active_courses']}")

        # Аналитика
        print("\nАналитика курса:")
        trends = analytics.get_learning_trends(course.id)
        print(f"  Всего записей на курс: {trends['total_enrollments']}")

        print("\n" + "=" * 50)
        print("Демонстрация завершена успешно!")
        print("=" * 50)

    except Exception as e:
        print(f"Ошибка в демонстрации: {e}")
        import traceback
        traceback.print_exc()

class MaterialProgress(BaseModel):
    def __init__(self, db: DatabaseConnection = None):
        super().__init__(db)
        self.id = None
        self.user_id = None
        self.material_id = None
        self.module_id = None
        self.status = None  # 'not_started', 'in_progress', 'completed'
        self.completed_at = None
        self.time_spent_sec = None
        self.created_at = None

    def create(self, progress_data: Dict[str, Any]) -> 'MaterialProgress':
        """Создание новой записи прогресса по материалу"""
        # Генерация ID
        query = "SELECT id FROM material_progress ORDER BY id DESC LIMIT 1"
        result = self.db.execute_query(query)

        seq_num = 1
        if result:
            last_id = result[0]['id']
            _, last_num = parse_id(last_id)
            if last_num:
                seq_num = last_num + 1

        progress_id = generate_id("MPR", seq_num)

        query = """
        INSERT INTO material_progress (id, user_id, material_id, module_id, status, 
                                     completed_at, time_spent_sec, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            progress_id,
            progress_data['user_id'],
            progress_data['material_id'],
            progress_data['module_id'],
            progress_data.get('status', ProgressStatus.NOT_STARTED.value),
            progress_data.get('completed_at'),
            progress_data.get('time_spent_sec', 0),
            datetime.now().isoformat()
        )

        self.db.execute_query(query, params)

        return self.get_by_id(progress_id)

    def get_by_id(self, progress_id: str) -> Optional['MaterialProgress']:
        """Получение прогресса по ID"""
        query = "SELECT * FROM material_progress WHERE id = ?"
        result = self.db.execute_query(query, (progress_id,), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_user_and_material(self, user_id: str, material_id: str) -> Optional['MaterialProgress']:
        """Получение прогресса пользователя по материалу"""
        query = "SELECT * FROM material_progress WHERE user_id = ? AND material_id = ?"
        result = self.db.execute_query(query, (user_id, material_id), fetch_one=True)

        if result:
            return self.from_dict(result, self.db)
        return None

    def get_by_user_and_module(self, user_id: str, module_id: str,
                              skip: int = 0, limit: int = 100) -> List['MaterialProgress']:
        """Получение прогресса пользователя по всем материалам модуля"""
        query = """
        SELECT * FROM material_progress 
        WHERE user_id = ? AND module_id = ? 
        ORDER BY created_at 
        LIMIT ? OFFSET ?
        """
        results = self.db.execute_query(query, (user_id, module_id, limit, skip))

        return [self.from_dict(row, self.db) for row in results]

    def get_completed_materials(self, user_id: str, module_id: str) -> List[str]:
        """Получение списка ID завершенных материалов пользователя в модуле"""
        query = """
        SELECT material_id FROM material_progress 
        WHERE user_id = ? AND module_id = ? AND status = 'completed'
        """
        results = self.db.execute_query(query, (user_id, module_id))

        return [row['material_id'] for row in results]

    def get_progress_percentage(self, user_id: str, module_id: str) -> float:
        """Получение процента завершения материалов модуля пользователем"""
        # Получаем общее количество материалов в модуле
        query = "SELECT COUNT(*) as count FROM learning_materials WHERE module_id = ?"
        total_result = self.db.execute_query(query, (module_id,), fetch_one=True)
        total_materials = total_result['count'] if total_result else 0

        if total_materials == 0:
            return 0.0

        # Получаем количество завершенных материалов
        query = """
        SELECT COUNT(*) as count FROM material_progress 
        WHERE user_id = ? AND module_id = ? AND status = 'completed'
        """
        completed_result = self.db.execute_query(query, (user_id, module_id), fetch_one=True)
        completed_materials = completed_result['count'] if completed_result else 0

        return round((completed_materials / total_materials) * 100, 2)

    def update(self, progress_id: str, update_data: Dict[str, Any]) -> Optional['MaterialProgress']:
        """Обновление прогресса"""
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(progress_id)

        query = f"UPDATE material_progress SET {set_clause} WHERE id = ?"
        self.db.execute_query(query, tuple(values))

        return self.get_by_id(progress_id)

    def mark_as_completed(self, progress_id: str) -> Optional['MaterialProgress']:
        """Отметить материал как завершенный"""
        update_data = {
            "status": ProgressStatus.COMPLETED.value,
            "completed_at": datetime.now().isoformat()
        }
        return self.update(progress_id, update_data)

    def delete(self, progress_id: str) -> bool:
        """Удаление прогресса"""
        query = "DELETE FROM material_progress WHERE id = ?"
        try:
            self.db.execute_query(query, (progress_id,))
            return True
        except:
            return False

# Запуск демонстрации
if __name__ == "__main__":
    demo()