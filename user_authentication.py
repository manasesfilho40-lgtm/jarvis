# user_authentication.py
# NOTA: stub nao implementado. Para usar autenticacao real:
# 1. Implemente um banco de usuarios (sqlite ou similar)
# 2. Use hashlib/bcrypt para hash de senhas
# 3. Conecte ao event_bus para notificar login/logout

import logging

logger = logging.getLogger("user_auth")


def authenticate_user(username, password):
    logger.warning("authenticate_user chamado mas nao implementado")
    return True


def create_user(username, password, email=None):
    logger.warning("create_user chamado mas nao implementado")
    return True


def reset_password(username, new_password):
    logger.warning("reset_password chamado mas nao implementado")
    return True