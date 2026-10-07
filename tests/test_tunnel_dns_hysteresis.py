from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_LOOP = ROOT / "scripts" / "health-loop.sh"
MOUNTS = (ROOT / "bootstrap" / "y700-mount.sh", ROOT / "scripts" / "mount-chroot.sh")
DNS = ROOT / "config" / "y700-resolv.conf"


class TunnelDnsAndHysteresisContractTests(unittest.TestCase):
    def test_managed_dns_avoids_observed_dead_resolver(self) -> None:
        text = DNS.read_text()
        self.assertIn("nameserver 8.8.8.8", text)
        self.assertIn("nameserver 8.8.4.4", text)
        self.assertNotIn("nameserver 114.114.114.114", text)
        self.assertIn("options timeout:1 attempts:2", text)

    def test_mount_prefers_explicit_override_then_git_managed_dns(self) -> None:
        for path in MOUNTS:
            text = path.read_text()
            self.assertIn("resolv.conf.override", text)
            self.assertIn("config/y700-resolv.conf", text)
            self.assertIn("DNS_LEGACY=/data/local/y700-linux/resolv.conf", text)
            self.assertLess(text.index('if [ -s "$DNS_OVERRIDE" ]'), text.index('elif [ -s "$DNS_MANAGED" ]'))
            self.assertLess(text.index('elif [ -s "$DNS_MANAGED" ]'), text.index('elif [ -s "$DNS_LEGACY" ]'))

    def test_remote_probe_hysteresis_only_applies_with_live_ha_connections(self) -> None:
        text = HEALTH_LOOP.read_text()
        self.assertIn("Y700_CLOUDFLARED_REMOTE_FAILURE_GRACE_CYCLES:-2", text)
        self.assertIn('required_grace_cycles="$DISCONNECTED_GRACE_CYCLES"', text)
        self.assertIn('[ "$tunnel_process" = HEALTHY ] && [ "$connections" -gt 0 ]', text)
        self.assertIn('required_grace_cycles="$REMOTE_FAILURE_GRACE_CYCLES"', text)
        self.assertIn('if [ "$disconnected_cycles" -lt "$required_grace_cycles" ]; then', text)
        self.assertIn("CLOUDFLARED_REMOTE_PROBE_GRACE", text)


if __name__ == "__main__":
    unittest.main()
