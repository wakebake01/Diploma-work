import asyncio
import time
import pandas as pd
from telethon import TelegramClient, events
from datetime import datetime, timedelta, timezone

# Егер src.processor ішінде clean_text болмаса, осы қарапайым тазартқышты қолданамыз
def simple_clean(text):
    return text.replace('\n', ' ').strip()

class TelegramParser:
    def __init__(self, api_id, api_hash, model=None, db=None, session_name='diploma_session'):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        
        # Жаңа архитектураға қажетті айнымалылар
        self.model = model
        self.db = db
        self.buffer = []
        self.buffer_limit = 10 # 10 хабарлама жиналғанда 1 пакет жіберіледі
        self.last_sync_time = time.time()
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)

    # ==========================================
    # 1. ЕСКІ ФУНКЦИЯ: ТАРИХТЫ ЖҮКТЕУ (POLLING)
    # ==========================================
    def collect_opinions(self, target_chat, days_ago=4, limit=10):
        """
        days_ago=1 : Кешегі күнгі хабарламалар
        days_ago=0 : Бүгінгі хабарламалар
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            today = datetime.now(timezone.utc).date()
            target_date = today - timedelta(days=days_ago)
            
            print(f"\n📱 Telegram-нан тарихты жинау басталды ({target_chat})...")
            messages_list = []
            
            with TelegramClient(self.session_name, self.api_id, self.api_hash, loop=loop) as client:
                for message in client.iter_messages(target_chat, limit=300):
                    if not message.date:
                        continue
                        
                    msg_date = message.date.date()
                    
                    if msg_date > target_date:
                        continue
                    if msg_date < target_date:
                        break
                        
                    if msg_date == target_date and message.text and len(message.text.strip()) > 5:
                        messages_list.append({
                            'date': message.date,
                            'text': message.text,
                            'username': str(message.sender_id)
                        })
                        
                        if len(messages_list) >= limit:
                            break
                            
            print(f"✅ {target_date} күніне {len(messages_list)} хабарлама сәтті жиналды!")
            return pd.DataFrame(messages_list)

        except Exception as e:
            print(f"Telegram-нан жинау кезінде қате кетті: {e}")
            return pd.DataFrame(columns=['date', 'text', 'username'])

    # ==========================================
    # 2. ЖАҢА ФУНКЦИЯЛАР: НАҚТЫ УАҚЫТ ЖӘНЕ ПАКЕТТЕР
    # ==========================================
    async def process_buffer(self):
        """Буфердегі хабарламаларды пакетпен Gemini-ге жіберіп, базаға сақтау"""
        if not self.buffer:
            return

        print(f"\n🔄 Пакеттік талдау басталды: {len(self.buffer)} хабарлама...")
        texts_to_analyze = [m['cleaned'] for m in self.buffer]
        
        try:
            # model.py-дағы жаңа analyze_batch функциясын шақыру
            results = self.model.analyze_batch(texts_to_analyze)
            
            if results:
                for idx, res in enumerate(results):
                    # Әр нәтижені SQLite базасына сақтау
                    self.db.insert_opinion(
                        date_val=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        username=self.buffer[idx]['sender'],
                        text=self.buffer[idx]['raw'],
                        sentiment=res.get('sentiment', 'Neutral'),
                        topic=res.get('topic', 'Жалпы'),
                        summary=res.get('summary', '-'),
                        source='telegram_live'
                    )
                print(f"✅ {len(results)} хабарлама өңделіп, SQLite қорына сақталды.")
        except Exception as e:
            print(f"❌ Пакетті өңдеуде қате кетті: {e}")
            
        # Буферді тазарту және уақытты жаңарту
        self.buffer = [] 
        self.last_sync_time = time.time()

    async def check_timeout(self):
        """Егер хабарламалар баяу келсе, 15 минут сайын буферді мәжбүрлі жіберу"""
        while True:
            await asyncio.sleep(60) # Әр 1 минут сайын тексеру
            # Егер буфер бос емес және соңғы хабарламадан бері 15 минут (900 сек) өтсе
            if self.buffer and (time.time() - self.last_sync_time > 900):
                print("\n⏰ Тайм-аут іске қосылды: Буфердегі хабарламалар өңдеуге жіберілуде...")
                await self.process_buffer()

    async def start_monitoring(self, target_chats):
        """Real-time мониторингті іске қосу (Дашбордтан бөлек фондық режимде жұмыс істейді)"""
        if not self.model or not self.db:
            print("Қате: Мониторинг үшін Model және Database нысандары берілуі керек!")
            return

        print(f"\n🚀 Telegram мониторингі басталды. Нысаналы чаттар: {target_chats}")
        self.last_sync_time = time.time()
        
        # Тайм-аутты бақылайтын фонодық тапсырманы іске қосу
        asyncio.create_task(self.check_timeout())

        # Жаңа хабарлама келгенде орындалатын оқиға
        @self.client.on(events.NewMessage(chats=target_chats))
        async def handler(event):
            self.last_sync_time = time.time()
            raw_text = event.message.message
            
            # Тек ұзындығы 5 символдан асатын хабарламаларды аламыз
            if raw_text and len(raw_text.strip()) > 5:
                # Қажет болса src.processor импортын қолдан, әзірге simple_clean
                cleaned = simple_clean(raw_text) 
                
                # Студенттің атын немесе ID-сін алу
                sender = await event.get_sender()
                username = f"@{sender.username}" if sender and sender.username else f"User_{event.sender_id}"

                self.buffer.append({
                    "raw": raw_text, 
                    "cleaned": cleaned,
                    "sender": username
                })
                print(f"📥 Жаңа хабарлама алынды. Буферде: {len(self.buffer)}/{self.buffer_limit}")

                # Буфер толса - талдауға жібереміз
                if len(self.buffer) >= self.buffer_limit:
                    await self.process_buffer()

        await self.client.start()
        print("Құлаққап киілді 🎧 (Тыңдау процесі жүріп жатыр...) Тоқтату үшін Ctrl+C басыңыз.")
        await self.client.run_until_disconnected()