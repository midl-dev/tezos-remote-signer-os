Tezos Remote signer OS
----------------------

This is an ansible manifest to turn a Raspberry Pi with Ubuntu ARM64 OS into a remote signer for the Tezos peer-to-peer cryptocurrency.

The remote signer is connected to a Ledger Nano S running the [Tezos Baking app](https://github.com/obsidiansystems/ledger-app-tezos).

You need a Raspberry Pi 4 (we have seen problems with Ledger USB disconnects with Raspberry Pi 3).

To protect against power failures, you need a Uninterruptible Power Supply hat. We had good results with the [Geekworm x728](https://geekworm.com/products/raspberry-pi-x728-max-5-1v-8a-18650-ups-power-management-board).

Brought to you by MIDL.dev
--------------------------

<img src="midl-dev-logo.png" alt="MIDL.dev" height="100"/>

We can deploy and manage a remote signer connected to a complete Tezos baking infrastructure for you. [Hire us](https://midl.dev).

Features
========

* ssh tunneling of remote signer http endpoint
* autossh for automatically reestblishing ssh connection
* system daemons for automatically starting the signer at boot time
* firewalld rules to allow only the needed inbound connections
* interfaces well with [tezos-k8s](https://github.com/oxheadalpha/tezos-k8s).

Installation
============

We use [packer] to create a Micro SD image to burn to a card.

## Install Packer

[Follow instructions](https://developer.hashicorp.com/packer/tutorials/docker-get-started/get-started-install-cli).

## Install Packer-Builder-ARM
[Follow instructions](https://github.com/mkaczanowski/packer-builder-arm#quick-start).

## Prepare inventory file

Copy the `inventory-template.yaml` file to a location of your choice and fill in
the required data.

Some of the data is sensitive (ssh private keys, tezos private keys), act accordingly.

## Install 

Run the following command as root:

```
sudo packer build -var 'inventory_file=path/to/inventory.yaml' tezos_signer.pkr.hcl
```

## Burn image

```
sudo dd if=inventory.yaml-rpi-sd-card.img of=/dev/sdb status=progress
```

Note: make sure that your card is mounted as `/dev/sdb` or adapt the command.

Active services
===============

After setup is complete, check that all services are running:

```sh
service tezos-signer-forwarder status
service tezos-signer-wrapper status
service tezos-signer status
```

tezos-signer-forwarder
------------------------------

This service runs autossh to forward the signer port to a remote location. It also forwards the ssh port (so you can ssh to your signer remotely).

The remote location must run sshd.

tezos-signer-wrapper
------------------------------

This is a gunicorn server used as a wrapper around the tezos baker. It forwards most requests to the baker, but it also does these things:

* exposes a `healthz` endpoint with prometheus node exporter metrics, as well as special metrics related to the auxiliary LTE connection and the UPS hat
* verifies that the signer address is configured properly (key import commands have been run succesfully)
* exposes a `statusz` endpoint (see load balancing section below)

NOTE: if you are not using a UPS hat or LTE dongle, you may have to modify this script

NOTE: you can also bypass the wrapper script entirely and just forward the signer endpoint by modifying /etc/systemd/system/tezos-signer-forwarder.service to forward port 8442 instead of 8443

tezos-signer
------------------------------

The native `tezos-signer` daemon.

Load balancing
==============

You may set up a load balancer and monitor the following status endpoint:

```sh
http://<signer_ip>:<signer_port>/statusz/<public key hash starting with tz...>?ledger_url=<encoded URI of the ledger url>
```

This endpoint will return 200 OK if and only if:

* the signer daemon is running and has the baker's public key has configured
* the Ledger is connected (note that we don't check whether the baker app is open due to concurrency issues)
