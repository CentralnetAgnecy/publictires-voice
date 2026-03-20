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
    response.gather(num_digits=1, action="/handle-key", method="POST")
    return str(response)

@app.route("/handle-key", methods=["POST"])
def handle_key():
    """Handle DTMF input"""
    digit = request.form.get("Digits", "")
    response = VoiceResponse()
    
    if digit == "1":
        response.say("Pneus neufs et usages disponibles.", language="fr-FR", voice="woman")
    elif digit == "2":
        response.say("Installation a notre centre PneusPJ.", language="fr-FR", voice="woman")
    else:
        response.say("Merci d'avoir appele PublicTires.", language="fr-FR", voice="woman")
    
    return str(response)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
