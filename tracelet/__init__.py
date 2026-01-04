from tracelet.config import settings

def init(max_workers=None, enabled=True):
    """The user calls this to set up Tracelet."""
    settings.configure(max_workers=max_workers, enabled=enabled)