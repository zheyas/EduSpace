# database/database.py
import sqlite3
import os


class Database:
    """Класс для управления подключением к базе данных"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, 'database', 'educational_platform.db')

        self.db_path = db_path
        self.connection = None
        self._init_db()

    def _init_db(self):
        """Инициализация базы данных (создание таблиц при необходимости)"""
        conn = self.get_connection()
        conn.close()

    def get_connection(self):
        """Получение подключения к базе данных"""
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False):
        """Выполнение SQL запроса"""
        conn = self.get_connection()
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

    def execute_many(self, query: str, params_list: list):
        """Выполнение множественных запросов"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.executemany(query, params_list)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e

    def close(self):
        """Закрытие соединения"""
        if self.connection:
            self.connection.close()
            self.connection = None