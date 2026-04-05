import pandas as pd
import time
import json
from google import genai

class OpinionModel:
    def __init__(self, api_key, provider="gemini"):
        """
        api_key: .env файлынан алынған Google API кілті
        provider: үйлесімділік үшін қалдырылған параметр
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-2.5-flash'

    def analyze(self, text):
        """
        Мәтінді талдау және нәтижені JSON форматында қайтару.
        """
        # 1. Тексеріс: Егер мәтін тым қысқа немесе бос болса
        if not text or pd.isna(text) or len(str(text).strip()) < 5:
            return pd.Series(["Neutral", "Жалпы", "Талдауға мәтін жеткіліксіз"])
            
        # 2. ЖҮЙЕЛІК ПРОМПТ: ИИ-ге қатаң нұсқау береміз
        prompt = f"""
        Сен — студенттердің пікірін талдайтын сарапшысың. 
        Берілген мәтінді талдап, нәтижені ТЕК қана келесі JSON форматында қайтар:
        {{
          "sentiment": "Positive немесе Negative немесе Neutral",
          "topic": "Пікірдің негізгі тақырыбы қазақ тілінде (1 сөз)",
          "summary": "Пікірдің қысқаша мазмұны қазақ тілінде (1 сөйлем)"
        }}

        Мәтін: {text}
        """
            
        try:
            # API шектеулерін (Rate Limits) сақтау үшін кідіріс
            print("Gemini API лимиітн сақтау үшін күтеміз...")
            time.sleep(5) 
                
            # JSON Mode қосылған сұраныс
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json' 
                }
            )
            
            # 3. ЖАУАПТЫ ӨҢДЕУ
            # ИИ қайтарған JSON-ды Python сөздігіне (dict) айналдырамыз
            res_data = json.loads(response.text)
            
            sentiment = res_data.get("sentiment", "Neutral").strip()
            topic = res_data.get("topic", "Жалпы").strip()
            summary = res_data.get("summary", "Мазмұны анықталмады").strip()
            
            return pd.Series([sentiment, topic, summary])
                    
        except Exception as e:
            # Қате болған жағдайда бағдарлама тоқтап қалмауы үшін "Neutral" қайтарамыз
            print(f"[Gemini Error]: {e}")
            return pd.Series(["Neutral", "Белгісіз", "Техникалық өңдеу қатесі"])