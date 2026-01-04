class TraceletConfig:
    def __init__(self):
        self.max_workers = 1  # Default safe value
        self.enabled = True # Denotes to block tracelet to track during migrations/testing/crashes
        self.tables_created = False

    def configure(self, max_workers=None, enabled=True):
        from tracelet.db.config import DBSetup
        db = DBSetup()
        
        self.enabled = enabled
        
        if max_workers and max_workers >= 1 and db.db_type == 'postgres':
            self.max_workers = max_workers
        else:
            self.max_workers = 1

# One instance to be shared across the whole project
settings = TraceletConfig()