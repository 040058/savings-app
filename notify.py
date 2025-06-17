# notify.py
import requests

LINE_NOTIFY_TOKEN = '你的_LINE_NOTIFY_TOKEN'

def send_line_notify(message):
    url = 'https://notify-api.line.me/api/notify'
    headers = {
        "Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"
    }
    data = {'message': message}
    return requests.post(url, headers=headers, data=data)