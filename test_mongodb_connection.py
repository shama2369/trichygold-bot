import os
import certifi
from pymongo import MongoClient
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def test_connection(uri):
    """Test MongoDB connection with the provided URI"""
    logger.info("Testing MongoDB connection...")
    
    # Check if URI is empty
    if not uri:
        logger.error("MongoDB URI is empty or not set!")
        return False
    
    # Mask the password in the URI for safe logging
    masked_uri = uri
    if '@' in uri:
        parts = uri.split('@')
        if ':' in parts[0]:
            auth_parts = parts[0].split(':')
            if len(auth_parts) > 2:
                # Format: mongodb+srv://username:password@cluster
                masked_uri = f"{auth_parts[0]}:{auth_parts[1]}:****@{parts[1]}"
            else:
                # Format: mongodb://username:password@host
                prefix = parts[0].split('://')
                if len(prefix) > 1:
                    masked_uri = f"{prefix[0]}://{prefix[1].split(':')[0]}:****@{parts[1]}"
    
    logger.info(f"Using connection string pattern: {masked_uri}")
    
    try:
        logger.info("Initializing MongoDB client...")
        # Connect with SSL certificate validation
        client = MongoClient(
            uri,
            tlsCAFile=certifi.where(),
            connectTimeoutMS=30000,
            socketTimeoutMS=30000,
            serverSelectionTimeoutMS=30000
        )
        
        # Test the connection
        logger.info("Attempting to ping MongoDB server...")
        ping_result = client.admin.command('ping')
        logger.info(f"Ping result: {ping_result}")
        
        # Get server info
        logger.info("Retrieving server info...")
        server_info = client.server_info()
        logger.info(f"Successfully connected to MongoDB!")
        logger.info(f"Server version: {server_info.get('version', 'unknown')}")
        logger.info(f"Server: {server_info.get('host', 'unknown')}")
        
        # List available databases
        logger.info("Listing available databases...")
        databases = client.list_database_names()
        logger.info(f"Available databases: {', '.join(databases)}")
        
        # Try to access the trichygold_bot database
        logger.info("Attempting to access trichygold_bot database...")
        db = client.get_database("trichygold_bot")
        collections = db.list_collection_names()
        logger.info(f"Collections in trichygold_bot: {', '.join(collections) if collections else 'No collections found'}")
        
        # Try to create a test document
        logger.info("Testing write operation...")
        test_collection = db.get_collection("test_connection")
        result = test_collection.insert_one({"test": "connection", "timestamp": str(datetime.now())})
        logger.info(f"Write test result: {result.acknowledged}")
        
        # Clean up test document
        test_collection.delete_one({"_id": result.inserted_id})
        
        return True
        
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    # Get MongoDB URI from environment or input
    mongodb_uri = os.getenv('MONGODB_URI')
    
    if not mongodb_uri:
        mongodb_uri = input("Enter your MongoDB connection string: ")
    
    test_connection(mongodb_uri)
