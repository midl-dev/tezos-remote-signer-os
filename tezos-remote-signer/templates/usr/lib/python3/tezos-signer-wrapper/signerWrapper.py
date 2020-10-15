# Copyright 2020 MIDL.dev

from flask import Flask, jsonify, request
from markupsafe import escape
import subprocess
from multiprocessing import Lock
import os
import json
import requests
import RPi.GPIO as GPIO
from urllib.parse import quote
app = Flask(__name__)

SIGNER_CHECK_ARGS = ["/home/tezos/tezos/tezos-signer", "get", "ledger", "authorized", "path", "for" ]
CHECK_IP = "8.8.8.8"
LOCAL_SIGNER_PORT="8442"

GPIO.setmode(GPIO.BCM)
GPIO.setup(6, GPIO.IN)
FNULL = open(os.devnull, 'w')

lock = Lock()

# Bug in gunicorn/wsgi. The tezos signer uses chunked encoding which is not handled properly
# unless you do this.
# https://github.com/benoitc/gunicorn/issues/1733#issuecomment-377000612
@app.before_request
def handle_chunking():
    """
    Sets the "wsgi.input_terminated" environment flag, thus enabling
    Werkzeug to pass chunked requests as streams.  The gunicorn server
    should set this, but it's not yet been implemented.
    """

    transfer_encoding = request.headers.get("Transfer-Encoding", None)
    if transfer_encoding == u"chunked":
        request.environ["wsgi.input_terminated"] = True

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

    This request locks the daemon, because it interacts with the ledger.
    If it's running, we wait for it to complete before we sign anything.
    Otherwise, signature may fail.
    '''
    with lock:
        # sanitize
        pubkey = escape(pubkey)
        signer_response = requests.get('http://localhost:%s/keys/%s' % (LOCAL_SIGNER_PORT, pubkey))
        if signer_response:
            ledger_url = escape(request.args.get('ledger_url'))
            # sanitize
            # https://stackoverflow.com/questions/55613607/how-to-sanitize-url-string-in-python
            ledger_url = quote(ledger_url, safe='/:?&')
            with open("/home/tezos/.tezos-signer/secret_keys") as json_file:
                signer_data = json.load(json_file)
            signer_conf =  next((item for item in signer_data if item["name"] == "ledger_tezos"))
            if not signer_conf or signer_conf["value"] != ledger_url:
                return "Misconfigured signer", 500
            ledger_response = subprocess.run(SIGNER_CHECK_ARGS + [ ledger_url ], timeout=10, capture_output=True)
            return_data = signer_response.content + ledger_response.stdout + ledger_response.stderr, 200 if ledger_response.returncode == 0 else 500
        else:
            return_data = signer_response.content, signer_response.status_code
    return return_data

@app.route('/healthz')
def healthz():
    '''
    Health metrics
    '''
    ping_eth0 = subprocess.run([ "/bin/ping", "-I", "eth0", "-c1", CHECK_IP ], timeout=10, stdout=FNULL)
    ping_eth1 = subprocess.run([ "/bin/ping", "-I", "eth1", "-c1", CHECK_IP ], timeout=10, stdout=FNULL)
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
""" % (ping_eth0.returncode, ping_eth1.returncode, GPIO.input(6), node_exporter_metrics)

@app.route('/keys/<pubkey>', methods=['POST'])
def sign(pubkey):
    '''
    This request locks the daemon, because it uses Ledger to sign.
    Healthcheck also uses ledger, and ledger doesn't multiplex.
    '''
    with lock:
        signer_response = requests.post('http://localhost:%s/keys/%s' % (LOCAL_SIGNER_PORT, pubkey), json.dumps(request.json))
    return  jsonify(json.loads(signer_response.content)), signer_response.status_code

@app.route('/', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST'])
def catch_all(path):
    '''
    For any other request, simply forward to remote signer daemon
    Future proof.
    '''
    if request.method == 'POST':
        signer_response = requests.post('http://localhost:%s/%s' % (LOCAL_SIGNER_PORT, path), json.dumps(request.json))
    else:
        signer_response = requests.get('http://localhost:%s/%s' % (LOCAL_SIGNER_PORT, path) )
    return  jsonify(json.loads(signer_response.content)), signer_response.status_code

