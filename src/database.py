from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
engine = None
session = None


class Comment(Base):
	__tablename__ = 'comments'

	id = Column(String(60), primary_key=True)
	created = Column(DateTime, nullable=False)
	retrieved = Column(DateTime, nullable=False)

	def __init__(self, id, created, retrieved):
		self.id = id
		self.created = created
		self.retrieved = retrieved


def init():
	global engine
	global session
	engine = create_engine(f'sqlite:///database.db')
	session_maker = sessionmaker(bind=engine)
	session = session_maker()
	Base.metadata.create_all(engine)
	session.commit()
