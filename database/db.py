from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

class Database_Initializer():
    def __init__(self, base):
        self.base = base

    def init_db(self, dsn):
        engine = create_engine(dsn)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.base.metadata.create_all(bind=engine)

        return SessionLocal
    
Base = declarative_base()
DB_INITIALIZER = Database_Initializer(Base)