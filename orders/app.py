import os
import json
import logging
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("/logs/orders.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Service URLs
product_service_url = os.environ.get('SERVICE_PRODUCTS', 'http://products:5000')
payment_service_url = os.environ.get('SERVICE_PAYMENTS', 'http://payments:5003')
inventory_service_url = os.environ.get('SERVICE_INVENTORY', 'http://inventory:5004')

# MongoDB connection
mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/ecommerce')
client = MongoClient(mongo_uri)
db = client.get_database()
orders_collection = db.orders

# Order status constants
ORDER_STATUS = {
    'PENDING': 'PENDING',
    'PAYMENT_PROCESSING': 'PAYMENT_PROCESSING',
    'PAID': 'PAID',
    'PROCESSING': 'PROCESSING',
    'SHIPPED': 'SHIPPED',
    'DELIVERED': 'DELIVERED',
    'CANCELLED': 'CANCELLED',
    'REFUNDED': 'REFUNDED'
}

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "orders"})

@app.route('/', methods=['GET'])
def get_orders():
    try:
        # Auth would go here - only retrieve orders for the authenticated user
        # or all orders for admin
        
        # Get user_id from query param (in real app, this would come from auth token)
        user_id = request.args.get('user_id')
        
        # Build query
        query = {}
        if user_id:
            query['user_id'] = user_id
            
        # Optional status filter
        status = request.args.get('status')
        if status:
            query['status'] = status
            
        # Get orders from database
        orders = list(orders_collection.find(query).sort('created_at', -1))
        
        # Convert ObjectId to string
        for order in orders:
            order['_id'] = str(order['_id'])
            if 'items' in order:
                for item in order['items']:
                    if '_id' in item:
                        item['_id'] = str(item['_id'])
        
        return jsonify(orders), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/", "method": "GET", "params": {json.dumps(request.args.to_dict())}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<order_id>', methods=['GET'])
def get_order(order_id):
    try:
        # Auth would go here
        
        # Find order
        order = orders_collection.find_one({"_id": ObjectId(order_id)})
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
            
        # Convert ObjectId to string
        order['_id'] = str(order['_id'])
        if 'items' in order:
            for item in order['items']:
                if '_id' in item:
                    item['_id'] = str(item['_id'])
        
        return jsonify(order), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{order_id}", "method": "GET"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['POST'])
def create_order():
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['user_id', 'items']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
                
        # Validate items
        if not isinstance(data['items'], list) or len(data['items']) == 0:
            return jsonify({"error": "Items must be a non-empty array"}), 400
            
        # Fetch product details and calculate total
        total_amount = 0
        order_items = []
        
        for item in data['items']:
            if 'product_id' not in item or 'quantity' not in item:
                return jsonify({"error": "Each item must have product_id and quantity"}), 400
                
            try:
                # Get product details from product service
                product_response = requests.get(
                    f"{product_service_url}/{item['product_id']}",
                    timeout=5
                )
                
                if product_response.status_code != 200:
                    return jsonify({"error": f"Failed to fetch product {item['product_id']}"}), 400
                    
                product = product_response.json()
                
                # Check inventory
                inventory_response = requests.get(
                    f"{inventory_service_url}/{item['product_id']}",
                    timeout=5
                )
                
                if inventory_response.status_code != 200:
                    return jsonify({"error": f"Failed to check inventory for product {item['product_id']}"}), 400
                    
                inventory = inventory_response.json()
                available = inventory['quantity'] - inventory['reserved']
                
                if available < item['quantity']:
                    return jsonify({
                        "error": f"Insufficient inventory for product {item['product_id']}",
                        "requested": item['quantity'],
                        "available": available
                    }), 400
                
                # Calculate item total
                item_price = product['price']
                item_total = item_price * item['quantity']
                
                # Add to order items
                order_items.append({
                    "product_id": item['product_id'],
                    "product_name": product['name'],
                    "quantity": item['quantity'],
                    "price": item_price,
                    "total": item_total
                })
                
                # Add to order total
                total_amount += item_total
                
                # Reserve inventory
                reserve_response = requests.post(
                    f"{inventory_service_url}/reserve",
                    json={
                        "product_id": item['product_id'],
                        "quantity": item['quantity']
                    },
                    timeout=5
                )
                
                if reserve_response.status_code != 200:
                    return jsonify({"error": f"Failed to reserve inventory for product {item['product_id']}"}), 400
                
            except requests.exceptions.RequestException as e:
                return jsonify({"error": f"Service communication error: {str(e)}"}), 500
        
        # Create order
        new_order = {
            "user_id": data['user_id'],
            "items": order_items,
            "total_amount": total_amount,
            "status": ORDER_STATUS['PENDING'],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Add shipping details if provided
        if 'shipping_address' in data:
            new_order['shipping_address'] = data['shipping_address']
            
        # Insert order into database
        result = orders_collection.insert_one(new_order)
        order_id = str(result.inserted_id)
        
        # Start payment processing if payment details provided
        if 'payment' in data:
            # Update order status
            orders_collection.update_one(
                {"_id": result.inserted_id},
                {"$set": {"status": ORDER_STATUS['PAYMENT_PROCESSING']}}
            )
            
            # Process payment
            try:
                payment_data = {
                    "order_id": order_id,
                    "amount": total_amount,
                    "method": data['payment'].get('method', 'credit_card'),
                    "details": data['payment'].get('details', {})
                }
                
                payment_response = requests.post(
                    f"{payment_service_url}/process",
                    json=payment_data,
                    timeout=10
                )
                
                if payment_response.status_code == 201:
                    payment_result = payment_response.json()
                    
                    # Update order with payment info
                    orders_collection.update_one(
                        {"_id": result.inserted_id},
                        {
                            "$set": {
                                "status": ORDER_STATUS['PAID'],
                                "payment_id": payment_result['payment_id'],
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    
                    # Commit inventory
                    for item in order_items:
                        requests.post(
                            f"{inventory_service_url}/commit",
                            json={
                                "product_id": item['product_id'],
                                "quantity": item['quantity']
                            },
                            timeout=5
                        )
                else:
                    # Payment failed, release inventory
                    for item in order_items:
                        requests.post(
                            f"{inventory_service_url}/release",
                            json={
                                "product_id": item['product_id'],
                                "quantity": item['quantity']
                            },
                            timeout=5
                        )
                    
                    # Update order status
                    orders_collection.update_one(
                        {"_id": result.inserted_id},
                        {
                            "$set": {
                                "status": ORDER_STATUS['CANCELLED'],
                                "payment_error": payment_response.json().get('error', 'Payment processing failed'),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    
                    return jsonify({
                        "order_id": order_id,
                        "error": "Payment failed",
                        "details": payment_response.json()
                    }), 400
                        
            except requests.exceptions.RequestException as e:
                # Payment service error, release inventory
                for item in order_items:
                    requests.post(
                        f"{inventory_service_url}/release",
                        json={
                            "product_id": item['product_id'],
                            "quantity": item['quantity']
                        },
                        timeout=5
                    )
                
                # Update order status
                orders_collection.update_one(
                    {"_id": result.inserted_id},
                    {
                        "$set": {
                            "status": ORDER_STATUS['CANCELLED'],
                            "payment_error": str(e),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                
                return jsonify({
                    "order_id": order_id,
                    "error": "Payment service error",
                    "details": str(e)
                }), 500
        
        # Fetch updated order
        order = orders_collection.find_one({"_id": result.inserted_id})
        order['_id'] = order_id
        
        return jsonify(order), 201
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/", "method": "POST", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    try:
        # Auth would go here
        
        # Find order
        order = orders_collection.find_one({"_id": ObjectId(order_id)})
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
            
        # Check if order can be cancelled
        if order['status'] in [ORDER_STATUS['SHIPPED'], ORDER_STATUS['DELIVERED'], ORDER_STATUS['CANCELLED'], ORDER_STATUS['REFUNDED']]:
            return jsonify({"error": f"Cannot cancel order with status: {order['status']}"}), 400
            
        # Release inventory if not yet committed
        if order['status'] not in [ORDER_STATUS['PAID'], ORDER_STATUS['PROCESSING']]:
            for item in order['items']:
                requests.post(
                    f"{inventory_service_url}/release",
                    json={
                        "product_id": item['product_id'],
                        "quantity": item['quantity']
                    },
                    timeout=5
                )
        
        # Update order status
        orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {
                "$set": {
                    "status": ORDER_STATUS['CANCELLED'],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return jsonify({"message": "Order cancelled successfully"}), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{order_id}/cancel", "method": "POST"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    try:
        data = request.json
        
        # Validate status
        if 'status' not in data or data['status'] not in ORDER_STATUS.values():
            return jsonify({"error": "Invalid status"}), 400
            
        # Find order
        order = orders_collection.find_one({"_id": ObjectId(order_id)})
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
            
        # Update order status
        orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {
                "$set": {
                    "status": data['status'],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return jsonify({"message": "Order status updated successfully"}), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{order_id}/status", "method": "PUT", "data": {json.dumps(request.json)}}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port) 