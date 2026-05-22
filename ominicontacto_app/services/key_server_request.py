# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

import requests

from constance import config as config_constance


class KeyServerRequest(object):

    def __init__(self, timeout=None):
        self.timeout = timeout

    def _hosts(self):
        hosts = [config_constance.PRIMARY_KEYS_SERVER_HOST]
        secondary_host = getattr(config_constance, 'SECONDARY_KEY_SERVER_HOST', None)
        if secondary_host and secondary_host not in hosts:
            hosts.append(secondary_host)

        return hosts

    def _request(self, method, path, **kwargs):
        last_exception = None
        last_response = None

        request_kwargs = dict(kwargs)
        if self.timeout is not None:
            request_kwargs.setdefault('timeout', self.timeout)

        for host in self._hosts():
            url = '{0}/{1}'.format(host.rstrip('/'), path.lstrip('/'))
            try:
                response = requests.request(method, url, **request_kwargs)
            except requests.RequestException as error:
                last_exception = error
                continue

            if response.ok:
                return response

            last_response = response

        if last_exception is not None:
            raise last_exception

        return last_response

    def get(self, path, **kwargs):
        return self._request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self._request('POST', path, **kwargs)
