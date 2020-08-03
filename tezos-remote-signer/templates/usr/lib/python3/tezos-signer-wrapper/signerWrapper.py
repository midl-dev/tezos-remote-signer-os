# Copyright 2020 MIDL.dev

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
def statusz(pubkey):
    '''
    Status of the remote signer
    Checks:
    * whether signer daemon is up
    * whether signer daemon knows about the key passed as parameter
    * whether ledger is connected and unlocked
    * whether ledger baking app is on
    * whether baking app is configured to bake for URL passed as parameter
    Returns 200 iif all confitions above are met.
    '''
    # sanitize
    pubkey = escape(pubkey)
    signer_response = requests.get('http://localhost:8442/keys/%s' % pubkey)
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
    '''
    Health metrics
    '''
    ping_eth0 = subprocess.run([ "/bin/ping", "-I", "eth0", "-c1", CHECK_IP ])
    ping_eth1 = subprocess.run([ "/bin/ping", "-I", "eth1", "-c1", CHECK_IP ])
    node_exporter_metrics = requests.get('http://localhost:9100/metrics').content.decode("utf-8")
    return """# HELP wired_network Status of the wired network. 0 if it can ping google. 1 if it cannot.
# TYPE wired_network gauge
wired_network %s
# HELP wireless_network Status of the 4g backup connection.
# TYPE wireless_network gauge
wireless_network %s
# HELP power state of the wall power for the signer. 0 means that it currently has wall power. anything else means it is on battery.
# TYPE power gauge
power %s
%s
""" % (ping_eth0.returncode, ping_eth1.returncode, GPIO.input(6), strnode_exporter_metrics)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    '''
    For any other request, simply forward to remote signer daemon
    '''
    signer_response = requests.get('http://localhost:8442/%s' % path )
    return  signer_response.content, signer_response.status_code
