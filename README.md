Tezos Remote signer OS
----------------------

This is an ansible manifest to turn a Raspberry Pi with Raspbian OS into a remote signer for the Tezos peer-to-peer cryptocurrency.

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

First, install [Raspberry Pi OS](https://www.raspberrypi.org/downloads/raspberry-pi-os/) with ssh access enabled. To enable ssh access, add a file named `ssh` to the boot partition.

The default credentials will be `pi`/`raspberry`.

You also need

* a Linux environment with ansible installed
* a ssh public/private keypair in your home direcroty `~/.ssh` folder

Edit the `inventory` file to set the ip address of your Pi.

Edit the tezos-remote-signer.yaml with the required parameters.

Download the ansible dependencies:

```
ansible-galaxy install -r requirements.yaml
```

Run the ansible fully automated install:

```
ansible-playbook tezos-remote-signer.yaml --inventory-file inventory
```

As part of the installation, it will remove the default `pi` user, add the `tezos` user, disable ssh password access, enable public-key ssh authentication as `tezos` user with the public key that is in your `~/.ssh` folder.

The first attempt will fail at that step since ansible is logged in as this user. Error will look like:

```
TASK [tezos-remote-signer : Remove the default raspbian user 'pi'] ***********************************************************************************************************************************************************************************************************************************************************
fatal: [192.168.X.X]: FAILED! => {"changed": false, "msg": "userdel: user pi is currently used by process 992\n", "name": "pi", "rc": 8}
```

At this point, edit your `inventory` file, comment out the following lines:

```
#ansible_ssh_user=pi
#ansible_ssh_pass=raspberry
```

And uncomment:

```
ansible_ssh_user=tezos
```

Then run ansible again:

```
ansible-playbook tezos-remote-signer.yaml --inventory-file inventory
```

At this point, it will perform a firewall configuration change that requires a reboot, then fail with the following:

```
TASK [tezos-remote-signer : Configure ufw defaults] **************************************************************************************************************************************************************************************************************************************************************************
failed: [192.168.X.X] (item={'direction': 'incoming', 'policy': 'deny'}) => {"ansible_loop_var": "item", "changed": false, "commands": ["/usr/sbin/ufw status verbose"], "item": {"direction": "incoming", "policy": "deny"}, "msg": "ERROR: problem running iptables: iptables v1.8.2 (legacy): can't initialize iptables table `filter': Table does not exist (do you need to insmod?)\nPerhaps iptables or your kernel needs to be upgraded.\n\n\n"}
failed: [192.168.X.X] (item={'direction': 'outgoing', 'policy': 'allow'}) => {"ansible_loop_var": "item", "changed": false, "commands": ["/usr/sbin/ufw status verbose"], "item": {"direction": "outgoing", "policy": "allow"}, "msg": "ERROR: problem running iptables: iptables v1.8.2 (legacy): can't initialize iptables table `filter': Table does not exist (do you need to insmod?)\nPerhaps iptables or your kernel needs to be upgraded.\n\n\n"}
```

At this point, login to the device;

```
ssh tezos@192.168.X.X
```

Then reboot:

```
sudo reboot
```

Then run ansible again:

```
ansible-playbook tezos-remote-signer.yaml --inventory-file inventory
```

It will run to completion. As it compiles Tezos on a very low-power CPU, it will take several hours to complete.

Set up the signers
==================

You need both Ledgers connected to your signers to be configured with the same recovery phrase, this way they sign the same account.

*This is your baking key. Keep it safe.*

Open the Ledgers' baking apps then issue the following commands:

```
tezos-signer list connected ledgers
```

It will give you a command with an animal menmonic address to import the key. Enter it in your terminal. Note that you need to import it to both the client and the signer.

```
tezos-signer import secret key ledger_tezos "ledger://<mnemonic>/ed25519/0'/0'" 
tezos-client import secret key ledger_tezos "ledger://<mnemonic>/ed25519/0'/0'" 
```

For each of these commands, you need to match the address displayed on the screen with the Ledger screen, then approve with the Ledger button.

You may replace the `0'/0'` value with `0'/1'` or more. This is useful when using the same setup with alphanet to use the same hardware but not the same keys.

Finally you need to set the ledger to bake for this key:

```
./tezos-client setup ledger to bake for ledger_tezos --main-chain-id NetXdQprcVkpaWU
```

Again you need to approve using the Ledger button.

Active services
===============

After setup is complete, check that all services are running:

```
service tezos-signer-forwarder status
service tezos-signer-wrapper status
service tezos-signer status
service isp-failover status
```

### Tezos-signer-forwarder

This service runs autossh to forward the signer port to a remote location. It also forwards the ssh port (so you can ssh to your signer remotely).

The remote location must run sshd.

### Tezos-signer-wrapper

This is a gunicorn server used as a wrapper around the tezos baker. It forwards most requests to the baker, but it also does these things:

* exposes a `healthz` endpoint with prometheus node exporter metrics, as well as special metrics related to the auxiliary LTE connection and the UPS hat
* verifies that the signer address is configured properly (key import commands have been run succesfully)
* exposes a `statusz` endpoint (see load balancing section below)

NOTE: if you are not using a UPS hat or LTE dongle, you may have to modify this script

NOTE: you can also bypass the wrapper script entirely and just forward the signer endpoint by modifying /etc/systemd/system/tezos-signer-forwarder.service to forward port 8442 instead of 8443

### Tezos-signer

The native `tezos-signer` daemon.

### isp-failover

A script that continuously pings the Internet from 2 interfaces and changes the default route when one is down. If you do not have an auxiliary internet connection, you may disable it.

Load balancing
==============

You may set up a load balancer and monitor the following status endpoint:

```
http://<signer_ip>:<signer_port>/statusz/<public key hash starting with tz...>?ledger_url=<encoded URI of the ledger url>
```

This endpoint will return 200 OK if and only if:

*the signer daemon is running and has the baker's public key has configured
* the Ledger is connected, baking app is open and configured to bake at the given URL.
