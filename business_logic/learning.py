from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from database.models import DatabaseConnection, Module, LearningMaterial, ProgressModule, Test, \
    TestResult, ProgressCourse, MaterialProgress


class LearningService:
    def __init__(self, db_path: str = "educational_platform.db"):
        self.db = DatabaseConnection(db_path)
        self.db_path = db_path

    def get_module_with_materials(self, module_id: str, user_id: str = None) -> Optional[Dict[str, Any]]:
        """Получение модуля со всеми материалами и статусом изучения для пользователя"""
        module_model = Module(self.db)
        material_model = LearningMaterial(self.db)

        module = module_model.get_by_id(module_id)
        if not module:
            return None

        materials = material_model.get_by_module(module_id)

        result = {
            'module': module.to_dict(),
            'materials': []
        }

        # Если передан user_id, добавляем информацию о прогрессе
        if user_id and materials:
            material_progress_model = MaterialProgress(self.db)
            completed_materials = material_progress_model.get_completed_materials(user_id, module_id)

            for material in materials:
                material_dict = material.to_dict()
                material_dict['completed'] = material.id in completed_materials
                result['materials'].append(material_dict)
        else:
            result['materials'] = [material.to_dict() for material in materials]

        return result

    def start_module_learning(self, user_id: str, module_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Начать изучение модуля"""
        module_model = Module(self.db)
        progress_module_model = ProgressModule(self.db)
        progress_course_model = ProgressCourse(self.db)

        # Проверяем, существует ли модуль
        module = module_model.get_by_id(module_id)
        if not module:
            return False, "Модуль не найден", None

        # Получаем прогресс по курсу
        progress = progress_course_model.get_by_user_and_course(user_id, module.course_id)
        if not progress:
            return False, "Вы не записаны на этот курс", None

        # Проверяем, существует ли уже прогресс по модулю
        existing_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module_id)

        if existing_progress:
            # Обновляем статус на "в процессе", если еще не начат
            if existing_progress.status == 'not_started':
                update_data = {
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat()
                }
                progress_module_model.update(existing_progress.id, update_data)
                existing_progress = progress_module_model.get_by_id(existing_progress.id)

            return True, "Изучение модуля начато", existing_progress.to_dict()
        else:
            # Создаем новую запись о прогрессе
            progress_data = {
                "enrollment_id": progress.id,
                "module_id": module_id,
                "status": "in_progress",
                "progress_percent": 0.0,
                "started_at": datetime.now().isoformat()
            }

            new_progress = progress_module_model.create(progress_data)
            return True, "Изучение модуля начато", new_progress.to_dict()

    def mark_material_completed(self, user_id: str, material_id: str) -> Tuple[bool, str]:
        """Отметить материал как изученный"""
        material_model = LearningMaterial(self.db)
        module_model = Module(self.db)
        progress_module_model = ProgressModule(self.db)
        progress_course_model = ProgressCourse(self.db)
        material_progress_model = MaterialProgress(self.db)

        # Получаем материал и его модуль
        material = material_model.get_by_id(material_id)
        if not material:
            return False, "Материал не найден"

        module = module_model.get_by_id(material.module_id)
        if not module:
            return False, "Модуль не найден"

        # Получаем прогресс по курсу
        progress = progress_course_model.get_by_user_and_course(user_id, module.course_id)
        if not progress:
            return False, "Вы не записаны на этот курс"

        # Получаем прогресс по модулю
        module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
        if not module_progress:
            return False, "Модуль еще не начат"

        # Создаем или обновляем запись о прогрессе материала
        material_progress = material_progress_model.get_by_user_and_material(user_id, material_id)

        if material_progress:
            # Если материал уже изучен
            if material_progress.status == 'completed':
                return True, "Материал уже изучен"

            # Обновляем статус материала
            update_data = {
                "status": "completed",
                "completed_at": datetime.now().isoformat()
            }
            material_progress_model.update(material_progress.id, update_data)
        else:
            # Создаем новую запись о прогрессе материала
            progress_data = {
                "user_id": user_id,
                "material_id": material_id,
                "module_id": material.module_id,
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "time_spent_sec": 0  # Можно добавить логику отслеживания времени
            }
            material_progress_model.create(progress_data)

        # Обновляем прогресс модуля на основе изученных материалов
        self._update_module_progress_from_materials(user_id, module.id, progress.id)

        return True, "Материал отмечен как изученный"

    def _update_module_progress_from_materials(self, user_id: str, module_id: str, enrollment_id: str) -> None:
        """Обновить прогресс модуля на основе изученных материалов"""
        material_progress_model = MaterialProgress(self.db)
        progress_module_model = ProgressModule(self.db)
        material_model = LearningMaterial(self.db)

        # Получаем все материалы модуля
        materials = material_model.get_by_module(module_id)
        total_materials = len(materials)

        if total_materials == 0:
            return

        # Получаем изученные материалы
        completed_materials = material_progress_model.get_completed_materials(user_id, module_id)
        completed_count = len(completed_materials)

        # Рассчитываем процент прогресса
        progress_percent = (completed_count / total_materials) * 100 if total_materials > 0 else 0

        # Получаем или создаем прогресс модуля
        module_progress = progress_module_model.get_by_enrollment_and_module(enrollment_id, module_id)

        update_data = {
            "progress_percent": round(progress_percent, 2)
        }

        # Если все материалы изучены, отмечаем модуль как завершенный
        if progress_percent >= 99.9:
            update_data["status"] = "completed"
            if not module_progress or not module_progress.finished_at:
                update_data["finished_at"] = datetime.now().isoformat()

        if module_progress:
            progress_module_model.update(module_progress.id, update_data)
        else:
            # Создаем новую запись о прогрессе модуля
            progress_data = {
                "enrollment_id": enrollment_id,
                "module_id": module_id,
                "status": "completed" if progress_percent >= 99.9 else "in_progress",
                "progress_percent": round(progress_percent, 2),
                "started_at": datetime.now().isoformat(),
                "finished_at": datetime.now().isoformat() if progress_percent >= 99.9 else None
            }
            progress_module_model.create(progress_data)

        # Обновляем прогресс курса
        self.update_course_progress(enrollment_id)

    def update_course_progress(self, enrollment_id: str) -> bool:
        """Обновление прогресса курса на основе прогресса по модулям"""
        progress_course_model = ProgressCourse(self.db)
        progress_module_model = ProgressModule(self.db)
        module_model = Module(self.db)

        # Получаем прогресс по курсу
        progress = progress_course_model.get_by_id(enrollment_id)
        if not progress:
            return False

        # Получаем все модули курса
        modules = module_model.get_by_course(progress.course_id)
        total_modules = len(modules)

        if total_modules == 0:
            return False

        # Получаем прогресс по всем модулям
        total_progress = 0
        completed_modules = 0

        for module in modules:
            module_progress = progress_module_model.get_by_enrollment_and_module(enrollment_id, module.id)
            if module_progress:
                total_progress += module_progress.progress_percent
                if module_progress.status == 'completed':
                    completed_modules += 1

        # Рассчитываем средний прогресс
        avg_progress = total_progress / total_modules if total_modules > 0 else 0

        # Обновляем прогресс курса
        update_data = {
            "progress_percent": round(avg_progress, 2)
        }

        # Если все модули завершены, отмечаем курс как завершенный
        if completed_modules == total_modules and total_modules > 0:
            update_data["status"] = "completed"
            update_data["finished_at"] = datetime.now().isoformat()
            # Устанавливаем финальную оценку
            update_data["final_score"] = self.calculate_final_score(progress.user_id, progress.course_id)

        progress_course_model.update(progress.id, update_data)

        return True

    def calculate_final_score(self, user_id: str, course_id: str) -> float:
        """Рассчитать финальную оценку за курс на основе тестов"""
        test_model = Test(self.db)
        test_result_model = TestResult(self.db)
        module_model = Module(self.db)

        # Получаем все модули курса
        modules = module_model.get_by_course(course_id)

        total_weight = 0
        weighted_score = 0

        for module in modules:
            # Получаем тесты модуля
            tests = test_model.get_by_module(module.id)

            for test in tests:
                # Получаем лучший результат пользователя по тесту
                results = test_result_model.get_by_user_and_test(user_id, test.id)
                if results:
                    best_result = max(results, key=lambda x: x.score)
                    test_weight = 1  # Можно настроить веса
                    total_weight += test_weight
                    weighted_score += (best_result.score / best_result.max_score) * 100 * test_weight

        if total_weight > 0:
            return round(weighted_score / total_weight, 2)
        return 0.0

    def get_next_module(self, user_id: str, course_id: str, current_module_id: str = None) -> Optional[Dict[str, Any]]:
        """Получить следующий модуль для изучения"""
        module_model = Module(self.db)
        progress_course_model = ProgressCourse(self.db)
        progress_module_model = ProgressModule(self.db)

        # Получаем прогресс по курсу
        progress = progress_course_model.get_by_user_and_course(user_id, course_id)
        if not progress:
            return None

        # Получаем все модули курса в порядке их следования
        modules = module_model.get_by_course(course_id)
        modules.sort(key=lambda x: x.module_order)

        if current_module_id:
            # Находим текущий модуль
            current_index = next((i for i, m in enumerate(modules) if m.id == current_module_id), -1)
            if current_index >= 0 and current_index < len(modules) - 1:
                next_module = modules[current_index + 1]

                # Проверяем, начат ли следующий модуль
                next_progress = progress_module_model.get_by_enrollment_and_module(progress.id, next_module.id)
                return {
                    'module': next_module.to_dict(),
                    'progress': next_progress.to_dict() if next_progress else None
                }
        else:
            # Находим первый незавершенный модуль
            for module in modules:
                module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)
                if not module_progress or module_progress.status != 'completed':
                    return {
                        'module': module.to_dict(),
                        'progress': module_progress.to_dict() if module_progress else None
                    }

        return None

    def get_course_learning_path(self, user_id: str, course_id: str) -> List[Dict[str, Any]]:
        """Получить полный путь обучения по курсу"""
        module_model = Module(self.db)
        progress_course_model = ProgressCourse(self.db)
        progress_module_model = ProgressModule(self.db)
        material_model = LearningMaterial(self.db)
        test_model = Test(self.db)
        material_progress_model = MaterialProgress(self.db)

        # Получаем прогресс по курсу
        progress = progress_course_model.get_by_user_and_course(user_id, course_id)
        if not progress:
            return []

        # Получаем все модули курса
        modules = module_model.get_by_course(course_id)
        modules.sort(key=lambda x: x.module_order)

        learning_path = []

        for module in modules:
            # Получаем прогресс по модулю
            module_progress = progress_module_model.get_by_enrollment_and_module(progress.id, module.id)

            # Получаем материалы модуля
            materials = material_model.get_by_module(module.id)

            # Добавляем информацию о прогрессе материалов
            completed_materials = material_progress_model.get_completed_materials(user_id, module.id)
            materials_data = []

            for material in materials:
                material_dict = material.to_dict()
                material_dict['completed'] = material.id in completed_materials
                materials_data.append(material_dict)

            # Получаем тесты модуля
            tests = test_model.get_by_module(module.id)

            learning_path.append({
                'module': module.to_dict(),
                'progress': module_progress.to_dict() if module_progress else None,
                'materials': materials_data,
                'tests': [test.to_dict() for test in tests]
            })

        return learning_path

    def get_course_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """Получить все модули курса"""
        module_model = Module(self.db)
        modules = module_model.get_by_course(course_id)
        return [module.to_dict() for module in modules] if modules else []

    def complete_module(self, user_id: str, module_id: str, course_id: str) -> Tuple[bool, str]:
        """Отметить модуль как завершенный"""
        progress_course_model = ProgressCourse(self.db)
        progress_module_model = ProgressModule(self.db)
        module_model = Module(self.db)
        material_progress_model = MaterialProgress(self.db)
        material_model = LearningMaterial(self.db)

        # Получаем прогресс курса
        progress_course = progress_course_model.get_by_user_and_course(user_id, course_id)
        if not progress_course:
            return False, "Вы не записаны на этот курс"

        # Получаем все материалы модуля
        materials = material_model.get_by_module(module_id)

        # Отмечаем все материалы как изученные
        for material in materials:
            material_progress = material_progress_model.get_by_user_and_material(user_id, material.id)
            if not material_progress:
                progress_data = {
                    "user_id": user_id,
                    "material_id": material.id,
                    "module_id": module_id,
                    "status": "completed",
                    "completed_at": datetime.now().isoformat()
                }
                material_progress_model.create(progress_data)

        # Получаем или создаем прогресс модуля
        module_progress = progress_module_model.get_by_enrollment_and_module(progress_course.id, module_id)

        if module_progress:
            # Обновляем прогресс модуля
            update_data = {
                'status': 'completed',
                'progress_percent': 100.0,
                'finished_at': datetime.now().isoformat()
            }
            success = progress_module_model.update(module_progress.id, update_data) is not None
        else:
            # Создаем прогресс модуля
            module_progress_data = {
                'enrollment_id': progress_course.id,
                'module_id': module_id,
                'status': 'completed',
                'progress_percent': 100.0,
                'started_at': datetime.now().isoformat(),
                'finished_at': datetime.now().isoformat()
            }
            success = progress_module_model.create(module_progress_data) is not None

        if success:
            # Обновляем прогресс курса
            progress_course_model.update_progress_percent(progress_course.id)
            return True, "Модуль отмечен как завершенный"
        else:
            return False, "Ошибка при завершении модуля"

    def get_user_material_progress(self, user_id: str, module_id: str) -> Dict[str, Any]:
        """Получить прогресс пользователя по материалам модуля"""
        material_progress_model = MaterialProgress(self.db)
        material_model = LearningMaterial(self.db)

        # Получаем все материалы модуля
        materials = material_model.get_by_module(module_id)

        # Получаем изученные материалы
        completed_materials = material_progress_model.get_completed_materials(user_id, module_id)

        return {
            'total_materials': len(materials),
            'completed_materials': len(completed_materials),
            'progress_percent': (len(completed_materials) / len(materials) * 100) if materials else 0,
            'completed_ids': completed_materials
        }