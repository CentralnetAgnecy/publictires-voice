#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - Optimized Version
Claude Sonnet 4 + Twilio Speech Recognition + Google fr-CA Voice
Optimized for speed and voice consistency
"""

import os
import json
import logging
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
import requests as http_requests

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Best French Canadian voice on Twilio (natural, consistent)
VOICE = "Polly.Gabrielle-Neural"
LANG = "fr-CA"

SYSTEM_PROMPT = """Tu es Amélie, une agente de support client chaleureuse pour PublicTires.

CONTEXTE:
- PublicTires vend des pneus neufs et usagés en ligne
- Site: pneuspublic.ca (français) / publictires.ca (anglais)
- Installation: Centre Pneus PJ Express, 4100 rue Jarry Est, Montréal
- Téléphone installation: 514-459-4500
- Ramassage GRATUIT pour clients PublicTires

RÈGLES:
1. Parle en français québécois naturel
2. Maximum 2-3 phrases par réponse (COURT!)
3. Pour les prix: dirige vers pneuspublic.ca
4. Ne JAMAIS inventer un prix
5. Sois conversationnelle
6. Propose toujours d'aider davantage"""

# Conversation memory per call
conversations = {}


def get_claude_response(user_message, call_sid="default"):
    """Get response from Claude Sonnet 4 - optimized for speed"""
    if not ANTHROPIC_API_KEY:
        return "Visitez pneuspublic.ca pour nous contacter."

    if call_sid not in conversations:
        conversations[call_sid] = []

    conversations[call_sid].append({"role": "user", "content": user_message})
    history = conversations[call_sid][-4:]  # Keep only last 4 messages for speed

    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100,  # Short responses = faster
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
            conversations[call_sid].append({"role": "assistant", "content": msg})
            return msg
        else:
            logger.error(f"Claude error: {response.status_code}")
            return "Désolé, visitez pneuspublic.ca ou rappelez-nous."
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return "Visitez pneuspublic.ca pour nous contacter."


@app.route("/")
def health():
    return "PublicTires Voice Agent ✓ (Claude Sonnet 4 + Polly Gabrielle)"


@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming call - greeting + speech input"""
    call_sid = request.form.get("CallSid", "unknown")
    conversations[call_sid] = []

    response = VoiceResponse()

    response.say(
        "Bonjour! Bienvenue chez PublicTires. Comment est-ce que je peux vous aider?",
        voice=VOICE,
        language=LANG
    )

    gather = response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=10,
        speech_model="phone_call",
        hints="pneus, installation, prix, taille, Michelin, Bridgestone, hiver, été"
    )

    response.say("Je n'ai pas entendu. Pouvez-vous répéter?", voice=VOICE, language=LANG)
    response.redirect("/call")

    return str(response)


@app.route("/respond", methods=["POST"])
def respond():
    """Process speech and respond with Claude"""
    call_sid = request.form.get("CallSid", "unknown")
    speech = request.form.get("SpeechResult", "")
    digits = request.form.get("Digits", "")

    response = VoiceResponse()

    # Determine input
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

    logger.info(f"Client: '{user_input}'")

    # Get Claude response
    claude_response = get_claude_response(user_input, call_sid)
    logger.info(f"Amélie: '{claude_response[:80]}...'")

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

    response.say("Merci d'avoir appelé PublicTires. Bonne journée!", voice=VOICE, language=LANG)

    return str(response)


@app.route("/health")
def health_check():
    return {
        "status": "healthy",
        "ai": "Claude Sonnet 4",
        "voice": "Amazon Polly Gabrielle-Neural (fr-CA)",
        "mode": "Speech Recognition + AI",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
