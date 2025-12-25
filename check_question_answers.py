# check_data_structure.py
from business_logic.tests import TestService
from database.models import DatabaseConnection, Test, Question, Answer
import sqlite3


def check_test_structure(test_id="TST024"):
    """Проверить структуру данных теста"""
    db = DatabaseConnection("educational_platform.db")

    # Проверяем через модели
    test_model = Test(db)
    question_model = Question(db)
    answer_model = Answer(db)

    print(f"=== Проверка теста {test_id} ===")

    # Получаем тест
    test = test_model.get_by_id(test_id)
    if not test:
        print(f"Тест {test_id} не найден")
        return

    print(f"Тест: {test.title}")
    print(f"Макс. баллов: {getattr(test, 'max_score', 'не указано')}")

    # Получаем вопросы
    questions = question_model.get_by_test(test_id)
    print(f"\nВопросы ({len(questions)}):")

    for i, question in enumerate(questions, 1):
        print(f"\n{i}. {question.text}")
        print(f"   Тип: {question.type}")
        print(f"   Баллы: {getattr(question, 'points', 1)}")

        # Получаем ответы
        answers = answer_model.get_by_question(question.id)
        print(f"   Ответы ({len(answers)}):")

        for j, answer in enumerate(answers, 1):
            correct_mark = "✓" if answer.is_correct else " "
            print(f"     [{correct_mark}] {answer.text} (ID: {answer.id})")


def check_test_results():
    """Проверить результаты тестов"""
    db_path = "educational_platform.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n=== Последние 5 результатов тестов ===")

    cursor.execute('''
        SELECT tr.id, tr.test_id, tr.user_id, tr.score, tr.max_score, 
               tr.finished_at, t.title
        FROM test_results tr
        JOIN tests t ON tr.test_id = t.id
        WHERE tr.finished_at IS NOT NULL
        ORDER BY tr.finished_at DESC
        LIMIT 5
    ''')

    results = cursor.fetchall()

    if not results:
        print("Нет завершенных тестов")
    else:
        for result in results:
            print(f"\nID: {result[0]}")
            print(f"Тест: {result[6]} ({result[1]})")
            print(f"Пользователь: {result[2]}")
            print(f"Баллы: {result[3]}/{result[4]}")
            print(f"Завершен: {result[5]}")

            # Проверяем ответы для этого результата
            cursor.execute('SELECT COUNT(*) FROM user_answers WHERE test_result_id = ?', (result[0],))
            answers_count = cursor.fetchone()[0]
            print(f"Ответов: {answers_count}")

    conn.close()


if __name__ == "__main__":
    check_test_structure()
    check_test_results()