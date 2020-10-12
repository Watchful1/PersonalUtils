import prometheus_client

inbox_size = prometheus_client.Gauge("bot_inbox_size", "Inbox size", ['type'])
folder_size = prometheus_client.Gauge("bot_folder_size", "Folder size", ['name'])
hard_drive_size = prometheus_client.Gauge("bot_hard_drive_size", "Hard drive size")
pushshift_beta_lag = prometheus_client.Gauge("bot_pushshift_beta_lag", "Pushshift beta endpoint lag")
pushshift_old_lag = prometheus_client.Gauge("bot_pushshift_old_lag", "Pushshift old endpoint lag")
pushshift_missing_beta_comments = prometheus_client.Counter("bot_pushshift_beta_missing", "Pushshift beta endpoint missing a comment")


def init(port):
	prometheus_client.start_http_server(port)
