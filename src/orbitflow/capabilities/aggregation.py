"""Single-device read-only LAG observation using shared transport and CLI."""
from datetime import datetime, timezone
import re
from orbitflow.vendors.aggregation import parse_aggregation, AggregationParserUnsupported
from orbitflow.vendors.common import open_prompt_cli
from orbitflow.vendors.cisco.ios import open_cisco_cli
from orbitflow.vendors.cisco.interfaces import CiscoXRCLI


class AggregationService:
    """Collect the shared explicit configured relationship contract."""
    def __init__(self, *, timeout=30, clock=None):
        self.timeout = timeout
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, session, context, *, cli=None, interfaces=()):
        platform = context.platform
        if platform in {'cisco_ios', 'cisco_xe', 'cisco_xr'}:
            if context.device_family not in {'C3750X', 'C3850', 'ME3600X', 'ASR920', 'NCS540'}:
                raise AggregationParserUnsupported('unsupported aggregation family')
            options = {'cli_type': CiscoXRCLI} if platform == 'cisco_xr' else {}
            manager = open_cisco_cli(session, cli=cli, timeout=self.timeout, **options)
            command = 'show running-config'
        elif platform in {'huawei_vrp', 'ubiquiti_edgeswitch'}:
            huawei = platform == 'huawei_vrp'
            manager = open_prompt_cli(session, cli=cli, timeout=self.timeout,
                paging_command='screen-length 0 temporary' if huawei else 'terminal length 0',
                prompt_pattern=r'^([^\r\n]*(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\]))[ \t]*$' if huawei else r'^([^\r\n]+[>#])[ \t]*$',
                rejected=lambda x: bool(re.search(r'(?i)(?:Error:|Invalid command)', x)),
                platform_name=platform)
            command = 'display current-configuration' if huawei else 'show running-config'
        else:
            raise AggregationParserUnsupported('unsupported aggregation platform')
        with manager as shell:
            output = shell.run_command(command, timeout=self.timeout)
        return parse_aggregation(output, context, (i.port_name for i in interfaces), collection_time=self.clock().isoformat())
