from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    task_text = Column(String)
    assigned_to = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed = Column(Boolean, default=False)
    reminder_minutes = Column(Integer)
    last_reminder = Column(DateTime, nullable=True)

class Concern(Base):
    __tablename__ = 'concerns'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    raised_by = Column(String)
    concern_text = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved = Column(Boolean, default=False)

# Create database engine
engine = create_engine('sqlite:///trichygold.db')
Base.metadata.create_all(engine)

# Create session factory
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
