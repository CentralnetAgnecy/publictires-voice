#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - ConversationRelay Edition
Real-time conversation with Claude Sonnet 4 + ElevenLabs Amélie
Ultra-low latency via Twilio ConversationRelay WebSocket
"""

import os
import json
import logging
import uvicorn
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PORT = int(os.getenv("PORT", "8080"))
DOMAIN = os.getenv("DOMAIN", "")
WS_URL = f"wss://{DOMAIN}/ws" if DOMAIN else ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ElevenLabs Amélie voice ID
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "UJCi4DDncuo0VJDSIegj")

# Voice settings: voiceId-model_speed_stability_similarity
# Flash 2.5 = fastest, speed 1.1 = slightly faster, stability 0.8 = natural
VOICE_CONFIG = f"{ELEVENLABS_VOICE_ID}-eleven_flash_v2_5_1.1_0.8_0.8"

WELCOME_GREETING = "Bonjour! Bienvenue chez PublicTires. Comment est-ce que je peux vous aider?"

SYSTEM_PROMPT = """Tu es Amélie, une agente de support client chaleureuse et professionnelle pour PublicTires.

CONTEXTE:
- PublicTires vend des pneus neufs et usagés en ligne
- Site français: pneuspublic.ca
- Site anglais: publictires.ca  
- Installation: Centre Pneus PJ Express, 4100 rue Jarry Est, Montréal
- Téléphone installation: 514-459-4500
- Ramassage GRATUIT pour clients PublicTires
- Les prix sont sur le site web

RÈGLES IMPORTANTES:
1. Parle en français québécois naturel et chaleureux
2. Sois courte et claire, deux à trois phrases max par réponse
3. Pour les prix, dirige TOUJOURS vers pneuspublic point ca
4. Ne JAMAIS inventer un prix ou une disponibilité
5. Sois conversationnelle, pas robotique
6. Cette conversation est vocale: épelle les nombres en lettres
7. Ne mets pas d'émojis ni de symboles spéciaux dans tes réponses
8. Ne mets pas de puces, d'astérisques ou de formatage markdown
9. Écris les URLs en les épelant: pneuspublic point ca
10. Propose toujours d'aider davantage"""

# Store active call sessions
sessions = {}

# Create FastAPI app
app = FastAPI()


def get_claude_response(messages):
    """Get response from Claude Sonnet 4 via API"""
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        # Convert messages format (remove system, keep user/assistant)
        api_messages = [m for m in messages if m["role"] != "system"]
        system_content = next((m["content"] for m in messages if m["role"] == "system"), SYSTEM_PROMPT)

        data = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 150,
            "system": system_content,
            "messages": api_messages
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=8
        )

        if response.status_code == 200:
            result = response.json()
            return result["content"][0]["text"]
        else:
            logger.error(f"Claude API error: {response.status_code}")
            return "Désolé, une petite erreur est survenue. Pouvez-vous répéter votre question?"

    except Exception as e:
        logger.error(f"Claude error: {str(e)}")
        return "Excusez-moi, je n'ai pas pu traiter votre demande. Pouvez-vous réessayer?"


@app.get("/")
async def health():
    return {"status": "healthy", "service": "PublicTires Voice Agent", "ai": "Claude Sonnet 4", "voice": "ElevenLabs Amélie", "mode": "ConversationRelay"}


@app.post("/twiml")
async def twiml_endpoint():
    """Returns TwiML to connect call to ConversationRelay WebSocket"""
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
      <Connect>
        <ConversationRelay
          url="{WS_URL}"
          welcomeGreeting="{WELCOME_GREETING}"
          ttsProvider="ElevenLabs"
          voice="{VOICE_CONFIG}"
          language="fr-CA"
          transcriptionLanguage="fr-CA"
          ttsLanguage="fr-CA"
          transcriptionProvider="Deepgram"
          speechModel="nova-3-general"
          interruptible="speech"
          interruptSensitivity="medium"
          dtmfDetection="true"
          elevenlabsTextNormalization="on"
        >
          <Language code="fr-CA" ttsProvider="ElevenLabs" voice="{VOICE_CONFIG}" transcriptionProvider="Deepgram" speechModel="nova-3-general" />
        </ConversationRelay>
      </Connect>
    </Response>"""

    return Response(content=xml_response, media_type="text/xml")


@app.post("/call")
async def call_endpoint():
    """Fallback: same as /twiml for Twilio webhook compatibility"""
    return await twiml_endpoint()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time ConversationRelay communication"""
    await websocket.accept()
    call_sid = None

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "setup":
                call_sid = message.get("callSid", "unknown")
                logger.info(f"New call connected: {call_sid}")
                websocket.call_sid = call_sid
                sessions[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]

            elif message["type"] == "prompt":
                voice_prompt = message.get("voicePrompt", "")
                logger.info(f"Client said: '{voice_prompt}'")

                if not voice_prompt.strip():
                    continue

                conversation = sessions.get(getattr(websocket, 'call_sid', None), [{"role": "system", "content": SYSTEM_PROMPT}])
                conversation.append({"role": "user", "content": voice_prompt})

                # Get Claude's response
                response_text = get_claude_response(conversation)
                conversation.append({"role": "assistant", "content": response_text})

                # Send response back to ConversationRelay for TTS
                await websocket.send_text(
                    json.dumps({
                        "type": "text",
                        "token": response_text,
                        "last": True
                    })
                )
                logger.info(f"Amélie says: '{response_text[:100]}...'")

            elif message["type"] == "interrupt":
                logger.info("Client interrupted - stopping current response")

            elif message["type"] == "dtmf":
                digit = message.get("digit", "")
                logger.info(f"DTMF received: {digit}")

                # Handle DTMF as text input
                dtmf_map = {
                    "1": "Je veux des informations sur vos pneus",
                    "2": "Je veux des informations sur l'installation",
                    "0": "Je veux parler à quelqu'un"
                }

                if digit in dtmf_map:
                    conversation = sessions.get(getattr(websocket, 'call_sid', None), [{"role": "system", "content": SYSTEM_PROMPT}])
                    conversation.append({"role": "user", "content": dtmf_map[digit]})
                    response_text = get_claude_response(conversation)
                    conversation.append({"role": "assistant", "content": response_text})

                    await websocket.send_text(
                        json.dumps({
                            "type": "text",
                            "token": response_text,
                            "last": True
                        })
                    )

            else:
                logger.debug(f"Unknown message type: {message.get('type', 'unknown')}")

    except WebSocketDisconnect:
        logger.info(f"Call ended: {call_sid}")
        if call_sid:
            sessions.pop(call_sid, None)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        if call_sid:
            sessions.pop(call_sid, None)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
