from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import discord_logging

log = discord_logging.get_logger()

Base = declarative_base()
engine = None
session = None


class RedditObject(Base):
	__tablename__ = 'objects'

	id = Column(Integer, primary_key=True)
	object_id = Column(String(60), nullable=False)
	object_type = Column(String(60), nullable=False)
	scores = relationship("Score")

	def __init__(self, object_id, object_type, score):
		self.object_id = object_id
		self.object_type = object_type
		self.scores = [Score(score)]

	def get_avg_score(self):
		total = 0
		for score in self.scores:
			total += score.score
		return int(round(total / len(self.scores), 0))

	def record_score(self, score):
		if score < 10:
			count_scores = 25
		elif score < 100:
			count_scores = 50
		elif score < 500:
			count_scores = 75
		else:
			count_scores = 100
		if len(self.scores) >= count_scores:
			old_average = self.get_avg_score()
			self.scores.pop(0)
			self.scores.append(Score(score))
			new_average = self.get_avg_score()
			if old_average != new_average:
				log.warning(f"{self.object_type} {self.object_id} from {old_average} to {new_average}")
		else:
			self.scores.append(Score(score))

	def __str__(self):
		return f"{self.object_id} : {self.get_avg_score()} : "+','.join([str(score) for score in self.scores])


class Score(Base):
	__tablename__ = 'scores'

	id = Column(Integer, primary_key=True)
	score = Column(Integer, nullable=False)
	object_id = Column(Integer, ForeignKey('objects.id'))

	def __init__(self, score):
		self.score = score

	def __str__(self):
		return str(self.score)


def init():
	global engine
	global session
	engine = create_engine(f'sqlite:///database.db')
	session_maker = sessionmaker(bind=engine)
	session = session_maker()
	Base.metadata.create_all(engine)
	session.commit()
