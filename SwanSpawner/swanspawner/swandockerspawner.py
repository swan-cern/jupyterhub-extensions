
from .swanspawner import define_SwanSpawner_from
from dockerspawner import SystemUserSpawner
from tornado import gen

import pickle, struct
import calendar, datetime
from socket import (
    socket,
    AF_INET,
    SOCK_STREAM
)

class SwanDockerSpawner(define_SwanSpawner_from(SystemUserSpawner)):

    def send_metrics(self):
        """
        Send user chosen options to the metrics server.
        This will allow us to see what users are choosing from within Grafana.
        """

        metric_path = ".".join([self.graphite_metric_path, self.this_host, self.graphite_base_path])

        d = datetime.datetime.utcnow()
        date = calendar.timegm(d.timetuple())

        metrics = []
        for (key, value) in self.user_options.items():
            if key == self.user_script_env_field:
                path = ".".join([metric_path, key])
                metrics.append((path, (date, 1 if value else 0)))
            else:
                value_cleaned = str(value).replace('/', '_')
                path = ".".join([metric_path, key, value_cleaned])
                # Metrics values are a number
                metrics.append((path, (date, 1)))

        # Serialize the message and send everything in on single package
        payload = pickle.dumps(metrics, protocol=2)
        header = struct.pack("!L", len(payload))
        message = header + payload

        # Send the message
        conn = socket(AF_INET, SOCK_STREAM)
        conn.settimeout(2)
        conn.connect((self.graphite_server, self.graphite_server_port_batch))
        conn.send(message)
        conn.close()

