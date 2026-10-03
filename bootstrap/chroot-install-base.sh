#!/system/bin/sh
ROOT=/data/local/y700-linux/rootfs
exec /system/bin/chroot "$ROOT" /usr/bin/dash -c 'export DEBIAN_FRONTEND=noninteractive; /usr/bin/apt-get install -y --no-install-recommends coreutils ca-certificates curl git python3 python3-pip nodejs npm procps iproute2; echo ---VERSIONS---; /usr/bin/node --version; /usr/bin/npm --version; /usr/bin/python3 --version; /usr/bin/git --version; /usr/bin/curl --version | /usr/bin/head -1'
