import logging
from utils.db_migration import DatabaseMigrator
from utils.logger import setup_logger

def run_migration():
    # Set up logging
    logger = setup_logger()
    logger.info("Starting database migration from SQLite to PostgreSQL")
    
    try:
        # Initialize migrator
        migrator = DatabaseMigrator()
        
        # Run migration
        success = migrator.migrate_all_data()
        
        if success:
            logger.info("Migration completed successfully")
            return True
        else:
            logger.error("Migration failed")
            return False
            
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False

if __name__ == "__main__":
    run_migration()
