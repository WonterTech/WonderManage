#!/usr/bin/env python
"""Start the Work log as a real (production-style) local server.

    python serve.py            only this computer can reach it  -> http://127.0.0.1:8000
    python serve.py --lan      also devices on your home/office network -> http://<this PC's address>:8000
    python serve.py --tailscale   same, plus Tailscale devices from anywhere -> http://<Tailscale address>
    python serve.py --mode saved   use the mode chosen with network.bat (data/network_mode.txt)
    python serve.py --show         print the current mode and the addresses to type, then exit
    python serve.py --https        encrypted connection (padlock): https://... on port 443, plain http only redirects
    python serve.py --certs        show the certificate to install on devices, then exit
    python serve.py --port 9000

When started without a window (pythonw, see install_autostart.bat) everything it would print goes to data/server.log.
It backs up the database by itself: at start, every few hours (only if something changed) and when it stops.
"""
import argparse
import os
import socket
import stat
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["WORKLOG_SERVE"] = "1"   # tells the site it may offer the "Shut down server" button


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no traffic is sent; this just picks the right network card
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def tailscale_ip():
    """This computer's Tailscale address, if Tailscale is installed and connected."""
    import subprocess
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # no console flash when running without a window
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5, creationflags=flags)
        return out.stdout.split()[0] if out.returncode == 0 and out.stdout.split() else None
    except (OSError, subprocess.SubprocessError):
        return None


MODES = ("local", "lan", "tailscale", "tailscale-only")
MODE_LABELS = {
    "local": "This computer only",
    "lan": "Local network (Wi-Fi / cable)",
    "tailscale": "Tailscale + local network",
    "tailscale-only": "Tailscale ONLY (the local network is blocked)",
}


def read_https_saved():
    """True if network.bat turned the encrypted connection on (data/https.txt says 'on')."""
    try:
        return (data_dir() / "https.txt").read_text(encoding="utf-8").strip().lower() == "on"
    except OSError:
        return False


def base_url(host, https, port, https_port):
    if https:
        return f"https://{host}" + ("" if https_port == 443 else f":{https_port}")
    return f"http://{host}" + ("" if port == 80 else f":{port}")


def data_dir():
    """Same folder settings.py uses, worked out here without importing Django (settings freeze the mode on import)."""
    from pathlib import Path
    return Path(os.environ.get("WORKLOG_DATA_DIR", Path(__file__).resolve().parent / "data"))


def read_saved_mode():
    """The mode chosen with network.bat. Falls back to 'tailscale' (what worklog_hidden.vbs used to hard-code)."""
    try:
        value = (data_dir() / "network_mode.txt").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return "tailscale"
    return value if value in MODES else "tailscale"


def show_status(mode, port, https=False, https_port=443):
    name = os.environ.get("WORKLOG_NAME", "wondermanage").lower()
    url = lambda host: base_url(host, https, port, https_port)
    print(f"  Mode:           {MODE_LABELS[mode]}")
    print(f"  Encryption:     " + ("HTTPS on (padlock)" if https else "off (plain http)"))
    print(f"  Server:         {'RUNNING' if already_running(https_port if https else port) else 'not running'}")
    print(f"  This computer:  {url('localhost')}")
    if mode in ("lan", "tailscale"):
        ip = lan_ip()
        print(f"  Local network:  " + (url(ip) if ip else "(no network connection found)"))
        print(f"  Easy name:      {url(name + '.local')}")
    elif mode == "tailscale-only":
        print("  Local network:  blocked on purpose")
    if mode in ("tailscale", "tailscale-only"):
        ts = tailscale_ip()
        print(f"  Tailscale:      " + (url(ts) if ts else "(Tailscale not installed or not connected)"))


def already_running(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def use_log_file(settings):
    """With no console window (pythonw) there is nowhere to print, so write to data/server.log."""
    log = settings.DATA_DIR / "server.log"
    if log.exists() and log.stat().st_size > 1_000_000:
        log.replace(settings.DATA_DIR / "server.log.old")
    sys.stdout = sys.stderr = open(log, "a", buffering=1, encoding="utf-8")
    print(f"\n--- started {time.strftime('%Y-%m-%d %H:%M:%S')} ---")


def start_auto_backup(settings):
    from tracker.backups import make_backup

    def loop():
        while True:
            try:
                saved = make_backup()
                if saved:
                    print(f"Backup saved: {saved}", flush=True)
            except Exception as exc:
                print(f"Backup failed: {exc}", flush=True)
            time.sleep(settings.BACKUP_EVERY_HOURS * 3600)

    threading.Thread(target=loop, daemon=True, name="auto-backup").start()


def start_name_advertising(name, port):
    """Announce  <name>.local  on the network (mDNS) so devices can type it instead of the IP address.

    Runs in the background and re-announces if the computer's address changes or Wi-Fi connects late.
    """
    def loop():
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            print("Friendly name not available: run  venv\\Scripts\\pip install zeroconf  (see README).", flush=True)
            return
        zc = info = current = None
        while True:
            try:
                ip = lan_ip()
                if ip and ip != current:
                    if zc:
                        zc.unregister_service(info)
                        zc.close()
                    info = ServiceInfo(
                        "_http._tcp.local.", f"{name}._http._tcp.local.",
                        addresses=[socket.inet_aton(ip)], port=port, properties={}, server=f"{name}.local.",
                    )
                    zc = Zeroconf()
                    zc.register_service(info)
                    current = ip
                    print(f"Friendly name active: http://{name}.local  ->  {ip}", flush=True)
            except Exception as exc:
                print(f"Friendly name problem: {exc}", flush=True)
                zc = info = current = None
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="mdns").start()


def cert_identity(settings, mode):
    """The names and addresses the server certificate must cover right now."""
    names = [settings.SERVER_NAME + ".local", "localhost"]
    addresses = ["127.0.0.1", "::1"]
    if mode in ("lan", "tailscale"):
        addresses.append(lan_ip())
    if mode in ("tailscale", "tailscale-only"):
        addresses.append(tailscale_ip())
    return names, [a for a in addresses if a]


def start_cert_refresher(adapter, settings, mode):
    """If this computer's address changes (new network, Tailscale connecting), re-issue the certificate and use it
    straight away for new connections. No restart and nothing to reinstall on devices."""
    import certs

    def loop():
        while True:
            time.sleep(30)
            try:
                names, addresses = cert_identity(settings, mode)
                cert, key, changed = certs.ensure_server_cert(
                    settings.DATA_DIR, names, addresses, socket.gethostname(), settings.SERVER_NAME)
                if changed:
                    adapter.context.load_cert_chain(str(cert), str(key))
                    print(f"Certificate renewed for: {', '.join(names + addresses)}", flush=True)
            except Exception as exc:
                print(f"Certificate refresh problem: {exc}", flush=True)

    threading.Thread(target=loop, daemon=True, name="cert-refresh").start()


def start_http_redirect(host, port, https_port):
    """Plain-http port that does one thing: send the visitor to the https address (only for local visitors)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from tracker import security

    class Redirect(BaseHTTPRequestHandler):
        def _redirect(self):
            if not security._is_local(self.client_address[0]):
                return self.send_error(403)
            raw = (self.headers.get("Host") or "").strip()
            probe = type("Probe", (), {"META": {"HTTP_HOST": raw}})()
            if not raw or not security._host_is_local(probe):
                return self.send_error(400)
            name = raw[:raw.find("]") + 1] if raw.startswith("[") else raw.split(":")[0]
            target = f"https://{name}" + ("" if https_port == 443 else f":{https_port}") + self.path
            self.send_response(301)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD = _redirect

        def do_POST(self):
            self.send_error(405, "Use the https address")

        def log_message(self, *args):
            pass

    try:
        server = ThreadingHTTPServer((host, port), Redirect)
    except OSError as exc:
        print(f"Plain-http redirect not started on port {port}: {exc}", flush=True)
        return
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="http-redirect").start()


def show_certificates():
    """Tell the person which file to install on devices, and the fingerprint to check it against."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import certs
    folder = certs.certs_dir(data_dir())
    certs.ensure_ca(data_dir(), socket.gethostname(), os.environ.get("WORKLOG_NAME", "wondermanage").lower())
    print(f"  File to install on devices:\n    {folder / certs.EXPORT_FILE}\n")
    print("  Fingerprints, to compare on the device before trusting (Windows shows SHA-1, iPhone SHA-256):")
    print(f"    SHA-1:    {certs.fingerprint(data_dir(), 'sha1')}")
    print(f"    SHA-256:  {certs.fingerprint(data_dir())}\n")
    print("  Send ONLY that .crt file (USB stick, e-mail, WhatsApp). Never send ca.key.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lan", action="store_true", help="also accept other devices on your local network")
    parser.add_argument("--tailscale", action="store_true",
                        help="also accept visitors coming through your Tailscale network (implies --lan)")
    parser.add_argument("--mode", choices=MODES + ("saved",),
                        help="local | lan | tailscale, or 'saved' = whatever network.bat last chose")
    parser.add_argument("--show", action="store_true", help="print the current mode and addresses, then exit")
    parser.add_argument("--https", action="store_true", help="encrypted connection (needs the certificate installed on devices)")
    parser.add_argument("--https-port", type=int, default=443)
    parser.add_argument("--certs", action="store_true", help="show the certificate to install on devices, then exit")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.certs:
        show_certificates()
        return 0

    # --tailscale / --lan win over --mode; with nothing given the default stays "this computer only".
    if args.tailscale:
        mode = "tailscale"
    elif args.lan:
        mode = "lan"
    elif args.mode:
        mode = args.mode
    else:
        mode = "saved" if args.show else "local"
    from_saved = mode == "saved"
    if from_saved:
        mode = read_saved_mode()
    https = args.https or (from_saved and read_https_saved())     # "saved" also remembers the https choice
    args.lan = mode in ("lan", "tailscale", "tailscale-only")
    args.tailscale = mode in ("tailscale", "tailscale-only")

    if args.show:
        show_status(mode, args.port, https, args.https_port)
        return 0
    if args.tailscale:
        os.environ["WORKLOG_TAILSCALE"] = "1"
    if mode == "tailscale-only":
        os.environ["WORKLOG_TAILSCALE_ONLY"] = "1"
    if https:
        os.environ["WORKLOG_HTTPS"] = "1"

    listen_port = args.https_port if https else args.port
    if already_running(listen_port):
        print(f"Work log seems to be running already on port {listen_port}. Nothing to do.")
        return 0

    ip = lan_ip() if args.lan else None
    if args.lan:
        os.environ["WORKLOG_LAN"] = "1"
        hosts = [h for h in (ip, socket.gethostname(), socket.gethostname() + ".local") if h]
        existing = os.environ.get("WORKLOG_ALLOWED_HOSTS", "")
        os.environ["WORKLOG_ALLOWED_HOSTS"] = ",".join(filter(None, [existing] + hosts))

    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    if sys.stdout is None or sys.stderr is None:
        use_log_file(settings)

    # Bring the database up to date and gather the CSS/JS files (both are quick and safe to repeat).
    from tracker.backups import make_backup
    try:   # a safety copy before the database structure is touched by an update
        saved = make_backup()
        if saved:
            print(f"Backup saved: {saved}", flush=True)
    except Exception as exc:
        print(f"Backup before update failed: {exc}", flush=True)

    try:   # writes a new migration file only if the models changed (e.g. after an update)
        call_command("makemigrations", "tracker", interactive=False, verbosity=0)
    except Exception as exc:
        print(f"makemigrations problem: {exc}", flush=True)
    call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0)

    if os.name == "posix":   # keep the data folder and database private to your user account
        os.chmod(settings.DATA_DIR, stat.S_IRWXU)
        if settings.DB_PATH.exists():
            os.chmod(settings.DB_PATH, stat.S_IRUSR | stat.S_IWUSR)

    adapter = None
    if https:   # fail closed: if encryption was asked for and cannot start, do not quietly fall back to plain http
        try:
            import certs
            from cheroot.ssl.builtin import BuiltinSSLAdapter
            from cheroot.wsgi import Server
        except ImportError as exc:
            print(f"HTTPS needs two more packages ({exc.name}). Run start.bat once, or: venv\\Scripts\\pip install -r requirements.txt",
                  flush=True)
            return 1
        names, addresses = cert_identity(settings, mode)
        cert_file, key_file, _ = certs.ensure_server_cert(
            settings.DATA_DIR, names, addresses, socket.gethostname(), settings.SERVER_NAME)
        adapter = BuiltinSSLAdapter(str(cert_file), str(key_file))

    start_auto_backup(settings)
    if args.lan and mode != "tailscale-only":
        start_name_advertising(settings.SERVER_NAME, listen_port)

    from config.wsgi import application

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if https and args.port != args.https_port:
        if already_running(args.port):
            print(f"Port {args.port} is busy, so plain http will not redirect to https.", flush=True)
        else:
            start_http_redirect(host, args.port, args.https_port)
    url = lambda h: base_url(h, https, args.port, args.https_port)
    print(f"Work log is running ({MODE_LABELS[mode]}" + (", HTTPS" if https else ", plain http") + "). Press Ctrl+C to stop.")
    print(f"  This computer:  {url('localhost')}")
    if mode in ("lan", "tailscale"):
        print(f"  Your network:   {url(ip or '<this computer address>')}")
        print(f"  Easy name:      {url(settings.SERVER_NAME + '.local')}")
    if mode in ("tailscale", "tailscale-only"):
        ts = tailscale_ip()
        print(f"  Tailscale:      {url(ts or '<Tailscale address of this computer>')}")
    print(f"  Database:       {settings.DB_PATH}", flush=True)
    try:
        if https:
            import ssl
            try:
                adapter.context.minimum_version = ssl.TLSVersion.TLSv1_2
            except (AttributeError, ValueError):
                pass
            server = Server((host, args.https_port), application, numthreads=8, request_queue_size=64,
                            server_name="worklog")
            server.ssl_adapter = adapter
            start_cert_refresher(adapter, settings, mode)
            try:
                server.start()
            except KeyboardInterrupt:
                server.stop()
        else:
            from waitress import serve
            serve(application, host=host, port=args.port, threads=4)
    finally:
        from tracker.backups import make_backup
        try:
            make_backup()
        except Exception as exc:
            print(f"Backup on exit failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
