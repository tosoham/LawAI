#!/usr/bin/env python3
"""
Initialize ChromaDB with sample legal data
Run this script to populate the vector database with BNS, BNSS, BSA, and SC judgements
"""
import sys
import os
import logging

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.vector_service import get_vector_service, VectorService
from services.data_loader import LegalDataLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_collection(vector_service: VectorService, collection_name: str, data: list, data_type: str):
    """
    Initialize a collection with data
    
    Args:
        vector_service: VectorService instance
        collection_name: Name of the collection
        data: List of data items
        data_type: Type of data (for logging)
    """
    try:
        logger.info(f"Initializing {collection_name} with {len(data)} {data_type}...")
        
        # Extract documents, metadatas, and ids
        documents = [item['text'] for item in data]
        metadatas = [item['metadata'] for item in data]
        ids = [item['id'] for item in data]
        
        # Add to collection
        vector_service.add_documents(
            collection_name=collection_name,
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        # Get stats
        stats = vector_service.get_collection_stats(collection_name)
        logger.info(f"✓ {collection_name}: {stats['count']} documents loaded")
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize {collection_name}: {e}")
        raise


def main():
    """Main initialization function"""
    try:
        logger.info("=" * 60)
        logger.info("LawAI Vector Database Initialization")
        logger.info("=" * 60)
        
        # Initialize services
        logger.info("Initializing services...")
        vector_service = get_vector_service()
        data_loader = LegalDataLoader()
        
        # Load all data
        logger.info("Loading sample legal data...")
        all_data = data_loader.load_all_data()
        
        # Initialize each collection
        logger.info("\nPopulating collections...")
        
        # BNS (Bharatiya Nyaya Sanhita)
        init_collection(
            vector_service,
            VectorService.BNS_COLLECTION,
            all_data['bns'],
            "BNS sections"
        )
        
        # BNSS (Bharatiya Nagarik Suraksha Sanhita)
        init_collection(
            vector_service,
            VectorService.BNSS_COLLECTION,
            all_data['bnss'],
            "BNSS sections"
        )
        
        # BSA (Bharatiya Sakshya Adhiniyam)
        init_collection(
            vector_service,
            VectorService.BSA_COLLECTION,
            all_data['bsa'],
            "BSA sections"
        )
        
        # SC Judgements
        init_collection(
            vector_service,
            VectorService.SC_JUDGEMENTS_COLLECTION,
            all_data['sc_judgements'],
            "SC judgements"
        )
        
        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Initialization Complete!")
        logger.info("=" * 60)
        
        logger.info("\nCollection Summary:")
        for collection_name in [
            VectorService.BNS_COLLECTION,
            VectorService.BNSS_COLLECTION,
            VectorService.BSA_COLLECTION,
            VectorService.SC_JUDGEMENTS_COLLECTION
        ]:
            stats = vector_service.get_collection_stats(collection_name)
            logger.info(f"  • {collection_name}: {stats['count']} documents")
        
        total_docs = sum([
            len(all_data['bns']),
            len(all_data['bnss']),
            len(all_data['bsa']),
            len(all_data['sc_judgements'])
        ])
        logger.info(f"\nTotal documents: {total_docs}")
        logger.info("\n✓ Vector database is ready for use!")
        logger.info("  You can now run the API server and perform RAG searches.")
        
    except Exception as e:
        logger.error(f"\n✗ Initialization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

# Made with Bob
