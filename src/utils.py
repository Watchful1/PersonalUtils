import os
import discord_logging
import prawcore
import requests
import traceback
from datetime import datetime

log = discord_logging.get_logger()


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
	return datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%S.%f+00:00")


def conversation_is_unread(conversation):
	return conversation.last_unread is not None and parse_modmail_datetime(conversation.last_unread) > \
				parse_modmail_datetime(conversation.last_updated)


def get_keyword_comments(keyword, base_url, limit):
	url = f"{base_url}?{('' if keyword is None else 'q='+keyword)}&limit={limit}&sort=desc"
	try:
		response = requests.get(url, headers={'User-Agent': "Remind me tester"}, timeout=10)
		if response.status_code != 200:
			log.warning(f"Pushshift error: {response.status_code} : {url}")
			return []
		return response.json()['data']

	except requests.exceptions.ReadTimeout:
		log.warning(f"Pushshift timeout : {url}")
		return []

	except Exception as err:
		log.warning(f"Could not parse data for search term: {keyword} : {url}")
		log.warning(traceback.format_exc())
		return []
