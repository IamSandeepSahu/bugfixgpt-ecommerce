import os
import json
import logging
import hashlib
import uuid
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    handlers=[
        logging.FileHandler("/logs/users.log"),
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
users_collection = db.users
sessions_collection = db.sessions

# Hash password function
def hash_password(password, salt=None):
    if not salt:
        salt = uuid.uuid4().hex
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{hashed}"

# Verify password
def verify_password(stored_password, provided_password):
    salt, hashed = stored_password.split(':')
    return stored_password == hash_password(provided_password, salt)

# Generate session token
def generate_session_token(user_id):
    token = uuid.uuid4().hex
    expiry = datetime.utcnow() + timedelta(days=1)
    
    # Store session
    sessions_collection.insert_one({
        "user_id": user_id,
        "token": token,
        "expires": expiry
    })
    
    return token, expiry

# Initialize with sample data if empty
if users_collection.count_documents({}) == 0:
    sample_users = [
        {
            "username": "admin",
            "email": "admin@example.com",
            "password": hash_password("admin123"),
            "role": "admin",
            "created_at": datetime.utcnow()
        },
        {
            "username": "user1",
            "email": "user1@example.com",
            "password": hash_password("password123"),
            "role": "customer",
            "created_at": datetime.utcnow()
        }
    ]
    
    users_collection.insert_many(sample_users)
    logger.info("Users database initialized with sample data")

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "users"})

@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
                
        # Check if username or email already exists
        if users_collection.find_one({"username": data['username']}):
            return jsonify({"error": "Username already taken"}), 409
            
        if users_collection.find_one({"email": data['email']}):
            return jsonify({"error": "Email already registered"}), 409
            
        # Create new user
        new_user = {
            "username": data['username'],
            "email": data['email'],
            "password": hash_password(data['password']),
            "role": "customer",
            "created_at": datetime.utcnow()
        }
        
        # Add optional fields
        if 'first_name' in data:
            new_user['first_name'] = data['first_name']
            
        if 'last_name' in data:
            new_user['last_name'] = data['last_name']
            
        # Insert user into database
        result = users_collection.insert_one(new_user)
        
        # Return user data (excluding password)
        new_user.pop('password', None)
        new_user['_id'] = str(result.inserted_id)
        
        return jsonify({"message": "User registered successfully", "user": new_user}), 201
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/register", "method": "POST"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.json
        
        # Validate required fields
        if 'username' not in data or 'password' not in data:
            return jsonify({"error": "Missing username or password"}), 400
            
        # Find user
        user = users_collection.find_one({"username": data['username']})
        
        if not user:
            return jsonify({"error": "Invalid username or password"}), 401
            
        # Verify password
        if not verify_password(user['password'], data['password']):
            return jsonify({"error": "Invalid username or password"}), 401
            
        # Generate session token
        token, expiry = generate_session_token(str(user['_id']))
        
        # Return token and user data (excluding password)
        user_data = {
            "_id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": user['role']
        }
        
        if 'first_name' in user:
            user_data['first_name'] = user['first_name']
            
        if 'last_name' in user:
            user_data['last_name'] = user['last_name']
        
        return jsonify({
            "message": "Login successful",
            "token": token,
            "expires": expiry.isoformat(),
            "user": user_data
        }), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/login", "method": "POST"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/me', methods=['GET'])
def get_current_user():
    try:
        # Get authorization token
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization token"}), 401
            
        token = auth_header.split(' ')[1]
        
        # Find session
        session = sessions_collection.find_one({
            "token": token,
            "expires": {"$gt": datetime.utcnow()}
        })
        
        if not session:
            return jsonify({"error": "Invalid or expired token"}), 401
            
        # Find user
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        # Return user data (excluding password)
        user_data = {
            "_id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": user['role'],
            "created_at": user['created_at'].isoformat() if isinstance(user['created_at'], datetime) else user['created_at']
        }
        
        if 'first_name' in user:
            user_data['first_name'] = user['first_name']
            
        if 'last_name' in user:
            user_data['last_name'] = user['last_name']
        
        return jsonify(user_data), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/me", "method": "GET"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/logout', methods=['POST'])
def logout_user():
    try:
        # Get authorization token
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization token"}), 401
            
        token = auth_header.split(' ')[1]
        
        # Delete session
        result = sessions_collection.delete_one({"token": token})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Invalid token"}), 401
            
        return jsonify({"message": "Logout successful"}), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/logout", "method": "POST"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        # Only admins or the user themselves should be able to access this
        # Auth logic would go here
        
        # Find user
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        # Return user data (excluding password)
        user_data = {
            "_id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "role": user['role'],
            "created_at": user['created_at'].isoformat() if isinstance(user['created_at'], datetime) else user['created_at']
        }
        
        if 'first_name' in user:
            user_data['first_name'] = user['first_name']
            
        if 'last_name' in user:
            user_data['last_name'] = user['last_name']
        
        return jsonify(user_data), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{user_id}", "method": "GET"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

@app.route('/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        # Only admins or the user themselves should be able to update
        # Auth logic would go here
        
        data = request.json
        
        # Find user
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
            
        # Update user fields
        update_data = {}
        
        allowed_fields = ['first_name', 'last_name', 'email']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
                
        # Handle password separately with hashing
        if 'password' in data:
            update_data['password'] = hash_password(data['password'])
            
        # Update user in database
        if update_data:
            users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
        return jsonify({"message": "User updated successfully"}), 200
        
    except Exception as e:
        error_msg = f'{{"error": "{str(e)}", "route": "/{user_id}", "method": "PUT"}}'
        logger.error(error_msg)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port) 