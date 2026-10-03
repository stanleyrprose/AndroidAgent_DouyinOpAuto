#!/system/bin/sh
ROOT=/data/local/y700-linux/rootfs
exec /system/bin/chroot "$ROOT" /usr/bin/dash -c '
echo "APT/DKPG";
ps aux 2>/dev/null | grep -E "[a]pt|[d]pkg" || true;
dpkg --audit 2>/dev/null || true;
echo "---TOOLS---";
for x in sed node npm python3 git curl; do command -v "$x" 2>/dev/null || true; done;
node --version 2>/dev/null || true;
npm --version 2>/dev/null || true;
python3 --version 2>/dev/null || true;
git --version 2>/dev/null || true;
'
