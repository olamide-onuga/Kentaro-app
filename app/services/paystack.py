import os
import json
import logging
import urllib.request
import urllib.error
from flask import current_app

PAYSTACK_API_BASE = "https://api.paystack.co"

# Default exchange rates for NGN-only Paystack merchant accounts.
# These are approximate rates and can be overridden via environment variables.
CURRENCY_TO_NGN_RATES = {
    'USD': 1500.0,
    'GBP': 1900.0,
    'EUR': 1600.0,
    'ZAR': 85.0,
    'KES': 11.5,
    'GHS': 95.0,
}


def get_paystack_secret_key():
    return current_app.config.get('PAYSTACK_SECRET_KEY') or os.environ.get('PAYSTACK_SECRET_KEY') or ''


def get_paystack_public_key():
    return current_app.config.get('PAYSTACK_PUBLIC_KEY') or os.environ.get('PAYSTACK_PUBLIC_KEY') or ''


def _get_ngn_rate(currency):
    """Get exchange rate from currency to NGN. Returns None if NGN already."""
    currency = (currency or 'NGN').upper()
    if currency == 'NGN':
        return None  # Already NGN, no conversion needed
    # Allow override via environment variable: e.g. PAYSTACK_RATE_USD=1550
    env_rate = os.environ.get(f'PAYSTACK_RATE_{currency}')
    if env_rate:
        try:
            return float(env_rate)
        except (ValueError, TypeError):
            pass
    return CURRENCY_TO_NGN_RATES.get(currency)


def _convert_to_ngn(amount, currency):
    """
    Convert an amount from a foreign currency to NGN for Nigerian merchant accounts.
    Returns (ngn_amount, original_currency, rate_used) or (amount, 'NGN', None) if already NGN.
    """
    currency = (currency or 'NGN').upper()
    if currency == 'NGN':
        return float(amount), 'NGN', None

    rate = _get_ngn_rate(currency)
    if rate is None:
        # Unknown currency, default to passing as-is (will likely fail at Paystack)
        logging.warning(f"No NGN conversion rate for currency: {currency}")
        return float(amount), currency, None

    ngn_amount = round(float(amount) * rate, 2)
    logging.info(f"Converted {amount} {currency} -> {ngn_amount} NGN (rate: {rate})")
    return ngn_amount, 'NGN', rate


def initialize_paystack_payment(email, amount, currency='NGN', reference=None, callback_url=None, metadata=None):
    """
    Initialize a Paystack transaction.
    amount: float/int in major currency units (e.g. 5000 for 5000 NGN or 50.00 USD)
    amount is converted to subunits (kobo/cents * 100).

    If the merchant only supports NGN and a foreign currency is passed,
    the amount is automatically converted to NGN using approximate rates.
    Original currency and amount are stored in metadata for record-keeping.

    Returns dict: {'status': bool, 'authorization_url': str, 'access_code': str,
                   'reference': str, 'message': str, 'converted_from': dict or None}
    """
    secret_key = get_paystack_secret_key()

    # Store original amount/currency for metadata
    original_amount = float(amount)
    original_currency = (currency or 'NGN').upper()

    # Convert non-NGN currencies to NGN for Nigerian merchant accounts
    converted_amount, effective_currency, rate_used = _convert_to_ngn(amount, currency)
    amount_subunits = int(round(converted_amount * 100))

    conversion_info = None
    if rate_used is not None:
        conversion_info = {
            'original_amount': original_amount,
            'original_currency': original_currency,
            'ngn_amount': converted_amount,
            'rate_used': rate_used
        }
        # Include conversion info in metadata
        if metadata is None:
            metadata = {}
        metadata['currency_conversion'] = conversion_info

    if not secret_key:
        logging.warning("PAYSTACK_SECRET_KEY is not set. Operating in sandbox fallback mode.")
        sep = '&' if (callback_url and '?' in callback_url) else '?'
        return {
            'status': True,
            'is_mock': True,
            'authorization_url': f"{callback_url}{sep}reference={reference}" if callback_url and reference else None,
            'access_code': f'acc_{reference}',
            'reference': reference,
            'message': 'Mock transaction initialized',
            'converted_from': conversion_info
        }

    url = f"{PAYSTACK_API_BASE}/transaction/initialize"
    payload = {
        'email': email,
        'amount': amount_subunits,
        'currency': effective_currency,
    }
    if reference:
        payload['reference'] = reference
    if callback_url:
        payload['callback_url'] = callback_url
    if metadata:
        payload['metadata'] = metadata

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'User-Agent': 'Kentaro-Fitness-Platform'
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get('status') and 'data' in res_data:
                return {
                    'status': True,
                    'is_mock': False,
                    'authorization_url': res_data['data'].get('authorization_url'),
                    'access_code': res_data['data'].get('access_code'),
                    'reference': res_data['data'].get('reference'),
                    'message': res_data.get('message', 'Success'),
                    'converted_from': conversion_info
                }
            return {
                'status': False,
                'message': res_data.get('message', 'Failed to initialize payment')
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        logging.error(f"Paystack HTTPError {e.code}: {err_body}")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get('message', str(e))
        except Exception:
            msg = str(e)
        return {'status': False, 'message': msg}
    except Exception as e:
        logging.error(f"Paystack initialize exception: {e}")
        return {'status': False, 'message': str(e)}


def verify_paystack_payment(reference):
    """
    Verify a transaction reference with Paystack.
    Returns dict: {'status': bool, 'data': dict or None, 'message': str}

    Mock / sandbox references are auto-approved without hitting the real API.
    Recognised mock prefixes: pstk_test_mock_, test_mock_, sandbox_sim_,
    and the app-generated pstk_pkg_ / pstk_offer_ prefixes (used by the
    "Simulate Instant Sandbox Payment" button on the checkout pages).
    """
    if not reference:
        return {'status': False, 'message': 'Missing payment reference'}

    # Accept any well-known sandbox / simulation reference without calling Paystack
    _SANDBOX_PREFIXES = (
        'pstk_test_mock_', 'test_mock_', 'sandbox_sim_',
        'pstk_pkg_', 'pstk_offer_',
    )
    if reference.startswith(_SANDBOX_PREFIXES):
        return {
            'status': True,
            'is_mock': True,
            'data': {
                'status': 'success',
                'reference': reference,
                'gateway_response': 'Successful (Sandbox Mock Mode)'
            },
            'message': 'Mock verification successful'
        }

    secret_key = get_paystack_secret_key()
    if not secret_key:
        logging.info("Paystack secret key not configured; verifying mock transaction.")
        return {
            'status': True,
            'is_mock': True,
            'data': {
                'status': 'success',
                'reference': reference,
                'gateway_response': 'Successful (Sandbox Test Mode)'
            },
            'message': 'Sandbox verification successful'
        }

    url = f"{PAYSTACK_API_BASE}/transaction/verify/{reference}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {secret_key}',
        'Content-Type': 'application/json',
        'User-Agent': 'Kentaro-Fitness-Platform'
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get('status') and res_data.get('data', {}).get('status') == 'success':
                return {
                    'status': True,
                    'is_mock': False,
                    'data': res_data['data'],
                    'message': 'Transaction verified successfully'
                }
            return {
                'status': False,
                'data': res_data.get('data'),
                'message': res_data.get('message', 'Transaction verification failed')
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        logging.error(f"Paystack verify HTTPError {e.code}: {err_body}")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get('message', str(e))
        except Exception:
            msg = str(e)
        return {'status': False, 'message': msg}
    except Exception as e:
        logging.error(f"Paystack verify exception: {e}")
        return {'status': False, 'message': str(e)}
