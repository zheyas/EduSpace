# database/migrations/add_points_to_questions.py
import sqlite3
import os


def add_points_column():
    """Добавляет колонку points в таблицу questions"""
    # Определите правильный путь к вашей базе данных
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, '..', 'educational_platform.db')

    print(f"Путь к БД: {db_path}")

    if not os.path.exists(db_path):
        print(f"База данных не найдена по пути: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем, существует ли колонка points
        cursor.execute("PRAGMA table_info(questions)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'points' not in columns:
            # Добавляем колонку points
            cursor.execute("ALTER TABLE questions ADD COLUMN points INTEGER DEFAULT 1")
            print("Колонка 'points' добавлена в таблицу 'questions'")

            # Обновляем существующие записи
            cursor.execute("UPDATE questions SET points = 1 WHERE points IS NULL")
            print("Существующие записи обновлены")
        else:
            print("Колонка 'points' уже существует")

        conn.commit()
        print("Миграция успешно выполнена")

    except Exception as e:
        print(f"Ошибка при выполнении миграции: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    add_points_column()