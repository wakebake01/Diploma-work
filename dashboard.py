import streamlit as st
import pandas as pd
import os
import io
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
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
st.sidebar.header("⚙️ Басқару және Сүзгілеу")

# 0. Автоматты жаңарту (Real-time)
auto_update = st.sidebar.toggle("🔄 Автоматты жаңарту (10 сек)", value=False)

# 1. КҮНДЕР БОЙЫНША СҮЗГІ (ФИЛЬТР ПО ДАТАМ)
st.sidebar.subheader("📅 Уақыт аралығы")
all_df = db.get_all_df()

if not all_df.empty:
    # Датаны форматтау (аралас форматтар мен уақыт белдеулерін біріктіру үшін)
    all_df['date_only'] = pd.to_datetime(all_df['date'], format='mixed', errors='coerce', utc=True).dt.date
    min_date = all_df['date_only'].min()
    max_date = all_df['date_only'].max()
    
    # Сохраняем выбор в одну переменную-кортеж
    date_selection = st.sidebar.date_input(
        "Күнді таңдаңыз:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    # Проверяем, сколько дат выбрал пользователь
    if len(date_selection) == 2:
        start_date, end_date = date_selection
    else:
        # Если кликнул только один раз, считаем этот день и началом, и концом
        start_date = date_selection[0]
        end_date = date_selection[0]
else:
    start_date, end_date = date.today(), date.today()

st.sidebar.markdown("---")
st.sidebar.header("📥 Дереккөзді таңдау")

# 2. Загрузка файла (Google Forms) - ПАКЕТНАЯ ОБРАБОТКА
st.sidebar.subheader("📂 Сауалнаманы жүктеу (CSV)")
uploaded_file = st.sidebar.file_uploader("Google Forms нәтижесін жүктеңіз", type=['csv'])

if uploaded_file is not None:
    # 1. Файлды тікелей байт форматында оқу (курсорды жоғалтпау үшін)
    raw_bytes = uploaded_file.getvalue()

    # 2. Отказоустойчивое декодирование (қазақша әріптер мен кодировка қателерін болдырмау)
    try:
        text_data = raw_bytes.decode('utf-8-sig') # Жаңа Excel/Google Forms үшін
    except UnicodeDecodeError:
        text_data = raw_bytes.decode('cp1251')    # Ескі Windows жүйелері үшін

    # 3. CSV құрылымындағы қателерді қолмен тазарту
    cleaned_lines = []
    for line in text_data.splitlines():
        if not line.strip():
            continue
            
        # Барлық жолды қоршап тұрған артық тырнақшаларды алып тастау
        clean_line = line.strip().strip('"')
        
        # Мәтін ішіндегі қос тырнақшаларды қалыпты жағдайға келтіру
        clean_line = clean_line.replace('""', '"')
        
        cleaned_lines.append(clean_line)

    # 4. Таза мәтінді қайта жинап, pandas-қа беру
    cleaned_csv = '\n'.join(cleaned_lines)
    raw_df = pd.read_csv(io.StringIO(cleaned_csv), sep=',')
    
    st.sidebar.success("✅ Файл сәтті жүктелді және тазартылды!")
    
    # 5. Бағандарды тексеру және талдау
    if 'text' not in raw_df.columns:
        st.sidebar.error("Қате: Файлда 'text' бағаны табылған жоқ! Баған аттарын тексеріңіз.")
    else:
        if st.sidebar.button("🚀 Пакеттік талдау (Batch)"):
            ai_model = OpinionModel(os.getenv("DASHBOARD_GEMINI_KEY"), provider="gemini")
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            
            # Подготовка данных
            texts = raw_df['text'].dropna().astype(str).tolist()
            dates = raw_df['date'].tolist() if 'date' in raw_df.columns else [datetime.now().strftime("%Y-%m-%d %H:%M:%S")] * len(texts)
            users = raw_df['username'].tolist() if 'username' in raw_df.columns else ["Студент"] * len(texts)
            
            batch_size = 10 # Группируем по 10 сообщений
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i+batch_size]
                status_text.text(f"Талдануда: {i} - {min(i+batch_size, len(texts))} / {len(texts)}")
                
                # Используем новую функцию пакетного анализа
                results = ai_model.analyze_batch(batch_texts)
                
                if results:
                    for idx, res in enumerate(results):
                        # Егер API қайтарған жауаптар саны жіберілген мәтіндерден аз болса, Index қатесін болдырмау үшін қорғаныс
                        if idx >= len(batch_texts):
                            break
                            
                        sentiment = res.get("sentiment", "Neutral")
                        topic = res.get("topic", "Жалпы")
                        summary = res.get("summary", "Мазмұн жоқ")
                        
                        db.insert_opinion(dates[i+idx], users[i+idx], batch_texts[idx], sentiment, topic, summary, "google_forms")
                
                progress_bar.progress(min((i + batch_size) / len(texts), 1.0))
                
            st.sidebar.success("🎉 Пакеттік талдау толық аяқталды!")
            time.sleep(2)
            st.rerun()

# 3. Песочница (Sandbox) - ОДИНОЧНАЯ ОБРАБОТКА
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
                
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.insert_opinion(current_time, "Қолмен енгізу (Sandbox)", manual_text, sentiment, topic, summary, "sandbox")
                
                if sentiment == 'Positive':
                    st.sidebar.success(f"✅ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                elif sentiment == 'Negative':
                    st.sidebar.error(f"❌ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                else:
                    st.sidebar.info(f"➖ **Тональділік:** {sentiment}\n\n🔥 **Тақырып:** {topic}\n\n📝 **Қысқаша мазмұн:** {summary}")
                
                time.sleep(3)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"API қате кетті: {e}")
    else:
        st.sidebar.warning("Мәтінді енгізіңіз!")

# 4. Telegram Парсер (Web Scraping) - ПАКЕТНАЯ ОБРАБОТКА
st.sidebar.markdown("---")
st.sidebar.subheader("✈️ Telegram-нан жүктеу")
tg_channel = st.sidebar.text_input("Канал сілтемесі (мыс: kaznu_kz):", value="kaznu_kz")
tg_limit = st.sidebar.number_input("Қанша хабарлама?", min_value=1, max_value=50, value=10)

if st.sidebar.button("🚀 Парсерді іске қосу"):
    if tg_channel:
        clean_channel = tg_channel.replace('https://', '').replace('t.me/', '').replace('@', '').strip()
        url = f"https://t.me/s/{clean_channel}"
        
        with st.spinner(f"@{clean_channel} каналынан деректер жиналуда... ⏳"):
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message_text')
                
                if not messages:
                    st.sidebar.error("Бұл канал жабық немесе табылмады.")
                else:
                    recent_messages = messages[-int(tg_limit):]
                    
                    # Собираем тексты
                    texts_to_analyze = [msg.get_text(separator=' ', strip=True) for msg in recent_messages if len(msg.get_text(separator=' ', strip=True)) > 10]
                    
                    if not texts_to_analyze:
                        st.sidebar.warning("Талдауға жарамды (ұзын) мәтін табылмады.")
                    else:
                        progress_bar = st.sidebar.progress(0)
                        status_text = st.sidebar.empty()
                        ai_model = OpinionModel(os.getenv("DASHBOARD_GEMINI_KEY"), provider="gemini")
                        
                        batch_size = 10
                        success_count = 0
                        
                        for i in range(0, len(texts_to_analyze), batch_size):
                            batch_texts = texts_to_analyze[i:i+batch_size]
                            status_text.text(f"Талдануда: {i} - {min(i+batch_size, len(texts_to_analyze))} / {len(texts_to_analyze)}")
                            
                            results = ai_model.analyze_batch(batch_texts)
                            
                            if results:
                                for idx, res in enumerate(results):
                                    sentiment = res.get("sentiment", "Neutral")
                                    topic = res.get("topic", "Жалпы")
                                    summary = res.get("summary", "Мазмұн жоқ")
                                    
                                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    db.insert_opinion(current_time, f"@{clean_channel}", batch_texts[idx], sentiment, topic, summary, "telegram")
                                    success_count += 1
                            
                            progress_bar.progress(min((i + batch_size) / len(texts_to_analyze), 1.0))
                        
                        st.sidebar.success(f"✅ {success_count} хабарлама алынып, базаға сақталды!")
                        time.sleep(2)
                        st.rerun()
            except Exception as e:
                st.sidebar.error(f"Қате кетті: {e}")
    else:
        st.sidebar.warning("Каналдың атын жазыңыз!")

# --- НЕГІЗГІ ДЕРЕКТЕРДІ СҮЗГІЛЕУ (ФИЛЬТРАЦИЯ ДАННЫХ ДЛЯ ГРАФИКОВ) ---
if not all_df.empty:
    mask = (all_df['date_only'] >= start_date) & (all_df['date_only'] <= end_date)
    df = all_df.loc[mask]
else:
    df = all_df

# --- ИНТЕРФЕЙС ЖӘНЕ ГРАФИКТЕР ---
if df.empty:
    st.info("⚠️ Таңдалған уақыт аралығында деректер жоқ. Басқа күнді таңдаңыз немесе деректер жүктеңіз.")
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
            if i < 3: # Защита от выхода за пределы колонок
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
    display_df = df[['id', 'date', 'username', 'text', 'sentiment', 'topic', 'summary', 'source']]
    st.dataframe(display_df, use_container_width=True)

# --- АВТОМАТТЫ ЖАҢАРТУ ЛОГИКАСЫ ---
if auto_update:
    time.sleep(10) # 10 секунд сайын қайта жүктеледі
    st.rerun()