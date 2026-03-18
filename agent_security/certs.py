"""
Local PKI: Generates a CA and service TLS certificates for mTLS.
"""

import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from agent_config import security_settings

def _generate_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Generate a self-signed CA."""
    ca_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Agent OS CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "agent-os-ca"),
    ])
    ca_cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        ca_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True,
    ).sign(ca_key, hashes.SHA256())
    
    return ca_key, ca_cert

def _generate_service_cert(
    service_name: str, 
    ca_key: rsa.RSAPrivateKey, 
    ca_cert: x509.Certificate
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Generate a certificate signed by the CA for a service."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Agent OS Services"),
        x509.NameAttribute(NameOID.COMMON_NAME, service_name),
    ])
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        ca_cert.subject
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(service_name), x509.DNSName("localhost"), x509.DNSName("127.0.0.1")]),
        critical=False,
    ).sign(ca_key, hashes.SHA256())
    
    return key, cert

def ensure_certs():
    """Ensure CA and service certificates exist in the certs directory."""
    if not security_settings.tls_enabled:
        return
        
    certs_dir = security_settings.certs_dir
    os.makedirs(certs_dir, exist_ok=True)
    
    ca_key_path = os.path.join(certs_dir, "ca.key")
    ca_cert_path = os.path.join(certs_dir, "ca.crt")
    
    # Generate CA if missing
    if not os.path.exists(ca_key_path) or not os.path.exists(ca_cert_path):
        print("[security] Generating new CA...")
        ca_key, ca_cert = _generate_ca()
        
        with open(ca_key_path, "wb") as f:
            f.write(ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
            
        with open(ca_cert_path, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    else:
        # Load existing CA
        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
            )
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
            
    # Generate service certs
    for service in ["agent-app", "tools-api"]:
        key_path = os.path.join(certs_dir, f"{service}.key")
        cert_path = os.path.join(certs_dir, f"{service}.crt")
        
        if not os.path.exists(key_path) or not os.path.exists(cert_path):
            print(f"[security] Generating cert for {service}...")
            key, cert = _generate_service_cert(service, ca_key, ca_cert)
            
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
                
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

if __name__ == "__main__":
    ensure_certs()
