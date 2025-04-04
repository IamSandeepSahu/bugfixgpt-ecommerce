import os
import json
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("/logs/payments.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# MongoDB connection
mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/ecommerce')
client = MongoClient(mongo_uri)
db = client.get_database()
payments_collection = db.payments

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "payments"})

@app.route('/process', methods=['POST'])
def process_payment():
    try:
        payment_data = request.json
        
        # Simple payment processing logic
        result = payments_collection.insert_one(payment_data)
        payment_id = str(result.inserted_id)
        
        return jsonify({
            "status": "success",
            "message": "Payment processed successfully",
            "payment_id": payment_id
        }), 201
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/process", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5003))
    app.run(host='0.0.0.0', port=port) 