# -*- coding: utf-8 -*-
from asyncy.Config import Config
from asyncy.models import Applications, Repositories, Stories, Users

from pytest import fixture


@fixture
def magic(mocker):
    """
    Shorthand for mocker.MagicMock. It's magic!
    """
    return mocker.MagicMock


@fixture
def patch(mocker):
    return mocker.patch


@fixture
def logger(magic):
    return magic()


@fixture
def user():
    return Users('name', 'email', '@handle')


@fixture
def application(user, magic):
    app = Applications(name='app', user=user)
    app.stories = magic()
    return app


@fixture
def repository(user):
    return Repositories(name='project', organization='org', owner=user)


@fixture
def story(repository):
    return Stories(filename='test.story', repository=repository)


@fixture
def context(application):
    return {'application': application, 'story': 'story', 'results': {},
            'environment': {}}


@fixture
def config(mocker):
    return Config()
