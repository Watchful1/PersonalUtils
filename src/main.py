import praw
import discord_logging
import argparse
import time
import os
import shutil
import traceback
import prawcore
import sys
import signal
import logging.handlers
from datetime import datetime, timedelta

log = discord_logging.init_logging()

import database
import utils
import counters


def signal_handler(signal, frame):
	log.info("Handling interrupt")
	discord_logging.flush_discord()
	database.session.commit()
	database.engine.dispose()
	sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


# Post on r/all under a certain age
# get the latest comment/post id to count how many comments/posts there are per hour


account_list = [
	{'username': "RemindMeBot", 'banned': False, 'checked': None, 'posted': None},
	{'username': "UpdateMeBot", 'banned': False, 'checked': None, 'posted': None},
	{'username': "NFCAAOfficialRefBot", 'banned': False, 'checked': None, 'posted': None},
	{'username': "OWMatchThreads", 'banned': False, 'checked': None, 'posted': None},
	{'username': "Watchful1BotTest", 'banned': False, 'checked': None, 'posted': None},
	{'username': "Watchful1Bot", 'banned': False, 'checked': None, 'posted': None},
	{'username': "Watchful12", 'banned': False, 'checked': None, 'posted': None},
	{'username': "RainbowPointsBot", 'banned': False, 'checked': None, 'posted': None},
	{'username': "NCAABBallPoster", 'banned': False, 'checked': None, 'posted': None},
	{'username': "CustomModBot", 'banned': False, 'checked': None, 'posted': None},
]


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
	for reddit_comment in reversed(list(reddit.user.me().comments.new(limit=50))):
		if datetime.utcfromtimestamp(reddit_comment.created_utc) > datetime.utcnow() - timedelta(hours=24 * 2):
			utils.process_reddit_object(reddit_comment, "comment", database, counters)

	# get post scores
	for reddit_submission in reversed(list(reddit.user.me().submissions.new(limit=10))):
		if datetime.utcfromtimestamp(reddit_submission.created_utc) > datetime.utcnow() - timedelta(hours=24 * 5):
			utils.process_reddit_object(reddit_submission, "submission", database, counters)

	# delete old objects
	utils.delete_old_objects("comment", database, counters, 24 * 2)
	utils.delete_old_objects("submission", database, counters, 24 * 5)

	# get karma totals
	me = reddit.user.me()
	me._fetch()
	counters.karma.labels(type="comment").set(me.comment_karma)
	counters.karma.labels(type="submission").set(me.link_karma)

	# check accounts for shadowbans
	for account in account_list:
		if account['banned'] or account['checked'] is None or account['checked'] < datetime.utcnow() - timedelta(minutes=60):
			msg = None
			try:
				fullname = reddit.redditor(account['username']).fullname
				if account['banned']:
					log.warning(f"u/{account['username']} has been unbanned")
					account['banned'] = False
			except prawcore.exceptions.NotFound:
				if not account['banned'] or account['posted'] is None or account['posted'] < datetime.utcnow() - timedelta(hours=24):
					msg = f"u/{account['username']} has been shadowbanned"
			except AttributeError:
				if not account['banned'] or account['posted'] is None or account['posted'] < datetime.utcnow() - timedelta(hours=24):
					msg = f"u/{account['username']} has been banned"
			if msg is not None:
				log.warning(f"u/{account['username']} has been banned")
				account['banned'] = True
				account['posted'] = datetime.utcnow()

			account['checked'] = datetime.utcnow()

	# post in announcements
	newest_post = next(reddit.subreddit("reddit").new())
	saved_post_id = database.session.query(database.KeyValue).filter_by(key="reddit_post").first().value
	if saved_post_id is None:
		log.info(f"First saving post id: {newest_post.id}")
		database.session.merge(database.KeyValue("reddit_post", newest_post.id))
	else:
		if saved_post_id != newest_post.id:
			log.warning(f"Posting on r/reddit post: <http://www.reddit.com{newest_post.permalink}>")
			try:
				comment_result = newest_post.reply(
					'''Thanks for answering questions Spez. There's a lot of anger going around over the decisions, but I'd like to try to ask something productive.
	
	If you look at any of the announcement threads from the third party app devs or subreddits announcing blackouts, the most common sentiment has been that people love the experience they get on their chosen apps and dislike the experience on the official app. To the point of saying they won't use the official app at all if their chosen app shuts down.
	
	Has reddit done any work over the last year or two to ask these third party app users what specifically they like about their chosen app and tried to build it into the official app? In my reading most of the differences have been relatively simple things like use of screen space and number of button clicks to complete certain actions, stuff that could be built in a matter of a month or two.
	
	Reddit has said a fair bit over the last few days about mod tools that are coming and accessibility issues, so I'd like to say I'm specifically not talking about those and am asking about the ordinary browsing experience of regular users.'''
				)
				log.warning(f"<@95296130761371648> Posted: <http://www.reddit.com{comment_result.permalink}>")
				database.session.merge(database.KeyValue("reddit_post", newest_post.id))
			except Exception as err:
				log.warning(f"Failed to comment on post <http://www.reddit.com{newest_post.permalink}> : {err}")

	database.session.commit()
	discord_logging.flush_discord()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Reddit Personal Utils")
	parser.add_argument("user", help="The reddit user account to use")
	parser.add_argument("--once", help="Only run the loop once", action='store_const', const=True, default=False)
	args = parser.parse_args()

	reddit = praw.Reddit(args.user)
	discord_logging.init_discord_logging(args.user, logging.WARNING, 1)

	counters.init(8004)

	database.init()

	log.info(f"Starting up: u/{args.user}")

	while True:
		try:
			main(reddit)
		except Exception as err:
			utils.process_error(f"Error in main loop", err, traceback.format_exc())

		discord_logging.flush_discord()

		if args.once:
			database.session.close()
			break

		time.sleep(60)
