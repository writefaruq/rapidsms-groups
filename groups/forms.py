#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8
import logging
import re

from django import forms

from rapidsms.models import Contact

from groups.models import GroupContact, Group
from groups.utils import format_number
from groups.validators import validate_phone


__all__ = ('GroupForm', 'ContactForm', 'ForwardingRuleFormset',)


logger = logging.getLogger('groups.forms')


class FancyPhoneInput(forms.TextInput):

    def render(self, name, value, attrs=None):
        if value:
            value = format_number(value)
        return super(FancyPhoneInput, self).render(name, value, attrs)

    def value_from_datadict(self, data, files, name):
        value = super(FancyPhoneInput, self).value_from_datadict(data, files, name)
        if value:
            value = re.sub(r'\D', '', value)
        return value


class GroupForm(forms.ModelForm):

    class Meta:
        model = Group
        exclude = ('is_editable',)

    def __init__(self, *args, **kwargs):
        super(GroupForm, self).__init__(*args, **kwargs)
        self.fields['group_contacts'].help_text = ''
        qs = Contact.objects.filter().order_by('name')
        self.fields['group_contacts'].queryset = qs
        self.fields['group_contacts'].widget.attrs['class'] = 'horitzonal-multiselect'


class GroupContactForm(forms.ModelForm):
    """ Form for managing contacts """
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.none())
    phone = forms.CharField(validators=[validate_phone], widget=FancyPhoneInput)

    class Meta:
        model = GroupContact
        #exclude = ('language', 'name', 'primary_backend', 'pin')

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        if instance and instance.pk:
            pks = instance.groups.values_list('pk', flat=True)
            kwargs['initial'] = {'groups': list(pks)}
        super(GroupContactForm, self).__init__(*args, **kwargs)
        self.fields['groups'].widget = forms.CheckboxSelectMultiple()
        self.fields['groups'].queryset = Group.objects.order_by('name')
        self.fields['groups'].required = False
        for name in ('first_name', 'last_name', 'phone'):
            self.fields[name].required = True

    def save(self, commit=True):
        instance = super(GroupContactForm, self).save()
        instance.groups = self.cleaned_data['groups']
        return instance
