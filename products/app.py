import os
import json
import logging
import re
from flask import Flask, jsonify, request, g, has_request_context
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId
import time
from functools import wraps

# Custom JSON formatter that automatically includes request info
class RequestFormatter(logging.Formatter):
    def format(self, record):
        # Add request info to log record if available
        if has_request_context():
            record.url = request.path
            record.method = request.method
            record.remote_addr = request.remote_addr
            record.query_params = dict(request.args)
            # For POST/PUT requests, include data if it's JSON
            if request.is_json and request.method in ['POST', 'PUT']:
                record.request_data = request.json
        else:
            record.url = None
            record.method = None
            record.remote_addr = None
            record.query_params = {}
            record.request_data = None
        
        # Call the original formatter
        return super().format(record)

# Configure logging with automatic route/request information
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter with request context and source info
formatter = RequestFormatter(
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "file": "%(pathname)s", "line": %(lineno)d, '
    '"function": "%(funcName)s", "url": "%(url)s", "method": "%(method)s", "params": %(query_params)s, "message": %(message)s}'
)

# Add handlers
file_handler = logging.FileHandler("/logs/products.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Prevent double logging with root logger
logger.propagate = False

app = Flask(__name__)
CORS(app)

# Request timing middleware
@app.before_request
def start_timer():
    g.start = time.time()

@app.after_request
def log_request(response):
    if not request.path.startswith('/health'):  # Skip health check endpoints
        total_time = time.time() - g.start
        log_data = {
            "status_code": response.status_code,
            "execution_time": f"{total_time:.4f}s"
        }
        logger.info(json.dumps(log_data))
    return response

# MongoDB connection
mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/ecommerce')
client = MongoClient(mongo_uri)
db = client.get_database()
products_collection = db.products

# Sample data for initialization
sample_products = [
    {
        "name": "Smartphone X",
        "description": "Latest smartphone with advanced features",
        "price": 999.99,
        "category": "Electronics",
        "stock": 100,
        "tags": ["smartphone", "electronics", "mobile"]
    },
    {
        "name": "Laptop Pro",
        "description": "High-performance laptop for professionals",
        "price": 1499.99,
        "category": "Electronics",
        "stock": 50,
        "tags": ["laptop", "electronics", "computer"]
    },
    {
        "name": "Wireless Headphones",
        "description": "Premium noise-canceling wireless headphones",
        "price": 249.99,
        "category": "Audio",
        "stock": 200,
        "tags": ["headphones", "audio", "wireless"]
    }
]

# Initialize database with sample data if empty
if products_collection.count_documents({}) == 0:
    products_collection.insert_many(sample_products)
    logger.info(json.dumps({"message": "Database initialized with sample products"}))

# Helper function - BUG: Does not handle ObjectId conversion properly
def product_to_dict(product):
    # Convert ObjectId to string
    product_copy = product.copy()
    product_copy['_id'] = str(product['_id'])
    return product_copy

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "products"})

@app.route('/', methods=['GET'])
def get_products():
    try:
        # BUG: No pagination, could cause performance issues with large datasets
        products = list(products_collection.find())
        
        # Convert ObjectId to string for JSON serialization
        for product in products:
            product['_id'] = str(product['_id'])
            
        return jsonify(products), 200
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/<product_id>', methods=['GET'])
def get_product(product_id):
    try:
        # BUG: No error handling for invalid ObjectId
        product = products_collection.find_one({"_id": ObjectId(product_id)})
        
        if not product:
            logger.error(json.dumps({"error": "Product not found"}))
            return jsonify({"error": "Product not found"}), 404
            
        return jsonify(product_to_dict(product)), 200
        
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['POST'])
def create_product():
    try:
        product_data = request.json
        
        # BUG: No validation of required fields
        result = products_collection.insert_one(product_data)
        product_id = result.inserted_id
        
        # Fix: Convert ObjectId to string for JSON serialization
        return jsonify({"id": str(product_id), "message": "Product created successfully"}), 201
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/<product_id>', methods=['PUT'])
def update_product(product_id):
    try:
        product_data = request.json
        
        # Fix: Remove _id from update data to avoid MongoDB error
        if '_id' in product_data:
            del product_data['_id']
            
        result = products_collection.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": product_data}
        )
        
        if result.matched_count == 0:
            logger.error(json.dumps({"error": "Product not found"}))
            return jsonify({"error": "Product not found"}), 404
            
        return jsonify({"message": "Product updated successfully"}), 200
        
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        # BUG: No error handling for invalid ObjectId
        result = products_collection.delete_one({"_id": ObjectId(product_id)})
        
        if result.deleted_count == 0:
            logger.error(json.dumps({"error": "Product not found"}))
            return jsonify({"error": "Product not found"}), 404
            
        return jsonify({"message": "Product deleted successfully"}), 200
        
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/category/<category>', methods=['GET'])
def get_products_by_category(category):
    try:
        # Fix: Case insensitive search
        products = list(products_collection.find({"category": {"$regex": f"^{category}$", "$options": "i"}}))
        
        # Convert ObjectId to string for JSON serialization
        for product in products:
            product['_id'] = str(product['_id'])
            
        return jsonify(products), 200
        
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
        return jsonify({"error": str(e)}), 500

@app.route('/search', methods=['GET'])
@app.route('/search', methods=['GET'])
def search_products():
    try:
        query = request.args.get('q', '')
        
        # Use re.escape to escape special characters in the search query
        regex_pattern = f".*{re.escape(query)}.*"
        
        products = list(products_collection.find({"name": {"$regex": regex_pattern, "$options": "i"}}))
        
        # Convert ObjectId to string for JSON serialization
        for product in products:
            product['_id'] = str(product['_id'])
            
        return jsonify(products), 200
        
    except Exception as e:
        error_data = {"error": str(e), "query": query}
        logger.error(json.dumps(error_data))
        return jsonify({"error": f"Search failed: {str(e)}"}), 500
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 