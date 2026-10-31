import os

c.ServerApp.ip = "0.0.0.0"
c.ServerApp.port = 8888
c.ServerApp.open_browser = False
c.ServerApp.root_dir = "/workspace"
c.ServerApp.allow_remote_access = True
c.ServerApp.terminals_enabled = True
c.ServerApp.disable_check_xsrf = False

token = os.environ.get("JUPYTER_TOKEN")
if token:
    c.ServerApp.token = token

