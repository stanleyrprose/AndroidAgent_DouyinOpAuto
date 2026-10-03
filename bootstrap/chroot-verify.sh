#!/system/bin/sh
ROOT=/data/local/y700-linux/rootfs
exec /system/bin/chroot "$ROOT" /bin/bash -lc '
set -e
printf "CHROOT_OK\n"
uname -m
cat /etc/os-release | head -3
printf "%s\n" "---VERSIONS---"
node --version
npm --version
python3 --version
git --version
curl --version | head -1
printf "%s\n" "---NETWORK---"
getent hosts deb.debian.org | head -2
curl -I --max-time 15 https://deb.debian.org/ 2>/dev/null | head -1
'
