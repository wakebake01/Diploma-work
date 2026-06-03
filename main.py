from src.processor import clean_text
from src.model import OpinionModel
from src.telegram_parser import TelegramParser
from dotenv import load_dotenv
from src.database import Database
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
    
    print(f"1. Деректерді жинау көзі (Источник данных): {DATA_SOURCE.upper()}")
    
    if DATA_SOURCE == "mock":
        print("Тестілеу режимі (Mock Data) іске қосылды. Синтетикалық пікірлер жүктелуде...")
        mock_data = [
            {'date': '2026-03-21', 'text': "Асханадағы тамақ өте дәмді, бірақ кезек көп.", 'username': 'student1'},
            {'date': '2026-03-21', 'text': "Жатақхана өте суық, жылу қашан береді?", 'username': 'student2'},
            {'date': '2026-03-21', 'text': "Оқу ақысы тым қымбат, стипендия мүлдем жетпейді.", 'username': 'student3'},
            {'date': '2026-03-21', 'text': "Мұғалімдер өте білімді, сабақтар қызықты өтеді. Рахмет!", 'username': 'student4'},
            {'date': '2026-03-21', 'text': "Кітапханада жаңа кітаптар жоқ, интернет өте нашар.", 'username': 'student5'}
        ]
        df = pd.DataFrame(mock_data)
        process_and_save(df, db)
        return

    # --- ИНИЦИАЛИЗАЦИЯ ИИ И ПАРСЕРА ---
    tg_scraper = TelegramParser(os.getenv("TG_API_ID"), os.getenv("TG_API_HASH"))
    
    print("🚀 Автосбор жүйесі (Listener) іске қосылды. Тоқтату үшін Ctrl+C басыңыз.")
    print("Жүйе әр 60 секунд сайын жаңа хабарламаларды тексеріп отырады...")

    while True:
        try:
            # 1. Сбор данных 
            df = tg_scraper.collect_opinions(os.getenv("TARGET_TG_CHAT"), days_ago=0, limit=100)
            
            if df is not None and not df.empty:
                process_and_save(df, db)
            else:
                print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] Жаңа хабарламалар табылған жоқ. Күтудеміз...")

            # Тайм-аут: Келесі тексеруге дейін 60 секунд күту
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\n🛑 Жүйе пайдаланушы тарапынан тоқтатылды.")
            break
        except Exception as e:
            print(f"❌ Қате туындады: {e}")
            time.sleep(10) # Қате болған жағдайда 10 секунд күтіп, қайта жалғастыру

def process_and_save(df, db):
    # 1. СҮЗГІ: Базаны тексеру арқылы бұрын өңделген хабарламаларды алып тастау
    # (Бұл жерде DataFrame-ді сүземіз. Тек базада ЖОҚ хабарламалар ғана қалады)
    is_new = df['text'].apply(lambda x: not db.is_text_processed(x))
    new_messages = df[is_new].copy()
    
    total_found = len(df)
    new_count = len(new_messages)
    
    print(f"\n--- ЖАҢА ЦИКЛ БАСТАЛДЫ ({pd.Timestamp.now().strftime('%H:%M:%S')}) ---")
    print(f"📥 Telegram-нан {total_found} хабарлама алынды.")
    
    if new_messages.empty:
        print("ℹ️ Барлық хабарламалар бұрын өңделген (Базада бар). Жаңа циклді күтеміз...")
        print("-" * 40)
        return
        
    print(f"🔍 Оның ішінде {new_count} хабарлама ЖАҢА (базада жоқ). Олар кезекке қойылды.")
    
    # 2. Очистка данных
    new_messages['cleaned_text'] = new_messages['text'].apply(clean_text)
    
    # 3. ИИ Анализ
    ai_model = OpinionModel(os.getenv("GEMINI_KEY"), provider=AI_PROVIDER)
    
    print("🧠 Gemini арқылы талдау басталды (Кезекпен, әр хабарламаға 13 сек үзіліспен):")
    
    results_list = []
    
    # Бұл цикл хабарламаларды бір-бірлеп өңдейді
    for index, row in new_messages.iterrows():
        text_to_analyze = row['cleaned_text']
        
        # Индекстер DataFrame-де шашыраңқы болуы мүмкін, сондықтан тізбекті нөмір үшін len қолданамыз
        current_step = len(results_list) + 1 
        print(f"   ⏳ Талдануда [{current_step}/{new_count}]: '{text_to_analyze[:30]}...'")
        
        try:
            time.sleep(13) 
            
            result = ai_model.analyze(text_to_analyze)
            results_list.append([result.iloc[0], result.iloc[1], "—"])
            print(f"   ✅ Нәтиже: {result.iloc[0]} | {result.iloc[1]}")
            
        except Exception as e:
            print(f"   ❌ Gemini API қатесі: {e}")
            results_list.append(["Neutral", "Қате", "—"])
            
    # Талдау нәтижелерін DataFrame-ге қайта қосу
    results_df = pd.DataFrame(results_list, columns=['sentiment', 'topic', 'summary'], index=new_messages.index)
    new_messages = pd.concat([new_messages, results_df], axis=1)
    
    # 4. СОХРАНЕНИЕ В БАЗУ ДАННЫХ SQLite
    for index, row in new_messages.iterrows():
        date_val = str(row.get('date', pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")))
        user_val = str(row.get('username', 'Студент'))
        text_val = str(row.get('text', ''))
        sentiment_val = str(row.get('sentiment', 'Neutral'))
        topic_val = str(row.get('topic', 'Жалпы'))
        summary_val = str(row.get('summary', '—'))
        
        db.insert_opinion(date_val, user_val, text_val, sentiment_val, topic_val, summary_val, DATA_SOURCE)

    # Тарихи CSV сақтау
    output_path = "data/final_results.csv"
    
    if os.path.exists(output_path):
        new_messages.to_csv(output_path, mode='a', header=False, index=False, encoding='utf-8-sig')
    else:
        new_messages.to_csv(output_path, index=False, encoding='utf-8-sig')
        
    print(f"💾 {new_count} жаңа хабарлама SQLite базасына сәтті сақталды!")
    print("-" * 40)

if __name__ == "__main__":
    run_system()