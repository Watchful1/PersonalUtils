import praw
import discord_logging
import argparse
import prometheus_client
import time
import os
from datetime import datetime, timedelta

log = discord_logging.init_logging()


# Mark r/fakecollegefootball modmails as read
# Post when a comment from me hits upvote thresholds, track recent comments upvote count over time
# Post on r/all under a certain age
# Inbox size
# get the latest comment/post id to count how many comments/posts there are per hour
# notify when I hide a post
# Total server disk space
# Various folder sizes


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


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Reddit Personal Utils")
	parser.add_argument("user", help="The reddit user account to use")
	parser.add_argument("--once", help="Only run the loop once", action='store_const', const=True, default=False)
	args = parser.parse_args()

	reddit = praw.Reddit(args.user)

	prometheus_client.start_http_server(8004)
	#prom_upvotes = prometheus_client.Counter("bot_upvotes", "Comment/post upvote counts", ['fullname'])
	prom_inbox_size = prometheus_client.Gauge("bot_inbox_size", "Inbox size", ['type'])
	prom_folder_size = prometheus_client.Gauge("bot_folder_size", "Folder size", ['name'])

	log.info(f"Starting up: u/{args.user}")

	while True:
		# mark r/fakecollegefootball modmails as read
		for conversation in reddit.subreddit('fakecollegefootball').modmail.conversations(limit=10, state='all'):
			if conversation_is_unread(conversation):
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
		prom_inbox_size.labels(type="messages").set(count_messages)
		prom_inbox_size.labels(type="comments").set(count_comments)

		# export folder sizes
		base_folder = "/home/watchful1"
		for dir_path, dir_names, file_names in os.walk(base_folder):
			for dir_name in dir_names:
				if dir_name.startswith("."):
					continue
				folder_bytes = get_size(base_folder + "/" + dir_name)
				prom_folder_size.labels(name=dir_name).set(folder_bytes / 1024 / 1024)
			break

		if args.once:
			break

		time.sleep(60)
