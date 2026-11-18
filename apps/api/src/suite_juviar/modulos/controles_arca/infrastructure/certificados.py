"""Clave privada y pedido de certificado (CSR) para ARCA, generados en el servidor."""

from __future__ import annotations

import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ..domain.modelos import DatosCertificado


class CertificadosRSA:
    def generar_pedido(self, cuit: str, alias: str, organizacion: str) -> tuple[str, str]:
        clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        sujeto = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organizacion),
            x509.NameAttribute(NameOID.COMMON_NAME, alias),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}"),
        ])
        csr = x509.CertificateSigningRequestBuilder().subject_name(sujeto).sign(clave, hashes.SHA256())
        clave_pem = clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()
        return clave_pem, csr.public_bytes(serialization.Encoding.PEM).decode()

    def leer_certificado(self, certificado_pem: str, clave_pem: str) -> DatosCertificado:
        try:
            certificado = x509.load_pem_x509_certificate(certificado_pem.strip().encode())
        except ValueError as exc:
            raise ValueError("No se pudo leer el certificado: subí el archivo .crt que te dio ARCA.") from exc
        clave = serialization.load_pem_private_key(clave_pem.encode(), password=None)
        publica = serialization.PublicFormat.SubjectPublicKeyInfo
        if (certificado.public_key().public_bytes(serialization.Encoding.DER, publica)
                != clave.public_key().public_bytes(serialization.Encoding.DER, publica)):
            raise ValueError("El certificado no corresponde al pedido generado en Gestión.")
        serie = certificado.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
        cuit = re.sub(r"\D", "", str(serie[0].value)) if serie else ""
        return DatosCertificado(cuit, certificado.subject.rfc4514_string(), certificado.not_valid_after_utc)
