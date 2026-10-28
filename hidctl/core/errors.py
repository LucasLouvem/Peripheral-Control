"""Exceções do projeto. Todas herdam de ``HidctlError``."""


class HidctlError(Exception):
    """Base de todos os erros do hidctl."""


class DescriptorError(HidctlError):
    """Report descriptor HID malformado."""


class DiscoveryError(HidctlError):
    """Falha ao localizar o dispositivo/interface esperados."""


class NoDeviceFound(DiscoveryError):
    """Nenhum dispositivo com o VID:PID esperado."""


class RevisionMismatch(DiscoveryError):
    """VID:PID corretos, mas ``bcdDevice`` diferente do suportado."""


class DescriptorMismatch(DiscoveryError):
    """Nenhuma interface do dispositivo tem o descritor esperado."""


class AmbiguousDevice(DiscoveryError):
    """Mais de uma interface candidata; não há como escolher com segurança."""


class TransportError(HidctlError):
    """Falha de E/S com o nó hidraw."""


class PermissionDenied(TransportError):
    """Sem permissão para abrir o nó hidraw."""


class DeviceGone(TransportError):
    """O dispositivo foi desconectado ou o nó desapareceu."""


class IoFailure(TransportError):
    """Erro de E/S ou resposta de tamanho inesperado."""


class ProtocolError(HidctlError):
    """Resposta do dispositivo fora do formato esperado."""


class ValidationError(HidctlError):
    """Entrada rejeitada antes de qualquer envio ao dispositivo."""


class SessionError(HidctlError):
    """Violação de uma guarda de segurança da sessão."""
