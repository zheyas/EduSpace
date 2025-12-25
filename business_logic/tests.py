# business_logic/tests.py
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import sqlite3
from database.models import DatabaseConnection, Test, Question, Answer, TestResult, UserAnswer
from database.models import QuestionType


class TestService:
    def __init__(self, db_path: str = "educational_platform.db"):
        self.db = DatabaseConnection(db_path)
        self.db_path = db_path

    def get_test_with_questions(self, test_id: str, include_correct_answers: bool = False) -> Optional[Dict[str, Any]]:
        """Получить тест с вопросами и ответами (без правильных ответов)"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Получаем информацию о тесте
            cursor.execute('SELECT id, title, description, time_limit, max_score FROM tests WHERE id = ?', (test_id,))
            test_row = cursor.fetchone()

            if not test_row:
                conn.close()
                return None

            test = {
                'id': test_row['id'],
                'title': test_row['title'],
                'description': test_row['description'],
                'time_limit': test_row['time_limit'],
                'max_score': test_row['max_score'],
                'questions': []
            }

            # Получаем вопросы теста
            cursor.execute('''
                SELECT id, text, type, question_order 
                FROM questions 
                WHERE test_id = ? 
                ORDER BY question_order
            ''', (test_id,))

            questions = cursor.fetchall()

            for question_row in questions:
                question_id = question_row['id']
                question = {
                    'id': question_id,
                    'text': question_row['text'],
                    'type': question_row['type'],
                    'question_order': question_row['question_order'],
                    'answers': []
                }

                # Получаем ответы на вопрос
                cursor.execute('''
                    SELECT id, text, is_correct, answer_order 
                    FROM answers 
                    WHERE question_id = ? 
                    ORDER BY answer_order
                ''', (question_id,))

                answers = cursor.fetchall()

                for answer_row in answers:
                    answer = {
                        'id': answer_row['id'],
                        'text': answer_row['text'],
                        'answer_order': answer_row['answer_order']
                    }

                    # Если нужно показывать правильные ответы, добавляем информацию
                    if include_correct_answers:
                        answer['is_correct'] = answer_row['is_correct']

                    question['answers'].append(answer)

                # Если нужно, собираем ID правильных ответов
                if include_correct_answers:
                    correct_ids = [a['id'] for a in question['answers'] if a.get('is_correct') == 1]
                    question['correct_answer_ids'] = correct_ids

                test['questions'].append(question)

            conn.close()
            return test

        except Exception as e:
            print(f"Error in get_test_with_questions: {e}")
            return None


    def calculate_score_for_question(self, question_id: str, user_answers: List[str],
                                     max_score_per_question: float = 1.0) -> Dict[str, Any]:
        """Рассчитать баллы для вопроса с учетом типа вопроса"""
        question_model = Question(self.db)
        answer_model = Answer(self.db)

        question = question_model.get_by_id(question_id)
        if not question:
            return {"score": 0, "is_correct": False, "max_score": max_score_per_question}

        # Получаем все правильные ответы на этот вопрос
        all_answers = answer_model.get_by_question(question_id)
        correct_answers = [answer.id for answer in all_answers if answer.is_correct]
        total_correct = len(correct_answers)

        if question.type == QuestionType.SINGLE.value:
            # Один правильный ответ
            if len(user_answers) > 0:
                user_answer = user_answers[0]
                is_correct = user_answer in correct_answers
                score = max_score_per_question if is_correct else 0
                return {
                    "score": score,
                    "is_correct": is_correct,
                    "max_score": max_score_per_question,
                    "user_answers": user_answers,
                    "correct_answers": correct_answers
                }

        elif question.type == QuestionType.MULTIPLE.value:
            # Несколько правильных ответов - только полный правильный ответ дает баллы
            if not user_answers:
                return {
                    "score": 0,
                    "is_correct": False,
                    "max_score": max_score_per_question,
                    "user_answers": user_answers,
                    "correct_answers": correct_answers
                }

            # Проверяем, все ли правильные ответы выбраны и нет ли неправильных
            user_set = set(user_answers)
            correct_set = set(correct_answers)

            # Все выбранные ответы должны быть правильными
            if user_set == correct_set:  # Точное совпадение
                is_correct = True
                score = max_score_per_question
            else:
                is_correct = False
                score = 0

            return {
                "score": score,
                "is_correct": is_correct,
                "max_score": max_score_per_question,
                "user_answers": user_answers,
                "correct_answers": correct_answers,
                "correct_selected": len(user_set.intersection(correct_set)),
                "total_correct": total_correct
            }

        elif question.type in [QuestionType.OPEN.value, QuestionType.TEXT.value]:
            # Открытые вопросы - требуют проверки преподавателем
            # По умолчанию 0 баллов, пока не проверено
            return {
                "score": 0,
                "is_correct": False,
                "max_score": max_score_per_question,
                "user_answers": user_answers,
                "correct_answers": [],  # Для открытых вопросов нет предопределенных ответов
                "requires_review": True
            }

        return {"score": 0, "is_correct": False, "max_score": max_score_per_question}

    def start_test(self, user_id: str, test_id: str) -> Tuple[bool, str, str]:
        """Начать прохождение теста - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
        try:
            test_result_model = TestResult(self.db)
            test_model = Test(self.db)

            # Получаем тест
            test = test_model.get_by_id(test_id)
            if not test:
                print(f"DEBUG start_test: Тест {test_id} не найден")
                return False, "Тест не найден", ""

            # Генерируем ID результата теста
            import time
            result_id = f"TRS{int(time.time() * 1000)}"
            print(f"DEBUG start_test: Генерация ID: {result_id}")

            # Создаем запись о начале теста
            test_result_data = {
                'id': result_id,
                'test_id': test_id,
                'user_id': user_id,
                'score': 0.0,
                'max_score': test.max_score if hasattr(test, 'max_score') else 100.0,
                'started_at': datetime.now().isoformat(),
                'finished_at': None,
                'duration_sec': 0
            }

            print(f"DEBUG start_test: Создаем результат теста с данными: {test_result_data}")

            result = test_result_model.create(test_result_data)

            if result:
                print(f"DEBUG start_test: Результат теста успешно создан: {result.id}")
                # Проверяем, что результат действительно сохранен в БД
                check_result = test_result_model.get_by_id(result.id)
                if check_result:
                    print(f"DEBUG start_test: Подтверждение: результат найден в БД")
                    return True, "Тест начат", result.id
                else:
                    print(f"DEBUG start_test: ОШИБКА: Результат не найден в БД после создания")
                    return False, "Ошибка сохранения результата теста", ""
            else:
                print(f"DEBUG start_test: Ошибка при создании записи о тесте")
                return False, "Ошибка при создании записи о тесте", ""

        except Exception as e:
            print(f"Ошибка при начале теста: {e}")
            import traceback
            traceback.print_exc()
            return False, "Ошибка при начале теста", ""

    def submit_test_answer(self, test_result_id: str, question_id: str, answer_data: Dict[str, Any]) -> Tuple[
        bool, str]:
        """Отправить ответ на вопрос теста - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
        try:
            user_answer_model = UserAnswer(self.db)
            test_result_model = TestResult(self.db)
            question_model = Question(self.db)

            # Получаем вопрос для определения типа
            question = question_model.get_by_id(question_id)
            if not question:
                return False, "Вопрос не найден"

            # Получаем ответы пользователя для этого вопроса (если уже были)
            existing_answers = user_answer_model.get_by_test_result(test_result_id)
            existing_for_question = [a for a in existing_answers if a.question_id == question_id]

            print(f"DEBUG submit_test_answer: test_result_id={test_result_id}, question_id={question_id}")
            print(f"DEBUG submit_test_answer: существующие ответы: {len(existing_for_question)}")

            # Удаляем существующие ответы на этот вопрос
            for existing in existing_for_question:
                print(f"DEBUG submit_test_answer: удаляем существующий ответ {existing.id}")
                user_answer_model.delete(existing.id)

            # Обрабатываем ответ в зависимости от типа вопроса
            user_answers = []
            is_correct = False

            if question.type == QuestionType.SINGLE.value:
                answer_id = answer_data.get('answer_id')
                print(f"DEBUG submit_test_answer: single answer_id={answer_id}")
                if answer_id:
                    user_answers = [answer_id]

                    # Проверяем правильность ответа
                    from database.models import Answer
                    answer_model = Answer(self.db)
                    answer = answer_model.get_by_id(answer_id)
                    if answer:
                        is_correct = answer.is_correct

                    print(f"DEBUG submit_test_answer: создаем ответ с is_correct={is_correct}")

                    answer_record = {
                        'test_result_id': test_result_id,
                        'question_id': question_id,
                        'answer_id': answer_id,
                        'text_answer': None,
                        'is_correct': is_correct
                    }

                    created = user_answer_model.create(answer_record)
                    if created:
                        print(f"DEBUG submit_test_answer: создан ответ {created.id}")
                    else:
                        print(f"DEBUG submit_test_answer: ошибка создания ответа")

            elif question.type == QuestionType.MULTIPLE.value:
                answer_ids = answer_data.get('answer_ids', [])
                print(f"DEBUG submit_test_answer: multiple answer_ids={answer_ids}")
                if answer_ids:
                    user_answers = answer_ids

                    # Получаем все правильные ответы
                    from database.models import Answer
                    answer_model = Answer(self.db)
                    all_answers = answer_model.get_by_question(question_id)
                    correct_answers = [ans.id for ans in all_answers if ans.is_correct]

                    # Для multiple: ответ считается правильным только если ВСЕ правильные выбраны и НИ ОДНОГО неправильного
                    user_set = set(answer_ids)
                    correct_set = set(correct_answers)
                    is_correct = (user_set == correct_set) and len(user_set) > 0

                    print(f"DEBUG submit_test_answer: correct_answers={correct_answers}, is_correct={is_correct}")

                    # Создаем запись для каждого выбранного ответа
                    for answer_id in answer_ids:
                        # Для каждого отдельного ответа проверяем, правильный ли он
                        individual_correct = answer_id in correct_answers

                        answer_record = {
                            'test_result_id': test_result_id,
                            'question_id': question_id,
                            'answer_id': answer_id,
                            'text_answer': None,
                            'is_correct': is_correct  # Общий результат для вопроса
                        }

                        created = user_answer_model.create(answer_record)
                        if created:
                            print(f"DEBUG submit_test_answer: создан ответ {created.id} для answer_id={answer_id}")
                        else:
                            print(f"DEBUG submit_test_answer: ошибка создания ответа для answer_id={answer_id}")

            elif question.type in [QuestionType.OPEN.value, QuestionType.TEXT.value]:
                text_answer = answer_data.get('text_answer', '')
                print(f"DEBUG submit_test_answer: text_answer length={len(text_answer)}")
                if text_answer:
                    user_answers = [text_answer]
                    # Для открытых вопросов is_correct = False по умолчанию
                    is_correct = False

                    answer_record = {
                        'test_result_id': test_result_id,
                        'question_id': question_id,
                        'answer_id': None,
                        'text_answer': text_answer,
                        'is_correct': is_correct
                    }

                    created = user_answer_model.create(answer_record)
                    if created:
                        print(f"DEBUG submit_test_answer: создан текст ответа {created.id}")
                    else:
                        print(f"DEBUG submit_test_answer: ошибка создания текста ответа")

            return True, "Ответ сохранен"

        except Exception as e:
            print(f"Ошибка при сохранении ответа: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Ошибка при сохранении ответа: {str(e)}"

    def finish_test(self, test_result_id):
        """Завершить тест и рассчитать результат - ИСПРАВЛЕННЫЙ ВАРИАНТ"""
        try:
            test_result_model = TestResult(self.db)
            user_answer_model = UserAnswer(self.db)
            question_model = Question(self.db)
            answer_model = Answer(self.db)

            # Получаем результат теста
            test_result = test_result_model.get_by_id(test_result_id)
            if not test_result:
                print(f"DEBUG finish_test: Результат теста {test_result_id} не найден")
                return False, "Результат теста не найден", None

            print(f"DEBUG finish_test: Найден результат: ID={test_result.id}")

            # Получаем все ответы пользователя для этого теста
            user_answers = user_answer_model.get_by_test_result(test_result_id)
            print(f"DEBUG finish_test: Найдено ответов пользователя: {len(user_answers)}")

            # Получаем вопросы теста
            questions = question_model.get_by_test(test_result.test_id)
            print(f"DEBUG finish_test: Найдено вопросов: {len(questions)}")

            if not questions:
                print(f"DEBUG finish_test: В тесте нет вопросов")
                return False, "В тесте нет вопросов", None

            # Рассчитываем баллы ТОЛЬКО для вопросов с выбором ответа
            total_score = 0
            max_score = 0
            correct_answers_count = 0
            total_autogradable_questions = 0  # Вопросы, которые можно оценить автоматически

            for question in questions:
                question_max_score = getattr(question, 'points', 1)

                # Для открытых вопросов не учитываем в автоматической оценке
                if question.type in ['text', 'open']:
                    print(f"DEBUG finish_test: Вопрос {question.id} - открытый, пропускаем в автоматической оценке")
                    continue

                max_score += question_max_score
                total_autogradable_questions += 1

                # Получаем ответы пользователя на этот вопрос
                user_answers_for_question = [
                    ua for ua in user_answers if ua.question_id == question.id
                ]

                print(
                    f"DEBUG finish_test: Вопрос {question.id}, тип {question.type}, ответов: {len(user_answers_for_question)}")

                # Получаем правильные ответы на вопрос
                correct_answers = answer_model.get_by_question(question.id)
                correct_answer_ids = [ans.id for ans in correct_answers if ans.is_correct]
                print(f"DEBUG finish_test: Правильные ответы: {correct_answer_ids}")

                # Проверяем ответ пользователя
                if question.type == 'single':
                    # Один правильный ответ
                    if user_answers_for_question and user_answers_for_question[0].answer_id:
                        user_answer_id = user_answers_for_question[0].answer_id
                        if user_answer_id in correct_answer_ids:
                            total_score += question_max_score
                            correct_answers_count += 1
                            print(f"DEBUG finish_test: Вопрос {question.id} - ПРАВИЛЬНО")
                            # Отмечаем ответ как правильный
                            user_answer_model.update(user_answers_for_question[0].id, {'is_correct': True})
                        else:
                            print(f"DEBUG finish_test: Вопрос {question.id} - НЕПРАВИЛЬНО")
                            user_answer_model.update(user_answers_for_question[0].id, {'is_correct': False})
                    else:
                        print(f"DEBUG finish_test: Вопрос {question.id} - ОТВЕТ НЕ ДАН")
                        if user_answers_for_question:
                            user_answer_model.update(user_answers_for_question[0].id, {'is_correct': False})

                elif question.type == 'multiple':
                    # Несколько правильных ответов
                    if user_answers_for_question:
                        user_answer_ids = [ua.answer_id for ua in user_answers_for_question if ua.answer_id]

                        # Проверяем полное совпадение (ВСЕ правильные ответы должны быть выбраны)
                        user_set = set(user_answer_ids)
                        correct_set = set(correct_answer_ids)

                        # Для вопросов с множественным выбором проверяем:
                        # 1. Пользователь выбрал ВСЕ правильные ответы
                        # 2. Пользователь НЕ выбрал неправильные ответы
                        if user_set == correct_set and len(user_set) > 0:
                            # Все правильно
                            total_score += question_max_score
                            correct_answers_count += 1
                            print(f"DEBUG finish_test: Вопрос {question.id} - ВСЕ ПРАВИЛЬНО")
                            for ua in user_answers_for_question:
                                user_answer_model.update(ua.id, {'is_correct': True})
                        else:
                            print(f"DEBUG finish_test: Вопрос {question.id} - НЕПОЛНОЕ СОВПАДЕНИЕ")
                            # Отмечаем каждый ответ как правильный/неправильный
                            for ua in user_answers_for_question:
                                is_correct = ua.answer_id in correct_answer_ids
                                user_answer_model.update(ua.id, {'is_correct': is_correct})
                    else:
                        print(f"DEBUG finish_test: Вопрос {question.id} - ОТВЕТЫ НЕ ДАНЫ")

            # Округляем балл
            final_score = round(total_score, 2)

            print(
                f"DEBUG finish_test: Итоговый расчет: балл={final_score}, макс={max_score}, правильных={correct_answers_count}/{total_autogradable_questions}")

            # Обновляем результат теста
            update_data = {
                'score': final_score,
                'max_score': max_score,
                'finished_at': datetime.now().isoformat(),
                'duration_sec': self._calculate_duration(test_result.started_at)
            }

            updated_result = test_result_model.update(test_result_id, update_data)

            if updated_result:
                print(f"DEBUG finish_test: Результат обновлен успешно")
                return True, "Тест завершен успешно", {
                    'score': final_score,
                    'max_score': max_score,
                    'percentage': round((final_score / max_score * 100), 2) if max_score > 0 else 0,
                    'correct_answers': correct_answers_count,
                    'total_questions': total_autogradable_questions,
                    'total_all_questions': len(questions)  # Все вопросы включая открытые
                }
            else:
                print(f"DEBUG finish_test: Ошибка обновления результата")
                return False, "Ошибка при обновлении результата теста", None

        except Exception as e:
            print(f"Ошибка при завершении теста: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Ошибка при завершении теста: {str(e)}", None

    def _calculate_duration(self, started_at):
        """Рассчитать продолжительность теста в секундах"""
        if not started_at:
            return 0

        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))

        now = datetime.now()
        duration = (now - started_at).total_seconds()
        return int(duration)

    def get_test_results_for_student(self, user_id: str) -> List[Dict[str, Any]]:
        """Получить результаты тестов для студента"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT tr.test_id, tr.id as result_id, tr.score, tr.max_score, 
                       tr.finished_at, t.title as test_title, t.description,
                       m.course_id, c.title as course_title
                FROM test_results tr
                JOIN tests t ON tr.test_id = t.id
                JOIN modules m ON t.module_id = m.id
                JOIN courses c ON m.course_id = c.id
                WHERE tr.user_id = ? AND tr.finished_at IS NOT NULL
                ORDER BY tr.finished_at DESC
            ''', (user_id,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'test_id': row['test_id'],
                    'result_id': row['result_id'],
                    'score': round(float(row['score']), 2),
                    'max_score': round(float(row['max_score']), 2),
                    'finished_at': row['finished_at'],
                    'test_title': row['test_title'],
                    'description': row['description'],
                    'course_id': row['course_id'],
                    'course_title': row['course_title'],
                    'percentage': round((float(row['score']) / float(row['max_score'])) * 100, 2) if row[
                                                                                                         'max_score'] and
                                                                                                     row[
                                                                                                         'max_score'] > 0 else 0
                })

            conn.close()
            return results

        except Exception as e:
            print(f"Error in get_test_results_for_student: {e}")
            return []

    def get_test_analytics(self, user_id: str) -> Dict[str, Any]:
        """Получить аналитику тестов для пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Получаем общую статистику
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT test_id) as total_tests_taken,
                    COUNT(*) as total_attempts,
                    AVG(score) as average_score,
                    MAX(score) as best_score,
                    SUM(CASE WHEN score >= (max_score * 0.6) THEN 1 ELSE 0 END) as passed_tests
                FROM test_results 
                WHERE user_id = ? AND finished_at IS NOT NULL
            ''', (user_id,))

            stats_row = cursor.fetchone()

            if stats_row:
                stats = {
                    'total_tests_taken': stats_row['total_tests_taken'] or 0,
                    'total_attempts': stats_row['total_attempts'] or 0,
                    'average_score': round(float(stats_row['average_score'] or 0), 2),
                    'best_score': round(float(stats_row['best_score'] or 0), 2),
                    'passed_tests': stats_row['passed_tests'] or 0
                }
            else:
                stats = {
                    'total_tests_taken': 0,
                    'total_attempts': 0,
                    'average_score': 0,
                    'best_score': 0,
                    'passed_tests': 0
                }

            # Получаем последние результаты
            cursor.execute('''
                SELECT tr.id, tr.test_id, tr.score, tr.max_score, tr.finished_at, t.title
                FROM test_results tr
                JOIN tests t ON tr.test_id = t.id
                WHERE tr.user_id = ? AND tr.finished_at IS NOT NULL
                ORDER BY tr.finished_at DESC
                LIMIT 5
            ''', (user_id,))

            recent_results = []
            for row in cursor.fetchall():
                recent_results.append({
                    'test_id': row['test_id'],
                    'test_title': row['title'],
                    'score': round(float(row['score'] or 0), 2),
                    'max_score': round(float(row['max_score'] or 100), 2),
                    'percentage': round((float(row['score'] or 0) / float(row['max_score'] or 100)) * 100, 2) if row[
                                                                                                                     'max_score'] and
                                                                                                                 row[
                                                                                                                     'max_score'] > 0 else 0,
                    'finished_at': row['finished_at']
                })

            conn.close()

            return {
                'stats': stats,
                'recent_results': recent_results
            }

        except Exception as e:
            print(f"Error in get_test_analytics: {e}")
            return {
                'stats': {
                    'total_tests_taken': 0,
                    'total_attempts': 0,
                    'average_score': 0,
                    'best_score': 0,
                    'passed_tests': 0
                },
                'recent_results': []
            }

    def get_test_with_correct_answers(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Получить тест с вопросами и правильными ответами для отображения результатов"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Получаем информацию о тесте
            cursor.execute('SELECT id, title, description, time_limit, max_score FROM tests WHERE id = ?', (test_id,))
            test_row = cursor.fetchone()

            if not test_row:
                conn.close()
                return None

            test = {
                'id': test_row['id'],
                'title': test_row['title'],
                'description': test_row['description'],
                'time_limit': test_row['time_limit'],
                'max_score': test_row['max_score'],
                'questions': []
            }

            # Получаем вопросы теста
            cursor.execute('''
                SELECT id, text, type, question_order, points
                FROM questions 
                WHERE test_id = ? 
                ORDER BY question_order
            ''', (test_id,))

            questions = cursor.fetchall()

            for question_row in questions:
                question_id = question_row['id']
                question_type = question_row['type']

                question = {
                    'id': question_id,
                    'text': question_row['text'],
                    'type': question_type,
                    'points': question_row['points'] or 1,
                    'question_order': question_row['question_order'],
                    'answers': [],
                    'correct_answer_ids': []  # ID правильных ответов
                }

                # Для вопросов с выбором ответа получаем варианты
                if question_type in ['single', 'multiple']:
                    cursor.execute('''
                        SELECT id, text, is_correct, answer_order 
                        FROM answers 
                        WHERE question_id = ? 
                        ORDER BY answer_order
                    ''', (question_id,))

                    answers = cursor.fetchall()

                    for answer_row in answers:
                        answer = {
                            'id': answer_row['id'],
                            'text': answer_row['text'],
                            'is_correct': bool(answer_row['is_correct']),
                            'answer_order': answer_row['answer_order']
                        }

                        if answer_row['is_correct']:
                            question['correct_answer_ids'].append(answer_row['id'])

                        question['answers'].append(answer)
                else:
                    # Для открытых вопросов нет вариантов ответа
                    question['answers'] = []

                test['questions'].append(question)

            conn.close()
            return test

        except Exception as e:
            print(f"Error in get_test_with_correct_answers: {e}")
            return None
