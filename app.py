#app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
import os
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
from config import config
from business_logic.auth import AuthService
from business_logic.courses import CourseService
from business_logic.tests import TestService
from database.models import Test, Course, TestResult, UserAnswer, Question, User, AnalyticsService, UserRole, Module, \
    Answer, QuestionType, ProgressCourse, EnrollmentStatus

# Инициализация Flask приложения
app = Flask(__name__)
app.config.from_object(config['default'])
config['default'].init_app(app)

# Инициализация сервисов
auth_service = AuthService(app.config['DATABASE_PATH'])
course_service = CourseService(app.config['DATABASE_PATH'])
test_service = TestService(app.config['DATABASE_PATH'])

BASE_DIR = os.path.dirname(__file__)

# Настройки базы данных
DB_PATH = os.path.join(BASE_DIR, 'database/educational_platform.db')

# Функция для получения соединения с БД
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Возвращаем строки как словари
    return conn

# Функция для коррекции баллов
def correct_test_score(score, max_score, test_id, user_id, auth_service):
    """Корректирует баллы теста если все ответы правильные"""
    # Если баллы уже максимальные или близки к максимальным
    if score >= max_score * 0.999:
        return max_score

    # Проверяем, все ли ответы были правильными
    try:
        # Находим результат теста с этим баллом
        test_result_model = TestResult(auth_service.db)
        results = test_result_model.get_by_user_and_test(user_id, test_id)

        for result in results:
            if result.finished_at and abs(float(result.score) - score) < 0.01:  # Нашли нужный результат
                # Проверяем количество правильных ответов
                user_answer_model = UserAnswer(auth_service.db)
                user_answers = user_answer_model.get_by_test_result(result.id)
                correct_answers_count = sum(1 for answer in user_answers if answer.is_correct)

                # Получаем количество вопросов в тесте
                question_model = Question(auth_service.db)
                total_questions = len(question_model.get_by_test(test_id))

                # Если все ответы правильные, возвращаем максимальный балл
                if total_questions > 0 and correct_answers_count == total_questions:
                    print(f"DEBUG correct_test_score: Все ответы правильные! Исправляем {score} на {max_score}")
                    return max_score
                break
    except Exception as e:
        print(f"Ошибка при проверке коррекции баллов: {e}")

    return score

# Декораторы для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Требуется авторизация', 'warning')
                return redirect(url_for('login'))

            if session.get('user_role') != required_role:
                flash('Доступ запрещен', 'danger')
                return redirect(url_for('index'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


# Главная страница
@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/student/test/<test_id>/start')
@login_required
@role_required('student')
def start_test(test_id):
    """Начать прохождение теста"""
    user_id = session.get('user_id')

    # Проверяем, может ли студент начать тест
    from database.models import Test
    test_model = Test(auth_service.db)

    test = test_model.get_by_id(test_id)
    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('student_tests'))

    # ПРЯМОЙ SQL ЗАПРОС для проверки лимита
    import sqlite3
    db_path = app.config['DATABASE_PATH']

    completed_attempts = 0
    best_score = 0.0
    max_score = getattr(test, 'max_score', 100)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Получаем количество завершенных попыток и лучший результат
        cursor.execute('''
            SELECT COUNT(*) as count, MAX(score) as best_score
            FROM test_results 
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL
        ''', (user_id, test_id))

        row = cursor.fetchone()
        completed_attempts = row[0] if row else 0
        best_score = float(row[1]) if row and row[1] is not None else 0.0

        conn.close()

        print(f"DEBUG [start_test SQL]: Завершенные попытки: {completed_attempts}, лучший результат: {best_score}")

    except Exception as e:
        print(f"Ошибка SQL запроса в start_test: {e}")

    if completed_attempts >= 3:
        flash(f'Лимит попыток исчерпан (3 попытки). Ваш лучший результат: {best_score}/{max_score}', 'warning')
        return redirect(url_for('student_test_detail', test_id=test_id))

    # Перенаправляем на страницу прохождения теста
    return redirect(url_for('take_test', test_id=test_id))


@app.route('/student/test/<test_id>')
@login_required
@role_required('student')
def student_test_detail(test_id):
    """Детальная страница теста с исправлением баллов"""
    user_id = session.get('user_id')

    # Получаем информацию о тесте
    from database.models import Test
    test_model = Test(auth_service.db)
    test = test_model.get_by_id(test_id)

    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('student_tests'))

    # ПРЯМОЙ SQL ЗАПРОС для получения результатов
    import sqlite3
    db_path = app.config['DATABASE_PATH']

    test_results = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        cursor = conn.cursor()

        # Получаем все завершенные результаты теста для пользователя
        cursor.execute('''
            SELECT id, test_id, user_id, score, max_score, started_at, finished_at, duration_sec
            FROM test_results 
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL
            ORDER BY finished_at DESC
        ''', (user_id, test_id))

        rows = cursor.fetchall()
        print(f"DEBUG SQL: Найдено {len(rows)} завершенных результатов")

        for row in rows:
            test_results.append({
                'test_id': row['test_id'],
                'result_id': row['id'],
                'id': row['id'],
                'score': float(row['score']) if row['score'] is not None else 0.0,
                'max_score': float(row['max_score']) if row['max_score'] is not None else 100.0,
                'started_at': row['started_at'],
                'finished_at': row['finished_at'],
                'duration_sec': row['duration_sec'] if row['duration_sec'] is not None else 0
            })

            print(f"DEBUG SQL: Результат {row['id']} - {row['score']}/{row['max_score']} - {row['finished_at']}")

        conn.close()

    except Exception as e:
        print(f"Ошибка SQL запроса: {e}")
        import traceback
        traceback.print_exc()

    # Получаем информацию о курсе
    from database.models import Module, Course
    module_model = Module(auth_service.db)
    course_model = Course(auth_service.db)

    course = None
    course_title = ""
    if hasattr(test, 'module_id') and test.module_id:
        module = module_model.get_by_id(test.module_id)
        if module and hasattr(module, 'course_id'):
            course = course_model.get_by_id(module.course_id)
            if course:
                course_title = course.title

    # Получаем ТОЛЬКО ЗАВЕРШЕННЫЕ попытки
    completed_attempts = test_results  # Уже отфильтрованы в SQL
    print(f"DEBUG: Завершенные попытки: {len(completed_attempts)}")

    attempts_used = len(completed_attempts)

    # Получаем лучший результат из ЗАВЕРШЕННЫХ попыток
    best_score = None
    if completed_attempts:
        try:
            # Получаем все оценки из завершенных тестов
            scores = [r.get('score', 0) for r in completed_attempts if r.get('score') is not None]
            print(f"DEBUG: Найденные оценки: {scores}")
            if scores:
                best_score_raw = max(scores)
                # Корректируем балл если все ответы правильные
                max_score = getattr(test, 'max_score', 100)
                best_score = correct_test_score(best_score_raw, max_score, test_id, user_id, auth_service)
                print(f"DEBUG: Лучший результат после коррекции: {best_score_raw} -> {best_score}")
        except (ValueError, TypeError) as e:
            print(f"DEBUG: Ошибка при получении лучшего результата: {e}")
            best_score = None

    # Проверяем, может ли студент начать тест
    can_start = True
    unavailable_reason = ""

    # Безопасно получаем атрибуты теста с дефолтными значениями
    time_limit = getattr(test, 'time_limit', 60)
    max_score = getattr(test, 'max_score', 100)
    description = getattr(test, 'description', '')
    title = getattr(test, 'title', 'Тест')

    # Проверяем ограничения - максимально 3 попытки из бизнес-логики
    attempts_allowed = 3  # Фиксированный лимит согласно бизнес-логике

    print(f"DEBUG: attempts_used={attempts_used}, attempts_allowed={attempts_allowed}, best_score={best_score}")

    # Проверяем лимит попыток
    if attempts_used >= attempts_allowed:
        can_start = False
        unavailable_reason = f"Лимит попыток исчерпан ({attempts_allowed} попытки)"
        if best_score is not None:
            unavailable_reason += f". Ваш лучший результат: {best_score}/{max_score}"

    # Проверяем активность теста
    is_active = getattr(test, 'is_active', True)
    if not is_active:
        can_start = False
        unavailable_reason = "Тест недоступен"

    print(f"DEBUG: can_start={can_start}, unavailable_reason={unavailable_reason}")

    # Форматируем предыдущие попытки (только завершенные)
    previous_attempts = []
    for i, result in enumerate(completed_attempts, 1):
        score_raw = result.get('score', 0)
        # Корректируем балл если все ответы правильные
        score = correct_test_score(score_raw, max_score, test_id, user_id, auth_service)

        # Рассчитываем процент
        percentage = (score / max_score * 100) if max_score > 0 else 0

        # Форматируем дату
        finished_at = result.get('finished_at', '')
        if finished_at:
            try:
                # Пытаемся распарсить дату из SQLite
                if 'T' in finished_at:
                    # ISO формат: 2025-12-18T08:13:32.879177
                    dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                else:
                    # SQLite формат: 2025-12-18 08:13:32.879177
                    dt = datetime.strptime(finished_at, '%Y-%m-%d %H:%M:%S.%f')
                formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            except Exception as e:
                print(f"DEBUG: Ошибка форматирования даты {finished_at}: {e}")
                formatted_time = str(finished_at)[:16]  # Берем первые 16 символов
        else:
            formatted_time = ""

        previous_attempts.append({
            'attempt_number': i,
            'score': score,
            'percentage': round(percentage, 1),
            'finished_at': formatted_time,
            'duration_sec': result.get('duration_sec', 0),
            'result_id': result.get('result_id', '') or result.get('id', '')
        })

    # Подготавливаем данные для шаблона
    test_info = {
        'test_id': test_id,
        'test_title': title,
        'description': description,
        'duration_minutes': time_limit,
        'max_score': max_score,
        'attempts_allowed': attempts_allowed,
        'attempts_used': attempts_used,
        'best_score': best_score,
        'course_id': course.id if course else '',
        'course_title': course_title,
        'can_start': can_start,
        'unavailable_reason': unavailable_reason,
        'previous_attempts': previous_attempts
    }

    return render_template('student/test_detail.html',
                           test_info=test_info,
                           user_name=session.get('user_name'))


# Маршруты авторизации
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Заполните все поля', 'danger')
            return render_template('auth/login.html')

        success, message, user_data = auth_service.login_user(email, password)

        if success and user_data:
            # Сохраняем данные в сессии
            session['user_id'] = user_data['id']
            session['user_email'] = user_data['email']
            session['user_name'] = f"{user_data['first_name']} {user_data['last_name']}"
            session['user_role'] = user_data['role']
            session['logged_in'] = True

            flash('Вход выполнен успешно', 'success')

            # Перенаправляем в зависимости от роли
            if user_data['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user_data['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash(message or 'Ошибка входа', 'danger')

    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Страница регистрации"""
    if request.method == 'POST':
        # Получаем данные из формы
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        role = request.form.get('role', 'student').strip()

        # Валидация
        errors = []
        if not all([first_name, last_name, email, password, confirm_password]):
            errors.append('Заполните все поля')

        if password != confirm_password:
            errors.append('Пароли не совпадают')

        if len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html')

        # Подготавливаем данные для регистрации
        user_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'password': password,
            'role': role
        }

        success, message, user = auth_service.register_user(user_data)

        if success and user:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'danger')

    return render_template('auth/register.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


# ==================== СТУДЕНТ ====================

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    """Панель управления студента"""
    user_id = session.get('user_id')

    # Получаем курсы студента
    courses = course_service.get_student_courses(user_id)

    # Получаем статистику пользователя
    user_stats = auth_service.get_user_statistics(user_id)

    # Получаем аналитику тестов
    test_analytics = test_service.get_test_analytics(user_id)

    # Получаем результаты тестов для группировки по курсам
    all_results = test_service.get_test_results_for_student(user_id)

    # Группируем по курсам
    from database.models import Course
    course_model = Course(auth_service.db)

    tests_by_course = {}
    for result in all_results:
        course_id = result.get('course_id')
        if not course_id:
            continue

        if course_id not in tests_by_course:
            course = course_model.get_by_id(course_id)
            tests_by_course[course_id] = {
                'course_title': course.title if course else 'Неизвестный курс',
                'tests': []
            }

        tests_by_course[course_id]['tests'].append(result)

    return render_template('student/dashboard.html',
                           courses=courses,
                           user_stats=user_stats,
                           test_analytics=test_analytics,
                           tests_by_course=tests_by_course,
                           user_name=session.get('user_name'))


@app.route('/student/courses')
@login_required
@role_required('student')
def student_courses():
    """Страница курсов студента"""
    user_id = session.get('user_id')

    print(f"DEBUG: Получение курсов для студента {user_id}")

    # Получаем все активные курсы
    from database.models import Course
    db = auth_service.db
    course_model = Course(db)
    all_courses = course_model.get_all(active_only=True)

    # Получаем курсы, на которые записан студент
    enrolled_courses = []
    try:
        from database.models import ProgressCourse
        progress_course_model = ProgressCourse(db)
        user_progress = progress_course_model.get_by_user(user_id)

        for progress in user_progress:
            course = course_model.get_by_id(progress.course_id)
            if course:
                # Получаем прогресс для каждого курса
                from database.models import ProgressModule, Module
                progress_module_model = ProgressModule(db)
                module_model = Module(db)

                modules = module_model.get_by_course(course.id)
                total_modules = len(modules)
                completed_modules = 0

                for module in modules:
                    module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
                    if module_progress and module_progress.status == 'completed':
                        completed_modules += 1

                progress_percent = (completed_modules / total_modules * 100) if total_modules > 0 else 0

                enrolled_courses.append({
                    'course': course.to_dict(),
                    'progress': {
                        'id': progress.id,
                        'status': progress.status,
                        'progress_percent': round(progress_percent, 2),
                        'final_score': progress.final_score,
                        'enrolled_at': progress.enrolled_at,
                        'finished_at': progress.finished_at
                    }
                })
    except Exception as e:
        print(f"Ошибка получения записанных курсов: {e}")
        import traceback
        traceback.print_exc()

    enrolled_ids = [course['course']['id'] for course in enrolled_courses]

    # Разделяем курсы на записанные и доступные для записи
    available_courses = []
    for course in all_courses:
        if course.id not in enrolled_ids:
            available_courses.append(course.to_dict())

    print(f"DEBUG: Записанных курсов: {len(enrolled_courses)}, доступных курсов: {len(available_courses)}")

    # Для демонстрации, если нет курсов, создадим демо-данные
    if len(enrolled_courses) == 0 and len(available_courses) == 0:
        print("DEBUG: Создаем демо-курсы")
        # Создаем демо-курсы
        demo_courses = [
            {
                'id': 'demo_001',
                'title': 'Введение в Python для начинающих',
                'short_description': 'Изучите основы Python за 4 недели',
                'author_id': 'teacher_001'
            },
            {
                'id': 'demo_002',
                'title': 'Основы веб-разработки на Flask',
                'short_description': 'Создайте свое первое веб-приложение',
                'author_id': 'teacher_001'
            },
            {
                'id': 'demo_003',
                'title': 'Базы данных и SQL для разработчиков',
                'short_description': 'Научитесь работать с базами данных',
                'author_id': 'teacher_001'
            }
        ]

        available_courses = demo_courses

    return render_template('student/courses.html',
                           enrolled_courses=enrolled_courses,
                           available_courses=available_courses,
                           user_name=session.get('user_name'))

@app.route('/student/enroll_test_courses', methods=['POST'])
@login_required
@role_required('student')
def enroll_test_courses():
    """Записать студента на тестовые курсы для демонстрации"""
    user_id = session.get('user_id')

    # Находим активные курсы
    from database.models import Course
    db = auth_service.db
    course_model = Course(db)
    all_courses = course_model.get_all(active_only=True)

    # Проверяем, на какие курсы уже записан
    from database.models import ProgressCourse
    progress_model = ProgressCourse(db)
    enrolled_courses = progress_model.get_by_user(user_id)
    enrolled_ids = [progress.course_id for progress in enrolled_courses]

    # Записываем на первые 3 курса, если еще не записан
    enrolled_count = 0
    enrolled_course_titles = []

    for course in all_courses[:3]:
        if course.id not in enrolled_ids:
            # Записываем студента на курс
            progress_data = {
                'user_id': user_id,
                'course_id': course.id,
                'status': 'active',
                'enrolled_at': datetime.now().isoformat()
            }
            progress_model.create(progress_data)
            enrolled_count += 1
            enrolled_course_titles.append(course.title)

    if enrolled_count > 0:
        flash(f'Вы были успешно записаны на {enrolled_count} курс(а): {", ".join(enrolled_course_titles)}', 'success')
    else:
        flash('Вы уже записаны на все доступные демо-курсы', 'info')

    return redirect(url_for('student_courses'))

@app.route('/student/course/<course_id>')
@login_required
@role_required('student')
def student_course_detail(course_id):
    """Детальная страница курса для студента"""
    user_id = session.get('user_id')

    # Получаем информацию о курсе
    from database.models import Course, User, Module, ProgressCourse, ProgressModule, Test

    db = auth_service.db
    course_model = Course(db)
    user_model = User(db)
    module_model = Module(db)
    progress_course_model = ProgressCourse(db)
    progress_module_model = ProgressModule(db)
    test_model = Test(db)

    # Получаем курс
    course = course_model.get_by_id(course_id)
    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('student_courses'))

    # Получаем преподавателя
    teacher = user_model.get_by_id(course.author_id)

    # Получаем прогресс студента
    progress_obj = progress_course_model.get_by_user_and_course(user_id, course_id)
    if not progress_obj:
        flash('Вы не записаны на этот курс', 'danger')
        return redirect(url_for('student_courses'))

    # Конвертируем прогресс в словарь
    progress_dict = {}
    if hasattr(progress_obj, 'to_dict'):
        progress_dict = progress_obj.to_dict()
    else:
        # Создаем словарь вручную
        progress_dict = {
            'id': progress_obj.id,
            'user_id': progress_obj.user_id,
            'course_id': progress_obj.course_id,
            'status': progress_obj.status if hasattr(progress_obj, 'status') else 'in_progress',
            'started_at': progress_obj.started_at.isoformat() if hasattr(progress_obj.started_at, 'isoformat') else str(
                progress_obj.started_at),
            'completed_at': progress_obj.completed_at.isoformat() if hasattr(progress_obj,
                                                                             'completed_at') and progress_obj.completed_at else None
        }

    # Получаем модули курса
    modules = module_model.get_by_course(course_id)

    # Получаем прогресс по модулям и тесты
    module_list = []
    total_modules = len(modules)
    completed_modules = 0
    total_tests = 0

    for module in modules:
        # Прогресс модуля
        module_progress = progress_module_model.get_by_enrollment_and_module(progress_obj.id, module.id)

        # Тесты модуля
        module_tests = test_model.get_by_module(module.id)
        total_tests += len(module_tests)

        # Конвертируем прогресс модуля в словарь
        module_progress_dict = {}
        if module_progress and hasattr(module_progress, 'to_dict'):
            module_progress_dict = module_progress.to_dict()
        elif module_progress:
            module_progress_dict = {
                'id': module_progress.id,
                'enrollment_id': module_progress.enrollment_id,
                'module_id': module_progress.module_id,
                'status': module_progress.status if hasattr(module_progress, 'status') else 'in_progress',
                'started_at': module_progress.started_at.isoformat() if hasattr(module_progress.started_at,
                                                                                'isoformat') else str(
                    module_progress.started_at),
                'completed_at': module_progress.completed_at.isoformat() if hasattr(module_progress,
                                                                                    'completed_at') and module_progress.completed_at else None
            }

        # Формируем список тестов с информацией
        tests_list = []
        for test in module_tests:
            # Получаем результаты теста для этого пользователя
            test_results = []
            try:
                # Используем старый метод до исправления
                from database.models import TestResult
                test_result_model = TestResult(db)
                results = test_result_model.get_by_user_and_test(user_id, test.id)

                for result in results:
                    if result.finished_at:
                        test_results.append({
                            'test_id': test.id,
                            'result_id': result.id,
                            'score': float(result.score) if result.score else 0.0,
                            'max_score': float(result.max_score) if result.max_score else 100.0
                        })
            except Exception as e:
                print(f"Ошибка получения результатов теста {test.id}: {e}")

            test_taken = len(test_results) > 0

            # Получаем лучший результат
            best_score = None
            if test_taken and test_results:
                best_score = max(r['score'] for r in test_results)

            tests_list.append({
                'id': test.id,
                'title': test.title,
                'description': getattr(test, 'description', ''),
                'duration_minutes': getattr(test, 'time_limit', 60),
                'max_score': getattr(test, 'max_score', 100),
                'taken': test_taken,
                'best_score': best_score,
                'attempts_allowed': 3,
                'attempts_used': len(test_results),
                'result_id': test_results[0]['result_id'] if test_results else None
            })

        # Считаем завершенные модули
        if module_progress and module_progress.status == 'completed':
            completed_modules += 1

        # Конвертируем модуль в словарь
        module_dict = {}
        if hasattr(module, 'to_dict'):
            module_dict = module.to_dict()
        else:
            module_dict = {
                'id': module.id,
                'course_id': module.course_id,
                'title': module.title,
                'description': module.description if hasattr(module, 'description') else '',
                'order_index': module.order_index if hasattr(module, 'order_index') else 1,
                'created_at': module.created_at.isoformat() if hasattr(module.created_at, 'isoformat') else str(
                    module.created_at)
            }

        module_list.append({
            'module': module_dict,
            'progress': module_progress_dict,
            'tests': tests_list
        })

    # Рассчитываем процент завершения курса
    completion_percentage = (completed_modules / total_modules * 100) if total_modules > 0 else 0

    # Получаем результаты тестов по курсу - используем упрощенный метод
    test_results = []
    try:
        # Используем прямой SQL запрос для получения результатов
        import sqlite3
        db_path = app.config['DATABASE_PATH']

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем все тесты курса
        cursor.execute('''
            SELECT t.id, t.title, t.module_id
            FROM tests t
            JOIN modules m ON t.module_id = m.id
            WHERE m.course_id = ?
        ''', (course_id,))

        course_tests = cursor.fetchall()

        # Для каждого теста получаем результаты пользователя
        for test_row in course_tests:
            cursor.execute('''
                SELECT id, score, max_score, started_at, finished_at, duration_sec
                FROM test_results 
                WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL
                ORDER BY finished_at DESC
            ''', (user_id, test_row['id']))

            for result_row in cursor.fetchall():
                test_results.append({
                    'test_id': test_row['id'],
                    'test_title': test_row['title'],
                    'result_id': result_row['id'],
                    'score': float(result_row['score']) if result_row['score'] is not None else 0.0,
                    'max_score': float(result_row['max_score']) if result_row['max_score'] is not None else 100.0,
                    'percentage': round((float(result_row['score']) / float(result_row['max_score'])) * 100, 2) if
                    result_row['max_score'] and result_row['max_score'] > 0 else 0.0,
                    'started_at': result_row['started_at'],
                    'finished_at': result_row['finished_at'],
                    'duration_sec': result_row['duration_sec'] if result_row['duration_sec'] is not None else 0
                })

        conn.close()

    except Exception as e:
        print(f"Ошибка получения результатов тестов курса: {e}")

    # Группируем результаты тестов по модулям для статистики
    module_stats = {}
    for module in modules:
        module_tests = test_model.get_by_module(module.id)
        module_test_ids = [t.id for t in module_tests]

        module_test_results = [r for r in test_results if r['test_id'] in module_test_ids]

        if module_test_results:
            module_stats[module.id] = {
                'title': module.title,
                'total_tests': len(module_tests),
                'completed_tests': len(module_test_results),
                'average_score': sum(r['score'] for r in module_test_results) / len(
                    module_test_results) if module_test_results else 0,
                'best_score': max(r['score'] for r in module_test_results) if module_test_results else 0
            }

    return render_template('student/course_detail.html',
                           course=course.to_dict(),
                           teacher=teacher.to_dict() if teacher else {},
                           progress=progress_dict,
                           modules=module_list,
                           total_modules=total_modules,
                           completed_modules=completed_modules,
                           completion_percentage=round(completion_percentage, 2),
                           total_tests=total_tests,
                           test_results=test_results,
                           module_stats=module_stats,
                           user_name=session.get('user_name'))


@app.route('/student/tests')
@login_required
@role_required('student')
def student_tests():
    """Страница тестов студента"""
    user_id = session.get('user_id')

    # Получаем аналитику тестов
    test_analytics = test_service.get_test_analytics(user_id)

    # Получаем все результаты тестов
    all_results = test_service.get_test_results_for_student(user_id)

    # Группируем по курсам
    from database.models import Course
    course_model = Course(auth_service.db)

    tests_by_course = {}
    for result in all_results:
        course_id = result.get('course_id')
        if not course_id:
            continue

        if course_id not in tests_by_course:
            course = course_model.get_by_id(course_id)
            tests_by_course[course_id] = {
                'course_title': course.title if course else 'Неизвестный курс',
                'course_id': course_id,
                'tests': []
            }

        # Добавляем ссылку на страницу результата теста
        if 'result_id' in result:
            tests_by_course[course_id]['tests'].append(result)

    # Также получаем доступные для прохождения тесты (те, которые еще не были пройдены или есть попытки)
    from database.models import Test, Module
    test_model = Test(auth_service.db)
    module_model = Module(auth_service.db)

    # Получаем все тесты из курсов, на которые записан студент
    available_tests = []

    # Получаем курсы студента
    enrolled_courses = course_service.get_student_courses(user_id)

    for course_data in enrolled_courses:
        course_id = course_data['course']['id']

        # Получаем все модули курса
        modules = module_model.get_by_course(course_id)

        for module in modules:
            # Получаем тесты модуля
            tests = test_model.get_by_module(module.id)

            for test in tests:
                # Проверяем, был ли уже пройден этот тест
                test_already_taken = any(r['test_id'] == test.id for r in all_results)

                # Получаем информацию о тесте
                test_info = {
                    'test_id': test.id,
                    'test_title': test.title,
                    'description': getattr(test, 'description', ''),
                    'duration_minutes': getattr(test, 'time_limit', 60),
                    'max_score': getattr(test, 'max_score', 100),
                    'module_id': test.module_id,
                    'course_id': course_id,
                    'course_title': course_data['course']['title'],
                    'already_taken': test_already_taken,
                    'can_start': True  # По умолчанию разрешаем
                }

                available_tests.append(test_info)

    return render_template('student/tests.html',
                           test_analytics=test_analytics,
                           tests_by_course=tests_by_course,
                           available_tests=available_tests,
                           user_name=session.get('user_name'))


@app.route('/student/test/<test_id>/take', methods=['GET', 'POST'])
@login_required
@role_required('student')
def take_test(test_id):
    """Страница прохождения теста - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
    user_id = session.get('user_id')

    print(f"DEBUG: Function called with test_id = '{test_id}'")
    print(f"DEBUG: Request method = {request.method}")

    if request.method == 'POST':
        print(f"DEBUG: POST data: {request.form}")

        # Получаем test_result_id из формы
        test_result_id = request.form.get('test_result_id')

        if not test_result_id:
            print(f"DEBUG: ОШИБКА: test_result_id отсутствует в форме")
            flash('Ошибка: отсутствует ID результата теста', 'danger')
            return redirect(url_for('student_test_detail', test_id=test_id))

        print(f"DEBUG: Найден test_result_id: {test_result_id}")

        # Получаем тест с вопросами для понимания структуры
        test_with_questions = test_service.get_test_with_questions(test_id, include_correct_answers=False)
        if not test_with_questions:
            flash('Тест не найден', 'danger')
            return redirect(url_for('student_tests'))

        # Сохраняем ВСЕ ответы из формы
        saved_count = 0

        # Получаем все поля формы с ответами
        for key in request.form.keys():
            if key.startswith('question_'):
                # Извлекаем ID вопроса
                question_id = key.replace('question_', '')

                # Убираем возможные суффиксы для множественного выбора
                if question_id.endswith('[]'):
                    question_id = question_id.replace('[]', '')

                print(f"DEBUG: Обработка ответа для question_id={question_id}")

                # Получаем вопрос из теста
                question = None
                for q in test_with_questions.get('questions', []):
                    if q.get('id') == question_id:
                        question = q
                        break

                if not question:
                    print(f"DEBUG: Вопрос {question_id} не найден в тесте")
                    continue

                # Обрабатываем ответ в зависимости от типа вопроса
                if question.get('type') == 'single':
                    answer_id = request.form.get(key)
                    if answer_id:
                        print(f"DEBUG: Сохраняем single ответ: question_id={question_id}, answer_id={answer_id}")
                        success, message = test_service.submit_test_answer(
                            test_result_id,
                            question_id,
                            {'answer_id': answer_id}
                        )
                        if success:
                            saved_count += 1
                        else:
                            print(f"DEBUG: Ошибка сохранения ответа: {message}")

                elif question.get('type') == 'multiple':
                    answer_ids = request.form.getlist(f'question_{question_id}[]')
                    if answer_ids:
                        print(f"DEBUG: Сохраняем multiple ответы: question_id={question_id}, answer_ids={answer_ids}")
                        success, message = test_service.submit_test_answer(
                            test_result_id,
                            question_id,
                            {'answer_ids': answer_ids}
                        )
                        if success:
                            saved_count += 1
                        else:
                            print(f"DEBUG: Ошибка сохранения ответов: {message}")

                else:  # open/text question
                    text_answer = request.form.get(key)
                    if text_answer:
                        print(
                            f"DEBUG: Сохраняем текст ответа: question_id={question_id}, text_length={len(text_answer)}")
                        success, message = test_service.submit_test_answer(
                            test_result_id,
                            question_id,
                            {'text_answer': text_answer}
                        )
                        if success:
                            saved_count += 1
                        else:
                            print(f"DEBUG: Ошибка сохранения текста: {message}")

        print(f"DEBUG: Сохранено ответов: {saved_count}")

        # Завершаем тест
        success, message, result_details = test_service.finish_test(test_result_id)

        if success:
            print(f"DEBUG: Тест успешно завершен. Result ID: {test_result_id}")
            flash(message, 'success')
            # Перенаправляем на страницу результатов
            return redirect(url_for('test_result', test_id=test_id, test_result_id=test_result_id))
        else:
            print(f"DEBUG: Ошибка завершения теста: {message}")
            flash(message, 'danger')
            return redirect(url_for('student_test_detail', test_id=test_id))

    # GET запрос - отображение теста
    success, message, test_result_id = test_service.start_test(user_id, test_id)

    if not success:
        flash(message, 'danger')
        return redirect(url_for('student_test_detail', test_id=test_id))

    # Получаем тест с вопросами (БЕЗ правильных ответов)
    test_with_questions = test_service.get_test_with_questions(test_id, include_correct_answers=False)

    if not test_with_questions:
        flash('Тест не найден', 'danger')
        return redirect(url_for('student_tests'))

    # Убедимся, что test_id передается в тестовые данные
    if isinstance(test_with_questions, dict):
        test_with_questions['test_id'] = test_id

    # Получаем информацию о времени
    from database.models import TestResult
    test_result_model = TestResult(auth_service.db)
    test_result = test_result_model.get_by_id(test_result_id)

    # Рассчитываем оставшееся время
    time_limit = test_with_questions.get('time_limit')
    remaining_time = None

    if time_limit and test_result and test_result.started_at:
        started_at = datetime.fromisoformat(test_result.started_at) if isinstance(test_result.started_at,
                                                                                  str) else test_result.started_at
        elapsed_time = (datetime.now() - started_at).total_seconds()
        remaining_time = max(0, time_limit * 60 - elapsed_time)

    # Используем исправленный шаблон
    return render_template('student/take_test.html',
                           test=test_with_questions,
                           test_result_id=test_result_id,
                           time_limit=time_limit,
                           remaining_time=remaining_time,
                           test_id=test_id)


@app.route('/student/test/<test_id>/result/<test_result_id>')
@login_required
@role_required('student')
def test_result(test_id, test_result_id):
    """Страница результатов теста - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    user_id = session.get('user_id')

    print(f"DEBUG test_result: test_id={test_id}, test_result_id={test_result_id}, user_id={user_id}")

    # Проверяем, что результат теста принадлежит текущему пользователю
    from database.models import TestResult
    test_result_model = TestResult(auth_service.db)
    test_result_obj = test_result_model.get_by_id(test_result_id)

    if not test_result_obj:
        print(f"DEBUG test_result: Результат с ID {test_result_id} не найден в БД")
        flash('Результат теста не найден', 'danger')
        return redirect(url_for('student_test_detail', test_id=test_id))

    if test_result_obj.user_id != user_id:
        print(f"DEBUG test_result: Доступ запрещен")
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('student_tests'))

    # Получаем тест с вопросами И правильными ответами
    test_with_questions = test_service.get_test_with_correct_answers(test_id)

    if not test_with_questions:
        flash('Тест не найден', 'danger')
        return redirect(url_for('student_tests'))

    # Получаем ответы пользователя на этот тест
    from database.models import UserAnswer
    user_answer_model = UserAnswer(auth_service.db)
    user_answers_raw = user_answer_model.get_by_test_result(test_result_id)

    print(f"DEBUG test_result: Найдено {len(user_answers_raw)} ответов пользователя")

    # Структурируем ответы пользователя
    user_answers_dict = {}
    for answer in user_answers_raw:
        question_id = answer.question_id

        if question_id not in user_answers_dict:
            user_answers_dict[question_id] = {
                'selected_ids': [],
                'text_answer': None,
                'is_correct': False
            }

        if answer.answer_id:
            user_answers_dict[question_id]['selected_ids'].append(answer.answer_id)
            # Для multiple вопросов is_correct одинаковый для всех ответов на этот вопрос
            user_answers_dict[question_id]['is_correct'] = answer.is_correct or False
        elif answer.text_answer:
            user_answers_dict[question_id]['text_answer'] = answer.text_answer
            user_answers_dict[question_id]['is_correct'] = answer.is_correct or False

        print(
            f"DEBUG test_result: Ответ для question_id={question_id}: answer_id={answer.answer_id}, is_correct={answer.is_correct}")

    # Получаем информацию о тесте
    from database.models import Test
    test_model = Test(auth_service.db)
    test_obj = test_model.get_by_id(test_id)

    # Форматируем даты для шаблона
    if hasattr(test_result_obj, 'finished_at') and test_result_obj.finished_at:
        if isinstance(test_result_obj.finished_at, str):
            finished_at_str = test_result_obj.finished_at
        else:
            # Это объект datetime
            finished_at_str = test_result_obj.finished_at.isoformat()
    else:
        finished_at_str = ""

    # Рассчитываем процент выполнения
    score = float(test_result_obj.score) if test_result_obj.score else 0.0
    max_score = float(test_result_obj.max_score) if test_result_obj.max_score else 100.0

    if max_score > 0:
        percentage = round((score / max_score * 100), 2)
    else:
        percentage = 0

    # Считаем количество правильных ответов (только для автоматически проверяемых вопросов)
    correct_answers_count = 0
    for answer in user_answers_raw:
        if answer.is_correct and answer.answer_id is not None:
            correct_answers_count += 1

    # Считаем количество автоматически проверяемых вопросов
    autogradable_questions_count = 0
    total_questions = len(test_with_questions.get('questions', []))

    for question in test_with_questions.get('questions', []):
        if question.get('type') in ['single', 'multiple']:
            autogradable_questions_count += 1

    # Подготавливаем данные для шаблона
    test_result_data = {
        'id': test_result_obj.id,
        'user_id': test_result_obj.user_id,
        'test_id': test_result_obj.test_id,
        'score': score,
        'max_score': max_score,
        'percentage': percentage,
        'started_at': test_result_obj.started_at.isoformat() if hasattr(test_result_obj.started_at,
                                                                        'isoformat') else str(
            test_result_obj.started_at),
        'finished_at': finished_at_str,
        'duration_sec': test_result_obj.duration_sec if hasattr(test_result_obj, 'duration_sec') else 0,
        'correct_answers': correct_answers_count,
        'total_questions': total_questions,
        'total_autogradable_questions': autogradable_questions_count,
        'total_all_questions': total_questions  # Для совместимости с шаблоном
    }

    # Получаем информацию о курсе
    from database.models import Module, Course
    module_model = Module(auth_service.db)
    course_model = Course(auth_service.db)

    course = None
    if test_obj and test_obj.module_id:
        module = module_model.get_by_id(test_obj.module_id)
        if module:
            course = course_model.get_by_id(module.course_id)

    # Получаем информацию о тесте для кнопки "Пройти снова"
    test_info = {'can_start': True}

    # Передаем тестовые данные в шаблон
    test_data_for_template = {
        'id': test_id,
        'title': test_obj.title if test_obj else 'Тест',
        'description': test_obj.description if test_obj else '',
        'time_limit': test_obj.time_limit if test_obj else 60,
        'max_score': max_score,
        'questions': test_with_questions.get('questions', [])
    }

    return render_template('student/test_result.html',
                           test=test_data_for_template,
                           test_result=test_result_data,
                           user_answers=user_answers_dict,
                           course=course.to_dict() if course else None,
                           test_info=test_info,
                           user_name=session.get('user_name'))

@app.route('/api/test/submit_answer', methods=['POST'])
@login_required
@role_required('student')
def submit_test_answer():
    """API для отправки ответа на вопрос теста"""
    data = request.json
    test_result_id = data.get('test_result_id')
    question_id = data.get('question_id')
    answer_data = data.get('answer_data', {})

    if not all([test_result_id, question_id]):
        return jsonify({'success': False, 'message': 'Недостаточно данных'}), 400

    success, message = test_service.submit_test_answer(test_result_id, question_id, answer_data)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/api/test/finish', methods=['POST'])
@login_required
@role_required('student')
def api_finish_test():  # Изменяем имя функции
    """API для завершения теста"""
    data = request.json
    test_result_id = data.get('test_result_id')

    if not test_result_id:
        return jsonify({'success': False, 'message': 'Не указан ID результата теста'}), 400

    success, message, result_details = test_service.finish_test(test_result_id)

    if success:
        return jsonify({
            'success': True,
            'message': message,
            'result': result_details
        })
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/api/enroll/<course_id>', methods=['POST'])
@login_required
@role_required('student')
def enroll_course(course_id):
    """API для записи на курс"""
    user_id = session.get('user_id')

    success, message, progress = course_service.enroll_student(user_id, course_id)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/student/progress')
@login_required
@role_required('student')
def student_progress():
    """Страница прогресса студента"""
    user_id = session.get('user_id')

    # Получаем курсы студента
    courses = course_service.get_student_courses(user_id)

    # Получаем детальную статистику
    from database.models import ProgressCourse, ProgressModule
    progress_course_model = ProgressCourse(auth_service.db)
    progress_module_model = ProgressModule(auth_service.db)

    detailed_stats = []
    for course_data in courses:
        course_id = course_data['course']['id']
        progress = progress_course_model.get_by_user_and_course(user_id, course_id)

        if progress:
            # Получаем модули курса с прогрессом
            from database.models import Module
            module_model = Module(auth_service.db)
            modules = module_model.get_by_course(course_id)

            module_progress_list = []
            for module in modules:
                module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
                if module_progress:
                    module_progress_list.append({
                        'module': module.to_dict(),
                        'progress': module_progress.to_dict()
                    })

            detailed_stats.append({
                'course': course_data['course'],
                'progress': progress.to_dict(),
                'modules': module_progress_list
            })

    # Получаем аналитику тестов
    test_analytics = test_service.get_test_analytics(user_id)

    return render_template('student/progress.html',
                           detailed_stats=detailed_stats,
                           test_analytics=test_analytics)


@app.route('/student/profile')
@login_required
@role_required('student')
def student_profile():
    """Страница профиля студента"""
    user_id = session.get('user_id')

    # Получаем данные пользователя
    from database.models import User
    user_model = User(auth_service.db)
    user = user_model.get_by_id(user_id)

    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('student_dashboard'))

    # Получаем статистику
    user_stats = auth_service.get_user_statistics(user_id)
    test_analytics = test_service.get_test_analytics(user_id)

    return render_template('student/profile.html',
                           user=user,
                           user_stats=user_stats,
                           test_analytics=test_analytics)


# ==================== ПРЕПОДАВАТЕЛЬ ====================

@app.route('/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    """Панель управления преподавателя"""
    user_id = session.get('user_id')

    # Получаем курсы преподавателя
    courses = course_service.get_teacher_courses(user_id)

    # Получаем статистику
    total_students = 0
    average_completion = 0

    if courses:
        for course in courses:
            total_students += course['stats'].get('total_students', 0)
            average_completion += course['stats'].get('completion_rate', 0)

        average_completion = average_completion / len(courses) if len(courses) > 0 else 0

    return render_template('teacher/dashboard.html',
                           courses=courses,
                           total_students=total_students,
                           average_completion=round(average_completion, 2),
                           user_name=session.get('user_name'))


# ==================== АДМИНИСТРАТОР ====================

# ==================== АДМИНСКАЯ ПАНЕЛЬ ====================

@app.route('/admin/panel')
@login_required
@role_required('admin')
def admin_panel():
    """Главная панель администратора"""
    return render_template('admin/base.html',
                           user_name=session.get('user_name'),
                           user_role=session.get('user_role'))


@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    """Дашборд администратора с общей статистикой"""
    # Используем сервисы для получения статистики вместо прямого доступа к моделям

    # Инициализируем модели через auth_service для получения правильного соединения
    user_model = User(auth_service.db)
    course_model = Course(auth_service.db)
    test_model = Test(auth_service.db)
    analytics = AnalyticsService(auth_service.db)

    # Получаем статистику через сервисы
    all_users = user_model.get_all()
    total_users = len(all_users)

    # Получаем пользователей по ролям
    students = len([u for u in all_users if u.role == 'student'])
    teachers = len([u for u in all_users if u.role == 'teacher'])
    admins = len([u for u in all_users if u.role == 'admin'])

    # Получаем курсы
    all_courses = course_model.get_all(active_only=False)
    total_courses = len(all_courses)
    active_courses = len([c for c in all_courses if c.is_active])

    # Получаем последние 5 пользователей
    recent_users = all_users[-5:] if len(all_users) > 5 else all_users

    # Получаем последние 5 курсов
    recent_courses = all_courses[-5:] if len(all_courses) > 5 else all_courses

    # Получаем статистику платформы за последние 30 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    # Добавляем текущее время для шаблона
    now = datetime.now()

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           students=students,
                           teachers=teachers,
                           admins=admins,
                           total_courses=total_courses,
                           active_courses=active_courses,
                           recent_users=recent_users,
                           recent_courses=recent_courses,
                           start_date=start_date,
                           end_date=end_date,
                           now=now,
                           user_name=session.get('user_name'))

# ==================== CRUD ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ====================

@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    """Управление пользователями"""
    user_model = User(auth_service.db)

    # Получаем параметры фильтрации
    search = request.args.get('search', '').strip()
    role = request.args.get('role', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 20

    # Получаем всех пользователей
    all_users = user_model.get_all()

    # Применяем фильтры
    filtered_users = all_users
    if search:
        filtered_users = [
            u for u in filtered_users
            if search.lower() in u.email.lower() or
               search.lower() in f"{u.first_name} {u.last_name}".lower() or
               search.lower() in str(u.id).lower()
        ]

    if role:
        filtered_users = [u for u in filtered_users if u.role == role]

    # Пагинация
    total_users = len(filtered_users)
    total_pages = (total_users + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    users_page = filtered_users[start_idx:end_idx]

    return render_template('admin/users.html',
                           users=users_page,
                           total_users=total_users,
                           page=page,
                           total_pages=total_pages,
                           search=search,
                           role=role,
                           user_roles=UserRole,
                           user_name=session.get('user_name'))


@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_user():
    """Создание пользователя"""
    if request.method == 'POST':
        try:
            user_data = {
                'first_name': request.form.get('first_name'),
                'last_name': request.form.get('last_name'),
                'email': request.form.get('email'),
                'password': request.form.get('password'),
                'role': request.form.get('role', UserRole.STUDENT.value)
            }

            # Хэшируем пароль
            import hashlib
            password_hash = hashlib.sha256(user_data['password'].encode()).hexdigest()
            user_data['password_hash'] = password_hash

            user_model = User(auth_service.db)
            new_user = user_model.create(user_data)

            flash(f'Пользователь {new_user.email} создан успешно!', 'success')
            return redirect(url_for('admin_users'))

        except Exception as e:
            flash(f'Ошибка при создании пользователя: {str(e)}', 'danger')

    return render_template('admin/user_form.html',
                           user=None,
                           user_roles=UserRole,
                           user_name=session.get('user_name'))


@app.route('/admin/users/<user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    """Редактирование пользователя"""
    user_model = User(auth_service.db)
    user = user_model.get_by_id(user_id)

    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        try:
            update_data = {
                'first_name': request.form.get('first_name'),
                'last_name': request.form.get('last_name'),
                'email': request.form.get('email'),
                'role': request.form.get('role')
            }

            # Если указан новый пароль
            new_password = request.form.get('password')
            if new_password:
                import hashlib
                update_data['password_hash'] = hashlib.sha256(new_password.encode()).hexdigest()

            updated_user = user_model.update(user_id, update_data)

            flash(f'Пользователь {updated_user.email} обновлен успешно!', 'success')
            return redirect(url_for('admin_users'))

        except Exception as e:
            flash(f'Ошибка при обновлении пользователя: {str(e)}', 'danger')

    return render_template('admin/user_form.html',
                           user=user,
                           user_roles=UserRole,
                           user_name=session.get('user_name'))


@app.route('/admin/users/<user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    """Удаление пользователя"""
    user_model = User(auth_service.db)
    user = user_model.get_by_id(user_id)

    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('admin_users'))

    try:
        success = user_model.delete(user_id)
        if success:
            flash(f'Пользователь {user.email} удален успешно!', 'success')
        else:
            flash('Ошибка при удалении пользователя', 'danger')
    except Exception as e:
        flash(f'Ошибка при удалении пользователя: {str(e)}', 'danger')

    return redirect(url_for('admin_users'))


# ==================== CRUD ДЛЯ КУРСОВ ====================

@app.route('/admin/courses')
@login_required
@role_required('admin')
def admin_courses():
    """Управление курсами"""
    # Получаем параметры фильтрации
    search = request.args.get('search', '').strip()
    author_id = request.args.get('author_id', '').strip()
    active_only = request.args.get('active_only', 'true') == 'true'
    page = int(request.args.get('page', 1))
    per_page = 15

    # Получаем все курсы через сервис
    all_courses_data = course_service.get_all_courses(include_inactive=not active_only)

    # Применяем фильтры
    filtered_courses = all_courses_data
    if search:
        filtered_courses = [
            c for c in filtered_courses
            if search.lower() in c['title'].lower() or
               (c.get('short_description') and search.lower() in c['short_description'].lower())
        ]

    if author_id:
        filtered_courses = [c for c in filtered_courses if c['author_id'] == author_id]

    # Пагинация
    total_courses = len(filtered_courses)
    total_pages = (total_courses + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    courses_page = filtered_courses[start_idx:end_idx]

    # Получаем авторов для фильтра
    from database.models import User, UserRole
    user_model = User(auth_service.db)
    teachers = user_model.get_by_role(UserRole.TEACHER.value)

    return render_template('admin/courses.html',
                           courses=courses_page,
                           total_courses=total_courses,
                           page=page,
                           total_pages=total_pages,
                           search=search,
                           author_id=author_id,
                           active_only=active_only,
                           teachers=teachers,
                           user_name=session.get('user_name'))


# ==================== АДМИНСКИЕ МАРШРУТЫ ДЛЯ УПРАВЛЕНИЯ КУРСАМИ ====================

@app.route('/admin/courses/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_course():
    """Создание нового курса с валидацией"""
    if request.method == 'POST':
        try:
            # Получаем и валидируем данные
            title = request.form.get('title')
            short_description = request.form.get('short_description')
            description = request.form.get('description')
            author_id = request.form.get('author_id')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            is_active = request.form.get('is_active') == 'true'

            # Валидация
            from datetime import datetime
            errors = []

            if not title:
                errors.append('Название курса обязательно')
            if not author_id:
                errors.append('Необходимо выбрать автора (преподавателя)')

            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    if start_date.date() < datetime.now().date():
                        errors.append('Дата начала не может быть в прошлом')
                except ValueError:
                    errors.append('Неверный формат даты начала')
            else:
                # Устанавливаем дату начала как сегодня по умолчанию
                start_date = datetime.now()

            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    if start_date_str and end_date <= start_date:
                        errors.append('Дата окончания должна быть позже даты начала')
                except ValueError:
                    errors.append('Неверный формат даты окончания')
            else:
                end_date = None

            if errors:
                for error in errors:
                    flash(error, 'danger')
                # Получаем преподавателей для повторного отображения формы
                from database.models import User, UserRole
                user_model = User(auth_service.db)
                teachers = user_model.get_by_role(UserRole.TEACHER.value)
                return render_template('admin/course_create.html',
                                       teachers=teachers,
                                       user_name=session.get('user_name'),
                                       form_data=request.form)  # Передаем данные формы

            course_data = {
                'title': title,
                'short_description': short_description,
                'description': description,
                'author_id': author_id,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat() if end_date else None,
                'is_active': is_active
            }

            success, message, course = course_service.create_course(course_data, session.get('user_id'))

            if success:
                flash(f'Курс "{course.title}" создан успешно!', 'success')
                return redirect(url_for('admin_courses'))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании курса: {str(e)}', 'danger')

    # Получаем всех преподавателей для выбора автора
    from database.models import User, UserRole
    user_model = User(auth_service.db)
    teachers = user_model.get_by_role(UserRole.TEACHER.value)

    return render_template('admin/course_create.html',
                           teachers=teachers,
                           user_name=session.get('user_name'))

@app.route('/admin/courses/<course_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_course(course_id):
    """Редактирование курса с валидацией"""
    # Валидация дат
    from datetime import datetime
    course = course_service.course_model.get_by_id(course_id)

    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('admin_courses'))

    if request.method == 'POST':
        try:
            # Получаем данные из формы
            title = request.form.get('title')
            short_description = request.form.get('short_description')
            description = request.form.get('description')
            author_id = request.form.get('author_id')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            is_active = request.form.get('is_active') == 'true'


            errors = []

            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    # Проверяем, что дата начала не в прошлом
                    if start_date.date() < datetime.now().date():
                        errors.append('Дата начала не может быть в прошлом')
                except ValueError:
                    errors.append('Неверный формат даты начала')
            else:
                start_date = course.start_date  # Сохраняем существующую дату

            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    if start_date_str and end_date <= start_date:
                        errors.append('Дата окончания должна быть позже даты начала')
                except ValueError:
                    errors.append('Неверный формат даты окончания')
            else:
                end_date = course.end_date  # Сохраняем существующую дату

            if errors:
                for error in errors:
                    flash(error, 'danger')
                return redirect(url_for('admin_edit_course', course_id=course_id))

            update_data = {
                'title': title,
                'short_description': short_description,
                'description': description,
                'author_id': author_id,
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'is_active': is_active
            }

            success, message, updated_course = course_service.update_course(
                course_id, update_data, session.get('user_id')
            )

            if success:
                flash(f'Курс "{updated_course.title}" обновлен успешно!', 'success')
                return redirect(url_for('admin_view_course', course_id=course_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при обновлении курса: {str(e)}', 'danger')

    # Получаем всех преподавателей для выбора автора
    from database.models import User, UserRole
    user_model = User(auth_service.db)
    teachers = user_model.get_by_role(UserRole.TEACHER.value)

    # Форматируем даты для шаблона
    if course.start_date:
        if isinstance(course.start_date, datetime):
            course.start_date_formatted = course.start_date.strftime('%Y-%m-%d')
        else:
            course.start_date_formatted = course.start_date[:10] if course.start_date else ''
    else:
        course.start_date_formatted = ''

    if course.end_date:
        if isinstance(course.end_date, datetime):
            course.end_date_formatted = course.end_date.strftime('%Y-%m-%d')
        else:
            course.end_date_formatted = course.end_date[:10] if course.end_date else ''
    else:
        course.end_date_formatted = ''

    return render_template('admin/course_edit.html',
                           course=course,
                           teachers=teachers,
                           user_name=session.get('user_name'))


@app.route('/admin/courses/<course_id>/view')
@login_required
@role_required('admin')
def admin_view_course(course_id):
    """Просмотр курса с модулями"""
    # Получаем курс с модулями через сервис
    course_with_modules = course_service.get_course_with_modules(course_id)

    if not course_with_modules or 'course' not in course_with_modules:
        flash('Курс не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем статистику курса
    from database.models import Course
    course_model = Course(auth_service.db)
    stats = {}
    try:
        stats = course_model.get_completion_stats(course_id)
    except Exception as e:
        print(f"Ошибка получения статистики: {e}")

    return render_template('admin/course_view.html',
                           course_data=course_with_modules,
                           stats=stats,
                           user_name=session.get('user_name'))


@app.route('/admin/courses/<course_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_course(course_id):
    """Удаление курса"""
    success, message = course_service.delete_course(course_id, session.get('user_id'))

    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')

    return redirect(url_for('admin_courses'))


# ==================== МОДУЛИ ====================
@app.route('/admin/modules/<module_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_module(module_id):
    """Редактирование модуля"""
    module = course_service.module_model.get_by_id(module_id)

    if not module:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('admin_courses'))

    if request.method == 'POST':
        try:
            update_data = {
                'title': request.form.get('title'),
                'short_description': request.form.get('short_description'),
                'module_order': int(request.form.get('module_order', 1)),
                'estimated_duration': request.form.get('estimated_duration')
            }

            success, message, updated_module = course_service.update_module(
                module_id, update_data, session.get('user_id')
            )

            if success:
                flash(f'Модуль "{updated_module.title}" обновлен успешно!', 'success')
                return redirect(url_for('admin_view_course', course_id=module.course_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при обновлении модуля: {str(e)}', 'danger')

    # Получаем информацию о курсе
    from database.models import Course
    course_model = Course(auth_service.db)
    course = course_model.get_by_id(module.course_id)

    return render_template('admin/module_edit.html',
                           module=module,  # Передаем как module
                           course=course,
                           user_name=session.get('user_name'))


@app.route('/admin/modules/<module_id>/view')
@login_required
@role_required('admin')
def admin_view_module(module_id):
    """Просмотр модуля с материалами и тестами"""
    from database.models import Module, Course, LearningMaterial, Test

    # Получаем модуль
    module_model = Module(auth_service.db)
    module = module_model.get_by_id(module_id)

    if not module:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем курс
    course_model = Course(auth_service.db)
    course = course_model.get_by_id(module.course_id) if module.course_id else None

    # Получаем материалы модуля
    material_model = LearningMaterial(auth_service.db)
    materials = material_model.get_by_module(module_id)

    # Получаем тесты модуля
    test_model = Test(auth_service.db)
    tests = test_model.get_by_module(module_id)

    # Преобразуем объекты в простые структуры
    module_data = {
        'id': module.id,
        'course_id': module.course_id,
        'title': module.title,
        'description': getattr(module, 'description', ''),
        'short_description': getattr(module, 'short_description', ''),
        'module_order': getattr(module, 'module_order', 1),
        'estimated_duration': getattr(module, 'estimated_duration', ''),
        'created_at': getattr(module, 'created_at', '')
    }

    course_data = {
        'id': course.id if course else '',
        'title': course.title if course else 'Неизвестный курс'
    }

    return render_template('admin/module_view.html',
                           module=module_data,
                           course=course_data,
                           materials=materials,
                           tests=tests,
                           user_name=session.get('user_name'))


@app.route('/admin/modules/<module_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_module(module_id):
    """Удаление модуля"""
    module = course_service.module_model.get_by_id(module_id)

    if not module:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('admin_courses'))

    try:
        # Используем прямой SQL для удаления
        db_path = app.config['DATABASE_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Удаляем модуль (каскадное удаление должно быть настроено в БД)
        cursor.execute("DELETE FROM modules WHERE id = ?", (module_id,))
        conn.commit()
        conn.close()

        flash(f'Модуль "{module.title}" удален успешно!', 'success')
    except Exception as e:
        flash(f'Ошибка при удалении модуля: {str(e)}', 'danger')

    return redirect(url_for('admin_view_course', course_id=module.course_id))


# ==================== МАТЕРИАЛЫ ====================

@app.route('/admin/modules/<module_id>/materials/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_material(module_id):
    """Создание учебного материала с возможностью выбора модуля или создания нового"""
    from database.models import Course, Module

    module = course_service.module_model.get_by_id(module_id)
    if not module:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем информацию о курсе
    course_model = Course(auth_service.db)
    course = course_model.get_by_id(module.course_id)

    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем все модули этого курса для выпадающего списка
    module_model = Module(auth_service.db)
    all_modules = module_model.get_by_course(course.id)

    if request.method == 'POST':
        try:
            # Проверяем, создается ли новый модуль
            create_new_module = request.form.get('create_new_module') == 'true'

            if create_new_module:
                # Создаем новый модуль
                new_module_data = {
                    'course_id': course.id,
                    'title': request.form.get('new_module_title'),
                    'short_description': request.form.get('new_module_description'),
                    'module_order': int(request.form.get('new_module_order', 1))
                }

                success, message, new_module = course_service.create_module(
                    new_module_data, session.get('user_id')
                )

                if not success:
                    flash(message, 'danger')
                    return redirect(url_for('admin_create_material', module_id=module_id))

                module_id = new_module.id
                module = new_module
                flash(f'Новый модуль "{new_module.title}" создан успешно!', 'success')

            else:
                # Используем выбранный модуль
                selected_module_id = request.form.get('selected_module_id')
                if selected_module_id and selected_module_id != module_id:
                    module_id = selected_module_id
                    module = course_service.module_model.get_by_id(module_id)

            # Создаем материал
            material_data = {
                'module_id': module_id,
                'title': request.form.get('title'),
                'content': request.form.get('content'),
                'content_type': request.form.get('content_type', 'text'),
                'material_order': int(request.form.get('material_order', 1))
            }

            success, message, material = course_service.create_material(
                material_data, session.get('user_id')
            )

            if success:
                flash(f'Материал "{material.title}" создан успешно!', 'success')
                return redirect(url_for('admin_view_module', module_id=module_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании материала: {str(e)}', 'danger')

    # Получаем текущие материалы для определения порядка
    existing_materials = course_service.material_model.get_by_module(module_id)

    return render_template('admin/material_create.html',
                           module=module,
                           course=course,
                           all_modules=all_modules,
                           next_order=len(existing_materials) + 1,
                           content_types=['text', 'video', 'pdf', 'link', 'quiz'],
                           user_name=session.get('user_name'))


@app.route('/admin/materials/<material_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_material(material_id):
    """Редактирование учебного материала"""
    material = course_service.material_model.get_by_id(material_id)

    if not material:
        flash('Материал не найден', 'danger')
        return redirect(url_for('admin_courses'))

    if request.method == 'POST':
        try:
            update_data = {
                'title': request.form.get('title'),
                'content': request.form.get('content'),
                'content_type': request.form.get('content_type'),
                'material_order': int(request.form.get('material_order', 1))
            }

            success, message, updated_material = course_service.update_material(
                material_id, update_data, session.get('user_id')
            )

            if success:
                flash(f'Материал "{updated_material.title}" обновлен успешно!', 'success')
                return redirect(url_for('admin_view_module', module_id=material.module_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при обновлении материала: {str(e)}', 'danger')

    module = course_service.module_model.get_by_id(material.module_id)

    return render_template('admin/material_edit.html',
                           material=material,
                           module=module,
                           content_types=['text', 'video', 'pdf', 'link', 'quiz'],
                           user_name=session.get('user_name'))


@app.route('/admin/materials/<material_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_material(material_id):
    """Удаление учебного материала"""
    material = course_service.material_model.get_by_id(material_id)

    if not material:
        flash('Материал не найден', 'danger')
        return redirect(url_for('admin_courses'))

    success, message = course_service.delete_material(material_id, session.get('user_id'))

    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')

    return redirect(url_for('admin_view_module', module_id=material.module_id))


# ==================== ТЕСТЫ ====================
@app.route('/admin/tests/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_test_standalone():
    """Создание теста (без указания модуля)"""
    from database.models import Course, Module

    # Получаем все курсы для выпадающего списка
    course_model = Course(auth_service.db)
    courses = course_model.get_all(active_only=True)

    # Получаем все модули каждого курса
    module_model = Module(auth_service.db)
    course_modules = {}
    for course in courses:
        modules_list = module_model.get_by_course(course.id)
        course_modules[course.id] = modules_list

    if request.method == 'POST':
        try:
            # Получаем данные из формы
            title = request.form.get('title')
            description = request.form.get('description')
            time_limit = int(request.form.get('time_limit', 60))
            max_score = int(request.form.get('max_score', 100))

            # Определяем к чему привязывать тест
            test_data = {
                'title': title,
                'description': description,
                'time_limit': time_limit,
                'max_score': max_score
            }

            # Проверяем, выбрал ли пользователь модуль
            selected_module_id = request.form.get('selected_module_id')
            if selected_module_id and selected_module_id != 'none':
                # Привязываем к выбранному модулю
                test_data['module_id'] = selected_module_id
            else:
                flash('Выберите модуль для теста', 'danger')
                return render_template('admin/test_create_standalone.html',
                                       courses=courses,
                                       course_modules=course_modules,
                                       user_name=session.get('user_name'))

            success, message, test = course_service.create_test(
                test_data, session.get('user_id')
            )

            if success:
                flash(f'Тест "{test.title}" создан успешно!', 'success')
                return redirect(url_for('admin_view_test', test_id=test.id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании теста: {str(e)}', 'danger')

    return render_template('admin/test_create_standalone.html',
                           courses=courses,
                           course_modules=course_modules,
                           user_name=session.get('user_name'))

@app.route('/admin/modules/<module_id>/tests/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_test(module_id):
    """Создание теста"""
    from database.models import Module, Course

    module = course_service.module_model.get_by_id(module_id)

    if not module:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем курс для отображения информации
    course_model = Course(auth_service.db)
    course = course_model.get_by_id(module.course_id)

    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем все курсы для выпадающего списка
    courses = course_model.get_all(active_only=True)

    # Получаем все модули каждого курса для выпадающего списка
    module_model = Module(auth_service.db)
    course_modules = {}
    for c in courses:
        modules_list = module_model.get_by_course(c.id)
        course_modules[c.id] = modules_list

    if request.method == 'POST':
        try:
            # Получаем данные из формы
            title = request.form.get('title')
            description = request.form.get('description')
            time_limit = int(request.form.get('time_limit', 60))
            max_score = int(request.form.get('max_score', 100))

            # Определяем к чему привязывать тест
            test_data = {
                'title': title,
                'description': description,
                'time_limit': time_limit,
                'max_score': max_score
            }

            # Проверяем, выбрал ли пользователь другой модуль
            selected_module_id = request.form.get('selected_module_id')
            if selected_module_id and selected_module_id != 'none':
                # Привязываем к выбранному модулю
                test_data['module_id'] = selected_module_id
            else:
                # Привязываем к текущему модулю (по умолчанию)
                test_data['module_id'] = module_id

            success, message, test = course_service.create_test(
                test_data, session.get('user_id')
            )

            if success:
                flash(f'Тест "{test.title}" создан успешно!', 'success')
                return redirect(url_for('admin_view_test', test_id=test.id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании теста: {str(e)}', 'danger')

    return render_template('admin/test_create.html',
                           module=module,
                           course=course,
                           courses=courses,
                           course_modules=course_modules,
                           user_name=session.get('user_name'))


@app.route('/admin/tests/<test_id>/view')
@login_required
@role_required('admin')
def admin_view_test(test_id):
    """Просмотр теста с вопросами"""
    test_with_questions = course_service.get_test_with_questions(test_id, include_correct_answers=True)

    if not test_with_questions or 'test' not in test_with_questions:
        flash('Тест не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Получаем информацию о курсе и модуле
    from database.models import Module, Course
    module_model = Module(auth_service.db)
    course_model = Course(auth_service.db)

    test = test_with_questions['test']
    course_title = ''
    module_title = ''

    if hasattr(test, 'module_id') and test.module_id:
        module = module_model.get_by_id(test.module_id)
        if module:
            module_title = module.title if hasattr(module, 'title') else ''
            if hasattr(module, 'course_id') and module.course_id:
                course = course_model.get_by_id(module.course_id)
                if course:
                    course_title = course.title if hasattr(course, 'title') else ''

    # Добавляем информацию о курсе и модуле в данные
    test_with_questions['course_title'] = course_title
    test_with_questions['module_title'] = module_title

    return render_template('admin/test_view.html',
                           test_data=test_with_questions,
                           user_name=session.get('user_name'))

@app.route('/admin/tests/<test_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_test(test_id):
    """Редактирование теста"""
    test = course_service.test_model.get_by_id(test_id)

    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('admin_courses'))

    # Определяем модуль
    module = None
    if test.module_id:
        module = course_service.module_model.get_by_id(test.module_id)

    if request.method == 'POST':
        try:
            update_data = {
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'time_limit': int(request.form.get('time_limit', 60)),
                'max_score': int(request.form.get('max_score', 100))
            }

            success, message, updated_test = course_service.update_test(
                test_id, update_data, session.get('user_id')
            )

            if success:
                flash(f'Тест "{updated_test.title}" обновлен успешно!', 'success')
                return redirect(url_for('admin_view_test', test_id=test_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при обновлении теста: {str(e)}', 'danger')

    return render_template('admin/test_edit.html',
                           test=test,
                           module=module,
                           user_name=session.get('user_name'))


@app.route('/admin/tests/<test_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_test(test_id):
    """Удаление теста"""
    test = course_service.test_model.get_by_id(test_id)

    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('admin_courses'))

    success, message = course_service.delete_test(test_id, session.get('user_id'))

    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')

    # Определяем куда перенаправлять
    if test.module_id:
        return redirect(url_for('admin_view_module', module_id=test.module_id))
    elif test.course_id:
        return redirect(url_for('admin_view_course', course_id=test.course_id))
    else:
        return redirect(url_for('admin_courses'))


# ==================== ВОПРОСЫ И ОТВЕТЫ ====================
@app.route('/admin/tests/<test_id>/questions/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_question(test_id):
    """Создание вопроса в тесте - ОКОНЧАТЕЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    from database.models import Test, Module, Course, Question, Answer
    test_model = Test(auth_service.db)
    test = test_model.get_by_id(test_id)

    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('admin_tests'))

    # Получаем информацию о курсе и модуле
    module_model = Module(auth_service.db)
    course_model = Course(auth_service.db)

    module_info = None
    course_info = None

    if hasattr(test, 'module_id') and test.module_id:
        module_info = module_model.get_by_id(test.module_id)
        if module_info and hasattr(module_info, 'course_id') and module_info.course_id:
            course_info = course_model.get_by_id(module_info.course_id)

    if request.method == 'POST':
        try:
            # Получаем данные вопроса из формы
            question_text = request.form.get('text', '').strip()
            question_type = request.form.get('type', 'single')
            points = int(request.form.get('points', 1))
            question_order = int(request.form.get('question_order', 1))

            if not question_text:
                flash('Текст вопроса обязателен', 'danger')
                return redirect(url_for('admin_create_question', test_id=test_id))

            # Создаем вопрос
            question_data = {
                'test_id': test_id,
                'text': question_text,
                'type': question_type,
                'points': points,
                'question_order': question_order
            }

            # Создаем вопрос через модель
            question_model = Question(auth_service.db)
            question = question_model.create(question_data)

            if not question:
                flash('Ошибка при создании вопроса', 'danger')
                return redirect(url_for('admin_create_question', test_id=test_id))

            # Для вопросов с выбором ответа создаем варианты
            if question_type in ['single', 'multiple']:
                # Получаем все тексты ответов
                option_texts = request.form.getlist('option_text[]')

                # Получаем индексы правильных ответов
                correct_options_raw = request.form.getlist('correct_option[]')
                correct_options = [int(idx) for idx in correct_options_raw if idx.isdigit()]

                print(f"DEBUG: Всего вариантов ответа: {len(option_texts)}")
                print(f"DEBUG: Индексы правильных ответов: {correct_options}")

                if len(option_texts) < 2:
                    flash('Должно быть минимум 2 варианта ответа', 'danger')
                    # Удаляем созданный вопрос, если вариантов недостаточно
                    question_model.delete(question.id)
                    return redirect(url_for('admin_create_question', test_id=test_id))

                # Создаем каждый вариант ответа
                answer_model = Answer(auth_service.db)
                for i, option_text in enumerate(option_texts):
                    if option_text.strip():  # Пропускаем пустые варианты
                        # Определяем, является ли этот вариант правильным
                        is_correct = i in correct_options

                        answer_data = {
                            'question_id': question.id,
                            'text': option_text.strip(),
                            'is_correct': is_correct,
                            'answer_order': i + 1
                        }

                        created_answer = answer_model.create(answer_data)
                        print(f"DEBUG: Создан ответ {i + 1}: '{option_text[:50]}...', правильный: {is_correct}")

                # Проверяем, что есть хотя бы один правильный ответ для single
                if question_type == 'single' and len(correct_options) == 0:
                    flash('Для вопроса с одиночным выбором должен быть выбран один правильный ответ', 'warning')
                elif question_type == 'single' and len(correct_options) > 1:
                    flash('Для вопроса с одиночным выбором должен быть выбран только один правильный ответ', 'warning')
                elif question_type == 'multiple' and len(correct_options) == 0:
                    flash('Для вопроса с множественным выбором должен быть выбран хотя бы один правильный ответ',
                          'warning')

            flash('Вопрос успешно создан!', 'success')
            return redirect(url_for('admin_questions', test_id=test_id))

        except Exception as e:
            flash(f'Ошибка при создании вопроса: {str(e)}', 'danger')
            print(f"ERROR in admin_create_question: {str(e)}")
            import traceback
            traceback.print_exc()

    # GET запрос - отображение формы

    # Получаем текущие вопросы для определения порядка
    question_model = Question(auth_service.db)
    existing_questions = question_model.get_by_test(test_id)

    # Подготавливаем данные для шаблона
    selected_test = {
        'id': test.id,
        'title': test.title,
        'description': getattr(test, 'description', ''),
        'time_limit': getattr(test, 'time_limit', 60),
        'max_score': getattr(test, 'max_score', 100),
        'course_title': course_info.title if course_info else 'Неизвестный курс'
    }

    return render_template('admin/question_form.html',
                           question=None,
                           selected_test=selected_test,
                           test_id=test_id,
                           tests=[],
                           next_order=len(existing_questions) + 1,
                           question_types=['single', 'multiple', 'text'],
                           user_name=session.get('user_name'))
# ==================== CRUD ДЛЯ ТЕСТОВ ====================

@app.route('/admin/tests')
@login_required
@role_required('admin')
def admin_tests():
    """Управление тестами"""
    test_model = Test(auth_service.db)
    course_model = Course(auth_service.db)
    module_model = Module(auth_service.db)

    # Получаем параметры фильтрации
    search = request.args.get('search', '').strip()
    course_id = request.args.get('course_id', '').strip()
    module_id = request.args.get('module_id', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 15

    # Получаем все тесты
    tests = []
    all_courses = course_model.get_all(active_only=True)
    for course in all_courses:
        course_tests = test_model.get_by_course(course.id)
        tests.extend(course_tests)

    # Применяем фильтры
    filtered_tests = tests
    if search:
        filtered_tests = [
            t for t in filtered_tests
            if search.lower() in t.title.lower() or
               (t.description and search.lower() in t.description.lower())
        ]

    if course_id:
        filtered_tests = [t for t in filtered_tests if t.course_id == course_id]

    if module_id:
        filtered_tests = [t for t in filtered_tests if t.module_id == module_id]

    # Пагинация
    total_tests = len(filtered_tests)
    total_pages = (total_tests + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    tests_page = filtered_tests[start_idx:end_idx]

    # Получаем курсы и модули для фильтра
    courses = course_model.get_all(active_only=True)
    modules = []
    if course_id:
        modules = module_model.get_by_course(course_id)

    return render_template('admin/tests.html',
                           tests=tests_page,
                           total_tests=total_tests,
                           page=page,
                           total_pages=total_pages,
                           search=search,
                           course_id=course_id,
                           module_id=module_id,
                           courses=courses,
                           modules=modules,
                           user_name=session.get('user_name'))


# ==================== CRUD ДЛЯ МОДУЛЕЙ ====================
# ==================== МОДУЛИ ====================

@app.route('/admin/modules/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_module():
    """Создание модуля (без указания курса - выбираем из списка)"""
    if request.method == 'POST':
        try:
            module_data = {
                'course_id': request.form.get('course_id'),
                'title': request.form.get('title'),
                'short_description': request.form.get('short_description'),
                'module_order': int(request.form.get('module_order', 1)),
                'estimated_duration': request.form.get('estimated_duration')
            }

            if not module_data['course_id']:
                flash('Необходимо выбрать курс', 'danger')
                return redirect(url_for('admin_create_module'))

            success, message, module = course_service.create_module(
                module_data, session.get('user_id')
            )

            if success:
                flash(f'Модуль "{module.title}" создан успешно!', 'success')
                return redirect(url_for('admin_view_course', course_id=module_data['course_id']))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании модуля: {str(e)}', 'danger')

    # Получаем все активные курсы для выбора
    from database.models import Course
    course_model = Course(auth_service.db)
    courses = course_model.get_all(active_only=True)

    return render_template('admin/module_create_standalone.html',
                           courses=courses,
                           user_name=session.get('user_name'))


@app.route('/admin/courses/<course_id>/modules/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_create_module_for_course(course_id):
    """Создание модуля для конкретного курса"""
    course = course_service.course_model.get_by_id(course_id)

    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('admin_courses'))

    if request.method == 'POST':
        try:
            module_data = {
                'course_id': course_id,
                'title': request.form.get('title'),
                'short_description': request.form.get('short_description'),
                'module_order': int(request.form.get('module_order', 1)),
                'estimated_duration': request.form.get('estimated_duration')
            }

            success, message, module = course_service.create_module(
                module_data, session.get('user_id')
            )

            if success:
                flash(f'Модуль "{module.title}" создан успешно!', 'success')
                return redirect(url_for('admin_view_course', course_id=course_id))
            else:
                flash(message, 'danger')

        except Exception as e:
            flash(f'Ошибка при создании модуля: {str(e)}', 'danger')

    # Получаем текущие модули для определения порядка
    existing_modules = course_service.module_model.get_by_course(course_id)

    return render_template('admin/module_create.html',
                           course=course,
                           next_order=len(existing_modules) + 1,
                           user_name=session.get('user_name'))


@app.route('/admin/modules')
@login_required
@role_required('admin')
def admin_modules():
    """Управление модулями"""
    import sqlite3

    # Получаем параметры фильтрации
    search = request.args.get('search', '').strip()
    course_id = request.args.get('course_id', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 15

    # Прямой SQL запрос для получения модулей
    db_path = app.config['DATABASE_PATH']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Базовый запрос
    query = '''
        SELECT m.*, c.title as course_title, c.is_active as course_active
        FROM modules m
        JOIN courses c ON m.course_id = c.id
        WHERE 1=1
    '''
    params = []

    if course_id:
        query += ' AND m.course_id = ?'
        params.append(course_id)

    if search:
        query += ' AND (m.title LIKE ? OR c.title LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])

    query += ' ORDER BY c.title, m.module_order'

    # Выполняем запрос
    cursor = conn.cursor()
    cursor.execute(query, params)
    all_rows = cursor.fetchall()

    # Пагинация
    total_modules = len(all_rows)
    total_pages = (total_modules + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    modules_page = all_rows[start_idx:end_idx]

    # Получаем информацию о курсах
    cursor.execute('SELECT id, title FROM courses WHERE is_active = 1 ORDER BY title')
    courses_rows = cursor.fetchall()
    courses = [{'id': row['id'], 'title': row['title']} for row in courses_rows]

    conn.close()

    # Форматируем данные для шаблона
    modules = []
    for row in modules_page:
        # Получаем количество материалов
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM learning_materials WHERE module_id = ?', (row['id'],))
        materials_count = cursor.fetchone()[0] or 0

        # Получаем количество тестов
        cursor.execute('SELECT COUNT(*) as count FROM tests WHERE module_id = ?', (row['id'],))
        tests_count = cursor.fetchone()[0] or 0

        conn.close()

        modules.append({
            'id': row['id'],
            'course_id': row['course_id'],
            'course_title': row['course_title'],
            'course_active': row['course_active'],
            'title': row['title'],
            'short_description': row['short_description'],
            'module_order': row['module_order'],
            'estimated_duration': row['estimated_duration'],
            'created_at': row['created_at'],
            'materials_count': materials_count,
            'tests_count': tests_count
        })

    return render_template('admin/modules.html',
                           modules=modules,
                           total_modules=total_modules,
                           page=page,
                           total_pages=total_pages,
                           per_page=per_page,  # Добавляем эту строку
                           search=search,
                           course_id=course_id,
                           courses=courses,
                           user_name=session.get('user_name'))

# ==================== CRUD ДЛЯ ВОПРОСОВ И ОТВЕТОВ ====================

@app.route('/admin/questions/<test_id>')
@login_required
@role_required('admin')
def admin_questions(test_id):
    """Управление вопросами теста"""
    test_model = Test(auth_service.db)
    question_model = Question(auth_service.db)
    answer_model = Answer(auth_service.db)

    # Получаем тест
    test = test_model.get_by_id(test_id)
    if not test:
        flash('Тест не найден', 'danger')
        return redirect(url_for('admin_tests'))

    # Получаем параметры пагинации
    page = int(request.args.get('page', 1))
    per_page = 10

    # Получаем вопросы для этого теста
    questions = question_model.get_by_test(test_id)

    # Пагинация
    total_questions = len(questions)
    total_pages = (total_questions + per_page - 1) // per_page

    # Применяем пагинацию
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    questions_page = questions[start_idx:end_idx]

    # Получаем ответы для каждого вопроса
    questions_with_answers = []
    for question in questions_page:
        answers = answer_model.get_by_question(question.id)
        questions_with_answers.append({
            'question': question,
            'answers': answers
        })

    # Получаем все тесты для фильтра (если нужно)
    tests = []
    try:
        from database.models import Course, Module
        course_model = Course(auth_service.db)
        module_model = Module(auth_service.db)

        all_tests = test_model.get_all()
        for t in all_tests:
            tests.append({
                'id': t.id,
                'title': t.title,
                'course_title': 'Неизвестный курс',
                'module_title': 'Неизвестный модуль'
            })

            if t.module_id:
                module = module_model.get_by_id(t.module_id)
                if module and module.course_id:
                    course = course_model.get_by_id(module.course_id)
                    if course:
                        tests[-1]['course_title'] = course.title
                        tests[-1]['module_title'] = module.title if hasattr(module, 'title') else 'Модуль'
    except Exception as e:
        print(f"Ошибка получения информации о тестах: {e}")

    return render_template('admin/questions.html',
                           questions_with_answers=questions_with_answers,
                           selected_test={
                               'id': test.id,
                               'title': test.title,
                               'max_score': getattr(test, 'max_score', 100),
                               'time_limit': getattr(test, 'time_limit', 60)
                           },
                           tests=tests,
                           test_id=test_id,
                           search=request.args.get('search', ''),
                           question_type=request.args.get('question_type', ''),
                           page=page,
                           total_pages=total_pages,
                           total_questions=total_questions,
                           per_page=per_page,
                           user_name=session.get('user_name'))

# ==================== АНАЛИТИКА ====================

# Добавьте эти маршруты в app.py

# Обновите маршрут /admin/analytics в app.py

@app.route('/admin/analytics', methods=['GET'])
@login_required
@role_required('admin')
def admin_analytics():
    """Аналитика платформы - 3 отчета"""
    try:
        from database.models import Course, Test, User, AnalyticsService, UserRole, ProgressCourse, TestResult, \
            ProgressModule, Module
        from datetime import datetime, timedelta
        import sqlite3
        import traceback

        db = auth_service.db
        course_model = Course(db)
        test_model = Test(db)
        user_model = User(db)
        progress_course_model = ProgressCourse(db)
        progress_module_model = ProgressModule(db)
        module_model = Module(db)

        # Получаем параметры из запроса
        analytic_type = request.args.get('analytic_type', '')
        validation_error = None

        # Получаем списки для выпадающих меню
        courses = course_model.get_all(active_only=True)
        tests = test_model.get_all()
        students = user_model.get_by_role(UserRole.STUDENT.value)

        # Обрабатываем каждый тип аналитики
        top_students = None
        completion_data = None
        learning_dynamics = None

        # Для передачи в шаблон
        selected_course = None
        target_type = ''
        target_title = ''
        selected_student = None
        activity_labels = []
        activity_data = []
        module_progress_data = []
        test_results_labels = []
        test_results_data = []

        print(f"DEBUG: analytic_type = {analytic_type}")
        print(f"DEBUG: Все параметры запроса: {dict(request.args)}")

        if analytic_type == 'top_students':
            # Топ лучших студентов по курсу
            course_id = request.args.get('course_id', '')
            start_date_str = request.args.get('start_date', '')
            end_date_str = request.args.get('end_date', '')
            top_limit_str = request.args.get('top_limit', '10')

            try:
                top_limit = int(top_limit_str) if top_limit_str else 10
                if top_limit <= 0:
                    top_limit = 10
            except:
                top_limit = 10

            print(
                f"DEBUG: top_students - course_id={course_id}, start={start_date_str}, end={end_date_str}, limit={top_limit}")

            # Валидация
            if not course_id:
                validation_error = "Необходимо выбрать курс для анализа"
            elif start_date_str and end_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    if start_date > end_date:
                        validation_error = "Дата 'по' должна быть позже даты 'с'"
                except ValueError:
                    validation_error = "Неверный формат даты"

            if not validation_error and course_id:
                selected_course = course_model.get_by_id(course_id)
                print(f"DEBUG: selected_course = {selected_course}")
                if selected_course:
                    try:
                        db_path = app.config['DATABASE_PATH']
                        conn = sqlite3.connect(db_path)
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()

                        # Основной запрос для получения прогресса студентов
                        query = '''
                            SELECT 
                                pc.*,
                                u.id as student_id,
                                u.first_name,
                                u.last_name,
                                u.email
                            FROM progress_courses pc
                            JOIN users u ON pc.user_id = u.id
                            WHERE pc.course_id = ? 
                              AND u.role = 'student'
                        '''
                        params = [course_id]

                        if start_date_str and end_date_str:
                            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                            start_date_sql = start_date.strftime('%Y-%m-%d 00:00:00')
                            end_date_sql = end_date.strftime('%Y-%m-%d 23:59:59')
                            query += " AND pc.finished_at BETWEEN ? AND ?"
                            params.extend([start_date_sql, end_date_sql])

                        query += " ORDER BY pc.final_score DESC LIMIT ?"
                        params.append(top_limit)

                        print(f"DEBUG: Query: {query}")
                        print(f"DEBUG: Params: {params}")

                        cursor.execute(query, params)
                        progress_rows = cursor.fetchall()
                        print(f"DEBUG: Found {len(progress_rows)} progress rows")

                        top_students = []
                        for rank, row in enumerate(progress_rows, 1):
                            student_id = row['student_id']

                            # Получаем результаты тестов для этого студента
                            cursor.execute('''
                                SELECT 
                                    tr.score,
                                    tr.max_score,
                                    tr.finished_at
                                FROM test_results tr
                                JOIN tests t ON tr.test_id = t.id
                                JOIN modules m ON t.module_id = m.id
                                WHERE tr.user_id = ? 
                                  AND m.course_id = ?
                                  AND tr.finished_at IS NOT NULL
                            ''', (student_id, course_id))

                            test_rows = cursor.fetchall()
                            test_results = []
                            total_percentage = 0

                            for tr_row in test_rows:
                                score = float(tr_row['score']) if tr_row['score'] else 0.0
                                max_score = float(tr_row['max_score']) if tr_row['max_score'] else 100.0
                                percentage = (score / max_score * 100) if max_score > 0 else 0
                                total_percentage += percentage

                                test_results.append({
                                    'score': score,
                                    'max_score': max_score,
                                    'percentage': percentage,
                                    'finished_at': tr_row['finished_at']
                                })

                            avg_test_score = (total_percentage / len(test_rows)) if test_rows else 0

                            student_data = {
                                "rank": rank,
                                "student_id": student_id,
                                "student_name": f"{row['first_name']} {row['last_name']}",
                                "email": row['email'],
                                "final_score": float(row['final_score']) if row['final_score'] else 0.0,
                                "progress_percent": float(row['progress_percent']) if row['progress_percent'] else 0.0,
                                "finished_at": row['finished_at'],
                                "test_results": test_results,
                                "average_test_score": round(avg_test_score, 2)
                            }

                            top_students.append(student_data)

                        conn.close()

                    except Exception as e:
                        app.logger.error(f"Ошибка получения топ студентов: {e}")
                        traceback.print_exc()
                        validation_error = f"Ошибка получения данных: {str(e)}"

        elif analytic_type == 'test_completion':
            # Результаты теста/курса
            target_id = request.args.get('target_id', '')
            start_date_str = request.args.get('completion_start_date', '')
            end_date_str = request.args.get('completion_end_date', '')

            print(f"DEBUG: test_completion - target_id={target_id}, start={start_date_str}, end={end_date_str}")

            # Валидация
            if not target_id:
                validation_error = "Необходимо выбрать тест или курс для анализа"
            elif start_date_str and end_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    if start_date > end_date:
                        validation_error = "Дата 'по' должна быть позже даты 'с'"
                except ValueError:
                    validation_error = "Неверный формат даты"
            elif start_date_str or end_date_str:
                validation_error = "Необходимо указать обе даты или оставить обе пустыми"

            if not validation_error and target_id:
                if target_id.startswith('test_'):
                    # Это тест
                    test_id = target_id[5:]
                    print(f"DEBUG: test_id = {test_id}")
                    test = test_model.get_by_id(test_id)
                    print(f"DEBUG: test = {test}")
                    if test:
                        target_type = 'test'
                        target_title = test.title

                        try:
                            db_path = app.config['DATABASE_PATH']
                            conn = sqlite3.connect(db_path)
                            conn.row_factory = sqlite3.Row
                            cursor = conn.cursor()

                            # Устанавливаем даты по умолчанию
                            start_date_sql = '1900-01-01 00:00:00'
                            end_date_sql = '2100-12-31 23:59:59'

                            if start_date_str and end_date_str:
                                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                                start_date_sql = start_date.strftime('%Y-%m-%d 00:00:00')
                                end_date_sql = end_date.strftime('%Y-%m-%d 23:59:59')

                            # Общая статистика
                            cursor.execute('''
                                SELECT 
                                    COUNT(*) as total_attempts,
                                    COUNT(DISTINCT user_id) as unique_students,
                                    AVG(score) as avg_score
                                FROM test_results 
                                WHERE test_id = ? 
                                    AND finished_at IS NOT NULL
                                    AND finished_at BETWEEN ? AND ?
                            ''', (test_id, start_date_sql, end_date_sql))

                            stats_row = cursor.fetchone()
                            print(f"DEBUG: stats_row = {stats_row}")

                            total_attempts = stats_row['total_attempts'] or 0 if stats_row else 0
                            unique_students = stats_row['unique_students'] or 0 if stats_row else 0
                            avg_score = float(stats_row['avg_score']) if stats_row and stats_row['avg_score'] else 0.0
                            max_score = getattr(test, 'max_score', 100)
                            print(
                                f"DEBUG: total_attempts = {total_attempts}, avg_score = {avg_score}, max_score = {max_score}")

                            # Процент сдачи (если балл >= 60%)
                            pass_threshold = max_score * 0.6
                            cursor.execute('''
                                SELECT COUNT(*) as passed
                                FROM test_results 
                                WHERE test_id = ? 
                                    AND finished_at IS NOT NULL
                                    AND finished_at BETWEEN ? AND ?
                                    AND score >= ?
                            ''', (test_id, start_date_sql, end_date_sql, pass_threshold))

                            passed_row = cursor.fetchone()
                            passed_attempts = passed_row['passed'] if passed_row else 0
                            pass_rate = (passed_attempts / total_attempts * 100) if total_attempts > 0 else 0

                            # Распределение баллов
                            score_distribution = {
                                "0-20%": 0,
                                "21-40%": 0,
                                "41-60%": 0,
                                "61-80%": 0,
                                "81-100%": 0
                            }

                            if total_attempts > 0:
                                cursor.execute('''
                                    SELECT score, max_score
                                    FROM test_results 
                                    WHERE test_id = ? 
                                        AND finished_at IS NOT NULL
                                        AND finished_at BETWEEN ? AND ?
                                ''', (test_id, start_date_sql, end_date_sql))

                                for result_row in cursor.fetchall():
                                    score = float(result_row['score']) if result_row['score'] else 0.0
                                    max_score_val = float(result_row['max_score']) if result_row['max_score'] else 100.0
                                    percentage = (score / max_score_val * 100) if max_score_val > 0 else 0

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

                            # Детальные результаты по студентам
                            cursor.execute('''
                                SELECT 
                                    u.first_name,
                                    u.last_name,
                                    u.email,
                                    MAX(tr.score) as best_score,
                                    COUNT(tr.id) as attempts_count,
                                    MAX(tr.finished_at) as last_attempt,
                                    AVG(tr.duration_sec) as avg_duration
                                FROM test_results tr
                                JOIN users u ON tr.user_id = u.id
                                WHERE tr.test_id = ? 
                                    AND tr.finished_at IS NOT NULL
                                    AND tr.finished_at BETWEEN ? AND ?
                                GROUP BY tr.user_id
                                ORDER BY best_score DESC
                            ''', (test_id, start_date_sql, end_date_sql))

                            detailed_results = []
                            for row in cursor.fetchall():
                                best_score = float(row['best_score']) if row['best_score'] else 0.0
                                percentage = (best_score / max_score * 100) if max_score > 0 else 0

                                detailed_results.append({
                                    'student_name': f"{row['first_name']} {row['last_name']}",
                                    'email': row['email'],
                                    'best_score': best_score,
                                    'best_percentage': percentage,
                                    'attempts_count': row['attempts_count'],
                                    'last_attempt': row['last_attempt'],
                                    'avg_duration': row['avg_duration']
                                })

                            completion_data = {
                                "test_id": test_id,
                                "test_title": test.title,
                                "total_attempts": total_attempts,
                                "unique_students": unique_students,
                                "average_score": round(avg_score, 2),
                                "average_percentage": round((avg_score / max_score * 100) if max_score > 0 else 0, 2),
                                "pass_rate": round(pass_rate, 2),
                                "score_distribution": score_distribution,
                                "detailed_results": detailed_results
                            }

                            # Данные для графика распределения
                            test_results_labels = list(score_distribution.keys())
                            test_results_data = list(score_distribution.values())

                            conn.close()

                        except Exception as e:
                            app.logger.error(f"Ошибка получения статистики теста: {e}")
                            traceback.print_exc()
                            validation_error = f"Ошибка получения данных: {str(e)}"
                else:
                    # Это курс
                    course_id = target_id
                    course = course_model.get_by_id(course_id)
                    if course:
                        target_type = 'course'
                        target_title = course.title
                        # TODO: Добавить логику для аналитики курса

        elif analytic_type == 'learning_dynamics':
            # Динамика обучения студента
            student_id = request.args.get('student_id', '')
            start_date_str = request.args.get('dynamics_start_date', '')
            end_date_str = request.args.get('dynamics_end_date', '')
            analysis_type = request.args.get('analysis_type', 'all')

            print(f"DEBUG: learning_dynamics - student_id={student_id}, start={start_date_str}, end={end_date_str}")

            # Валидация
            if not student_id:
                validation_error = "Необходимо выбрать студента для анализа"
            elif start_date_str and end_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                    if start_date > end_date:
                        validation_error = "Дата 'по' должна быть позже даты 'с'"
                except ValueError:
                    validation_error = "Неверный формат даты"
            elif start_date_str or end_date_str:
                validation_error = "Необходимо указать обе даты или оставить обе пустыми"

            if not validation_error and student_id:
                selected_student = user_model.get_by_id(student_id)
                print(f"DEBUG: selected_student = {selected_student}")
                if selected_student:
                    try:
                        # Устанавливаем даты по умолчанию
                        if start_date_str and end_date_str:
                            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                        else:
                            # По умолчанию последние 30 дней
                            end_date = datetime.now()
                            start_date = end_date - timedelta(days=30)

                        start_date_sql = start_date.strftime('%Y-%m-%d 00:00:00')
                        end_date_sql = end_date.strftime('%Y-%m-%d 23:59:59')

                        db_path = app.config['DATABASE_PATH']
                        conn = sqlite3.connect(db_path)
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()

                        # Получаем курсы студента
                        cursor.execute('''
                            SELECT 
                                pc.*,
                                c.title as course_title,
                                c.description as course_description
                            FROM progress_courses pc
                            JOIN courses c ON pc.course_id = c.id
                            WHERE pc.user_id = ?
                            ORDER BY pc.enrolled_at DESC
                        ''', (student_id,))

                        course_rows = cursor.fetchall()
                        print(f"DEBUG: Found {len(course_rows)} courses for student")

                        learning_dynamics = {
                            "student": {
                                "id": selected_student.id,
                                "name": f"{selected_student.first_name} {selected_student.last_name}",
                                "email": selected_student.email
                            },
                            "total_courses": len(course_rows),
                            "active_courses": 0,
                            "completed_courses": 0,
                            "average_score": 0,
                            "courses": [],
                            "period": {
                                "start": start_date.strftime('%Y-%m-%d'),
                                "end": end_date.strftime('%Y-%m-%d')
                            }
                        }

                        total_score = 0
                        completed_count = 0

                        # Собираем данные для графика активности
                        activity_by_date = {}

                        for progress in course_rows:
                            course_id = progress['course_id']
                            status = progress['status']

                            # Подсчет статистики по статусам
                            if status == 'active':
                                learning_dynamics["active_courses"] += 1
                            elif status == 'completed':
                                learning_dynamics["completed_courses"] += 1
                                if progress['final_score']:
                                    total_score += float(progress['final_score'])
                                    completed_count += 1

                            # Получаем прогресс по модулям
                            cursor.execute('''
                                SELECT 
                                    pm.*,
                                    m.title as module_title,
                                    m.module_order as module_order
                                FROM progress_modules pm
                                JOIN modules m ON pm.module_id = m.id
                                WHERE pm.enrollment_id = ?
                                ORDER BY m.module_order
                            ''', (progress['id'],))

                            module_rows = cursor.fetchall()
                            module_progress_list = []

                            for mp in module_rows:
                                module_progress_list.append({
                                    "module_id": mp['module_id'],
                                    "module_title": mp['module_title'],
                                    "status": mp['status'],
                                    "progress_percent": float(mp['progress_percent']) if mp[
                                        'progress_percent'] else 0.0,
                                    "started_at": mp['started_at'],
                                    "finished_at": mp['finished_at']
                                })

                            # Получаем результаты тестов для этого курса
                            cursor.execute('''
                                SELECT 
                                    tr.*,
                                    t.title as test_title,
                                    t.max_score as test_max_score
                                FROM test_results tr
                                JOIN tests t ON tr.test_id = t.id
                                JOIN modules m ON t.module_id = m.id
                                WHERE tr.user_id = ? 
                                    AND m.course_id = ?
                                    AND tr.finished_at IS NOT NULL
                                    AND tr.finished_at BETWEEN ? AND ?
                                ORDER BY tr.finished_at DESC
                            ''', (student_id, course_id, start_date_sql, end_date_sql))

                            test_rows = cursor.fetchall()
                            test_results_list = []

                            for tr in test_rows:
                                score = float(tr['score']) if tr['score'] else 0.0
                                max_score = float(tr['max_score']) if tr['max_score'] else 100.0
                                percentage = (score / max_score * 100) if max_score > 0 else 0

                                test_results_list.append({
                                    "test_id": tr['test_id'],
                                    "test_title": tr['test_title'],
                                    "score": score,
                                    "max_score": max_score,
                                    "percentage": percentage,
                                    "finished_at": tr['finished_at']
                                })

                                # Собираем данные для графика активности
                                if tr['finished_at']:
                                    date_str = tr['finished_at'][:10]  # YYYY-MM-DD
                                    activity_by_date[date_str] = activity_by_date.get(date_str, 0) + 1

                            course_data = {
                                "course_id": course_id,
                                "course_title": progress['course_title'],
                                "status": status,
                                "progress_percent": float(progress['progress_percent']) if progress[
                                    'progress_percent'] else 0.0,
                                "final_score": float(progress['final_score']) if progress['final_score'] else None,
                                "enrolled_at": progress['enrolled_at'],
                                "finished_at": progress['finished_at'],
                                "modules": module_progress_list,
                                "test_results": test_results_list
                            }

                            learning_dynamics["courses"].append(course_data)

                        # Рассчитываем средний балл
                        if completed_count > 0:
                            learning_dynamics["average_score"] = round(total_score / completed_count, 2)

                        # Формируем данные для графика активности
                        current_date = start_date
                        while current_date <= end_date:
                            date_str = current_date.strftime('%Y-%m-%d')
                            activity_labels.append(current_date.strftime('%d.%m'))
                            activity_data.append(activity_by_date.get(date_str, 0))
                            current_date += timedelta(days=1)

                        # Данные для графика прогресса по курсам
                        for course in learning_dynamics["courses"]:
                            module_progress_data.append({
                                "course": course["course_title"],
                                "progress": course["progress_percent"]
                            })

                        conn.close()
                        print(f"DEBUG: learning_dynamics prepared successfully")

                    except Exception as e:
                        app.logger.error(f"Ошибка получения динамики обучения: {e}")
                        traceback.print_exc()
                        validation_error = f"Ошибка получения данных: {str(e)}"

        print(f"DEBUG: validation_error = {validation_error}")

        return render_template('admin/analytics.html',
                               analytic_type=analytic_type,
                               courses=courses,
                               tests=tests,
                               students=students,
                               top_students=top_students,
                               selected_course=selected_course,
                               selected_course_id=request.args.get('course_id', ''),
                               start_date=request.args.get('start_date', ''),
                               end_date=request.args.get('end_date', ''),
                               top_limit=request.args.get('top_limit', '10'),

                               completion_data=completion_data,
                               target_id=request.args.get('target_id', ''),
                               target_type=target_type,
                               target_title=target_title,
                               completion_start_date=request.args.get('completion_start_date', ''),
                               completion_end_date=request.args.get('completion_end_date', ''),

                               learning_dynamics=learning_dynamics,
                               selected_student=selected_student,
                               selected_student_id=request.args.get('student_id', ''),
                               dynamics_start_date=request.args.get('dynamics_start_date', ''),
                               dynamics_end_date=request.args.get('dynamics_end_date', ''),
                               analysis_type=request.args.get('analysis_type', 'all'),

                               # Данные для графиков
                               activity_labels=activity_labels,
                               activity_data=activity_data,
                               module_progress_data=module_progress_data,
                               test_results_labels=test_results_labels,
                               test_results_data=test_results_data,

                               validation_error=validation_error,
                               now=datetime.now(),
                               user_name=session.get('user_name'))

    except Exception as e:
        app.logger.error(f"Ошибка в функции admin_analytics: {e}")
        traceback.print_exc()
        return render_template('admin/analytics.html',
                               error=f"Внутренняя ошибка сервера: {str(e)}",
                               analytic_type='',
                               courses=[],
                               tests=[],
                               students=[],
                               validation_error="Произошла ошибка при обработке запроса")


@app.route('/admin/create_test_analytics_data', methods=['GET'])
@login_required
@role_required('admin')
def create_test_analytics_data():
    """Создание тестовых данных для аналитики"""
    try:
        # Просто редирект на страницу аналитики с тестовым студентом
        # Ищем любого студента
        from database.models import User, UserRole
        db = auth_service.db
        user_model = User(db)
        students = user_model.get_by_role(UserRole.STUDENT.value)

        if students and len(students) > 0:
            student_id = students[0].id
            return redirect(f'/admin/analytics?analytic_type=learning_dynamics&student_id={student_id}')
        else:
            return redirect('/admin/analytics?analytic_type=learning_dynamics&student_id=USR001')
    except Exception as e:
        return f"Ошибка: {str(e)}"

# ==================== API ДЛЯ АДМИНКИ ====================

@app.route('/api/admin/get_modules')
@login_required
@role_required('admin')
def api_get_modules():
    """API для получения модулей курса"""
    course_id = request.args.get('course_id')
    if not course_id:
        return jsonify({'success': False, 'message': 'Не указан ID курса'})

    module_model = Module(auth_service.db)
    modules = module_model.get_by_course(course_id)

    modules_list = []
    for module in modules:
        modules_list.append({
            'id': module.id,
            'title': module.title,
            'order': module.module_order
        })

    return jsonify({
        'success': True,
        'modules': modules_list
    })


@app.route('/api/admin/get_course_stats/<course_id>')
@login_required
@role_required('admin')
def api_get_course_stats(course_id):
    """API для получения статистики курса"""
    analytics_service = AnalyticsService(auth_service.db)

    try:
        completion_stats = analytics_service.get_course_completion_rate(course_id)
        return jsonify({'success': True, 'stats': completion_stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/export_data')
@login_required
@role_required('admin')
def api_export_data():
    """API для экспорта данных"""
    import csv
    from io import StringIO
    from datetime import datetime

    export_type = request.args.get('type', 'users')

    output = StringIO()
    writer = csv.writer(output)

    if export_type == 'users':
        user_model = User(auth_service.db)
        users = user_model.get_all()

        writer.writerow(['ID', 'Email', 'Имя', 'Фамилия', 'Роль', 'Дата регистрации'])
        for user in users:
            writer.writerow([
                user.id,
                user.email,
                user.first_name,
                user.last_name,
                user.role,
                user.created_at.isoformat() if user.created_at else ''
            ])

    elif export_type == 'courses':
        course_model = Course(auth_service.db)
        courses = course_model.get_all(active_only=False)

        writer.writerow(['ID', 'Название', 'Описание', 'Автор ID', 'Дата начала', 'Дата окончания', 'Активен'])
        for course in courses:
            writer.writerow([
                course.id,
                course.title,
                course.short_description or '',
                course.author_id,
                course.start_date.isoformat() if course.start_date else '',
                course.end_date.isoformat() if course.end_date else '',
                'Да' if course.is_active else 'Нет'
            ])

    output.seek(0)

    filename = f'export_{export_type}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    return app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={filename}'}
    )


# ==================== УПРАВЛЕНИЕ ПРОГРЕССОМ ====================

@app.route('/admin/progress')
@login_required
@role_required('admin')
def admin_progress():
    """Управление прогрессом студентов"""
    progress_model = ProgressCourse(auth_service.db)
    course_model = Course(auth_service.db)
    user_model = User(auth_service.db)

    # Получаем параметры фильтрации
    student_name = request.args.get('student_name', '').strip()
    course_id = request.args.get('course_id', '').strip()
    status = request.args.get('status', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 15

    # Получаем все курсы для фильтра
    courses = course_model.get_all(active_only=True)

    # Получаем весь прогресс с фильтрацией
    all_progress = []
    if course_id:
        all_progress = progress_model.get_by_course(course_id)
    else:
        # Получаем прогресс по всем курсам
        for course in courses:
            course_progress = progress_model.get_by_course(course.id)
            all_progress.extend(course_progress)

    # Применяем фильтр по статусу
    if status:
        all_progress = [p for p in all_progress if p.status == status]

    # Фильтрация по имени студента
    if student_name:
        filtered_progress = []
        for progress in all_progress:
            # Получаем информацию о студенте
            user = user_model.get_by_id(progress.user_id)
            if user:
                full_name = f"{user.first_name} {user.last_name}".lower()
                if student_name.lower() in full_name:
                    filtered_progress.append(progress)
        all_progress = filtered_progress

    # Рассчитываем статистику
    total_students = len(set(p.user_id for p in all_progress))
    active_students = len(set(p.user_id for p in all_progress if p.status == 'active'))
    completed_courses = len([p for p in all_progress if p.status == 'completed'])

    # Рассчитываем средний прогресс
    avg_progress = 0
    if all_progress:
        # Получаем информацию о модулях для каждого прогресса
        from database.models import Module, ProgressModule
        module_model = Module(auth_service.db)
        progress_module_model = ProgressModule(auth_service.db)

        total_progress_sum = 0
        for progress in all_progress:
            # Получаем модули курса
            modules = module_model.get_by_course(progress.course_id)
            total_modules = len(modules)

            if total_modules > 0:
                # Получаем завершенные модули
                completed_modules = 0
                for module in modules:
                    module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
                    if module_progress and module_progress.status == 'completed':
                        completed_modules += 1

                # Рассчитываем процент завершения для этого курса
                course_progress_percent = (completed_modules / total_modules) * 100
                total_progress_sum += course_progress_percent

        avg_progress = total_progress_sum / len(all_progress) if all_progress else 0

    # Пагинация
    total_progress = len(all_progress)
    total_pages = (total_progress + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    progress_page = all_progress[start_idx:end_idx]

    # Подготавливаем данные для шаблона
    progresses = []
    for progress in progress_page:
        user = user_model.get_by_id(progress.user_id)
        course = course_model.get_by_id(progress.course_id)

        # Получаем информацию о модулях для расчета прогресса
        from database.models import Module, ProgressModule
        module_model = Module(auth_service.db)
        progress_module_model = ProgressModule(auth_service.db)

        modules = module_model.get_by_course(progress.course_id)
        total_modules = len(modules)
        completed_modules = 0

        for module in modules:
            module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
            if module_progress and module_progress.status == 'completed':
                completed_modules += 1

        progress_percent = (completed_modules / total_modules * 100) if total_modules > 0 else 0

        # Получаем последнюю активность и результаты тестов
        from database.models import TestResult
        test_result_model = TestResult(auth_service.db)

        last_activity_str = None
        last_activity = None
        final_grade = None
        test_results = None

        # Получаем результаты тестов для этого курса
        if course:
            # Ищем результаты тестов для этого курса
            conn = sqlite3.connect(app.config['DATABASE_PATH'])
            cursor = conn.cursor()

            cursor.execute('''
                SELECT tr.score, tr.finished_at
                FROM test_results tr
                JOIN tests t ON tr.test_id = t.id
                JOIN modules m ON t.module_id = m.id
                WHERE tr.user_id = ? AND m.course_id = ? AND tr.finished_at IS NOT NULL
                ORDER BY tr.finished_at DESC
            ''', (progress.user_id, progress.course_id))

            test_rows = cursor.fetchall()
            if test_rows:
                last_activity_str = test_rows[0][1]  # Последняя дата завершения теста как строка

                # Пытаемся преобразовать в datetime
                try:
                    if last_activity_str:
                        if 'T' in last_activity_str:
                            # ISO формат: 2025-12-18T08:13:32.879177
                            last_activity = datetime.fromisoformat(last_activity_str.replace('Z', '+00:00'))
                        else:
                            # SQLite формат: 2025-12-18 08:13:32.879177
                            try:
                                last_activity = datetime.strptime(last_activity_str, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError:
                                last_activity = datetime.strptime(last_activity_str, '%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    print(f"Ошибка преобразования даты {last_activity_str}: {e}")
                    last_activity = None

                # Рассчитываем среднюю оценку
                scores = [float(row[0]) for row in test_rows if row[0]]
                if scores:
                    final_grade = sum(scores) / len(scores)
                    test_results = {
                        'passed': len([s for s in scores if s >= 50]),
                        'total': len(scores)
                    }

            conn.close()

        progresses.append({
            'id': progress.id,
            'student_id': progress.user_id,
            'student_name': f"{user.first_name} {user.last_name}" if user else "Неизвестный студент",
            'student_email': user.email if user else "",
            'course_id': progress.course_id,
            'course_title': course.title if course else "Неизвестный курс",
            'progress_percent': progress_percent,
            'completed_modules': completed_modules,
            'total_modules': total_modules,
            'last_activity': last_activity,  # datetime объект или None
            'last_activity_str': last_activity_str,  # строка
            'final_grade': final_grade,
            'test_results': test_results,
            'status': progress.status
        })

    return render_template('admin/progress.html',
                           progresses=progresses,
                           courses=courses,
                           student_name=student_name,
                           course_id=course_id,
                           status=status,
                           total_students=total_students,
                           active_students=active_students,
                           completed_courses=completed_courses,
                           avg_progress=avg_progress,
                           page=page,
                           total_pages=total_pages,
                           user_name=session.get('user_name'))


# ==================== API ====================

@app.route('/api/user/profile', methods=['GET', 'POST'])
@login_required
def user_profile_api():
    """API для работы с профилем пользователя"""
    user_id = session.get('user_id')

    if request.method == 'GET':
        # Получаем данные профиля
        user = auth_service.get_user_by_id(user_id)
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'role': user.role,
                    'created_at': user.created_at.isoformat() if user.created_at else None
                }
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'}), 404

    elif request.method == 'POST':
        # Обновляем профиль
        data = request.json
        update_data = {}

        if 'first_name' in data:
            update_data['first_name'] = data['first_name'].strip()

        if 'last_name' in data:
            update_data['last_name'] = data['last_name'].strip()

        if 'password' in data and data['password']:
            update_data['password'] = data['password'].strip()

        if update_data:
            success, message, updated_user = auth_service.update_user_profile(user_id, update_data)

            if success:
                # Обновляем данные в сессии
                session['user_name'] = f"{updated_user.first_name} {updated_user.last_name}"

                return jsonify({
                    'success': True,
                    'message': message,
                    'user': {
                        'id': updated_user.id,
                        'first_name': updated_user.first_name,
                        'last_name': updated_user.last_name,
                        'email': updated_user.email
                    }
                })
            else:
                return jsonify({'success': False, 'message': message}), 400

        return jsonify({'success': False, 'message': 'Нет данных для обновления'}), 400


@app.route('/api/courses/search')
def search_courses_api():
    """API для поиска курсов"""
    query = request.args.get('q', '').strip()
    filters = {}

    # Применяем фильтры
    author_id = request.args.get('author_id', '').strip()
    if author_id:
        filters['author_id'] = author_id

    courses = course_service.search_courses(query, filters)

    return jsonify({
        'success': True,
        'courses': courses,
        'count': len(courses)
    })


# ==================== ОБРАБОТЧИКИ ====================

@app.route('/_sdk/<path:filename>')
def sdk_files(filename):
    """Обработка запросов к SDK файлам"""
    return '', 204


@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


@app.template_filter('format_date')
def format_date_filter(date):
    if isinstance(date, datetime):
        return date.strftime('%Y-%m-%d')
    elif isinstance(date, str):
        try:
            # Пытаемся распарсить строку
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return date
    return date


@app.template_filter('format_datetime')
def format_datetime_filter(date):
    if isinstance(date, datetime):
        return date.strftime('%Y-%m-%d %H:%M')
    elif isinstance(date, str):
        try:
            dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return date
    return date


@app.route('/student/learn/<course_id>/module/<module_id>')
@login_required
@role_required('student')
def learn_module(course_id, module_id):
    """Страница изучения модуля"""
    user_id = session.get('user_id')

    # Получаем активный material_id из параметров запроса
    material_id = request.args.get('material_id')

    # Получаем информацию о курсе
    from database.models import Course
    course_model = Course(auth_service.db)
    course = course_model.get_by_id(course_id)

    if not course:
        flash('Курс не найден', 'danger')
        return redirect(url_for('student_courses'))

    # Получаем модуль с материалами
    from business_logic.learning import LearningService
    learning_service = LearningService(app.config['DATABASE_PATH'])

    module_with_materials = learning_service.get_module_with_materials(module_id)

    if not module_with_materials:
        flash('Модуль не найден', 'danger')
        return redirect(url_for('student_course_detail', course_id=course_id))

    # Определяем активный материал
    active_material = None
    if module_with_materials.get('materials'):
        materials = module_with_materials['materials']

        if material_id:
            # Ищем материал по ID
            active_material = next((m for m in materials if m.get('id') == material_id), None)

        if not active_material and materials:
            # Берем первый материал
            active_material = sorted(materials, key=lambda x: x.get('material_order', 0))[0]

    # Начинаем изучение модуля
    success, message, module_progress = learning_service.start_module_learning(user_id, module_id)

    if not success:
        flash(message, 'warning')

    # Получаем прогресс по материалам
    from database.models import MaterialProgress
    material_progress_model = MaterialProgress(auth_service.db)

    # Получаем информацию о завершенных материалах
    completed_materials = material_progress_model.get_completed_materials(user_id, module_id)

    # Помечаем материалы как завершенные в данных для шаблона
    if module_with_materials.get('materials'):
        for material in module_with_materials['materials']:
            material['completed'] = material['id'] in completed_materials

    # Получаем прогресс по активному материалу
    material_progress = None
    if active_material:
        material_progress = material_progress_model.get_by_user_and_material(user_id, active_material['id'])

    # Получаем следующий модуль
    next_module = learning_service.get_next_module(user_id, course_id, module_id)

    # Получаем тесты модуля
    from database.models import Test
    test_model = Test(auth_service.db)
    tests = test_model.get_by_module(module_id)

    return render_template('student/learn_module.html',
                           course=course.to_dict(),
                           module_data=module_with_materials,
                           active_material=active_material,
                           material_progress=material_progress.to_dict() if material_progress else None,
                           module_progress=module_progress,
                           next_module=next_module,
                           tests=tests,
                           user_id=user_id)


@app.route('/student/continue_learning/<course_id>')
@login_required
@role_required('student')
def continue_learning(course_id):
    """Продолжить обучение с того места, где остановились"""
    user_id = session.get('user_id')

    # Получаем следующий модуль для изучения
    from business_logic.learning import LearningService
    learning_service = LearningService(app.config['DATABASE_PATH'])

    next_module_data = learning_service.get_next_module(user_id, course_id)

    if not next_module_data:
        # Если все модули завершены, перенаправляем на первый модуль для повторения
        from database.models import Module
        module_model = Module(auth_service.db)
        modules = module_model.get_by_course(course_id)

        if modules:
            # Перенаправляем на первый модуль курса
            module_id = modules[0].id
            flash('Вы завершили все модули курса! Можете повторить материалы или пройти тесты.', 'success')
            return redirect(url_for('learn_module', course_id=course_id, module_id=module_id))
        else:
            flash('В курсе нет модулей', 'warning')
            return redirect(url_for('student_course_detail', course_id=course_id))

    module_id = next_module_data['module']['id']

    # Перенаправляем на изучение модуля
    return redirect(url_for('learn_module', course_id=course_id, module_id=module_id))


@app.route('/api/learning/mark_completed', methods=['POST'])
@login_required
@role_required('student')
def mark_material_completed_api():
    """API для отметки материала как изученного"""
    data = request.json
    material_id = data.get('material_id')
    user_id = session.get('user_id')

    if not material_id:
        return jsonify({'success': False, 'message': 'Не указан ID материала'}), 400

    from business_logic.learning import LearningService
    learning_service = LearningService(app.config['DATABASE_PATH'])

    success, message = learning_service.mark_material_completed(user_id, material_id)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.context_processor
def utility_processor():
    """Добавляет функции в контекст шаблонов"""

    def get_test_attempts(user_id, test_id):
        """Получить количество использованных попыток теста"""
        from database.models import TestResult
        test_result_model = TestResult(auth_service.db)
        results = test_result_model.get_by_user_and_test(user_id, test_id)
        return len(results) if results else 0

    def get_completed_modules(user_id, course_id):
        """Получить список завершенных модулей курса"""
        from database.models import ProgressCourse, ProgressModule, Module
        progress_course_model = ProgressCourse(auth_service.db)
        progress_module_model = ProgressModule(auth_service.db)
        module_model = Module(auth_service.db)

        # Получаем запись о прогрессе курса
        progress_course = progress_course_model.get_by_user_and_course(user_id, course_id)
        if not progress_course:
            return []

        # Получаем все модули курса
        modules = module_model.get_by_course(course_id)
        completed_modules = []

        for module in modules:
            progress = progress_module_model.get_by_enrollment_and_module(progress_course.id, module.id)
            if progress and progress.status == 'completed':
                completed_modules.append(module.id)

        return completed_modules

    return dict(
        get_test_attempts=get_test_attempts,
        get_completed_modules=get_completed_modules
    )


@app.route('/api/module/mark_completed', methods=['POST'])
@login_required
@role_required('student')
def mark_module_completed_api():
    """API для отметки модуля как завершенного"""
    data = request.json
    module_id = data.get('module_id')
    course_id = data.get('course_id')
    user_id = session.get('user_id')

    if not module_id or not course_id:
        return jsonify({'success': False, 'message': 'Не указаны данные модуля или курса'}), 400

    from business_logic.learning import LearningService
    learning_service = LearningService(app.config['DATABASE_PATH'])

    success, message = learning_service.complete_module(user_id, module_id, course_id)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route('/test_debug/<test_id>')
@login_required
def test_debug(test_id):
    """Отладочная страница для проверки результатов теста"""
    user_id = session.get('user_id')

    # Проверяем данные напрямую из БД
    from database.models import TestResult
    test_result_model = TestResult(auth_service.db)

    print(f"ПРЯМОЙ ЗАПРОС К БД: user_id={user_id}, test_id={test_id}")

    results = test_result_model.get_by_user_and_test(user_id, test_id)

    html = f"""
    <html>
    <body>
        <h1>Отладка теста {test_id}</h1>
        <p>User ID: {user_id}</p>
        <p>Найдено записей в TestResult: {len(results)}</p>
        <table border="1">
            <tr>
                <th>ID</th>
                <th>Test ID</th>
                <th>User ID</th>
                <th>Score</th>
                <th>Started At</th>
                <th>Finished At</th>
                <th>Duration</th>
            </tr>
    """

    for result in results:
        html += f"""
            <tr>
                <td>{result.id}</td>
                <td>{result.test_id}</td>
                <td>{result.user_id}</td>
                <td>{result.score}</td>
                <td>{result.started_at}</td>
                <td>{result.finished_at}</td>
                <td>{getattr(result, 'duration_sec', 'N/A')}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    return html


@app.route('/admin/test-results')
@login_required
@role_required('admin')
def admin_test_results():
    """Управление результатами тестов"""
    import sqlite3

    # Получаем параметры фильтрации
    search = request.args.get('search', '').strip()
    test_id = request.args.get('test_id', '').strip()
    user_id = request.args.get('user_id', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 20

    # Прямой SQL запрос
    db_path = app.config['DATABASE_PATH']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Базовый запрос для результатов тестов
    query = '''
        SELECT tr.*, u.first_name, u.last_name, u.email, t.title as test_title
        FROM test_results tr
        JOIN users u ON tr.user_id = u.id
        JOIN tests t ON tr.test_id = t.id
        WHERE tr.finished_at IS NOT NULL
    '''
    params = []

    # Добавляем фильтры
    if test_id:
        query += ' AND tr.test_id = ?'
        params.append(test_id)

    if user_id:
        query += ' AND tr.user_id = ?'
        params.append(user_id)

    query += ' ORDER BY tr.finished_at DESC'

    # Выполняем запрос
    cursor = conn.cursor()
    cursor.execute(query, params)
    all_rows = cursor.fetchall()

    # Пагинация
    total_results = len(all_rows)
    total_pages = (total_results + per_page - 1) // per_page

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    results_page = all_rows[start_idx:end_idx]

    # Подготавливаем данные для шаблона
    results = []
    for row in results_page:
        score = float(row['score']) if row['score'] else 0.0
        max_score = float(row['max_score']) if row['max_score'] else 100.0
        percentage = (score / max_score * 100) if max_score > 0 else 0.0

        results.append({
            'result': {
                'id': row['id'],
                'test_id': row['test_id'],
                'user_id': row['user_id'],
                'score': score,
                'max_score': max_score,
                'started_at': row['started_at'],
                'finished_at': row['finished_at'],
                'duration_sec': row['duration_sec'] if 'duration_sec' in row.keys() else 0
            },
            'test_title': row['test_title'],
            'user_name': f"{row['first_name']} {row['last_name']}",
            'user_email': row['email']
        })

    # Получаем список тестов для фильтра
    cursor.execute('SELECT id, title FROM tests ORDER BY title')
    tests_rows = cursor.fetchall()
    tests = [{'id': row['id'], 'title': row['title']} for row in tests_rows]

    # Получаем список пользователей для фильтра
    cursor.execute('''
        SELECT id, first_name, last_name, email 
        FROM users 
        WHERE role = 'student' 
        ORDER BY first_name, last_name
    ''')
    users_rows = cursor.fetchall()
    users = []
    for row in users_rows:
        users.append({
            'id': row['id'],
            'first_name': row['first_name'],
            'last_name': row['last_name'],
            'email': row['email']
        })

    conn.close()

    return render_template('admin/test_results.html',
                           results=results,
                           tests=tests,
                           users=users,
                           test_id=test_id,
                           user_id=user_id,
                           page=page,
                           total_pages=total_pages,
                           total_results=total_results,
                           user_name=session.get('user_name'))


@app.route('/admin/test-attempts')
@login_required
@role_required('admin')
def admin_test_attempts():
    """Управление попытками тестов"""
    import sqlite3

    # Получаем параметры фильтрации
    test_id = request.args.get('test_id', '').strip()
    user_id = request.args.get('user_id', '').strip()

    # Прямой SQL запрос
    db_path = app.config['DATABASE_PATH']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Получаем список всех тестов
    cursor = conn.cursor()
    cursor.execute('SELECT id, title FROM tests ORDER BY title')
    tests_rows = cursor.fetchall()
    tests = [{'id': row['id'], 'title': row['title']} for row in tests_rows]

    # Получаем список всех студентов
    cursor.execute('''
        SELECT id, first_name, last_name, email 
        FROM users 
        WHERE role = 'student' 
        ORDER BY first_name, last_name
    ''')
    students_rows = cursor.fetchall()
    students = []
    for row in students_rows:
        students.append({
            'id': row['id'],
            'first_name': row['first_name'],
            'last_name': row['last_name'],
            'email': row['email']
        })

    # Получаем попытки, если выбраны тест и пользователь
    attempts_info = []
    selected_test = None
    selected_student = None

    if test_id and user_id:
        # Получаем информацию о выбранном тесте
        cursor.execute('SELECT id, title FROM tests WHERE id = ?', (test_id,))
        test_row = cursor.fetchone()
        if test_row:
            selected_test = {'id': test_row['id'], 'title': test_row['title']}

        # Получаем информацию о выбранном студенте
        cursor.execute('SELECT id, first_name, last_name, email FROM users WHERE id = ?', (user_id,))
        student_row = cursor.fetchone()
        if student_row:
            selected_student = {
                'id': student_row['id'],
                'first_name': student_row['first_name'],
                'last_name': student_row['last_name'],
                'email': student_row['email']
            }

        # Получаем все попытки для выбранных теста и пользователя
        cursor.execute('''
            SELECT * FROM test_results 
            WHERE test_id = ? AND user_id = ? 
            ORDER BY started_at DESC
        ''', (test_id, user_id))
        attempts_rows = cursor.fetchall()

        for i, row in enumerate(attempts_rows, 1):
            score = float(row['score']) if row['score'] else 0.0
            max_score = float(row['max_score']) if row['max_score'] else 100.0
            percentage = (score / max_score * 100) if max_score > 0 else 0.0

            attempts_info.append({
                'attempt_number': i,
                'attempt_id': row['id'],
                'score': score,
                'max_score': max_score,
                'percentage': percentage,
                'completed': row['finished_at'] is not None,
                'started_at': row['started_at'],
                'finished_at': row['finished_at'],
                'duration_sec': row['duration_sec'] if 'duration_sec' in row.keys() else None
            })

    conn.close()

    return render_template('admin/test_attempts.html',
                           tests=tests,
                           students=students,
                           test_id=test_id,
                           user_id=user_id,
                           attempts_info=attempts_info,
                           selected_test=selected_test,
                           selected_student=selected_student,
                           user_name=session.get('user_name'))


# ==================== РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ ВОПРОСОВ ====================

@app.route('/admin/questions/<question_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_question(question_id):
    """Редактирование вопроса - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    from database.models import Question, Test, Answer
    question_model = Question(auth_service.db)
    test_model = Test(auth_service.db)
    answer_model = Answer(auth_service.db)

    question = question_model.get_by_id(question_id)
    if not question:
        flash('Вопрос не найден', 'danger')
        return redirect(url_for('admin_tests'))

    # Получаем тест вопроса
    test = test_model.get_by_id(question.test_id)

    if request.method == 'POST':
        try:
            # Обновляем данные вопроса
            update_data = {
                'text': request.form.get('text', '').strip(),
                'type': request.form.get('type', 'single'),
                'points': int(request.form.get('points', 1)),
                'question_order': int(request.form.get('question_order', 1))
            }

            # Обновляем вопрос
            question_model.update(question_id, update_data)

            # Для вопросов с выбором ответа обрабатываем варианты
            if update_data['type'] in ['single', 'multiple']:
                # Получаем существующие ответы
                existing_answers = answer_model.get_by_question(question_id)

                # Получаем новые данные из формы
                option_texts = request.form.getlist('option_text[]')
                correct_options_raw = request.form.getlist('correct_option[]')
                correct_options = [int(idx) for idx in correct_options_raw if idx.isdigit()]

                print(f"DEBUG edit: Всего вариантов: {len(option_texts)}")
                print(f"DEBUG edit: Правильные индексы: {correct_options}")

                # Удаляем старые ответы
                for existing_answer in existing_answers:
                    answer_model.delete(existing_answer.id)

                # Создаем новые ответы
                for i, option_text in enumerate(option_texts):
                    if option_text.strip():
                        is_correct = i in correct_options

                        answer_data = {
                            'question_id': question_id,
                            'text': option_text.strip(),
                            'is_correct': is_correct,
                            'answer_order': i + 1
                        }

                        answer_model.create(answer_data)
                        print(f"DEBUG edit: Создан ответ {i + 1}: правильный={is_correct}")

            else:  # Для текстовых вопросов удаляем существующие ответы
                existing_answers = answer_model.get_by_question(question_id)
                for existing_answer in existing_answers:
                    answer_model.delete(existing_answer.id)

            flash('Вопрос успешно обновлен!', 'success')
            return redirect(url_for('admin_questions', test_id=question.test_id))

        except Exception as e:
            flash(f'Ошибка при обновлении вопроса: {str(e)}', 'danger')
            print(f"ERROR in admin_edit_question: {str(e)}")
            import traceback
            traceback.print_exc()

    # GET запрос - отображаем форму редактирования
    # Получаем ответы вопроса
    answers = answer_model.get_by_question(question_id)

    # Подготавливаем данные для шаблона
    question_data = {
        'id': question.id,
        'text': question.text,
        'type': question.type,
        'points': question.points if hasattr(question, 'points') else 1,
        'question_order': question.question_order if hasattr(question, 'question_order') else 1,
        'test_id': question.test_id,
        'options': []
    }

    for answer in answers:
        question_data['options'].append({
            'id': answer.id,
            'text': answer.text,
            'is_correct': answer.is_correct
        })

    return render_template('admin/question_form.html',
                           question=question_data,
                           selected_test=test,
                           test_id=question.test_id,
                           next_order=question.question_order,
                           question_types=['single', 'multiple', 'text'],
                           user_name=session.get('user_name'))


@app.route('/admin/questions/<question_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_question(question_id):
    """Удаление вопроса"""
    from database.models import Question
    question_model = Question(auth_service.db)

    question = question_model.get_by_id(question_id)
    if not question:
        flash('Вопрос не найден', 'danger')
        return redirect(url_for('admin_tests'))

    try:
        # Сохраняем ID теста для перенаправления
        test_id = question.test_id

        # Удаляем вопрос
        success = question_model.delete(question_id)

        if success:
            flash('Вопрос успешно удален!', 'success')
        else:
            flash('Ошибка при удалении вопроса', 'danger')

        return redirect(url_for('admin_questions', test_id=test_id))

    except Exception as e:
        flash(f'Ошибка при удалении вопроса: {str(e)}', 'danger')
        return redirect(url_for('admin_tests'))

# ==================== ДЕТАЛЬНЫЙ ПРОСМОТР ПРОГРЕССА ====================

@app.route('/admin/progress/<int:progress_id>')
@login_required
@role_required('admin')
def admin_view_progress(progress_id):
    """Просмотр детальной информации о прогрессе студента"""
    # Пока просто перенаправляем на страницу прогресса
    flash(f'Детальный просмотр прогресса ID: {progress_id} будет реализован позже', 'info')
    return redirect(url_for('admin_progress'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
