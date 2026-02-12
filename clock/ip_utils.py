"""
IP validation utilities for anti-fraud location verification.
"""

import ipaddress
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Get the real client IP address from the request.

    Priority:
    1. X-Real-IP (set by Nginx, trusted)
    2. X-Forwarded-For first IP (if behind proxy)
    3. REMOTE_ADDR (direct connection)

    In production, Nginx should be configured to set X-Real-IP
    to the actual client IP, overwriting any spoofed headers.
    """
    # Priority 1: X-Real-IP from Nginx
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        try:
            ipaddress.ip_address(x_real_ip)
            return x_real_ip
        except ValueError:
            logger.warning(f"Invalid X-Real-IP: {x_real_ip}")

    # Priority 2: X-Forwarded-For (first IP)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP (client's IP)
        first_ip = x_forwarded_for.split(',')[0].strip()
        try:
            ipaddress.ip_address(first_ip)
            return first_ip
        except ValueError:
            logger.warning(f"Invalid X-Forwarded-For: {first_ip}")

    # Priority 3: Direct connection
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def is_ip_allowed(client_ip, allowed_list):
    """
    Check if a client IP is in the allowed list.

    Args:
        client_ip: String IP address of the client
        allowed_list: List of allowed IPs or CIDR ranges
                     e.g., ["85.123.45.67", "192.168.1.0/24"]

    Returns:
        True if the IP is allowed, False otherwise
    """
    if not allowed_list:
        logger.warning("Empty allowed IP list")
        return False

    try:
        client_addr = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.error(f"Invalid client IP: {client_ip}")
        return False

    for allowed in allowed_list:
        try:
            if '/' in allowed:
                # CIDR range
                network = ipaddress.ip_network(allowed, strict=False)
                if client_addr in network:
                    return True
            else:
                # Single IP
                if client_addr == ipaddress.ip_address(allowed):
                    return True
        except ValueError as e:
            logger.warning(f"Invalid entry in whitelist: {allowed} - {e}")
            continue

    logger.info(f"IP {client_ip} not in whitelist: {allowed_list}")
    return False


def validate_location_access(request, location):
    """
    Validate that a request comes from an allowed IP for a location.

    Args:
        request: Django request object
        location: Location model instance

    Returns:
        Tuple of (is_allowed: bool, client_ip: str, error_message: str or None)
    """
    client_ip = get_client_ip(request)

    if not location.is_active:
        return False, client_ip, "Este local no está activo"

    if not location.allowed_ips:
        return False, client_ip, "No hay IPs configuradas para este local"

    if is_ip_allowed(client_ip, location.allowed_ips):
        return True, client_ip, None

    return False, client_ip, (
        "No puedes fichar desde fuera del local. "
        "Asegúrate de estar conectado al Wi-Fi del establecimiento."
    )
