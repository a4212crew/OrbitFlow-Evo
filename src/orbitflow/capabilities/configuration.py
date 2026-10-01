"""Single-device sensitive configuration capture over a borrowed CLI."""
from orbitflow.vendors.configuration import PROFILES


class ConfigurationCaptureError(Exception):
    """Capture was empty, rejected, or unsupported; never includes device output."""


class UnsupportedConfigurationPlatform(ConfigurationCaptureError):
    """No configuration command is approved for the resolved platform."""


class EmptyConfigurationCapture(ConfigurationCaptureError):
    """The configuration command returned no content."""


class ConfigurationCommandRejected(ConfigurationCaptureError):
    """The device rejected the configuration command."""


class ConfigurationService:
    def __init__(self, *, timeout=60.0):
        self.timeout = timeout

    def collect(self, session, context, *, cli):
        cli.require_session(session)
        profile = PROFILES.get(context.platform)
        if profile is None:
            raise UnsupportedConfigurationPlatform("unsupported configuration platform")
        cli.configure(paging_command=profile.paging, prompt_pattern=profile.prompt,
                      rejected=profile.rejected, platform_name=context.platform,
                      timeout=self.timeout)
        text = cli.read_configuration(profile.command, timeout=self.timeout)
        if not text.strip():
            raise EmptyConfigurationCapture("configuration empty")
        if profile.rejected(text):
            raise ConfigurationCommandRejected("configuration command rejected")
        return text
