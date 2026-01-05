from tracelet.config import settings

def init(max_workers=None, enabled=True, db_config=None):
    """The user calls this to set up Tracelet."""
    settings.configure(max_workers=max_workers, enabled=enabled, db_config=db_config)