import requests
from configs import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from twilio.rest import Client

class TwilioMediaHelper:
    def __init__(self):
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.client = Client(self.account_sid, self.auth_token)

    def send_message(self, to: str, body: str):
        message = self.client.messages.create(
            to=f"{to}",
            from_="whatsapp:+14155238886",
            body=body
        )
        return message

    def list_media(self, message_sid: str):
        media_list = self.client.messages(message_sid).media.list()
        results = []
        for m in media_list:
            media_url = f"https://api.twilio.com{m.uri.replace('.json', '')}"
            results.append({
                "sid": m.sid,
                "content_type": m.content_type,
                "url": media_url
            })
        return results

    def download_media(self, media_url: str, filename: str):
        resp = requests.get(media_url, auth=(self.account_sid, self.auth_token))
        resp.raise_for_status()
        with open(filename, "wb") as f:
            f.write(resp.content)
        return filename

    def download_all_media(self, message_sid: str, save_dir: str = "."):
        media_files = self.list_media(message_sid)
        saved_files = []
        for m in media_files:
            filename = f"{save_dir}/{m['sid']}"
            self.download_media(m["url"], filename)
            saved_files.append(filename)
        return saved_files
