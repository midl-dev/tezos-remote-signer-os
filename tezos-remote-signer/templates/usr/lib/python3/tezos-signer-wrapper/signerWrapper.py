# Copyright 2020 MIDL.dev

from flask import Flask, jsonify, request
from markupsafe import escape
import subprocess
from multiprocessing import Lock
import os
import json
import re
import requests
import RPi.GPIO as GPIO
from urllib.parse import quote
app = Flask(__name__)

# SIGNER_CHECK_ARGSSIGNER_CHECK_ARGS = ["/usr/bin/tezos-signer",
#                      "get", "ledger", "authorized", "path", "for"]
CHECK_IP = "8.8.8.8"
LOCAL_SIGNER_PORT = "8442"
LEDGER_USB_IDENTIFIERS = [ b"2c97:0001", b"2c97:0005" ]

GPIO.setmode(GPIO.BCM)
GPIO.setup(6, GPIO.IN)
FNULL = open(os.devnull, 'w')

lock = Lock()


def is_ledger_connected_and_unlocked():
    """
    From https://stackoverflow.com/a/8265634/207209
    """
    device_re = re.compile(
        b"Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)$", # noqa
        re.I)
    df = subprocess.check_output("lsusb")
    devices = []
    for i in df.split(b'\n'):
        if i:
            info = device_re.match(i)
            if info:
                dinfo = info.groupdict()
                bus_info, device_info = dinfo.pop('bus'), dinfo.pop('device')
                dinfo['device'] = f"/dev/bus/usb/{bus_info}/{device_info}"
                devices.append(dinfo)

    return len([d for d in devices if d["id"] in LEDGER_USB_IDENTIFIERS]) == 1


# Bug in gunicorn/wsgi. The tezos signer uses chunked encoding which is
# not handled properly unless you do this.
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
    Returns 200 if all confitions above are met.

    We no longer check if ledger is authorized to bake because it tends
    to freeze the daemon. The locking logic is left here just in case
    we somehow get 2 concurrent requests or one freezes.
    '''
    with lock:
        # sanitize
        pubkey = escape(pubkey)
        signer_resp = requests.get(
            f"http://localhost:{LOCAL_SIGNER_PORT}/keys/{pubkey}"
        )
        if signer_resp:
            ledger_url = escape(request.args.get('ledger_url'))
            # sanitize
            # https://stackoverflow.com/questions/55613607/how-to-sanitize-url-string-in-python
            ledger_url = quote(ledger_url, safe='/:?&')
            with open("/home/tezos/.tezos-signer/secret_keys") as json_file:
                signer_data = json.load(json_file)
            signer_conf = next((item for item in signer_data
                                if item["name"] == "ledger_tezos"))

            if not signer_conf or signer_conf["value"] != ledger_url:
                print(f"""
                    Mismatch found between local ledger url and remote one:
                    Value found in ~/.tezos-signer: {signer_conf['value']},
                    value found in LB request URL: {ledger_url}
                """)
                err_msg = ("Ledger URL mismatch, "
                           "check tezos-signer-forwarder logs on signer")
                return err_msg, 500

            if not is_ledger_connected_and_unlocked():
                return "Ledger not connected or not unlocked", 500

    return signer_resp.content, signer_resp.status_code


@app.route('/healthz')
def healthz():
    '''
    Health metrics
    '''
    wired_interface_name = os.getenv("WIRED_INTERFACE_NAME")
    wireless_interface_name = os.getenv("WIRELESS_INTERFACE_NAME")
    ping_wired = subprocess.run(
        ["/bin/ping", "-I", wired_interface_name, "-c1", CHECK_IP],
        stdout=FNULL
    )
    ping_wireless = subprocess.run(
        ["/bin/ping", "-I", wireless_interface_name, "-c1", CHECK_IP],
        stdout=FNULL
    )
    node_exporter_metrics = requests.get('http://localhost:9100/metrics').\
        content.decode("utf-8")

    health_msg = f"""
# HELP wired_network Status of the wired network.
# 0 if it can ping google. 1 if it cannot.
# TYPE wired_network gauge
wired_network {ping_wired.returncode}

# HELP wireless_network Status of the 4g backup connection.
# TYPE wireless_network gauge
wireless_network {ping_wireless.returncode}

# HELP power state of the wall power for the signer.
# 0 means that it has wall power, anything else means it is on battery.
# TYPE power gauge
power {GPIO.input(6)}

{node_exporter_metrics}
"""
    return health_msg


@app.route('/keys/<pubkey>', methods=['POST'])
def sign(pubkey):
    '''
    This request locks the daemon, because it uses Ledger to sign.
    Healthcheck also uses ledger, and ledger doesn't multiplex.
    '''
    with lock:
        signer_resp = requests.post(
            'http://localhost:%s/keys/%s' % (LOCAL_SIGNER_PORT, pubkey),
            json.dumps(request.json))

    return jsonify(json.loads(signer_resp.content)), signer_resp.status_code


@app.route('/', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST'])
def catch_all(path):
    '''
    For any other request, simply forward to remote signer daemon
    Future proof.
    '''
    if request.method == 'POST':
        signer_resp = requests.post(
            'http://localhost:%s/%s' % (LOCAL_SIGNER_PORT, path),
            json.dumps(request.json))
    else:
        signer_resp = requests.get(
            'http://localhost:%s/%s' % (LOCAL_SIGNER_PORT, path))

    return jsonify(json.loads(signer_resp.content)), signer_resp.status_code
