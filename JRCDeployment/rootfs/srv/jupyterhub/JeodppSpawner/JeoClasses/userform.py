import json


class Userform:
    presets = {}
    usecases = {}
    user_presets = {}
    form = {}

    def __init__(self, username, swan_dir):  # Constructor takes three arguments
        self.username = username
        self.swan_dir = swan_dir
        self.presets = dict()
        self.readjsons()

    def readjsons(self):

        with open(self.swan_dir + "/" + 'form_presets.json', "r") as f:
            self.presets = json.load(f)

        with open(self.swan_dir + "/" + 'form_use_cases.json', "r") as f:
            self.usecases = json.load(f)

        with open(self.swan_dir + "/" + 'form_user_presets.json', "r") as f:
            self.user_presets = json.load(f)

    def get_uc_members(self, user1):
        ucs = []
        for presetid, uc in self.usecases.items():
            if user1 in uc["members"]:
                ucs.append(presetid)
        return ucs

    def get_user_presets(self, user):
        ucs = self.user_presets['default']['presets']
        if user in self.user_presets.keys():
            ucs = ucs + self.user_presets[user]['presets']
        return ucs        # return ucs[0]

    def get_by_presetid(self, presetid):
        pre = {}
        for pid, pr in self.presets.items():
            if pid == presetid:
                pre[pid] = pr
        return pre

    def get_preset_by_user(self, u):
        pre = []
        userpresets = self.get_user_presets(u)
        if userpresets:
            for pid in userpresets:
                if self.get_by_presetid(pid):
                    pre.append(self.get_by_presetid(pid))
        return pre

    def get_preset_by_user_ucs(self, u):
        pre = {}
        for pid in self.get_uc_members(u):
            if self.get_by_presetid(pid):
                pre.update({"Use Case: " + pid.upper(): self.get_by_presetid(pid)})

        return pre

    def user_form(self):
        # The code below is valid just from Python 3.8
        form = {}
        p = self.get_preset_by_user_ucs(self.username)
        if p:
            form = p

        parr = self.get_preset_by_user(self.username)
        uform = {}
        if parr:
            for p in parr:
                uform.update(p)
        form.update({"Preset for the user: " + self.username.upper(): uform})
        return form
