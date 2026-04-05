import streamlit as st
import pandas as pd
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from src.model import OpinionModel
from src.database import Database
from dotenv import load_dotenv

# .env файлындағы айнымалыларды жүйелік ортаға жүктейді
load_dotenv()




# Инициализация Базы Данных
db = Database()

st.set_page_config(page_title="Студенттер пікірі", page_icon="🎓", layout="wide")

st.title("📊 Студенттердің пікірін талдау дашборды")
st.markdown("Бұл жүйе әлеуметтік желілердегі және сауалнамалардағы студенттердің пікірлерін Жасанды Интеллект арқылы талдайды.")

# --- БҮЙІРЛІК ПАНЕЛЬ (SIDEBAR) ---
st.sidebar.header("⚙️ Дереккөзді таңдау")

# 1. Загрузка файла (Google Forms)
st.sidebar.subheader("📂 Сауалнаманы жүктеу (CSV)")
uploaded_file = st.sidebar.file_uploader("Google Forms нәтижесін жүктеңіз", type=['csv'])

if uploaded_file is not None:
    raw_df = pd.read_csv(uploaded_file, encoding='utf-8')
    st.sidebar.success("✅ Файл сәтті жүктелді!")
    
    if 'text' not in raw_df.columns:
        st.sidebar.error("Қате: Файлда 'text' бағаны табылған жоқ!")
    else:
        if st.sidebar.button("🚀 ИИ арқылы талдау (Анализ)"):
            ai_model = OpinionModel(os.getenv("DASHBOARD_GEMINI_KEY"), provider="gemini")
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            
            for i, row in raw_df.iterrows():
                status_text.text(f"Талдануда: {i+1} / {len(raw_df)}")
                result = ai_model.analyze(str(row['text']))
                
                sentiment = result.iloc[0]
                topic = result.iloc[1]
                summary = result.iloc[2] if len(result) > 2 else "Мазмұн жоқ"
                
                # Достаем дату и имя, если они есть, иначе ставим текущие
                date_val = str(row['date']) if 'date' in raw_df.columns else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                user_val = str(row['username']) if 'username' in raw_df.columns else "Студент"
                
                # САМОЕ ВАЖНОЕ: Сохраняем в Базу Данных! Источник - google_forms
                db.insert_opinion(date_val, user_val, str(row['text']), sentiment, topic, summary, "google_forms")
                
                progress_bar.progress((i + 1) / len(raw_df))
                
            st.sidebar.success("🎉 Талдау толық аяқталды және Базаға сақталды!")
            # Перезагружаем страницу, чтобы обновить графики
            st.rerun()

# 2. Песочница (Sandbox)
st.sidebar.markdown("---")
st.sidebar.subheader("✍️ Мәтінді қолмен тексеру (Sandbox)")
manual_text = st.sidebar.text_area("Студенттің пікірін осында жазыңыз:")

if st.sidebar.button("Талдау (Sandbox)"):
    if manual_text:
        with st.spinner("ИИ талдап жатыр... ⏳"):
            try:
                ai_model = OpinionModel(os.getenv("DASHBOARD_GEMINI_KEY"), provider="gemini")
                result = ai_model.analyze(manual_text)
                
                sentiment = result.iloc[0]
                topic = result.iloc[1]
                summary = result.iloc[2] if len(result) > 2 else "Мазмұн жоқ"
                
                # СОХРАНЯЕМ ПЕСОЧНИЦУ В БАЗУ! Источник - sandbox
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.insert_opinion(current_time, "Қолмен енгізу (Sandbox)", manual_text, sentiment, topic, summary, "sandbox")
                
                if sentiment == 'Positive':
                    st.sidebar.success(f"✅ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                elif sentiment == 'Negative':
                    st.sidebar.error(f"❌ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                else:
                    st.sidebar.info(f"➖ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                
                # Обновляем интерфейс
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.sidebar.error("API шектеуі немесе қате кетті.")
    else:
        st.sidebar.warning("Мәтінді енгізіңіз!")

# 3. Telegram Парсер (Web Scraping)
st.sidebar.markdown("---")
st.sidebar.subheader("✈️ Telegram-нан жүктеу")
tg_channel = st.sidebar.text_input("Канал сілтемесі (мыс: kaznu_kz):", value="kaznu_kz")
tg_limit = st.sidebar.number_input("Қанша хабарлама?", min_value=1, max_value=50, value=5)

if st.sidebar.button("🚀 Парсерді іске қосу"):
    if tg_channel:
        # Пайдаланушы қалай жазса да (сілтемемен немесе @ арқылы), оны тазалап аламыз
        clean_channel = tg_channel.replace('https://', '').replace('t.me/', '').replace('@', '').strip()
        url = f"https://t.me/s/{clean_channel}"
        
        with st.spinner(f"@{clean_channel} каналынан деректер жиналуда... ⏳"):
            try:
               # 1. Браузердің маскасымен кіреміз!
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 2. HTML ішінен хабарлама мәтіндерін іздейміз
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                
                if not messages:
                    st.sidebar.error("Бұл канал жабық немесе қате жазылған (t.me/s/ жұмыс істемейді).")
                else:
                    # Тек соңғы N хабарламаны аламыз
                    recent_messages = messages[-int(tg_limit):]
                    
                    progress_bar = st.sidebar.progress(0)
                    status_text = st.sidebar.empty()
                    
                    ai_model = OpinionModel(os.getenv("DASHBOARD_GEMINI_KEY"), provider="gemini")
                    success_count = 0
                    
                    # 3. Әр хабарламаны ИИ арқылы талдап, Базаға сақтаймыз
                    for i, msg in enumerate(recent_messages):
                        text = msg.get_text(separator=' ', strip=True)
                        
                        # Өте қысқа немесе бос хабарламаларды өткізіп жібереміз
                        if len(text) > 10:
                            status_text.text(f"Талдануда: {i+1} / {len(recent_messages)}")
                            
                            result = ai_model.analyze(text)
                            sentiment = result.iloc[0]
                            topic = result.iloc[1]
                            summary = result.iloc[2] if len(result) > 2 else "Мазмұн жоқ"
                            
                            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            db.insert_opinion(current_time, f"@{clean_channel}", text, sentiment, topic, summary, "telegram")
                            success_count += 1
                            
                        progress_bar.progress((i + 1) / len(recent_messages))
                    
                    st.sidebar.success(f"✅ {success_count} хабарлама алынып, базаға сақталды!")
                    time.sleep(2)
                    st.rerun() # Бетті жаңартып, кестені көрсетеміз
                    
            except Exception as e:
                st.sidebar.error(f"Қате кетті: {e}")
    else:
        st.sidebar.warning("Каналдың атын жазыңыз!")
# --- НЕГІЗГІ ДЕРЕКТЕРДІ ОҚУ ЖӘНЕ КӨРСЕТУ ---
# Теперь мы просто берем всё из Базы Данных! Никаких CSV.
df = db.get_all_df()

# --- ИНТЕРФЕЙС ЖӘНЕ ГРАФИКТЕР ---
if df.empty:
    st.info("⚠️ Деректер табылған жоқ. База бос.")
else:
    st.subheader("📈 Жалпы көрсеткіштер")
    total_comments = len(df)
    
    pos_count = len(df[df['sentiment'] == 'Positive'])
    neg_count = len(df[df['sentiment'] == 'Negative'])
    neu_count = len(df[df['sentiment'] == 'Neutral'])
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Барлық пікірлер", total_comments)
    col2.metric("✅ Позитивті", pos_count)
    col3.metric("❌ Негативті", neg_count)
    col4.metric("➖ Бейтарап", neu_count)
    
    st.divider()

    st.subheader("🔥 Ең көп талқыланатын 3 тақырып")
    valid_topics = df[~df['topic'].isin(['Қате', 'Жалпы (Общее)', 'Жалпы', 'Error', 'Күтіңіз', 'Мәтін жоқ'])]
    top_topics = valid_topics['topic'].value_counts().head(3)
    
    if not top_topics.empty:
        t_col1, t_col2, t_col3 = st.columns(3)
        cols = [t_col1, t_col2, t_col3]
        for i, (topic, count) in enumerate(top_topics.items()):
            cols[i].info(f"**{i+1}. {topic}** \n\n Пікірлер саны: {count}")
    else:
        st.write("Әзірге нақты тақырыптар анықталмады.")
    
    st.divider()

    st.subheader("📊 Тональділік көрінісі")
    chart_data = pd.DataFrame({
        'Тональділік': ['Позитивті', 'Негативті', 'Бейтарап'],
        'Саны': [pos_count, neg_count, neu_count]
    }).set_index('Тональділік')
    st.bar_chart(chart_data, color="#4CAF50")

    # ТАБЛИЦА
    st.subheader("📝 Пікірлер тізімі")
    # Красиво выводим нужные колонки, включая источник (source)
    display_df = df[['id', 'date', 'username', 'text', 'sentiment', 'topic', 'summary', 'source']]
    st.dataframe(display_df)