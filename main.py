#!/usr/bin/env python3
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "PublicTires Voice Agent Online ✓"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
