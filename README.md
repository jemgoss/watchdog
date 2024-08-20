# Simple systemd watchdog example

Quick demonstration of a systemd service with a watchdog.

```
$ mkdir -p ~/.config/systemd/user/
$ cp watchdog.service ~/.config/systemd/user/
$ systemctl start --user watchdog
$ journalctl --user -u watchdog.service -f
$ systemctl stop --user watchdog
```

In another terminal:
```
$ curl -X POST https://localhost:9080/api/restart
$ curl -X POST https://localhost:9080/api/disableNotify
$ curl -X POST https://localhost:9080/api/shutdown
```
