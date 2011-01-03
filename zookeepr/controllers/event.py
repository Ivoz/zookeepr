import logging

from pylons import request, response, session, tmpl_context as c
from pylons.controllers.util import redirect_to
from pylons.decorators import validate
from pylons.decorators.rest import dispatch_on

from formencode import validators, htmlfill, ForEach, Invalid
from formencode.variabledecode import NestedVariables

from zookeepr.lib.base import BaseController, render
from zookeepr.lib.ssl_requirement import enforce_ssl
from zookeepr.lib.validators import BaseSchema, ProposalValidator
import zookeepr.lib.helpers as h

from authkit.authorize.pylons_adaptors import authorize
from authkit.permissions import ValidAuthKitUser

from zookeepr.lib.mail import email

from zookeepr.model import meta
from zookeepr.model.event import Event
from zookeepr.model.event_type import EventType, EventTypeValidator
from zookeepr.model.proposal import Proposal

from zookeepr.config.lca_info import lca_info

log = logging.getLogger(__name__)

class EventSchema(BaseSchema):
    type = EventTypeValidator(not_empty=True)
    proposal = ProposalValidator()
    title = validators.String()
    url = validators.String()
    publish = validators.Bool()
    exclusive = validators.Bool()

class NewEventSchema(BaseSchema):
    event = EventSchema()
    pre_validators = [NestedVariables]

class EditEventSchema(BaseSchema):
    event = EventSchema()
    pre_validators = [NestedVariables]

class EventController(BaseController):

    @enforce_ssl(required_all=True)
    @authorize(h.auth.has_organiser_role)
    def __before__(self, **kwargs):
        c.proposals = Proposal.find_all_accepted()
        c.event_types = EventType.find_all()

    @dispatch_on(POST="_new")
    def new(self):
        return render('/event/new.mako')

    @validate(schema=NewEventSchema(), form='new', post_only=True, on_get=True, variable_decode=True)
    def _new(self):
        results = self.form_result['event']

        c.event = Event(**results)
        meta.Session.add(c.event)
        meta.Session.commit()

        h.flash("Event created")
        redirect_to(action='index', id=None)

    def new_proposals(self):
        for proposal in c.proposals:
            if not proposal.event:
                event = Event(type_id=1, proposal=proposal, publish=True, exclusive=False)
                meta.Session.add(event)
        meta.Session.commit()

        h.flash("Events successfully created from Proposals")
        redirect_to(action='index', id=None)

    def index(self):
        c.can_edit = True
        c.event_collection = Event.find_all()
        return render('/event/list.mako')

    @dispatch_on(POST="_edit")
    def edit(self, id):
        c.event = Event.find_by_id(id)

        defaults = h.object_to_defaults(c.event, 'event')
        defaults['event.type'] = c.event.type_id
        defaults['event.proposal'] = c.event.proposal_id

        form = render('/event/edit.mako')
        return htmlfill.render(form, defaults)

    @validate(schema=EditEventSchema(), form='edit', post_only=True, on_get=True, variable_decode=True)
    def _edit(self, id):
        event = Event.find_by_id(id)

        for key in self.form_result['event']:
            setattr(event, key, self.form_result['event'][key])

        # update the objects with the validated form data
        meta.Session.commit()
        h.flash("The Event has been updated successfully.")
        redirect_to(action='index', id=None)

    @dispatch_on(POST="_delete")
    def delete(self, id):
        """Delete the event

        GET will return a form asking for approval.

        POST requests will delete the item.
        """
        c.event = Event.find_by_id(id)
        return render('/event/confirm_delete.mako')

    @validate(schema=None, form='delete', post_only=True, on_get=True, variable_decode=True)
    def _delete(self, id):
        c.event = Event.find_by_id(id)
        meta.Session.delete(c.event)
        meta.Session.commit()

        h.flash("Event has been deleted.")
        redirect_to('index')