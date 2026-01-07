from tracelet.logger_config import logger

class TraceletConfig:
    def __init__(self):
        self.tables_created = False

    def configure(self, db_config=None, **kwargs):

        logger.info("Initializing Tracelet...")
        logger.info("Setting Up user settings")

        max_workers = kwargs.get('max_workers', 1)
        self.enabled = kwargs.get('enabled', True)
        self.use_bulk_mode = kwargs.get('use_bulk_mode', True)
        self.batch_size = kwargs.get('batch_size', 50)
        self.flush_interval = kwargs.get('flush_interval', 5.0)
        logger_level = kwargs.get('logger_level', 'INFO')
        
        db = self.configure_db(db_config)
        self.configure_logger(logger_level)
        self._logger_level = logger_level
        
        if max_workers >= 1 and db.db_type == 'postgres':
            self.max_workers = max_workers
        else:
            self.max_workers = 1
        
        user_settings = {
            "max_workers" : self.max_workers, 
            "tracelet_enabled": self.enabled,
            "tracelet_logger_level": logger_level,
            "database": db.db_type,
            "bulk_mode" : self.use_bulk_mode,
            "batch_size": self.batch_size,
            "flush_interval": self.flush_interval
            
        }
        
        logger.info(f"Settings Applied: {user_settings}")

    def configure_db(self, db_config):
        from tracelet.db.config import DBSetup
        from tracelet.db.models import create_tables
        
        db = DBSetup(db_config=db_config if db_config else {})
        self.engine = db.engine
        self.SessionLocal = db.SessionLocal
        logger.info("Database configuration Completed")
        create_tables()

        return db

    def configure_logger(self, logger_level):
        if logger_level == 'INFO':
            return 

        level_upper = str(logger_level).upper()

        if level_upper in ['DEBUG', 'WARNING', 'ERROR', 'CRITICAL']:
            logger.setLevel(level_upper)
            logger.info(f"Logger level updated to {level_upper}")
        else:
            logger.warning(f"'{logger_level}' is not a valid log level. Keeping default [INFO].")

# One instance to be shared across the whole project
settings = TraceletConfig()