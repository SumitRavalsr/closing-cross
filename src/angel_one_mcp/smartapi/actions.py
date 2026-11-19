from enum import Enum

from angel_one_mcp.smartapi.client import SmartAPISessionExpired
from angel_one_mcp.smartapi.errors import BrokerError
from angel_one_mcp.smartapi.reads import ORDERS, SECURE, SmartAPIReads


class Action(Enum):
    PLACE_ORDER = f'{ORDERS}/placeOrder'
    MODIFY_ORDER = f'{ORDERS}/modifyOrder'
    CANCEL_ORDER = f'{ORDERS}/cancelOrder'
    CONVERT_POSITION = f'{ORDERS}/convertPosition'
    CREATE_GTT_RULE = f'{SECURE}/gtt/v1/createRule'
    MODIFY_GTT_RULE = f'{SECURE}/gtt/v1/modifyRule'
    CANCEL_GTT_RULE = f'{SECURE}/gtt/v1/cancelRule'
    INITIATE_EDIS = f'{SECURE}/edis/v1/verifyDis'
    GENERATE_EDIS_TPIN = f'{SECURE}/edis/v1/generateTPIN'
    LOGOUT = f'{SECURE}/user/v1/logout'


class SmartAPIBroker(SmartAPIReads):
    def action(self, endpoint: Action, payload: dict | None = None):
        if endpoint is Action.LOGOUT:
            if 'Authorization' not in self._headers:
                self.clear_session()
                return None
            payload = {'clientcode': self._credentials.client_code}
        try:
            return self._authenticated('POST', endpoint.value, endpoint.name.lower(), payload,
                                       retry_expired=False)
        except SmartAPISessionExpired:
            raise BrokerError('SmartAPI session expired during the action. Check broker state before retrying') from None
        except BrokerError as error:
            raise BrokerError(f'{error}. Check broker state before retrying') from None
        finally:
            if endpoint is Action.LOGOUT:
                self.clear_session()

    def stream_credentials(self, market: bool, rejected_auth: str | None = None) -> tuple[dict[str, str], set[str]]:
        authorization = self._headers.get('Authorization')
        if not authorization or authorization == rejected_auth:
            self.recover_session()
        headers = {'Authorization': self._headers['Authorization']}
        if market:
            if not self._feed_token:
                raise BrokerError('SmartAPI session did not provide a market feed token')
            headers.update({
                'x-api-key': self._credentials.api_key,
                'x-client-code': self._credentials.client_code,
                'x-feed-token': self._feed_token,
            })
        return headers, self.session_secrets()
