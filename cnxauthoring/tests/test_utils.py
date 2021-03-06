# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###

import datetime
import json
import unittest
try:
    import urlparse  # python2
except ImportError:
    import urllib.parse as urlparse  # renamed in python3
try:
    from unittest import mock  # python3
except ImportError:
    import mock  # python2

import httpretty
from pyramid import testing

from .. import utils
from .testing import integration_test_settings


class CaptureRequest:
    """Used to capture a HTTPretty request.

    Use in the ``register_uri`` method like so::

        captured_request = CaptureRequest()
        httpretty.register_uri(method, url, body=captured_request)

    Then use the ``request`` attribute on the object after the request
    has gone through.

    """

    def __init__(self, status=200, body=''):
        self._resp_status = status
        self._resp_body = body
        # Place to put the captured values...
        self.headers = None
        self.body = None
        self.request = None

    def __call__(self, request, uri, headers):
        self.request = request
        self.headers = request.headers
        self.body = request.body
        return self._resp_status, headers, self._resp_body


class UtilsTests(unittest.TestCase):

    maxDiff = None

    def test_change_dict_keys(self):
        data = {
            'id': '1234',
            'deriveFrom': 'uuid@version',
            'nextLevel': {
                'anotherLevel': {
                    'someOtherThing': 'value',
                    },
                },
            'listItem': [
                {'itemTitle': 'itemValue'},
                {'itemTitle2': 'itemValue2'},
                'itemTitle3',
                ],
            }
        utils.change_dict_keys(data, utils.camelcase_to_underscore)
        self.assertEqual(data, {
            'id': '1234',
            'derive_from': 'uuid@version',
            'next_level': {
                'another_level': {
                    'some_other_thing': 'value',
                    },
                },
            'list_item': [
                {'item_title': 'itemValue'},
                {'item_title2': 'itemValue2'},
                'itemTitle3',
                ],
            })

    def test_camelcase_to_underscore(self):
        c2u = utils.camelcase_to_underscore

        self.assertEqual(c2u('id'), 'id')
        self.assertEqual(c2u('deriveFrom'), 'derive_from')
        self.assertEqual(c2u('someOtherThing'), 'some_other_thing')

    def test_underscore_to_camelcase(self):
        u2c = utils.underscore_to_camelcase

        self.assertEqual(u2c('id'), 'id')
        self.assertEqual(u2c('derive_from'), 'deriveFrom')
        self.assertEqual(u2c('some_other_thing'), 'someOtherThing')

    def test_empty_profile_to_dict(self):
        expected = {
            'firstname': '',
            'surname': '',
            'id': '',
            'fullname': '',
            }
        with self.assertRaises(ValueError) as caught_exc:
            utils.profile_to_user_dict({})
        self.assertEqual(
            caught_exc.exception.args[0],
            "A 'username' or 'id' MUST be supplied in the profile argument.")

    def test_full_profile_to_dict(self):
        profile = {
            'first_name': u'Cäroline',
            'last_name': u'Läne',
            'id': 1234,
            'username': 'clane',
            }
        expected = {
            'firstname': u'Cäroline',
            'surname': u'Läne',
            'id': 'clane',
            'fullname': u'Cäroline Läne',
            'suffix': None,
            'title': None,
            }

        self.assertEqual(utils.profile_to_user_dict(profile), expected)

    def test_profile_to_dict_twice(self):
        original = {
            'firstname': 'Caroline',
            'surname': 'Lane',
            'id': 'clane',
            'fullname': 'Caroline Lane',
            }
        expected = original.copy()
        expected['title'] = None
        expected['suffix'] = None
        self.assertEqual(utils.profile_to_user_dict(original), expected)

    def test_utf8_single_string(self):
        test1 = b'simple test string!'
        test2 = u'idzie wąż wąską dróżką'.encode('utf-8')

        self.assertEqual(utils.utf8(test1).encode('utf-8'), test1)
        self.assertEqual(utils.utf8(test2).encode('utf-8'), test2)

    def test_utf8_list(self):
        test_list = [
            b"email@something.org",
            u"Radioactive (Die Verstoßenen)".encode('utf-8'),
            u"40文字でわかる！".encode('utf-8')]
        utf8_list = utils.utf8(test_list)

        for i in range(len(test_list)):
            self.assertEqual(utf8_list[i].encode('utf-8'), test_list[i])

    def test_utf8_dict(self):
        test_dict = {
            b"First name": b"Caroline",
            u"知っておきたいhiビジネス理論".encode('utf-8'):
            u"40文字でわthereかる-知っ".encode('utf-8')}
        utf8_dict = utils.utf8(test_dict)

        for k, v in utf8_dict.items():
            self.assertEqual(v.encode("utf-8"), test_dict[k.encode('utf-8')])

    def test_structured_query_text(self):
        text1 = 'Some text'
        text2 = '知っておきたいhi thereかる-知っ'
        text3 = '"A phrase"'

        self.assertEqual(utils.structured_query(text1),
                         [('text', 'Some'), ('text', 'text')])
        self.assertEqual(utils.structured_query(text2),
                         [('text', '知っておきたいhi'),
                          ('text', 'thereかる-知っ')])
        self.assertEqual(utils.structured_query(text3),
                         [('text', 'A phrase')])

    def test_structured_query_terms_and_fields(self):
        query = 'author:"John Smith" type:book Radioactive:"(Die Verstoßenen)"'

        self.assertEqual(utils.structured_query(query), [
            ('author', 'John Smith'), ('type', 'book'),
            ('Radioactive', '(Die Verstoßenen)')])

    def test_structured_query_missing_quotes(self):
        test1 = '"Phrase without quotes'

        self.assertEqual(utils.structured_query(test1),
                         [('text', 'Phrase without quotes')])

    def test_declare_acl_on_create(self):
        from ..models import create_content

        document = create_content(
            title='My Document',
            submitter={'id': 'submitter'},
            authors=[{'id': 'author'}, {'id': 'me'}],
            editors=[{'id': 'editor'}],
            translators=[{'id': 'translator'}, {'id': 'you'}],
            publishers=[{'id': 'me', 'has_accepted': True},
                        {'id': 'you', 'has_accepted': True}],
            licensors=[{'id': 'licensor'}],
            illustrators=[{'id': 'illustrator'}],
            )
        settings = {
            'publishing.url': 'http://publishing/',
            'publishing.api_key': 'trusted-publisher',
            }

        records = [
            {'uid': 'me', 'permission': 'publish'},
            {'uid': 'you', 'permission': 'publish'},
            ]
        with mock.patch('requests.get') as get:
            get.return_value.status_code = 200
            get.json.side_effect = ([], records,)
            with mock.patch('requests.post') as post:
                post.return_value.status_code = 202

                with testing.testConfig(settings=settings):
                    utils.declare_acl(document)

                self.assertEqual(post.call_count, 1)
                (url,), kwargs = post.call_args
                self.assertEqual(
                    url,
                    'http://publishing/contents/{}/permissions'
                    .format(document.id))
                self.assertEqual(
                    json.loads(kwargs['data']),
                    [{'uid': 'me', 'permission': 'publish'},
                     {'uid': 'you', 'permission': 'publish'}])
                self.assertEqual(kwargs['headers'], {
                    'x-api-key': 'trusted-publisher',
                    'content-type': 'application/json',
                    })

    @mock.patch('cnxauthoring.utils.get_current_registry')
    def test_notify_role_for_acceptance(self, mock_registry):
        from ..models import create_content

        document = create_content(title='My Document')
        mock_accounts = mock.Mock()
        mock_registry().getUtility.return_value = mock_accounts
        mock_registry().settings = {'webview.url': 'http://cnx.org/'}

        utils.notify_role_for_acceptance('user2', 'user1', document)
        self.assertEqual(mock_accounts.send_message.call_count, 1)
        (user_id, subject, body), _ = mock_accounts.send_message.call_args
        self.assertEqual(user_id, 'user2')
        self.assertEqual(subject, 'Requesting action on OpenStax CNX content')
        self.assertEqual(body, '''\
Hello user2,

user1 added you to content titled My Document.
Please go to the following link to accept your roles and license:
http://cnx.org/users/role-acceptance/{}

Thank you from your friends at OpenStax CNX
'''.format(document.id))

    @mock.patch('cnxauthoring.utils.get_current_request')
    def test_accept_roles(self, mock_request):
        cstruct = {
            u'submitlog': u'first version',
            u'abstract': None,
            u'revised': None,
            u'derived_from_title': u'Madlavning',
            u'parent_title': None,
            u'keywords': [u'k\xf8kken',
                          u'Madlavning'],
            u'subjects': [u'Arts'],
            u'title': u'Copy of Madlavning',
            u'parent_version': u'',
            u'editors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'id': 'user2'},
                ],
            u'id': u'feda4909-5bbd-431e-a017-049aff54416d',
            u'parent_id': None,
            u'version': u'1.1',
            u'legacy_id': u'col11368',
            u'media_type': u'application/vnd.org.cnx.collection',
            u'publishers': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'id': 'user1'}],
            u'parent_authors': [],
            u'stateid': 1,
            u'google_analytics': None,
            u'language': u'da',
            u'maintainers': [],
            u'buy_link': None,
            u'authors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'id': 'user2'},
                ],
            u'legacy_version': u'1.1',
            u'licensors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'id': 'user1'}],
            u'roles': None,
            u'license': {
                'url': 'http://creativecommons.org/licenses/by/4.0/'
                },
            u'created': None,
            u'tree': {
                u'id': u'feda4909-5bbd-431e-a017-049aff54416d@1.1',
                u'contents': [],
                u'title': u'Madlavning'},
            u'doctype': u'',
            u'illustrators': [],
            u'translators': [],
            u'submitter': {
                'fullname': u'User One',
                'surname': u'One',
                'firstname': u'User',
                'id': 'user1'},
            u'derived_from_uri': 'http://cnx.org/contents/'
                                 'feda4909-5bbd-431e-a017-049aff54416d@1.1',
            }
        now = datetime.datetime.now(utils.TZINFO)
        formatted_now = now.astimezone(utils.TZINFO).isoformat()
        with mock.patch('datetime.datetime') as mock_datetime:
            mock_request().authenticated_userid = 'user1'
            mock_datetime.now.return_value = now
            utils.accept_roles(cstruct, {
                'fullname': u'User One',
                'surname': u'One',
                'firstname': u'User',
                'has_accepted': True,
                'id': 'user1'})
        self.maxDiff = None
        self.assertDictEqual(
            cstruct, {
                u'submitlog': u'first version',
                u'abstract': None,
                u'revised': None,
                u'derived_from_title': u'Madlavning',
                u'parent_title': None,
                u'keywords': [u'k\xf8kken',
                              u'Madlavning'],
                u'subjects': [u'Arts'],
                u'title': u'Copy of Madlavning',
                u'parent_version': u'',
                u'editors': [
                    {'fullname': u'User One',
                     'surname': u'One',
                     'firstname': u'User',
                     'has_accepted': True,
                     'assignment_date': formatted_now,
                     'requester': 'user1',
                     'id': 'user1'},
                    {'fullname': 'User Two',
                     'surname': u'Two',
                     'firstname': u'User',
                     'id': 'user2'},
                    ],
                u'id': u'feda4909-5bbd-431e-a017-049aff54416d',
                u'parent_id': None,
                u'version': u'1.1',
                u'legacy_id': u'col11368',
                u'media_type': u'application/vnd.org.cnx.collection',
                u'publishers': [
                    {'fullname': u'User One',
                     'surname': u'One',
                     'firstname': u'User',
                     'has_accepted': True,
                     'assignment_date': formatted_now,
                     'requester': 'user1',
                     'id': 'user1'}],
                u'parent_authors': [],
                u'stateid': 1,
                u'google_analytics': None,
                u'language': u'da',
                u'maintainers': [],
                u'buy_link': None,
                u'authors': [
                    {'fullname': u'User One',
                     'surname': u'One',
                     'firstname': u'User',
                     'has_accepted': True,
                     'assignment_date': formatted_now,
                     'requester': 'user1',
                     'id': 'user1'},
                    {'fullname': 'User Two',
                     'surname': u'Two',
                     'firstname': u'User',
                     'id': 'user2'},
                    ],
                u'legacy_version': u'1.1',
                u'licensors': [
                    {'fullname': u'User One',
                     'surname': u'One',
                     'has_accepted': True,
                     'assignment_date': formatted_now,
                     'requester': 'user1',
                     'firstname': u'User',
                     'id': 'user1'}],
                u'roles': None,
                u'license': {
                    'url': 'http://creativecommons.org/licenses/by/4.0/'
                    },
                u'created': None,
                u'tree': {
                    u'id': u'feda4909-5bbd-431e-a017-049aff54416d@1.1',
                    u'contents': [],
                    u'title': u'Madlavning'},
                u'doctype': u'',
                u'illustrators': [],
                u'translators': [],
                u'submitter': {
                    'fullname': u'User One',
                    'surname': u'One',
                    'firstname': u'User',
                    'id': 'user1'},
                u'derived_from_uri': ('http://cnx.org/contents/feda4909-5bbd'
                                      '-431e-a017-049aff54416d@1.1'),
                })

    @mock.patch('cnxauthoring.utils.get_current_request')
    def test_accept_roles_w_reject(self, mock_request):
        now = datetime.datetime.now(utils.TZINFO)
        formatted_now = now.astimezone(utils.TZINFO).isoformat()
        cstruct = {
            u'authors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'has_accepted': False,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user2'},
                ],
            u'licensors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'firstname': u'User',
                 'id': 'user1'},
                ],
            }
        with mock.patch('datetime.datetime') as mock_datetime:
            mock_request().authenticated_userid = 'user1'
            mock_datetime.now.return_value = now
            utils.accept_roles(cstruct, {'id': 'user1'})
        self.assertEqual(cstruct, {
            u'authors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'has_accepted': False,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user2'},
                ],
            u'licensors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'firstname': u'User',
                 'id': 'user1'},
                ],
            })

    @mock.patch('cnxauthoring.utils.get_current_request')
    def test_accept_roles_w_self_assignment(self, mock_request):
        now = datetime.datetime.now(utils.TZINFO)
        formatted_now = now.astimezone(utils.TZINFO).isoformat()
        # authenticated user is 'user1'
        cstruct = {
            u'authors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user2'},
                ],
            u'licensors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'firstname': u'User',
                 'id': 'user1'},
                ],
            }
        with mock.patch('datetime.datetime') as mock_datetime:
            mock_request().authenticated_userid = 'user1'
            mock_datetime.now.return_value = now
            utils.accept_roles(cstruct, {'id': 'user1'})
        self.assertEqual(cstruct, {
            u'authors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'firstname': u'User',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user1',
                 'id': 'user1'},
                {'fullname': 'User Two',
                 'surname': u'Two',
                 'firstname': u'User',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'id': 'user2'},
                ],
            u'licensors': [
                {'fullname': u'User One',
                 'surname': u'One',
                 'has_accepted': True,
                 'assignment_date': formatted_now,
                 'requester': 'user2',
                 'firstname': u'User',
                 'id': 'user1'},
                ],
            })

    def test_accept_license(self):
        from ..models import create_content

        document = create_content(
            title='My Document',
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            )
        utils.accept_license(document, {'id': 'me'})
        self.assertEqual(document.licensor_acceptance,
                         [{'id': 'me', 'has_accepted': True}])

    @mock.patch('cnxauthoring.utils.get_current_request')
    @mock.patch('cnxauthoring.utils.notify_role_for_acceptance')
    def test_declare_roles(self, mock_notify, mock_request):
        from ..models import create_content

        document = create_content(
            title='My Document',
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            )
        settings = {
            'publishing.url': 'http://publishing/',
            'publishing.api_key': 'trusted-publisher',
            }

        with mock.patch('requests.get') as get:
            publishing_records = []
            get.return_value.status_code = 200
            get.json.side_effect = publishing_records
            with mock.patch('requests.post') as post:
                post.return_value.status_code = 202

                with testing.testConfig(settings=settings):
                    mock_request().authenticated_userid = 'user1'
                    utils.declare_roles(document)

                self.assertEqual(post.call_count, 1)

                (url,), kwargs = post.call_args_list[0]
                self.assertEqual(
                    url,
                    'http://publishing/contents/{}/roles'.format(document.id))
                self.assertEqual(
                    sorted(json.loads(kwargs['data']),
                           key=lambda v: (v['uid'], v['role'],)),
                    [{u'uid': u'me', u'role': u'Author',
                      u'has_accepted': None},
                     {u'uid': u'me', u'role': u'Editor',
                      u'has_accepted': None},
                     {u'uid': u'me', u'role': u'Publisher',
                      u'has_accepted': None},
                     {u'uid': u'you', u'role': u'Editor',
                      u'has_accepted': None},
                     {u'uid': u'you', u'role': u'Translator',
                      u'has_accepted': None},
                     ])
                self.assertEqual(kwargs['headers'], {
                    'x-api-key': 'trusted-publisher',
                    'content-type': 'application/json',
                    })

    @mock.patch('cnxauthoring.utils.get_current_request')
    @mock.patch('cnxauthoring.utils.notify_role_for_acceptance')
    def test_declare_roles_raises_exception(self, mock_notify, mock_request):
        from ..models import create_content

        document = create_content(
            title='My Document',
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            )
        settings = {
            'publishing.url': 'http://publishing/',
            'publishing.api_key': 'trusted-publisher',
            }

        from ..models import PublishingError

        with testing.testConfig(settings=settings), \
                mock.patch('requests.get') as get, \
                mock.patch('requests.post') as post, \
                mock.patch('requests.delete') as delete:
            mock_request().authenticated_userid = 'user1'

            get.return_value.status_code = 500
            # The initial GET should fail.
            with self.assertRaises(PublishingError):
                utils.declare_roles(document)
            get.return_value.status_code = 200
            get.return_value.json.return_value = [
                {'uid': 'you', 'role': 'Author', 'has_accepted': False}]
            delete.return_value.status_code = 500
            # Attempt to DELETE should fail.
            with self.assertRaises(PublishingError):
                utils.declare_roles(document)
            delete.return_value.status_code = 200
            # Lastly, the POST of roles should fail.
            with self.assertRaises(PublishingError):
                utils.declare_roles(document)

    @httpretty.activate
    @mock.patch('cnxauthoring.utils.get_current_request')
    @mock.patch('cnxauthoring.utils.notify_role_for_acceptance')
    def test_declare_roles_removal(self, mock_notify, mock_request):
        # Tests removal of roles removes the role from publishing as well.
        from ..models import create_content

        document = create_content(
            title='My Document',
            authors=[{'id': 'me'}],
            editors=[{'id': 'me'}],
            )
        uuid = document.id
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }
        records = [
            ('Author', 'me', uuid, True),
            ('Author', 'you', uuid, True),  # should remain
            ('Editor', 'me', uuid, True),
            ('Editor', 'you', uuid, None),  # should be removed
            ('Translator', 'me', uuid, False),  # should be removed
            ]
        record_keys = ('role', 'uid', 'uuid', 'has_accepted',)
        get_response_body = [dict(zip(record_keys, r)) for r in records]

        url = urlparse.urljoin(publishing_url,
                               '/contents/{}/roles'.format(document.id))
        httpretty.register_uri(httpretty.GET, url,
                               body=json.dumps(get_response_body), status=200)
        httpretty.register_uri(httpretty.POST, url, status=202)
        captured_delete = CaptureRequest()
        httpretty.register_uri(httpretty.DELETE, url, body=captured_delete, status=200)

        with testing.testConfig(settings=settings):
            mock_request().authenticated_userid = 'me'
            utils.declare_roles(document)

        # Check that the correct data was sent.
        self.assertEqual(
            json.loads(captured_delete.body),
            [dict(zip(record_keys[:2], e[:2])) for e in records[3:]])
        # Check if it was called with the api key.
        self.assertEqual(
            captured_delete.request.headers['X-API-Key'],
            'trusted-publisher')

        # Check the document's roles remained intact
        self.assertEqual(len(document.metadata['authors']), 1)
        self.assertEqual(document.metadata['authors'][-1]['id'], 'me')
        self.assertEqual(len(document.metadata['editors']), 1)
        self.assertEqual(document.metadata['editors'][-1]['id'], 'me')
        self.assertEqual(len(document.metadata.get('translators', [])), 0)

    @httpretty.activate
    @mock.patch('cnxauthoring.utils.get_current_request')
    @mock.patch('cnxauthoring.utils.notify_role_for_acceptance')
    def test_declare_roles_w_invalid_role_type(self, mock_notify, mock_request):
        """Ignore invalid roles"""
        from ..models import create_content

        document = create_content(
            title='My Document',
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            )
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }

        publishing_records = []
        url = urlparse.urljoin(publishing_url,
                               '/contents/{}/roles'.format(document.id))
        httpretty.register_uri(httpretty.GET, url,
                               body=json.dumps(publishing_records), status=200)
        httpretty.register_uri(httpretty.POST, url, status=202)

        with testing.testConfig(settings=settings):
            mock_request().authenticated_userid = 'user1'
            utils.declare_roles(document)

        post_request = httpretty.last_request()
        data = post_request.parse_request_body(post_request.body)
        expected = [
            {u'uid': u'me', u'role': u'Author', u'has_accepted': None},
            {u'uid': u'me', u'role': u'Editor', u'has_accepted': None},
            {u'uid': u'me', u'role': u'Publisher', u'has_accepted': None},
            {u'uid': u'you', u'role': u'Editor', u'has_accepted': None},
            {u'uid': u'you', u'role': u'Translator', u'has_accepted': None},
            ]
        self.assertEqual(sorted(data, key=lambda v: (v['uid'], v['role'],)),
                         expected)

    @httpretty.activate
    @mock.patch('cnxauthoring.utils.get_current_request')
    @mock.patch('cnxauthoring.utils.notify_role_for_acceptance')
    def test_declare_roles_on_revision(self, mock_notify, mock_request):
        from ..models import create_content

        id = '916849b5-d71f-40e3-aaf8-7da2aa82508e'
        document = create_content(
            id=id,
            title='My Document',
            authors=[{'id': 'smoo'}, {'id': 'fred'}],
            )
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }

        url = urlparse.urljoin(publishing_url,
                               '/contents/{}/roles'.format(document.id))
        get_response = [
            {'uid': 'smoo', 'role': 'Author',
             'has_accepted': True, 'uuid': id},
            {'uid': 'fred', 'role': 'Author',
             'has_accepted': True, 'uuid': id},
            ]
        httpretty.register_uri(httpretty.GET, url,
                               body=json.dumps(get_response), status=200)
        httpretty.register_uri(httpretty.POST, url, status=202)

        mock_request().authenticated_userid = 'smoo'
        now = datetime.datetime.now()
        formatted_now = now.isoformat()
        with mock.patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = now
            with testing.testConfig(settings=settings):
                utils.declare_roles(document)

        # Check the roles for acceptance.
        expected = [
            {'assignment_date': formatted_now,
             'has_accepted': True,
             u'id': u'smoo',
             'requester': 'smoo'},
            {'assignment_date': formatted_now,
             'has_accepted': True,
             u'id': u'fred',
             'requester': 'smoo'}]
        self.assertTrue(document.metadata['authors'], expected)

        # Now change the has_accepted on one role to verify the syncing
        #   only happens during role addtion.
        document.metadata['authors'][1]['has_accepted'] = False
        document.metadata['authors'].append({'id': 'ren'})
        with mock.patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = now
            with testing.testConfig(settings=settings):
                utils.declare_roles(document)
        expected[1]['has_accepted'] = False
        expected.append(
            {'assignment_date': formatted_now,
             'has_accepted': None,
             'id': 'ren',
             'requester': 'smoo'})
        self.assertEqual(document.metadata['authors'], expected)

    @httpretty.activate
    def test_declare_licensors(self):
        from ..models import create_content, DEFAULT_LICENSE

        document = create_content(
            title='My Document',
            license={'url': DEFAULT_LICENSE.url},
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            licensor_acceptance=[{'id': 'me', 'has_accepted': True},
                                 {'id': 'you', 'has_accepted': None}],
            )
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }

        publishing_records = {
            'license_url': DEFAULT_LICENSE.url,
            'licensors': [],
            }
        url = urlparse.urljoin(publishing_url,
                               '/contents/{}/licensors'.format(document.id))
        httpretty.register_uri(httpretty.GET, url,
                               body=json.dumps(publishing_records), status=200)
        httpretty.register_uri(httpretty.POST, url, status=202)

        with testing.testConfig(settings=settings):
            utils.declare_licensors(document)

        post_request = httpretty.last_request()
        data = post_request.parse_request_body(post_request.body)
        expected_licensors = [
            {u'uid': u'me', u'has_accepted': True},
            {u'uid': u'you', u'has_accepted': None},
            ]
        self.assertEqual(data['license_url'], DEFAULT_LICENSE.url)
        self.assertEqual(sorted(data['licensors'], key=lambda v: v['uid']),
                         expected_licensors)

    def test_declare_licensors_raises_exception(self):
        from ..models import create_content, DEFAULT_LICENSE

        document = create_content(
            title='My Document',
            license={'url': DEFAULT_LICENSE.url},
            authors=[{'id': 'me'}],
            publishers=[{'id': 'me'}],
            editors=[{'id': 'me'}, {'id': 'you'}],
            translators=[{'id': 'you'}],
            licensor_acceptance=[{'id': 'me', 'has_accepted': True},
                                 {'id': 'you', 'has_accepted': None}],
            )
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }

        publishing_records = {
            'license_url': DEFAULT_LICENSE.url,
            'licensors': [{'uid': 'typo', 'has_accepted': False}],
            }

        from ..models import PublishingError

        with testing.testConfig(settings=settings), \
                mock.patch('requests.get') as get, \
                mock.patch('requests.post') as post, \
                mock.patch('requests.delete') as delete:
            get.return_value.status_code = 500
            post.return_value.status_code = 202
            # No exception raised on a bad GET
            utils.declare_licensors(document)
            get.return_value.status_code = 200
            get.return_value.json.return_value = publishing_records
            delete.return_value.status_code = 500
            # Check DELETE fails
            with self.assertRaises(PublishingError):
                utils.declare_licensors(document)
            delete.return_value.status_code = 200
            post.return_value.status_code = 500
            # Check POST fails
            with self.assertRaises(PublishingError):
                utils.declare_licensors(document)

    @httpretty.activate
    def test_declare_licensors_removal(self):
        from ..models import create_content, DEFAULT_LICENSE

        tracted_acceptance = {'id': 'me', 'has_accepted': None}
        document = create_content(
            title='My Document',
            license={'url': DEFAULT_LICENSE.url},
            authors=[{'id': 'me'}],
            licensor_acceptance=[tracted_acceptance,
                                 {'id': 'user2', 'has_accepted': True}],
            )
        uuid = document.id
        publishing_url = 'http://publishing/'
        settings = {
            'publishing.url': publishing_url,
            'publishing.api_key': 'trusted-publisher',
            }

        records = [
            ('me', None, uuid,),
            ('user2', True, uuid,),  # should remain
            ('you', None, uuid,),  # should be removed
            ('user1', False, uuid,),  # should be removed
            ]
        record_keys = ('uid', 'has_accepted', 'uuid',)
        get_response_body = {
            'license_url': DEFAULT_LICENSE.url,
            'licensors': [dict(zip(record_keys, e)) for e in records],
            }
        url = urlparse.urljoin(publishing_url,
                               '/contents/{}/licensors'.format(document.id))
        httpretty.register_uri(httpretty.GET, url,
                               body=json.dumps(get_response_body), status=200)
        httpretty.register_uri(httpretty.POST, url, status=202)
        captured_delete = CaptureRequest()
        httpretty.register_uri(httpretty.DELETE, url, body=captured_delete)

        with testing.testConfig(settings=settings):
            utils.declare_licensors(document)

        expected = {'licensors': [{'uid': e[0]} for e in records[2:]]}
        self.assertEqual(
            json.loads(captured_delete.body),
            expected)

        # Check the document's acceptor list remains intact
        self.assertEqual(document.licensor_acceptance, [tracted_acceptance])

    def test_validate_for_publish_on_document(self):
        from ..models import create_content, DEFAULT_LICENSE

        def make_doc():
            document = create_content(
                title='My Document',
                license={'url': DEFAULT_LICENSE.url},
                authors=[{'id': 'me', 'has_accepted': True}],
                publishers=[{'id': 'me', 'has_accepted': True}],
                editors=[{'id': 'me', 'has_accepted': True},
                         {'id': 'you', 'has_accepted': True}],
                translators=[{'id': 'you', 'has_accepted': True}],
                licensor_acceptance=[{'id': 'me', 'has_accepted': True},
                                     {'id': 'you', 'has_accepted': True}],
                content="<p>Hello world!</p>",
                )
            return document

        self.assertEqual(utils.validate_for_publish(make_doc()), None)

        # False when missing content
        doc = make_doc()
        doc.content = ""
        self.assertEqual(utils.validate_for_publish(doc),
                         [utils.VALIDATION_NO_CONTENT])

        # False when not all roles have accepted.
        doc = make_doc()
        doc.metadata['authors'][0]['has_accepted'] = False
        self.assertEqual(utils.validate_for_publish(doc),
                         [utils.VALIDATION_ROLES_REJECTED])

        # False when not all roles have accepted the license.
        doc = make_doc()
        doc.licensor_acceptance[1]['has_accepted'] = None
        self.assertEqual(utils.validate_for_publish(doc),
                         [utils.VALIDATION_ROLES_PENDING])

    def test_validate_for_publish_on_binder(self):
        from ..models import create_content, DEFAULT_LICENSE, BINDER_MEDIATYPE

        def make_doc():
            document = create_content(
                title='My Document',
                license={'url': DEFAULT_LICENSE.url},
                submitter={'id': 'me'},
                authors=[{'id': 'me', 'has_accepted': True}],
                publishers=[{'id': 'me', 'has_accepted': True}],
                editors=[{'id': 'me', 'has_accepted': True},
                         {'id': 'you', 'has_accepted': True}],
                translators=[{'id': 'you', 'has_accepted': True}],
                licensor_acceptance=[{'id': 'me', 'has_accepted': True},
                                     {'id': 'you', 'has_accepted': True}],
                content="<p>Hello world!</p>",
                )
            return document

        def make_binder(docs=[]):
            contents = [{'id': '{}@draft'.format(doc.id)} for doc in docs]
            binder = create_content(
                media_type=BINDER_MEDIATYPE,
                tree={'contents': contents},
                title='My Binder',
                license={'url': DEFAULT_LICENSE.url},
                authors=[{'id': 'me', 'has_accepted': True}],
                publishers=[{'id': 'me', 'has_accepted': True}],
                editors=[{'id': 'me', 'has_accepted': True},
                         {'id': 'you', 'has_accepted': True}],
                translators=[{'id': 'you', 'has_accepted': True}],
                licensor_acceptance=[{'id': 'me', 'has_accepted': True},
                                     {'id': 'you', 'has_accepted': True}],
                )
            return binder

        from ..storage.database import CONNECTION_SETTINGS_KEY, initdb
        from ..storage.postgresql import PostgresqlStorage
        settings = integration_test_settings()
        test_db = settings[CONNECTION_SETTINGS_KEY]
        initdb({CONNECTION_SETTINGS_KEY: test_db}, clear=True)
        self.storage = PostgresqlStorage(db_connection_string=test_db)

        def persist_and_disconnect():
            self.storage.persist()
            self.storage.conn.close()
        self.addCleanup(persist_and_disconnect)

        from .. import storage
        setattr(storage, 'storage', self.storage)

        from ..storage import storage

        def persist(models):
            for model in models:
                storage.add(model)
            storage.persist()

        docs = (make_doc(), make_doc(),)
        persist(docs)
        self.assertEqual(utils.validate_for_publish(make_binder(docs)), None)

        # Missing content
        binder = make_binder()
        self.assertEqual(utils.validate_for_publish(binder),
                         [utils.VALIDATION_NO_CONTENT])

        # Not all roles have accepted
        docs = (make_doc(), make_doc(),)
        persist(docs)
        binder = make_binder(docs)
        binder.metadata['authors'][0]['has_accepted'] = False
        binder.metadata['editors'][0]['has_accepted'] = None
        self.assertEqual(utils.validate_for_publish(binder),
                         [utils.VALIDATION_ROLES_PENDING,
                          utils.VALIDATION_ROLES_REJECTED])

        # Not all roles have accepted on contained
        docs = (make_doc(), make_doc(),)
        persist(docs)
        binder = make_binder(docs)
        binder.metadata['authors'][0]['has_accepted'] = False
        self.assertEqual(utils.validate_for_publish(binder),
                         [utils.VALIDATION_ROLES_REJECTED])

        # Not all roles have accepted the license
        docs = (make_doc(), make_doc(),)
        persist(docs)
        binder = make_binder(docs)
        binder.licensor_acceptance[0]['has_accepted'] = None
        self.assertEqual(utils.validate_for_publish(binder),
                         [utils.VALIDATION_ROLES_PENDING])

    def test_validate_for_publish_on_obj(self):
        with self.assertRaises(ValueError):
            utils.validate_for_publish(object())


class ArchiveCommunicationsTestCase(unittest.TestCase):

    @httpretty.activate
    def test_content(self):
        content_id = 'uuid'
        archive_url = 'http://example.com'
        url = "{}/contents/{}.json".format(archive_url, content_id)
        response_data = {'id': content_id}
        faux_response_body = json.dumps(response_data)
        httpretty.register_uri(httpretty.GET, url,
                               body=faux_response_body, status=200)

        request = testing.DummyRequest()
        request.registry = mock.Mock()
        request.registry.settings = {'archive.url': archive_url}

        from ..utils import fetch_archive_content
        document_as_dict = fetch_archive_content(request, content_id)
        self.assertEqual(document_as_dict, response_data)

    @httpretty.activate
    def test_extras(self):
        content_id = 'uuid'
        archive_url = 'http://example.com'
        url = "{}/extras/{}".format(archive_url, content_id)
        response_data = {'extraInfo': content_id}
        faux_response_body = json.dumps(response_data)
        httpretty.register_uri(httpretty.GET, url,
                               body=faux_response_body, status=200)

        request = testing.DummyRequest()
        request.registry = mock.Mock()
        request.registry.settings = {'archive.url': archive_url}

        from ..utils import fetch_archive_content
        extras = fetch_archive_content(request, content_id, extras=True)
        self.assertEqual(extras, {'extra_info': content_id})

    @httpretty.activate
    def test_not_found(self):
        content_id = 'uuid'
        archive_url = 'http://example.com'
        url = "{}/contents/{}.json".format(archive_url, content_id)
        response_data = {'id': content_id}
        faux_response_body = json.dumps(response_data)
        httpretty.register_uri(httpretty.GET, url, status=404)

        request = testing.DummyRequest()
        request.registry = mock.Mock()
        request.registry.settings = {'archive.url': archive_url}

        from ..utils import fetch_archive_content
        from ..models import DocumentNotFoundError
        self.assertRaises(DocumentNotFoundError, fetch_archive_content,
                          request, content_id)

    @httpretty.activate
    def test_not_json(self):
        content_id = 'uuid'
        archive_url = 'http://example.com'
        url = "{}/contents/{}.json".format(archive_url, content_id)
        response_data = "<p>not json</p>"
        httpretty.register_uri(httpretty.GET, url, body=response_data, status=200)

        request = testing.DummyRequest()
        request.registry = mock.Mock()
        request.registry.settings = {'archive.url': archive_url}

        from ..utils import fetch_archive_content
        from ..models import DocumentNotFoundError
        self.assertRaises(DocumentNotFoundError, fetch_archive_content,
                          request, content_id)

    def test_connection_error(self):
        content_id = 'uuid'
        archive_url = 'http://example.com'
        request = testing.DummyRequest()
        request.registry = mock.Mock()
        request.registry.settings = {'archive.url': archive_url}

        from ..utils import fetch_archive_content
        from ..models import ArchiveConnectionError
        from requests.exceptions import ConnectionError
        with mock.patch('requests.get', side_effect=ConnectionError()) as get:
            self.assertRaises(ArchiveConnectionError, fetch_archive_content,
                              request, content_id)
