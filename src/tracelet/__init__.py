from tracelet.config import settings


def init(db_config=None, **kwargs):
    """
    Initializes the Tracelet engine and background workers.

    Args:
        db_config (dict, optional): Database connection settings.
            - 'db_url' (str): SQLAlchemy connection string.
            - 'echo' (bool): If True, SQLAlchemy will log SQL queries. (Default: False)
            - 'connect_args' (dict): Extra args for the DB driver (e.g., {'timeout': 30}).

        **kwargs:
            - enabled (bool): Enable or disable Tracelet tracking. (Default: True)
            - max_workers (int): Number of background threads for processing. (Default: 1)
            - logger_level (str): Logging severity ('DEBUG', 'INFO', 'WARNING', 'ERROR'). (Default: 'INFO')
            - batch_size (int): Number of metrics to accumulate before flushing. (Default: 50)
            - flush_interval (float): Max seconds to wait before flushing metrics. (Default: 5.0)
            - BUCKET_THRESHOLDS (List): Bucket thresholds to classify the captured latemcy in DB.
              (Default: [25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000, float('inf') ])

    Example:
        >>> tracelet.init(
        ...     db_config={'db_url': 'sqlite:///tracelet.db'},
        ...     batch_size=100,
        ...     logger_level='DEBUG'
        ... )
    """
    settings.configure(db_config=db_config, **kwargs)
