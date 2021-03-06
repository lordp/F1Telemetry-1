#!/usr/bin/env python

import struct
import wx
from datetime import date
import os
import decimal
import requests

class Packet(object):
    keys = ['time', 'lap_time', 'lap_distance',
            'distance', 'x', 'y', 'z',
            'speed', 'world_speed_x', 'world_speed_y', 'world_speed_z',
            'xr', 'roll', 'zr', 'xd', 'pitch', 'zd',
            'suspension_position_rear_left',
            'suspension_position_rear_right',
            'suspension_position_front_left',
            'suspension_position_front_right',
            'suspension_velocity_rear_left',
            'suspension_velocity_rear_right',
            'suspension_velocity_front_left',
            'suspension_velocity_front_right',
            'wheel_speed_back_left', 'wheel_speed_back_right',
            'wheel_speed_front_left', 'wheel_speed_front_right',
            'throttle', 'steer', 'brake', 'clutch', 'gear',
            'lateral_acceleration', 'longitudinal_acceleration',
            'lap_no', 'engine_revs', 'new_field1',
            'race_position', 'kers_remaining', 'kers_recharge', 'drs_status',
            'difficulty', 'assists', 'fuel_remaining',
            'session_type', 'on_pit_jacks', 'sector', 'time_sector1', 'time_sector2',
            'brake_temperature_rear_left', 'brake_temperature_rear_right',
            'brake_temperature_front_left', 'brake_temperature_front_right',
            'new_field18', 'new_field19', 'new_field20', 'new_field21',
            'completed_laps_in_race', 'total_laps_in_race', 'track_length', 'previous_lap_time',
            'new_field_1301', 'new_field_1302', 'new_field_1303',
            'new_field_1501', 'new_field_1502', 'new_field_1503', 'new_field_1504']

    def __init__(self, data):
        self.data = dict()
        self.decode_raw_packet(data)

    def __getattr__(self, name):
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError

    def __len__(self):
        return struct.calcsize('f' * len(self.keys))

    def decode_raw_packet(self, raw_packet):
        data = list(struct.unpack('f' * len(self.keys), raw_packet))
        self.data = dict(zip(self.keys, data))


class Lap(object):
    def __init__(self, session):
        self.session = session
        self.packets = list()
        self.lap_time = 0
        self.lap_number = 0
        self.sector_1 = None
        self.sector_2 = None
        self.position = 0
        self.top_speed = 0
        self.current_fuel = None

    def get_closest_packet(self, reference_packet):
        def packet_seperation(packet):
            return abs(reference_packet.lap_distance - packet.lap_distance)
        return sorted(self.packets, key=packet_seperation)[0]

    def add_packet(self, packet):
        if packet.time_sector1 > 0 and self.sector_1 is None:
            self.sector_1 = packet.time_sector1

        if packet.time_sector2 > 0 and self.sector_2 is None:
            self.sector_2 = packet.time_sector2

        if self.top_speed < packet.speed:
            self.top_speed = packet.speed

        self.current_fuel = packet.fuel_remaining
        self.position = packet.race_position

        #check if lap has finished, if it hasn't store this packet
        if len(self.packets) > 1 and \
                packet.lap_time < self.packets[-1].lap_time:
            self.finish_lap(packet)
            return False
        self.packets.append(packet)
        return True

    def finish_lap(self, packet):
        self.lap_time = packet.previous_lap_time  # self.packets[-1].lap_time
        self.lap_number = self.packets[-1].lap_no
        del self.packets[:]
        self.session.new_lap()  # this updates current lap to a new lap


class Session(object):
    def __init__(self, logger):
        self.logger = logger
        self.last_lap = None
        self.current_lap = None
        self.fastest_lap = None
        self.top_speed = 0
        self.current_fuel = None
        self.reset_laps()

    def new_lap(self):
        #record a fastest lap if we don't already have one
        if not self.fastest_lap:
            self.fastest_lap = self.current_lap

        #update fastest lap if required
        if self.fastest_lap.lap_time > self.current_lap.lap_time:
            self.fastest_lap = self.current_lap

        if self.top_speed < self.current_lap.top_speed:
            self.top_speed = self.current_lap.top_speed

        if self.current_fuel is None or self.current_fuel > self.current_lap.current_fuel:
            self.current_fuel = self.current_lap.current_fuel

        # create a new lap
        self.logger.lap(self.current_lap)  # todo new thread?
        new_lap = Lap(self)
        self.current_lap = new_lap
        self.laps.append(new_lap)

    def reset_laps(self):
        self.laps = list()
        self.laps.append(Lap(self))
        self.current_lap = self.laps[0]


class ShowLogDialog(wx.Dialog):
    def __init__(self, *args, **kw):
        super(ShowLogDialog, self).__init__(*args, **kw)

        self.SetTitle('Session log')

        self.logctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox = wx.BoxSizer(wx.VERTICAL)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(self, label='Ok')
        hbox.Add(ok_button)
        save_button = wx.Button(self, label='Save')
        hbox.Add(save_button)

        vbox.Add(self.logctrl, proportion=1, flag=wx.ALL | wx.EXPAND, border=5)
        vbox.Add(hbox, flag=wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, border=10)

        self.SetSizer(vbox)

        ok_button.Bind(wx.EVT_BUTTON, self.on_close)
        save_button.Bind(wx.EVT_BUTTON, self.save_log)

    def on_close(self, event):
        self.Destroy()

    def set_content(self, log):
        self.logctrl.SetValue('\n'.join(log))

    def save_log(self, event):
        today = date.today().strftime('%Y-%m-%d')
        counter = 1
        while True:
            if not os.path.isfile('rlc-log-{0}-{1}.log'.format(today, counter)):
                break
            counter += 1

        path = 'rlc-log-{0}-{1}.log'.format(today, counter)
        fp = file(path, 'w')
        fp.write(self.logctrl.GetValue())
        fp.close()

        wx.MessageBox('Log saved to {0}'.format(path), 'Info', wx.OK | wx.ICON_INFORMATION)


class SettingsDialog(wx.Dialog):
    def __init__(self, *args, **kw):
        super(SettingsDialog, self).__init__(*args, **kw)

        self.parent = args[0]

        self.SetTitle('Settings')

        self.SetBackgroundColour("white")
        self.SetSize((250, 475))

        sizer = wx.BoxSizer(wx.VERTICAL)

        general_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)

        general_sizer = wx.StaticBoxSizer(wx.StaticBox(general_panel, wx.ID_ANY, u"General"), wx.VERTICAL)

        general_token = wx.BoxSizer(wx.HORIZONTAL)

        general_token_label = wx.StaticText(
            general_panel, wx.ID_ANY, u"Auth Token:", wx.DefaultPosition, wx.DefaultSize, 0
        )
        general_token.Add(general_token_label, 0, wx.TOP, 9)

        self.general_token_text = wx.TextCtrl(
            general_panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.general_token_text.Bind(wx.EVT_KILL_FOCUS, self.update_drivers)
        general_token.Add(self.general_token_text, 1, wx.ALL, 5)

        general_sizer.Add(general_token, 1, wx.EXPAND, 5)

        general_name = wx.BoxSizer(wx.HORIZONTAL)

        general_name_label = wx.StaticText(general_panel, wx.ID_ANY, u"Name:", wx.DefaultPosition, wx.DefaultSize, 0)
        general_name_label.Wrap(-1)
        general_name.Add(general_name_label, 0, wx.TOP, 9)

        self.general_name_combo = wx.ComboBox(general_panel, wx.ID_ANY, '', style=wx.CB_SORT | wx.CB_READONLY)
        general_name.Add(self.general_name_combo, 1, wx.ALL, 5)

        general_sizer.Add(general_name, 1, wx.EXPAND, 5)

        general_panel.SetSizer(general_sizer)
        general_panel.Layout()
        general_sizer.Fit(general_panel)

        sizer.Add(general_panel, 1, wx.ALL | wx.EXPAND, 5)

        # F1 options
        f1_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
        f1_sizer = wx.StaticBoxSizer(wx.StaticBox(f1_panel, wx.ID_ANY, u"Codemasters F1"), wx.VERTICAL)

        f1_config_location = wx.BoxSizer(wx.HORIZONTAL)

        f1_config_location_button = wx.Button(f1_panel, wx.ID_ANY, u"&Locate Config", wx.DefaultPosition, wx.DefaultSize, 0)
        f1_config_location_button.Bind(wx.EVT_BUTTON, self.locate_config)

        f1_config_location.Add(f1_config_location_button, 1, wx.ALL, 5)

        f1_sizer.Add(f1_config_location, 1, wx.EXPAND, 5)

        self.enable_general = wx.CheckBox(f1_panel, wx.ID_ANY, u"Enable", wx.DefaultPosition, wx.DefaultSize, 0)
        f1_sizer.Add(self.enable_general, 0, wx.ALL, 0)

        f1_port = wx.BoxSizer(wx.HORIZONTAL)

        f1_port_label = wx.StaticText(f1_panel, wx.ID_ANY, u"Port:", wx.DefaultPosition, wx.DefaultSize, 0)
        f1_port.Add(f1_port_label, 0, wx.TOP, 9)

        self.f1_port_text = wx.TextCtrl(
            f1_panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0
        )
        f1_port.Add(self.f1_port_text, 1, wx.ALL, 5)

        f1_sizer.Add(f1_port, 1, wx.EXPAND, 5)

        f1_panel.SetSizer(f1_sizer)
        f1_panel.Layout()
        f1_sizer.Fit(f1_panel)

        sizer.Add(f1_panel, 1, wx.ALL | wx.EXPAND, 5)

        # Local mode options
        local_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
        local_sizer = wx.StaticBoxSizer(wx.StaticBox(local_panel, wx.ID_ANY, u'Local Mode'), wx.VERTICAL)
        self.enable_local_mode = wx.CheckBox(local_panel, wx.ID_ANY, u"Enable", wx.DefaultPosition, wx.DefaultSize, 0)
        local_sizer.Add(self.enable_local_mode, 0, wx.ALL, 5)
        local_panel.SetSizer(local_sizer)
        local_panel.Layout()
        local_sizer.Fit(local_panel)

        sizer.Add(local_panel, 1, wx.ALL | wx.EXPAND, 5)

        # Forwarding options
        forwarding_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)

        forwarding_sizer = wx.StaticBoxSizer(wx.StaticBox(forwarding_panel, wx.ID_ANY, u"Forwarding"), wx.VERTICAL)

        self.enable_forwarding = wx.CheckBox(
            forwarding_panel, wx.ID_ANY, u"Enable", wx.DefaultPosition, wx.DefaultSize, 0
        )
        forwarding_sizer.Add(self.enable_forwarding, 0, wx.ALL, 5)

        forwarding_host = wx.BoxSizer(wx.HORIZONTAL)

        forwarding_host_label = wx.StaticText(
            forwarding_panel, wx.ID_ANY, u"Host:", wx.DefaultPosition, wx.DefaultSize, 0
        )
        forwarding_host.Add(forwarding_host_label, 0, wx.TOP, 9)

        self.forwarding_host_text = wx.TextCtrl(
            forwarding_panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0
        )
        forwarding_host.Add(self.forwarding_host_text, 1, wx.ALL, 5)

        forwarding_sizer.Add(forwarding_host, 1, wx.EXPAND, 5)

        forwarding_port = wx.BoxSizer(wx.HORIZONTAL)

        forwarding_port_label = wx.StaticText(
            forwarding_panel, wx.ID_ANY, u"Port:", wx.DefaultPosition, wx.DefaultSize, 0
        )
        forwarding_port.Add(forwarding_port_label, 0, wx.TOP, 9)

        self.forwarding_port_text = wx.TextCtrl(
            forwarding_panel, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, 0
        )
        forwarding_port.Add(self.forwarding_port_text, 1, wx.ALL, 5)

        forwarding_sizer.Add(forwarding_port, 1, wx.EXPAND, 5)

        forwarding_panel.SetSizer(forwarding_sizer)
        forwarding_panel.Layout()
        forwarding_sizer.Fit(forwarding_panel)

        sizer.Add(forwarding_panel, 1, wx.ALL | wx.EXPAND, 5)

        buttons = wx.BoxSizer(wx.HORIZONTAL)

        save_button = wx.Button(self, wx.ID_OK, u"&Save", wx.DefaultPosition, wx.DefaultSize, 0)
        buttons.Add(save_button, 0, wx.ALL, 5)

        cancel_button = wx.Button(self, wx.ID_CANCEL, u"&Cancel", wx.DefaultPosition, wx.DefaultSize, 0)
        buttons.Add(cancel_button, 0, wx.ALL, 5)

        sizer.Add(buttons, 1, wx.ALIGN_CENTER_HORIZONTAL, 5)

        self.SetSizer(sizer)
        self.Layout()

    def update_ui(self, config):
        self.enable_general.SetValue(config['game_enabled'])
        self.f1_port_text.SetValue(config['f1_port'])
        self.general_token_text.SetValue(config['token'])
        self.general_name_combo.SetItems(self.get_drivers())

        self.select_driver()

        self.enable_local_mode.SetValue(config['local_enabled'])

        self.enable_forwarding.SetValue(config['forwarding_enabled'])
        self.forwarding_host_text.SetValue(config['forwarding_host'])
        self.forwarding_port_text.SetValue(config['forwarding_port'])

        return True

    def get_drivers(self):
        try:
            token = self.general_token_text.GetValue()
            req = requests.get('https://racingleaguecharts.com/drivers.json?token={0}'.format(token), verify=False)
            if req.status_code == 200:
                return req.json()['drivers']
            else:
                raise requests.exceptions.RequestException
        except requests.exceptions.RequestException:
            return []

    def update_drivers(self, event):
        self.general_name_combo.SetItems(self.get_drivers())
        self.select_driver()

    def select_driver(self):
        if self.parent.config['name'] in self.general_name_combo.GetItems():
            self.general_name_combo.SetValue(self.parent.config['name'])
        else:
            options = self.general_name_combo.GetItems()
            if len(options) > 0:
                self.general_name_combo.SetValue(options[0])
                self.parent.config['name'] = options[0]
            else:
                self.parent.config['name'] = None

    def locate_config(self, event):
        locate_file_dialog = wx.FileDialog(self, "Locate", "", "",
                                           "Config File (hardware_settings_config.xml)|hardware_settings_config.xml",
                                           wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        locate_file_dialog.ShowModal()
        self.parent.config['game_config'] = locate_file_dialog.GetPath()
        self.parent.config['game_config_missing'] = False
        self.parent.load_game_config()

        self.enable_general.SetValue(self.parent.config['game_enabled'])
        self.f1_port_text.SetValue(self.parent.config['f1_port'])

        locate_file_dialog.Destroy()

class Instructions(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, id, title, ((600, 200)), wx.Size(450, 200))

        panel = wx.Panel(self, -1)

        headertext = "Instructions"

        header = wx.StaticText(panel, -1, headertext, (10, 15), style=wx.ALIGN_CENTRE)
        header.SetFont(wx.Font(14, 70, 90, 92, False, wx.EmptyString))

        text = ("1. Click the settings button to open the settings window\n"
                "2. Choose your name from the dropdown list\n"
                "3. (Optional) Change the port this app runs on. (Only do this if another app already uses this port)\n"
                "4. Press start and run the game\n"
                "5. Keep note of the session ID for the race and forward it to your race organiser.")

        instructionstext = wx.StaticText(panel, -1, text, (10, 50), style=wx.ALIGN_LEFT)
        instructionstext.SetMinSize(wx.Size(430, 100))
        instructionstext.SetMaxSize(wx.Size(430, 200))
        instructionstext.Wrap(-1)
