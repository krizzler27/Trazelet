from tracelet.utils.logger_config import logger
import json

class TraceletConfig:
    def __init__(self):
        self.tables_created = False
        self._logger_level = "INFO"
        self.BUCKET_THRESHOLDS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float('inf')]

    def configure(self, db_config=None, **kwargs):

        logger.info("Initializing Tracelet...")
        logger.info("Setting Up user settings")

        max_workers = kwargs.get('max_workers', 1)
        self.enabled = kwargs.get('enabled', True)
        self.batch_size = kwargs.get('batch_size', 50)
        self.flush_interval = kwargs.get('flush_interval', 5.0)
        logger_level = kwargs.get('logger_level', 'INFO')
        
        db = self.configure_db(db_config)
        self.logger_level = logger_level  # Use property setter
        self.db_type = db.db_type
        
        if max_workers >= 1 and db.db_type == 'postgres':
            self.max_workers = max_workers
        else:
            self.max_workers = 1
        
        user_settings = {
            "max_workers" : self.max_workers, 
            "tracelet_enabled": self.enabled,
            "tracelet_logger_level": logger_level,
            "db_config": db_config,
            "database": self.db_type,
            "batch_size": self.batch_size,
            "flush_interval": self.flush_interval,
            "BUCKET_THRESHOLDS": [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float('inf')],
            "tracelet_tables_created": self.tables_created
            
        }
        
        with open("settings.json", "w") as f:
            json.dump(user_settings, f)
        
        logger.info(f"Settings saved in settings.json")

    def configure_db(self, db_config):
        from tracelet.db.config import setup_db
        from tracelet.db.models import create_tables
        
        db = setup_db(db_config=db_config if db_config else {})
        self.engine = db.engine
        self.SessionLocal = db.SessionLocal
        print("engine: ", db)
        logger.info("Database configuration Completed")
        create_tables()

        return db

    def configure_logger(self, logger_level):
        level_upper = str(logger_level).upper()

        if level_upper in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            logger.setLevel(level_upper)
            logger.info(f"Logger level updated to {level_upper}")
        else:
            logger.warning(f"'{logger_level}' is not a valid log level. Keeping default [INFO].")

    @property
    def logger_level(self):
        """Get the current logger level."""
        return self._logger_level
    
    @logger_level.setter
    def logger_level(self, value):
        """Set the logger level and update the actual logger."""
        self._logger_level = value
        self.configure_logger(value)

# One instance to be shared across the whole project
settings = TraceletConfig()