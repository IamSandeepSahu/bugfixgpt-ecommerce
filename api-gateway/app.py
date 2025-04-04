import os
import json
import logging
import requests
import structlog
from flask import Flask, jsonify, request, Response
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("/logs/api_gateway.log"),
        logging.StreamHandler()
    ]
)
logger = structlog.get_logger()

app = Flask(__name__)

# Get service URLs from environment variables
services = {
    'products': os.environ.get('SERVICE_PRODUCTS', 'http://products:5000'),
    'orders': os.environ.get('SERVICE_ORDERS', 'http://orders:5001'),
    'users': os.environ.get('SERVICE_USERS', 'http://users:5002'),
    'payments': os.environ.get('SERVICE_PAYMENTS', 'http://payments:5003'),
    'inventory': os.environ.get('SERVICE_INVENTORY', 'http://inventory:5004')
}

# BUG: Missing check for the 'service' key in request_timeout function
# INTRODUCING ANOTHER BUG: Removing inventory from timeouts dict to cause KeyError
def request_timeout(service):
    # BUG: Inventory service is missing from timeouts dict
    timeouts = {
        'products': 2.0,
        'orders': 5.0,
        'users': 1.0,
        'payments': 10.0
        # 'inventory': 3.0  # BUG: Intentionally removed inventory timeout
    }
    # Logs the error to make it easier to detect
    if service not in timeouts:
        error_msg = f'{{"error": "Timeout not configured", "service": "{service}"}}'
        logger.error(error_msg)
    return timeouts[service]  # Will raise KeyError if service not in timeouts

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "services": list(services.keys())})

@app.route('/<service>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def route_request(service, path):
    if service not in services:
        error_msg = f'{{"error": "Service not found", "service": "{service}"}}'
        logger.error(error_msg)
        return jsonify({"error": f"Service '{service}' not found"}), 404
    
    service_url = services[service]
    url = urljoin(service_url + '/', path)
    
    # BUG: Not handling connection errors properly
    try:
        # Get timeout for service, will raise KeyError if not found
        timeout = request_timeout(service)
        
        # Forward the request to the appropriate service
        method = request.method
        headers = {key: value for key, value in request.headers if key != 'Host'}
        data = request.get_data()
        params = request.args
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout
        )
        
        # BUG: Not properly handling binary responses
        # Should check content type before trying to decode JSON
        if response.headers.get('Content-Type') == 'application/json':
            try:
                json_response = response.json()
                return jsonify(json_response), response.status_code
            except ValueError:
                # Not JSON, return raw
                return Response(response.content, response.status_code, content_type=response.headers.get('Content-Type'))
        else:
            # BUG: Setting wrong content type for non-JSON responses
            return response.text, response.status_code
    
    except KeyError as e:
        error_msg = f'{{"error": "Configuration error", "details": "{str(e)}", "service": "{service}"}}'
        logger.error(error_msg)
        return jsonify({"error": f"Gateway configuration error for service '{service}'"}), 500
        
    except requests.exceptions.ConnectionError:
        error_msg = f'{{"error": "Connection error", "service": "{service}", "url": "{url}"}}'
        logger.error(error_msg)
        return jsonify({"error": f"Could not connect to service '{service}'"}), 503
    
    except requests.exceptions.Timeout:
        error_msg = f'{{"error": "Timeout error", "service": "{service}", "url": "{url}"}}'
        logger.error(error_msg)
        return jsonify({"error": f"Service '{service}' timed out"}), 504
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "service": "{service}", "url": "{url}"}}'
        logger.error(error_msg)
        return jsonify({"error": "Internal gateway error"}), 500

@app.route('/<service>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def route_root_request(service):
    return route_request(service, '')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port) 