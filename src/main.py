import praw
import discord_logging
import argparse
import prometheus_client
import time
import os
import shutil
import traceback
import requests
import sys
import signal
from datetime import datetime, timedelta

log = discord_logging.init_logging()

import database
import utils
import counters
from database import Comment


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	database.session.close()
	discord_logging.flush_discord()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# Post when a comment from me hits upvote thresholds, track recent comments upvote count over time
# Post on r/all under a certain age
# get the latest comment/post id to count how many comments/posts there are per hour
# notify when I hide a post


def main(reddit, missing_comment_ids):
	# mark r/fakecollegefootball modmails as read
	for conversation in reddit.subreddit('fakecollegefootball').modmail.conversations(limit=10, state='all'):
		if utils.conversation_is_unread(conversation):
			log.info(f"Marking r/fakecollegefootball conversation {conversation.id} as read")
			conversation.read()

	# export inbox size
	count_messages, count_comments = 0, 0
	for inbox_item in reddit.inbox.unread(limit=None):
		if inbox_item.fullname.startswith("t1_"):
			count_comments += 1
		elif inbox_item.fullname.startswith("t4_"):
			count_messages += 1
		else:
			log.warning(f"Unexpected item in inbox: {inbox_item.fullname}")
	counters.inbox_size.labels(type="messages").set(count_messages)
	counters.inbox_size.labels(type="comments").set(count_comments)

	# export folder sizes
	base_folder = "/home/watchful1"
	for dir_path, dir_names, file_names in os.walk(base_folder):
		for dir_name in dir_names:
			if dir_name.startswith("."):
				continue
			folder_bytes = utils.get_size(base_folder + "/" + dir_name)
			counters.folder_size.labels(name=dir_name).set(folder_bytes / 1024 / 1024)
		break

	# export hard drive space
	total, used, free = shutil.disk_usage("/")
	counters.hard_drive_size.set(round(used / (2 ** 30), 2))

	# pushshift beta tracking
	# get beta comments
	comments_added = []
	comments, seconds = utils.get_keyword_comments("remindme", "https://beta.pushshift.io/search/reddit/comments", 100, "size")
	counters.scan_seconds.labels("beta").observe(seconds)
	for comment in comments:
		if database.session.query(Comment).filter_by(id=comment['id']).count() > 0:
			break

		database.session.merge(
			Comment(
				comment['id'],
				datetime.utcfromtimestamp(comment['created_utc']),
				datetime.utcfromtimestamp(comment['retrieved_utc'])
			)
		)
		comments_added.append(comment['id'])
	# if len(comments_added) > 0:
	# 	log.info(f"Added comments: {','.join(comments_added)}")

	# now get old pushshift comments and compare
	comments, seconds = utils.get_keyword_comments("remindme", "https://api.pushshift.io/reddit/comment/search", 100, "limit")
	counters.scan_seconds.labels("prod").observe(seconds)
	for comment in comments:
		if comment['id'] not in missing_comment_ids and database.session.query(Comment).filter_by(id=comment['id']).count() == 0:
			log.info(f"Missing comment: {comment['id']}")
			missing_comment_ids.add(comment['id'])
			counters.pushshift_missing_beta_comments.inc()

	# beta ingest lag
	comments, seconds = utils.get_keyword_comments(None, "https://beta.pushshift.io/search/reddit/comments", 1, "size")
	if len(comments):
		counters.pushshift_beta_lag.set(round((datetime.utcnow() - datetime.utcfromtimestamp(comments[0]['created_utc'])).total_seconds() / 60, 0))

	# old ingest lag
	comments, seconds = utils.get_keyword_comments(None, "https://api.pushshift.io/reddit/comment/search", 1, "limit")
	if len(comments):
		counters.pushshift_old_lag.set(round((datetime.utcnow() - datetime.utcfromtimestamp(comments[0]['created_utc'])).total_seconds() / 60, 0))

	database.session.commit()
	discord_logging.flush_discord()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Reddit Personal Utils")
	parser.add_argument("user", help="The reddit user account to use")
	parser.add_argument("--once", help="Only run the loop once", action='store_const', const=True, default=False)
	args = parser.parse_args()

	reddit = praw.Reddit(args.user)

	counters.init(8004)

	database.init()

	log.info(f"Starting up: u/{args.user}")

	missing_comment_ids = set()
	while True:
		try:
			main(reddit, missing_comment_ids)
		except Exception as err:
			utils.process_error(f"Error in main loop", err, traceback.format_exc())

		if args.once:
			break

		time.sleep(60)
