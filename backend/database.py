from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid

engine = create_engine("sqlite:///./research.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class ResearchRequest(Base):
    __tablename__ = "research_requests"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ticker = Column(String, nullable=False)
    company = Column(String)
    status = Column(String, default="pending")
    brief_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()