# gunicorn.conf.py — Production server config for EC2

bind = "0.0.0.0:5000"
workers = 2
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
