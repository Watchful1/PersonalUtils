import prometheus_client

inbox_size = prometheus_client.Gauge("bot_inbox_size", "Inbox size", ['type'])
folder_size = prometheus_client.Gauge("bot_folder_size", "Folder size", ['name'])
hard_drive_size = prometheus_client.Gauge("bot_hard_drive_size", "Hard drive size")
scores = prometheus_client.Gauge("bot_reddit_scores", "Post/comment scores", ['id', 'type'])


def init(port):
	prometheus_client.start_http_server(port)
