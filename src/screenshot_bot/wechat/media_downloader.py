from .official_api import AccessTokenInvalidError, WeChatOfficialClient


class WeChatMediaDownloader:
    def __init__(self, appid=None, appsecret=None, client=None):
        self.client = client or WeChatOfficialClient(appid, appsecret)

    def download(self, media_id):
        try:
            return self._download(media_id, force_refresh=False)
        except AccessTokenInvalidError:
            # Same recovery as WeChatImageSender: the cached token was rejected
            # server-side, force one fresh token and retry once.
            return self._download(media_id, force_refresh=True)

    def _download(self, media_id, force_refresh):
        token = self.client.get_access_token(force_refresh=force_refresh)
        return self.client.download_media(token, media_id)
