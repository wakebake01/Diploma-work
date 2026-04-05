import asyncio
from telethon.sync import TelegramClient
import pandas as pd
from datetime import datetime, timedelta, timezone

class TelegramParser:
    def __init__(self, api_id, api_hash, session_name='diploma_session'):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name

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
            # Кешегі күнді анықтау
            today = datetime.now(timezone.utc).date()
            target_date = today - timedelta(days=days_ago)
            
            print(f"\n📱 Telegram-нан деректер жинау басталды ({target_chat})...")
            print(f"📅 Іздеу күні: {target_date} (күнгі пікірлер)")
            
            messages_list = []
            
            with TelegramClient(self.session_name, self.api_id, self.api_hash, loop=loop) as client:
                # Чат тарихын оқу (көп хабарламаны қараймыз, бірақ тек кешегіні аламыз)
                for message in client.iter_messages(target_chat, limit=300):
                    if not message.date:
                        continue
                        
                    msg_date = message.date.date()
                    
                    # Егер хабарлама бүгінгі болса - өткізіп жібереміз
                    if msg_date > target_date:
                        continue
                    
                    # Егер хабарлама алдыңғы күндерге (мыс: 2 күн бұрын) кетіп қалса - тоқтатамыз
                    if msg_date < target_date:
                        break
                        
                    # Егер дәл кешегі күн болса және мәтін болса
                    if msg_date == target_date and message.text and len(message.text.strip()) > 5:
                        messages_list.append({
                            'date': message.date,
                            'text': message.text,
                            'username': str(message.sender_id)
                        })
                        
                        # Керек мөлшерге жетсек, тоқтаймыз
                        if len(messages_list) >= limit:
                            break
                            
            print(f"✅ {target_date} күніне {len(messages_list)} хабарлама сәтті жиналды!")
            
            df = pd.DataFrame(messages_list)
            if df.empty:
                print("Бұл күні ешқандай мәтін жазылмаған.")
                return pd.DataFrame(columns=['date', 'text', 'username'])
                
            return df

        except Exception as e:
            print(f"Telegram-нан жинау кезінде қате кетті: {e}")
            return pd.DataFrame(columns=['date', 'text', 'username'])