class TraceletConfig:
    def __init__(self):
        self.max_workers = 1  # Default safe value
        self.enabled = True # Denotes to block tracelet to track during migrations/testing/crashes
        self.tables_created = False
        # Batch processing settings
        self.use_bulk_mode = True  # Use bulk insert for metrics (False = single save)
        self.batch_size = 50  # Flush queue when this many items accumulate
        self.flush_interval = 5.0  # Flush queue every N seconds (heartbeat)

    def configure(self, max_workers=None, enabled=True, db_config=None):
        from tracelet.db.config import DBSetup
        from tracelet.db.models import create_tables
        
        # Create new DBSetup instance with user's configuration
        db = DBSetup(db_config=db_config if db_config else {})
        self.engine = db.engine
        self.SessionLocal = db.SessionLocal
        create_tables()

        self.enabled = enabled
        
        if max_workers and max_workers >= 1 and db.db_type == 'postgres':
            self.max_workers = max_workers
        else:
            self.max_workers = 1

# One instance to be shared across the whole project
settings = TraceletConfig()