# SSH plane

The Y700 runs OpenSSH inside the Debian chroot for direct shell access when the tablet moves between Wi-Fi networks or a phone hotspot.

## Server policy

- TCP port: 2222
- IPv4 listener
- root login: public key only
- password and keyboard-interactive authentication: disabled
- agent forwarding: disabled
- TCP forwarding: disabled
- SSH tunneling: disabled
- SFTP: internal-sftp
- authorized key material is local-only and ignored by Git

## Files

- `config/sshd_config`
- `scripts/start-sshd.sh`
- `scripts/ssh-status.sh`
- `scripts/boot-start.sh` wires SSH into boot persistence

## Verification

```bash
/usr/sbin/sshd -t -f config/sshd_config
bash scripts/ssh-status.sh
```

The status script reports the current WLAN address and key fingerprint locally. Those runtime values should not be copied into public documentation.
