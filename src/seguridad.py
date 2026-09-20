import hashlib

class SeguridadesDatos:
    @staticmethod
    def anonimizar_dni(dni: str) -> str:
        """
        Genera un hash SHA-256 a partir del DNI en texto plano y retorna
        los primeros 16 caracteres hexadecimales para preservar la confidencialidad.
        """
        return hashlib.sha256(dni.encode('utf-8')).hexdigest()[:16]