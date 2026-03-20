#!/usr/bin/env python3
import os
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)

@app.route("/")
def hello():
    return "PublicTires Voice Agent ✓"

@app.route("/call", methods=["POST"])
def incoming_call():
    response = VoiceResponse()
    response.say(
        "Bonjour! Bienvenue chez PublicTires. "
        "Appuyez sur 1 pour les pneus, ou 2 pour l'installation.",
        language="fr-FR",
        voice="woman"
    )
    response.gather(num_digits=1, action="/process", method="POST", timeout=10)
    response.redirect("/call")
    return str(response)

@app.route("/process", methods=["POST"])
def process():
    digit = request.form.get("Digits", "0")
    response = VoiceResponse()
    
    if digit == "1":
        response.say(
            "Pneus neufs et usagés. Visitez pneuspublic.ca pour commander.",
            language="fr-FR",
            voice="woman"
        )
    elif digit == "2":
        response.say(
            "Installation: 4100 rue Jarry Est, Montréal. 514-459-4500.",
            language="fr-FR",
            voice="woman"
        )
    else:
        response.say(
            "Appuyez sur 1 ou 2.",
            language="fr-FR",
            voice="woman"
        )
        response.redirect("/call")
        return str(response)
    
    response.say("Merci!",language="fr-FR", voice="woman")
    response.hangup()
    return str(response)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
