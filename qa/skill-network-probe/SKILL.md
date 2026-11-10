---
name: skill-network-probe
description: Check curl and SSH availability inside the MOVo Skill sandbox and optionally probe network destinations.
version: 1.0.1
---

# Skill sandbox network probe

Use this Skill when an administrator asks whether the isolated Skill runtime has `curl` and the OpenSSH client, or whether it can reach a specified HTTP or SSH destination.

Run `sh scripts/probe.sh` from this Skill's directory. Report the command paths, version lines, and exit status exactly as printed.

For an HTTP connectivity check, pass a URL supplied by the administrator:

```sh
CURL_URL='https://example.com' sh scripts/probe.sh
```

For an SSH connectivity and authentication attempt, pass a destination supplied by the administrator:

```sh
SSH_TARGET='user@host.example' SSH_PORT=22 sh scripts/probe.sh
```

The SSH test may report authentication failure even when the network path and SSH handshake work. Do not claim that an authentication failure proves a network failure. Never ask for or print passwords or private keys.

The included `apt-packages.txt` marker triggers MOVo's separate Skill environment preparation. It requests no extra packages, so the probe checks whether `curl` and `ssh` were inherited from the sandbox base image.
