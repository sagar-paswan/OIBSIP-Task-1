
import speech_recognition as sr
import pyttsx3
import spacy
from datetime import datetime

engine = pyttsx3.init()
nlp = spacy.load("en_core_web_sm")

def speak(text):
    engine.say(text)
    engine.runAndWait()

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = r.listen(source)
    try:
        query = r.recognize_google(audio)
        print(f"User said: {query}")
        return query.lower()
    except Exception as e:
        print("Could not understand audio:", e)
        speak("Sorry, I didn't catch that. Please try again.")
        return ""

def detect_intent(text):
    doc = nlp(text)
    if "hello" in text or "hi" in text:
        return "greet"
    elif "time" in text:
        return "time_query"
    elif "date" in text:
        return "date_query"
    elif "weather" in text:
        return "weather_query"
    elif "email" in text:
        return "send_email"
    elif "reminder" in text:
        return "set_reminder"
    elif "exit" in text or "stop" in text:
        return "exit"
    else:
        return "unknown"

def main():
    speak("Hi! How can I help you today?")
    while True:
        query = listen()
        if not query:
            continue

        intent = detect_intent(query)
        print(f"Detected intent: {intent}")

        if intent == "greet":
            speak("Hello! How are you?")
        elif intent == "time_query":
            now = datetime.now().strftime("%H:%M")
            speak(f"The current time is {now}")
        elif intent == "date_query":
            today = datetime.now().strftime("%B %d, %Y")
            speak(f"Today's date is {today}")
        elif intent == "weather_query":
            speak("Sorry, I can't provide weather updates yet.")
        elif intent == "send_email":
            speak("Email sending is not implemented yet.")
        elif intent == "set_reminder":
            speak("Reminder setting is not implemented yet.")
        elif intent == "exit":
            speak("Goodbye!")
            break
        else:
            speak("I didn't understand that. Could you please repeat?")

if __name__ == "__main__":
    main()
