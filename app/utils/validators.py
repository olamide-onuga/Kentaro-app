import re

def validate_password_strength(password):
    """
    Validate that password is at least 6 characters and includes both letters and numbers.
    Returns (is_valid: bool, error_message: str or None)
    """
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if not re.search(r'[a-zA-Z]', password):
        return False, "Password must include at least one letter."
    if not re.search(r'[0-9]', password):
        return False, "Password must include at least one number."
    return True, None
