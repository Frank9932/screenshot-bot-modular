from .official_api import AccessTokenInvalidError, WeChatOfficialClient


class WeChatMenuManager:
    """Pushes/reads the account's tap-to-command custom menu. Mirrors WeChatImageSender's
    retry-once-on-invalid-token pattern rather than sharing a base class with it -- the two
    have no other behavior in common, and menu pushes are rare (an operator action, not a
    per-message hot path)."""

    def __init__(self, appid, appsecret, client=None):
        self.client = client or WeChatOfficialClient(appid, appsecret)

    def set_menu(self, menu):
        try:
            return self._set_menu(menu, force_refresh=False)
        except AccessTokenInvalidError:
            return self._set_menu(menu, force_refresh=True)

    def _set_menu(self, menu, force_refresh):
        token = self.client.get_access_token(force_refresh=force_refresh)
        return self.client.create_menu(token, menu)

    def get_menu(self):
        try:
            return self._get_menu(force_refresh=False)
        except AccessTokenInvalidError:
            return self._get_menu(force_refresh=True)

    def _get_menu(self, force_refresh):
        token = self.client.get_access_token(force_refresh=force_refresh)
        return self.client.get_menu(token)
