from flask import Flask, request
from markupsafe import escape
import subprocess
import requests
import RPi.GPIO as GPIO
from urllib.parse import quote
app = Flask(__name__)

SIGNER_CHECK_ARGS = ["/home/tezos/tezos/tezos-signer", "get", "ledger", "authorized", "path", "for" ]
CHECK_IP = "8.8.8.8"

GPIO.setmode(GPIO.BCM)
GPIO.setup(6, GPIO.IN)

@app.route('/statusz/<pubkey>')
def status(pubkey):
    # sanitize
    pubkey = escape(pubkey)
    signer_response = requests.get('http://localhost:8443/keys/%s' % pubkey)
    if signer_response:
        ledger_url = escape(request.args.get('ledger_url'))
        # sanitize
        # https://stackoverflow.com/questions/55613607/how-to-sanitize-url-string-in-python
        ledger_url = quote(ledger_url, safe='/:?&')
        ledger_response = subprocess.run(SIGNER_CHECK_ARGS + [ ledger_url ], capture_output=True)
        return signer_response.content + ledger_response.stdout + ledger_response.stderr, 200 if ledger_response.returncode == 0 else 500
    else:
        return signer_response.content, signer_response.status_code

@app.route('/healthz')
def healthz():
    ping_eth0 = subprocess.run([ "/bin/ping", "-I", "eth0", "-c1", CHECK_IP ])
    ping_eth1 = subprocess.run([ "/bin/ping", "-I", "eth1", "-c1", CHECK_IP ])
    return """
wired_network %s
wireless_network %s
power %s
""" % (ping_eth0.returncode, ping_eth1.returncode, GPIO.input(6))
