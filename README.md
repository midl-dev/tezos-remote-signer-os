Tezos Remote signer OS
----------------------

This is an ansible manifest to turn a Raspberry Pi with Ubuntu ARM64 OS into a remote signer for the Tezos peer-to-peer cryptocurrency.

The remote signer is connected to a Ledger Nano S running the [Tezos Baking app](https://github.com/obsidiansystems/ledger-app-tezos).

You need a Raspberry Pi 4 (we have seen problems with Ledger USB disconnects with Raspberry Pi 3).

To protect against power failures, you need a Uninterruptible Power Supply hat. We had good results with the [Geekworm x728](https://geekworm.com/products/raspberry-pi-x728-max-5-1v-8a-18650-ups-power-management-board).

You also need a USB 4G Dongle to protect against losses of wired Internet. We had good results with the [Huawei E3372](https://www.amazon.com/Huawei-E3372h-153-Unlocked-Europe-Middle/dp/B01N6P3HI2).

In the US, a Google Fi subscription comes in handy as they will ship you up to 10 SIM cards at no cost, which is perfect for this purpose.

Brought to you by MIDL.dev
--------------------------

<img src="midl-dev-logo.png" alt="MIDL.dev" height="100"/>

We can deploy and manage a remote signer connected to a complete Tezos baking infrastructure for you. [Hire us](https://midl.dev).

Features
========

* ssh tunneling of remote signer http endpoint
* autossh for automatically reestblishing ssh connection
* system daemons for automatically starting the signer at boot time
* firewalld rules to allow just the needed inbound connections
* interfaces well with [tezos-remote-signer-forwarder](https://github.com/midl-dev/tezos-on-gke/tree/master/docker/tezos-remote-signer-forwarder) from [Tezos-on-GKE](https://github.com/midl-dev/tezos-on-gke/tree/master/docker/tezos-remote-signer-forwarder) project.

Installation
============

Install Base OS on remote singer
--------------------------------

First, [install Ubuntu on a Raspberry Pi](https://ubuntu.com/download/raspberry-pi).

The default credentials will be `ubuntu`/`ubuntu`, ssh to it and in first login you will be forced to change password, keep that one in mind as you will need it in steps below.

You also need

* a Linux environment with ansible installed
* a ssh public/private keypair in your home direcroty `~/.ssh` folder

Create `inventory` file baesd on the `inventory-template` to set the ip address of your Pi.

Create `tezos-remote-signer.yaml` file based on `tezos-remote-signer-vars-template.yaml` with the required parameters.

Download the ansible dependencies:

```sh
ansible-galaxy install -r requirements.yaml
ansible-galaxy collection install -r requirements.yaml
```

Bootstrap remote signer
-----------------------

```sh
ansible-playbook tezos-remote-signer-bootstrap.yaml -e "ansible_ssh_user=ubuntu" -e "ansible_ssh_pass=<password_you_changed_after first_login>" --inventory-file inventory
```

The bootstrap procedure will add the `tezos` user, disable ssh password access, enable public-key ssh authentication as `tezos` user with the public key that is in your `~/.ssh` folder.

Install remote signer services
------------------------------

> As `ubuntu` is the user to execute the reboot task during remote-signer bootstrap, sshd would still cache the logged in `ubuntu` user after bootstrap.
>
> At the beginning of this step, you need to login manually as `tezos` user and reboot the remote signer so `ubuntu` user wouldn't be cached by sshd and can be deleted successfully in the following steps..

The service installation procedure will remove the default `ubuntu` user and install all remote signer services.

Run the ansible fully automated install:

```sh
ansible-playbook tezos-remote-signer.yaml -e @tezos-remote-signer-vars.yaml  --inventory-file inventory
```

Set up the signers
==================

You need both Ledgers connected to your signers to be configured with the same recovery phrase, this way they sign the same account.

*This is your baking key. Keep it safe.*

Open the Ledgers' baking apps then issue the following commands:

```sh
tezos-signer list connected ledgers
```

It will give you a command with an animal menmonic address to import the key. Enter it in your terminal. Note that you need to import it to both the client and the signer.

```sh
tezos-signer import secret key ledger_tezos "ledger://<mnemonic>/ed25519/0'/0'" 
tezos-client import secret key ledger_tezos "ledger://<mnemonic>/ed25519/0'/0'" 
```

For each of these commands, you need to match the address displayed on the screen with the Ledger screen, then approve with the Ledger button.

You may replace the `0'/0'` value with `0'/1'` or more. This is useful when using the same setup with alphanet to use the same hardware but not the same keys.

Finally you need to set the ledger to bake for this key:

```sh
./tezos-client setup ledger to bake for ledger_tezos --main-chain-id NetXdQprcVkpaWU
```

Again you need to approve using the Ledger button.

Import tezos ledger using ansible
---------------------------------

You can import the tezos signer configuration using ansible by setting `import_tezos_ledger: True` in `tezos-remote-signer-vars.yaml` with required variables

```yaml
import_tezos_ledger: True
tezos_ledger_url: <tezos ledger url to be imported>
tezos_public_key: <public key on ledger to be imported>
tezos_public_key_hash: <public key hash to be imported>
```

This way, there is no need to run the command `tezos-client import secret key` to add the Ledger's address to the signer's known addresses.

Active services
===============

After setup is complete, check that all services are running:

```sh
service tezos-signer-forwarder status
service tezos-signer-wrapper status
service tezos-signer status
service isp-failover status
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

isp-failover
------------------------------

A script that continuously pings the Internet from 2 interfaces and changes the default route when one is down. If you do not have an auxiliary internet connection, you may disable it.

Load balancing
==============

You may set up a load balancer and monitor the following status endpoint:

```sh
http://<signer_ip>:<signer_port>/statusz/<public key hash starting with tz...>?ledger_url=<encoded URI of the ledger url>
```

This endpoint will return 200 OK if and only if:

* the signer daemon is running and has the baker's public key has configured
* the Ledger is connected (note that we don't check whether the baker app is open due to concurrency issues)
