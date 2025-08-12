import speech_recognition as sr
import pyttsx3
import spacy
from datetime import datetime
import smtplib
from email.message import EmailMessage
import getpass
import re
import sqlite3
import threading
import requests
import wikipedia
import dateparser
from apscheduler.schedulers.background import BackgroundScheduler
import time
import json
import os

OPENWEATHER_API_KEY = "a1878f1669852018bcb82dae37b52d2a"     
IFTTT_WEBHOOK_KEY = "https://maker.ifttt.com/use/abc123XYZ"
WOLFRAM_APP_ID = "4RQ845QWKT"        
DATABASE_PATH = "assistant_data.db"
engine = pyttsx3.init()
nlp = spacy.load("en_core_web_sm")
recognizer = sr.Recognizer()
scheduler = BackgroundScheduler()
scheduler.start()

conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fired INTEGER DEFAULT 0
)
""")
conn.commit()

def speak(text):
    print("Assistant:", text)
    engine.say(text)
    engine.runAndWait()

def listen(timeout=None, phrase_time_limit=None):
    with sr.Microphone() as source:
        print("Listening...")
        audio = None
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except Exception as e:
            print("Listen error:", e)
            speak("I couldn't hear you. Please try again.")
            return ""
    try:
        text = recognizer.recognize_google(audio)
        print("You:", text)
        return text.lower()
    except Exception as e:
        print("Recognition error:", e)
        speak("Sorry, I didn't catch that.")
        return ""

def normalize_email(spoken):
    if not spoken:
        return ""
    s = spoken.lower().strip()
    s = re.sub(r'\s+at\s+', '@', s)
    s = re.sub(r'\s+dot\s+', '.', s)
    s = s.replace(' underscore ', '_')
    s = s.replace(' dash ', '-')
    s = s.replace(' ', '')
    s = re.sub(r'[^a-z0-9@._\-+]', '', s)
    return s

def send_email_smtp(to_email, subject, body, from_email, from_password):
    msg = EmailMessage()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(from_email, from_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False

def email_flow():
    speak("Please say the recipient's email address.")
    spoken = listen()
    to_email = normalize_email(spoken)
    if not to_email:
        speak("I didn't get a valid recipient. Cancelled.")
        return
    speak(f"I understood {to_email}. What's the subject?")
    subject = listen()
    if not subject:
        speak("No subject detected. Cancelled.")
        return
    speak("What should I say in the email?")
    body = listen()
    if not body:
        speak("No message detected. Cancelled.")
        return
    speak("Type your sender email in the console.")
    from_email = input("Sender email: ").strip()
    speak("Type your email password (input will be hidden).")
    from_password = getpass.getpass("Password (hidden): ")
    speak("Sending email...")
    ok = send_email_smtp(to_email, subject, body, from_email, from_password)
    if ok:
        speak("Email sent successfully.")
    else:
        speak("Failed to send email. Check credentials or network.")

def persist_reminder(text, remind_at_iso):
    created = datetime.utcnow().isoformat()
    cursor.execute("INSERT INTO reminders (text, remind_at, created_at, fired) VALUES (?, ?, ?, 0)",
                   (text, remind_at_iso, created))
    conn.commit()
    return cursor.lastrowid

def reminder_job(rem_id, text):
    speak(f"Reminder: {text}")
    cursor.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (rem_id,))
    conn.commit()

def schedule_existing_reminders():
    cursor.execute("SELECT id, text, remind_at FROM reminders WHERE fired = 0")
    rows = cursor.fetchall()
    for r in rows:
        rem_id, text, remind_at = r
        dt = dateparser.parse(remind_at)
        if dt and dt > datetime.now():
            scheduler.add_job(reminder_job, 'date', run_date=dt, args=[rem_id, text], id=f"rem_{rem_id}")

def set_reminder_flow():
    speak("What would you like to be reminded about?")
    text = listen()
    if not text:
        speak("I didn't catch the reminder text.")
        return
    speak("When should I remind you? You can say 'tomorrow at 9 am' or 'in 2 hours' etc.")
    time_text = listen()
    if not time_text:
        speak("I didn't get the time. Cancelled.")
        return
    dt = dateparser.parse(time_text, settings={'PREFER_DATES_FROM': 'future'})
    if not dt:
        speak("I couldn't understand that time. Please try again in a simpler format.")
        return
    rem_id = persist_reminder(text, dt.isoformat())
    scheduler.add_job(reminder_job, 'date', run_date=dt, args=[rem_id, text], id=f"rem_{rem_id}")
    speak(f"Reminder set for {dt.strftime('%c')}.")

def get_weather_by_city(city):
    if not OPENWEATHER_API_KEY:
        return None, "No API key configured for OpenWeatherMap."
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        desc = data['weather'][0]['description']
        temp = data['main']['temp']
        return {"desc": desc, "temp": temp}, None
    except Exception as e:
        return None, str(e)

def weather_flow():
    speak("Which city's weather would you like to know?")
    city = listen()
    if not city:
        speak("I didn't catch the city name.")
        return
    info, err = get_weather_by_city(city)
    if err:
        speak("Couldn't fetch weather: " + err)
    else:
        speak(f"The current weather in {city} is {info['desc']} with temperature {info['temp']} degrees Celsius.")

def ifttt_trigger(event_name, value1=None, value2=None, value3=None):
    if not IFTTT_WEBHOOK_KEY:
        return False, "IFTTT webhook key not configured."
    url = f"https://maker.ifttt.com/trigger/{event_name}/with/key/{IFTTT_WEBHOOK_KEY}"
    payload = {}
    if value1: payload['value1'] = value1
    if value2: payload['value2'] = value2
    if value3: payload['value3'] = value3
    try:
        r = requests.post(url, json=payload, timeout=6)
        r.raise_for_status()
        return True, None
    except Exception as e:
        return False, str(e)

def smart_home_flow():
    speak("What would you like to do? For example, 'turn on living room light' or 'start coffee'.")
    cmd = listen()
    if not cmd:
        speak("No command detected.")
        return
    event_name = re.sub(r'[^a-z0-9_ ]', '', cmd.lower()).replace(' ', '_')[:50]
    ok, err = ifttt_trigger(event_name, value1=cmd)
    if ok:
        speak("Smart-home command sent to IFTTT.")
    else:
        speak("Failed to trigger IFTTT: " + (err or "unknown"))

def general_knowledge_flow(query_text):
    try:
        summary = wikipedia.summary(query_text, sentences=2, auto_suggest=True)
        speak(summary)
    except Exception as e:
        speak("I couldn't find a concise answer on Wikipedia. Try rephrasing or use WolframAlpha integration.")

def detect_intent(text):
    if not text:
        return "unknown"
    if any(w in text for w in ["hello", "hi", "hey"]):
        return "greet"
    if "time" in text:
        return "time_query"
    if "date" in text:
        return "date_query"
    if "weather" in text:
        return "weather_query"
    if "send email" in text or ("email" in text and "send" in text):
        return "send_email"
    if "remind" in text or "reminder" in text or "set reminder" in text:
        return "set_reminder"
    if "turn on" in text or "turn off" in text or "start" in text or "stop" in text:
        return "smart_home"
    if any(phrase in text for phrase in ["who is", "what is", "tell me about", "search for"]):
        return "general_knowledge"
    if "stop" in text or "exit" in text or "quit" in text:
        return "exit"
    return "unknown"

def main():
    schedule_existing_reminders()
    speak("Assistant ready. Say a command. Say 'stop' to exit.")
    while True:
        user_text = listen()
        if not user_text:
            continue
        intent = detect_intent(user_text)
        print("Intent:", intent)
        if intent == "greet":
            speak("Hello! How can I help you?")
        elif intent == "time_query":
            now = datetime.now().strftime("%H:%M")
            speak(f"The current time is {now}")
        elif intent == "date_query":
            today = datetime.now().strftime("%B %d, %Y")
            speak(f"Today's date is {today}")
        elif intent == "weather_query":
            weather_flow()
        elif intent == "send_email":
            email_flow()
        elif intent == "set_reminder":
            set_reminder_flow()
        elif intent == "smart_home":
            smart_home_flow()
        elif intent == "general_knowledge":
            general_knowledge_flow(user_text)
        elif intent == "exit":
            speak("Goodbye!")
            break
        else:
            speak("Sorry, I didn't understand. Try: 'send email', 'set reminder', 'weather in city', or 'turn on light'.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        scheduler.shutdown()
        conn.close()
        print("Exiting.")
