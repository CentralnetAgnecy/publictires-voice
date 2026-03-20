#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - Phase 1
Claude Sonnet 4.6 + Twilio Speech Recognition + Google fr-CA Voice
Full conversational AI - the client SPEAKS and the AI RESPONDS naturally
"""

import os
import json
import logging
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
import requests

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Config
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# System prompt for Claude
SYSTEM_PROMPT = """Tu es Amélie, une agente de support client chaleureuse et professionnelle pour PublicTires.

CONTEXTE ENTREPRISE:
- PublicTires vend des pneus neufs et usagés en ligne
- Site français: pneuspublic.ca
- Site anglais: publictires.ca
- Installation: Centre Pneus PJ Express, 4100 rue Jarry Est, Montréal, QC
- Téléphone installation: 514-459-4500
- Ramassage GRATUIT pour les clients PublicTires
- Les prix sont directement sur le site web

RÈGLES:
1. Parle en français québécois naturel et chaleureux
2. Sois courte et claire (2-3 phrases max par réponse)
3. Pour les prix: dirige TOUJOURS vers pneuspublic.ca
4. Pour l'installation: donne l'adresse et le numéro
5. Ne JAMAIS inventer un prix ou une disponibilité
6. Si tu ne sais pas: "Laissez-moi vérifier, vous pouvez aussi visiter pneuspublic.ca"
7. Propose toujours d'aider davantage à la fin
8. Sois conversationnelle, pas robotique

EXEMPLES:
- "Combien coûtent les pneus?" → "Les prix varient selon la taille. Visitez pneuspublic.ca pour voir nos meilleurs prix du moment!"
- "Où faire installer?" → "On a notre centre PneusPJ au 4100 Jarry Est à Montréal. Appelez le 514-459-4500, pis le ramassage est gratuit!"
"""

# Conversation history per call (in-memory, resets on restart)
conversations = {}


def get_claude_response(user_message, call_sid="default"):
    """Get intelligent response from Claude Sonnet 4.6"""
    if not ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY set")
        return "Désolé, notre système est temporairement indisponible. Visitez pneuspublic.ca pour nous contacter."

    # Build conversation history
    if call_sid not in conversations:
        conversations[call_sid] = []

    conversations[call_sid].append({"role": "user", "content": user_message})

    # Keep only last 6 messages to avoid token overflow
    history = conversations[call_sid][-6:]

    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 150,
            "system": SYSTEM_PROMPT,
            "messages": history
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            assistant_msg = result["content"][0]["text"]
            conversations[call_sid].append({"role": "assistant", "content": assistant_msg})
            logger.info(f"Claude response: {assistant_msg[:100]}...")
            return assistant_msg
        else:
            logger.error(f"Claude API error: {response.status_code} - {response.text[:200]}")
            return "Désolé, une erreur est survenue. Visitez pneuspublic.ca ou rappelez-nous."

    except Exception as e:
        logger.error(f"Claude error: {str(e)}")
        return "Une erreur est survenue. Visitez pneuspublic.ca pour nous contacter."


# ==========================================
# VOICE: Google fr-CA-Chirp3-HD-Aoede
# Best natural French Canadian voice available on Twilio
# ==========================================
VOICE = "Google.fr-CA-Chirp3-HD-Aoede"
LANG = "fr-CA"


@app.route("/")
def health():
    return "PublicTires AI Voice Agent ✓ (Claude Sonnet 4.6 + Google fr-CA)"


@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming Twilio calls - Natural greeting + speech input"""
    call_sid = request.form.get("CallSid", "unknown")
    logger.info(f"New call: {call_sid}")

    # Reset conversation for new call
    conversations[call_sid] = []

    response = VoiceResponse()

    # Natural greeting with Google fr-CA voice
    response.say(
        "Bonjour! Bienvenue chez PublicTires. Comment est-ce que je peux vous aider?",
        voice=VOICE,
        language=LANG
    )

    # Listen for speech input (client SPEAKS!)
    gather = response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout=5,
        timeout=10,
        speech_model="phone_call",
        hints="pneus, installation, prix, taille, Michelin, Bridgestone, Continental, hiver, été, quatre saisons"
    )

    # If no input after timeout, ask again
    response.say(
        "Je n'ai pas entendu. Pouvez-vous répéter votre question?",
        voice=VOICE,
        language=LANG
    )
    response.redirect("/call")

    return str(response)


@app.route("/respond", methods=["POST"])
def respond():
    """Process speech/DTMF and respond with Claude AI"""
    call_sid = request.form.get("CallSid", "unknown")
    speech_result = request.form.get("SpeechResult", "")
    digits = request.form.get("Digits", "")
    confidence = request.form.get("Confidence", "0")

    logger.info(f"Call {call_sid} - Speech: '{speech_result}' | Digits: '{digits}' | Confidence: {confidence}")

    response = VoiceResponse()

    # Determine user input
    if speech_result:
        user_input = speech_result
    elif digits == "1":
        user_input = "Je veux des informations sur vos pneus"
    elif digits == "2":
        user_input = "Je veux des informations sur l'installation"
    elif digits == "0":
        user_input = "Je veux parler à quelqu'un"
    else:
        user_input = f"L'utilisateur a appuyé sur {digits}" if digits else ""

    if not user_input:
        response.say(
            "Je n'ai pas compris. Pouvez-vous répéter?",
            voice=VOICE,
            language=LANG
        )
        response.redirect("/call")
        return str(response)

    # Get Claude's intelligent response
    claude_response = get_claude_response(user_input, call_sid)

    # Speak Claude's response
    response.say(
        claude_response,
        voice=VOICE,
        language=LANG
    )

    # Continue conversation - listen for more
    gather = response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout=5,
        timeout=8,
        speech_model="phone_call",
        hints="oui, non, merci, au revoir, pneus, installation, prix"
    )

    # If no more input, end politely
    response.say(
        "Merci d'avoir appelé PublicTires. Bonne journée!",
        voice=VOICE,
        language=LANG
    )

    return str(response)


@app.route("/health", methods=["GET"])
def health_check():
    return {
        "status": "healthy",
        "service": "PublicTires Voice Agent",
        "ai": "Claude Sonnet 4.6",
        "voice": "Google fr-CA-Chirp3-HD-Aoede",
        "language": "French Canadian",
        "mode": "Full Conversational AI",
        "features": [
            "Speech recognition (fr-CA)",
            "DTMF fallback (1/2/0)",
            "Multi-turn conversation",
            "Conversation memory per call",
            "Claude AI intelligence"
        ]
    }, 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
