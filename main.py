#!/usr/bin/env python3
"""
PublicTires Voice Agent - Claude Sonnet 4.6 + Twilio
"""

import os
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

app = Flask(__name__)

# Initialize Claude if available
client = None
if CLAUDE_AVAILABLE:
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except:
        CLAUDE_AVAILABLE = False

SYSTEM_PROMPT = """Tu es un agent de support client pour PublicTires.
Aide sur pneus (neufs/usagés) et installation.
Réponds en français québécois court et clair.
Prix: pneuspublic.ca
Installation: 4100 rue Jarry Est, Montréal, 514-459-4500
Ramassage gratuit pour clients."""

def get_claude_response(user_message):
    """Get response from Claude Sonnet 4.6"""
    if not CLAUDE_AVAILABLE or not client:
        return "Service temporairement indisponible. Veuillez appuyer sur 1 ou 2."
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Claude error: {str(e)}")
        return "Une erreur est survenue. Veuillez réessayer."

@app.route("/")
def health():
    status = "Claude Sonnet 4.6" if CLAUDE_AVAILABLE else "Simple Menu"
    return f"PublicTires Voice Agent ✓ ({status})"

@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming Twilio calls"""
    response = VoiceResponse()
    
    response.say(
        "Bonjour! Bienvenue chez PublicTires. "
        "Appuyez sur 1 pour les pneus ou 2 pour l'installation.",
        language="fr-FR",
        voice="woman"
    )
    
    response.gather(num_digits=1, action="/process", method="POST", timeout=10)
    response.redirect("/call")
    
    return str(response)

@app.route("/process", methods=["POST"])
def process():
    """Process menu choice with Claude intelligence"""
    digit = request.form.get("Digits", "0")
    response = VoiceResponse()
    
    if digit == "1":
        if CLAUDE_AVAILABLE:
            msg = get_claude_response("Parlez-moi de vos pneus neufs et usagés")
        else:
            msg = "Pneus neufs et usagés disponibles. Visitez pneuspublic.ca"
    elif digit == "2":
        if CLAUDE_AVAILABLE:
            msg = get_claude_response("Quels sont vos services d'installation?")
        else:
            msg = "Installation au Centre PneusPJ. 4100 rue Jarry Est, Montréal. 514-459-4500."
    else:
        response.say("Appuyez sur 1 ou 2.", language="fr-FR", voice="woman")
        response.redirect("/call")
        return str(response)
    
    response.say(msg, language="fr-FR", voice="woman")
    response.say("Merci d'avoir appelé PublicTires!", language="fr-FR", voice="woman")
    response.hangup()
    
    return str(response)

@app.route("/health", methods=["GET"])
def health_check():
    return {
        "status": "healthy",
        "service": "PublicTires Voice Agent",
        "ai": "Claude Sonnet 4.6" if CLAUDE_AVAILABLE else "Simple Menu",
        "voice": "Amélie (ElevenLabs)",
    }, 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
