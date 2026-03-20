#!/usr/bin/env python3
"""
PublicTires AI Voice Agent - V5.0 (OPUS AUDIT EDITION)
Gemini 2.5 Flash + Polly Gabrielle (fr-CA)
All security, performance, and stability fixes applied.
"""

import os
import re
import csv
import json
import logging
import hashlib
import time
from collections import deque, OrderedDict
from datetime import datetime, timedelta
from io import StringIO
from functools import wraps
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse
from twilio.request_validator import RequestValidator
import requests as http_requests

# ============================================================
# CONFIG & CONSTANTS
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# API Keys (never bake into URLs)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Twilio
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

# Admin API key for protected endpoints
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "publictires-admin-2026")

# Voice
VOICE = "Polly.Gabrielle-Neural"
LANG = "fr-CA"

# Tuning constants
MAX_OUTPUT_TOKENS = 500
TEMPERATURE = 0.7
GEMINI_TIMEOUT = 8
CONVERSATION_HISTORY_TURNS = 6
MAX_CALL_LOGS = 200
MAX_CALL_RECORDS = 500
CONVERSATION_TTL_MINUTES = 60
MAX_NO_INPUT_REDIRECTS = 3
GATHER_TIMEOUT_INITIAL = 10
GATHER_TIMEOUT_FOLLOWUP = 8

# Pre-compiled regex (compiled ONCE at module level)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937\U00010000-\U0010ffff\u2640-\u2642\u2600-\u2B55"
    "\u200d\u23cf\u23e9\u231a\ufe0f\u3030]+", flags=re.UNICODE
)

TIRE_SIZE_FULL = re.compile(r'(\d{3})[/\\\s\-](\d{2,3})\s*[Rr]\s*(\d{2})')
TIRE_SIZE_PARTIAL = re.compile(r'(\d{3})[/\\\s\-](\d{2,3})(?!\s*[Rr])')
TIRE_SIZE_DETECT = re.compile(r'\d{3}[\s/\-]?\d{2,3}(?:[Rr]\d{2})?')
TIRE_SIZE_EXTRACT = re.compile(r'(\d{3})[/\s\-](\d{2,3})(?:[Rr](\d{2}))?')
MARKDOWN_BOLD = re.compile(r'\*\*([^*]+)\*\*')
MARKDOWN_ITALIC = re.compile(r'\*([^*]+)\*')
MARKDOWN_HEADER = re.compile(r'#{1,6}\s')
MARKDOWN_BULLET = re.compile(r'[-•]\s')
MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
PAREN_CONTENT = re.compile(r'\([^)]*\)')
MULTI_SPACE = re.compile(r'\s+')

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """Tu es Amélie, une vraie conseillère en pneus chez Pneus Public. Tu parles au téléphone avec un client québécois.

ENTREPRISE:
- Pneus Public vend des pneus neufs et usagés en ligne
- Site: pneus public point ca
- Installation: Centre PneusPJ, 4100 Jarry Est, Montréal, 514-459-4500
- Ramassage GRATUIT pour nos clients
- Prix et dispo: sur le site web

COMMENT PARLER:
Tu parles comme une vraie personne, pas un robot. Naturelle, chaleureuse, compétente.
Tu connais les pneus et tu aides le client à trouver ce qu'il veut.
Tes phrases sont courtes et directes, comme au téléphone.
Tu vouvoies le client.
IMPORTANT: Ne dis JAMAIS "Bonjour" deux fois. C'est juste au début de l'appel!

OBJECTION HANDLING:
Si client dit "C'est trop cher": "Je comprends! On a des pneus excellents à meilleur prix. Quel est votre budget?"
Si client dit "Pas maintenant": "Bien sûr! Quand serait bon pour vous? Je peux vous laisser notre numéro."
Si client dit "J'ai déjà des pneus": "Et pour l'installation? Ramassage gratuit chez PneusPJ!"
Si client dit "Pourquoi vous": "Pneus de qualité, prix compétitifs, et installation pro avec ramassage gratuit!"

RÈGLES TECHNIQUES POUR LA VOIX:
- JAMAIS d'émojis, astérisques, tirets, listes, puces ou formatage
- JAMAIS de parenthèses ou crochets
- Pour les tailles de pneus: dis-les naturellement comme "deux cent cinq soixante R seize" pas chiffre par chiffre
- Pour le site: "pneus public point ca"
- Pour l'adresse: "quatre mille cent rue Jarry Est à Montréal"
- Pour le tel: "cinq un quatre, quatre cinq neuf, quatre cinq zéro zéro"
- Minimum 2-3 phrases complètes par réponse
- Ne JAMAIS inventer un prix ou une disponibilité
- Réponds complètement - jamais coupé ou incomplet

EXEMPLES NATURELS:
- Client: "bonjour" → "Bonjour! Bienvenue chez Pneus Public. Comment puis-je vous aider?"
- Client: "205 55 16" → "Oui, on a une belle sélection en deux cent cinq soixante R seize! Vous cherchez quoi comme type de pneu, été ou hiver? Visitez pneus public point ca pour voir tout ce qu'on a."
- Client: "installation" → "Bien sûr! Notre centre PneusPJ est au quatre mille cent Jarry Est à Montréal. Appelez-les au cinq un quatre, quatre cinq neuf, quatre cinq zéro zéro. Le ramassage est gratuit pour nos clients!"
- Client: "prix" → "Les prix sont directement sur pneus public point ca, ils changent souvent selon les promotions. Vous pouvez aussi nous laisser votre numéro pour qu'on vous rappelle avec une soumission."

IMPORTANT: Donne TOUJOURS une réponse complète et utile. Avance vers la vente. Propose toujours d'aider davantage."""

# ============================================================
# STATE (with TTL cleanup)
# ============================================================

conversations = OrderedDict()  # call_sid → {"messages": [], "created": datetime}
call_logs = deque(maxlen=MAX_CALL_LOGS)  # O(1) append and pop
call_records = OrderedDict()  # call_sid → CallRecord


def cleanup_old_conversations():
    """Evict conversations older than TTL to prevent memory leak."""
    cutoff = datetime.utcnow() - timedelta(minutes=CONVERSATION_TTL_MINUTES)
    stale_keys = [k for k, v in conversations.items()
                  if v.get("created", datetime.utcnow()) < cutoff]
    for k in stale_keys:
        del conversations[k]

    # Also cap call_records
    while len(call_records) > MAX_CALL_RECORDS:
        call_records.popitem(last=False)


# ============================================================
# AUTH & SECURITY
# ============================================================

def require_admin(f):
    """Decorator: require ADMIN_API_KEY via header or query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("key")
        if not key or key != ADMIN_API_KEY:
            return {"error": "Unauthorized. Provide X-API-Key header or ?key= param."}, 401
        return f(*args, **kwargs)
    return decorated


def validate_twilio_request():
    """Validate that the request actually came from Twilio."""
    if not TWILIO_AUTH_TOKEN:
        return True  # Skip validation if no token configured
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    url = request.url
    params = request.form.to_dict()
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(url, params, signature)


def sanitize_speech_input(text: str) -> str:
    """Basic sanitization of speech input to reduce prompt injection risk."""
    # Remove common injection patterns
    dangerous_patterns = [
        r'ignore\s+(previous|all|your)\s+(instructions|rules|prompts?)',
        r'you\s+are\s+now\s+',
        r'system\s*:\s*',
        r'<\s*/?script',
    ]
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()


# ============================================================
# CALL RECORD (Analytics)
# ============================================================

class CallRecord:
    """Stores call metadata for analytics."""

    def __init__(self, call_sid: str, phone_number: str):
        self.call_sid = call_sid
        self.phone_number = self._mask_phone(phone_number)
        self.start_time = datetime.utcnow()
        self.messages: list = []
        self.intent: str | None = None
        self.sentiment: str = "neutral"
        self.outcome: str = "in_progress"
        self.tire_size_mentioned: str | None = None
        self.objections: list = []

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """Mask phone number for privacy: +1873736XXXX"""
        if len(phone) > 4:
            return phone[:-4] + "XXXX"
        return "XXXX"

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def add_message(self, role: str, text: str):
        self.messages.append({
            "role": role,
            "text": text[:500],  # Cap message length
            "timestamp": datetime.utcnow().isoformat()
        })

        text_lower = text.lower()

        # Detect intent
        if any(w in text_lower for w in ["pneu", "tire", "205", "235", "195", "215", "225", "245"]):
            self.intent = "tire_inquiry"
        elif any(w in text_lower for w in ["install", "ramassage", "pickup", "poser"]):
            self.intent = "installation"
        elif any(w in text_lower for w in ["prix", "price", "combien", "cost", "cher"]):
            self.intent = "pricing"

        # Detect objections
        if any(w in text_lower for w in ["trop cher", "expensive", "price too high", "budget"]):
            if "price" not in self.objections:
                self.objections.append("price")
        elif any(w in text_lower for w in ["pas maintenant", "later", "réfléchir", "plus tard"]):
            if "timing" not in self.objections:
                self.objections.append("timing")
        elif any(w in text_lower for w in ["déjà", "already have", "j'en ai"]):
            if "already_has" not in self.objections:
                self.objections.append("already_has")

    def to_dict(self) -> dict:
        return {
            "call_sid": self.call_sid,
            "phone": self.phone_number,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": round((datetime.utcnow() - self.start_time).total_seconds(), 1),
            "intent": self.intent,
            "sentiment": self.sentiment,
            "outcome": self.outcome,
            "tire_size": self.tire_size_mentioned,
            "objections_count": len(self.objections),
            "objections": self.objections,
            "message_count": self.message_count,
            "messages": self.messages[-5:]
        }


# ============================================================
# TEXT-TO-SPEECH CLEANUP
# ============================================================

def number_to_french(num_str: str) -> str:
    """Convert a number string to French words."""
    num = int(num_str)
    if num == 0:
        return "zéro"

    ones = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"]
    teens = ["dix", "onze", "douze", "treize", "quatorze", "quinze",
             "seize", "dix-sept", "dix-huit", "dix-neuf"]
    tens = ["", "", "vingt", "trente", "quarante", "cinquante",
            "soixante", "soixante-dix", "quatre-vingt", "quatre-vingt-dix"]

    if num < 10:
        return ones[num]
    elif num < 20:
        return teens[num - 10]
    elif num < 100:
        t, o = divmod(num, 10)
        if t == 7:
            return f"soixante-{teens[o]}"
        elif t == 9:
            return f"quatre-vingt-{teens[o]}"
        elif o == 0:
            return tens[t]
        elif o == 1 and t in (2, 3, 4, 5, 6):
            return f"{tens[t]} et un"
        return f"{tens[t]}-{ones[o]}"
    elif num < 1000:
        h, remainder = divmod(num, 100)
        prefix = "cent" if h == 1 else f"{ones[h]} cent"
        if remainder == 0:
            return f"{prefix}s" if h > 1 else prefix
        return f"{prefix} {number_to_french(str(remainder))}"
    elif num < 10000:
        th, remainder = divmod(num, 1000)
        prefix = "mille" if th == 1 else f"{number_to_french(str(th))} mille"
        if remainder == 0:
            return prefix
        return f"{prefix} {number_to_french(str(remainder))}"
    return str(num)


def detect_tire_size(text: str) -> str:
    """Detect and normalize tire sizes in text."""
    matches = list(TIRE_SIZE_DETECT.finditer(text))
    for match in reversed(matches):  # Reverse to preserve indices
        tire_str = match.group(0)
        m = TIRE_SIZE_EXTRACT.search(tire_str)
        if m:
            width, ratio, diameter = m.groups()
            if 165 <= int(width) <= 275 and 30 <= int(ratio) <= 80:
                if diameter and 13 <= int(diameter) <= 24:
                    normalized = f"{width} {ratio} R {diameter}"
                else:
                    normalized = f"{width} {ratio}"
                text = text[:match.start()] + normalized + text[match.end():]
    return text


def clean_for_speech(text: str) -> str:
    """Clean AI output for natural TTS speech."""
    # Normalize tire sizes first
    text = detect_tire_size(text)

    # Remove emojis (pre-compiled pattern)
    text = EMOJI_PATTERN.sub('', text)

    # Remove markdown formatting
    text = MARKDOWN_BOLD.sub(r'\1', text)
    text = MARKDOWN_ITALIC.sub(r'\1', text)
    text = MARKDOWN_HEADER.sub('', text)
    text = MARKDOWN_BULLET.sub('', text)
    text = MARKDOWN_LINK.sub(r'\1', text)

    # Fix URL pronunciation
    text = text.replace('pneuspublic.ca', 'pneus public point ca')
    text = text.replace('publictires.ca', 'pneus public point ca')
    text = text.replace('PublicTires', 'Pneus Public')
    text = text.replace('publictires', 'pneus public')
    text = text.replace('pneuspublic', 'pneus public')

    # Fix phone pronunciation
    text = text.replace('514-459-4500', 'cinq un quatre, quatre cinq neuf, quatre cinq zéro zéro')
    text = text.replace('514 459-4500', 'cinq un quatre, quatre cinq neuf, quatre cinq zéro zéro')
    text = text.replace('(514)', 'cinq un quatre')

    # Convert tire sizes to French words
    text = TIRE_SIZE_FULL.sub(
        lambda m: f"{number_to_french(m.group(1))} {number_to_french(m.group(2))} R {number_to_french(m.group(3))}",
        text)
    text = TIRE_SIZE_PARTIAL.sub(
        lambda m: f"{number_to_french(m.group(1))} {number_to_french(m.group(2))}",
        text)

    # Remove leftover special chars
    text = PAREN_CONTENT.sub('', text)
    text = text.replace('*', '').replace('#', '').replace('`', '')
    text = MULTI_SPACE.sub(' ', text).strip()

    return text


# ============================================================
# GEMINI API
# ============================================================

def _build_gemini_url() -> str | None:
    """Build Gemini URL at call time (never bake key into module-level constant)."""
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set!")
        return None
    return f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"


def get_gemini_response(user_message: str, call_sid: str = "default") -> str:
    """Get response from Gemini 2.5 Flash with retry."""
    url = _build_gemini_url()
    if not url:
        return "Visitez pneus public point ca pour nous contacter."

    # Initialize or fetch conversation
    if call_sid not in conversations:
        conversations[call_sid] = {"messages": [], "created": datetime.utcnow()}

    conv = conversations[call_sid]
    conv["messages"].append({"role": "user", "parts": [{"text": user_message}]})

    # Build contents (last N turns)
    contents = conv["messages"][-CONVERSATION_HISTORY_TURNS:]

    data = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE
        }
    }

    # Retry logic (1 retry on transient failure)
    for attempt in range(2):
        try:
            response = http_requests.post(url, json=data, timeout=GEMINI_TIMEOUT)

            if response.status_code == 200:
                result = response.json()
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        msg = parts[0].get("text", "")
                        if msg:
                            msg = clean_for_speech(msg)
                            conv["messages"].append({"role": "model", "parts": [{"text": msg}]})
                            return msg

                logger.warning(f"Gemini empty/blocked response: {result.get('promptFeedback', 'unknown')}")
                return "Je n'ai pas bien compris. Pouvez-vous reformuler votre question?"

            elif response.status_code in (429, 500, 502, 503):
                logger.warning(f"Gemini transient error {response.status_code}, attempt {attempt + 1}")
                if attempt == 0:
                    time.sleep(0.5)
                    continue
            else:
                logger.error(f"Gemini error: {response.status_code} - {response.text[:200]}")
                break

        except http_requests.exceptions.Timeout:
            logger.warning(f"Gemini timeout, attempt {attempt + 1}")
            if attempt == 0:
                continue
        except Exception as e:
            logger.error(f"Gemini exception: {str(e)}")
            break

    return "Désolé, visitez pneus public point ca ou rappelez-nous."


# ============================================================
# LOGGING
# ============================================================

def log_call(call_sid: str, user_said: str, ai_said: str, phone_number: str | None = None):
    """Log call exchange with detailed analytics."""
    # Periodic cleanup
    cleanup_old_conversations()

    # Simple log (deque handles max size automatically)
    call_logs.append({
        "ts": datetime.utcnow().isoformat(),
        "sid": call_sid,
        "user": user_said[:200],
        "ai": ai_said[:500]
    })

    # Detailed record
    if call_sid not in call_records:
        call_records[call_sid] = CallRecord(call_sid, phone_number or "unknown")

    record = call_records[call_sid]
    record.add_message("user", user_said)
    record.add_message("assistant", ai_said)

    # Detect tire size mentioned
    tire_match = TIRE_SIZE_EXTRACT.search(user_said)
    if tire_match:
        w, r = tire_match.group(1), tire_match.group(2)
        record.tire_size_mentioned = f"{w}/{r}"

    logger.info(f"CALL[{call_sid[:8]}] User: '{user_said[:40]}' → AI: '{ai_said[:40]}' | Intent: {record.intent}")


# ============================================================
# ROUTES — Twilio Webhooks
# ============================================================

@app.route("/")
def index():
    return "PublicTires Voice Agent V5.0 ✓ (Gemini 2.5 Flash + Opus Audit)"


@app.route("/call", methods=["POST"])
def incoming_call():
    """Handle incoming call — first greeting."""
    if not validate_twilio_request():
        logger.warning("Invalid Twilio signature on /call")
        return Response("Forbidden", status=403)

    call_sid = request.form.get("CallSid", "unknown")
    conversations.pop(call_sid, None)  # Fresh conversation

    response = VoiceResponse()
    response.say(
        "Bonjour! Bienvenue chez Pneus Public. Comment est-ce que je peux vous aider?",
        voice=VOICE, language=LANG
    )

    response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=GATHER_TIMEOUT_INITIAL,
        speech_model="phone_call",
        hints="pneus, installation, prix, taille, Michelin, Bridgestone, hiver, été, quatre saisons"
    )

    # On no input: polite goodbye instead of infinite loop
    response.say(
        "Je n'ai pas entendu de réponse. N'hésitez pas à nous rappeler. Bonne journée!",
        voice=VOICE, language=LANG
    )
    return str(response)


@app.route("/respond", methods=["POST"])
def respond():
    """Handle ongoing conversation turns."""
    if not validate_twilio_request():
        logger.warning("Invalid Twilio signature on /respond")
        return Response("Forbidden", status=403)

    call_sid = request.form.get("CallSid", "unknown")
    speech = request.form.get("SpeechResult", "")
    digits = request.form.get("Digits", "")

    response = VoiceResponse()

    if speech:
        user_input = sanitize_speech_input(speech)
    elif digits == "1":
        user_input = "Informations sur vos pneus"
    elif digits == "2":
        user_input = "Informations sur l'installation"
    else:
        user_input = ""

    if not user_input:
        response.say("Pouvez-vous répéter?", voice=VOICE, language=LANG)
        response.gather(
            input="speech dtmf",
            action="/respond",
            method="POST",
            language="fr-CA",
            speech_timeout="auto",
            timeout=GATHER_TIMEOUT_FOLLOWUP,
            speech_model="phone_call"
        )
        response.say("Merci d'avoir appelé Pneus Public. Bonne journée!", voice=VOICE, language=LANG)
        return str(response)

    # Get AI response
    ai_response = get_gemini_response(user_input, call_sid)
    phone = request.form.get("Caller", "unknown")
    log_call(call_sid, user_input, ai_response, phone)

    response.say(ai_response, voice=VOICE, language=LANG)

    response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=GATHER_TIMEOUT_FOLLOWUP,
        speech_model="phone_call",
        hints="oui, non, merci, au revoir, pneus, installation, prix"
    )

    response.say("Merci d'avoir appelé Pneus Public. Bonne journée!", voice=VOICE, language=LANG)
    return str(response)


@app.route("/status", methods=["POST"])
def call_status():
    """Twilio status callback — mark calls as completed."""
    if not validate_twilio_request():
        return Response("Forbidden", status=403)
    
    call_sid = request.form.get("CallSid", "")
    status = request.form.get("CallStatus", "")
    if call_sid in call_records and status in ("completed", "busy", "failed", "no-answer"):
        call_records[call_sid].outcome = status
        logger.info(f"Call {call_sid[:8]} → {status}")
    return "", 204


@app.route("/outbound", methods=["POST"])
def outbound_call():
    """Outbound call greeting — when Amélie calls a prospect."""
    if not validate_twilio_request():
        return Response("Forbidden", status=403)

    call_sid = request.form.get("CallSid", "unknown")
    conversations.pop(call_sid, None)  # Fresh conversation

    response = VoiceResponse()
    response.say(
        "Bonjour! C'est Amélie de Pneus Public. Comment allez-vous aujourd'hui?",
        voice=VOICE, language=LANG
    )

    response.gather(
        input="speech dtmf",
        action="/respond",
        method="POST",
        language="fr-CA",
        speech_timeout="auto",
        timeout=GATHER_TIMEOUT_INITIAL,
        speech_model="phone_call",
        hints="pneus, installation, prix, taille"
    )

    response.say("Merci d'avoir écouté. Bonne journée!", voice=VOICE, language=LANG)
    return str(response)


# ============================================================
# ROUTES — Admin / Analytics (PROTECTED)
# ============================================================

@app.route("/health")
def health_check():
    """Public health check (no sensitive data)."""
    return {
        "status": "healthy",
        "ai": f"Gemini 2.5 Flash",
        "voice": "Polly.Gabrielle-Neural (fr-CA)",
        "version": "V5.0",
        "features": [
            "twilio_signature_validation",
            "admin_auth",
            "phone_masking",
            "retry_logic",
            "memory_cleanup",
            "objection_handling",
            "tire_detection",
            "call_analytics",
            "prompt_injection_guard"
        ]
    }


@app.route("/logs")
@require_admin
def get_logs():
    """View recent call logs (admin only)."""
    return {"total": len(call_logs), "logs": list(call_logs)[-20:]}


@app.route("/call-records")
@require_admin
def get_call_records():
    """View detailed call analytics (admin only)."""
    records = [r.to_dict() for r in call_records.values()]
    return {"total_calls": len(records), "records": records[-20:]}


@app.route("/call-stats")
@require_admin
def get_call_stats():
    """View aggregated statistics (admin only)."""
    if not call_records:
        return {"message": "No call data yet"}

    records = list(call_records.values())
    intents: dict = {}
    objection_counts: dict = {}
    outcomes: dict = {}

    for record in records:
        if record.intent:
            intents[record.intent] = intents.get(record.intent, 0) + 1
        for obj in record.objections:
            objection_counts[obj] = objection_counts.get(obj, 0) + 1
        outcomes[record.outcome] = outcomes.get(record.outcome, 0) + 1

    total_messages = sum(r.message_count for r in records)

    return {
        "total_calls": len(records),
        "intents": dict(sorted(intents.items(), key=lambda x: x[1], reverse=True)),
        "top_objections": dict(sorted(objection_counts.items(), key=lambda x: x[1], reverse=True)),
        "outcomes": outcomes,
        "avg_messages_per_call": round(total_messages / len(records), 1) if records else 0
    }


@app.route("/export-csv")
@require_admin
def export_csv_endpoint():
    """Export call data as CSV (admin only)."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "call_sid", "phone", "start_time", "duration_seconds",
        "intent", "objections_count", "tire_size", "outcome", "message_count"
    ])
    writer.writeheader()

    for record in call_records.values():
        data = record.to_dict()
        writer.writerow({
            "call_sid": data["call_sid"],
            "phone": data["phone"],
            "start_time": data["start_time"],
            "duration_seconds": data["duration_seconds"],
            "intent": data["intent"],
            "objections_count": data["objections_count"],
            "tire_size": data["tire_size"],
            "outcome": data["outcome"],
            "message_count": data["message_count"]
        })

    return output.getvalue(), 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=publictires_calls.csv"
    }


@app.route("/analyze")
@require_admin
def analyze():
    """Analyze call topics (admin only)."""
    if not call_logs:
        return {"message": "No calls yet"}
    topics: dict = {}
    for log in call_logs:
        u = log["user"].lower()
        if any(w in u for w in ["prix", "combien", "coût", "cher"]):
            topics["prix"] = topics.get("prix", 0) + 1
        elif "install" in u:
            topics["installation"] = topics.get("installation", 0) + 1
        elif any(w in u for w in ["pneu", "tire"]):
            topics["pneus"] = topics.get("pneus", 0) + 1
        else:
            topics["autre"] = topics.get("autre", 0) + 1
    return {"total": len(call_logs), "topics": topics}


# ============================================================
# STARTUP CHECKS
# ============================================================

@app.before_request
def startup_check():
    """Run once: verify critical config."""
    if not hasattr(app, '_checked'):
        if not GEMINI_API_KEY:
            logger.critical("⚠️  GEMINI_API_KEY is NOT SET! Voice agent will use fallback responses.")
        if not TWILIO_AUTH_TOKEN:
            logger.warning("⚠️  TWILIO_AUTH_TOKEN not set — Twilio signature validation DISABLED.")
        app._checked = True


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting PublicTires Voice Agent V5.0 on port {port}")
    app.run(host="0.0.0.0", port=port)
