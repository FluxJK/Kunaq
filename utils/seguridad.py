import hashlib
from cryptography.fernet import Fernet

class SeguridadKunaq:
    """Clase utilitaria para cumplir con la Ley N.° 29733 de Protección de Datos Personales."""
    
    def __init__(self, key: bytes):
        self._cipher = Fernet(key) # Encapsulamiento de la llave criptográfica

    def hashear_dni(self, dni: str) -> str:
        """Aplica SHA-256 para anonimización del DNI en búsquedas."""
        try:
            return hashlib.sha256(dni.encode('utf-8')).hexdigest()
        except Exception as e:
            print(f"Error al procesar el DNI: {e}")
            return None

    def encriptar_historial(self, texto_plano: str) -> bytes:
        """Cifrado en reposo para datos médicos sensibles (AES-256)."""
        try:
            return self._cipher.encrypt(texto_plano.encode('utf-8'))
        except Exception as e:
            print(f"Error de encriptación: {e}")
            return b""

    def desencriptar_historial(self, texto_cifrado: bytes, rol_usuario: str) -> str:
        """Desencripta solo si el rol está autorizado (Médico)."""
        try:
            if rol_usuario not in ["MEDICO", "ADMIN"]:
                raise PermissionError("Acceso denegado según Ley 29733.")
            return self._cipher.decrypt(texto_cifrado).decode('utf-8')
        except Exception as e:
            return f"Dato protegido / Error: {e}"