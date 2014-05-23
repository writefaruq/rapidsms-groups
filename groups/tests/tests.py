#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError

from rapidsms.models import Contact
from rapidsms.tests.harness import MockRouter
from rapidsms.messages.incoming import IncomingMessage

from groups import forms as group_forms
from groups.models import GroupContact
from groups.app import GroupsApp
from groups.tests.base import CreateDataTest, patch_settings
from groups.validators import validate_phone
from groups.utils import normalize_number


class GroupCreateDataTest(CreateDataTest):

    def create_group_contact(self, data={}):
        """ Override super's create_contact to include extension fields """
        defaults = self._data()
        defaults.update(data)
        return GroupContact.objects.create(**defaults)

    def _data(self, initial_data={}, instance=None):
        """ Helper function to generate form-like POST data """
        if instance:
            data = model_to_dict(instance)
        else:
            data = {
                'contact': Contact.objects.create(),
                'first_name': self.random_string(8),
                'last_name': self.random_string(8),
                'email': 'test@abc.com',
                'phone': '31112223333',
            }
        data.update(initial_data)
        return data


class GroupFormTest(GroupCreateDataTest):

    def test_create_contact(self):
        """ Test contact creation functionality with form """
        group1 = self.create_group()
        group2 = self.create_group()
        data = self._data({'groups': [group1.pk]})
        data['contact'] = data['contact'].pk
        form = group_forms.GroupContactForm(data)
        self.assertTrue(form.is_valid())
        contact = form.save()
        self.assertEqual(contact.first_name, data['first_name'])
        self.assertEqual(contact.groups.count(), 1)
        self.assertTrue(contact.groups.filter(pk=group1.pk).exists())
        self.assertFalse(contact.groups.filter(pk=group2.pk).exists())

    def test_edit_contact(self):
        """ Test contact edit functionality with form """
        group1 = self.create_group()
        group2 = self.create_group()
        group_contact = self.create_group_contact()
        group_contact.groups.add(group1)
        data = self._data({'groups': [group2.pk]}, instance=group_contact)
        form = group_forms.GroupContactForm(data, instance=group_contact)
        self.assertTrue(form.is_valid(), dict(form.errors))
        group_contact = form.save()
        self.assertEqual(group_contact.groups.count(), 1)
        self.assertFalse(group_contact.groups.filter(pk=group1.pk).exists())
        self.assertTrue(group_contact.groups.filter(pk=group2.pk).exists())


class GroupViewTest(CreateDataTest):

    def setUp(self):
        self.user = User.objects.create_user('test', 'a@b.com', 'abc')
        self.client.login(username='test', password='abc')

    def test_editable_views(self):
        group = self.create_group({'is_editable': False})
        edit_url = reverse('edit-group', args=[group.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 403)
        delete_url = reverse('delete-group', args=[group.pk])
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 403)


class PhoneTest(GroupCreateDataTest):

    def setUp(self):
        self.backend = self.create_backend(data={'name': 'test-backend'})
        self.router = MockRouter()
        self.app = GroupsApp(router=self.router)

    def test_valid_phone(self):
        valid_numbers = ('12223334444', '112223334444', '1112223334444')
        for number in valid_numbers:
            self.assertEqual(None, validate_phone(number))

    def test_invalid_phone(self):
        invalid_numbers = ('2223334444', '11112223334444')
        for number in invalid_numbers:
            self.assertRaises(ValidationError, validate_phone, number)

    def _send(self, conn, text):
        msg = IncomingMessage(conn, text)
        self.app.filter(msg)
        return msg

    def test_normalize_number(self):
        """
        All numbers should be stripped of non-numeric characters and, if
        defined, should be prepended with the COUNTRY_CODE
        """
        normalized = '12223334444'
        number = '1-222-333-4444'
        self.assertEqual(normalize_number(number), normalized)
        number = '1 (222) 333-4444'
        self.assertEqual(normalize_number(number), normalized)
        with patch_settings(COUNTRY_CODE='66'):
            normalized = '662223334444'
            number = '22-23334444'
            self.assertEqual(normalize_number(number), normalized)
        with patch_settings(COUNTRY_CODE=None):
            normalized = '2223334444'
            number = '22-23334444'
            self.assertEqual(normalize_number(number), normalized)

    def test_contact_association(self):
        number = '1112223334444'
        group_contact = self.create_group_contact({'phone': number})
        other_contact = self.create_group_contact()
        connection = self.create_connection({'backend': self.backend,
                                             'identity': '+111-222-333-4444'})
        msg = self._send(connection, 'test')
        # XXX for some reason msg.connections is an instance rather than a list, not sure why
        self.assertEqual(msg.connections.contact_id, group_contact.contact.id)
        self.assertNotEqual(msg.connections.contact_id, other_contact.contact.id)
