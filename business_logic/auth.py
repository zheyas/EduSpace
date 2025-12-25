from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import hashlib
from database.models import DatabaseConnection, User, UserRole


class AuthService:
    """Сервис для управления аутентификацией и авторизацией"""

    def __init__(self, db_path: str):
        self.db = DatabaseConnection(db_path)
        self.user_model = User(self.db)

    def hash_password(self, password: str) -> str:
        """Простое хеширование пароля"""
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        return self.hash_password(password) == hashed_password

    def register_user(self, user_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[User]]:
        """
        Регистрация нового пользователя
        """
        try:
            # Проверяем, что email свободен
            existing_user = self.user_model.get_by_email(user_data['email'])
            if existing_user:
                return False, "Пользователь с таким email уже существует", None

            # Хешируем пароль
            hashed_password = self.hash_password(user_data['password'])

            # Подготавливаем данные для создания пользователя
            user_create_data = {
                'last_name': user_data['last_name'],
                'first_name': user_data['first_name'],
                'email': user_data['email'],
                'password_hash': hashed_password,
                'role': user_data.get('role', UserRole.STUDENT.value)
            }

            # Создаем пользователя
            user = self.user_model.create(user_create_data)

            return True, "Пользователь успешно зарегистрирован", user

        except Exception as e:
            return False, f"Ошибка регистрации: {str(e)}", None

    def login_user(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Аутентификация пользователя
        """
        try:
            # Ищем пользователя по email
            user = self.user_model.get_by_email(email)
            if not user:
                return False, "Пользователь не найден", None

            # Проверяем пароль
            if not self.verify_password(password, user.password_hash):
                return False, "Неверный пароль", None

            # Формируем данные пользователя для сессии
            user_data = {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }

            return True, "Успешный вход", user_data

        except Exception as e:
            return False, f"Ошибка входа: {str(e)}", None

    def update_user_profile(self, user_id: str, update_data: Dict[str, Any]) -> Tuple[
        bool, Optional[str], Optional[User]]:
        """
        Обновление профиля пользователя
        """
        try:
            user = self.user_model.get_by_id(user_id)
            if not user:
                return False, "Пользователь не найден", None

            # Если обновляется пароль, хешируем его
            if 'password' in update_data:
                update_data['password_hash'] = self.hash_password(update_data['password'])
                del update_data['password']

            # Обновляем пользователя
            updated_user = self.user_model.update(user_id, update_data)

            if updated_user:
                return True, "Профиль успешно обновлен", updated_user
            else:
                return False, "Не удалось обновить профиль", None

        except Exception as e:
            return False, f"Ошибка обновления профиля: {str(e)}", None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Получение пользователя по ID"""
        return self.user_model.get_by_id(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Получение пользователя по email"""
        return self.user_model.get_by_email(email)

    def get_all_users(self, skip: int = 0, limit: int = 100) -> list:
        """Получение всех пользователей"""
        return self.user_model.get_all(skip, limit)

    def get_users_by_role(self, role: UserRole, skip: int = 0, limit: int = 100) -> list:
        """Получение пользователей по роли"""
        return self.user_model.get_by_role(role, skip, limit)

    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Получение статистики пользователя
        """
        try:
            from database.models import ProgressCourse, TestResult

            user = self.user_model.get_by_id(user_id)
            if not user:
                return {}

            progress_model = ProgressCourse(self.db)
            test_result_model = TestResult(self.db)

            # Получаем прогресс по курсам
            user_progress = progress_model.get_by_user(user_id)

            # Собираем статистику
            stats = {
                'user_id': user_id,
                'name': f"{user.first_name} {user.last_name}",
                'role': user.role,
                'courses': {
                    'total': len(user_progress),
                    'completed': sum(1 for p in user_progress if p.status == 'completed'),
                    'active': sum(1 for p in user_progress if p.status == 'active'),
                    'dropped': sum(1 for p in user_progress if p.status == 'dropped')
                },
                'average_score': 0,
                'last_activity': None
            }

            # Рассчитываем средний балл
            completed_courses = [p for p in user_progress if p.status == 'completed' and p.final_score]
            if completed_courses:
                stats['average_score'] = sum(p.final_score for p in completed_courses) / len(completed_courses)

            # Получаем дату последней активности
            test_results = test_result_model.get_by_user_and_test(user_id, '', skip=0, limit=1)
            if test_results:
                stats['last_activity'] = test_results[0].finished_at.isoformat() if test_results[
                    0].finished_at else None

            return stats

        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return {}
