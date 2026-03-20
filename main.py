#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - V3 Optimized
Claude Sonnet 4 + Polly Gabrielle (fr-CA)
+ Text cleanup (no emoji, proper pronunciation)
+ Call logging for continuous improvement
"""

import os
import re
import json
import logging
from datetime import datetime
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
import requests as http_requests

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
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
4. JAMAIS de listes à puces
5. Pour le site web dis: pneus public point ca (tout en français, mots séparés)
6. Ne dis JAMAIS "publictires" comme un mot anglais. Dis plutôt "pneus public point ca"
7. Pour les prix: dirige vers le site web
8. Ne JAMAIS inventer un prix ou une disponibilité
9. Les nombres en lettres: cinq cent, pas 500
10. Pas de parenthèses ni de crochets
11. Sois conversationnelle, comme une vraie personne au téléphone
12. Propose toujours d'aider davantage à la fin"""

# Conversation memory per call
conversations = {}

# Call logs for improvement
call_logs = []


def clean_for_speech(text):
    """Clean text for natural speech synthesis - remove everything that sounds weird"""
    # Remove emojis
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "\u2640-\u2642"
        "\u2600-\u2B55"
        "\u200d\u23cf\u23e9\u231a\ufe0f\u3030"
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)

    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # *italic*
    text = re.sub(r'#{1,6}\s', '', text)  # headers
    text = re.sub(r'[-•]\s', '', text)  # bullet points
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links

    # Fix URL pronunciation
    text = text.replace('pneuspublic.ca', 'pneus public point ca')
    text = text.replace('publictires.ca', 'pneus public point ca')
    text = text.replace('PublicTires', 'Pneus Public')
    text = text.replace('publictires', 'pneus public')
    text = text.replace('pneuspublic', 'pneus public')

    # Fix phone number pronunciation
    text = text.replace('514-459-4500', 'cinq-un-quatre, quatre-cinq-neuf, quatre-cinq-zéro-zéro')

    # Remove parentheses content that sounds weird
    text = re.sub(r'\([^)]*\)', '', text)

    # Remove special characters
    text = text.replace('*', '')
    text = text.replace('#', '')
    text = text.replace('_', ' ')
    text = text.replace('`', '')

    # Clean extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def get_claude_response(user_message, call_sid="default"):
    """Get response from Claude Sonnet 4"""
    if not ANTHROPIC_API_KEY:
        return "Visitez pneus public point ca pour nous contacter."

    if call_sid not in conversations:
        conversations[call_sid] = []

    conversations[call_sid].append({"role": "user", "content": user_message})
    history = conversations[call_sid][-4:]

    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100,
            "system": SYSTEM_PROMPT,
            "messages": history
        }

        response = http_requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=6
        )

        if response.status_code == 200:
            result = response.json()
            msg = result["content"][0]["text"]
            # Clean for speech BEFORE saving
            msg = clean_for_speech(msg)
            conversations[call_sid].append({"role": "assistant", "content": msg})
            return msg
        else:
            logger.error(f"Claude error: {response.status_code}")
            return "Désolé, visitez pneus public point ca ou rappelez-nous."
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return "Visitez pneus public point ca pour nous contacter."


def log_call(call_sid, user_said, ai_said):
    """Log conversation for analysis and improvement"""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "call_sid": call_sid,
        "user": user_said,
        "ai": ai_said
    }
    call_logs.append(entry)
    logger.info(f"CALL LOG | User: '{user_said}' | AI: '{ai_said[:80]}...'")

    # Keep last 100 logs in memory
    if len(call_logs) > 100:
        call_logs.pop(0)


@app.route("/")
def health():
    return "PublicTires Voice Agent V3 ✓"


@app.route("/call", methods=["POST"])
def incoming_call():
    call_sid = request.form.get("CallSid", "unknown")
    conversations[call_sid] = []

    response = VoiceResponse()
    response.say(
        "Bonjour! Bienvenue chez Pneus Public. Comment est-ce que je peux vous aider?",
        voice=VOICE, language=LANG
    )

    gather = response.gather(
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

    # Get Claude response (already cleaned)
    claude_response = get_claude_response(user_input, call_sid)

    # Log for improvement
    log_call(call_sid, user_input, claude_response)

    # Speak response
    response.say(claude_response, voice=VOICE, language=LANG)

    # Continue conversation
    gather = response.gather(
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


# ==========================================
# MONITORING & IMPROVEMENT ENDPOINTS
# ==========================================

@app.route("/logs", methods=["GET"])
def get_logs():
    """View recent call logs for analysis"""
    return {"total": len(call_logs), "logs": call_logs[-20:]}


@app.route("/analyze", methods=["GET"])
def analyze():
    """Analyze calls and suggest improvements"""
    if not call_logs:
        return {"message": "No calls yet"}

    total = len(call_logs)
    topics = {}
    for log in call_logs:
        user_msg = log["user"].lower()
        if "prix" in user_msg or "combien" in user_msg or "coût" in user_msg:
            topics["prix"] = topics.get("prix", 0) + 1
        elif "install" in user_msg:
            topics["installation"] = topics.get("installation", 0) + 1
        elif "pneu" in user_msg or "tire" in user_msg:
            topics["pneus"] = topics.get("pneus", 0) + 1
        elif "hiver" in user_msg or "neige" in user_msg:
            topics["pneus_hiver"] = topics.get("pneus_hiver", 0) + 1
        else:
            topics["autre"] = topics.get("autre", 0) + 1

    return {
        "total_interactions": total,
        "topics": topics,
        "suggestions": [
            "Si beaucoup de questions prix: ajouter plus de détails prix dans le prompt",
            "Si beaucoup d'installations: ajouter les heures d'ouverture",
            "Si beaucoup de pneus hiver: ajouter promotions saisonnières"
        ]
    }


@app.route("/health")
def health_check():
    return {
        "status": "healthy",
        "ai": "Claude Sonnet 4",
        "voice": "Polly.Gabrielle-Neural (fr-CA)",
        "version": "V3",
        "features": [
            "Speech recognition fr-CA",
            "Claude AI intelligence",
            "Text cleanup (no emoji/symbols)",
            "URL pronunciation fix",
            "Call logging & analytics",
            "Multi-turn conversation"
        ],
        "total_calls_logged": len(call_logs)
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
