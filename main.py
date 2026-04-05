from src.processor import clean_text
from src.model import OpinionModel
from src.telegram_parser import TelegramParser
from dotenv import load_dotenv
from src.database import Database # <-- ҚОСЫЛДЫ: Базаға қосылу үшін
import pandas as pd
import os
import time
load_dotenv()



# ГЛАВНЫЙ ПЕРЕКЛЮЧАТЕЛЬ: "telegram" или "mock"
DATA_SOURCE = "telegram"  # Поменяй на "mock" для тестирования

# --- ИИ БАПТАУЛАРЫ (НАСТРОЙКИ ИИ) ---
AI_PROVIDER = "gemini" 

def run_system():
    # Создаем папку data, если её нет
    if not os.path.exists('data'):
        os.makedirs('data')
        
    # Инициализация Базы Данных SQLite
    db = Database()

    # 1. Сбор данных
    print(f"1. Деректерді жинау көзі (Источник данных): {DATA_SOURCE.upper()}")
    if DATA_SOURCE == "telegram":
        tg_scraper = TelegramParser(os.getenv("TG_API_ID"), os.getenv("TG_API_HASH"))
        df = tg_scraper.collect_opinions(os.getenv("TARGET_TG_CHAT"), days_ago=4, limit=10)
        print("1. Телеграмнан пікірлер жинау басталды...")
        
    elif DATA_SOURCE == "mock":
        print("Тестілеу режимі (Mock Data) іске қосылды. Синтетикалық пікірлер жүктелуде...")
        mock_data = [
            {'date': '2026-03-21', 'text': "Асханадағы тамақ өте дәмді, бірақ кезек көп.", 'username': 'student1'},
            {'date': '2026-03-21', 'text': "Жатақхана өте суық, жылу қашан береді?", 'username': 'student2'},
            {'date': '2026-03-21', 'text': "Оқу ақысы тым қымбат, стипендия мүлдем жетпейді.", 'username': 'student3'},
            {'date': '2026-03-21', 'text': "Мұғалімдер өте білімді, сабақтар қызықты өтеді. Рахмет!", 'username': 'student4'},
            {'date': '2026-03-21', 'text': "Кітапханада жаңа кітаптар жоқ, интернет өте нашар.", 'username': 'student5'}
        ]
        df = pd.DataFrame(mock_data)
    else:
        print("Қате: Дұрыс емес дереккөз көрсетілген.")
        return
        
    # 2. Очистка данных (Прямо в памяти)
    print("2. Мәтіндерді тазарту жүріп жатыр...")
    df['cleaned_text'] = df['text'].apply(clean_text)
    if df.empty:
        print("Қате: Талдауға арналған деректер жиналмады. API кілттерін немесе чат атауын тексеріңіз. Бағдарлама тоқтатылды.")
        return
    
    # 3. ИИ Анализ
    print("3. Жасанды интеллект талдауы басталды...")
    if AI_PROVIDER == "gemini":
        ai_model = OpinionModel(os.getenv("GEMINI_KEY"), provider="gemini")
        
    # <-- ИСПРАВЛЕНИЕ ОШИБКИ ЗДЕСЬ -->
    # ИИ қайтаратын 3 мәнді (sentiment, topic, summary) дұрыс қабылдаймыз
    def get_analysis(text):
        result = ai_model.analyze(text)
        # Парсер үшін Выжимка (summary) қажет емес, сондықтан оған сызықша "-" қоямыз
        return pd.Series([result.iloc[0], result.iloc[1], "—"])
        
    df[['sentiment', 'topic', 'summary']] = df['cleaned_text'].apply(get_analysis)
    
    # 4. СОХРАНЕНИЕ В БАЗУ ДАННЫХ SQLite
    print("4. Деректерді SQLite базасына сақтау")
    for index, row in df.iterrows():
        date_val = str(row.get('date', pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")))
        user_val = str(row.get('username', 'Студент'))
        text_val = str(row.get('cleaned_text', ''))
        sentiment_val = str(row.get('sentiment', 'Neutral'))
        topic_val = str(row.get('topic', 'Жалпы'))
        summary_val = str(row.get('summary', '—'))
        
        # Базаға жазамыз (source бағанына DATA_SOURCE жазылады)
        db.insert_opinion(date_val, user_val, text_val, sentiment_val, topic_val, summary_val, DATA_SOURCE)

    # Ескі CSV файлды да сақтай береміз (тарих үшін)
    output_path = "data/final_results.csv"
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"--- Жұмыс аяқталды! Нәтижелер SQLite базасына (opinions.db) және {output_path} файлына сақталды! ---")

if __name__ == "__main__":
    run_system()