import praw
import discord_logging
import argparse
import prometheus_client
import time
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
	prom_upvotes = prometheus_client.Counter("bot_upvotes", "Comment/post upvote counts", ['fullname'])
	prom_inbox_size = prometheus_client.Gauge("bot_inbox_size", "Inbox size", ['type'])

	while True:
		# mark r/fakecollegefootball modmails as read
		for conversation in reddit.subreddit('fakecollegefootball').modmail.conversations(limit=10, state='all'):
			if conversation_is_unread(conversation):
				log.info(f"Marking r/fakecollegefootball conversation {conversation.id} as read")
				conversation.read()

		if args.once:
			break

		time.sleep(60)
