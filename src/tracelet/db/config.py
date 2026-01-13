from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from tracelet.utils.logger_config import logger

_shared_db_instance = None


class DBSetup:
    def __init__(self, db_config={}):
        self.database_url = db_config.get("db_url", "sqlite:///tracelet.db")
        self.connect_args = db_config.get("connect_args", {})
        self.echo = db_config.get("echo", False)

        self.db_type = (
            "postgres" if "postgres" in self.database_url.lower() else "sqlite"
        )

        self.engine = self._create_engine_instance()
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )

    def _create_engine_instance(self):
        if self.db_type == "sqlite":
            self.connect_args.setdefault("check_same_thread", False)

        try:
            engine = create_engine(
                self.database_url, connect_args=self.connect_args, echo=self.echo
            )
        except Exception as e:
            logger.error("Failed to create DB engine for URL: %s", e)
            raise RuntimeError(f"Failed to initialize database engine: {e}")

        # Apply WAL mode only if it's SQLite
        if self.db_type == "sqlite":

            @event.listens_for(engine, "connect")  # Attaching to THIS engine instance
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache
                except Exception as e:
                    logger.error(
                        "Exception occurred while applying SQLite PRAGMA: %s", e
                    )
                finally:
                    cursor.close()

        return engine


def setup_db(db_config):
    """
    This is the ONLY way to get the engine.
    It ensures we never create more than one.
    """
    global _shared_db_instance
    if _shared_db_instance is None:
        _shared_db_instance = DBSetup(db_config)
    return _shared_db_instance
