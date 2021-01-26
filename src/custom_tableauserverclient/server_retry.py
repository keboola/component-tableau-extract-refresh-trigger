from tableauserverclient import Server


class RetryServer(Server):

    def __init__(self, server_address, use_server_ver, custom_session):
        Server.__init__(self, server_address, use_server_ver)
        self._session = custom_session
