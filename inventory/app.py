import os
import json
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("/logs/inventory.log"),
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
inventory_collection = db.inventory

# Initialize with sample data if empty
if inventory_collection.count_documents({}) == 0:
    # Get products from products collection
    products_collection = db.products
    products = list(products_collection.find())
    
    # Create inventory entries for each product
    inventory_entries = []
    for product in products:
        inventory_entries.append({
            "product_id": str(product["_id"]),
            "quantity": product.get("stock", 100),
            "reserved": 0,
            "location": "Main Warehouse"
        })
    
    if inventory_entries:
        inventory_collection.insert_many(inventory_entries)
        logger.info("Inventory initialized with sample data")

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "inventory"})

@app.route('/', methods=['GET'])
def get_inventory():
    try:
        inventory = list(inventory_collection.find())
        # Convert ObjectId to string
        for item in inventory:
            item["_id"] = str(item["_id"])
        
        return jsonify(inventory), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/", "method": "GET"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['POST'])
def create_inventory():
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['product_id', 'quantity']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Check if inventory already exists for this product
        existing = inventory_collection.find_one({"product_id": data['product_id']})
        if existing:
            return jsonify({"error": "Inventory already exists for this product", "item_id": str(existing['_id'])}), 409
            
        # Set defaults for optional fields
        if 'reserved' not in data:
            data['reserved'] = 0
            
        if 'location' not in data:
            data['location'] = 'Main Warehouse'
            
        # Insert new inventory entry
        result = inventory_collection.insert_one(data)
        
        return jsonify({
            "message": "Inventory entry created successfully",
            "item_id": str(result.inserted_id)
        }), 201
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<product_id>', methods=['GET'])
def get_product_inventory(product_id):
    try:
        inventory_item = inventory_collection.find_one({"product_id": product_id})
        
        if not inventory_item:
            error_msg = f'{{"error": "Inventory item not found", "product_id": "{product_id}"}}'
            logger.error(error_msg)
            return jsonify({"error": "Inventory item not found"}), 404
            
        # Convert ObjectId to string
        inventory_item["_id"] = str(inventory_item["_id"])
        
        return jsonify(inventory_item), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{product_id}", "method": "GET"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<product_id>', methods=['PUT'])
def update_inventory(product_id):
    try:
        data = request.json
        
        # Validate required fields
        if "quantity" not in data:
            return jsonify({"error": "Missing required field: quantity"}), 400
            
        # Update inventory
        result = inventory_collection.update_one(
            {"product_id": product_id},
            {"$set": {"quantity": data["quantity"]}}
        )
        
        if result.matched_count == 0:
            error_msg = f'{{"error": "Inventory item not found", "product_id": "{product_id}"}}'
            logger.error(error_msg)
            return jsonify({"error": "Inventory item not found"}), 404
            
        return jsonify({"message": "Inventory updated successfully"}), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{product_id}", "method": "PUT", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/reserve', methods=['POST'])
def reserve_inventory():
    try:
        data = request.json
        
        # Validate required fields
        if "product_id" not in data or "quantity" not in data:
            return jsonify({"error": "Missing required fields: product_id, quantity"}), 400
            
        product_id = data["product_id"]
        quantity = int(data["quantity"])
        
        # Find inventory item
        inventory_item = inventory_collection.find_one({"product_id": product_id})
        
        if not inventory_item:
            error_msg = f'{{"error": "Inventory item not found", "product_id": "{product_id}"}}'
            logger.error(error_msg)
            return jsonify({"error": "Inventory item not found"}), 404
            
        # Check if enough quantity available
        available = inventory_item["quantity"] - inventory_item["reserved"]
        
        if available < quantity:
            error_msg = f'{{"error": "Insufficient inventory", "product_id": "{product_id}", "requested": {quantity}, "available": {available}}}'
            logger.error(error_msg)
            return jsonify({
                "error": "Insufficient inventory",
                "requested": quantity,
                "available": available
            }), 400
            
        # Update reserved quantity
        result = inventory_collection.update_one(
            {"product_id": product_id},
            {"$inc": {"reserved": quantity}}
        )
        
        return jsonify({
            "message": "Inventory reserved successfully",
            "product_id": product_id,
            "quantity": quantity
        }), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/reserve", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/release', methods=['POST'])
def release_inventory():
    try:
        data = request.json
        
        # Validate required fields
        if "product_id" not in data or "quantity" not in data:
            return jsonify({"error": "Missing required fields: product_id, quantity"}), 400
            
        product_id = data["product_id"]
        quantity = int(data["quantity"])
        
        # Find inventory item
        inventory_item = inventory_collection.find_one({"product_id": product_id})
        
        if not inventory_item:
            error_msg = f'{{"error": "Inventory item not found", "product_id": "{product_id}"}}'
            logger.error(error_msg)
            return jsonify({"error": "Inventory item not found"}), 404
            
        # Make sure we don't release more than reserved
        release_qty = min(quantity, inventory_item["reserved"])
        
        # Update reserved quantity
        result = inventory_collection.update_one(
            {"product_id": product_id},
            {"$inc": {"reserved": -release_qty}}
        )
        
        return jsonify({
            "message": "Inventory released successfully",
            "product_id": product_id,
            "quantity": release_qty
        }), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/release", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/commit', methods=['POST'])
def commit_inventory():
    try:
        data = request.json
        
        # Validate required fields
        if "product_id" not in data or "quantity" not in data:
            return jsonify({"error": "Missing required fields: product_id, quantity"}), 400
            
        product_id = data["product_id"]
        quantity = int(data["quantity"])
        
        # Find inventory item
        inventory_item = inventory_collection.find_one({"product_id": product_id})
        
        if not inventory_item:
            error_msg = f'{{"error": "Inventory item not found", "product_id": "{product_id}"}}'
            logger.error(error_msg)
            return jsonify({"error": "Inventory item not found"}), 404
            
        # Make sure we don't commit more than reserved
        commit_qty = min(quantity, inventory_item["reserved"])
        
        # Update reserved and actual quantity
        result = inventory_collection.update_one(
            {"product_id": product_id},
            {
                "$inc": {
                    "reserved": -commit_qty,
                    "quantity": -commit_qty
                }
            }
        )
        
        return jsonify({
            "message": "Inventory committed successfully",
            "product_id": product_id,
            "quantity": commit_qty
        }), 200
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/commit", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5004))
    app.run(host='0.0.0.0', port=port) 