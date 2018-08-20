# -*- coding: utf-8 -*-
from io import BytesIO, StringIO
from unittest.mock import MagicMock

from asyncy.Config import Config
from asyncy.Containers import Containers, MAX_RETRIES
from asyncy.Exceptions import AsyncyError, DockerError
from asyncy.constants.ServiceConstants import ServiceConstants
from asyncy.processing import Story

import pytest
from pytest import fixture, mark

from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPRequest, \
    HTTPResponse


@fixture
def line():
    return MagicMock()


@fixture
def http_response():
    def build(url, code, body):
        return HTTPResponse(HTTPRequest(url=url), code, buffer=StringIO(body))

    return build


@mark.asyncio
async def test_containers_start_container(patch, story, line, async_mock):
    response = MagicMock()
    response.code = 204
    patch.object(Containers, '_make_docker_request',
                 new=async_mock(return_value=response))
    await Containers._start_container(story, line, 'foo')
    Containers._make_docker_request.mock.assert_called_with(
        story, line, '/containers/foo/start', data='', method='POST')

    response.code = 304
    await Containers._start_container(story, line, 'foo')

    with pytest.raises(DockerError):
        response.code = 500
        await Containers._start_container(story, line, 'foo')


@mark.asyncio
async def test_containers_inspect_container(patch, story, line, async_mock):
    response = MagicMock()
    response.code = 200
    response.body = '{"foo": "bar"}'
    patch.object(Containers, '_make_docker_request',
                 new=async_mock(return_value=response))

    ret = await Containers.inspect_container(story, line, 'foo')

    Containers._make_docker_request.mock.assert_called_with(
        story, line, '/containers/foo/json')

    assert ret == {'foo': 'bar'}

    response.code = 500
    ret = await Containers.inspect_container(story, line, 'foo')

    assert ret is None


@mark.asyncio
async def test_containers_stop_container(patch, story, line, async_mock):
    response = MagicMock()
    response.code = 204
    response.body = '{"foo":"bar"}'
    patch.object(Containers, '_make_docker_request',
                 new=async_mock(return_value=response))
    ret = await Containers.stop_container(story, line, 'foo')
    Containers._make_docker_request.mock.assert_called_with(
        story, line, '/containers/foo/stop')
    assert ret == {'foo': 'bar'}

    response.code = 304
    ret = await Containers.stop_container(story, line, 'foo')
    assert ret == {'foo': 'bar'}

    with pytest.raises(DockerError):
        response.code = 500
        await Containers.stop_container(story, line, 'foo')


@mark.asyncio
async def test_containers_remove_container(patch, story, line, async_mock):
    response = MagicMock()
    response.code = 204
    patch.object(Containers, '_make_docker_request',
                 new=async_mock(return_value=response))
    await Containers.remove_container(story, line, 'foo')
    Containers._make_docker_request.mock.assert_called_with(
        story, line, '/containers/foo?force=false', method='DELETE')

    response.code = 304
    await Containers.remove_container(story, line, 'foo', force=True)
    Containers._make_docker_request.mock.assert_called_with(
        story, line, '/containers/foo?force=true', method='DELETE')

    response.code = 404
    await Containers.remove_container(story, line, 'foo')

    with pytest.raises(DockerError):
        response.code = 500
        await Containers.remove_container(story, line, 'foo')


@mark.asyncio
async def test_container_get_hostname(patch, story, line, async_mock):
    patch.object(Containers, 'inspect_container',
                 new=async_mock(
                     return_value={'Config': {'Hostname': 'foo.com'}}
                 ))
    ret = await Containers.get_hostname(story, line, 'foo')
    assert ret == 'foo.com'


@mark.asyncio
async def test_container_exec(patch, story, app, logger, async_mock, line):
    create_response = MagicMock()
    create_response.body = '{"Id": "exec_id"}'

    exec_response = MagicMock()
    exec_response.buffer = BytesIO(b'\x01\x00\x00\x00\x00\x00\x00\x03asy'
                                   b'\x01\x00\x00\x00\x00\x00\x00\x01n'
                                   b'\x01\x00\x00\x00\x00\x00\x00\x01c'
                                   b'\x02\x00\x00\x00\x00\x00\x00\x08my_error'
                                   b'\x01\x00\x00\x00\x00\x00\x00\x02y\n')

    patch.object(AsyncHTTPClient, '__init__', return_value=None)

    patch.object(AsyncHTTPClient, 'fetch',
                 new=async_mock(side_effect=[create_response, exec_response]))

    app.config = Config()

    story.app = app
    story.app.services = {}
    story.prepare()

    patch.object(Containers, 'format_command', return_value=['pwd'])

    line = {
        'service': 'alpine',
        'command': 'pwd'
    }

    result = await Containers.exec(logger, story, line, 'alpine', 'pwd')

    assert result == 'asyncy'

    fetch = AsyncHTTPClient.fetch.mock

    endpoint = app.config.DOCKER_HOST
    if story.app.config.DOCKER_TLS_VERIFY == '1':
        endpoint = endpoint.replace('http://', 'https://')

    assert fetch.mock_calls[0][1][1] == \
        '{0}/v1.37/containers/asyncy--alpine-1/exec'.format(endpoint)
    assert fetch.mock_calls[0][2]['method'] == 'POST'
    assert fetch.mock_calls[0][2]['body'] == \
        '{"Container":"asyncy--alpine-1","User":"root","Privileged":false,' \
        '"Cmd":["pwd"],"AttachStdin":false,' \
        '"AttachStdout":true,"AttachStderr":true,"Tty":false}'

    assert fetch.mock_calls[1][1][1] == \
        '{0}/v1.37/exec/exec_id/start'.format(endpoint)
    assert fetch.mock_calls[1][2]['method'] == 'POST'
    assert fetch.mock_calls[1][2]['body'] == '{"Tty":false,"Detach":false}'


@mark.asyncio
async def test_fetch_with_retry(patch, story, line):
    def raise_error(url, **kwargs):
        raise HTTPError(500)

    patch.object(AsyncHTTPClient, 'fetch', side_effect=raise_error)
    client = AsyncHTTPClient()

    with pytest.raises(DockerError):
        # noinspection PyProtectedMember
        await Containers._fetch_with_retry(story, line, 'url', client, {})

    assert client.fetch.call_count == MAX_RETRIES


@mark.asyncio
async def test_get_network_name(patch, story, line, async_mock, http_response):
    patch.object(
        Containers, '_make_docker_request',
        new=async_mock(
            return_value=http_response('/networks', 200,
                                       '[{"Name": "foo"},'
                                       '{"Name":"90_asyncy-backend"}]')))

    name = await Containers.get_network_name(story, line)
    assert name == '90_asyncy-backend'


@mark.asyncio
async def test_get_network_name_exc(patch, story, line,
                                    async_mock, http_response):
    patch.object(
        Containers, '_make_docker_request',
        new=async_mock(
            return_value=http_response('/networks', 200,
                                       '[{"Name": "92_asyncy-backend"},'
                                       '{"Name":"90_asyncy-backend"}]')))
    with pytest.raises(AsyncyError):
        await Containers.get_network_name(story, line)


def test_format_command(logger, app, echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = echo_service

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo', '{"msg":"foo"}'] == cmd


def test_format_command_no_format(logger, app, echo_service, echo_line):
    story = Story.story(app, logger, 'echo.story')
    app.services = echo_service

    config = app.services['alpine'][ServiceConstants.config]
    config['commands']['echo']['format'] = None

    cmd = Containers.format_command(story, echo_line, 'alpine', 'echo')
    assert ['echo', '{"msg":"foo"}'] == cmd
