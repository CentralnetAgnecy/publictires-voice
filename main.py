#!/usr/bin/env python3
import os
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

@app.route("/")
def hello():
    return "PublicTires Voice Agent Online ✓"

@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming Twilio calls"""
    response = VoiceResponse()
    response.say("Bonjour, bienvenue chez PublicTires.", language="fr-FR", voice="woman")
    response.say("Appuyez sur 1 pour les pneus, ou 2 pour l'installation.", language="fr-FR", voice="woman")
    response.gather(num_digits=1, action="/handle-key", method="POST", timeout=5)
    response.redirect("/call")  # Loop back if no input
    return str(response)

@app.route("/handle-key", methods=["POST"])
def handle_key():
    """Handle DTMF input"""
    digit = request.form.get("Digits", "")
    response = VoiceResponse()
    
    if digit == "1":
        response.say("Pneus neufs et usages. Visitez pneuspublic.ca pour voir nos prix.", language="fr-FR", voice="woman")
    elif digit == "2":
        response.say("Installation au centre PneusPJ. Adresse: 4100 rue Jarry Est, Montreal. Telephone: 514-459-4500.", language="fr-FR", voice="woman")
    else:
        response.say("Je n'ai pas compris. Veuillez appuyer sur 1 ou 2.", language="fr-FR", voice="woman")
    
    response.say("Merci d'avoir appele PublicTires.", language="fr-FR", voice="woman")
    response.hangup()
    
    return str(response)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
