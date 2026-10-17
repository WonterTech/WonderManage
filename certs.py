"""Certificates for the encrypted (HTTPS) connection.

Why this exists: on plain http anyone on the same Wi-Fi can pose as the server, or read passwords as they travel.
HTTPS fixes that ONLY if devices can tell the real server from an impostor. So we do it properly:

  1. A private "certificate authority" (CA) is created once on this computer (data/certs/ca.crt + ca.key).
  2. You install ca.crt ONCE on each device that uses the Work log (see the README). Never send ca.key anywhere.
  3. The server's own certificate is signed by that CA and is re-issued automatically whenever this computer's
     network address changes (a new client's network, Tailscale connecting...), so devices never need touching again.

The CA is "name constrained": even if someone stole it, devices that trust it would accept certificates only for
your server's own name, localhost and private/Tailscale addresses, never for a real website such as your bank.
"""
import datetime
import hashlib
import ipaddress
import os
import shutil
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_FILE, CA_KEY = "ca.crt", "ca.key"
SERVER_FILE, SERVER_KEY = "server.crt", "server.key"
EXPORT_FILE = "WorkLog-install-on-devices.crt"      # the copy you hand to phones and computers (no secrets in it)

CA_YEARS = 10
SERVER_DAYS = 397            # under the 398-day limit browsers like
RENEW_BEFORE_DAYS = 30

# The only places the CA can vouch for: this computer's own name (chosen when the CA is created) and private addresses.
# (If you ever change WORKLOG_NAME, delete the data/certs folder so a matching CA is made, then reinstall it on devices.)
PERMITTED_NETWORKS = [
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10",
    "::1/128", "fd7a:115c:a1e0::/48",
]


def certs_dir(data_dir):
    path = Path(data_dir) / "certs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _save_key(path, key):
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _save_cert(path, cert):
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _load_cert(path):
    return x509.load_pem_x509_certificate(Path(path).read_bytes())


def _load_key(path):
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)


def _expires_soon(cert, days):
    return cert.not_valid_after_utc - _now() < datetime.timedelta(days=days)


# ------------------------------------------------------------------ the authority
def ensure_ca(data_dir, computer_name="this computer", server_name="wondermanage"):
    """Create the private CA the first time; afterwards reuse it. Returns (certificate, key)."""
    folder = certs_dir(data_dir)
    cert_path, key_path = folder / CA_FILE, folder / CA_KEY
    if cert_path.exists() and key_path.exists():
        cert = _load_cert(cert_path)
        if not _expires_soon(cert, 90):
            return cert, _load_key(key_path)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, f"Work log ({computer_name})"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Work log private CA"),
    ])
    constraints = x509.NameConstraints(
        permitted_subtrees=[x509.DNSName(f"{server_name.lower()}.local"), x509.DNSName("localhost")]
        + [x509.IPAddress(ipaddress.ip_network(n)) for n in PERMITTED_NETWORKS],
        excluded_subtrees=None,
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(days=1))
        .not_valid_after(_now() + datetime.timedelta(days=365 * CA_YEARS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(constraints, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _save_key(key_path, key)
    _save_cert(cert_path, cert)
    shutil.copyfile(cert_path, folder / EXPORT_FILE)
    return cert, key


def fingerprint(data_dir, algorithm="sha256"):
    """Fingerprint of the CA, to compare on a device before trusting it (Windows shows SHA-1, iPhone SHA-256)."""
    cert = _load_cert(certs_dir(data_dir) / CA_FILE)
    digest = hashlib.new(algorithm, cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


# ------------------------------------------------------------------ the server certificate
def _wanted_names(names, addresses, server_name="wondermanage"):
    allowed = {"localhost", f"{server_name.lower()}.local"}
    dns = sorted({n.lower() for n in names if n and n.lower() in allowed})
    allowed = [ipaddress.ip_network(n) for n in PERMITTED_NETWORKS]
    # An address the CA may not vouch for would make browsers reject the WHOLE certificate, so leave it out.
    ips = sorted({str(ip) for ip in (ipaddress.ip_address(a) for a in addresses if a)
                  if any(ip.version == net.version and ip in net for net in allowed)})
    return dns, ips


def _current_names(cert):
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return [], []
    return sorted(san.get_values_for_type(x509.DNSName)), sorted(str(i) for i in san.get_values_for_type(x509.IPAddress))


def ensure_server_cert(data_dir, names, addresses, computer_name="this computer", server_name="wondermanage"):
    """Make sure server.crt covers exactly these names and addresses. Returns (cert_path, key_path, changed)."""
    folder = certs_dir(data_dir)
    ca_cert, ca_key = ensure_ca(data_dir, computer_name, server_name)
    dns, ips = _wanted_names(names, addresses, server_name)
    cert_path, key_path = folder / SERVER_FILE, folder / SERVER_KEY
    if cert_path.exists() and key_path.exists():
        current = _load_cert(cert_path)
        if (_current_names(current) == (dns, ips) and not _expires_soon(current, RENEW_BEFORE_DAYS)
                and current.issuer == ca_cert.subject):
            try:
                current.verify_directly_issued_by(ca_cert)
                return cert_path, key_path, False
            except Exception:
                pass                                   # signed by an older CA: issue a fresh one below
    key = ec.generate_private_key(ec.SECP256R1())
    alt = [x509.DNSName(n) for n in dns] + [x509.IPAddress(ipaddress.ip_address(a)) for a in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, (dns or ["localhost"])[0])]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(hours=1))
        .not_valid_after(_now() + datetime.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _save_key(key_path, key)
    _save_cert(cert_path, cert)
    return cert_path, key_path, True
