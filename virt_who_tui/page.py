import sys
import os
import urwid
import logging

from virt_who_tui.display import FormTuiDisplay, PopUpTuiDisplay, YesNoPopUpTuiDisplay

from virtwho.config import InvalidOption
from virtwho.password import UnwritableKeyFile, InvalidKeyFile

class FormBase(object):
    def __init__(self, container, input_data=None):
        self.input_data = input_data
        self.form = FormTuiDisplay(container)
        self.form.title = 'Virt-who TUI'
        self.container = container
        self.previous_page = None
        self.next_page = None
        self.next_button_label = "Next"

    def render(self):
        if self.previous_page:
            self.form.add_button("Back", callback=self.go_back)

        if self.next_page:
            self.form.add_button(self.next_button_label, callback=self.go_next)

        return self.form.render()

    def error_pop_up(self, title, contents):
        dialog = PopUpTuiDisplay(self.container)
        dialog.title = ('error', title)
        dialog.render(contents)

    def yesno_pop_up(self, title, contents, on_yes):
        dialog = YesNoPopUpTuiDisplay(self.container, on_yes=on_yes)
        dialog.title = ('error', title)
        dialog.render(contents)

    def validate(self):
        raise NotImplementedError()

    def go_next(self, button):
        try:
            if self.validate():
                self.render_next_page()
        except InvalidOption as e:
            self.error_pop_up("Failed with following errors:", [str(e)])

    def go_back(self, button):
        self.previous_page.form.set_current()

    def render_next_page(self):
        new_page = self.next_page(self.container, input_data=self.input_data)
        new_page.previous_page = self
        new_page.render()

    def populate_inputs(self, fields):
        for args in fields:
            value = None
            field = args[0] if isinstance(args, list) else args
            if not hasattr(self.form, field):
                continue
            element = getattr(self.form, field)
            if isinstance(element, urwid.CheckBox):
                value = element.state
            elif isinstance(element, list):
                # Elements are radio buttons
                for e in element:
                    if e.state:
                        value = e.label
                        break
            else:
                value = element.get_edit_text()

            setattr(self.input_data, field, value)


class WelcomePage(FormBase):
    def __init__(self, *args, **kwargs):
        super(WelcomePage, self).__init__(*args, **kwargs)
        self.form.title = "Welcome to Virt-who TUI"
        self.form.text = "Virt-who TUI aims to simplify the complexity of settings up virt-who by guiding users step by step.\n\n" + \
            "Please enter a name for your configuration. It can be any name that is meaningful to you, such as 'redhat-rhevm-prod'."
        self.form.add_field("config_name", "text", label="Name")
        self.next_page = SMPage

    def go_next(self, button):
        self.populate_inputs(["config_name"])
        super(WelcomePage, self).go_next(button)

    def validate(self):
        self.input_data.validate_config_name()
        filename = self.input_data.filename()
        if os.path.exists(filename):
            msg = "A configuraton with the same name already exists in %s. Are you sure you want to REPLACE it?" % filename
            self.yesno_pop_up("Warning", [msg], lambda button: self.render_next_page())
            return False
        return True


class SMPage(FormBase):
    def __init__(self, *args, **kwargs):
        super(SMPage, self).__init__(*args, **kwargs)
        self.form.title = "Subscription Manager"
        self.form.text = "Choose where the host/guest associations should be reported:"
        self.form.add_field("smType", "radio", label=self.input_data.SM_MAP.keys())
        self.next_page = SMConfigPage

    def go_next(self, button):
        for v in self.form.smType:
            if not v.state:
                continue
            self.input_data.smType_label = v.label
            self.input_data.set_sm_type_by_label(v.label)

        super(SMPage, self).go_next(button)

    def validate(self):
        self.input_data.validate_sm_type()
        return True


class SMConfigPage(FormBase):
    FIELDS = {
        "sat": [
            ["sat_server",       "text",     "Server",            0],
            ["sat_username",     "text",     "Username",          0],
            ["sat_password",     "password", "Password",          0],
            ["sat_encrypt_pass", "check",    "Encrypt Password?", 2],
        ],
        "rhsm": [
            ["rhsm_hostname",     "text",     "Hostname",          0],
            ["rhsm_username",     "text",     "Username",          0],
            ["rhsm_password",     "password", "Password",          0],
            ["rhsm_encrypt_pass", "check",    "Encrypt Password?", 2],
        ],
    }

    def __init__(self, *args, **kwargs):
        super(SMConfigPage, self).__init__(*args, **kwargs)

        sm_type = self.input_data.smType
        self.prefix = sm_type if sm_type == "sat" else "rhsm"
        self.form.title = self.input_data.smType_label
        self.form.text = "Please enter Subscripton Manager details."

        if self.prefix == "rhsm":
            self.form.text += " All fields below are OPTIONAL."

        for args in self.FIELDS[self.prefix]:
            self.form.add_field(args[0], args[1], label=args[2], div=args[3])

        encrypt_checkbox = getattr(self.form, "%s_encrypt_pass" % self.prefix)
        encrypt_checkbox.state = True

        self.next_page = VirtPage

    def go_next(self, button):
        self.populate_inputs(self.FIELDS[self.prefix])
        super(SMConfigPage, self).go_next(button)

    def validate(self):
        self.input_data.validate_satellite_config()
        return True


class VirtPage(FormBase):
    def __init__(self, *args, **kwargs):
        super(VirtPage, self).__init__(*args, **kwargs)
        self.form.title = 'Virtualization Backend'
        self.form.text = "Choose a virtualization backend that should be used to gather host/guest associations:"
        self.form.add_field("virtual", "radio", label=self.input_data.VIRT_MAP.keys())
        self.next_page = VirtConfigPage

    def go_next(self, button):
        for v in self.form.virtual:
            if not v.state:
                continue
            self.input_data.set_type_by_label(v.label)

        super(VirtPage, self).go_next(button)

    def validate(self):
        self.input_data.validate_virt_type()
        return True


class VirtConfigPage(FormBase):
    def __init__(self, *args, **kwargs):
        super(VirtConfigPage, self).__init__(*args, **kwargs)
        self.virt_name = self.input_data.humanize_type()
        self.form.title = self.virt_name
        self.form.text = "Please virtualization backend details:"
        self.form.add_field("owner",             "text",     label="Organization")
        self.form.add_field("env",               "text",     label="Environment")
        self.form.add_field("server",            "text",     label="Server")
        self.form.add_field("username",          "text",     label="Username")
        self.form.add_field("password",          "password", label="Password")
        self.form.add_field("hypervisor_label",  "label",    label="How will be the hypervisor identified", value="", div=2)
        self.form.add_field("hypervisor_id",     "radio",    label=self.input_data.HYPERVISOR_IDS)
        self.form.add_field("encrypt_pass",      "check",    label="Encrypt Password?", div=2)
        # Set uuid as default hypervisor id
        self.form.hypervisor_id[0].set_state(True)
        self.form.encrypt_pass.state = True
        self.next_page = DetailPage
        self.next_button_label = "Submit"

    def go_next(self, button):
        fields = ["owner", "env", "server", "username", "password", "encrypt_pass", "hypervisor_id"]
        self.populate_inputs(fields)
        super(VirtConfigPage, self).go_next(button)

    def validate(self):
        self.input_data.validate_virt_config()
        return True


class DetailPage(FormBase):
    def __init__(self, *args, **kwargs):
        super(DetailPage, self).__init__(*args, **kwargs)
        self.form.text = "Processing..."

    def set_pass_state(self, field):
        state = "PASSED"
        field.set_text(('pass', state))

    def set_fail_state(self, field):
        state = "FAILED"
        field.set_text(('fail', state))

    def render(self):
        out = super(DetailPage, self).render()

        self.form.print_text("get_config", label="Configuring your settings")
        has_error = False

        try:
            config = self.input_data.get_config()
            self.set_pass_state(self.form.get_config)
        except (UnwritableKeyFile, InvalidKeyFile, ValueError) as e:
            if isinstance(e, ValueError):
                error = "Failed to parse configuration"
            else:
                error = "Failed encrypt password."
            self.error_pop_up(error, [repr(e)])
            self.set_fail_state(self.form.get_config)
            return out

        # Test to connect to the subscription manager
        self.form.print_text("check_sm_connection", label="Connecting to Subscription Manager")

        errors = self.input_data.check_sm_connection(config)
        if errors:
            self.error_pop_up("Failed to connect to '%s' server" % self.input_data.smType_label, errors)
            self.set_fail_state(self.form.check_sm_connection)
            has_error = True
        else:
            self.set_pass_state(self.form.check_sm_connection)

        # Test to connect to the virtualization backend
        self.form.print_text("check_virt_connection", label="Connecting to Virtualization Backend")

        errors = self.input_data.check_virt_connection(config)
        if errors:
            self.error_pop_up("Failed to connect to '%s' server" %  self.input_data.humanize_type(), errors)
            self.set_fail_state(self.form.check_virt_connection)
            has_error = True
        else:
            self.set_pass_state(self.form.check_virt_connection)

        if has_error:
            return out

        # Write the settings to file
        self.form.print_text("write_config", label="Writing configuraton file")

        try:
            self.input_data.to_ini()
            self.set_pass_state(self.form.write_config)
        except IOError as e:
            self.error_pop_up("Failed to create '%s' configuration file:" % self.input_data.filename(), [repr(e)])
            self.set_fail_state(self.form.write_config)
            return out

        # Start virt-who service
        self.form.print_text("start_service", label="Starting virth-who service")

        error = self.input_data.start_virt_who()
        if error:
            self.error_pop_up("Failed to start virt-who service", [error])
            self.set_fail_state(self.form.start_service)
            return out

        self.set_pass_state(self.form.start_service)

        # Enable virt-who service
        self.form.print_text("enable_service", label="Enabling virth-who service")

        error = self.input_data.enable_virt_who()
        if error:
            self.error_pop_up("Failed to enable virt-who service", [error])
            self.set_fail_state(self.form.enable_service)
            return out

        self.set_pass_state(self.form.enable_service)

        return out