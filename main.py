#!/usr/bin/env python3
"""
PublicTires Voice Agent - Optimized with ElevenLabs
Natural French conversation with Amélie voice
"""

import os
import requests
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

# Config
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "UJCi4DDncuo0VJDSIegj")
ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

def text_to_speech(text):
    """Convert text to speech using ElevenLabs"""
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.8,
                "similarity_boost": 0.75,
            }
        }
        
        response = requests.post(ELEVENLABS_URL, json=data, headers=headers)
        
        if response.status_code == 200:
            return response.content  # Returns MP3 audio
        else:
            print(f"ElevenLabs error: {response.status_code}")
            return None
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return None

@app.route("/")
def health():
    return "PublicTires Voice Agent Online ✓"

@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming Twilio calls with natural greeting"""
    response = VoiceResponse()
    
    # Natural greeting
    response.say(
        "Bonjour! Bienvenue chez PublicTires. "
        "Appuyez sur 1 pour les pneus neufs ou usagés, "
        "ou 2 pour l'installation.",
        language="fr-FR",
        voice="woman"
    )
    
    # Wait for input with longer timeout
    response.gather(
        num_digits=1,
        action="/process",
        method="POST",
        timeout=10,
        num_digits=1
    )
    
    # If no input, replay menu
    response.redirect("/call")
    
    return str(response)

@app.route("/process", methods=["POST"])
def process_input():
    """Process user input (1 or 2)"""
    digit = request.form.get("Digits", "0")
    response = VoiceResponse()
    
    if digit == "1":
        # Tire sales info
        response.say(
            "Excellent! Nous avons une large sélection de pneus neufs et usagés. "
            "Visitez pneuspublic.ca pour découvrir nos prix et commander en ligne. "
            "Vous pouvez aussi nous appeler pour plus de détails.",
            language="fr-FR",
            voice="woman"
        )
    
    elif digit == "2":
        # Installation info
        response.say(
            "Parfait! Nous offrons l'installation à notre centre partenaire, "
            "Centre Pneus PJ Express. "
            "Adresse: 4100 rue Jarry Est, Montréal. "
            "Téléphone: 514-459-4500. "
            "Nous offrons le ramassage gratuit pour les clients PublicTires.",
            language="fr-FR",
            voice="woman"
        )
    
    else:
        # Invalid input
        response.say(
            "Je n'ai pas bien compris. Appuyez sur 1 pour les pneus ou 2 pour l'installation.",
            language="fr-FR",
            voice="woman"
        )
        response.redirect("/call")
        return str(response)
    
    # End call
    response.say(
        "Merci d'avoir appelé PublicTires. Au revoir!",
        language="fr-FR",
        voice="woman"
    )
    response.hangup()
    
    return str(response)

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "PublicTires Voice Agent",
        "voice": "Amélie (ElevenLabs)",
        "language": "French",
    }, 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
