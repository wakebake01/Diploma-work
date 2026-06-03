import sqlite3
import pandas as pd
import os

class Database:
    def __init__(self, db_path="data/opinions.db"):
        # Убедимся, что папка data существует
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # Подключаемся к базе. check_same_thread=False нужен для работы внутри Streamlit
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()
        
    def is_text_processed(self, text):
        """Проверяет, существует ли уже такой текст в базе данных (Дубликаттарды сүзу)."""
        try:
            # ТҮЗЕТІЛДІ: Бұрын осы жерде қате болған. Енді әр сұраныс өз курсорын ашады.
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM opinions WHERE text = ?", (text,))
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            print(f"Ошибка проверки базы данных: {e}")
            return False
            
    def create_table(self):
        cursor = self.conn.cursor()
        # Создаем таблицу, если её еще нет. 
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS opinions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                username TEXT,
                text TEXT,
                sentiment TEXT,
                topic TEXT,
                summary TEXT,
                source TEXT
            )
        ''')
        self.conn.commit()

    def insert_opinion(self, date, username, text, sentiment, topic, summary, source):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO opinions (date, username, text, sentiment, topic, summary, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, username, text, sentiment, topic, summary, source))
        self.conn.commit()

    def get_all_df(self):
        # Эта функция будет мгновенно отдавать данные в Дашборд в виде красивой таблицы pandas
        query = "SELECT * FROM opinions ORDER BY id DESC"
        return pd.read_sql_query(query, self.conn)