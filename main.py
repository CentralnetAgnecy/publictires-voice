#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - V4 GEMINI FLASH
Gemini 2.5 Flash (~300ms!) + Polly Gabrielle (fr-CA)
Ultra-fast responses with speech recognition
"""

import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
import requests as http_requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

VOICE = "Polly.Gabrielle-Neural"
LANG = "fr-CA"

SYSTEM_PROMPT = """Tu es Amélie, une agente de support client chaleureuse pour PublicTires.

CONTEXTE:
- PublicTires vend des pneus neufs et usagés en ligne
- Site français: pneuspublic.ca
- Site anglais: publictires.ca
- Installation: Centre Pneus PJ Express, 4100 rue Jarry Est, Montréal
- Téléphone installation: 514-459-4500
- Ramassage GRATUIT pour clients PublicTires

RÈGLES CRITIQUES POUR LA VOIX:
1. Parle en français québécois naturel
2. Maximum 2-3 phrases par réponse
3. JAMAIS d'émojis, de symboles, d'astérisques ou de tirets
4. JAMAIS de listes à puces ou de formatage
5. Pour le site web dis: pneus public point ca
6. Ne dis JAMAIS publictires comme un mot anglais
7. Pour les prix: dirige vers le site web
8. Ne JAMAIS inventer un prix ou une disponibilité
9. Les nombres en lettres: cinq cent, pas 500
10. Pas de parenthèses ni de crochets
11. Sois conversationnelle, comme une vraie personne au téléphone
12. Propose toujours d'aider davantage à la fin"""

conversations = {}
call_logs = []


def clean_for_speech(text):
    """Clean text for natural speech"""
    # Remove emojis
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937\U00010000-\U0010ffff\u2640-\u2642\u2600-\u2B55"
        "\u200d\u23cf\u23e9\u231a\ufe0f\u3030]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)

    # Remove markdown
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s', '', text)
    text = re.sub(r'[-•]\s', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Fix URL pronunciation
    text = text.replace('pneuspublic.ca', 'pneus public point ca')
    text = text.replace('publictires.ca', 'pneus public point ca')
    text = text.replace('PublicTires', 'Pneus Public')
    text = text.replace('publictires', 'pneus public')
    text = text.replace('pneuspublic', 'pneus public')

    # Fix phone
    text = text.replace('514-459-4500', 'cinq-un-quatre, quatre-cinq-neuf, quatre-cinq-zéro-zéro')

    # Remove special chars
    text = re.sub(r'\([^)]*\)', '', text)
    text = text.replace('*', '').replace('#', '').replace('`', '')
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def get_gemini_response(user_message, call_sid="default"):
    """Get ultra-fast response from Gemini 2.5 Flash"""
    if not GEMINI_API_KEY:
        return "Visitez pneus public point ca pour nous contacter."

    if call_sid not in conversations:
        conversations[call_sid] = []

    conversations[call_sid].append({"role": "user", "parts": [{"text": user_message}]})

    # Build conversation with system prompt
    contents = []
    # Add history (last 4 turns)
    for msg in conversations[call_sid][-4:]:
        contents.append(msg)

    try:
        data = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": 100,
                "temperature": 0.7
            }
        }

        response = http_requests.post(
            GEMINI_URL,
            json=data,
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()
            msg = result["candidates"][0]["content"]["parts"][0]["text"]
            msg = clean_for_speech(msg)
            conversations[call_sid].append({"role": "model", "parts": [{"text": msg}]})
            return msg
        else:
            logger.error(f"Gemini error: {response.status_code} - {response.text[:200]}")
            return "Désolé, visitez pneus public point ca ou rappelez-nous."
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return "Visitez pneus public point ca pour nous contacter."


def log_call(call_sid, user_said, ai_said):
    """Log for analysis"""
    call_logs.append({
        "ts": datetime.utcnow().isoformat(),
        "sid": call_sid,
        "user": user_said,
        "ai": ai_said
    })
    logger.info(f"LOG | User: '{user_said}' | AI: '{ai_said[:80]}'")
    if len(call_logs) > 100:
        call_logs.pop(0)


@app.route("/")
def health():
    return "PublicTires Voice Agent V4 ✓ (Gemini 2.5 Flash)"


@app.route("/call", methods=["POST"])
def incoming_call():
    call_sid = request.form.get("CallSid", "unknown")
    conversations[call_sid] = []

    response = VoiceResponse()
    response.say(
        "Bonjour! Bienvenue chez Pneus Public. Comment est-ce que je peux vous aider?",
        voice=VOICE, language=LANG
    )

    response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=10,
        speech_model="phone_call",
        hints="pneus, installation, prix, taille, Michelin, Bridgestone, hiver, été, quatre saisons"
    )

    response.say("Je n'ai pas entendu. Pouvez-vous répéter?", voice=VOICE, language=LANG)
    response.redirect("/call")
    return str(response)


@app.route("/respond", methods=["POST"])
def respond():
    call_sid = request.form.get("CallSid", "unknown")
    speech = request.form.get("SpeechResult", "")
    digits = request.form.get("Digits", "")

    response = VoiceResponse()

    if speech:
        user_input = speech
    elif digits == "1":
        user_input = "Informations sur vos pneus"
    elif digits == "2":
        user_input = "Informations sur l'installation"
    else:
        user_input = speech or ""

    if not user_input:
        response.say("Pouvez-vous répéter?", voice=VOICE, language=LANG)
        response.redirect("/call")
        return str(response)

    # Get Gemini Flash response (FAST!)
    ai_response = get_gemini_response(user_input, call_sid)
    log_call(call_sid, user_input, ai_response)

    response.say(ai_response, voice=VOICE, language=LANG)

    response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=8,
        speech_model="phone_call",
        hints="oui, non, merci, au revoir, pneus, installation, prix"
    )

    response.say("Merci d'avoir appelé Pneus Public. Bonne journée!", voice=VOICE, language=LANG)
    return str(response)


@app.route("/logs")
def get_logs():
    return {"total": len(call_logs), "logs": call_logs[-20:]}


@app.route("/analyze")
def analyze():
    if not call_logs:
        return {"message": "No calls yet"}
    topics = {}
    for log in call_logs:
        u = log["user"].lower()
        if any(w in u for w in ["prix", "combien", "coût"]):
            topics["prix"] = topics.get("prix", 0) + 1
        elif "install" in u:
            topics["installation"] = topics.get("installation", 0) + 1
        elif any(w in u for w in ["pneu", "tire"]):
            topics["pneus"] = topics.get("pneus", 0) + 1
        else:
            topics["autre"] = topics.get("autre", 0) + 1
    return {"total": len(call_logs), "topics": topics}


@app.route("/health")
def health_check():
    return {
        "status": "healthy",
        "ai": "Gemini 2.5 Flash (~300ms)",
        "voice": "Polly.Gabrielle-Neural (fr-CA)",
        "version": "V4",
        "calls_logged": len(call_logs)
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
