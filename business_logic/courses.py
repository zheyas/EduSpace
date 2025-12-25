#business_logic/courses.py
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from database.models import (
    DatabaseConnection, Course, Module, Test, Question, Answer,
    ProgressCourse, ProgressModule, TestResult, UserAnswer,
    AnalyticsService, User, UserRole, EnrollmentStatus, ProgressStatus,
    LearningMaterial, MaterialProgress
)


class CourseService:
    """Сервис для управления курсами"""

    def __init__(self, db_path: str):
        self.db = DatabaseConnection(db_path)
        self.course_model = Course(self.db)
        self.module_model = Module(self.db)
        self.test_model = Test(self.db)
        self.question_model = Question(self.db)
        self.answer_model = Answer(self.db)
        self.material_model = LearningMaterial(self.db)
        self.material_progress_model = MaterialProgress(self.db)
        self.analytics = AnalyticsService(self.db)

    # business_logic/courses.py
    # Добавьте этот метод в класс CourseService

    # business_logic/courses.py
    # Добавьте этот метод в класс CourseService

    def enroll_student(self, user_id: str, course_id: str) -> Tuple[bool, str, Optional[ProgressCourse]]:
        """Записать студента на курс"""
        try:
            # Проверяем существование курса
            course = self.course_model.get_by_id(course_id)
            if not course:
                return False, "Курс не найден", None

            if not course.is_active:
                return False, "Курс не активен", None

            # Проверяем, что пользователь - студент
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            if user.role != UserRole.STUDENT.value:
                return False, "Только студенты могут записываться на курсы", None

            # Проверяем, не записан ли уже студент на курс
            progress_course_model = ProgressCourse(self.db)
            existing_progress = progress_course_model.get_by_user_and_course(user_id, course_id)

            if existing_progress:
                return False, "Вы уже записаны на этот курс", None

            # Создаем запись о прогрессе
            enrollment_data = {
                'user_id': user_id,
                'course_id': course_id,
                'status': ProgressStatus.IN_PROGRESS.value,
                'started_at': datetime.now().isoformat()
            }

            progress = progress_course_model.create(enrollment_data)

            # Получаем модули курса и создаем прогресс для каждого модуля
            modules = self.module_model.get_by_course(course_id)
            progress_module_model = ProgressModule(self.db)

            for module in modules:
                module_progress_data = {
                    'enrollment_id': progress.id,
                    'module_id': module.id,
                    'status': ProgressStatus.NOT_STARTED.value
                }
                progress_module_model.create(module_progress_data)

            return True, f"Вы успешно записались на курс '{course.title}'", progress

        except Exception as e:
            print(f"Ошибка записи на курс: {e}")
            return False, f"Ошибка записи на курс: {str(e)}", None

    def get_student_courses(self, user_id: str) -> List[Dict[str, Any]]:
        """Получение курсов, на которые записан студент"""
        try:
            # Прямой SQL запрос для получения курсов студента с прогрессом
            query = """
                SELECT 
                    c.id, c.title, c.short_description, c.author_id,
                    c.start_date, c.end_date, c.is_active,
                    pc.id as progress_id, pc.status, pc.enrolled_at, pc.finished_at,
                    pc.progress_percent, pc.final_score,
                    u.first_name as author_first_name, u.last_name as author_last_name
                FROM courses c
                JOIN progress_courses pc ON c.id = pc.course_id
                JOIN users u ON c.author_id = u.id
                WHERE pc.user_id = ? AND c.is_active = 1
                ORDER BY pc.enrolled_at DESC
            """

            rows = self.db.execute_query(query, (user_id,))
            result = []

            for row in rows:
                # Получаем модули курса
                modules = self.module_model.get_by_course(row['id'])

                # Получаем прогресс по модулям
                progress_module_model = ProgressModule(self.db)
                completed_modules = 0

                for module in modules:
                    module_progress = progress_module_model.get_by_enrollment_and_module(row['progress_id'], module.id)
                    if module_progress and module_progress.status == 'completed':
                        completed_modules += 1

                # Рассчитываем процент завершения
                completion_percentage = (completed_modules / len(modules) * 100) if len(modules) > 0 else 0

                # Форматируем enrolled_at
                enrolled_at = row['enrolled_at']
                enrolled_at_str = ""
                if enrolled_at:
                    try:
                        # Пробуем разные форматы дат
                        if isinstance(enrolled_at, str):
                            if 'T' in enrolled_at:
                                # ISO формат: 2025-12-18T08:13:32.879177
                                dt = datetime.fromisoformat(enrolled_at.replace('Z', '+00:00'))
                                enrolled_at_str = dt.isoformat()
                            else:
                                # SQLite формат: 2025-12-18 08:13:32.879177
                                try:
                                    dt = datetime.strptime(enrolled_at, '%Y-%m-%d %H:%M:%S.%f')
                                except ValueError:
                                    dt = datetime.strptime(enrolled_at, '%Y-%m-%d %H:%M:%S')
                                enrolled_at_str = dt.isoformat()
                        else:
                            enrolled_at_str = str(enrolled_at)
                    except Exception as e:
                        print(f"Ошибка форматирования enrolled_at {enrolled_at}: {e}")
                        enrolled_at_str = str(enrolled_at)[:19]  # Берем первые 19 символов

                # Форматируем finished_at
                finished_at = row['finished_at']
                finished_at_str = ""
                if finished_at:
                    try:
                        if isinstance(finished_at, str):
                            if 'T' in finished_at:
                                dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                                finished_at_str = dt.isoformat()
                            else:
                                try:
                                    dt = datetime.strptime(finished_at, '%Y-%m-%d %H:%M:%S.%f')
                                except ValueError:
                                    dt = datetime.strptime(finished_at, '%Y-%m-%d %H:%M:%S')
                                finished_at_str = dt.isoformat()
                        else:
                            finished_at_str = str(finished_at)
                    except Exception as e:
                        print(f"Ошибка форматирования finished_at {finished_at}: {e}")
                        finished_at_str = str(finished_at)[:19]

                # Форматируем данные для шаблона
                result.append({
                    'course': {
                        'id': row['id'],
                        'title': row['title'],
                        'short_description': row['short_description'],
                        'author_id': row['author_id'],
                        'author_name': f"{row['author_first_name']} {row['author_last_name']}",
                        'start_date': row['start_date'],
                        'end_date': row['end_date'],
                        'is_active': row['is_active']
                    },
                    'progress': {
                        'id': row['progress_id'],
                        'status': row['status'] or 'active',
                        'progress_percent': completion_percentage,
                        'enrolled_at': enrolled_at_str,  # ИСПРАВЛЕНО: используем enrolled_at
                        'finished_at': finished_at_str
                    },
                    'stats': {
                        'completed_modules': completed_modules,
                        'total_modules': len(modules),
                        'completed_tests': 0,
                        'total_tests': 0,
                        'average_score': 0
                    }
                })

            return result

        except Exception as e:
            print(f"Ошибка получения курсов студента: {e}")
            import traceback
            traceback.print_exc()
            return []
            # ==================== МЕТОДЫ ДЛЯ КУРСОВ ====================

    def create_course(self, course_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Course]]:
        """Создание нового курса"""
        try:
            # Проверяем права пользователя
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user or user.role not in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
                return False, "Только преподаватели и администраторы могут создавать курсы", None

            # Добавляем автора
            course_data['author_id'] = user_id
            course_data['created_at'] = datetime.now().isoformat()
            course_data['is_active'] = course_data.get('is_active', True)

            # Создаем курс
            course = self.course_model.create(course_data)

            return True, f"Курс '{course.title}' успешно создан", course
        except Exception as e:
            return False, f"Ошибка при создании курса: {str(e)}", None

    def update_course(self, course_id: str, update_data: Dict[str, Any], user_id: str) -> Tuple[
        bool, str, Optional[Course]]:
        """Обновление курса"""
        try:
            # Получаем курс
            course = self.course_model.get_by_id(course_id)
            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут редактировать все курсы, учителя - только свои
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для редактирования этого курса", None

            # Обновляем курс
            updated_course = self.course_model.update(course_id, update_data)
            return True, "Курс успешно обновлен", updated_course
        except Exception as e:
            return False, f"Ошибка при обновлении курса: {str(e)}", None

    def delete_course(self, course_id: str, user_id: str) -> Tuple[bool, str]:
        """Удаление курса"""
        try:
            # Получаем курс
            course = self.course_model.get_by_id(course_id)
            if not course:
                return False, "Курс не найден"

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден"

            # Админы могут удалять все курсы, учителя - только свои
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для удаления этого курса"

            # Удаляем все связанные данные (в каскадном порядке)

            # 1. Удаляем материалы и их прогресс
            modules = self.module_model.get_by_course(course_id)
            for module in modules:
                # Удаляем материалы модуля
                materials = self.material_model.get_by_module(module.id)
                for material in materials:
                    # Удаляем прогресс материалов
                    material_progress_list = []
                    try:
                        # Прямой SQL запрос для получения прогресса материалов
                        results = self.db.execute_query(
                            "SELECT id FROM material_progress WHERE material_id = ?",
                            (material.id,)
                        )
                        material_progress_list = [r['id'] for r in results]
                    except:
                        pass

                    for progress_id in material_progress_list:
                        self.material_progress_model.delete(progress_id)

                    # Удаляем материал
                    self.material_model.delete(material.id)

                # Удаляем тесты модуля
                tests = self.test_model.get_by_module(module.id)
                for test in tests:
                    # Удаляем вопросы теста
                    questions = self.question_model.get_by_test(test.id)
                    for question in questions:
                        # Удаляем ответы вопроса
                        answers = self.answer_model.get_by_question(question.id)
                        for answer in answers:
                            self.answer_model.delete(answer.id)

                        # Удаляем вопрос
                        self.question_model.delete(question.id)

                    # Удаляем результаты теста
                    try:
                        self.db.execute_query(
                            "DELETE FROM test_results WHERE test_id = ?",
                            (test.id,)
                        )
                    except:
                        pass

                    # Удаляем тест
                    self.test_model.delete(test.id)

                # Удаляем прогресс модуля
                try:
                    self.db.execute_query(
                        "DELETE FROM progress_modules WHERE module_id = ?",
                        (module.id,)
                    )
                except:
                    pass

                # Удаляем модуль
                self.module_model.delete(module.id)

            # 2. Удаляем прогресс курса
            try:
                self.db.execute_query(
                    "DELETE FROM progress_courses WHERE course_id = ?",
                    (course_id,)
                )
            except:
                pass

            # 3. Удаляем курс
            success = self.course_model.delete(course_id)

            if success:
                return True, f"Курс '{course.title}' успешно удален"
            else:
                return False, "Ошибка при удалении курса"
        except Exception as e:
            return False, f"Ошибка при удалении курса: {str(e)}"

    def get_course_with_modules(self, course_id: str) -> Dict[str, Any]:
        """Получение курса со всеми модулями"""
        try:
            course = self.course_model.get_by_id(course_id)
            if not course:
                return {}

            # Получаем модули курса
            modules = self.module_model.get_by_course(course_id)

            # Получаем информацию о каждом модуле
            modules_with_details = []
            for module in modules:
                # Получаем количество материалов в модуле
                materials_count = len(self.material_model.get_by_module(module.id))

                # Получаем количество тестов в модуле
                tests_count = len(self.test_model.get_by_module(module.id))

                modules_with_details.append({
                    'id': module.id,
                    'title': module.title,
                    'short_description': module.short_description,
                    'order': module.module_order,
                    'estimated_duration': module.estimated_duration,
                    'materials_count': materials_count,
                    'tests_count': tests_count,
                    'created_at': module.created_at
                })

            # Получаем автора курса
            user_model = User(self.db)
            author = user_model.get_by_id(course.author_id)

            return {
                'course': course.to_dict(),
                'author': author.to_dict() if author else {},
                'modules': modules_with_details,
                'total_modules': len(modules)
            }
        except Exception as e:
            print(f"Ошибка получения курса с модулями: {e}")
            return {}

    # ==================== МЕТОДЫ ДЛЯ МОДУЛЕЙ ====================

    def create_module(self, module_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Module]]:
        """Создание нового модуля"""
        try:
            # Проверяем существование курса
            course = self.course_model.get_by_id(module_data['course_id'])
            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут создавать модули в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для создания модулей в этом курсе", None

            # Автоматически определяем порядковый номер
            existing_modules = self.module_model.get_by_course(module_data['course_id'])
            module_data['module_order'] = len(existing_modules) + 1

            # Создаем модуль
            module = self.module_model.create(module_data)

            return True, f"Модуль '{module.title}' успешно создан", module
        except Exception as e:
            return False, f"Ошибка при создании модуля: {str(e)}", None

    def update_module(self, module_id: str, update_data: Dict[str, Any], user_id: str) -> Tuple[
        bool, str, Optional[Module]]:
        """Обновление модуля"""
        try:
            # Получаем модуль
            module = self.module_model.get_by_id(module_id)
            if not module:
                return False, "Модуль не найден", None

            # Получаем курс модуля
            course = self.course_model.get_by_id(module.course_id)
            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут редактировать модули в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для редактирования этого модуля", None

            # Обновляем модуль
            updated_module = self.module_model.update(module_id, update_data)
            return True, "Модуль успешно обновлен", updated_module
        except Exception as e:
            return False, f"Ошибка при обновлении модуля: {str(e)}", None

    def get_module_with_details(self, module_id: str) -> Dict[str, Any]:
        """Получение модуля со всеми материалами и тестами"""
        try:
            module = self.module_model.get_by_id(module_id)
            if not module:
                return {}

            # Получаем курс
            course = self.course_model.get_by_id(module.course_id)

            # Получаем материалы модуля
            materials = self.material_model.get_by_module(module_id)
            materials_list = []
            for material in materials:
                materials_list.append({
                    'id': material.id,
                    'title': material.title,
                    'content_type': material.content_type,
                    'content_preview': (material.content[:100] + '...') if material.content and len(
                        material.content) > 100 else material.content,
                    'material_order': material.material_order,
                    'created_at': material.created_at
                })

            # Получаем тесты модуля
            tests = self.test_model.get_by_module(module_id)
            tests_list = []
            for test in tests:
                # Получаем количество вопросов в тесте
                questions = self.question_model.get_by_test(test.id)

                tests_list.append({
                    'id': test.id,
                    'title': test.title,
                    'description': test.description,
                    'time_limit': test.time_limit,
                    'max_score': test.max_score,
                    'questions_count': len(questions),
                    'created_at': test.created_at
                })

            return {
                'module': module.to_dict(),
                'course': course.to_dict() if course else {},
                'materials': materials_list,
                'tests': tests_list,
                'materials_count': len(materials_list),
                'tests_count': len(tests_list)
            }
        except Exception as e:
            print(f"Ошибка получения модуля с деталями: {e}")
            return {}

    # ==================== МЕТОДЫ ДЛЯ МАТЕРИАЛОВ ====================

    def create_material(self, material_data: Dict[str, Any], user_id: str) -> Tuple[
        bool, str, Optional[LearningMaterial]]:
        """Создание учебного материала"""
        try:
            # Проверяем существование модуля
            module = self.module_model.get_by_id(material_data['module_id'])
            if not module:
                return False, "Модуль не найден", None

            # Получаем курс
            course = self.course_model.get_by_id(module.course_id)
            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут создавать материалы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для создания материалов в этом курсе", None

            # Автоматически определяем порядковый номер
            existing_materials = self.material_model.get_by_module(material_data['module_id'])
            material_data['material_order'] = len(existing_materials) + 1

            # Устанавливаем тип контента по умолчанию
            if 'content_type' not in material_data:
                material_data['content_type'] = 'text'

            # Создаем материал
            material = self.material_model.create(material_data)

            return True, f"Материал '{material.title}' успешно создан", material
        except Exception as e:
            return False, f"Ошибка при создании материала: {str(e)}", None

    def update_material(self, material_id: str, update_data: Dict[str, Any], user_id: str) -> Tuple[
        bool, str, Optional[LearningMaterial]]:
        """Обновление учебного материала"""
        try:
            # Получаем материал
            material = self.material_model.get_by_id(material_id)
            if not material:
                return False, "Материал не найден", None

            # Получаем модуль
            module = self.module_model.get_by_id(material.module_id)
            if not module:
                return False, "Модуль не найден", None

            # Получаем курс
            course = self.course_model.get_by_id(module.course_id)
            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут редактировать материалы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для редактирования этого материала", None

            # Обновляем материал
            updated_material = self.material_model.update(material_id, update_data)
            return True, "Материал успешно обновлен", updated_material
        except Exception as e:
            return False, f"Ошибка при обновлении материала: {str(e)}", None

    def delete_material(self, material_id: str, user_id: str) -> Tuple[bool, str]:
        """Удаление учебного материала"""
        try:
            # Получаем материал
            material = self.material_model.get_by_id(material_id)
            if not material:
                return False, "Материал не найден"

            # Получаем модуль
            module = self.module_model.get_by_id(material.module_id)
            if not module:
                return False, "Модуль не найден"

            # Получаем курс
            course = self.course_model.get_by_id(module.course_id)
            if not course:
                return False, "Курс не найден"

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден"

            # Админы могут удалять материалы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для удаления этого материала"

            # Удаляем прогресс по материалу
            try:
                self.db.execute_query(
                    "DELETE FROM material_progress WHERE material_id = ?",
                    (material_id,)
                )
            except:
                pass

            # Удаляем материал
            success = self.material_model.delete(material_id)

            if success:
                return True, f"Материал '{material.title}' успешно удален"
            else:
                return False, "Ошибка при удалении материала"
        except Exception as e:
            return False, f"Ошибка при удалении материала: {str(e)}"

    # ==================== МЕТОДЫ ДЛЯ ТЕСТОВ ====================

    def create_test(self, test_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Test]]:
        """Создание нового теста"""
        try:
            # Проверяем наличие module_id или course_id
            if 'module_id' not in test_data and 'course_id' not in test_data:
                return False, "Необходимо указать module_id или course_id", None

            # Если указан module_id, проверяем существование модуля
            if 'module_id' in test_data and test_data['module_id']:
                module = self.module_model.get_by_id(test_data['module_id'])
                if not module:
                    return False, "Модуль не найден", None

                # Получаем курс модуля
                course = self.course_model.get_by_id(module.course_id)
                if not course:
                    return False, "Курс не найден", None

                # Проверяем права доступа
                user_model = User(self.db)
                user = user_model.get_by_id(user_id)

                if not user:
                    return False, "Пользователь не найден", None

                # Админы могут создавать тесты в любых курсах, учителя - только в своих
                if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                    return False, "У вас нет прав для создания тестов в этом курсе", None

                # Добавляем course_id в данные теста
                test_data['course_id'] = course.id

            # Если указан только course_id, проверяем существование курса
            elif 'course_id' in test_data and test_data['course_id']:
                course = self.course_model.get_by_id(test_data['course_id'])
                if not course:
                    return False, "Курс не найден", None

                # Проверяем права доступа
                user_model = User(self.db)
                user = user_model.get_by_id(user_id)

                if not user:
                    return False, "Пользователь не найден", None

                # Админы могут создавать тесты в любых курсах, учителя - только в своих
                if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                    return False, "У вас нет прав для создания тестов в этом курсе", None

            # Устанавливаем значения по умолчанию
            test_data['max_score'] = test_data.get('max_score', 100)
            test_data['time_limit'] = test_data.get('time_limit', 60)

            # Создаем тест
            test = self.test_model.create(test_data)

            return True, f"Тест '{test.title}' успешно создан", test
        except Exception as e:
            return False, f"Ошибка при создании теста: {str(e)}", None

    def update_test(self, test_id: str, update_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Test]]:
        """Обновление теста"""
        try:
            # Получаем тест
            test = self.test_model.get_by_id(test_id)
            if not test:
                return False, "Тест не найден", None

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут редактировать тесты в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для редактирования этого теста", None

            # Обновляем тест
            updated_test = self.test_model.update(test_id, update_data)
            return True, "Тест успешно обновлен", updated_test
        except Exception as e:
            return False, f"Ошибка при обновлении теста: {str(e)}", None

    def delete_test(self, test_id: str, user_id: str) -> Tuple[bool, str]:
        """Удаление теста"""
        try:
            # Получаем тест
            test = self.test_model.get_by_id(test_id)
            if not test:
                return False, "Тест не найден"

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            if not course:
                return False, "Курс не найден"

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден"

            # Админы могут удалять тесты в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для удаления этого теста"

            # Удаляем все вопросы и ответы теста
            questions = self.question_model.get_by_test(test_id)
            for question in questions:
                # Удаляем ответы вопроса
                answers = self.answer_model.get_by_question(question.id)
                for answer in answers:
                    self.answer_model.delete(answer.id)

                # Удаляем вопрос
                self.question_model.delete(question.id)

            # Удаляем результаты теста
            try:
                self.db.execute_query(
                    "DELETE FROM test_results WHERE test_id = ?",
                    (test_id,)
                )
            except:
                pass

            # Удаляем ответы пользователей
            try:
                self.db.execute_query(
                    "DELETE FROM user_answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)",
                    (test_id,)
                )
            except:
                pass

            # Удаляем тест
            success = self.test_model.delete(test_id)

            if success:
                return True, f"Тест '{test.title}' успешно удален"
            else:
                return False, "Ошибка при удалении теста"
        except Exception as e:
            return False, f"Ошибка при удалении теста: {str(e)}"

    def get_test_with_questions(self, test_id: str, include_correct_answers: bool = False) -> Dict[str, Any]:
        """Получение теста со всеми вопросами и ответами"""
        try:
            test = self.test_model.get_by_id(test_id)
            if not test:
                return {}

            # Получаем вопросы теста
            questions = self.question_model.get_by_test(test_id)

            questions_list = []
            for question in questions:
                # Получаем ответы на вопрос
                answers = self.answer_model.get_by_question(question.id)

                answers_list = []
                for answer in answers:
                    answer_data = {
                        'id': answer.id,
                        'text': answer.text,
                        'answer_order': answer.answer_order
                    }

                    # Включаем информацию о правильности ответа только если нужно
                    if include_correct_answers:
                        answer_data['is_correct'] = answer.is_correct

                    answers_list.append(answer_data)

                questions_list.append({
                    'id': question.id,
                    'text': question.text,
                    'type': question.type,
                    'question_order': question.question_order,
                    'answers': answers_list
                })

            # Сортируем вопросы по порядку
            questions_list.sort(key=lambda x: x['question_order'])

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            return {
                'test': test.to_dict(),
                'course': course.to_dict() if course else {},
                'questions': questions_list,
                'total_questions': len(questions_list),
                'max_score': test.max_score or 100
            }
        except Exception as e:
            print(f"Ошибка получения теста с вопросами: {e}")
            return {}

    # ==================== МЕТОДЫ ДЛЯ ВОПРОСОВ И ОТВЕТОВ ====================

    def create_question(self, question_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Question]]:
        """Создание нового вопроса"""
        try:
            # Проверяем существование теста
            test = self.test_model.get_by_id(question_data['test_id'])
            if not test:
                return False, "Тест не найден", None

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут создавать вопросы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для создания вопросов в этом курсе", None

            # Автоматически определяем порядковый номер
            existing_questions = self.question_model.get_by_test(question_data['test_id'])
            question_data['question_order'] = len(existing_questions) + 1

            # Создаем вопрос
            question = self.question_model.create(question_data)

            return True, f"Вопрос успешно создан", question
        except Exception as e:
            return False, f"Ошибка при создании вопроса: {str(e)}", None

    def update_question(self, question_id: str, update_data: Dict[str, Any], user_id: str) -> Tuple[
        bool, str, Optional[Question]]:
        """Обновление вопроса"""
        try:
            # Получаем вопрос
            question = self.question_model.get_by_id(question_id)
            if not question:
                return False, "Вопрос не найден", None

            # Получаем тест
            test = self.test_model.get_by_id(question.test_id)
            if not test:
                return False, "Тест не найден", None

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут редактировать вопросы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для редактирования этого вопроса", None

            # Обновляем вопрос
            updated_question = self.question_model.update(question_id, update_data)
            return True, "Вопрос успешно обновлен", updated_question
        except Exception as e:
            return False, f"Ошибка при обновлении вопроса: {str(e)}", None

    def create_answer(self, answer_data: Dict[str, Any], user_id: str) -> Tuple[bool, str, Optional[Answer]]:
        """Создание нового ответа"""
        try:
            # Проверяем существование вопроса
            question = self.question_model.get_by_id(answer_data['question_id'])
            if not question:
                return False, "Вопрос не найден", None

            # Получаем тест
            test = self.test_model.get_by_id(question.test_id)
            if not test:
                return False, "Тест не найден", None

            # Определяем курс теста
            course = None
            if test.course_id:
                course = self.course_model.get_by_id(test.course_id)
            elif test.module_id:
                module = self.module_model.get_by_id(test.module_id)
                if module:
                    course = self.course_model.get_by_id(module.course_id)

            if not course:
                return False, "Курс не найден", None

            # Проверяем права доступа
            user_model = User(self.db)
            user = user_model.get_by_id(user_id)

            if not user:
                return False, "Пользователь не найден", None

            # Админы могут создавать ответы в любых курсах, учителя - только в своих
            if user.role == UserRole.TEACHER.value and course.author_id != user_id:
                return False, "У вас нет прав для создания ответов в этом курсе", None

            # Автоматически определяем порядковый номер
            existing_answers = self.answer_model.get_by_question(answer_data['question_id'])
            answer_data['answer_order'] = len(existing_answers) + 1

            # Создаем ответ
            answer = self.answer_model.create(answer_data)

            return True, "Ответ успешно создан", answer
        except Exception as e:
            return False, f"Ошибка при создании ответа: {str(e)}", None

    # ==================== УТИЛИТНЫЕ МЕТОДЫ ====================

    def get_all_courses(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Получение всех курсов"""
        try:
            courses = self.course_model.get_all(active_only=not include_inactive)

            result = []
            for course in courses:
                # Получаем автора
                user_model = User(self.db)
                author = user_model.get_by_id(course.author_id)

                # Получаем количество модулей
                modules = self.module_model.get_by_course(course.id)

                # Получаем статистику
                stats = self.course_model.get_completion_stats(course.id)

                result.append({
                    'id': course.id,
                    'title': course.title,
                    'short_description': course.short_description,
                    'author': f"{author.first_name} {author.last_name}" if author else "Неизвестно",
                    'author_id': course.author_id,
                    'modules_count': len(modules),
                    'is_active': course.is_active,
                    'start_date': course.start_date,
                    'end_date': course.end_date,
                    'created_at': course.created_at,
                    'stats': stats
                })

            return result
        except Exception as e:
            print(f"Ошибка получения всех курсов: {e}")
            return []

    def get_course_statistics(self, course_id: str) -> Dict[str, Any]:
        """Получение статистики курса"""
        try:
            course = self.course_model.get_by_id(course_id)
            if not course:
                return {}

            # Получаем базовую статистику
            stats = self.course_model.get_completion_stats(course_id)

            # Получаем топ студентов
            top_students = self.course_model.get_top_students(course_id, limit=5)

            # Получаем тренды
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            trends = self.analytics.get_learning_trends(course_id, start_date, end_date)

            return {
                'basic_stats': stats,
                'top_students': top_students,
                'trends': trends,
                'course': {
                    'id': course.id,
                    'title': course.title,
                    'author_id': course.author_id
                }
            }
        except Exception as e:
            print(f"Ошибка получения статистики курса: {e}")
            return {}
