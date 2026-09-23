"""Identity of the original upload, before Excel parsing or normalization."""
import base64
import binascii
import hashlib

from .parser import ImportValidationError, WorkbookReader


def uploaded_file(encoded):
    if not encoded:
        raise ImportValidationError('Seleccione un archivo Excel.')
    if len(encoded) > ((WorkbookReader.MAX_BYTES + 2) // 3) * 4:
        raise ImportValidationError('El archivo supera el límite de 25 MB.')
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ImportValidationError('El contenido del archivo no es válido.') from exc
    if not content:
        raise ImportValidationError('El archivo está vacío.')
    if len(content) > WorkbookReader.MAX_BYTES:
        raise ImportValidationError('El archivo supera el límite de 25 MB.')
    return content, hashlib.sha256(content).hexdigest()
