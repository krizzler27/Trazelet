from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


class DBSetup:
    def __init__(self, db_config={}):
        self.database_url = db_config.get('db_url', "sqlite:///tracelet.db")
        self.connect_args = db_config.get('connect_args', {})
        self.echo = db_config.get('echo', False)
        
        self.db_type = "postgres" if "postgres" in self.database_url.lower() else "sqlite"
        
        self.engine = self._create_engine_instance()
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def _create_engine_instance(self):
        if self.db_type == "sqlite":
            self.connect_args.setdefault("check_same_thread", False)
        
        engine =  create_engine(
            self.database_url, 
            connect_args=self.connect_args, 
            echo=self.echo
        )

        # Apply WAL mode only if it's SQLite
        if self.db_type == "sqlite":
            @event.listens_for(engine, "connect")  # Attaching to THIS engine instance
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

        return engine