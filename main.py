#!/usr/bin/env python3
"""
PublicTires Voice Agent - Claude Sonnet 4.6 + Twilio + ElevenLabs
Full conversational AI with intelligent menu
"""

import os
import json
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse
import anthropic

app = Flask(__name__)

# Initialize Claude Sonnet 4.6
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Tu es un agent de support client amical et professionnel pour PublicTires.

Mission: Aider les clients avec des questions sur les pneus (neufs/usagés) et l'installation.

Règles:
1. Réponds toujours en français québécois naturel
2. Sois chaleureux et conversationnel
3. Pour les prix: Dirige vers pneuspublic.ca
4. Pour l'installation: Centre PneusPJ, 4100 rue Jarry Est, Montréal, 514-459-4500
5. Mentionne: Ramassage gratuit pour clients PublicTires
6. Sois court et clair (max 2-3 phrases)
7. Reste toujours courtois et professionnel

Réponds directement sans préambule."""

def get_claude_response(user_message):
    """Get intelligent response from Claude Sonnet 4.6"""
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude error: {str(e)}")
        return "Désolé, une erreur est survenue. Veuillez réessayer."

@app.route("/")
def health():
    return "PublicTires Voice Agent ✓ (Claude Sonnet 4.6)"

@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming Twilio calls - Greeting"""
    response = VoiceResponse()
    
    # Greeting with Amélie
    response.say(
        "Bonjour! Bienvenue chez PublicTires. "
        "Vous pouvez appuyer sur 1 pour les pneus, 2 pour l'installation, "
        "ou simplement parler votre question.",
        language="fr-FR",
        voice="woman"
    )
    
    # Record voice for free-form question (10 seconds max)
    response.record(
        max_speech_time=10,
        action="/process-speech",
        method="POST",
        speech_timeout=3,
        transcribe=True,
        transcribe_callback="/transcribed"
    )
    
    return str(response)

@app.route("/transcribed", methods=["POST"])
def transcribed():
    """Receive transcription from Twilio"""
    # This is just a callback - actual processing in /process-speech
    return ""

@app.route("/process-speech", methods=["POST"])
def process_speech():
    """Process recorded/transcribed speech and respond with Claude"""
    response = VoiceResponse()
    
    transcription = request.form.get("SpeechResult", "").strip()
    
    # Check if user said "1" or "2" (menu options)
    if transcription in ["1", "un", "pneus"]:
        user_input = "Je veux des informations sur les pneus"
    elif transcription in ["2", "deux", "installation"]:
        user_input = "Je veux des informations sur l'installation"
    elif transcription:
        user_input = transcription
    else:
        response.say(
            "Je n'ai pas bien entendu. Veuillez appuyer sur 1 pour les pneus, ou 2 pour l'installation.",
            language="fr-FR",
            voice="woman"
        )
        response.gather(num_digits=1, action="/menu-choice", method="POST", timeout=5)
        return str(response)
    
    # Get Claude's response
    claude_response = get_claude_response(user_input)
    
    # Speak the response with Amélie
    response.say(
        claude_response,
        language="fr-FR",
        voice="woman"
    )
    
    # Ask if they want to continue
    response.say(
        "Avez-vous d'autres questions?",
        language="fr-FR",
        voice="woman"
    )
    
    response.gather(
        num_digits=1,
        action="/continue-choice",
        method="POST",
        timeout=5
    )
    
    response.hangup()
    
    return str(response)

@app.route("/menu-choice", methods=["POST"])
def menu_choice():
    """Handle menu choice (1 or 2)"""
    digit = request.form.get("Digits", "0")
    response = VoiceResponse()
    
    if digit == "1":
        claude_response = get_claude_response("Je veux savoir sur vos pneus")
    elif digit == "2":
        claude_response = get_claude_response("Je veux connaître vos services d'installation")
    else:
        response.say(
            "Appuyez sur 1 ou 2.",
            language="fr-FR",
            voice="woman"
        )
        response.redirect("/call")
        return str(response)
    
    response.say(claude_response, language="fr-FR", voice="woman")
    response.say("Merci!", language="fr-FR", voice="woman")
    response.hangup()
    
    return str(response)

@app.route("/continue-choice", methods=["POST"])
def continue_choice():
    """Handle continue or end"""
    digit = request.form.get("Digits", "0")
    response = VoiceResponse()
    
    if digit == "1":
        response.redirect("/call")
    else:
        response.say(
            "Merci d'avoir appelé PublicTires. Au revoir!",
            language="fr-FR",
            voice="woman"
        )
        response.hangup()
    
    return str(response)

@app.route("/health", methods=["GET"])
def health_check():
    return {
        "status": "healthy",
        "service": "PublicTires Voice Agent",
        "ai": "Claude Sonnet 4.6",
        "voice": "Amélie (ElevenLabs)",
        "transcriber": "Twilio",
        "language": "French",
        "mode": "Menu + Free Conversation"
    }, 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
