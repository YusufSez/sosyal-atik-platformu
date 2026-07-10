import logging

logger = logging.getLogger("atikport.socket")


def _log_emit(event: str, room: str, **extra) -> None:
    logger.debug("SOCKET EMIT %s room=%s %s", event, room, extra or "")


def _log_socket(event: str, **extra) -> None:
    logger.debug("SOCKET %s %s", event, extra or "")
