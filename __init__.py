# Copyright 2018 Lukas Gangel
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import speedtest

from ovos_utils.log import LOG
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill


class SpeedTestSkill(OVOSSkill):

    @intent_handler(IntentBuilder("SpeedtestIntent").require("Run").require("Speedtest"))
    def handle_speedtest_intent(self, message):
        LOG.info("speedtest started")
        try:
            self.speak_dialog('running')
            servers = []
            speed = speedtest.Speedtest()
            speed.get_servers(servers)
            speed.get_best_server()
            speed.download()
            speed.upload(pre_allocate=False)
            speed.results.share()
            result = speed.results.dict()
            downspeed = ('%.2f' % float((result["download"])/1000000))
            upspeed = ('%.2f' % float((result["upload"])/1000000))
            self.speak_dialog('result', {'DOWN': downspeed,'UP': upspeed})
        except:
            self.speak_dialog("error")
        LOG.info("speedtest finished")
