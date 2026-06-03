import pandas as pd
import time
import json
from google import genai
from google.genai import types # Жаңа SDK үшін конфигурация модулі

class OpinionModel:
    def __init__(self, api_key, provider="gemini"):
        """
        api_key: .env файлынан алынған Google API кілті
        provider: үйлесімділік үшін қалдырылған параметр
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-3.5-flash'

    def _clean_json_string(self, raw_text):
        """ИИ қайтарған жауаптан Markdown белгілерін тазарту"""
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
            
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        return cleaned.strip()

    # === ЖАҢА ҚОСЫЛҒАН БЛОК: ПАКЕТТІК ӨҢДЕУ (BATCHING) ===
    def analyze_batch(self, texts):
        """
        Бірнеше мәтінді бір пакетпен талдау (Batch Processing). 
        Токендерді және уақытты үнемдеуге арналған.
        """
        if not texts:
            return []

        formatted_list = "\n".join([f"{i+1}. {t}" for i, t in enumerate(texts)])
        
        batch_prompt = f"""
        Сен — студенттердің пікірін талдайтын сарапшысың. 
        Төмендегі хабарламалар тізімін талдап, нәтижені ТЕК қана JSON массиві (list of objects) форматында қайтар.
        Әр объектіде келесі өрістер болсын:
        - "sentiment": "Positive", "Negative" немесе "Neutral"
        - "topic": "Оқу", "Инфрақұрылым", "Асхана", "Мамандық", "Жүйе", "Жылу", "Кітапхана", "Деканат" сияқты 1 сөзбен тақырып
        - "summary": "Пікірдің қысқаша мазмұны қазақ тілінде (1 сөйлем)"

        Мәтіндер тізімі:
        {formatted_list}
        """

        try:
            print(f"Пакеттік талдау: {len(texts)} хабарлама жіберілуде...")
            time.sleep(2) 
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=batch_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            # Тазартылған мәтінді JSON-ға айналдыру
            clean_text = self._clean_json_string(response.text)
            return json.loads(clean_text)
                    
        except Exception as e:
            print(f"[Batch Gemini Error]: {e}")
            return None

    # === ЕСКІ БЛОК: ЖЕКЕ ХАБАРЛАМА ӨҢДЕУ (SANDBOX ҮШІН) ===
    def analyze(self, text):
        """
        Мәтінді талдау және нәтижені JSON форматында қайтару.
        """
        if not text or pd.isna(text) or len(str(text).strip()) < 5:
            return pd.Series(["Neutral", "Жалпы", "Талдауға мәтін жеткіліксіз"])
            
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
            print("Gemini API лимитін сақтау үшін күтеміз...")
            time.sleep(2) 
                
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            clean_text = self._clean_json_string(response.text)
            res_data = json.loads(clean_text)
            
            sentiment = res_data.get("sentiment", "Neutral").strip()
            topic = res_data.get("topic", "Жалпы").strip()
            summary = res_data.get("summary", "Мазмұны анықталмады").strip()
            
            return pd.Series([sentiment, topic, summary])
                    
        except Exception as e:
            # ТЕПЕРЬ ОШИБКА НЕ СКРЫВАЕТСЯ: выводится тип ошибки и её описание
            print(f"❌ [Gemini Error]: {type(e).__name__} - {e}")
            return pd.Series(["Neutral", "Белгісіз", "Техникалық өңдеу қатесі"])