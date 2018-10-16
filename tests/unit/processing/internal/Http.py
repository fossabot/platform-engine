# -*- coding: utf-8 -*-
from unittest.mock import MagicMock

from asyncy.Exceptions import AsyncyError
from asyncy.processing.Services import Services
from asyncy.processing.internal import Http
from asyncy.utils.HttpUtils import HttpUtils

import certifi

import pytest
from pytest import fixture, mark

from tornado.httpclient import AsyncHTTPClient


@fixture
def service_patch(patch):
    patch.object(Services, 'register_internal')


@fixture
def line():
    return {}


@mark.parametrize('method', [['post', 200], ['get', 201],
                             ['post', 500], ['get', 500]])
@mark.asyncio
async def test_service_http_fetch(patch, story, line,
                                  service_patch, async_mock, method):
    fetch_mock = MagicMock()
    patch.object(HttpUtils, 'fetch_with_retry',
                 new=async_mock(return_value=fetch_mock))
    patch.object(AsyncHTTPClient, '__init__', return_value=None)
    patch.object(certifi, 'where', return_value='ca_certs.pem')
    resolved_args = {
        'url': 'https://asyncy.com',
        'headers': {
            'Content-Type': 'application/json'
        },
        'method': method[0],
        'body': '{"foo":"bar"}'
    }

    client_kwargs = {
        'method': method[0].upper(),
        'ca_certs': 'ca_certs.pem',
        'headers': {
            'Content-Type': 'application/json',
            'User-Agent': 'Asyncy/1.0-beta'
        },
        'body': '{"foo":"bar"}'
    }
    fetch_mock.code = method[1]
    fetch_mock.body = 'hello world!'.encode('utf-8')
    if round(method[1] / 100) != 2:
        with pytest.raises(AsyncyError):
            await Http.http_post(story, line, resolved_args)
    else:
        result = await Http.http_post(story, line, resolved_args)
        HttpUtils.fetch_with_retry.mock.assert_called_with(
            3, story.logger, resolved_args['url'],
            AsyncHTTPClient(), client_kwargs
        )
        assert result == fetch_mock.body.decode('utf-8')


def test_service_http_init():
    Http.init()
