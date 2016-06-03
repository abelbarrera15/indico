# This file is part of Indico.
# Copyright (C) 2002 - 2016 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from flask import flash, redirect, session, request
from werkzeug.exceptions import Forbidden, BadRequest

from indico.core.db import db
from indico.modules.api import APIMode
from indico.modules.api import settings as api_settings
from indico.modules.api.forms import AdminSettingsForm
from indico.modules.api.models.keys import APIKey
from indico.modules.api.views import WPAPIAdmin, WPAPIUserProfile
from indico.modules.users.controllers import RHUserBase
from indico.util.i18n import _
from indico.web.flask.util import url_for, redirect_or_jsonify
from indico.web.forms.base import FormDefaults

from MaKaC.webinterface.rh.admins import RHAdminBase


class RHAPIAdminSettings(RHAdminBase):
    """API settings (admin)"""

    def _process(self):
        form = AdminSettingsForm(obj=FormDefaults(**api_settings.get_all()))
        if form.validate_on_submit():
            api_settings.set_multi(form.data)
            flash(_('Settings saved'), 'success')
            return redirect(url_for('.admin_settings'))
        count = APIKey.find(is_active=True).count()
        return WPAPIAdmin.render_template('admin_settings.html', form=form, count=count)


class RHAPIAdminKeys(RHAdminBase):
    """API key list (admin)"""

    def _process(self):
        keys = sorted(APIKey.find_all(is_active=True), key=lambda ak: (ak.use_count == 0, ak.user.full_name))
        return WPAPIAdmin.render_template('admin_keys.html', keys=keys)


class RHAPIUserProfile(RHUserBase):
    """API key details (user)"""

    def _process(self):
        key = self.user.api_key
        use_signatures = api_settings.get('security_mode') in {APIMode.SIGNED, APIMode.ONLYKEY_SIGNED,
                                                               APIMode.ALL_SIGNED}
        allow_persistent = api_settings.get('allow_persistent')
        old_keys = self.user.old_api_keys
        return WPAPIUserProfile.render_template('user_profile.html', user=self.user, key=key, old_keys=old_keys,
                                                use_signatures=use_signatures, allow_persistent=allow_persistent,
                                                can_modify=(not key or not key.is_blocked or session.user.is_admin))


class RHAPICreateKey(RHUserBase):
    """API key creation"""

    CSRF_ENABLED = True

    def _process(self):
        quiet = request.form.get('quiet') == '1'
        force = request.form.get('force') == '1'
        persistent = request.form.get('persistent') == '1' and api_settings.get('allow_persistent')
        old_key = self.user.api_key
        if old_key:
            if not force:
                raise BadRequest('There is already an API key for this user')
            if old_key.is_blocked and not session.user.is_admin:
                raise Forbidden
            old_key.is_active = False
            db.session.flush()
        key = APIKey(user=self.user)
        db.session.add(key)
        if persistent:
            key.is_persistent_allowed = persistent
        elif old_key:
            key.is_persistent_allowed = old_key.is_persistent_allowed
        if not quiet:
            if old_key:
                flash(_('Your API key has been successfully replaced.'), 'success')
                if old_key.use_count:
                    flash(_('Please update any applications which use old key.'), 'warning')
            else:
                flash(_('Your API key has been successfully created.'), 'success')
        db.session.flush()
        return redirect_or_jsonify(url_for('api.user_profile'), flash=not quiet,
                                   is_persistent_allowed=key.is_persistent_allowed)


class RHAPIDeleteKey(RHUserBase):
    """API key deletion"""

    CSRF_ENABLED = True

    def _process(self):
        key = self.user.api_key
        key.is_active = False
        flash(_('Your API key has been deleted.'), 'success')
        return redirect(url_for('api.user_profile'))


class RHAPITogglePersistent(RHUserBase):
    """API key - persistent signatures on/off"""

    CSRF_ENABLED = True

    def _process(self):
        quiet = request.form.get('quiet') == '1'
        key = self.user.api_key
        key.is_persistent_allowed = api_settings.get('allow_persistent') and request.form['enabled'] == '1'
        if not quiet:
            if key.is_persistent_allowed:
                flash(_('You can now use persistent signatures.'), 'success')
            else:
                flash(_('Persistent signatures have been disabled for your API key.'), 'success')
        return redirect_or_jsonify(url_for('api.user_profile'), flash=not quiet, enabled=key.is_persistent_allowed)


class RHAPIBlockKey(RHUserBase):
    """API key blocking/unblocking"""

    CSRF_ENABLED = True

    def _checkProtection(self):
        RHUserBase._checkProtection(self)
        if self._doProcess and not session.user.is_admin:
            raise Forbidden

    def _process(self):
        key = self.user.api_key
        key.is_blocked = not key.is_blocked
        if key.is_blocked:
            flash(_('The API key has been blocked.'), 'success')
        else:
            flash(_('The API key has been unblocked.'), 'success')
        return redirect(url_for('api.user_profile'))