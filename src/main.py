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


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	database.session.close()
	discord_logging.flush_discord()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# Track total karma
# Post on r/all under a certain age
# get the latest comment/post id to count how many comments/posts there are per hour


def main(reddit):
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

	count_objects_to_track = 25
	# get comment scores
	for reddit_comment in reversed(list(reddit.user.me().comments.new(limit=count_objects_to_track))):
		utils.process_reddit_object(reddit_comment, "comment", database, counters)

	# get post scores
	for reddit_submission in reversed(list(reddit.user.me().submissions.new(limit=count_objects_to_track))):
		utils.process_reddit_object(reddit_submission, "submission", database, counters)

	# delete old objects
	utils.delete_old_objects("comment", database, counters, count_objects_to_track)
	utils.delete_old_objects("submission", database, counters, count_objects_to_track)

	# get karma totals
	counters.karma.labels(type="comment").set(reddit.user.me().comment_karma)
	counters.karma.labels(type="submission").set(reddit.user.me().link_karma)

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

	while True:
		try:
			main(reddit)
		except Exception as err:
			utils.process_error(f"Error in main loop", err, traceback.format_exc())

		if args.once:
			database.session.close()
			break

		time.sleep(60)
