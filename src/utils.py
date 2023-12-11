import os
import discord_logging
import prawcore
import requests
import traceback
import time
from datetime import datetime, timedelta

log = discord_logging.get_logger()

from database import RedditObject


def process_error(message, exception, traceback):
	is_transient = \
		isinstance(exception, prawcore.exceptions.ServerError) or \
		isinstance(exception, requests.exceptions.Timeout) or \
		isinstance(exception, requests.exceptions.ReadTimeout)
	log.warning(f"{message}: {exception}")
	if is_transient:
		log.info(traceback)
	else:
		log.warning(traceback)

	return is_transient


def get_size(start_path):
	total_size = 0
	for dir_path, dir_names, file_names in os.walk(start_path):
		for f in file_names:
			fp = os.path.join(dir_path, f)
			# skip if it is symbolic link
			if not os.path.islink(fp):
				total_size += os.path.getsize(fp)

	return total_size


def parse_modmail_datetime(datetime_string):
	try:
		return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")
	except ValueError:
		return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+0000")



def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) >= \
				parse_modmail_datetime(conversation.last_updated)


def get_keyword_comments(keyword, base_url, limit, size_keyword):
	url = f"{base_url}?{('' if keyword is None else 'q='+keyword)}&{size_keyword}={limit}&sort=desc"
	try:
		start_time = time.perf_counter()
		response = requests.get(url, headers={'User-Agent': "Remind me tester"}, timeout=10)
		if response.status_code != 200:
			log.warning(f"Pushshift error: {response.status_code} : {url}")
			return [], 10
		return response.json()['data'], round(time.perf_counter() - start_time, 2)

	except requests.exceptions.ReadTimeout:
		log.warning(f"Pushshift timeout : {url}")
		return [], 10

	except Exception as err:
		log.warning(f"Could not parse data for search term: {keyword} : {url}")
		log.warning(traceback.format_exc())
		return [], 10


def process_reddit_object(reddit_object, object_type, database, counters):
	db_object = database.session.query(RedditObject)\
		.filter_by(object_type=object_type)\
		.filter_by(object_id=reddit_object.id)\
		.first()
	if db_object is None:
		log.info(f"New {object_type} {reddit_object.id}")
		db_object = RedditObject(reddit_object.id, object_type, reddit_object.score)
		database.session.add(db_object)
	else:
		db_object.record_score(reddit_object.score)

	counters.scores.labels(id=db_object.object_id, type=db_object.object_type).set(db_object.get_avg_score())


def delete_old_objects(object_type, database, counters, hours):
	before_date = datetime.utcnow() - timedelta(hours=hours)

	db_objects = database.session.query(RedditObject)\
		.filter_by(object_type=object_type)\
		.filter(RedditObject.time_created < before_date)\
		.all()

	for db_object in db_objects:
		log.info(f"Removing old {object_type} {db_object.object_id}")
		try:
			counters.scores.remove(db_object.object_id, db_object.object_type)
		except KeyError:
			pass
		database.session.delete(db_object)
