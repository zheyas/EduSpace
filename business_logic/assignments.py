from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from database.models import DatabaseConnection, User, Course, Module


class AssignmentService:
    """Сервис для управления заданиями (домашними работами)"""

    def __init__(self, db_path: str):
        self.db = DatabaseConnection(db_path)

    def create_assignment(self, teacher_id: str, assignment_data: Dict[str, Any]) -> Tuple[
        bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Создание задания

        Args:
            teacher_id: ID преподавателя
            assignment_data: Данные задания

        Returns:
            Tuple[success, message, assignment_data]
        """
        try:
            # В реальной системе здесь была бы таблица assignments
            # Для демо возвращаем успех

            assignment = {
                'id': f"ASN{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'teacher_id': teacher_id,
                'title': assignment_data.get('title'),
                'description': assignment_data.get('description'),
                'course_id': assignment_data.get('course_id'),
                'module_id': assignment_data.get('module_id'),
                'max_score': assignment_data.get('max_score', 100),
                'deadline': assignment_data.get('deadline'),
                'created_at': datetime.now().isoformat()
            }

            return True, "Задание создано", assignment

        except Exception as e:
            return False, f"Ошибка создания задания: {str(e)}", None

    def submit_assignment(self, student_id: str, assignment_id: str,
                          submission_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Отправка выполненного задания

        Args:
            student_id: ID студента
            assignment_id: ID задания
            submission_data: Данные отправки

        Returns:
            Tuple[success, message]
        """
        try:
            # В реальной системе здесь была бы таблица assignment_submissions
            # Для демо возвращаем успех

            return True, "Задание отправлено"

        except Exception as e:
            return False, f"Ошибка отправки задания: {str(e)}"

    def get_student_assignments(self, student_id: str, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получение заданий студента

        Args:
            student_id: ID студента
            course_id: ID курса (опционально)

        Returns:
            Список заданий
        """
        try:
            # В реальной системе здесь был бы запрос к БД
            # Для демо возвращаем тестовые данные

            # Получаем курсы студента
            from .courses import CourseService
            course_service = CourseService(self.db_path)
            enrolled_courses = course_service.get_student_courses(student_id)

            assignments = []

            # Для каждого курса создаем тестовые задания
            for course_data in enrolled_courses[:2]:  # Ограничиваем 2 курсами для демо
                if course_id and course_data['course']['id'] != course_id:
                    continue

                course_assignments = [
                    {
                        'id': f"ASN{datetime.now().strftime('%Y%m%d%H%M%S')}1",
                        'title': f'Домашняя работа 1: {course_data["course"]["title"]}',
                        'description': 'Выполните практическое задание по пройденному материалу',
                        'course_id': course_data['course']['id'],
                        'course_title': course_data['course']['title'],
                        'max_score': 100,
                        'deadline': (datetime.now() + timedelta(days=7)).isoformat(),
                        'status': 'pending',  # pending, submitted, graded
                        'submission_date': None,
                        'score': None,
                        'feedback': None
                    },
                    {
                        'id': f"ASN{datetime.now().strftime('%Y%m%d%H%M%S')}2",
                        'title': f'Проект: {course_data["course"]["title"]}',
                        'description': 'Разработайте небольшой проект на основе изученного материала',
                        'course_id': course_data['course']['id'],
                        'course_title': course_data['course']['title'],
                        'max_score': 150,
                        'deadline': (datetime.now() + timedelta(days=14)).isoformat(),
                        'status': 'pending',
                        'submission_date': None,
                        'score': None,
                        'feedback': None
                    }
                ]

                assignments.extend(course_assignments)

            return assignments

        except Exception as e:
            print(f"Ошибка получения заданий: {e}")
            return []

    def grade_assignment(self, teacher_id: str, submission_id: str,
                         grade_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Оценка задания преподавателем

        Args:
            teacher_id: ID преподавателя
            submission_id: ID отправки
            grade_data: Данные оценки

        Returns:
            Tuple[success, message]
        """
        try:
            # В реальной системе здесь был бы запрос к БД
            # Для демо возвращаем успех

            return True, "Задание оценено"

        except Exception as e:
            return False, f"Ошибка оценки задания: {str(e)}"
